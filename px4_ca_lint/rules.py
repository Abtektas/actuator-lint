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
        Rule("CA010", WARNING, "thrust gain above the limit"),
        Rule("CA011", WARNING, "thrust command to an actuator that produces no thrust on that axis"),
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


def _finding(rule_id: str, message: str, **where) -> Finding:
    return Finding(rule=rule_id, level=RULES[rule_id].level, message=message, **where)


def _labels(matrix: dict) -> list[str]:
    return [f"{actuator['type']}{actuator['index']}" for actuator in matrix["actuators"]]


def _has_non_finite(matrix: dict) -> bool:
    # the engine writes null for NaN and infinity
    values = [value for axis in AXES for value in matrix["effectiveness"][axis]]
    values += [row[axis] for row in matrix["mix"] for axis in AXES]
    return any(value is None for value in values)


def _join(names: list[str]) -> str:
    return ", ".join(names)


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


def _check_dropped_axes(matrix: dict, result: Result) -> None:
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

        _check_dropped_axes(matrix, result)
        _check_weak_axes(matrix, result)
        _check_thrust_gain(matrix, options, result)
        _check_cross_command(matrix, options, result)
        _check_unused_motor(matrix, result)

    if "error" not in engine_result:
        _check_needed_axes(engine_result, result)

    result.findings = [finding for finding in result.findings if finding.rule not in options.ignore]
    result.not_checked = {
        rule: reason for rule, reason in result.not_checked.items() if rule not in options.ignore
    }
    return result
