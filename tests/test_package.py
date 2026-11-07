# SPDX-License-Identifier: BSD-3-Clause
"""The names of the engine packages, and what engine/package.sh puts into one.

Packages of 0.4.2 and earlier were named actuator_lint_engine-px4-<PX4 version>-... and had PX4's
license as LICENSE-PX4. Newer ones have no PX4 in their names. The install steps must work with both.
"""

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from actuator_lint import legal
from actuator_lint.engine import EngineError, find_engine

ROOT = Path(__file__).parent.parent
PX4_DIR = os.environ.get("ACTUATOR_LINT_PX4_DIR")

try:
    # absolute: package.sh runs it from another directory, and CI names it with a relative path
    ENGINE = str(find_engine().resolve())
except EngineError:
    ENGINE = None

# how the install steps choose the package of a platform in SHA256SUMS
LOOKUP = 'grep -o "actuator_lint_engine-.*-'
INSTALL_STEPS = ("README.md", "action/install.sh", ".github/workflows/install-check.yml")

PLATFORMS = ("linux-x86_64", "linux-arm64", "macos-arm64")
CHECKSUM = "0" * 64


def checksums(name: str) -> str:
    """A SHA256SUMS file as the release workflow writes it, for packages named like name."""
    lines = [f"{CHECKSUM}  actuator_lint-9.9.9-py3-none-any.whl", f"{CHECKSUM}  actuator_lint-9.9.9.tar.gz"]
    lines += [f"{CHECKSUM}  {name.format(platform=platform)}.tar.gz" for platform in PLATFORMS]
    return "\n".join(lines) + "\n"


class Names(unittest.TestCase):
    def test_the_install_steps_find_old_and_new_packages(self):
        for path in INSTALL_STEPS:
            with self.subTest(path=path):
                self.assertIn(LOOKUP, (ROOT / path).read_text(encoding="utf-8"))

        for name in (
            "actuator_lint_engine-v1.18.0-schema1-{platform}",
            "actuator_lint_engine-v1.18.0-rc1-schema1-{platform}",
            # 0.4.2 and earlier
            "actuator_lint_engine-px4-v1.17.0-schema1-{platform}",
        ):
            text = checksums(name)

            for platform in PLATFORMS:
                with self.subTest(name=name, platform=platform):
                    found = re.findall(rf"actuator_lint_engine-.*-{re.escape(platform)}", text)
                    self.assertEqual(found, [name.format(platform=platform)])

    def test_package_sh_names_the_package_and_the_license_without_px4(self):
        script = (ROOT / "engine" / "package.sh").read_text(encoding="utf-8")
        self.assertIn('NAME="actuator_lint_engine-${PX4_VERSION}-schema${SCHEMA}-${PLATFORM}"', script)
        self.assertIn('"${WORK}/${NAME}/LICENSE-THIRD-PARTY"', script)
        self.assertIn("contains that license text as LICENSE-THIRD-PARTY", legal.ENGINE_NOTICE)

    def test_no_file_of_the_project_is_named_after_px4(self):
        """PX4 is a trademark. The golden reports keep the names of PX4's own airframe scripts."""
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()

        if not files:
            self.skipTest("not a git checkout")

        named = [name for name in files if "px4" in name.lower() and not name.startswith("tests/golden/")]
        self.assertEqual(named, [])


@unittest.skipUnless(
    ENGINE and PX4_DIR and shutil.which("bash") and shutil.which("tar"),
    "needs a built engine, ACTUATOR_LINT_PX4_DIR, bash and tar",
)
class Package(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        out = Path(cls.directory.name)
        cls.result = subprocess.run(
            ["bash", str(ROOT / "engine" / "package.sh"), ENGINE, PX4_DIR, "test-platform", str(out)],
            capture_output=True,
            text=True,
        )
        cls.archives = sorted(out.glob("*.tar.gz"))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertEqual(len(self.archives), 1, self.archives)

    def test_the_archive_has_no_px4_in_its_name(self):
        name = self.archives[0].name
        self.assertRegex(name, r"^actuator_lint_engine-v\d+\.\d+\.\d+\S*-schema\d+-test-platform\.tar\.gz$")
        self.assertNotIn("px4", name.lower())
        self.assertTrue(Path(str(self.archives[0]) + ".sha256").is_file())

    def test_the_archive_has_the_licenses_and_the_terms(self):
        top = self.archives[0].name[: -len(".tar.gz")]

        with tarfile.open(self.archives[0]) as archive:
            names = sorted(archive.getnames())
            self.assertEqual(
                names,
                sorted(
                    [top]
                    + [
                        f"{top}/{name}"
                        for name in ("actuator_lint_engine", "LICENSE", "LICENSE-THIRD-PARTY", "README.txt")
                    ]
                ),
            )

            def read(name: str) -> str:
                return archive.extractfile(f"{top}/{name}").read().decode("utf-8")

            self.assertEqual(read("LICENSE"), (ROOT / "LICENSE").read_text(encoding="utf-8"))
            self.assertEqual(read("LICENSE-THIRD-PARTY"), (Path(PX4_DIR) / "LICENSE").read_text(encoding="utf-8"))
            readme = " ".join(read("README.txt").split())

        self.assertIn("Its license text is in LICENSE-THIRD-PARTY.", readme)
        self.assertIn("without warranty of any kind", readme)
        self.assertIn("accept no liability and no responsibility", readme)
        self.assertIn("not an airworthiness approval", readme)
        self.assertIn("PX4 is a trademark of Dronecode Project, Inc.", readme)
        self.assertIn("not affiliated with or endorsed by the PX4 project", readme)
