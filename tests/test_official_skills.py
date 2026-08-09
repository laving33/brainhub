import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

EXPECTED_SKILLS = {
    "46m-bh-health": ("bh health", "bh operations", "bh backup", "bh validate"),
    "46m-bh-retrieve": ("bh query", "bh brief", "bh graph-summary", "bh benchmark"),
    "46m-bh-ingest": ("bh ingest-status", "bh propose-memories", "bh rebuild-index", "bh validate"),
    "46m-bh-memory": ("bh brief", "bh recall", "bh session-end", "bh remember", "bh memory-inbox"),
    "46m-bh-runtime": (
        "python3 brainhub.py init",
        "python3 brainhub.py artifact add",
        "python3 brainhub.py artifact capture",
        "python3 brainhub.py artifact list",
    ),
}


def read_skill(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    _, frontmatter, _body = text.split("---", 2)
    parsed: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


class OfficialSkillsTests(unittest.TestCase):
    def test_expected_skills_exist_with_valid_frontmatter(self):
        for name in EXPECTED_SKILLS:
            with self.subTest(skill=name):
                path = SKILLS_DIR / name / "SKILL.md"
                self.assertTrue(path.exists(), f"missing official skill: {path}")

                frontmatter = parse_frontmatter(read_skill(name))
                self.assertEqual(frontmatter.get("name"), name)
                self.assertGreaterEqual(len(frontmatter.get("description", "")), 60)

    def test_skills_are_cli_backed_and_lazy_loadable(self):
        forbidden_claims = (
            "mcp is required",
            "requires mcp",
            "start the mcp server",
            "must run `bh serve`",
            "must run bh serve",
        )
        for name, commands in EXPECTED_SKILLS.items():
            with self.subTest(skill=name):
                text = read_skill(name)
                lower = text.lower()
                if name == "46m-bh-runtime":
                    self.assertIn("brainhub.py", text)
                    self.assertIn("[workspace]", text)
                else:
                    self.assertIn("bh", text)
                    self.assertIn("[link-root]", text)
                self.assertIn("MCP", text)
                for command in commands:
                    self.assertIn(command, text)
                for forbidden in forbidden_claims:
                    self.assertNotIn(forbidden, lower)

    def test_skills_have_ambient_agent_triggers(self):
        expectations = {
            "46m-bh-health": ("start", "readiness", "installs"),
            "46m-bh-retrieve": ("before answering", "first substantive turn", "prior BrainHub memory"),
            "46m-bh-ingest": ("raw files", "drops files", "learn next"),
            "46m-bh-memory": ("important user-approved decisions", "propose first", "durable memory"),
            "46m-bh-runtime": ("runtime node", "workflow artifact", "source-backed"),
        }
        passive_only_phrases = (
            "use when a user asks",
            "use when a user wants",
            "use when users ask",
        )
        for name, required in expectations.items():
            with self.subTest(skill=name):
                text = read_skill(name)
                lower = text.lower()
                for phrase in passive_only_phrases:
                    self.assertNotIn(phrase, lower)
                for phrase in required:
                    self.assertIn(phrase.lower(), lower)

