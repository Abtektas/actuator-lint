# SPDX-License-Identifier: BSD-3-Clause
"""The reports stored in docs/example-reports/ are what the tool prints for the files in examples/.

Needs an engine built against the PX4 version of those reports; skipped with another engine.
"""

import importlib.util
import unittest
from pathlib import Path

from actuator_lint.engine import EngineError, find_engine, run_engine

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

    def test_a_difference_names_the_file_and_the_lines(self):
        from unittest import mock

        files = example_reports.build()
        files["quad_qgc_export.md"] = files["quad_qgc_export.md"].replace("4 motors", "5 motors")

        with mock.patch.object(example_reports, "build", return_value=files):
            problems = example_reports.out_of_date()

        self.assertEqual(len(problems), 1)
        self.assertIn("quad_qgc_export.md: stored", problems[0])
        self.assertIn("5 motors", problems[0])

    def test_the_mix_of_the_wrong_spin_example_may_differ_more(self):
        from unittest import mock

        name = "quad_wrong_spin.md"
        files = example_reports.build()
        stored = (example_reports.OUTPUT / name).read_text(encoding="utf-8")
        # what the x86_64 engine prints
        x86_64 = stored.replace("| 0.073 |", "| 0.009 |").replace("| -1.927 |", "| -1.991 |")
        self.assertNotEqual(x86_64, stored)

        with mock.patch.object(example_reports, "build", return_value={**files, name: x86_64}):
            self.assertEqual(example_reports.out_of_date(), [])

        # the same difference in another example is one, and so is a larger one here
        self.assertFalse(example_reports.same(stored, x86_64))
        larger = stored.replace("| 0.073 |", "| 0.300 |")

        with mock.patch.object(example_reports, "build", return_value={**files, name: larger}):
            self.assertEqual(len(example_reports.out_of_date()), 2)

    def test_version_strings_do_not_count(self):
        link = "[CA010](https://github.com/Abtektas/actuator-lint/blob/{}/rules/CA010.md)"
        first = "- Tool: actuator-lint 0.4.0\n" + link.format("v0.4.0")
        second = "- Tool: actuator-lint 0.5.0.dev0\n" + link.format("main")
        self.assertEqual(example_reports.normalised(first), example_reports.normalised(second))
        self.assertNotEqual(example_reports.normalised(first), example_reports.normalised(first + " "))

    def test_the_last_digit_of_a_number_may_differ(self):
        same = example_reports.same
        self.assertTrue(same("| roll | -0.707 | 0.000 |", "| roll | -0.708 | -0.000 |"))
        self.assertFalse(same("| roll | -0.707 |", "| roll | -0.709 |"))
        self.assertFalse(same("| roll | -0.707 |", "| pitch | -0.707 |"))
        self.assertFalse(same("| roll | -0.707 |", "| roll | -0.707 | 1.000 |"))
