"""Contract tests for the `link` verb (bh-link): brainhub.main(["link", ...])
and mcp_package.brainhub_core.wiki_publish.link_documents.

Only touches this file. Reuses the existing engine page store/search/backlinks
via wiki_publish (no parallel store introduced).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import brainhub
from mcp_package.brainhub_core import wiki_publish
from mcp_package.brainhub_core.frontmatter import parse_frontmatter
from mcp_package.brainhub_core.wiki import load_backlinks_index


class LinkVerbTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace = Path(self._tmp.name) / "brainhub"
        code = brainhub.main(["init", str(self.workspace)])
        self.assertEqual(code, 0)

        wiki_publish.publish_document(
            self.workspace,
            "A Title",
            "Body of document A.",
            agent="test-writer",
        )
        wiki_publish.publish_document(
            self.workspace,
            "B Title",
            "Body of document B.",
            agent="test-writer",
        )
        self.a_path = wiki_publish.document_path(
            wiki_publish.wiki_dir_for(self.workspace), "a-title"
        )
        self.b_path = wiki_publish.document_path(
            wiki_publish.wiki_dir_for(self.workspace), "b-title"
        )

    # -- (1) inserts wikilink under ## Links, preserves frontmatter, returns added=True ----
    def test_link_inserts_wikilink_under_links_section_and_preserves_frontmatter(self):
        before_text = self.a_path.read_text(encoding="utf-8")
        before_meta, _ = parse_frontmatter(before_text)

        result = wiki_publish.link_documents(self.workspace, "A Title", "B Title")

        self.assertTrue(result["added"])
        self.assertEqual(result["from_handle"], "a-title")
        self.assertEqual(result["to_handle"], "b-title")

        after_text = self.a_path.read_text(encoding="utf-8")
        after_meta, after_body = parse_frontmatter(after_text)

        self.assertIn("## Links", after_body)
        self.assertIn("[[b-title]]", after_body)
        # the wikilink line lives under the ## Links heading
        links_idx = after_body.index("## Links")
        link_idx = after_body.index("[[b-title]]")
        self.assertGreater(link_idx, links_idx)

        # frontmatter fields preserved exactly (type/title/handle/date_published)
        self.assertEqual(after_meta.get("type"), before_meta.get("type"))
        self.assertEqual(after_meta.get("title"), before_meta.get("title"))
        self.assertEqual(after_meta.get("handle"), before_meta.get("handle"))
        self.assertEqual(after_meta.get("date_published"), before_meta.get("date_published"))

    def test_link_creates_links_section_when_absent(self):
        # A Title was published with no links, so it has no ## Links section yet.
        _, body_before = parse_frontmatter(self.a_path.read_text(encoding="utf-8"))
        self.assertNotIn("## Links", body_before)

        wiki_publish.link_documents(self.workspace, "A Title", "B Title")

        _, body_after = parse_frontmatter(self.a_path.read_text(encoding="utf-8"))
        self.assertIn("## Links", body_after)
        self.assertIn("- [[b-title]]", body_after)

    # -- (2) backlinks rebuild: A appears among B's inbound backlinks ----------------------
    def test_link_rebuilds_backlinks_index(self):
        wiki_publish.link_documents(self.workspace, "A Title", "B Title")

        wiki_dir = wiki_publish.wiki_dir_for(self.workspace)
        backlinks, error = load_backlinks_index(wiki_dir / "_backlinks.json")
        self.assertIsNone(error)
        inbound = backlinks["backlinks"].get("b-title", [])
        self.assertIn("a-title", inbound)

    # -- (3) idempotent: second call returns added=False/already_linked=True, no dup ------
    def test_link_is_idempotent(self):
        first = wiki_publish.link_documents(self.workspace, "A Title", "B Title")
        self.assertTrue(first["added"])
        self.assertFalse(first["already_linked"])

        second = wiki_publish.link_documents(self.workspace, "A Title", "B Title")
        self.assertFalse(second["added"])
        self.assertTrue(second["already_linked"])

        _, body = parse_frontmatter(self.a_path.read_text(encoding="utf-8"))
        self.assertEqual(body.count("[[b-title]]"), 1)

    # -- (4) linking to a non-existent target raises ValueError (fail-closed) -------------
    def test_link_to_nonexistent_target_raises(self):
        with self.assertRaises(ValueError) as ctx:
            wiki_publish.link_documents(self.workspace, "A Title", "Ghost Page")
        self.assertIn("not found", str(ctx.exception).lower())

    # -- (5) linking a document to itself raises ValueError --------------------------------
    def test_link_to_self_raises(self):
        with self.assertRaises(ValueError):
            wiki_publish.link_documents(self.workspace, "A Title", "A Title")

    # -- (6) source must be an existing document page; memory/source pages never mutated --
    def test_link_from_nonexistent_source_raises(self):
        with self.assertRaises(ValueError) as ctx:
            wiki_publish.link_documents(self.workspace, "Nonexistent Source", "B Title")
        self.assertIn("source document not found", str(ctx.exception).lower())

    # -- (7) handles are forgiving: titles or slugs both resolve ---------------------------
    def test_link_accepts_titles_or_slugs(self):
        result = wiki_publish.link_documents(self.workspace, "a-title", "b-title")
        self.assertTrue(result["added"])
        self.assertEqual(result["from_handle"], "a-title")
        self.assertEqual(result["to_handle"], "b-title")

    # -- (8) CLI: text confirmation + --json emits added/from_handle/to_handle ------------
    def test_cli_link_text_confirmation(self):
        out = StringIO()
        with redirect_stdout(out):
            code = brainhub.main(["link", "A Title", "B Title", str(self.workspace)])
        self.assertEqual(code, 0)
        printed = out.getvalue()
        self.assertIn("a-title", printed)
        self.assertIn("b-title", printed)

    def test_cli_link_json_output(self):
        out = StringIO()
        with redirect_stdout(out):
            code = brainhub.main(
                ["link", "A Title", "B Title", str(self.workspace), "--json"]
            )
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertIn("added", payload)
        self.assertEqual(payload["from_handle"], "a-title")
        self.assertEqual(payload["to_handle"], "b-title")


if __name__ == "__main__":
    unittest.main()
