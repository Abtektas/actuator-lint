# SPDX-License-Identifier: BSD-3-Clause
"""Checks of a Gazebo (gz-sim) vehicle model, for the option --sdf.

The model is read with a small SDFormat reader of this module instead of libsdformat, so that the
tool keeps needing nothing but Python. It covers what vehicle models for PX4's gz simulation use:
links, joints, frames, nested models, <include> with and without merge, poses with relative_to,
joint axes with expressed_in or use_parent_model_frame, and SDFormat 1.4 to 1.11. The tests compare
its poses and axes with libsdformat when its Python bindings are installed.

The facts the rules rest on, and the simulation runs that show each failure, are in the documents
of the rules (rules/SDF*.md). Where a rule repeats behaviour of PX4 or gz-sim, the document names
the source file it follows.
"""

from __future__ import annotations

import math
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .rules import ERROR, RULES, WARNING, Finding, Result

GRAVITY = 9.81
# W1 (SDF001): the system each sensor type needs when the world does not load server.config
_SENSOR_SYSTEMS = {
    "imu": "Imu",
    "air_pressure": "AirPressure",
    "magnetometer": "Magnetometer",
    "navsat": "NavSat",
    "air_speed": "AirSpeed",
}
_RENDERING_SENSORS = {
    "camera",
    "depth_camera",
    "rgbd_camera",
    "gpu_lidar",
    "gpu_ray",
    "thermal_camera",
    "segmentation_camera",
    "boundingbox_camera",
    "wide_angle_camera",
}
# M1 (SDF002): the sensors the bridge subscribes to on base_link (GZBridge.cpp), and the parameter
# with which PX4 simulates the sensor itself instead
_BRIDGE_SENSORS = (
    ("imu", "imu_sensor", None),
    ("air_pressure", "air_pressure_sensor", "SENS_EN_BAROSIM"),
    ("magnetometer", "magnetometer_sensor", "SENS_EN_MAGSIM"),
    ("navsat", "navsat_sensor", "SENS_EN_GPSSIM"),
)
# R3 (SDF012): the topic GZMixingInterfaceESC publishes motor speeds on, below the model name
MOTOR_TOPIC = "command/motor_speed"
# R4 (SDF013): below this thrust to weight ratio a warning; PX4's own multicopters have 1.41 or more
LOW_THRUST_TO_WEIGHT = 1.3
# R1 (SDF010): smallest |cos| between the thrust axis and the spin axis
_MIN_AXIS_COS = 0.99
# G1 (SDF020): shape difference, as a share of the arm, above which a rotor is reported. PX4's own
# models fly with up to 25%: x500 of v1.17.0, standard_vtol and tiltrotor of main (2026-11).
_MAX_SHAPE_OFFSET = 0.30

Vector = tuple[float, float, float]
Matrix = tuple[Vector, Vector, Vector]
_IDENTITY: Matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


class SdfError(Exception):
    """The model or the world cannot be read."""


class SdfSkipped(Exception):
    """The model cannot be checked offline, for example because it includes a model from a server."""


@dataclass(frozen=True)
class Pose:
    position: Vector = (0.0, 0.0, 0.0)
    rotation: Matrix = _IDENTITY

    def rotate(self, vector: Vector) -> Vector:
        return tuple(sum(row[i] * vector[i] for i in range(3)) for row in self.rotation)

    def __mul__(self, other: Pose) -> Pose:
        """This pose followed by other, which is expressed in this pose's frame."""
        rotation = tuple(
            tuple(sum(self.rotation[r][k] * other.rotation[k][c] for k in range(3)) for c in range(3))
            for r in range(3)
        )
        moved = self.rotate(other.position)
        return Pose(tuple(a + b for a, b in zip(self.position, moved)), rotation)


