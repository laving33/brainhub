from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import brainhub
from mcp_package.brainhub_core import validation, wiki_publish
from mcp_package.brainhub_core.frontmatter import parse_frontmatter


class PublishVerbTests(unittest.TestCase):
    def _init_workspace(self, root: Path) -> Path:
        workspace = root / "brainhub"
        self.assertEqual(brainhub.main(["init", str(workspace)]), 0)
        return workspace

    # 1. basic publish: file location, frontmatter, body shape -----------------
    def test_publish_creates_single_document_with_expected_frontmatter_and_body(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            code = brainhub.main([
                "publish",
                "Hello World",
                str(workspace),
                "--body",
                "This is the body of the page.",
                "--agent",
                "tester",
            ])
            self.assertEqual(code, 0)

            expected_slug = wiki_publish.slugify("Hello World")
            documents_dir = workspace / "wiki" / "documents"
            files = sorted(documents_dir.glob("*.md"))
            self.assertEqual(len(files), 1, f"expected exactly one document, found {files}")
            doc_path = documents_dir / f"{expected_slug}.md"
            self.assertEqual(files[0], doc_path)

            text = doc_path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            self.assertEqual(meta.get("type"), "document")
            self.assertEqual(meta.get("title"), "Hello World")
            self.assertEqual(meta.get("handle"), expected_slug)
            self.assertIn("date_published", meta)
            self.assertIn("date_updated", meta)
            self.assertEqual(meta.get("status"), "active")

            self.assertIn("# Hello World", body)
            self.assertIn("> **TLDR:**", body)
            self.assertIn("## Provenance", body)

    # 2. update-in-place: same title -> same file, date_published preserved ----
    def test_republish_same_title_updates_in_place_and_preserves_date_published(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            self.assertEqual(brainhub.main([
                "publish", "Release Notes", str(workspace), "--body", "First version of the notes.",
            ]), 0)

            documents_dir = workspace / "wiki" / "documents"
            slug = wiki_publish.slugify("Release Notes")
            first_text = (documents_dir / f"{slug}.md").read_text(encoding="utf-8")
            first_meta, first_body = parse_frontmatter(first_text)

            self.assertEqual(brainhub.main([
                "publish", "Release Notes", str(workspace), "--body", "Second, updated version of the notes.",
            ]), 0)

            files = sorted(documents_dir.glob("*.md"))
            self.assertEqual(len(files), 1, f"republish must not create a copy, found {files}")
            self.assertEqual(files[0].name, f"{slug}.md")

            second_text = files[0].read_text(encoding="utf-8")
            second_meta, second_body = parse_frontmatter(second_text)

            self.assertEqual(second_meta.get("date_published"), first_meta.get("date_published"))
            self.assertNotEqual(second_meta.get("date_updated"), first_meta.get("date_updated"))
            self.assertIn("Second, updated version of the notes.", second_body)
            self.assertNotIn("First version of the notes.", second_body)

    # 3a. --body-file works ------------------------------------------------------
    def test_publish_reads_body_from_body_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = self._init_workspace(root)
            body_file = root / "body.md"
            body_file.write_text("Body sourced from a file on disk.", encoding="utf-8")

            code = brainhub.main([
                "publish", "From File", str(workspace), "--body-file", str(body_file),
            ])
            self.assertEqual(code, 0)

            slug = wiki_publish.slugify("From File")
            text = (workspace / "wiki" / "documents" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn("Body sourced from a file on disk.", text)

    # 3b. stdin ('-' and omitted --body) both work -------------------------------
    def test_publish_reads_body_from_stdin_when_dash_or_omitted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            old_stdin = sys.stdin
            try:
                sys.stdin = io.StringIO("Body piped in via stdin with a dash flag.")
                code = brainhub.main(["publish", "Stdin Dash", str(workspace), "--body", "-"])
                self.assertEqual(code, 0)
            finally:
                sys.stdin = old_stdin

            slug = wiki_publish.slugify("Stdin Dash")
            text = (workspace / "wiki" / "documents" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn("Body piped in via stdin with a dash flag.", text)

            old_stdin = sys.stdin
            try:
                sys.stdin = io.StringIO("Body piped in via stdin with no --body flag at all.")
                code = brainhub.main(["publish", "Stdin Omitted", str(workspace)])
                self.assertEqual(code, 0)
            finally:
                sys.stdin = old_stdin

            slug2 = wiki_publish.slugify("Stdin Omitted")
            text2 = (workspace / "wiki" / "documents" / f"{slug2}.md").read_text(encoding="utf-8")
            self.assertIn("Body piped in via stdin with no --body flag at all.", text2)

    # 4. --link produces wikilinks and merges across republishes -----------------
    def test_publish_links_appear_as_wikilinks_and_merge_across_republish(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            self.assertEqual(brainhub.main([
                "publish", "Linker Page", str(workspace),
                "--body", "A page that links elsewhere.",
                "--link", "Target One",
            ]), 0)

            slug = wiki_publish.slugify("Linker Page")
            target_one_slug = wiki_publish.slugify("Target One")
            text = (workspace / "wiki" / "documents" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn(f"[[{target_one_slug}]]", text)

            # Republish WITHOUT re-specifying --link: the earlier link must survive.
            self.assertEqual(brainhub.main([
                "publish", "Linker Page", str(workspace),
                "--body", "A page that links elsewhere, updated.",
            ]), 0)
            text_after = (workspace / "wiki" / "documents" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn(f"[[{target_one_slug}]]", text_after)

            # Republish adding a SECOND link: both first and second must be present (merged).
            self.assertEqual(brainhub.main([
                "publish", "Linker Page", str(workspace),
                "--body", "A page that links elsewhere, updated again.",
                "--link", "Target Two",
            ]), 0)
            target_two_slug = wiki_publish.slugify("Target Two")
            text_merged = (workspace / "wiki" / "documents" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn(f"[[{target_one_slug}]]", text_merged)
            self.assertIn(f"[[{target_two_slug}]]", text_merged)

    # 5a. --artifact resolves to stored_path in frontmatter + Provenance ---------
    def test_publish_artifact_reference_resolves_to_stored_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = self._init_workspace(root)
            source = root / "report.md"
            source.write_text("# A report\n", encoding="utf-8")

            self.assertEqual(brainhub.main([
                "artifact", "add", str(source), str(workspace),
                "--kind", "report",
                "--task", "some-task",
                "--agent", "tester",
            ]), 0)

            code = brainhub.main([
                "publish", "Report Page", str(workspace),
                "--body", "This page references a built artifact.",
                "--artifact", "report.md",
            ])
            self.assertEqual(code, 0)

            slug = wiki_publish.slugify("Report Page")
            text = (workspace / "wiki" / "documents" / f"{slug}.md").read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            self.assertEqual(meta.get("related_artifact"), "artifacts/reports/report.md")
            self.assertIn("artifacts/reports/report.md", body)
            self.assertIn("resolved", body)

    # 5b. unknown --artifact still publishes, fail-open, marked unresolved -------
    def test_publish_unknown_artifact_reference_fails_open_and_is_marked_unresolved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            code = brainhub.main([
                "publish", "Dangling Reference Page", str(workspace),
                "--body", "This page references an artifact that was never built.",
                "--artifact", "never-built.md",
            ])
            self.assertEqual(code, 0)

            slug = wiki_publish.slugify("Dangling Reference Page")
            text = (workspace / "wiki" / "documents" / f"{slug}.md").read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            self.assertEqual(meta.get("related_artifact"), "never-built.md")
            self.assertIn("unresolved", body)

    # 6. empty/whitespace title raises ValueError ---------------------------------
    def test_publish_empty_or_whitespace_title_raises_value_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            # CLI reports empty titles loudly (nonzero exit + stderr message,
            # never a bare traceback).
            for bad_title in ("", "   "):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    code = brainhub.main(["publish", bad_title, str(workspace), "--body", "no title"])
                self.assertEqual(code, 1)
                self.assertTrue(stderr.getvalue().strip())

    # result reports body wikilinks, stored tags, and dead-link warnings ----------
    def test_publish_reports_body_wikilinks_stored_tags_and_dead_link_warnings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))
            wiki_publish.publish_document(workspace, "Existing Page", "Content.", agent="t")

            result = wiki_publish.publish_document(
                workspace,
                "Linker",
                "See [[existing-page]] and [[missing-page]].",
                agent="t",
                tags=["from:catalog"],
            )

            # Body [[wikilinks]] are reported — no bh-link round trips needed.
            self.assertIn("existing-page", result["links"])
            self.assertIn("missing-page", result["links"])
            # Stored tags echo back in dash form.
            self.assertEqual(result["tags"], ["document", "from-catalog"])
            # Dead targets warn but never fail the publish.
            self.assertTrue(result["published"])
            self.assertEqual(result["unresolved_links"], ["missing-page"])
            self.assertEqual(len(result["warnings"]), 1)
            self.assertIn("missing-page", result["warnings"][0])

    def test_publish_with_all_links_resolved_returns_no_warnings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))
            wiki_publish.publish_document(workspace, "Existing Page", "Content.", agent="t")

            result = wiki_publish.publish_document(
                workspace, "Clean Linker", "See [[existing-page]].", agent="t",
            )

            self.assertEqual(result["warnings"], [])
            self.assertEqual(result["unresolved_links"], [])
            self.assertIn("existing-page", result["links"])

    # TLDR extraction: leading blockquote bodies must not nest ---------------------
    def test_publish_tldr_strips_leading_blockquote_and_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            wiki_publish.publish_document(
                workspace,
                "Quoted Opener",
                "> **TLDR:** 一句話重點\n\n後面是內文。",
                agent="t",
            )

            markdown = wiki_publish.read_document(workspace, "quoted-opener")["markdown"]
            self.assertNotIn("> **TLDR:** >", markdown)
            self.assertIn("> **TLDR:** 一句話重點", markdown)

    # validate_wiki stays green after documents are published ---------------------
    def test_validate_wiki_passes_after_publishing_documents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            self.assertEqual(brainhub.main([
                "publish", "Another Page", str(workspace),
                "--body", "The link target, published first so the link below is not dead.",
            ]), 0)
            self.assertEqual(brainhub.main([
                "publish", "Validation Check Page", str(workspace),
                "--body", "Body content for validation.",
                "--link", "Another Page",
            ]), 0)

            result = validation.validate_wiki(workspace / "wiki")
            self.assertTrue(result["passed"], result)

    # end-to-end round trip via the CLI, capturing stdout -------------------------
    def test_cli_publish_then_read_round_trip_via_stdout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            publish_out = io.StringIO()
            with redirect_stdout(publish_out):
                code = brainhub.main([
                    "publish", "Round Trip Page", str(workspace),
                    "--body", "Body for the round trip check.",
                ])
            self.assertEqual(code, 0)
            self.assertIn("Published document", publish_out.getvalue())

            slug = wiki_publish.slugify("Round Trip Page")
            read_out = io.StringIO()
            with redirect_stdout(read_out):
                code = brainhub.main(["read", slug, str(workspace)])
            self.assertEqual(code, 0)
            self.assertIn("Body for the round trip check.", read_out.getvalue())

            # Republish and confirm the CLI reports an UPDATE, not a fresh publish.
            update_out = io.StringIO()
            with redirect_stdout(update_out):
                code = brainhub.main([
                    "publish", "Round Trip Page", str(workspace),
                    "--body", "Updated body for the round trip check.",
                ])
            self.assertEqual(code, 0)
            self.assertIn("Updated document", update_out.getvalue())

            documents_dir = workspace / "wiki" / "documents"
            self.assertEqual(len(list(documents_dir.glob("*.md"))), 1)


if __name__ == "__main__":
    unittest.main()
