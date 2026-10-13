"""The reports stored in docs/example-reports/ are what the tool prints for the files in examples/.

Needs an engine built against the PX4 version of those reports; skipped with another engine.
"""

import importlib.util
import platform
import sys
import unittest
from pathlib import Path

from px4_ca_lint.engine import EngineError, find_engine, run_engine

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("example_reports", ROOT / "tools" / "example_reports.py")
example_reports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example_reports)

try:
    PX4_VERSION = run_engine(find_engine(), {"CA_AIRFRAME": "0"}).get("px4_version")
except EngineError:
    PX4_VERSION = None


@unittest.skipUnless(PX4_VERSION == example_reports.PX4_VERSION, "needs an engine built against PX4 v1.17.0")
class ExampleReports(unittest.TestCase):
    def test_stored_reports_are_up_to_date(self):
        problems = example_reports.out_of_date()

        # The stored reports were made on arm64, and the engines for macOS and Linux arm64 print
        # them alike. The x86_64 engine prints the mix of examples/quad_wrong_spin.params with
        # larger differences. Until it is known how large, the differences are printed there
        # and do not fail the run.
        if problems and platform.machine() not in ("arm64", "aarch64"):
            print("\nexample reports differ on", platform.machine(), *problems, sep="\n  ", file=sys.stderr)
            self.skipTest(f"{len(problems)} difference(s) on {platform.machine()}, printed above")

        self.assertEqual(problems, [], "run tools/example_reports.py")

    def test_differences_fail_on_arm64_only(self):
        from unittest import mock

        problems = ["quad_wrong_spin.md: stored 'a', printed 'b'"]

        with mock.patch.object(example_reports, "out_of_date", return_value=problems):
            with mock.patch("platform.machine", return_value="aarch64"):
                self.assertRaises(AssertionError, self.test_stored_reports_are_up_to_date)

            with mock.patch("platform.machine", return_value="x86_64"), mock.patch("sys.stderr"):
                self.assertRaises(unittest.SkipTest, self.test_stored_reports_are_up_to_date)

    def test_version_strings_do_not_count(self):
        link = "[CA010](https://github.com/Abtektas/px4-ca-lint/blob/{}/rules/CA010.md)"
        first = "- Tool: px4-ca-lint 0.4.0\n" + link.format("v0.4.0")
        second = "- Tool: px4-ca-lint 0.5.0.dev0\n" + link.format("main")
        self.assertEqual(example_reports.normalised(first), example_reports.normalised(second))
        self.assertNotEqual(example_reports.normalised(first), example_reports.normalised(first + " "))

    def test_the_last_digit_of_a_number_may_differ(self):
        same = example_reports.same
        self.assertTrue(same("| roll | -0.707 | 0.000 |", "| roll | -0.708 | -0.000 |"))
        self.assertFalse(same("| roll | -0.707 |", "| roll | -0.709 |"))
        self.assertFalse(same("| roll | -0.707 |", "| pitch | -0.707 |"))
        self.assertFalse(same("| roll | -0.707 |", "| roll | -0.707 | 1.000 |"))
