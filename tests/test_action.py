# SPDX-License-Identifier: BSD-3-Clause
"""The script the GitHub Action runs, with this checkout as the installed tool.

The install script downloads a release and is checked by the "action check" workflow.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from actuator_lint import DISCLAIMER
from actuator_lint.engine import ENGINE_ENV, EngineError, find_engine

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "action" / "run.sh"

try:
    # absolute: the tests run it from another directory, and CI names it with a relative path
    ENGINE = str(find_engine().resolve())
except EngineError:
    ENGINE = None


@unittest.skipUnless(ENGINE and shutil.which("bash"), "needs a built engine and bash")
class Run(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)
        tool = self.work / "bin" / "actuator-lint"
        tool.parent.mkdir()
        tool.write_text(f'#!/bin/sh\nPYTHONPATH="{ROOT}" exec "{sys.executable}" -m actuator_lint "$@"\n')
        tool.chmod(0o755)

        for name in ("fixed_wing", "standard_vtol_pusher_offset", "quad_rotor_down"):
            shutil.copy(ROOT / "examples" / f"{name}.params", self.work)

        shutil.copy(ROOT / "examples" / "fixed_wing.params", self.work / "with space.params")

    def run_action(self, files, **inputs):
        environment = {
            **os.environ,
            "PATH": f"{self.work / 'bin'}{os.pathsep}{os.environ['PATH']}",
            ENGINE_ENV: ENGINE,
            "INPUT_FILES": files,
            "GITHUB_STEP_SUMMARY": str(self.work / "summary.md"),
            "GITHUB_OUTPUT": str(self.work / "output.txt"),
            **{f"INPUT_{name.upper()}": value for name, value in inputs.items()},
        }

        for name in ("summary.md", "output.txt"):
            (self.work / name).write_text("")

        result = subprocess.run(["bash", str(SCRIPT)], cwd=self.work, env=environment, capture_output=True, text=True)
        outputs = dict(line.split("=") for line in (self.work / "output.txt").read_text().split())
        return result, outputs, (self.work / "summary.md").read_text()

    def test_files_without_errors_pass_and_are_reported(self):
        result, outputs, summary = self.run_action("fixed_wing.params\n\n  with space.params  \r\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(outputs, {"files": "2", "failed": "0"})
        self.assertEqual(summary.count("### actuator-lint report"), 2)
        self.assertEqual(summary.count(DISCLAIMER), 2)
        self.assertIn("with space.params", summary)
        self.assertIn(DISCLAIMER, result.stdout)

    def test_a_pattern_and_an_error_finding(self):
        result, outputs, summary = self.run_action("*.params")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(outputs, {"files": "4", "failed": "1"})
        self.assertIn("::error file=quad_rotor_down.params::", result.stdout)
        self.assertEqual(summary.count("### actuator-lint report"), 4)

    def test_fail_on_and_arguments(self):
        result, outputs, _ = self.run_action("standard_vtol_pusher_offset.params", fail_on="warning")
        self.assertEqual((result.returncode, outputs["failed"]), (1, "1"))
        result, outputs, summary = self.run_action(
            "standard_vtol_pusher_offset.params", fail_on="warning", arguments="--ignore CA010,CA011"
        )
        self.assertEqual((result.returncode, outputs["failed"]), (0, "0"), result.stdout)
        self.assertNotIn("**warning", summary)
        result, _, _ = self.run_action("quad_rotor_down.params", fail_on="never")
        self.assertEqual(result.returncode, 0)
        result, _, _ = self.run_action("fixed_wing.params", fail_on="always")
        self.assertEqual(result.returncode, 2)

    def test_what_cannot_be_checked_fails(self):
        result, outputs, _ = self.run_action("missing.params\nnothing-*.params")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(outputs, {"files": "1", "failed": "2"})
        self.assertIn("no file matches 'nothing-*.params'", result.stdout)
        result, _, _ = self.run_action("\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("the input 'files' is empty", result.stdout)

    def test_summary_can_be_switched_off(self):
        result, _, summary = self.run_action("fixed_wing.params", summary="false")
        self.assertEqual((result.returncode, summary), (0, ""))

    def test_an_option_like_file_name_is_a_file(self):
        shutil.copy(ROOT / "examples" / "fixed_wing.params", self.work / "--version")
        result, outputs, _ = self.run_action("--version")
        self.assertEqual((result.returncode, outputs["files"]), (0, "1"), result.stdout)
        self.assertIn("Input:     --version", result.stdout)
