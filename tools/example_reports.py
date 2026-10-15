#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Write the report of every file in examples/ to docs/example-reports/.

usage: tools/example_reports.py [--check]

The reports show what the tool prints without installing it. They are made
with the engine the tool finds (see the README), which has to be one built
against the PX4 version named below. The stored ones were made on macOS arm64.
With --check nothing is written and the exit code says whether the stored
reports are up to date; the tests do that.
"""

import contextlib
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from actuator_lint.cli import main  # noqa: E402

PX4_VERSION = "v1.17.0"
OUTPUT = ROOT / "docs" / "example-reports"

# How far a number may be from the stored one. The engines of different platforms do not round
# every value alike, so the last digit may differ.
TOLERANCE = 0.0011
# PX4 computes the mix in single precision, and its pseudo-inverse amplifies the rounding of a
# matrix that is hard to invert. In the thrust_z column of this example the exact value is 0;
# the arm64 engines print 0.073 and the x86_64 engine 0.009. Twice the larger one is accepted.
TOLERANCES = {"quad_wrong_spin.md": 0.15}

# what each example shows, for the index
EXAMPLES = {
    "quad_qgc_export": "A quadrotor X, as a parameter file saved by QGroundControl",
    "quad_wrong_spin": "A quadrotor with the wrong spin direction on one motor",
    "quad_same_spin": "A quadrotor whose rotors all turn the same way",
    "quad_no_positions": "A quadrotor whose rotor positions were never entered",
    "quad_rotor_down": "A quadrotor with one rotor axis pointing down",
    "hexa_rotor_count_4": "A hexarotor whose `CA_ROTOR_COUNT` was left at 4",
    "no_rotors": "Rotor positions without `CA_ROTOR_COUNT`",
    "tricopter_tilt": "A tricopter with a tilt servo for yaw",
    "fixed_wing": "A plane with one motor, two ailerons, an elevator and a rudder",
    "fixed_wing_thrust_offset": "The same plane with the motor above the centre of gravity",
    "standard_vtol": "PX4's SIH standard VTOL: four lift motors, a pusher and three control surfaces",
    "standard_vtol_pusher_offset": "The standard VTOL with the pusher 5 cm above the centre of gravity",
    "standard_vtol_pusher_backwards": "The standard VTOL with the axis of the pusher turned around",
    "standard_vtol_typing_mistakes": "The standard VTOL with a decimal comma and a misspelled parameter name",
    "tailsitter": "A tailsitter VTOL with two motors and two elevons",
    "tiltrotor": "A tiltrotor VTOL with four motors, two of which tilt",
    "tiltrotor_tilt_servo_missing": "The tiltrotor with a rotor assigned to a tilt servo that does not exist",
}


def run(*arguments: str) -> tuple[int, str]:
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
        code = main(list(arguments))

    return code, stdout.getvalue()


def normalised(text: str) -> str:
    """A report without what changes from one tool version to the next."""
    text = re.sub(r"actuator-lint \d+\.\d+\.\d+\S*", "actuator-lint VERSION", text)
    return re.sub(r"/blob/[^/]+/rules/", "/blob/REF/rules/", text)


def same(first: str, second: str, tolerance: float = TOLERANCE) -> bool:
    """Whether two reports say the same: the same text, and numbers within the tolerance."""
    number = re.compile(r"(-?\d+\.\d+)")
    one, two = number.split(normalised(first)), number.split(normalised(second))

    if len(one) != len(two):
        return False

    for index, (left, right) in enumerate(zip(one, two)):
        # the odd items are the numbers
        if index % 2 and abs(float(left) - float(right)) > tolerance:
            return False

        if not index % 2 and left != right:
            return False

    return True


def build() -> dict[str, str]:
    """The files of docs/example-reports/ by name."""
    files = {}
    rows = []
    examples = sorted(path.stem for path in (ROOT / "examples").glob("*.params"))

    if sorted(EXAMPLES) != examples:
        raise SystemExit(f"EXAMPLES in {Path(__file__).name} does not list the files of examples/: {examples}")

    for name in EXAMPLES:
        path = f"examples/{name}.params"
        code, report = run("--format", "json", path)
        data = json.loads(report)

        if data["px4"]["version"] != PX4_VERSION:
            raise SystemExit(f"the engine is built against PX4 {data['px4']['version']}, not {PX4_VERSION}")

        files[f"{name}.md"] = run("--format", "markdown", path)[1]
        findings = ", ".join(
            f"[{rule}](../../rules/{rule}.md)" for rule in dict.fromkeys(item["rule"] for item in data["findings"])
        )
        summary = data["summary"]
        rows.append(
            f"| [`{name}.params`](../../{path}) | {EXAMPLES[name]} | {findings or 'none'} | "
            f"{summary['errors']} | {summary['warnings']} | {code} | [report]({name}.md) |"
        )

    files["README.md"] = "\n".join(
        [
            "# Example reports",
            "",
            "The report of every file in [`examples/`](../../examples), as the tool prints it with",
            f"`--format markdown` and the engine for PX4 {PX4_VERSION} on macOS arm64. They are written by",
            "`tools/example_reports.py`, and the tests fail when one of them is out of date. On another",
            "platform the last digit of a value can differ, and the mix of `quad_wrong_spin` differs",
            "more: see [Reading a report](../reading-a-report.md#mix).",
            "",
            "[Reading a report](../reading-a-report.md) explains the parts of a report.",
            "",
            "| Parameter file | What it is | Findings | Errors | Warnings | Exit code | Report |",
            "|---|---|---|---:|---:|---:|---|",
            *rows,
            "",
        ]
    )
    return files


def out_of_date() -> list[str]:
    """What differs between the stored files and what the tool prints now, one line per difference.

    A file that is missing or left over is one line; of a file with other content the first lines
    that differ are given, so that the log of a failed run shows what the difference is.
    """
    files = build()
    stored = {path.name for path in OUTPUT.glob("*.md")} if OUTPUT.is_dir() else set()
    problems = [
        f"{name}: {'not stored' if name in files else 'no example for it'}" for name in sorted(stored ^ set(files))
    ]

    for name in sorted(stored & set(files)):
        old, new = (OUTPUT / name).read_text(encoding="utf-8"), files[name]
        tolerance = TOLERANCES.get(name, TOLERANCE)

        if same(old, new, tolerance):
            continue

        old_lines, new_lines = old.splitlines(), new.splitlines()

        if len(old_lines) != len(new_lines):
            problems.append(f"{name}: {len(old_lines)} lines stored, {len(new_lines)} printed")

        differing = [(a, b) for a, b in zip(old_lines, new_lines) if not same(a, b, tolerance)]
        problems += [f"{name}: stored {a!r}, printed {b!r}" for a, b in differing[:6]]

    return problems


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        problems = out_of_date()

        if problems:
            raise SystemExit("out of date, run tools/example_reports.py:\n" + "\n".join(problems))

    elif sys.argv[1:]:
        raise SystemExit(__doc__)

    else:
        OUTPUT.mkdir(parents=True, exist_ok=True)

        for name, text in build().items():
            (OUTPUT / name).write_text(text, encoding="utf-8")

        print(f"wrote {OUTPUT.relative_to(ROOT)}")
