# SPDX-License-Identifier: BSD-3-Clause
"""The SDF rules (--sdf) on small models made from tests/sdf, and on PX4's own gz models.

Each broken model below is one that was flown in PX4's gz simulation (SITL) before the rule was
written, with the failure named in the test. The cross-check against libsdformat runs when its
Python bindings (sdformat14) are installed; the run over PX4's models needs ACTUATOR_LINT_PX4_DIR
to point to a PX4 checkout with the Tools/simulation/gz submodule.
"""

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from actuator_lint import DISCLAIMER, sdf
from actuator_lint.params import parse_file
from tests.test_cli import run
from tests.test_engine import fake_engine

FIXTURES = Path(__file__).parent / "sdf"
PX4_DIR = os.environ.get("ACTUATOR_LINT_PX4_DIR")
PX4_MODELS = Path(PX4_DIR or "-") / "Tools" / "simulation" / "gz" / "models"
PX4_AIRFRAMES = Path(PX4_DIR or "-") / "ROMFS" / "px4fmu_common" / "init.d-posix" / "airframes"
HAVE_PX4_MODELS = PX4_MODELS.is_dir() and any(PX4_MODELS.iterdir())

try:
    import sdformat14
    from gz.math7 import Vector3d
except ImportError:
    sdformat14 = None


def params(**changes) -> dict[str, str]:
    values = dict(parse_file(FIXTURES / "quad.params").params)
    values.update({name: str(value) for name, value in changes.items()})
    return values