def _rpy(roll: float, pitch: float, yaw: float) -> Matrix:
    cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch),
                              math.cos(yaw), math.sin(yaw))
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def _quaternion(x: float, y: float, z: float, w: float) -> Matrix:
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def _numbers(text: str | None, where: str) -> list[float]:
    try:
        return [float(part) for part in (text or "").split()]
    except ValueError:
        raise SdfError(f"{where}: '{text}' is not a list of numbers") from None


def _pose(element: ET.Element | None, where: str) -> Pose:
    if element is None or not (element.text or "").strip():
        return Pose()

    values = _numbers(element.text, where)

    if element.get("rotation_format", "euler_rpy") == "quat_xyzw":
        if len(values) != 7:
            raise SdfError(f"{where}: a pose in quat_xyzw needs 7 numbers")
        return Pose(tuple(values[:3]), _quaternion(*values[3:]))

    if len(values) != 6:
        raise SdfError(f"{where}: a pose needs 6 numbers, not '{element.text.strip()}'")

    angles = values[3:]

    if element.get("degrees", "false").strip().lower() in ("true", "1"):
        angles = [math.radians(angle) for angle in angles]

    return Pose(tuple(values[:3]), _rpy(*angles))


def _text(element: ET.Element, tag: str, default: str = "") -> str:
    child = element.find(tag)
    return default if child is None or child.text is None else child.text.strip()


def _number(element: ET.Element | None, tag: str, default: float | None) -> float | None:
    if element is None or element.find(tag) is None:
        return default

    values = _numbers(element.find(tag).text, tag)
    return values[0] if values else default


_PREFIX = re.compile(r"[<\s]([A-Za-z_][\w.-]*):[A-Za-z_]")
_ROOT_TAG = re.compile(r"<(?![?!])[\w:.-]+")


def parse_xml(path: str | Path) -> ET.Element:
    """Parse an SDF file. Like libsdformat, accept prefixes such as gz: that the file does not declare."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise SdfError(f"{path}: {error.strerror}") from None
    except UnicodeDecodeError:
        raise SdfError(f"{path}: not a UTF-8 text file") from None

    prefixes = set(_PREFIX.findall(text)) - {"xml", "xmlns"}
    declared = set(re.findall(r"xmlns:([\w.-]+)=", text))
    root = _ROOT_TAG.search(text)

    if root and prefixes - declared:
        extra = "".join(f' xmlns:{prefix}="urn:sdf-extension:{prefix}"' for prefix in sorted(prefixes - declared))
        text = text[: root.end()] + extra + text[root.end() :]

    try:
        return ET.fromstring(text)
    except ET.ParseError as error:
        raise SdfError(f"{path}: {error}") from None


def _version(root: ET.Element) -> tuple[int, int]:
    try:
        major, minor = root.get("version", "1.9").split(".")[:2]
        return int(major), int(minor)
    except ValueError:
        return 1, 9


@dataclass
class Link:
    name: str
    mass: float
    sensors: list[tuple[str, str]] = field(default_factory=list)  # (name, type)


@dataclass
class Joint:
    name: str
    type: str
    parent: str
    child: str
    axis: Vector | None
    axis_frame: str  # the frame the axis is expressed in
    lower: float
    upper: float
    velocity: float | None


@dataclass
class Model:
    path: Path
    links: dict[str, Link] = field(default_factory=dict)
    joints: dict[str, Joint] = field(default_factory=dict)
    # frame name -> (the frame its pose is relative to, the pose)
    frames: dict[str, tuple[str, Pose]] = field(default_factory=dict)
    plugins: list[dict[str, str]] = field(default_factory=list)
    _resolved: dict[str, Pose] = field(default_factory=dict)

    def pose(self, frame: str) -> Pose:
        """The pose of a frame in the model frame (__model__)."""
        chain = []

        while frame != "__model__" and frame not in self._resolved:
            if frame not in self.frames:
                raise SdfError(f"{self.path}: unknown frame '{frame}'")
            if frame in chain:
                raise SdfError(f"{self.path}: the poses of {', '.join(chain)} refer to each other")
            chain.append(frame)
            frame = self.frames[frame][0]

        pose = Pose() if frame == "__model__" else self._resolved[frame]

        for name in reversed(chain):
            pose = pose * self.frames[name][1]
            self._resolved[name] = pose

        return pose

    def axis(self, joint: Joint) -> Vector:
        """The joint axis in the model frame, as a unit vector like libsdformat gives it."""
        axis = self.pose(joint.axis_frame).rotate(joint.axis or (0.0, 0.0, 1.0))
        length = math.sqrt(sum(value * value for value in axis)) or 1.0
        return tuple(value / length for value in axis)


def model_file(path: str | Path) -> Path:
    """The SDF file of a model directory (its model.config, else model.sdf), or the file itself."""
    path = Path(path)

    if path.is_dir():
        config = path / "model.config"

        if config.is_file():
            entries = parse_xml(config).findall("sdf")

            # the newest SDFormat version the model offers
            entries.sort(key=lambda entry: _version(entry), reverse=True)

            for entry in entries:
                if entry.text and (path / entry.text.strip()).is_file():
                    return path / entry.text.strip()

        path = path / "model.sdf"

    if not path.is_file():
        raise SdfError(f"{path}: no such model file")

    return path


def search_path(model: Path) -> list[Path]:
    """Where model:// URIs are looked up: next to the model, then GZ_SIM_RESOURCE_PATH."""
    paths = [model.parent.parent if model.name.endswith(".sdf") else model.parent]
    paths += [Path(part) for part in os.environ.get("GZ_SIM_RESOURCE_PATH", "").split(os.pathsep) if part]
    return paths


