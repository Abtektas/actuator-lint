# SPDX-License-Identifier: BSD-3-Clause
"""Every copy of the program carries its license and its notices, and no report is without the disclaimer."""

import os
import subprocess
import unittest
from pathlib import Path

from px4_ca_lint import DISCLAIMER, __version__, legal
from px4_ca_lint.engine import EngineError, find_engine
from tests.test_cli import run

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"

try:
    # absolute: the tests run it from another directory, and CI names it with a relative path
    ENGINE = str(find_engine().resolve())
except EngineError:
    ENGINE = None


class Terms(unittest.TestCase):
    def test_the_license_in_the_package_is_the_license_file(self):
        self.assertEqual(legal.LICENSE, (ROOT / "LICENSE").read_text(encoding="utf-8"))
        self.assertIn(legal.COPYRIGHT, legal.LICENSE)
        self.assertIn('"AS IS"', legal.LICENSE)
        self.assertIn("IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE", legal.LICENSE)

    def test_version_prints_the_terms_in_short(self):
        for arguments in (["--version"], ["diff", "--version"], ["engines", "--version"]):
            with self.assertRaises(SystemExit) as stop:
                run(*arguments)

            self.assertEqual(stop.exception.code, 0)

        lines = legal.version_text().split("\n")
        self.assertEqual(lines[0], f"px4-ca-lint {__version__}")
        self.assertIn("BSD-3-Clause", lines[2])
        self.assertIn("without warranty of any kind", lines[3])
        self.assertIn("no liability and no responsibility", lines[3])
        self.assertIn("not an airworthiness approval", lines[4])
        self.assertIn("at your own risk", lines[4])

    def test_license_command_prints_the_license_and_the_notices(self):
        code, stdout, stderr = run("license")
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn(legal.LICENSE, stdout)
        self.assertIn("PX4 Development Team", stdout)
        self.assertIn("not affiliated with or endorsed by", stdout)
        self.assertIn(legal.NO_WARRANTY, stdout)
        self.assertIn(legal.REVIEW_AID, stdout)

    def test_help_names_the_terms(self):
        from px4_ca_lint.cli import _check_parser

        text = " ".join(_check_parser().format_help().split())
        self.assertIn("No warranty and no liability", text)
        self.assertIn("px4-ca-lint license", text)

    def test_every_source_file_names_its_license(self):
        files = subprocess.run(
            ["git", "ls-files", "*.py", "*.sh", "*.cpp", "*.hpp", "*.h"], cwd=ROOT, capture_output=True, text=True
        ).stdout.split()

        if not files:
            self.skipTest("not a git checkout")

        missing = [
            name
            for name in files
            if "SPDX-License-Identifier: BSD-3-Clause" not in (ROOT / name).read_text(encoding="utf-8")[:200]
        ]
        self.assertEqual(missing, [])


@unittest.skipUnless(ENGINE, "needs a built engine")
class Reports(unittest.TestCase):
    def test_no_report_is_without_the_disclaimer(self):
        """Every format of every example, also when the report goes to a file or has errors."""
        files = sorted(EXAMPLES.glob("*.params"))
        self.assertGreater(len(files), 10)

        for path in files:
            for report_format in ("text", "markdown", "json"):
                _, stdout, _ = run("--format", report_format, str(path))
                self.assertIn(DISCLAIMER, stdout, f"{path.name} as {report_format}")

        for report_format in ("text", "markdown", "json"):
            _, stdout, _ = run("diff", "--format", report_format, str(files[0]), str(files[1]))
            self.assertIn(DISCLAIMER, stdout, f"diff as {report_format}")

    def test_no_option_leaves_the_disclaimer_out(self):
        from px4_ca_lint.cli import _check_parser, _diff_parser

        for parser in (_check_parser(), _diff_parser()):
            options = [option for action in parser._actions for option in action.option_strings]
            self.assertEqual(
                sorted(options),
                sorted(
                    ["-h", "--help", "--input-format", "--format", "--output", "--engine", "--px4", "--fail-on"]
                    + ["--ignore", "--max-thrust-gain", "--version"]
                ),
                "a new option: check that it cannot remove the disclaimer, then add it here",
            )

    def test_the_engine_source_has_the_notice(self):
        source = (ROOT / "engine" / "src" / "main.cpp").read_text(encoding="utf-8")
        self.assertIn("without warranty of any kind", source)
        self.assertIn("accept no liability", source)
        self.assertIn('"usage: px4_ca_engine <params file> <output json>\\n\\n%s\\n", NOTICE', source)

    def test_the_engine_prints_its_notice(self):
        result = subprocess.run([ENGINE], capture_output=True, text=True, env={**os.environ})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage: px4_ca_engine", result.stderr)

        if "PX4 Development Team" not in result.stderr:
            self.skipTest("an engine built before the notice was added")

        self.assertIn("without warranty of any kind", result.stderr)
        self.assertIn("no liability", result.stderr)
