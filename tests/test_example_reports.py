"""The reports stored in docs/example-reports/ are what the tool prints for the files in examples/.

Needs an engine built against the PX4 version of those reports; skipped with another engine.
"""

import importlib.util
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
        self.assertEqual(example_reports.out_of_date(), [], "run tools/example_reports.py")

    def test_version_strings_do_not_count(self):
        first = "- Tool: px4-ca-lint 0.4.0\n[CA010](https://github.com/Abtektas/px4-ca-lint/blob/v0.4.0/rules/CA010.md)"
        second = "- Tool: px4-ca-lint 0.5.0.dev0\n[CA010](https://github.com/Abtektas/px4-ca-lint/blob/main/rules/CA010.md)"
        self.assertEqual(example_reports.normalised(first), example_reports.normalised(second))
        self.assertNotEqual(example_reports.normalised(first), example_reports.normalised(first + " "))

    def test_the_last_digit_of_a_number_may_differ(self):
        same = example_reports.same
        self.assertTrue(same("| roll | -0.707 | 0.000 |", "| roll | -0.708 | -0.000 |"))
        self.assertFalse(same("| roll | -0.707 |", "| roll | -0.709 |"))
        self.assertFalse(same("| roll | -0.707 |", "| pitch | -0.707 |"))
        self.assertFalse(same("| roll | -0.707 |", "| roll | -0.707 | 1.000 |"))