def _include_path(uri: str, base: Path, search: list[Path]) -> Path:
    if uri.startswith(("http://", "https://")):
        raise SdfSkipped(f"it includes {uri}, which needs a download")

    for scheme in ("model://", "file://"):
        if uri.startswith(scheme):
            uri = uri[len(scheme):]

    if os.path.isabs(uri):
        return model_file(uri)

    for directory in (*search, base):
        if (directory / uri).exists():
            return model_file(directory / uri)

    raise SdfError(f"cannot find the included model '{uri}' in {', '.join(str(d) for d in (*search, base))}")


class _Reader:
    def __init__(self, path: Path, search: list[Path]):
        self.model = Model(path)
        self.search = search
        self.depth = 0

    def read_file(self, path: Path) -> tuple[ET.Element, tuple[int, int]]:
        root = parse_xml(path)
        element = root.find("model") if root.tag == "sdf" else None

        if element is None and root.tag == "sdf" and root.find("include") is not None:
            # a model file that only includes another model, for example one on a server
            include = root.find("include")
            self.depth += 1

            if self.depth > 20:
                raise SdfError(f"{path}: includes nest deeper than 20, is there a loop?")

            return self.read_file(_include_path(_text(include, "uri"), path.parent, self.search))

        if element is None:
            raise SdfError(f"{path}: no <model> in the file")

        return element, _version(root)

    def ref(self, name: str, scope: str, model_frame: str) -> str:
        if name in ("", "__model__"):
            return model_frame
        return name if name == "world" else scope + name

    def frame(self, name: str, element: ET.Element, scope: str, model_frame: str, default: str, where: str):
        pose = element.find("pose")
        relative_to = pose.get("relative_to", "") if pose is not None else ""
        parent = self.ref(relative_to, scope, model_frame) if relative_to else default
        self.model.frames[name] = (parent, _pose(pose, where))

    def read(self, element: ET.Element, version: tuple[int, int], path: Path, scope: str, model_frame: str):
        model = self.model
        link_names = {child.get("name", "") for child in element if child.tag == "link"}

        for child in element:
            name = child.get("name", "")
            where = f"{path}: {child.tag} '{name}'"

            if child.tag == "joint" and version < (1, 7) and name in link_names:
                name += "_joint"  # as libsdformat does when SDFormat 1.6 and older share a name

            if child.tag == "link":
                self.frame(scope + name, child, scope, model_frame, model_frame, where)
                mass = _number(child.find("inertial"), "mass", 1.0)
                sensors = [(sensor.get("name", ""), sensor.get("type", "")) for sensor in child.findall("sensor")]
                model.links[scope + name] = Link(scope + name, mass, sensors)

            elif child.tag == "joint":
                joint_child = self.ref(_text(child, "child"), scope, model_frame)
                self.frame(scope + name, child, scope, model_frame, joint_child, where)
                axis = child.find("axis")
                xyz = axis.find("xyz") if axis is not None else None
                vector = tuple(_numbers(xyz.text, where)) if xyz is not None else None

                if vector is not None and len(vector) != 3:
                    raise SdfError(f"{where}: the axis needs 3 numbers")

                if xyz is not None and xyz.get("expressed_in"):
                    axis_frame = self.ref(xyz.get("expressed_in"), scope, model_frame)
                elif axis is not None and (
                    version < (1, 5)
                    or (version < (1, 7) and _text(axis, "use_parent_model_frame").lower() in ("true", "1"))
                ):
                    axis_frame = model_frame
                else:
                    axis_frame = scope + name

                limit = axis.find("limit") if axis is not None else None
                model.joints[scope + name] = Joint(
                    name=scope + name,
                    type=child.get("type", ""),
                    parent=self.ref(_text(child, "parent"), scope, model_frame),
                    child=joint_child,
                    axis=vector,
                    axis_frame=axis_frame,
                    lower=_number(limit, "lower", -1e16),
                    upper=_number(limit, "upper", 1e16),
                    velocity=_number(limit, "velocity", None),
                )

            elif child.tag == "frame":
                attached = self.ref(child.get("attached_to", ""), scope, model_frame)
                self.frame(scope + name, child, scope, model_frame, attached, where)

            elif child.tag == "plugin":
                self.plugin(child, scope)

            elif child.tag == "model":
                self.frame(scope + name, child, scope, model_frame, model_frame, where)
                self.read(child, version, path, scope + name + "::", scope + name)

            elif child.tag == "include":
                self.include(child, path, scope, model_frame)

    def include(self, element: ET.Element, path: Path, scope: str, model_frame: str):
        uri = _text(element, "uri")
        self.depth += 1

        if self.depth > 20:
            raise SdfError(f"{path}: includes nest deeper than 20, is there a loop?")

        included_path = _include_path(uri, path.parent, self.search)
        included, version = self.read_file(included_path)
        name = _text(element, "name") or included.get("name", "")
        where = f"{path}: include '{uri}'"
        # the pose of the include, else the pose the included model gives itself
        pose_element = element if element.find("pose") is not None else included

        if element.get("merge", "false").strip().lower() in ("true", "1"):
            frame = f"{scope}_merged__{name}__model__"
            self.frame(frame, pose_element, scope, model_frame, model_frame, where)
            self.read(included, version, included_path, scope, frame)
            inner = scope
        else:
            self.frame(scope + name, pose_element, scope, model_frame, model_frame, where)
            self.read(included, version, included_path, scope + name + "::", scope + name)
            inner = scope + name + "::"

        for plugin in element.findall("plugin"):
            self.plugin(plugin, inner)

        self.depth -= 1

    def plugin(self, element: ET.Element, scope: str):
        values = {child.tag: (child.text or "").strip() for child in element}
        values["_name"] = element.get("name", "")
        values["_filename"] = element.get("filename", "")
        values["_scope"] = scope
        self.model.plugins.append(values)


