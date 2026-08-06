import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.prompts import starter_prompt_payload, welcome_payload  # noqa: E402


class PromptsCoreTests(unittest.TestCase):
    def make_wiki(self, parent: Path) -> Path:
        wiki = parent / "wiki"
        wiki.mkdir(parents=True, exist_ok=True)
        (wiki / "index.md").write_text("# Index\n", encoding="utf-8")
        return wiki

    def test_global_wiki_gets_personal_memory_prompts(self):
        root = Path(tempfile.mkdtemp(prefix="link-prompts-core-"))
        wiki = self.make_wiki(root)

        payload = starter_prompt_payload(wiki)
        prompts = [str(item["prompt"]) for item in payload["prompts"]]

        self.assertEqual(payload["project"], "")
        self.assertIn("記住我偏好本地優先的 agent 記憶", prompts)
        self.assertIn("BrainHub 對我了解多少？", prompts)
        self.assertIn("把這個專案灌進 BrainHub", prompts)
        self.assertIn("從 raw/<檔案> 提出記憶建議", prompts)
        self.assertTrue(str(payload["shortcut"]).startswith("bh next "))
        self.assertTrue(any(command.startswith("bh seed . ") for command in payload["commands"]))
        self.assertTrue(any(command.startswith("bh health ") for command in payload["commands"]))
        self.assertTrue(any(str(root.resolve()) in command for command in payload["commands"]))

    def test_git_project_gets_project_memory_prompts(self):
        root = Path(tempfile.mkdtemp(prefix="link-prompts-core-"))
        project = root / "Client Launch"
        (project / ".git").mkdir(parents=True)
        wiki = self.make_wiki(project)

        payload = starter_prompt_payload(wiki)
        prompts = [str(item["prompt"]) for item in payload["prompts"]]

        self.assertEqual(payload["project"], "client-launch")
        self.assertIn("記住這個專案用 BrainHub 做內部 wiki 與 agent 記憶", prompts)
        self.assertIn("BrainHub 記得這個專案的什麼？", prompts)

    def test_explicit_project_is_normalized(self):
        root = Path(tempfile.mkdtemp(prefix="link-prompts-core-"))
        wiki = self.make_wiki(root)

        payload = starter_prompt_payload(wiki, project="Client Launch")

        self.assertEqual(payload["project"], "client-launch")

    def test_welcome_payload_returns_short_proof_path(self):
        root = Path(tempfile.mkdtemp(prefix="link-prompts-core-"))
        wiki = self.make_wiki(root)

        payload = welcome_payload(wiki, project="Client Launch")

        self.assertEqual(payload["project"], "client-launch")
        self.assertEqual(len(payload["steps"]), 3)
        self.assertEqual(payload["steps"][0]["prompt"], "BrainHub 準備好了嗎？")
        self.assertIn("Agent 能找到 BrainHub", payload["steps"][0]["proves"])
        self.assertTrue(any(command.startswith("bh serve ") for command in payload["commands"]))
        self.assertTrue(any(str(root.resolve()) in command for command in payload["commands"]))
        self.assertIn("http://127.0.0.1:3000/onboard", payload["urls"])
        self.assertIn("http://127.0.0.1:3000/health", payload["urls"])


if __name__ == "__main__":
    unittest.main()
