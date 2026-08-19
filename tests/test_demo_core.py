import tempfile
import unittest
from pathlib import Path

from mcp_package.brainhub_core.demo import (
    DEMO_MARKER,
    DemoError,
    copy_runtime_files,
    create_demo_workspace,
)


ROOT = Path(__file__).resolve().parents[1]


class DemoCoreTests(unittest.TestCase):
    def test_copy_runtime_files_from_source_tree(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="link-demo-core-test-")))
        target = tmp / "target"

        copy_runtime_files(ROOT, target)

        self.assertTrue((target / "serve.py").exists())
        self.assertTrue((target / "brainhub_engine.py").exists())
        self.assertTrue((target / "BRAINHUB-SCHEMA.md").exists())
        self.assertTrue((target / "brainhub_core/frontmatter.py").exists())
        self.assertTrue((target / "logo.svg").exists())

    def test_create_demo_workspace_creates_preingested_wiki(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="link-demo-core-test-")))
        target = tmp / "demo"

        payload = create_demo_workspace(target, source_root=ROOT)

        self.assertEqual(payload["target"], str(target.resolve()))
        self.assertEqual(payload["wiki"], str((target / "wiki").resolve()))
        self.assertGreaterEqual(payload["file_count"], 1)
        self.assertTrue((target / DEMO_MARKER).exists())
        self.assertTrue((target / "START_HERE.md").exists())
        self.assertTrue((target / "wiki/_backlinks.json").exists())
        self.assertTrue((target / "wiki/_brainhub_schema.json").exists())
        self.assertTrue((target / "wiki/memories/prefer-local-personal-memory.md").exists())
        self.assertTrue((target / "raw/agent-memory-session.md").exists())

    def test_create_demo_workspace_seeds_reviewed_memory_set(self):
        # The first recall a new user sees should show a believable memory
        # system: several memories, mostly reviewed, one pending to teach the
        # review loop.
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="link-demo-core-test-")))
        target = tmp / "demo"

        create_demo_workspace(target, source_root=ROOT)

        memory_files = sorted((target / "wiki/memories").glob("*.md"))
        self.assertEqual(len(memory_files), 4)
        statuses = []
        for path in memory_files:
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("review_status:"):
                    statuses.append(line.split(":", 1)[1].strip())
                    break
        self.assertEqual(statuses.count("reviewed"), 3)
        self.assertEqual(statuses.count("pending"), 1)

    def test_create_demo_workspace_refuses_non_demo_directory(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="link-demo-core-test-")))
        target = tmp / "not-demo"
        target.mkdir()
        keep = target / "keep.txt"
        keep.write_text("keep", encoding="utf-8")

        with self.assertRaises(DemoError) as ctx:
            create_demo_workspace(target, source_root=ROOT, force=True)

        self.assertIn("refusing to overwrite", str(ctx.exception))
        self.assertEqual(keep.read_text(encoding="utf-8"), "keep")

    def test_create_demo_workspace_force_replaces_marked_demo(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="link-demo-core-test-")))
        target = tmp / "demo"
        create_demo_workspace(target, source_root=ROOT)
        old = target / "old.txt"
        old.write_text("old", encoding="utf-8")

        create_demo_workspace(target, source_root=ROOT, force=True)

        self.assertFalse(old.exists())
        self.assertTrue((target / DEMO_MARKER).exists())
        self.assertTrue((target / "wiki/index.md").exists())


if __name__ == "__main__":
    unittest.main()
