"""Contract tests for the `read` verb (bh-read): brainhub.main(["read", ...]) and
wiki_publish.read_document.

Only this file is edited for this verb; the engine (mcp_package/brainhub_core/wiki_publish.py)
and CLI wiring (brainhub.py) are shared code owned by the architect / other writers.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import brainhub
from mcp_package.brainhub_core import wiki_publish


class BhReadTests(unittest.TestCase):
    def _init_workspace(self, root: Path) -> Path:
        workspace = root / "brainhub"
        self.assertEqual(brainhub.main(["init", str(workspace)]), 0)
        return workspace

    def _publish(self, workspace: Path, title: str, body: str, *, extra: list[str] | None = None) -> None:
        code = brainhub.main(["publish", title, str(workspace), "--body", body, *(extra or [])])
        self.assertEqual(code, 0)

    # ------------------------------------------------------------------
    # (1) read_document returns the full contract dict, markdown/body correct
    # ------------------------------------------------------------------
    def test_read_document_returns_full_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))
            self._publish(workspace, "Release Plan", "Ship it on Friday.", extra=["--agent", "tester"])

            result = wiki_publish.read_document(workspace, "release-plan")

            self.assertEqual(
                set(result.keys()),
                {"handle", "sid", "title", "path", "markdown", "body", "metadata", "related_artifact", "links"},
            )

            on_disk = (workspace / "wiki" / "documents" / "release-plan.md").read_text(encoding="utf-8")
            self.assertEqual(result["markdown"], on_disk)
            self.assertEqual(result["handle"], "release-plan")
            self.assertEqual(result["title"], "Release Plan")
            self.assertEqual(result["path"], "wiki/documents/release-plan.md")

            # body has frontmatter stripped: no leading '---' block, no frontmatter keys.
            self.assertFalse(result["body"].startswith("---"))
            self.assertNotIn("type: document", result["body"])
            self.assertIn("Ship it on Friday.", result["body"])
            self.assertIn("# Release Plan", result["markdown"])

            self.assertIsInstance(result["metadata"], dict)
            self.assertEqual(result["metadata"].get("title"), "Release Plan")
            self.assertEqual(result["metadata"].get("handle"), "release-plan")
            self.assertEqual(result["links"], [])
            self.assertIsNone(result["related_artifact"])

    # ------------------------------------------------------------------
    # (2) forgiving handle resolution: slug / title / <slug>.md / documents/<slug>
    # ------------------------------------------------------------------
    def test_handle_resolution_is_forgiving(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))
            self._publish(workspace, "Release Plan", "Ship it on Friday.")

            baseline = wiki_publish.read_document(workspace, "release-plan")
            for handle in ("release-plan", "Release Plan", "release-plan.md", "documents/release-plan"):
                result = wiki_publish.read_document(workspace, handle)
                self.assertEqual(
                    result["handle"], "release-plan", f"handle resolution failed for {handle!r}"
                )
                self.assertEqual(result["markdown"], baseline["markdown"])
                # every variant normalizes through the same helper the module exposes
                self.assertEqual(wiki_publish.normalize_handle(handle), "release-plan")

    # ------------------------------------------------------------------
    # (3) CLI prints markdown by default, and a JSON object with --json
    # ------------------------------------------------------------------
    def test_cli_read_prints_markdown_then_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))
            self._publish(workspace, "Release Plan", "Ship it on Friday.")

            out = io.StringIO()
            with redirect_stdout(out):
                code = brainhub.main(["read", "release-plan", str(workspace)])
            self.assertEqual(code, 0)
            self.assertIn("# Release Plan", out.getvalue())

            out_json = io.StringIO()
            with redirect_stdout(out_json):
                code = brainhub.main(["read", "release-plan", str(workspace), "--json"])
            self.assertEqual(code, 0)
            payload = json.loads(out_json.getvalue())
            self.assertEqual(payload["title"], "Release Plan")
            self.assertEqual(payload["handle"], "release-plan")

    # ------------------------------------------------------------------
    # (4) missing handle raises ValueError containing 'document not found'
    # ------------------------------------------------------------------
    def test_missing_handle_raises_value_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))

            with self.assertRaises(ValueError) as ctx:
                wiki_publish.read_document(workspace, "does-not-exist")
            self.assertIn("document not found", str(ctx.exception))

            # CLI reports the same error loudly (nonzero exit + stderr message,
            # never a bare traceback).
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = brainhub.main(["read", "does-not-exist", str(workspace)])
            self.assertEqual(code, 1)
            self.assertIn("document not found", stderr.getvalue())

    # ------------------------------------------------------------------
    # body_only: skip the markdown/metadata duplication on large pages
    # ------------------------------------------------------------------
    def test_body_only_omits_markdown_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._init_workspace(Path(temp_dir))
            self._publish(workspace, "Big Page", "A very distinctive xylographic body.")

            result = wiki_publish.read_document(workspace, "big-page", body_only=True)

            self.assertTrue(result["body_only"])
            self.assertNotIn("markdown", result)
            self.assertNotIn("metadata", result)
            self.assertIn("xylographic", result["body"])
            self.assertEqual(result["handle"], "big-page")

            # default behavior unchanged: markdown + metadata still returned
            full = wiki_publish.read_document(workspace, "big-page")
            self.assertIn("markdown", full)
            self.assertIn("metadata", full)

            # CLI flag prints the body without frontmatter
            output = io.StringIO()
            with redirect_stdout(output):
                code = brainhub.main(["read", "big-page", str(workspace), "--body-only"])
            self.assertEqual(code, 0)
            text = output.getvalue()
            self.assertIn("xylographic", text)
            self.assertNotIn("type: document", text)

    # ------------------------------------------------------------------
    # (5) related_artifact + forward links round-trip through publish --link/--artifact
    # ------------------------------------------------------------------
    def test_related_artifact_and_links_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = self._init_workspace(root)

            self._publish(workspace, "Root Doc", "The root page other docs link to.")

            source = root / "release-report.md"
            source.write_text("# Release report\n", encoding="utf-8")
            code = brainhub.main(
                [
                    "artifact",
                    "add",
                    str(source),
                    str(workspace),
                    "--kind",
                    "report",
                    "--task",
                    "release-readiness",
                    "--agent",
                    "tester",
                ]
            )
            self.assertEqual(code, 0)

            self._publish(
                workspace,
                "Release Plan",
                "Ship it on Friday.",
                extra=[
                    "--link",
                    "root-doc",
                    "--artifact",
                    "artifacts/reports/release-report.md",
                ],
            )

            result = wiki_publish.read_document(workspace, "release-plan")
            self.assertIn("root-doc", result["links"])
            self.assertEqual(result["related_artifact"], "artifacts/reports/release-report.md")
            self.assertEqual(result["metadata"].get("related_artifact"), "artifacts/reports/release-report.md")


if __name__ == "__main__":
    unittest.main()


class AuthoredBodyRoundTripTests(unittest.TestCase):
    """`read --body-only` must return what a human wrote, not the rendered page.

    Round-tripping the rendered page through publish is what stacked a second
    generated head and tail onto 47 pages (38 heads, 19 tails, worst at ten
    layers) before 2026-07-22.
    """

    def test_strips_generated_head_and_tail(self):
        body = (
            "# T\n\n> **TLDR:** excerpt\n\n"
            "real content\n\n"
            "## Links\n\n- [[other]]\n\n"
            "## Provenance\n\n- Published via bh-publish by `x`.\n"
        )
        self.assertEqual(wiki_publish.authored_body("T", body), "real content")

    def test_stacked_pages_shed_one_layer_per_round_trip(self):
        # Deliberately not healed in one pass: a later pair's TLDR slot is where
        # an author's own summary ends up, and nothing positional can tell them
        # apart. One layer per trip, and no sentence is ever deleted.
        body = "# T\n\n> **TLDR:** a\n\n# T\n\n> **TLDR:** b\n\nkept\n"
        once = wiki_publish.authored_body("T", body)
        self.assertEqual(once, "# T\n\n> **TLDR:** b\n\nkept")
        self.assertEqual(wiki_publish.authored_body("T", once), "kept")

    def test_keeps_body_that_merely_mentions_a_heading(self):
        body = "# T\n\n> **TLDR:** x\n\nintro\n\n## Links\n\nthis is the author's own section\n"
        # Real prose under ## Links must survive: eating an author's text is far
        # worse than leaving one duplicate block behind.
        self.assertIn("this is the author's own section", wiki_publish.authored_body("T", body))

    def test_leaves_a_body_without_generated_wrapping_alone(self):
        self.assertEqual(wiki_publish.authored_body("T", "plain body\n"), "plain body")

    def test_does_not_eat_a_heading_that_is_not_the_title(self):
        body = "# Something Else\n\ncontent\n"
        self.assertEqual(wiki_publish.authored_body("T", body), "# Something Else\n\ncontent")

    def test_round_trip_through_publish_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            brainhub.main(["init", str(workspace)])
            for _ in range(3):
                result = wiki_publish.read_document(workspace, "round-trip", body_only=True) \
                    if (workspace / "wiki/documents/round-trip.md").exists() else None
                body = result["body"] if result else "the body"
                wiki_publish.publish_document(
                    workspace, title="round trip", body_markdown=body,
                    links=[], tags=["document"], agent="test",
                )
            text = (workspace / "wiki/documents/round-trip.md").read_text(encoding="utf-8")
            self.assertEqual(text.count("> **TLDR:**"), 1)
            self.assertEqual(text.count("\n## Provenance"), 1)


class AuthorTldrSurvivesTests(unittest.TestCase):
    """An author's own TLDR line must survive read --body-only.

    cospec, 2026-07-22: the first version of the stripper removed TLDR lines by
    position, so a body whose first line was the author's own `> **TLDR:** …`
    lost it on every round trip — and the engine then regenerated a summary from
    the next heading, degrading it silently. The engine only ever emits a TLDR as
    part of a "# <title>" pair, so only pairs may be stripped.
    """

    def test_author_tldr_directly_under_the_generated_one_survives(self):
        body = (
            "# T\n\n> **TLDR:** generated excerpt\n\n"
            "> **TLDR:** the author's own summary line\n\n"
            "## 1. section\n"
        )
        result = wiki_publish.authored_body("T", body)
        self.assertTrue(result.startswith("> **TLDR:** the author's own summary line"), result[:80])

    def test_lone_tldr_without_a_heading_is_never_stripped(self):
        body = "> **TLDR:** author line\n\ncontent\n"
        self.assertEqual(wiki_publish.authored_body("T", body), body.strip())

    def test_heading_pair_under_a_different_title_is_left_alone(self):
        # Renamed page: stale generated heads stay rather than risk eating text.
        body = "# Old Name\n\n> **TLDR:** x\n\nkept\n"
        self.assertIn("# Old Name", wiki_publish.authored_body("T", body))

    def test_a_stacked_pair_is_never_eaten_in_one_pass(self):
        # The second TLDR here may be an author sentence promoted by an earlier
        # stacking; it must survive this pass.
        body = "# T\n\n> **TLDR:** a\n\n# T\n\n> **TLDR:** author sentence\n\nkept\n"
        self.assertIn("author sentence", wiki_publish.authored_body("T", body))
