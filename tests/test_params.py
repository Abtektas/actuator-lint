# SPDX-License-Identifier: BSD-3-Clause
import tempfile
import unittest
from pathlib import Path

from actuator_lint.params import ParamFileError, detect_format, parse_file, parse_text


class DetectFormat(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(detect_format("# comment\nCA_AIRFRAME 2\n"), "plain")

    def test_airframe(self):
        self.assertEqual(detect_format("#!/bin/sh\nparam set-default CA_AIRFRAME 2\n"), "airframe")

    def test_qgc(self):
        self.assertEqual(detect_format("# Onboard parameters\n1\t1\tCA_AIRFRAME\t2\t6\n"), "qgc")


class Plain(unittest.TestCase):
    def test_values_and_comments(self):
        result = parse_text("# header\nCA_AIRFRAME 2\n\nCA_ROTOR4_PZ -0.05  # offset\n")
        self.assertEqual(result.format, "plain")
        self.assertEqual(result.params, {"CA_AIRFRAME": "2", "CA_ROTOR4_PZ": "-0.05"})
        self.assertEqual(result.notes, [])

    def test_bad_lines_are_not_used_and_recorded(self):
        result = parse_text("CA_AIRFRAME 2\nca_lower 1\nCA_ROTOR0_PX abc\nCA_ROTOR0_PY nan\nONLYNAME\nMPC_X 1,5\n")
        self.assertEqual(result.params, {"CA_AIRFRAME": "2"})
        self.assertEqual(result.notes, [])
        # in a parameter file every line counts, whatever the parameter
        self.assertEqual(len(result.unread), 5)
        self.assertIn("line 2: 'ca_lower' is not a valid parameter name", result.unread[0])
        self.assertIn("line 3: CA_ROTOR0_PX has the value 'abc', which is not a number", result.unread[1])
        self.assertIn("line 5: expected 'NAME VALUE'", result.unread[3])

    def test_only_numbers_the_engine_reads_the_same_way(self):
        good = ("1", "-0.05", "+2", ".5", "5.", "1e-3", "2.5E+2", "0000.1")
        bad = ("1_0", "\uff14", "nan", "inf", "0x10", "1,0", "1e", "--1", "1.0f", "9" * 41, "1e999")
        text = "".join(f"P{index} {value}\n" for index, value in enumerate(good + bad))
        result = parse_text(text)
        self.assertEqual(list(result.params.values()), list(good))
        self.assertEqual(len(result.unread), len(bad))

    def test_byte_order_mark(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bom.params"
            path.write_bytes(b"\xef\xbb\xbfCA_AIRFRAME 2\nCA_ROTOR_COUNT 5\n")
            result = parse_file(path)

        self.assertEqual(result.params, {"CA_AIRFRAME": "2", "CA_ROTOR_COUNT": "5"})
        self.assertEqual(result.unread, [])

    def test_last_value_wins(self):
        result = parse_text("CA_ROTOR_COUNT 4\nCA_ROTOR_COUNT 5\n")
        self.assertEqual(result.params["CA_ROTOR_COUNT"], "5")
        self.assertIn("more than once", result.notes[0])

    def test_no_parameters_is_an_error(self):
        with self.assertRaises(ParamFileError):
            parse_text("# nothing here\n")


class Airframe(unittest.TestCase):
    SCRIPT = (
        "#!/bin/sh\n"
        ". ${R}etc/init.d/rc.vtol_defaults\n"
        "param set-default CA_AIRFRAME 2\n"
        "param set CA_ROTOR_COUNT 5 # pusher included\n"
        "# param set-default CA_ROTOR0_PX 9\n"
        "param set-default PWM_MAIN_FUNC1 ${FUNC}\n"
        "if [ $X = yes ]\nthen\n\tparam set-default CA_ROTOR4_AX 1\nfi\n"
    )

    def test_param_lines(self):
        result = parse_text(self.SCRIPT)
        self.assertEqual(result.format, "airframe")
        self.assertEqual(result.params, {"CA_AIRFRAME": "2", "CA_ROTOR_COUNT": "5", "CA_ROTOR4_AX": "1"})

    def test_limits_are_reported(self):
        result = parse_text(self.SCRIPT)
        notes = "\n".join(result.notes)
        self.assertIn("which is not a number", notes)
        self.assertIn("was not found", notes)
        self.assertIn("conditional", notes)
        # a value from a shell variable is common for other parameters and only a note
        self.assertEqual(result.unread, [])

    def test_a_control_allocation_line_that_cannot_be_used(self):
        result = parse_text("param set-default CA_AIRFRAME 2\nparam set-default CA_ROTOR_COUNT ${COUNT}\n")
        self.assertEqual(result.params, {"CA_AIRFRAME": "2"})
        self.assertEqual(len(result.unread), 1)
        self.assertIn("line 2: CA_ROTOR_COUNT has the value '${COUNT}'", result.unread[0])


class SourcedFiles(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        # same layout as PX4's ROMFS/px4fmu_common
        self.root = Path(directory.name)
        (self.root / "init.d" / "airframes").mkdir(parents=True)
        (self.root / "init.d" / "rc.fw_defaults").write_text(
            "param set-default CA_AIRFRAME 1\nparam set-default CA_ROTOR_COUNT 1\n"
        )
        self.script = self.root / "init.d" / "airframes" / "2100_plane"

    def test_sourced_defaults_are_included(self):
        self.script.write_text(". ${R}etc/init.d/rc.fw_defaults\nparam set-default CA_ROTOR_COUNT 2\n")
        result = parse_file(self.script)
        self.assertEqual(result.params, {"CA_AIRFRAME": "1", "CA_ROTOR_COUNT": "2"})
        self.assertEqual(result.notes, ["included the sourced file rc.fw_defaults"])

    def test_missing_sourced_file_is_reported(self):
        self.script.write_text(". ${R}etc/init.d/rc.none\nparam set-default CA_ROTOR_COUNT 2\n")
        notes = "\n".join(parse_file(self.script).notes)
        self.assertIn("was not found", notes)
        self.assertIn("CA_AIRFRAME is not set", notes)

    def test_a_script_that_sources_itself_ends(self):
        self.script.write_text(". ${R}etc/init.d/airframes/2100_plane\nparam set-default CA_AIRFRAME 0\n")
        self.assertEqual(parse_file(self.script).params, {"CA_AIRFRAME": "0"})


class Qgc(unittest.TestCase):
    def test_export(self):
        result = parse_file("examples/quad_qgc_export.params")
        self.assertEqual(result.format, "qgc")
        self.assertEqual(len(result.params), 15)
        self.assertEqual(result.params["CA_ROTOR_COUNT"], "4")
        self.assertEqual(result.notes, [])

    def test_several_components(self):
        result = parse_text("1\t1\tCA_AIRFRAME\t0\t6\n1\t2\tCA_ROTOR_COUNT\t4\t6\n")
        self.assertIn("more than one", result.notes[0])


class Files(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(ParamFileError):
            parse_file("does/not/exist.params")

    def test_forced_format(self):
        with self.assertRaises(ParamFileError):
            parse_text("CA_AIRFRAME 2\n", file_format="airframe")


if __name__ == "__main__":
    unittest.main()
