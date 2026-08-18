"""Tests for scripts/check_docs_sync.py.

The real-tree assertion is the gate; the synthetic tree proves the checker can
actually fail, because a docs checker that silently passes is worse than none —
it converts "nobody verified this" into "something verified this".
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_package.brainhub_core import render
from mcp_package.brainhub_core.render.renderers.mermaid import VERIFIED_DIAGRAM_TYPES

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "check_docs_sync", ROOT / "scripts" / "check_docs_sync.py"
)
check_docs_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_docs_sync)


def _write_tree(root: Path, kinds, diagrams) -> None:
    """Lay down a minimal tree that names every fact the checker looks for."""
    kind_list = ", ".join(f"`{k}`" for k in kinds)
    diagram_list = ", ".join(diagrams)
    (root / "mcp_package" / "brainhub_mcp").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "46m-bh-runtime").mkdir(parents=True, exist_ok=True)

    (root / "README.md").write_text(
        f"{len(kinds)} renderers: {kind_list}\n\nmermaid: {diagram_list}\n",
        encoding="utf-8",
    )
    (root / "mcp_package" / "README.md").write_text(
        f"renderers: {kind_list}\n", encoding="utf-8"
    )
    # The skill also carries the spec table, so it must name every field of
    # every registered example.
    fields = sorted(
        {field for k in kinds for field in render.registry.get(k).example}
    )
    (root / "skills" / "46m-bh-runtime" / "SKILL.md").write_text(
        f"renderers: {kind_list}\n\nmermaid: {diagram_list}\n\n"
        f"spec fields: {', '.join(fields)}\n",
        encoding="utf-8",
    )
    (root / "mcp_package" / "brainhub_mcp" / "server.py").write_text(
        f'def bh_build(renderer, spec):\n    """Render a spec.\n\n'
        f'    renderer is one of: {", ".join(kinds)}.\n    """\n',
        encoding="utf-8",
    )


class SyntheticTreeTests(unittest.TestCase):
    """Drive the checker over a tree we control, so failure is observable."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.kinds = sorted(render.registry.kinds())
        _write_tree(self.root, self.kinds, VERIFIED_DIAGRAM_TYPES)

    def _check(self):
        with patch.object(check_docs_sync, "ROOT", self.root):
            return check_docs_sync.check()

    def test_complete_tree_is_clean(self):
        self.assertEqual(self._check(), [])

    def test_renderer_missing_from_a_surface_is_caught(self):
        path = self.root / "README.md"
        dropped = self.kinds[0]
        path.write_text(
            path.read_text(encoding="utf-8").replace(f"`{dropped}`, ", "", 1),
            encoding="utf-8",
        )
        findings = self._check()
        self.assertTrue(
            any(dropped in f and "README.md" in f for f in findings), findings
        )

    def test_renderer_missing_from_the_tool_docstring_is_caught(self):
        path = self.root / "mcp_package" / "brainhub_mcp" / "server.py"
        dropped = self.kinds[0]
        path.write_text(
            path.read_text(encoding="utf-8").replace(f"{dropped}, ", "", 1),
            encoding="utf-8",
        )
        findings = self._check()
        self.assertTrue(
            any("bh_build docstring" in f and dropped in f for f in findings), findings
        )

    def test_missing_mermaid_type_is_caught(self):
        path = self.root / "skills" / "46m-bh-runtime" / "SKILL.md"
        dropped = VERIFIED_DIAGRAM_TYPES[0]
        path.write_text(
            path.read_text(encoding="utf-8").replace(f"{dropped}, ", "", 1),
            encoding="utf-8",
        )
        findings = self._check()
        self.assertTrue(any(dropped in f for f in findings), findings)

    def test_wrong_renderer_count_in_prose_is_caught(self):
        path = self.root / "README.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                f"{len(self.kinds)} renderers", "99 renderers", 1
            ),
            encoding="utf-8",
        )
        findings = self._check()
        self.assertTrue(any("claims 99 renderers" in f for f in findings), findings)

    def test_stale_exemption_is_caught(self):
        with patch.object(check_docs_sync, "ROOT", self.root), patch.object(
            check_docs_sync,
            "RENDERER_OMISSIONS",
            {Path("README.md"): {"no-such-kind": "gone"}},
        ):
            findings = check_docs_sync.check()
        self.assertTrue(any("stale" in f for f in findings), findings)

    def test_a_kind_is_not_matched_inside_a_longer_kind(self):
        # "bar" must not be satisfied by "stacked-bar" or "bar-chart"; that is
        # what would let a genuinely missing renderer look present.
        self.assertFalse(check_docs_sync._names("stacked-bar and bar-chart", "bar"))
        self.assertTrue(check_docs_sync._names("`bar`, `line`", "bar"))


class RealTreeTests(unittest.TestCase):
    def test_repository_docs_are_in_sync(self):
        findings = check_docs_sync.check()
        self.assertEqual(findings, [], "\n".join(findings))


if __name__ == "__main__":
    unittest.main()
