# SPDX-License-Identifier: BSD-3-Clause
"""Rules that turn the engine output into findings.

Every rule has a document in rules/ that explains what it checks and why.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

AXES = ("roll", "pitch", "yaw", "thrust_x", "thrust_y", "thrust_z")
TORQUE_AXES = AXES[:3]
THRUST_AXES = AXES[3:]

ERROR = "error"
WARNING = "warning"
LEVELS = (WARNING, ERROR)

# PX4 sets mix entries below this to zero (ControlAllocationPseudoInverse)
_MIX_ZERO = 1e-3
_EFFECTIVENESS_ZERO = 1e-6
# CA021: the rotor parameters whose PX4 default is zero. A rotor with one of them set is
# taken as configured on purpose; thrust and moment coefficients have non-zero defaults.
_ROTOR_GEOMETRY = re.compile(r"^CA_ROTOR(\d+)_(?:PX|PY|PZ|AX|AY|TILT)$")
# CA022: the CA_AIRFRAME values for which PX4 reads CA_ROTORn_TILT (tiltrotor VTOL, multirotor with tilt)
_TILT_AIRFRAMES = (3, 8)
# CA005: the axes a vehicle of each CA_AIRFRAME value cannot be flown without. Every airframe script
# of PX4 v1.17.0 that PX4 can allocate controls them, see docs/px4-airframes.md.
_HOVER_AXES = ("roll", "pitch", "yaw", "thrust_z")
_NEEDED_AXES = {
    0: _HOVER_AXES,  # multirotor
    1: ("roll", "pitch"),  # fixed-wing: no yaw for a flying wing, no thrust for a glider
    2: (*_HOVER_AXES, "thrust_x"),  # standard VTOL: hover and forward thrust
    3: _HOVER_AXES,  # tiltrotor VTOL, in the hover position that the matrices are for
    4: _HOVER_AXES,  # tailsitter VTOL
    8: _HOVER_AXES,  # multirotor with tilt
}
# CA006: the test of ControlAllocationPseudoInverse::dropDependentAxes of PX4 main (added after
# release/1.18 was branched, PX4 pull request 28589): the order in which axes keep their row, the
# smallest squared norm of a row that is looked at, and the smallest share of a unit row that has
# to be independent of the rows before it
_AXIS_PRIORITY = ("thrust_z", "roll", "pitch", "thrust_x", "thrust_y", "yaw")
_FLT_EPSILON = 1.1920929e-07
_MIN_AXIS_INDEPENDENCE = 1e-2
# CA012: the CA_AIRFRAME values for which PX4 does not read the rotor axis CA_ROTORn_AX, _AY, _AZ
# (fixed-wing: always forwards, multirotor with tilt: always upwards)
_FIXED_AXIS_AIRFRAMES = (1, 8)


@dataclass(frozen=True)
class Rule:
    id: str
    level: str
    title: str


RULES = {
    rule.id: rule
    for rule in (
        Rule("CA001", ERROR, "PX4 produced no usable effectiveness matrix"),
        Rule("CA002", ERROR, "PX4 dropped a control axis"),
        Rule("CA003", ERROR, "a matrix contains NaN or infinity"),
        Rule("CA004", WARNING, "PX4 ignores an axis with weak authority"),
        Rule("CA005", ERROR, "an axis the vehicle cannot be flown without is not controlled"),
        Rule("CA006", ERROR, "an axis cannot be controlled independently of the others"),
        Rule("CA010", WARNING, "thrust gain above the limit"),
        Rule("CA011", WARNING, "thrust command to an actuator that produces no thrust on that axis"),
        Rule("CA012", ERROR, "the thrust of a rotor points down or backwards"),
        Rule("CA020", WARNING, "a motor is not used for roll or pitch"),
        Rule("CA021", WARNING, "a rotor is configured but not counted by CA_ROTOR_COUNT"),
        Rule("CA022", WARNING, "a rotor is assigned to a tilt servo that does not exist"),
        Rule("CA030", ERROR, "a line of the parameter file could not be used"),
        Rule("CA031", WARNING, "a control allocation parameter does not exist in this PX4 version"),
    )
}


def rule_url(rule_id: str) -> str:
    """Where the document of a rule is, for the version of the tool that is running."""
    from . import __version__

    ref = "main" if "dev" in __version__ else f"v{__version__}"
    return f"https://github.com/Abtektas/px4-ca-lint/blob/{ref}/rules/{rule_id}.md"


@dataclass(frozen=True)
class Options:
    # CA010: largest accepted |mix| on a thrust axis
    max_thrust_gain: float = 2.0
    # CA011: smallest |mix| that counts as a command
    min_cross_command: float = 0.05
    ignore: frozenset[str] = frozenset()


@dataclass
class Finding:
    rule: str
    level: str
    message: str
    matrix: int | None = None
    axis: str | None = None
    actuators: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    # rules that could not run, with the reason
    not_checked: dict[str, str] = field(default_factory=dict)

    def count(self, level: str) -> int:
        return sum(1 for finding in self.findings if finding.level == level)


def _finding(rule_id: str, message: str, level: str | None = None, **where) -> Finding:
    return Finding(rule=rule_id, level=level or RULES[rule_id].level, message=message, **where)


def _axis_level(airframe: int | None, axis: str) -> str:
    """CA002 and CA006: an axis that is not independent is an error, unless the vehicle type is
    known not to need the axis, for example thrust_x of a multirotor with canted rotors."""
    needed = _NEEDED_AXES.get(airframe)
    return WARNING if needed is not None and axis not in needed else ERROR


def _labels(matrix: dict) -> list[str]:
    return [f"{actuator['type']}{actuator['index']}" for actuator in matrix["actuators"]]


def _has_non_finite(matrix: dict) -> bool:
    # the engine writes null for NaN and infinity
    values = [value for axis in AXES for value in matrix["effectiveness"][axis]]
    values += [row[axis] for row in matrix["mix"] for axis in AXES]
    return any(value is None for value in values)


def _join(names: list[str]) -> str:
    return ", ".join(names)


def _and(names: list[str]) -> str:
    return " and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)


def axis_status(matrix: dict, axis: str) -> str:
    """What PX4 does with one axis of a matrix: controlled, or why not."""
    dropped = matrix.get("dropped_axes_bitmask")

    if axis in matrix["weak_axes_zeroed"]:
        return "weak, zeroed by PX4"

    if dropped is not None and dropped & (1 << AXES.index(axis)):
        return "dropped by PX4"

    # null values mean PX4 produced NaN or infinity
    if any(value for value in matrix["effectiveness"][axis] if value is not None):
        return "controlled"

    return "not controlled"


def _check_dropped_axes(matrix: dict, airframe: int | None, result: Result) -> None:
    dropped = matrix["dropped_axes_bitmask"]

    if dropped is None:
        result.not_checked["CA002"] = "this PX4 version does not report dropped axes"
        return

    for bit, axis in enumerate(AXES):
        if dropped & (1 << bit):
            result.findings.append(
                _finding(
                    "CA002",
                    f"PX4 dropped {axis}: its effectiveness row depends on axes with a higher "
                    "priority, so it cannot be controlled independently",
                    level=_axis_level(airframe, axis),
                    matrix=matrix["index"],
                    axis=axis,
                )
            )


def _dot(first: list[float], second: list[float]) -> float:
    return sum(x * y for x, y in zip(first, second))


def _combination(row: list[float], others: list[list[float]]) -> list[float]:
    """The factors of the combination of the other rows that is closest to the row (least squares)."""
    size = len(others)
    # normal equations, solved by Gaussian elimination with pivoting; the other rows are independent
    system = [[_dot(others[i], others[j]) for j in range(size)] + [_dot(others[i], row)] for i in range(size)]

    for column in range(size):
        pivot = max(range(column, size), key=lambda line: abs(system[line][column]))
        system[column], system[pivot] = system[pivot], system[column]

        for line in range(size):
            if line != column:
                factor = system[line][column] / system[column][column]
                system[line] = [value - factor * other for value, other in zip(system[line], system[column])]

    return [system[line][size] / system[line][line] for line in range(size)]


def dependent_axes(matrix: dict) -> list[tuple[str, list[str]]]:
    """The axes PX4 main would drop from a matrix, each with the axes its row is a combination of.

    The same test as ControlAllocationPseudoInverse::dropDependentAxes: in the order of
    _AXIS_PRIORITY a row is kept when enough of it is independent of the rows kept before it.
    """
    basis: list[list[float]] = []
    kept: list[str] = []
    dependent = []

    for axis in _AXIS_PRIORITY:
        row = matrix["effectiveness"][axis]
        norm_squared = _dot(row, row)

        if norm_squared < _FLT_EPSILON:
            continue

        unit = [value / norm_squared**0.5 for value in row]
        shares = [_dot(unit, vector) for vector in basis]
        independence = 1 - sum(share * share for share in shares)

        if independence < _MIN_AXIS_INDEPENDENCE:
            factors = _combination(row, [matrix["effectiveness"][other] for other in kept])
            # the rows that make up a noticeable part of this one
            parts = [
                other
                for other, factor in zip(kept, factors)
                if _dot(matrix["effectiveness"][other], matrix["effectiveness"][other]) * factor * factor
                > 0.01 * norm_squared
            ]
            dependent.append((axis, parts or list(kept)))
            continue

        rest = [
            value - sum(share * vector[i] for share, vector in zip(shares, basis)) for i, value in enumerate(unit)
        ]
        basis.append([value / independence**0.5 for value in rest])
        kept.append(axis)

    return dependent


def _check_independent_axes(matrix: dict, engine_result: dict, result: Result) -> None:
    # where PX4 drops such axes itself, CA002 reports them
    if matrix["dropped_axes_bitmask"] is not None:
        return

    px4_version = engine_result.get("px4_version")
    version = f"PX4 {px4_version}" if px4_version else "This PX4 version"

    for axis, parts in dependent_axes(matrix):
        result.findings.append(
            _finding(
                "CA006",
                f"{axis} cannot be controlled independently: its effectiveness row is a combination of "
                f"the {'row' if len(parts) == 1 else 'rows'} of {_and(parts)}, so no actuator command "
                f"changes {axis} without changing {'it' if len(parts) == 1 else 'them'}. {version} "
                "computes a mix for it all the same; PX4 main drops such an axis (CA002)",
                level=_axis_level(engine_result.get("ca_airframe"), axis),
                matrix=matrix["index"],
                axis=axis,
            )
        )


def _check_weak_axes(matrix: dict, result: Result) -> None:
    for axis in matrix["weak_axes_zeroed"]:
        result.findings.append(
            _finding(
                "CA004",
                f"every {axis} effectiveness value is 0.05 or smaller, so PX4 sets the row to "
                f"zero and does not control {axis} with this matrix",
                matrix=matrix["index"],
                axis=axis,
            )
        )


def _check_thrust_gain(matrix: dict, options: Options, result: Result) -> None:
    labels = _labels(matrix)

    for axis in THRUST_AXES:
        high = [
            (label, abs(row[axis]))
            for label, row in zip(labels, matrix["mix"])
            if abs(row[axis]) > options.max_thrust_gain
        ]

        if not high:
            continue

        gain = max(value for _, value in high)
        result.findings.append(
            _finding(
                "CA010",
                f"{_join([label for label, _ in high])}: {axis} gain up to {gain:.2f} "
                f"(limit {options.max_thrust_gain:g}); the output saturates at a {axis} "
                f"setpoint of {1 / gain:.2f}",
                matrix=matrix["index"],
                axis=axis,
                actuators=[label for label, _ in high],
            )
        )


def _check_cross_command(matrix: dict, options: Options, result: Result) -> None:
    labels = _labels(matrix)

    for axis in THRUST_AXES:
        effectiveness = matrix["effectiveness"][axis]
        affected = [
            label
            for label, produced, row in zip(labels, effectiveness, matrix["mix"])
            if abs(produced) < _EFFECTIVENESS_ZERO and abs(row[axis]) > options.min_cross_command
        ]

        if affected:
            result.findings.append(
                _finding(
                    "CA011",
                    f"{_join(affected)}: commanded by the {axis} setpoint without producing "
                    f"{axis} thrust; a {axis} setpoint changes their output",
                    matrix=matrix["index"],
                    axis=axis,
                    actuators=affected,
                )
            )


def _thrust_axis(thrust: dict[str, float]) -> str | None:
    """The thrust axis a rotor acts on most, None when it has no thrust or no single such axis."""
    axis = max(THRUST_AXES, key=lambda name: abs(thrust[name]))
    others = [abs(thrust[name]) for name in THRUST_AXES if name != axis]

    if abs(thrust[axis]) < _EFFECTIVENESS_ZERO or abs(thrust[axis]) <= max(others):
        return None

    return axis


def _check_thrust_direction(matrix: dict, airframe: int | None, result: Result) -> None:
    # the vehicle types whose rotors lift the vehicle or push it forwards, the same as for CA005
    if airframe not in _NEEDED_AXES:
        return

    motors = []

    for position, (actuator, label) in enumerate(zip(matrix["actuators"], _labels(matrix))):
        if actuator["type"] == "motor":
            thrust = {axis: matrix["effectiveness"][axis][position] for axis in THRUST_AXES}
            motors.append((label, _thrust_axis(thrust), thrust))

    # the body axes of PX4 point forwards, to the right and down
    down = [label for label, axis, thrust in motors if axis == "thrust_z" and thrust[axis] > 0]
    backwards = [label for label, axis, thrust in motors if axis == "thrust_x" and thrust[axis] < 0]

    if airframe == 0:
        # a multirotor has no rotor for forward thrust, and one with rotors along other axes than
        # the vertical is an omnidirectional vehicle, whose rotors may point anywhere
        backwards = []

        if any(axis not in (None, "thrust_z") for _, axis, _ in motors):
            down = []

    axis_parameter = "" if airframe in _FIXED_AXIS_AIRFRAMES else "CA_ROTORn_{} and "
    cases = (
        (down, "thrust_z", "down", "positive", "the rotors that lift this vehicle have to point up", "AZ"),
        (backwards, "thrust_x", "backwards", "negative", "a rotor for forward thrust has to point forwards", "AX"),
    )

    for wrong, axis, direction, value, needed, parameter in cases:
        if wrong:
            result.findings.append(
                _finding(
                    "CA012",
                    f"{_join(wrong)}: PX4 takes the thrust as pointing {direction} ({value} {axis} "
                    f"effectiveness), but {needed}. Check the sign of "
                    f"{axis_parameter.format(parameter)}CA_ROTORn_CT",
                    matrix=matrix["index"],
                    axis=axis,
                    actuators=wrong,
                )
            )


def _check_unused_motor(matrix: dict, result: Result) -> None:
    roll = matrix["effectiveness"]["roll"]
    pitch = matrix["effectiveness"]["pitch"]

    for actuator, label, roll_torque, pitch_torque, row in zip(
        matrix["actuators"], _labels(matrix), roll, pitch, matrix["mix"]
    ):
        if actuator["type"] != "motor":
            continue

        produces_both = abs(roll_torque) > _EFFECTIVENESS_ZERO and abs(pitch_torque) > _EFFECTIVENESS_ZERO
        unused = abs(row["roll"]) < _MIX_ZERO and abs(row["pitch"]) < _MIX_ZERO

        if produces_both and unused:
            result.findings.append(
                _finding(
                    "CA020",
                    f"{label} produces roll and pitch torque but gets no roll and no pitch "
                    "command. A frequent cause is a wrong spin direction "
                    "(sign of CA_ROTORn_KM) on this or another motor",
                    matrix=matrix["index"],
                    actuators=[label],
                )
            )


def _check_needed_axes(engine_result: dict, result: Result) -> None:
    matrices = engine_result.get("matrices", [])
    needed = _NEEDED_AXES.get(engine_result.get("ca_airframe"), ())

    # CA001 and CA003 already say that there is nothing to judge
    if not matrices or any(_has_non_finite(matrix) for matrix in matrices):
        return

    if engine_result.get("num_motors", 0) + engine_result.get("num_servos", 0) == 0:
        return

    for axis in needed:
        states = [axis_status(matrix, axis) for matrix in matrices]

        if "controlled" in states:
            continue

        if "weak, zeroed by PX4" in states:
            reason = "PX4 set its weak effectiveness values to zero, see CA004"

        elif "dropped by PX4" in states:
            reason = "PX4 dropped it, see CA002"

        else:
            reason = "no actuator has an effect on it"

        name = engine_result.get("effectiveness_source")
        vehicle = f"CA_AIRFRAME {engine_result['ca_airframe']}" + (f" ({name})" if name else "")
        result.findings.append(
            _finding(
                "CA005",
                f"{axis} is not controlled: {reason}. A vehicle with {vehicle} needs it",
                axis=axis,
            )
        )


def _check_input(engine_result: dict, params: dict[str, str], unread: list[str], result: Result) -> None:
    for message in unread:
        result.findings.append(_finding("CA030", message))

    # the engine leaves an integer parameter at its default when the value is not an integer
    for name in engine_result.get("not_integer_parameters", []):
        result.findings.append(
            _finding(
                "CA030",
                f"{name} is an integer parameter, but the value is '{params.get(name, '?')}'; "
                "it was not used and PX4's default applies",
            )
        )

    unknown = sorted(name for name in engine_result.get("unknown_parameters", []) if name.startswith("CA_"))

    if unknown:
        result.findings.append(
            _finding(
                "CA031",
                f"{_join(unknown)}: not a parameter of PX4 {engine_result.get('px4_version')}, ignored. "
                "Check the spelling, or the PX4 version the file is for",
            )
        )


def _rotor_count(engine_result: dict, params: dict[str, str]) -> int | None:
    """The number of rotors PX4 uses, None when it is not known."""
    if "num_motors" in engine_result:
        return engine_result["num_motors"]

    try:
        return int(float(params["CA_ROTOR_COUNT"]))

    except (KeyError, ValueError):
        return None


def _check_uncounted_rotors(engine_result: dict, params: dict[str, str], result: Result) -> None:
    count = _rotor_count(engine_result, params)

    if count is None:
        return

    configured = set()

    for name, value in params.items():
        match = _ROTOR_GEOMETRY.match(name)

        if match and int(match.group(1)) >= count and float(value) != 0:
            configured.add(int(match.group(1)))

    if not configured:
        return

    labels = [f"motor{index}" for index in sorted(configured)]
    unset = "" if "CA_ROTOR_COUNT" in params else " (not set in the input)"
    used = {0: "no rotors", 1: "rotor 0 only"}.get(count, f"rotors 0 to {count - 1} only")
    result.findings.append(
        _finding(
            "CA021",
            f"{_join(labels)}: rotor parameters are set, but CA_ROTOR_COUNT is {count}{unset}; "
            f"PX4 uses {used}",
            actuators=labels,
        )
    )


def _integer(params: dict[str, str], name: str) -> int:
    """An integer parameter of the input; 0, the PX4 default of the ones read here, when it is not set."""
    try:
        return int(float(params[name]))

    except (KeyError, ValueError):
        return 0


def _check_tilt_servos(engine_result: dict, params: dict[str, str], result: Result) -> None:
    if engine_result.get("ca_airframe") not in _TILT_AIRFRAMES:
        return

    count = _rotor_count(engine_result, params)

    if count is None:
        return

    tilts = _integer(params, "CA_SV_TL_COUNT")
    # CA_ROTORn_TILT is 0 for no tilt servo, else the number of the servo, starting at 1
    missing = [
        (index, tilt) for index in range(count) if (tilt := _integer(params, f"CA_ROTOR{index}_TILT")) > tilts
    ]

    if not missing:
        return

    labels = [f"motor{index}" for index, _ in missing]
    assigned = _join([f"CA_ROTOR{index}_TILT is {tilt}" for index, tilt in missing])
    unset = "" if "CA_SV_TL_COUNT" in params else " (not set in the input)"
    rotors = "the rotor" if len(missing) == 1 else "these rotors"
    result.findings.append(
        _finding(
            "CA022",
            f"{_join(labels)}: {assigned}, but CA_SV_TL_COUNT is {tilts}{unset}; "
            f"PX4 treats {rotors} as not tilting",
            actuators=labels,
        )
    )


def check(
    engine_result: dict,
    options: Options = Options(),
    params: dict[str, str] | None = None,
    unread: list[str] | None = None,
) -> Result:
    """Apply the rules to the engine output.

    params are the parameters of the input file and unread the lines of it that could not be
    used (ParamFile.unread); rules that look at the input are skipped without params.
    """
    result = Result()

    if params is not None:
        _check_input(engine_result, params, unread or [], result)

    if "error" in engine_result:
        result.findings.append(_finding("CA001", f"{engine_result['error']}"))

    elif engine_result["num_motors"] + engine_result["num_servos"] == 0:
        result.findings.append(
            _finding("CA001", "the configuration has no actuators; check CA_ROTOR_COUNT")
        )

    if params is not None:
        _check_uncounted_rotors(engine_result, params, result)
        _check_tilt_servos(engine_result, params, result)

    for matrix in engine_result.get("matrices", []):
        if _has_non_finite(matrix):
            result.findings.append(
                _finding(
                    "CA003",
                    "the matrix contains NaN or infinity; the other rules were not run on it",
                    matrix=matrix["index"],
                )
            )
            continue

        _check_dropped_axes(matrix, engine_result.get("ca_airframe"), result)
        _check_weak_axes(matrix, result)
        _check_independent_axes(matrix, engine_result, result)
        _check_thrust_gain(matrix, options, result)
        _check_cross_command(matrix, options, result)
        _check_thrust_direction(matrix, engine_result.get("ca_airframe"), result)
        _check_unused_motor(matrix, result)

    if "error" not in engine_result:
        _check_needed_axes(engine_result, result)

    result.findings = [finding for finding in result.findings if finding.rule not in options.ignore]
    result.not_checked = {
        rule: reason for rule, reason in result.not_checked.items() if rule not in options.ignore
    }
    return result
