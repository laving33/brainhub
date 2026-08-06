import json
import tempfile
import unittest
from pathlib import Path

from mcp_package.brainhub_core.artifacts import artifact_catalog


class ArtifactCatalogTests(unittest.TestCase):
    def test_catalog_derives_location_from_workspace_not_sidecar(self):
        workspace = Path(tempfile.mkdtemp(prefix="brainhub-artifacts-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(workspace, ignore_errors=True))
        artifact_dir = workspace / "artifacts/reports"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "release.md").write_text("# Release\n", encoding="utf-8")
        (artifact_dir / "release.md.meta.json").write_text(
            json.dumps({
                "kind": "html",
                "task": "release-readiness",
                "agent": "chief",
                "stored_path": "../../not-trusted",
            }),
            encoding="utf-8",
        )

        payload = artifact_catalog(workspace, kind="report")

        self.assertEqual(payload["count"], 1)
        record = payload["artifacts"][0]
        self.assertEqual(record["kind"], "report")
        self.assertEqual(record["stored_path"], "artifacts/reports/release.md")
        self.assertEqual(record["task"], "release-readiness")


if __name__ == "__main__":
    unittest.main()
