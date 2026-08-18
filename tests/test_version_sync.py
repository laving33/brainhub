"""The version string is declared in five places; this is what keeps them equal.

``BRAINHUB_VERSION`` is what the runtime reports, and the other four are what a
packager, an MCP registry, and ``pip show`` report. Nothing previously compared
them, so a release that bumped the runtime and forgot the manifests would ship a
package whose metadata disagreed with the thing inside it — and every existing
test would still pass, because each surface is individually self-consistent.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from mcp_package.brainhub_core.version import BRAINHUB_VERSION  # noqa: E402


class VersionSyncTests(unittest.TestCase):
    def test_package_metadata_matches_the_runtime_version(self):
        pyproject = (ROOT / "mcp_package" / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        self.assertIsNotNone(match, "mcp_package/pyproject.toml declares no version")
        self.assertEqual(match.group(1), BRAINHUB_VERSION)

    def test_dunder_version_matches_the_runtime_version(self):
        init = (ROOT / "mcp_package" / "brainhub_mcp" / "__init__.py").read_text(
            encoding="utf-8"
        )
        match = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.MULTILINE)
        self.assertIsNotNone(match, "brainhub_mcp/__init__.py declares no __version__")
        self.assertEqual(match.group(1), BRAINHUB_VERSION)

    def test_every_version_field_in_server_json_matches(self):
        manifest = json.loads(
            (ROOT / "mcp_package" / "server.json").read_text(encoding="utf-8")
        )
        found = []

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "version" and isinstance(value, str):
                        found.append(value)
                    else:
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(manifest)
        self.assertTrue(found, "server.json declares no version at all")
        for value in found:
            self.assertEqual(value, BRAINHUB_VERSION)

    def test_changelog_documents_the_current_version(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        headings = re.findall(r"^##\s+(.+)$", changelog, re.MULTILINE)
        released = [h.strip() for h in headings if h.strip()[:1].isdigit()]
        self.assertIn(
            BRAINHUB_VERSION,
            released,
            f"CHANGELOG.md has no '## {BRAINHUB_VERSION}' section",
        )


if __name__ == "__main__":
    unittest.main()