def read_model(path: str | Path) -> Model:
    """Read a model directory or SDF file, with its includes."""
    path = model_file(path)
    reader = _Reader(path, search_path(path))
    element, version = reader.read_file(path)
    reader.read(element, version, path, "", "__model__")
    return reader.model


def world_systems(path: str | Path) -> set[str] | None:
    """The systems a world file loads itself (the last part of each plugin name), None for none."""
    world = parse_xml(path).find("world")

    if world is None:
        raise SdfError(f"{path}: no <world> in the file")

    names = {plugin.get("name", "").split("::")[-1] for plugin in world.findall("plugin")}
    return names or None


def _float(params: dict[str, str], name: str) -> float | None:
    try:
        return float(params[name])
    except (KeyError, ValueError):
        return None


def _dot(first: Vector, second: Vector) -> float:
    return sum(a * b for a, b in zip(first, second))


def _norm(vector: Vector) -> float:
    return math.sqrt(_dot(vector, vector))


def _round(vector: Vector) -> str:
    return "(" + ", ".join(f"{value:.2f}" for value in vector) + ")"


def _finding(rule: str, message: str, level: str | None = None) -> Finding:
    return Finding(rule=rule, level=level or RULES[rule].level, message=message)


def _motor_plugins(model: Model) -> list[dict[str, str]]:
    return [plugin for plugin in model.plugins if "MulticopterMotorModel" in plugin["_name"] + plugin["_filename"]
            or "multicopter-motor-model" in plugin["_filename"]]


