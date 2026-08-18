"""The Agent Skills authoring rules, checked against the skills we ship.

Sources are Anthropic's published Skill specification and authoring guide. The
frontmatter limits are stated as requirements; the rest are the guide's
recommendations, kept here because they are cheap to violate in an edit and
invisible until a skill silently fails to trigger.

The format is an open standard adopted beyond Claude Code (Codex CLI, Cursor,
Gemini CLI, Copilot), so these constraints are not one vendor's preference.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(ROOT.glob("skills/*/SKILL.md"))

# Specification limits.
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 1024
RESERVED_WORDS = ("anthropic", "claude")
# Authoring guide: keep the body under 500 lines, split into references beyond.
MAX_BODY_LINES = 500

# The MCP server key these skills tell an agent to call. Unqualified tool names
# may not resolve when several servers are connected.
MCP_SERVER_PREFIX = "46m-bh:"
MCP_TOOL_NAMES = (
    "admin", "recall", "remember", "review", "ingest", "status",
    "bh_build", "bh_publish", "bh_read", "bh_search", "bh_link", "bh_export",
    "list_artifacts",
)


def frontmatter(text: str) -> dict:
    block = text.split("---", 2)[1]
    fields = {}
    for match in re.finditer(r"^(\w[\w-]*):\s*(.*)$", block, re.M):
        fields[match.group(1)] = match.group(2).strip()
    return fields


def body(text: str) -> str:
    return text.split("---", 2)[2]


class SkillsExistTests(unittest.TestCase):
    def test_skills_are_present(self):
        self.assertTrue(SKILLS, "no skills/*/SKILL.md found")


class FrontmatterRequirementTests(unittest.TestCase):
    """Specification requirements — a violation is invalid, not merely unwise."""

    def test_name_and_description_are_present(self):
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                fields = frontmatter(path.read_text(encoding="utf-8"))
                self.assertIn("name", fields)
                self.assertTrue(fields.get("description"))

    def test_name_is_within_limits_and_lowercase_kebab(self):
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                name = frontmatter(path.read_text(encoding="utf-8"))["name"]
                self.assertLessEqual(len(name), MAX_NAME_CHARS)
                self.assertRegex(name, r"^[a-z0-9-]+$")

    def test_name_avoids_reserved_words(self):
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                name = frontmatter(path.read_text(encoding="utf-8"))["name"].lower()
                for word in RESERVED_WORDS:
                    self.assertNotIn(word, name)

    def test_name_matches_its_directory(self):
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                name = frontmatter(path.read_text(encoding="utf-8"))["name"]
                self.assertEqual(name, path.parent.name)

    def test_description_is_within_limit(self):
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                description = frontmatter(path.read_text(encoding="utf-8"))["description"]
                self.assertLessEqual(len(description), MAX_DESCRIPTION_CHARS)

    def test_no_xml_tags_in_frontmatter(self):
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                fields = frontmatter(path.read_text(encoding="utf-8"))
                for key in ("name", "description"):
                    self.assertNotRegex(fields.get(key, ""), r"<[^>]+>")


class DescriptionQualityTests(unittest.TestCase):
    """The description is how a skill gets selected out of a hundred."""

    def test_description_states_the_capability_before_the_trigger(self):
        # The guide asks for BOTH what the skill does and when to use it. Ours
        # all opened with "Use when …", so the capability itself was never
        # stated — the half a model matches a task against was missing.
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                description = frontmatter(path.read_text(encoding="utf-8"))["description"]
                self.assertFalse(
                    description.startswith("Use "),
                    "description opens with the trigger; state what it does first",
                )

    def test_description_says_when_to_use_it(self):
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                description = frontmatter(path.read_text(encoding="utf-8"))["description"]
                self.assertIn("Use ", description, "description states no trigger")

    def test_description_is_third_person_not_addressed_to_the_reader(self):
        # It is injected into the system prompt; first/second person there
        # causes discovery problems.
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                description = frontmatter(path.read_text(encoding="utf-8"))["description"]
                for opener in ("I can ", "I will ", "You can ", "You should "):
                    self.assertNotIn(opener, description)


class BodyTests(unittest.TestCase):
    def test_body_is_under_the_line_budget(self):
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                lines = len(body(path.read_text(encoding="utf-8")).strip().split("\n"))
                self.assertLessEqual(
                    lines, MAX_BODY_LINES,
                    "split into reference files rather than growing SKILL.md",
                )

    def test_mcp_tools_are_named_with_their_server_prefix(self):
        # An unqualified tool name may fail to resolve with several MCP servers
        # connected, and the failure looks like a missing tool rather than a
        # naming problem.
        pattern = re.compile(r"(?<![\w:.-])(" + "|".join(MCP_TOOL_NAMES) + r")\(")
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                text = body(path.read_text(encoding="utf-8"))
                for match in pattern.finditer(text):
                    start = max(0, match.start() - len(MCP_SERVER_PREFIX))
                    self.assertEqual(
                        text[start:match.start()], MCP_SERVER_PREFIX,
                        f"{match.group(1)}() is not qualified with {MCP_SERVER_PREFIX}",
                    )

    def test_paths_use_forward_slashes(self):
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                self.assertNotRegex(body(path.read_text(encoding="utf-8")), r"\w+\\\w+\.(md|py|sh)")

    def test_no_time_sensitive_content(self):
        # "before August 2025, use the old API" goes wrong on its own.
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                self.assertNotRegex(
                    body(path.read_text(encoding="utf-8")),
                    r"\b(20\d\d-\d\d-\d\d|as of 20\d\d|before 20\d\d|after 20\d\d)\b",
                )

    def test_referenced_files_exist(self):
        # Progressive disclosure only works if the pointer resolves.
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                for target in re.findall(r"\[[^\]]+\]\((?!https?:)([^)#]+)\)",
                                         body(path.read_text(encoding="utf-8"))):
                    self.assertTrue(
                        (path.parent / target).exists(),
                        f"{path.parent.name} references missing {target}",
                    )


if __name__ == "__main__":
    unittest.main()
