# SPDX-License-Identifier: BSD-3-Clause
"""The picture stored in docs/images/terminal.svg is made from what the tool prints now.

Needs an engine built against the PX4 version of the picture; skipped with another engine.
"""

import importlib.util
import unittest
import xml.dom.minidom
from pathlib import Path
from unittest import mock

from px4_ca_lint.engine import EngineError, find_engine, run_engine

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("terminal_image", ROOT / "tools" / "terminal_image.py")
terminal_image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(terminal_image)

try:
    PX4_VERSION = run_engine(find_engine(), {"CA_AIRFRAME": "0"}).get("px4_version")
except EngineError:
    PX4_VERSION = None


class Pieces(unittest.TestCase):
    def test_a_long_line_is_wrapped_with_its_indent(self):
        line = "  warning CA010 matrix 0: " + "word " * 30
        pieces = terminal_image.wrapped(line.rstrip())
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(piece) <= terminal_image.COLUMNS for piece in pieces))
        self.assertTrue(pieces[1].startswith("    word"))
        self.assertEqual(terminal_image.wrapped("  short"), ["  short"])

    def test_only_the_start_of_a_finding_has_the_colour_of_its_level(self):
        first = terminal_image.spans("line", "  warning CA010 matrix 0: a < b")
        self.assertIn('<tspan class="warning">warning</tspan>', first)
        self.assertIn("a &lt; b", first)
        rest = terminal_image.spans("line", "  warning CA010", first=False)
        self.assertNotIn('class="warning"', rest)
        self.assertIn('class="error"', terminal_image.spans("line", "  error CA001: x"))

    def test_what_is_left_out_is_counted(self):
        report = [
            "px4-ca-lint 0.4.0",
            "",
            "Matrix 0 (pseudo_inverse)",
            "",
            "  Effectiveness: what each actuator produces on each axis",
            "",
            "  Mix: actuator command per unit of setpoint on each axis",
            "  motor0  1.000",
            "",
            "  Axes",
            "",
            "Findings",
            "  0 error(s), 0 warning(s)",
            "",
            "note",
            "",
            "This report is a review aid, not an airworthiness approval.",
        ]
        parts = terminal_image.selected(report)
        shown = sum(1 for part in parts for kind, line in part if kind != "omitted" and line in report)
        left_out = sum(int(line.split()[1]) for part in parts for kind, line in part if kind == "omitted")
        # the empty line before the disclaimer is added by the picture
        self.assertEqual(shown - 1 + left_out, len(report))
        self.assertRaises(SystemExit, terminal_image.selected, report[:-1])


NEEDED = terminal_image.example_reports.PX4_VERSION


@unittest.skipUnless(PX4_VERSION == NEEDED, f"needs an engine built against PX4 {NEEDED}")
class StoredPicture(unittest.TestCase):
    def test_stored_picture_is_up_to_date(self):
        self.assertEqual(terminal_image.out_of_date(), [], "run tools/terminal_image.py")

    def test_it_is_well_formed_and_complete_without_animation(self):
        picture = terminal_image.build()
        document = xml.dom.minidom.parseString(picture)
        self.assertEqual(document.documentElement.tagName, "svg")
        self.assertTrue(document.getElementsByTagName("title") and document.getElementsByTagName("desc"))
        # the animations only take effect inside the media query, and they start from the hidden state
        style = document.getElementsByTagName("style")[0].firstChild.data
        self.assertEqual(style.count("animation:"), 2)
        self.assertLess(style.index("@media (prefers-reduced-motion: no-preference)"), style.index("animation:"))
        self.assertNotIn("infinite", style)

    def test_a_difference_is_reported_with_its_line(self):
        changed = terminal_image.build().replace("2 warning(s)", "3 warning(s)")

        with mock.patch.object(terminal_image, "build", return_value=changed):
            problems = terminal_image.out_of_date()

        self.assertTrue(problems)
        self.assertTrue(all("terminal.svg: stored" in problem for problem in problems))
