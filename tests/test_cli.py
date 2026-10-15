# SPDX-License-Identifier: BSD-3-Clause
"""End-to-end tests. They need a built engine and are skipped without one."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actuator_lint.cli import main
from actuator_lint.engine import ENGINE_ENV, PX4_ENV, EngineError, find_engine, versioned_engine_path
from tests.test_engine import fake_engine

EXAMPLE = str(Path(__file__).parent.parent / "examples" / "standard_vtol.params")

try:
    ENGINE = str(find_engine())
except EngineError:
    ENGINE = None


def run(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(list(arguments))

    return code, stdout.getvalue(), stderr.getvalue()


class Errors(unittest.TestCase):
    def test_missing_file(self):
        code, _, stderr = run("does/not/exist.params")
        self.assertEqual(code, 2)
        self.assertIn("error", stderr)

    def test_missing_engine(self):
        code, _, stderr = run("--engine", "does/not/exist", "examples/standard_vtol.params")
        self.assertEqual(code, 2)
        self.assertIn("not an executable file", stderr)


class EngineChoice(unittest.TestCase):
    """Which engine is used. Stand-in engines that only report a PX4 version are enough for this."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.enterContext(mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.directory / "data")}))
        os.environ.pop(ENGINE_ENV, None)
        os.environ.pop(PX4_ENV, None)
        previous = os.getcwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)

    def install(self, px4: str, reports: str) -> None:
        versioned_engine_path(px4).parent.mkdir(parents=True)
        fake_engine(
            versioned_engine_path(px4).parent,
            f'echo \'{{"engine_schema": 1, "px4_version": "{reports}", "px4_commit": "0123456789abcdef"}}\' > "$2"\n',
        )

    def test_engines_lists_what_is_installed(self):
        self.install("v1.17.0", "v1.17.0")
        self.install("v1.18.0", "v1.18.0")
        code, stdout, _ = run("engines")
        self.assertEqual(code, 0)
        self.assertIn(f"--px4 v1.17.0: {versioned_engine_path('v1.17.0')}", stdout)
        self.assertIn("PX4 v1.18.0 (0123456789)", stdout)
        self.assertIn("several PX4 versions", stdout)

        with mock.patch.dict(os.environ, {PX4_ENV: "v1.18.0"}):
            _, stdout, _ = run("engines")

        self.assertIn(f"Used without --engine and --px4: {versioned_engine_path('v1.18.0')}", stdout)

    def test_engines_without_an_engine(self):
        code, stdout, _ = run("engines")
        self.assertEqual(code, 0)
        self.assertIn("Engines found:\n  none\n", stdout)
        self.assertIn("not found", stdout)

    def test_a_version_that_is_not_installed(self):
        self.install("v1.17.0", "v1.17.0")
        code, _, stderr = run("--px4", "1.18.0", EXAMPLE)
        self.assertEqual(code, 2)
        self.assertIn("no engine for PX4 v1.18.0", stderr)
        self.assertIn("Installed: v1.17.0.", stderr)

    def test_an_engine_of_another_release_is_refused(self):
        self.install("v1.18.0", "v1.17.0")
        code, stdout, stderr = run("--px4", "v1.18.0", EXAMPLE)
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("PX4 v1.18.0 was asked for", stderr)
        self.assertIn("built against PX4 v1.17.0", stderr)

    def test_the_single_engine_location_is_checked_against_the_release(self):
        directory = self.directory / "data" / "actuator-lint"
        directory.mkdir(parents=True)
        fake_engine(directory, 'echo \'{"engine_schema": 1, "px4_version": "v1.17.0"}\' > "$2"\n')
        code, _, stderr = run("--px4", "v1.18.0", EXAMPLE)
        self.assertEqual(code, 2)
        self.assertIn(f"the engine '{directory / 'actuator_lint_engine'}' was built against PX4 v1.17.0", stderr)

    def test_a_name_that_is_not_a_version(self):
        code, _, stderr = run("--px4", "../v1.17.0", EXAMPLE)
        self.assertEqual(code, 2)
        self.assertIn("is not a PX4 version", stderr)