def _check_world(model: Model, world: str | None, result: Result) -> None:
    if world is None:
        result.not_checked["SDF001"] = "no world file given (--world)"
        return

    systems = world_systems(world)

    if systems is None:
        return  # gz-sim loads server.config, which has every system a PX4 vehicle needs

    types = {sensor_type for link in model.links.values() for _, sensor_type in link.sensors}
    needed = {"Physics"} | {_SENSOR_SYSTEMS[t] for t in types if t in _SENSOR_SYSTEMS}

    if types & _RENDERING_SENSORS:
        needed.add("Sensors")

    for system in sorted(needed - systems):
        result.findings.append(
            _finding(
                "SDF001",
                f"{Path(world).name} loads its own systems, so gz-sim does not load server.config, "
                f"and the {system} system is not among them",
            )
        )


def _check_sensors(model: Model, params: dict[str, str], result: Result) -> None:
    base = model.links.get("base_link")
    names = [name for name, _ in base.sensors] if base else []

    for sensor_type, name, simulated in _BRIDGE_SENSORS:
        if any(found == name or found.startswith(name + "_") for found in names):
            continue

        if simulated and _float(params, simulated) == 1:
            continue  # PX4 simulates this sensor itself

        turned_off = (sensor_type == "navsat" and _float(params, "SYS_HAS_GPS") == 0) or (
            sensor_type == "magnetometer" and _float(params, "SYS_HAS_MAG") == 0
        )
        where = "the model has no link 'base_link'" if base is None else f"no sensor '{name}' on base_link"
        result.findings.append(
            _finding("SDF002", f"{where}: PX4 gets no {sensor_type} data", WARNING if turned_off else None)
        )


