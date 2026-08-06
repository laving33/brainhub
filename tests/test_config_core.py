import tempfile
import unittest
from pathlib import Path

from mcp_package.brainhub_core.config import (
    CONFIG_FILE,
    config_path,
    load_workspace_config,
    memory_disabled_notice,
    memory_layer_enabled,
)


class ConfigCoreTests(unittest.TestCase):
    def test_config_path_sits_at_workspace_root_outside_wiki(self):
        workspace = Path("/tmp/example-workspace")

        path = config_path(workspace)

        self.assertEqual(path, workspace / CONFIG_FILE)
        self.assertNotIn("wiki", path.parts)

    def test_missing_config_reads_as_memory_enabled(self):
        workspace = Path(tempfile.mkdtemp(prefix="link-config-core-"))

        self.assertEqual(load_workspace_config(workspace), {})
        self.assertTrue(memory_layer_enabled(workspace))

    def test_invalid_config_reads_as_memory_enabled(self):
        workspace = Path(tempfile.mkdtemp(prefix="link-config-core-"))
        config_path(workspace).write_text("not json", encoding="utf-8")

        self.assertEqual(load_workspace_config(workspace), {})
        self.assertTrue(memory_layer_enabled(workspace))

    def test_memory_enabled_false_disables_the_memory_layer(self):
        workspace = Path(tempfile.mkdtemp(prefix="link-config-core-"))
        config_path(workspace).write_text('{"memory_enabled": false}\n', encoding="utf-8")

        self.assertFalse(memory_layer_enabled(workspace))

    def test_disabled_notice_names_the_config_file(self):
        workspace = Path(tempfile.mkdtemp(prefix="link-config-core-"))

        notice = memory_disabled_notice(workspace)

        self.assertIn(str(config_path(workspace)), notice)
        self.assertIn('"memory_enabled": true', notice)


if __name__ == "__main__":
    unittest.main()