@unittest.skipIf(ENGINE is None, f"no engine found (set {ENGINE_ENV})")
class WithEngine(unittest.TestCase):
    def report(self, path):
        code, stdout, _ = run("--engine", ENGINE, "--format", "json", path)
        self.assertEqual(code, 0)
        return json.loads(stdout)

    def pusher_gain(self, path):
        return self.report(path)["matrices"][0]["mix"][4]["thrust_x"]

    def test_pusher_gain(self):
        # PX4 issue #28829: a pusher offset in z raises the pusher's thrust gain
        self.assertAlmostEqual(self.pusher_gain("examples/standard_vtol.params"), 1.0, places=3)
        self.assertAlmostEqual(self.pusher_gain("examples/standard_vtol_pusher_offset.params"), 4.0, places=3)

    def test_qgc_export(self):
        report = self.report("examples/quad_qgc_export.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["input"]["format"], "qgc")
        self.assertEqual(report["airframe"]["num_motors"], 4)
        self.assertEqual(report["matrices"][0]["actuators"], ["motor0", "motor1", "motor2", "motor3"])

    def test_text_report(self):
        code, stdout, _ = run("--engine", ENGINE, "examples/standard_vtol.params")
        self.assertEqual(code, 0)
        self.assertIn("Standard VTOL", stdout)
        self.assertIn("0 error(s), 0 warning(s)", stdout)

    def found(self, path):
        return sorted({finding["rule"] for finding in self.report(path)["findings"]})

    def test_known_problems_trigger_their_rules(self):
        self.assertEqual(self.found("examples/standard_vtol.params"), [])
        self.assertEqual(self.found("examples/quad_qgc_export.params"), [])
        self.assertEqual(self.found("examples/standard_vtol_pusher_offset.params"), ["CA010", "CA011"])
        self.assertEqual(self.found("examples/quad_wrong_spin.params"), ["CA020"])

    def test_axis_that_is_not_independent(self):
        code, stdout, _ = run("--engine", ENGINE, "--format", "json", "examples/quad_same_spin.params")
        self.assertEqual(code, 1)
        report = json.loads(stdout)
        found = {(finding["rule"], finding["level"], finding["axis"]) for finding in report["findings"]}

        if report["matrices"][0]["axes"][2]["status"] == "dropped by PX4":
            self.assertEqual(found, {("CA002", "error", "yaw"), ("CA005", "error", "yaw")})

        else:
            self.assertEqual(found, {("CA006", "error", "yaw")})

    def test_thrust_in_the_wrong_direction(self):
        for example, axis, motor in (
            ("examples/quad_rotor_down.params", "thrust_z", "motor1"),
            ("examples/standard_vtol_pusher_backwards.params", "thrust_x", "motor4"),
        ):
            code, stdout, _ = run("--engine", ENGINE, "--format", "json", example)
            self.assertEqual(code, 1, example)
            findings = json.loads(stdout)["findings"]
            found = [(item["rule"], item["level"], item["axis"], item["actuators"]) for item in findings]
            self.assertEqual(found, [("CA012", "error", axis, [motor])], example)

    def test_needed_axis_without_control(self):
        code, stdout, _ = run("--engine", ENGINE, "--format", "json", "examples/quad_no_positions.params")
        self.assertEqual(code, 1)
        findings = json.loads(stdout)["findings"]
        found = [(finding["rule"], finding["axis"]) for finding in findings]
        self.assertEqual(found, [("CA005", "roll"), ("CA005", "pitch")])
        self.assertEqual({finding["level"] for finding in findings}, {"error"})

    def test_typing_mistakes_are_findings(self):
        example = "examples/standard_vtol_typing_mistakes.params"
        code, stdout, _ = run("--engine", ENGINE, "--format", "json", example)
        self.assertEqual(code, 1)
        report = json.loads(stdout)
        self.assertEqual([finding["rule"] for finding in report["findings"]], ["CA030", "CA031"])
        self.assertIn("line 30: CA_ROTOR4_PZ has the value '-0,05'", report["findings"][0]["message"])
        self.assertIn("CA_ROTOR3_PYY", report["findings"][1]["message"])
        self.assertNotIn("CA_ROTOR4_PZ", report["input"]["parameters"])
        self.assertEqual(run("--engine", ENGINE, "--ignore", "CA030", example)[0], 0)

    def test_integer_parameter_with_a_fraction(self):
        from actuator_lint.engine import run_engine

        if "not_integer_parameters" not in run_engine(Path(ENGINE), {"CA_AIRFRAME": "0"}):
            self.skipTest("the engine was built before it refused such values")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fraction.params"
            path.write_text("CA_AIRFRAME 2.5\nCA_ROTOR_COUNT 4\n")
            code, stdout, _ = run("--engine", ENGINE, "--format", "json", str(path))

        self.assertEqual(code, 1)
        report = json.loads(stdout)
        # PX4's default, a multirotor, and not the tiltrotor that rounding would give
        self.assertEqual(report["airframe"]["ca_airframe"], 0)
        message = report["findings"][0]["message"]
        self.assertIn("CA_AIRFRAME is an integer parameter, but the value is '2.5'", message)
        self.assertEqual(report["findings"][0]["rule"], "CA030")

    def test_byte_order_mark_and_other_digits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bom.params"
            text = Path("examples/standard_vtol.params").read_text()
            path.write_bytes(b"\xef\xbb\xbf" + text.encode())
            report = self.report(str(path))
            self.assertEqual(report["airframe"]["ca_airframe"], 2)
            self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
            # a digit that is not ASCII used to end in a traceback
            path.write_text(text + "CA_ROTOR4_PZ \uff14\n")
            code, stdout, stderr = run("--engine", ENGINE, str(path))

        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", stderr)
        self.assertIn("error CA030", stdout)

    def test_missing_rotor_count(self):
        code, stdout, _ = run("--engine", ENGINE, "--format", "json", "examples/no_rotors.params")
        self.assertEqual(code, 1)
        findings = json.loads(stdout)["findings"]
        self.assertEqual([finding["rule"] for finding in findings], ["CA001", "CA021"])
        self.assertEqual(findings[1]["actuators"], ["motor0", "motor1"])

    def test_rotors_beyond_the_count(self):
        # the remaining rotors cannot control yaw independently, which is an error (CA006, or CA002)
        example = "examples/hexa_rotor_count_4.params"
        code, stdout, _ = run("--engine", ENGINE, "--format", "json", "--fail-on", "never", example)
        self.assertEqual(code, 0)
        report = json.loads(stdout)
        self.assertEqual(report["airframe"]["num_motors"], 4)
        uncounted = [finding for finding in report["findings"] if finding["rule"] == "CA021"]
        self.assertEqual(len(uncounted), 1)
        self.assertEqual(uncounted[0]["actuators"], ["motor4", "motor5"])
        self.assertIsNone(uncounted[0]["matrix"])

    def test_fixed_wing(self):
        report = self.report("examples/fixed_wing.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["airframe"]["name"], "Fixed Wing")
        self.assertEqual(len(report["matrices"]), 1)
        matrix = report["matrices"][0]
        self.assertEqual(matrix["method"], "pseudo_inverse")
        self.assertEqual(matrix["actuators"], ["motor0", "servo0", "servo1", "servo2", "servo3"])
        # the motor only gets the thrust setpoint, every control surface only its own axis
        commands = [
            {axis: round(value, 3) for axis, value in row.items() if abs(value) > 1e-3} for row in matrix["mix"]
        ]
        self.assertEqual(
            commands, [{"thrust_x": 1.0}, {"roll": -1.0}, {"roll": 1.0}, {"pitch": 1.0}, {"yaw": 1.0}]
        )

    def test_fixed_wing_thrust_offset(self):
        report = self.report("examples/fixed_wing_thrust_offset.params")
        self.assertEqual([finding["rule"] for finding in report["findings"]], ["CA011"])
        self.assertEqual(report["findings"][0]["actuators"], ["servo2"])
        mix = report["matrices"][0]["mix"]
        self.assertAlmostEqual(mix[0]["thrust_x"], 1.509, places=3)
        self.assertAlmostEqual(mix[3]["thrust_x"], 0.491, places=3)

    def test_tailsitter(self):
        report = self.report("examples/tailsitter.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["airframe"]["name"], "VTOL Tailsitter")
        actuators = [matrix["actuators"] for matrix in report["matrices"]]
        self.assertEqual(actuators, [["motor0", "motor1"], ["servo0", "servo1"]])

    def test_tiltrotor(self):
        report = self.report("examples/tiltrotor.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["airframe"]["name"], "VTOL Tiltrotor")
        # the tilt servos come after the control surfaces and are in the matrix of the motors
        self.assertEqual(report["matrices"][0]["actuators"][4:], ["servo4", "servo5"])
        self.assertEqual(report["matrices"][1]["actuators"], ["servo0", "servo1", "servo2", "servo3"])
        self.assertEqual([round(row["yaw"], 3) for row in report["matrices"][0]["mix"]], [0, 0, 0, 0, 1, -1])
        self.assertIn("tiltrotor: matrix 0", report["notes"][-1])

    def stopped_motors(self, path):
        phases = self.report(path)["flight_phases"]

        if phases is None:
            self.skipTest("the engine was built before flight phases were reported")

        return {phase["phase"]: phase["stopped_motors"] for phase in phases if phase["stopped_motors"]}

    def test_motors_stopped_by_the_flight_phase(self):
        lift_motors = ["motor0", "motor1", "motor2", "motor3"]
        self.assertEqual(self.stopped_motors("examples/standard_vtol.params"), {"forward": lift_motors})
        # the motors that do not tilt
        self.assertEqual(self.stopped_motors("examples/tiltrotor.params"), {"forward": ["motor1", "motor3"]})
        # a tailsitter flies forward on the motors it hovers on
        self.assertEqual(self.stopped_motors("examples/tailsitter.params"), {})
        self.assertEqual(self.stopped_motors("examples/quad_qgc_export.params"), {})
        self.assertEqual(self.stopped_motors("examples/fixed_wing.params"), {})

    def test_flight_phases_in_the_text_report(self):
        code, stdout, _ = run("--engine", ENGINE, "examples/standard_vtol_pusher_offset.params")
        self.assertEqual(code, 0)

        if "does not report which motors PX4 stops" in stdout:
            self.skipTest("the engine was built before flight phases were reported")

        self.assertIn("  forward flight                motor0, motor1, motor2, motor3\n", stdout)
        mix = stdout.split("Mix of the other motors in forward flight:")[1].split("Findings")[0].split()
        # only the pusher is left, with the thrust gain of PX4 issue #28829
        self.assertEqual(mix[7], "motor4")
        self.assertAlmostEqual(float(mix[11]), 4.0)
        self.assertEqual(len(mix), 14)

    def test_tiltrotor_tilt_servo_missing(self):
        report = self.report("examples/tiltrotor_tilt_servo_missing.params")
        self.assertEqual([finding["rule"] for finding in report["findings"]], ["CA022"])
        self.assertEqual(report["findings"][0]["actuators"], ["motor0"])
        self.assertEqual(report["airframe"]["num_servos"], 5)

    def test_multirotor_with_tilt(self):
        report = self.report("examples/tricopter_tilt.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["airframe"]["name"], "MC Tilt")
        matrix = report["matrices"][0]
        self.assertEqual(matrix["actuators"], ["motor0", "motor1", "motor2", "servo0"])
        # yaw comes from the tilt servo alone
        self.assertEqual([round(row["yaw"], 3) for row in matrix["mix"]], [0, 0, 0, -1])
        self.assertEqual(report["notes"], [])

    def test_exit_codes(self):
        warnings = "examples/standard_vtol_pusher_offset.params"
        self.assertEqual(run("--engine", ENGINE, warnings)[0], 0)
        self.assertEqual(run("--engine", ENGINE, "--fail-on", "warning", warnings)[0], 1)
        self.assertEqual(run("--engine", ENGINE, "--fail-on", "warning", "--ignore", "CA010,ca011", warnings)[0], 0)
        self.assertEqual(run("--engine", ENGINE, "examples/no_rotors.params")[0], 1)
        self.assertEqual(run("--engine", ENGINE, "--fail-on", "never", "examples/no_rotors.params")[0], 0)

    def test_diff(self):
        before, after = "examples/standard_vtol.params", "examples/standard_vtol_pusher_offset.params"
        code, stdout, _ = run("diff", "--engine", ENGINE, "--format", "json", before, after)
        self.assertEqual(code, 0)
        diff = json.loads(stdout)
        self.assertEqual(diff["parameters"], [{"name": "CA_ROTOR4_PZ", "before": None, "after": "-0.05"}])
        self.assertEqual(sorted(item["rule"] for item in diff["findings"]["new"]), ["CA010", "CA011"])
        self.assertEqual(len(diff["matrices"]), 6)

    def test_diff_exit_codes(self):
        before, after = "examples/standard_vtol.params", "examples/standard_vtol_pusher_offset.params"
        # only findings that are new in the second file count
        self.assertEqual(run("diff", "--engine", ENGINE, "--fail-on", "warning", before, after)[0], 1)
        self.assertEqual(run("diff", "--engine", ENGINE, "--fail-on", "warning", after, before)[0], 0)
        self.assertEqual(run("diff", "--engine", ENGINE, "--fail-on", "warning", after, after)[0], 0)
        self.assertEqual(run("diff", "--engine", ENGINE, before, "does/not/exist")[0], 2)

    def test_markdown_report(self):
        code, stdout, _ = run("--engine", ENGINE, "--format", "markdown", "examples/quad_wrong_spin.params")
        self.assertEqual(code, 0)
        self.assertIn("**warning [CA020](", stdout)

    def test_unsupported_airframe(self):
        path = Path(os.environ.get("TMPDIR", "/tmp")) / "actuator-lint-test-unsupported.params"
        path.write_text("CA_AIRFRAME 5\n")
        self.addCleanup(path.unlink)
        code, _, stderr = run("--engine", ENGINE, str(path))
        self.assertEqual(code, 2)
        self.assertIn("not supported yet", stderr)


if __name__ == "__main__":
    unittest.main()