class Case(unittest.TestCase):
    """Copies the fixtures, so that a test can change a model before checking it."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        shutil.copytree(FIXTURES, self.root, dirs_exist_ok=True)

    def edit(self, model: str, old: str, new: str, count: int = -1) -> None:
        path = self.root / "models" / model / "model.sdf"
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, count), encoding="utf-8")

    def check(self, world: str | None = "empty", **changes):
        world_path = None if world is None else str(self.root / "worlds" / f"{world}.sdf")
        result, info = sdf.check(self.root / "models" / "quad", world_path, params(**changes))
        return result, info

    def findings(self, world: str | None = "empty", **changes) -> list[tuple[str, str]]:
        result, _ = self.check(world, **changes)
        return [(finding.rule, finding.level) for finding in result.findings]


class Rules(Case):
    def test_the_model_as_it_is_has_no_findings(self):
        result, info = self.check()
        self.assertEqual(result.findings, [])
        self.assertEqual(result.not_checked, {})
        self.assertEqual((info["links"], info["motor_plugins"]), (5, 4))
        self.assertAlmostEqual(info["mass_kg"], 2.08)
        self.assertAlmostEqual(info["thrust_to_weight"], 34.0 / (2.08 * 9.81), places=3)

    def test_a_slowdown_of_one_is_not_reported(self):
        """rotorVelocitySlowdownSim 1 was one of the changes in forum thread 45612; it flies."""
        self.edit("quad", "<rotorVelocitySlowdownSim>10<", "<rotorVelocitySlowdownSim>1<")
        self.assertEqual(self.findings(), [])

    def test_sdf001_world_with_its_own_systems(self):
        """Forum thread 48506; in SITL the sensors are missing and PX4 does not arm."""
        result, _ = self.check("own_systems")
        self.assertEqual([finding.rule for finding in result.findings], ["SDF001"] * 4)
        missing = sorted(finding.message.split("the ")[-1].split()[0] for finding in result.findings)
        self.assertEqual(missing, ["AirPressure", "Imu", "Magnetometer", "NavSat"])

    def test_sdf001_needs_a_world(self):
        result, _ = self.check(None)
        self.assertEqual(result.findings, [])
        self.assertIn("SDF001", result.not_checked)

    def test_sdf001_world_with_the_systems(self):
        path = self.root / "worlds" / "own_systems.sdf"
        text = path.read_text(encoding="utf-8")
        systems = "".join(
            f'<plugin filename="x" name="gz::sim::systems::{name}"/>'
            for name in ("Imu", "AirPressure", "Magnetometer", "NavSat")
        )
        path.write_text(text.replace("</world>", systems + "</world>"), encoding="utf-8")
        self.assertEqual(self.findings("own_systems"), [])

    def test_sdf002_renamed_imu(self):
        """In SITL: no valid gyro or accel data, arming denied."""
        self.edit("quad_base", 'name="imu_sensor"', 'name="imu_main"')
        self.assertEqual(self.findings(), [("SDF002", "error")])

    def test_sdf002_turned_off_or_simulated_by_px4(self):
        self.edit("quad_base", '<sensor name="navsat_sensor" type="navsat"/>', "")
        self.edit("quad_base", '<sensor name="magnetometer_sensor" type="magnetometer"/>', "")
        self.assertEqual(self.findings(), [("SDF002", "error")] * 2)
        self.assertEqual(self.findings(SYS_HAS_GPS=0, SYS_HAS_MAG=0), [("SDF002", "warning")] * 2)
        self.assertEqual(self.findings(SENS_EN_GPSSIM=1, SENS_EN_MAGSIM=1), [])

    def test_sdf010_rotor_link_turned_but_the_axis_kept_vertical(self):
        """Forum thread 45612 (likely cause); in SITL the props spin and the vehicle does not lift."""
        for k, (x, y) in enumerate(((0.15, -0.2), (-0.15, 0.2), (0.15, 0.2), (-0.15, -0.2))):
            self.edit("quad_base", f"<pose>{x} {y} 0.05 0 0 0</pose>", f"<pose>{x} {y} 0.05 1.5708 0 0</pose>")

        self.edit("quad_base", "<xyz>0 0 1</xyz>", '<xyz expressed_in="__model__">0 0 1</xyz>')
        self.assertEqual(self.findings(), [("SDF010", "error")] * 4)

    def test_sdf010_axis_and_link_turned_together(self):
        """A rotor link and its axis turned the same way thrust along the axis: no finding."""
        self.edit("quad_base", "<pose>0.15 -0.2 0.05 0 0 0</pose>", "<pose>0.15 -0.2 0.05 0.3 0 0</pose>")
        self.assertEqual(self.findings(), [])

    def test_sdf011_velocity_limit(self):
        """Forum thread 45612 (likely cause); in SITL the vehicle does not lift."""
        self.edit("quad_base", "<upper>1e+16</upper>", "<upper>1e+16</upper><velocity>20</velocity>")
        self.assertEqual(self.findings(), [("SDF011", "error")] * 4)

    def test_sdf011_velocity_limit_above_the_rotor_speed(self):
        self.edit("quad_base", "<upper>1e+16</upper>", "<upper>1e+16</upper><velocity>100</velocity>")
        self.assertEqual(self.findings(), [])

    def test_sdf011_position_limits_and_fixed_joint(self):
        self.edit("quad_base", "<lower>-1e+16</lower><upper>1e+16</upper>", "<lower>0</lower><upper>3</upper>", 1)
        self.edit("quad_base", '"rotor_1_joint" type="revolute"', '"rotor_1_joint" type="fixed"')
        self.assertEqual(self.findings(), [("SDF011", "error")] * 2)

    def test_sdf012_wrong_command_topic(self):
        """In SITL PX4 arms, the motors get no command and the vehicle does not lift."""
        self.edit("quad", "<commandSubTopic>command/motor_speed<", "<commandSubTopic>command/motor_speeds<")
        self.assertEqual(self.findings(), [("SDF012", "error")] * 4)

    def test_sdf012_namespace_and_motor_numbers(self):
        self.edit("quad", "<motorNumber>3<", "<motorNumber>2<")
        self.edit("quad", "<jointName>rotor_0_joint<", "<robotNamespace>x</robotNamespace><jointName>rotor_0_joint<")
        # two motors on motorNumber 2: one of them also sits where CA rotor 2 is not
        self.assertEqual(sorted(self.findings()), [("SDF012", "error")] * 2 + [("SDF020", "error")])

    def test_sdf012_unknown_link(self):
        self.edit("quad", "<linkName>rotor_3<", "<linkName>rotor_9<")
        result, _ = self.check()
        self.assertEqual([finding.rule for finding in result.findings], ["SDF012"])
        self.assertIn("SDF013", result.not_checked)

    def test_sdf013_too_heavy(self):
        """Base link 2.0 to 4.5 kg; in SITL the vehicle does not lift."""
        self.edit("quad_base", "<mass>2.0</mass>", "<mass>4.5</mass>")
        result, _ = self.check()
        self.assertEqual([(finding.rule, finding.level) for finding in result.findings], [("SDF013", "error")])
        self.assertIn("thrust to weight 0.76", result.findings[0].message)

    def test_sdf013_little_margin(self):
        self.edit("quad_base", "<mass>2.0</mass>", "<mass>2.7</mass>")
        self.assertEqual(self.findings(), [("SDF013", "warning")])

    def test_sdf013_limited_by_the_output_maximum(self):
        maxima = {f"SIM_GZ_EC_MAX{n}": 700 for n in range(1, 5)}
        self.assertEqual(self.findings(**maxima), [("SDF013", "error")])

    def test_sdf020_swapped_motor_numbers(self):
        """Forum thread 48713 (in part); in SITL the vehicle flips on takeoff."""
        self.edit("quad", "<motorNumber>0<", "<motorNumber>X<")
        self.edit("quad", "<motorNumber>1<", "<motorNumber>0<")
        self.edit("quad", "<motorNumber>X<", "<motorNumber>1<")
        self.assertEqual(self.findings(), [("SDF020", "error")] * 2)

    def test_sdf020_turning_direction_and_rotor_count(self):
        self.assertEqual(self.findings(CA_ROTOR0_KM=-0.05), [("SDF020", "error")])
        self.assertEqual(self.findings(CA_ROTOR_COUNT=6), [("SDF020", "error")])

    def test_sdf020_shape_and_size(self):
        """Only the shape counts: twice the size is fine, a rotor far off its place is a warning."""
        double = {f"CA_ROTOR{k}_P{a}": 2 * float(params()[f"CA_ROTOR{k}_P{a}"]) for k in range(4) for a in "XY"}
        self.assertEqual(self.findings(**double), [])
        self.assertEqual(self.findings(CA_ROTOR0_PX=0.1, CA_ROTOR0_PY=0.25), [])  # about 20% off: PX4's own models
        self.assertEqual(self.findings(CA_ROTOR0_PX=0.03, CA_ROTOR0_PY=0.3), [("SDF020", "warning")])

    def test_sdf020_without_ca_rotor_count(self):
        values = params()
        del values["CA_ROTOR_COUNT"]
        result, _ = sdf.check(self.root / "models" / "quad", None, values)
        self.assertEqual(result.findings, [])
        self.assertIn("SDF020", result.not_checked)


class Reader(Case):
    def model(self, text: str, version: str = "1.9") -> sdf.Model:
        path = self.root / "models" / "test" / "model.sdf"
        path.parent.mkdir()
        path.write_text(f'<?xml version="1.0"?><sdf version="{version}"><model name="test">{text}</model></sdf>')
        return sdf.read_model(path.parent)

    def assertVector(self, first, second):
        for a, b in zip(first, second):
            self.assertAlmostEqual(a, b, places=6)

    def test_relative_to_chain_and_degrees(self):
        model = self.model(
            '<link name="a"><pose degrees="true">1 0 0 0 0 90</pose></link>'
            '<link name="b"><pose relative_to="a">1 0 0 0 0 0</pose></link>'
            '<frame name="f" attached_to="b"><pose>0 0 1 0 0 0</pose></frame>'
        )
        self.assertVector(model.pose("b").position, (1, 1, 0))
        self.assertVector(model.pose("f").position, (1, 1, 1))

    def test_quaternion(self):
        pose = '<pose rotation_format="quat_xyzw">0 0 0 0.7071068 0 0 0.7071068</pose>'
        model = self.model(f'<link name="a">{pose}</link>')
        self.assertVector(model.pose("a").rotate((0, 0, 1)), (0, -1, 0))

    def test_joint_axis_frames(self):
        joint = (
            '<link name="r"><pose>0 0 0 1.5707963 0 0</pose></link>'
            '<joint name="j" type="revolute"><parent>world</parent><child>r</child>'
            '<axis><xyz>0 0 1</xyz>{}</axis></joint>'
        )
        # SDFormat 1.7 and later: the axis is in the joint frame, which is the child link frame here
        model = self.model(joint.format(""))
        self.assertVector(model.axis(model.joints["j"]), (0, -1, 0))

    def test_use_parent_model_frame(self):
        model = self.model(
            '<link name="r"><pose>0 0 0 1.5707963 0 0</pose></link>'
            '<joint name="j" type="revolute"><parent>world</parent><child>r</child>'
            "<axis><xyz>0 0 1</xyz><use_parent_model_frame>1</use_parent_model_frame></axis></joint>",
            "1.6",
        )
        self.assertVector(model.axis(model.joints["j"]), (0, 0, 1))

    def test_nested_include_with_pose(self):
        model = self.model('<include><uri>model://quad_base</uri><name>q</name><pose>0 0 1 0 0 0</pose></include>')
        self.assertIn("q::rotor_0", model.links)
        self.assertVector(model.pose("q::rotor_0").position, (0.15, -0.2, 1.05))
        self.assertVector(model.axis(model.joints["q::rotor_0_joint"]), (0, 0, 1))

    def test_merged_include_with_pose(self):
        model = self.model('<include merge="true"><uri>quad_base</uri><pose>0 0 0 0 0 3.1415927</pose></include>')
        self.assertVector(model.pose("rotor_0").position, (-0.15, 0.2, 0.05))

    def test_undeclared_prefix(self):
        model = self.model('<link name="a"><sensor name="s" type="custom" gz:type="optical_flow"/></link>')
        self.assertEqual(model.links["a"].sensors, [("s", "custom")])

    def test_errors(self):
        with self.assertRaisesRegex(sdf.SdfError, "unknown frame 'nope'"):
            self.model('<link name="a"><pose relative_to="nope">0 0 0 0 0 0</pose></link>').pose("a")

        shutil.rmtree(self.root / "models" / "test")

        with self.assertRaisesRegex(sdf.SdfError, "refer to each other"):
            model = self.model(
                '<link name="a"><pose relative_to="b">0 0 0 0 0 0</pose></link>'
                '<link name="b"><pose relative_to="a">0 0 0 0 0 0</pose></link>'
            )
            model.pose("a")

        with self.assertRaisesRegex(sdf.SdfError, "cannot find the included model"):
            sdf.read_model(self.write_include("model://nothing_here"))

        with self.assertRaisesRegex(sdf.SdfError, "no such model file"):
            sdf.read_model(self.root / "nothing_here")

    def write_include(self, uri: str) -> Path:
        path = self.root / "models" / "inc" / "model.sdf"
        path.parent.mkdir(exist_ok=True)
        path.write_text(f'<sdf version="1.9"><model name="inc"><include><uri>{uri}</uri></include></model></sdf>')
        return path

    def test_a_model_from_a_server_is_not_checked(self):
        result, info = sdf.check(self.write_include("https://fuel.gazebosim.org/1.0/someone/models/x"), None, {})
        self.assertEqual(result.findings, [])
        self.assertEqual(
            sorted(result.not_checked), ["SDF001", "SDF002", "SDF010", "SDF011", "SDF012", "SDF013", "SDF020"]
        )
        self.assertIn("needs a download", result.not_checked["SDF010"])
        self.assertNotIn("links", info)


def _px4_jobs():
    for airframe in sorted(PX4_AIRFRAMES.glob("*_gz_*")):
        found = re.search(r"PX4_SIM_MODEL:=([A-Za-z0-9_]+)", airframe.read_text(encoding="utf-8"))

        if found and (PX4_MODELS / found.group(1)).is_dir():
            yield airframe, PX4_MODELS / found.group(1)


@unittest.skipUnless(HAVE_PX4_MODELS, "needs ACTUATOR_LINT_PX4_DIR with gz models")
class PX4Models(unittest.TestCase):
    def test_no_errors_on_px4_models(self):
        """No rule may give an error on a model that PX4 flies in its own simulation."""
        jobs = list(_px4_jobs())
        self.assertGreater(len(jobs), 10)
        errors = []

        for airframe, model in jobs:
            result, _ = sdf.check(model, None, parse_file(airframe, "airframe").params)
            errors += [f"{airframe.name}: {f.rule} {f.message}" for f in result.findings if f.level == "error"]

        self.assertEqual(errors, [])

    def test_no_errors_in_px4_worlds(self):
        """Every world of PX4 that loads no systems of its own, or all those the x500 needs."""
        worlds = sorted((PX4_MODELS.parent / "worlds").glob("*.sdf"))
        values = parse_file(PX4_AIRFRAMES / "4001_gz_x500", "airframe").params

        for world in worlds:
            if sdf.world_systems(world) is None:
                result, _ = sdf.check(PX4_MODELS / "x500", str(world), values)
                self.assertEqual([f.rule for f in result.findings if f.rule == "SDF001"], [], world.name)


@unittest.skipUnless(sdformat14, "needs the libsdformat Python bindings (sdformat14)")
class AgainstLibsdformat(unittest.TestCase):
    """The poses and joint axes of the reader are those of libsdformat."""

    def compare(self, path: Path, search: Path) -> int:
        config = sdformat14.ParserConfig()
        config.add_uri_path("model://", str(search))
        config.set_find_callback(lambda p: str(search / p) if (search / p).is_dir() else "")
        root = sdformat14.Root()

        try:
            root.load(str(sdf.model_file(path)), config)
        except sdformat14.SDFErrorsException:
            if root.model() is None:
                return 0

        reference, ours = root.model(), sdf.read_model(path)
        compared = 0

        for i in range(reference.link_count()):
            link = reference.link_by_index(i)
            pose = link.semantic_pose().resolve("__model__")
            axis = pose.rot().rotate_vector(Vector3d(0, 0, 1))
            mine = ours.pose(link.name())
            where = f"{path} {link.name()}"
            self.assertVector(mine.position, (pose.pos().x(), pose.pos().y(), pose.pos().z()), where)
            self.assertVector(mine.rotate((0, 0, 1)), (axis.x(), axis.y(), axis.z()), where)
            self.assertAlmostEqual(ours.links[link.name()].mass, link.inertial().mass_matrix().mass(), places=5)
            compared += 1

        for i in range(reference.joint_count()):
            joint = reference.joint_by_index(i)

            if joint.axis(0) is None:
                continue

            axis = joint.axis(0).resolve_xyz("__model__")
            mine = ours.axis(ours.joints[joint.name()])
            self.assertVector(mine, (axis.x(), axis.y(), axis.z()), f"{path} {joint.name()}")
            compared += 1

        return compared

    def assertVector(self, first, second, message):
        for a, b in zip(first, second):
            self.assertAlmostEqual(a, b, places=5, msg=message)

    def test_fixtures(self):
        self.assertGreater(self.compare(FIXTURES / "models" / "quad", FIXTURES / "models"), 8)

    @unittest.skipUnless(HAVE_PX4_MODELS, "needs ACTUATOR_LINT_PX4_DIR with gz models")
    def test_px4_models(self):
        compared = sum(self.compare(model, PX4_MODELS) for model in sorted(PX4_MODELS.iterdir()) if model.is_dir())
        self.assertGreater(compared, 100)


class Command(Case):
    """--sdf and --world on the command line, with an engine that gives no matrices."""

    def setUp(self):
        super().setUp()
        self.engine = str(
            fake_engine(
                self.root,
                'echo \'{"engine_schema": 1, "px4_version": "v1.17.0", "px4_commit": "0123456789abcdef", '
                '"ca_airframe": 0, "effectiveness_source": "Multirotor", "num_motors": 4, "num_servos": 0, '
                '"matrices": []}\' > "$2"\n',
            )
        )

    def lint(self, *arguments):
        return run("--engine", self.engine, "--fail-on", "never", str(self.root / "quad.params"), *arguments)

    def test_findings_and_model_in_every_format(self):
        self.edit("quad_base", 'name="imu_sensor"', 'name="imu_main"')
        model, world = str(self.root / "models" / "quad"), str(self.root / "worlds" / "own_systems.sdf")

        for report_format in ("text", "markdown", "json"):
            code, stdout, stderr = self.lint("--sdf", model, "--world", world, "--format", report_format)
            self.assertEqual((code, stderr), (0, ""))
            self.assertIn(DISCLAIMER, stdout)
            self.assertIn("SDF001", stdout)
            self.assertIn("SDF002", stdout)
            self.assertIn("thrust_to_weight" if report_format == "json" else "thrust to weight 1.67", stdout)

        report = json.loads(stdout)
        self.assertEqual(report["model"]["motor_plugins"], 4)
        self.assertTrue(report["findings"][-1]["url"].endswith("/rules/SDF002.md"))

    def test_ignore_and_exit_code(self):
        self.edit("quad_base", 'name="imu_sensor"', 'name="imu_main"')
        model = str(self.root / "models" / "quad")
        params_file = str(self.root / "quad.params")
        code, stdout, _ = run("--engine", self.engine, "--ignore", "CA005", params_file, "--sdf", model)
        self.assertEqual(code, 1)
        code, stdout, _ = run("--engine", self.engine, "--ignore", "CA005,SDF002", params_file, "--sdf", model)
        self.assertEqual(code, 0, stdout)
        self.assertNotIn("SDF002", stdout.split("Findings")[1])

    def test_without_sdf_the_report_has_no_model(self):
        _, stdout, _ = self.lint("--format", "json")
        self.assertNotIn("model", json.loads(stdout))

    def test_errors(self):
        with self.assertRaises(SystemExit):
            self.lint("--world", str(self.root / "worlds" / "empty.sdf"))

        code, _, stderr = self.lint("--sdf", str(self.root / "nothing_here"))
        self.assertEqual(code, 2)
        self.assertIn("no such model file", stderr)


if __name__ == "__main__":
    unittest.main()
