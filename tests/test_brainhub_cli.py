from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import brainhub


class BrainHubCliTests(unittest.TestCase):
    def test_init_creates_runtime_workspace_with_artifact_and_knowledge_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "brainhub"

            code = brainhub.main(["init", str(workspace)])

            self.assertEqual(code, 0)
            for rel_path in (
                "raw",
                "wiki/index.md",
                "wiki/log.md",
                "wiki/memories",
                "knowledge/runbooks",
                "knowledge/syntheses",
                "artifacts/reports",
                "artifacts/html",
                "artifacts/charts",
                "artifacts/exports",
                "BRAINHUB.md",
                "bh",
            ):
                self.assertTrue((workspace / rel_path).exists(), rel_path)

    def test_init_emits_executable_bh_launcher_pinned_to_this_workspace(self):
        # A tenant vault brain's `bh` is the only NDA-safe entry point, and the
        # AM skeleton tells AMs it exists. The pin is the load-bearing part: a
        # launcher pinned elsewhere writes client data there and succeeds, so
        # assert the target, not just the file.
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "_vault" / "brainhub"

            self.assertEqual(brainhub.main(["init", str(workspace), "--home", "am"]), 0)

            launcher = workspace / "bh"
            self.assertTrue(launcher.exists(), "init must emit the bh launcher")
            self.assertTrue(launcher.stat().st_mode & 0o111, "bh launcher must be executable")
            self.assertIn(f"BRAINHUB_HOME={workspace}", launcher.read_text(encoding="utf-8"))

    def test_init_does_not_overwrite_an_existing_bh_launcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "brainhub"
            self.assertEqual(brainhub.main(["init", str(workspace)]), 0)
            (workspace / "bh").write_text("#!/bin/sh\n# hand-tuned\n", encoding="utf-8")

            self.assertEqual(brainhub.main(["init", str(workspace)]), 0)

            self.assertIn("hand-tuned", (workspace / "bh").read_text(encoding="utf-8"))

    def test_artifact_add_copies_report_with_provenance_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "brainhub"
            source = root / "release-report.md"
            source.write_text("# Release report\n", encoding="utf-8")
            self.assertEqual(brainhub.main(["init", str(workspace)]), 0)

            code = brainhub.main([
                "artifact",
                "add",
                str(source),
                str(workspace),
                "--kind",
                "report",
                "--task",
                "release-readiness",
                "--agent",
                "chief",
                "--related",
                "knowledge/runbooks/release.md",
            ])

            self.assertEqual(code, 0)
            stored = workspace / "artifacts/reports/release-report.md"
            self.assertEqual(stored.read_text(encoding="utf-8"), "# Release report\n")
            metadata = json.loads((workspace / "artifacts/reports/release-report.md.meta.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["kind"], "report")
            self.assertEqual(metadata["task"], "release-readiness")
            self.assertEqual(metadata["agent"], "chief")
            self.assertEqual(metadata["related"], ["knowledge/runbooks/release.md"])

    def test_artifact_list_returns_catalog_records_as_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "brainhub"
            source = root / "release-report.md"
            source.write_text("# Release report\n", encoding="utf-8")
            self.assertEqual(brainhub.main(["init", str(workspace)]), 0)
            self.assertEqual(
                brainhub.main([
                    "artifact",
                    "add",
                    str(source),
                    str(workspace),
                    "--kind",
                    "report",
                    "--task",
                    "release-readiness",
                    "--agent",
                    "chief",
                ]),
                0,
            )

            output = io.StringIO()
            with redirect_stdout(output):
                code = brainhub.main(["artifact", "list", str(workspace), "--kind", "report", "--json"])

            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["artifacts"][0]["stored_path"], "artifacts/reports/release-report.md")
            self.assertEqual(payload["artifacts"][0]["task"], "release-readiness")


if __name__ == "__main__":
    unittest.main()