def _check_rotors(model: Model, params: dict[str, str], result: Result) -> dict:
    motors = _motor_plugins(model)
    numbers = []
    rotors = {}
    thrust_up = 0.0
    unread = False

    for motor in motors:
        scope = motor["_scope"]
        link_name, joint_name = motor.get("linkName", ""), motor.get("jointName", "")
        label = f"motor on '{link_name}'"

        if motor.get("commandSubTopic", "") != MOTOR_TOPIC:
            result.findings.append(
                _finding(
                    "SDF012",
                    f"{label}: commandSubTopic '{motor.get('commandSubTopic', '')}' is not '{MOTOR_TOPIC}'",
                )
            )

        if motor.get("robotNamespace"):
            result.findings.append(
                _finding("SDF012", f"{label}: robotNamespace '{motor['robotNamespace']}' moves the command topic")
            )

        try:
            number = int(float(motor.get("motorNumber", "")))
        except ValueError:
            number = None

        numbers.append(number)
        link = model.links.get(scope + link_name)
        joint = model.joints.get(scope + joint_name)

        if link is None or joint is None:
            result.findings.append(
                _finding("SDF012", f"{label}: the model has no link '{link_name}' or no joint '{joint_name}'")
            )
            unread = True
            continue

        thrust_axis = model.pose(link.name).rotate((0.0, 0.0, 1.0))
        spin_axis = model.axis(joint)
        cos = abs(_dot(thrust_axis, spin_axis)) / ((_norm(thrust_axis) * _norm(spin_axis)) or 1.0)

        if cos < _MIN_AXIS_COS:
            result.findings.append(
                _finding(
                    "SDF010",
                    f"{link_name}: the thrust axis {_round(thrust_axis)} (link z) is not along the spin axis "
                    f"{_round(spin_axis)} of {joint_name} (cos {cos:.2f}); both in the model frame",
                )
            )

        max_velocity = _number_of(motor, "maxRotVelocity", 0.0)
        slowdown = _number_of(motor, "rotorVelocitySlowdownSim", 10.0) or 10.0

        if joint.type not in ("revolute", "continuous"):
            result.findings.append(_finding("SDF011", f"{joint_name}: a joint of type '{joint.type}' cannot spin"))

        else:
            if joint.type == "revolute" and joint.upper - joint.lower < 2 * math.pi:
                result.findings.append(
                    _finding(
                        "SDF011",
                        f"{joint_name}: the position limits {joint.lower:g} to {joint.upper:g} stop the rotor",
                    )
                )

            needed = max_velocity / slowdown

            if joint.velocity is not None and 0 < joint.velocity < needed * 0.999:
                result.findings.append(
                    _finding(
                        "SDF011",
                        f"{joint_name}: the velocity limit {joint.velocity:g} rad/s is below "
                        f"maxRotVelocity / rotorVelocitySlowdownSim = {needed:.1f} rad/s",
                    )
                )

        if number is None:
            continue

        command_max = _float(params, f"SIM_GZ_EC_MAX{number + 1}")
        speed = max_velocity if command_max is None else min(max_velocity, command_max)
        thrust = _number_of(motor, "motorConstant", 0.0) * speed**2
        up = _dot(thrust_axis, (0.0, 0.0, 1.0))
        thrust_up += thrust * max(0.0, up)
        position = model.pose(link.name).position
        rotors[number] = {"x": position[0], "y": position[1], "direction": motor.get("turningDirection"), "up": up}

    if motors and sorted(n for n in numbers if n is not None) != list(range(len(numbers))):
        shown = ", ".join("?" if n is None else str(n) for n in sorted(numbers, key=lambda n: (n is None, n)))
        result.findings.append(
            _finding("SDF012", f"the motorNumber values ({shown}) are not 0 to {len(numbers) - 1}, each once")
        )

    mass = sum(link.mass for link in model.links.values())
    ratio = thrust_up / (mass * GRAVITY) if mass > 0 else 0.0
    hover = any(rotor["up"] > 0.7 for rotor in rotors.values())

    if unread:
        result.not_checked["SDF013"] = "a motor plugin names a link or joint that the model does not have"

    elif hover and ratio <= 1.0:
        result.findings.append(
            _finding(
                "SDF013",
                f"thrust to weight {ratio:.2f}: the rotors give {thrust_up:.1f} N upwards at full speed, "
                f"the model weighs {mass * GRAVITY:.1f} N ({mass:.3f} kg)",
            )
        )

    elif hover and ratio < LOW_THRUST_TO_WEIGHT:
        result.findings.append(
            _finding(
                "SDF013",
                f"thrust to weight {ratio:.2f} leaves little margin for control "
                f"(PX4's own multicopter models have 1.41 or more)",
                WARNING,
            )
        )

    _check_allocation(motors, rotors, params, result)
    return {
        "motor_plugins": len(motors),
        "mass_kg": round(mass, 4),
        "thrust_up_n": round(thrust_up, 3),
        "thrust_to_weight": round(ratio, 3) if motors else None,
    }


def _number_of(plugin: dict[str, str], name: str, default: float) -> float:
    try:
        return float(plugin[name])
    except (KeyError, ValueError):
        return default


