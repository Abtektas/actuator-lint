# SPDX-License-Identifier: BSD-3-Clause
"""The release notes that tools/release_notes.py writes for the release page."""

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "tools" / "release_notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

LINK = re.compile(r"\]\(([^)]+)\)")


class Links(unittest.TestCase):
    def test_links_inside_the_repository_become_absolute(self):
        text = "[Guide](docs/getting-started.md#install), [web](https://example.org) and [here](#top)"
        self.assertEqual(
            release_notes.absolute_links(text, "1.2.3"),
            f"[Guide]({release_notes.REPOSITORY}/blob/v1.2.3/docs/getting-started.md#install), "
            "[web](https://example.org) and [here](#top)",
        )

    def test_every_link_of_every_changelog_section_is_absolute_and_names_a_file(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        versions = re.findall(r"^## (\d+\.\d+\.\d+) ", text, re.MULTILINE)
        self.assertTrue(versions)
        prefix = f"{release_notes.REPOSITORY}/blob/v"

        for version in versions:
            notes = release_notes.absolute_links(release_notes.changelog_section(version), version)

            for target in LINK.findall(notes):
                with self.subTest(version=version, target=target):
                    self.assertTrue(target.startswith(("https://", "#")), target)

                    if target.startswith(prefix + version + "/"):
                        path = target[len(prefix + version + "/") :].split("#")[0]
                        self.assertTrue((ROOT / path).exists(), path)

    def test_the_notes_end_with_the_terms(self):
        self.assertIn("without warranty of any kind", release_notes.INSTALL)
        self.assertIn("PX4 is a trademark of Dronecode Project, Inc.", release_notes.INSTALL)


if __name__ == "__main__":
    unittest.main()