def _check_allocation(motors: list[dict], rotors: dict[int, dict], params: dict[str, str], result: Result) -> None:
    count = _float(params, "CA_ROTOR_COUNT")

    if not motors:
        return

    if count is None:
        result.not_checked["SDF020"] = "the parameter file does not set CA_ROTOR_COUNT"
        return

    if int(count) != len(motors):
        result.findings.append(
            _finding("SDF020", f"the model has {len(motors)} motor plugins, CA_ROTOR_COUNT is {int(count)}")
        )

    pairs = []

    for number, rotor in sorted(rotors.items()):
        function = _float(params, f"SIM_GZ_EC_FUNC{number + 1}")

        if function is None or not 101 <= function <= 112:
            continue  # not a motor output, or not set

        index = int(function) - 101
        x, y = _float(params, f"CA_ROTOR{index}_PX"), _float(params, f"CA_ROTOR{index}_PY")

        if x is not None and y is not None:
            # SDF is x forward, y left (FLU); CA_ROTORn_PX/PY are x forward, y right (FRD)
            pairs.append((number, index, (rotor["x"], -rotor["y"]), (x, y)))

    if not pairs:
        return

    # Control allocation normalises multicopter effectiveness, so only the shape counts. One size
    # ratio (RMS arm) brings the model to the size of CA_ROTORn_P*; a swapped rotor cannot change it.
    model_size = sum(_dot(a, a) for _, _, a, _ in pairs)
    scale = math.sqrt(sum(_dot(b, b) for _, _, _, b in pairs) / model_size) if model_size else 1.0
    arm = max(math.hypot(*b) for _, _, _, b in pairs) or 1.0

    for number, index, at, ca in pairs:
        dead_zone = 0.1 * arm
        flipped = [
            axis
            for axis, model_value, ca_value in (("x", at[0] * scale, ca[0]), ("y", at[1] * scale, ca[1]))
            if abs(model_value) > dead_zone and abs(ca_value) > dead_zone and (model_value > 0) != (ca_value > 0)
        ]
        place = f"sits at ({at[0]:.3f}, {at[1]:.3f}) FRD, CA_ROTOR{index} is at ({ca[0]:g}, {ca[1]:g})"

        if flipped:
            result.findings.append(
                _finding(
                    "SDF020",
                    f"motorNumber {number} drives CA rotor {index} (SIM_GZ_EC_FUNC{number + 1}) but the sign "
                    f"of {' and '.join(flipped)} differs: it {place}",
                )
            )
            continue

        offset = math.hypot(at[0] * scale - ca[0], at[1] * scale - ca[1]) / arm

        if offset > _MAX_SHAPE_OFFSET:
            result.findings.append(
                _finding(
                    "SDF020",
                    f"motorNumber {number}: the rotor layout differs from CA rotor {index} by {offset:.0%} of the "
                    f"arm after scaling: it {place}",
                    WARNING,
                )
            )

    for number, index, _, _ in pairs:
        moment = _float(params, f"CA_ROTOR{index}_KM")
        direction = rotors[number]["direction"]

        if moment and direction in ("ccw", "cw") and (moment > 0) != (direction == "ccw"):
            result.findings.append(
                _finding("SDF020", f"motorNumber {number} turns {direction}, but CA_ROTOR{index}_KM is {moment:g}")
            )


def check(model_path: str | Path, world: str | None, params: dict[str, str]) -> tuple[Result, dict]:
    """Apply the SDF rules to a model, its world and the parameters. Raises SdfError."""
    result = Result()
    info = {"model": str(model_path), "world": world}

    try:
        model = read_model(model_path)
    except SdfSkipped as skipped:
        for rule in RULES:
            if rule.startswith("SDF"):
                result.not_checked[rule] = f"the model was not read: {skipped}"
        return result, info

    _check_world(model, world, result)
    _check_sensors(model, params, result)
    info.update(links=len(model.links), **_check_rotors(model, params, result))
    return result, info
