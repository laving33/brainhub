import json
import tempfile
import unittest
from pathlib import Path

from mcp_package.brainhub_core.artifacts import (
    artifact_catalog,
    artifact_store_problem,
    ensure_standalone_html,
    is_standalone_html,
)


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


class ArtifactStoreProblemTests(unittest.TestCase):
    """The message has to name the right fix, because the two causes differ.

    A wiki-only workspace (what ``brainhub_engine.py demo`` produces) is
    initialized — it just has no artifact store. Telling its owner the workspace
    "is not initialized" sends them to re-initialize something already fine.
    """

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="brainhub-store-problem-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))

    def test_no_problem_when_the_artifact_directory_exists(self):
        (self.root / "artifacts/html").mkdir(parents=True)
        self.assertIsNone(artifact_store_problem(self.root, "html"))

    def test_wiki_only_workspace_is_named_as_such(self):
        (self.root / "wiki").mkdir(parents=True)
        problem = artifact_store_problem(self.root, "html")
        self.assertIn("wiki-only workspace", problem)
        self.assertIn("artifacts/html", problem)
        self.assertIn("bh init", problem)
        self.assertNotIn("not initialized", problem)

    def test_missing_path_reads_as_a_path_problem(self):
        problem = artifact_store_problem(self.root / "typo", "html")
        self.assertIn("no BrainHub workspace", problem)
        self.assertIn("check the path", problem)

    def test_unrelated_directory_is_not_called_a_workspace(self):
        problem = artifact_store_problem(self.root, "html")
        self.assertIn("is not a BrainHub workspace", problem)

    def test_unknown_kind_lists_the_valid_ones(self):
        problem = artifact_store_problem(self.root, "sculpture")
        self.assertIn("unknown artifact kind", problem)
        self.assertIn("html", problem)


class StandaloneHtmlTests(unittest.TestCase):
    """A stored artifact is opened straight from disk, so it must be a whole document.

    Agent-authored pages often arrive as fragments because the rendering surface
    supplied the shell. Without a doctype the browser drops into quirks mode, and a
    ``<title>`` left in the body is discarded — the page loses its name in the tab
    and in the viewer's listing.
    """

    FRAGMENT = (
        "<title>My Page</title>\n"
        "<style>body { color: red; }</style>\n"
        '<div class="wrap"><h1>Hello</h1><p>Body text</p></div>\n'
    )

    def test_detects_a_whole_document(self):
        self.assertTrue(is_standalone_html("<!doctype html>\n<html><body>x</body></html>"))
        self.assertTrue(is_standalone_html('  <html lang="en"><body>x</body></html>'))
        self.assertFalse(is_standalone_html(self.FRAGMENT))
        self.assertFalse(is_standalone_html("<div>just a div</div>"))

    def test_wrapping_hoists_title_and_style_into_head(self):
        doc = ensure_standalone_html(self.FRAGMENT)
        head = doc[doc.index("<head>"):doc.index("</head>")]
        body = doc[doc.index("<body>"):doc.index("</body>")]

        self.assertIn("<title>My Page</title>", head)
        self.assertIn("<style>", head)
        self.assertIn('<div class="wrap">', body)
        # Left in the body, the title would be dropped and the style would be
        # non-conforming; neither may be duplicated across the two either.
        self.assertNotIn("<title>", body)
        self.assertNotIn("<style>", body)
        self.assertTrue(doc.lstrip().lower().startswith("<!doctype html>"))

    def test_wrapping_loses_no_content(self):
        doc = ensure_standalone_html(self.FRAGMENT)
        for fragment in ("My Page", "color: red", "Hello", "Body text"):
            self.assertIn(fragment, doc)

    def test_an_existing_document_is_returned_untouched(self):
        original = "<!doctype html>\n<html><head><title>T</title></head><body>x</body></html>"
        self.assertEqual(ensure_standalone_html(original), original)

    def test_title_fallback_only_applies_when_the_page_has_none(self):
        titled = ensure_standalone_html(self.FRAGMENT, title="Fallback")
        self.assertIn("<title>My Page</title>", titled)
        self.assertNotIn("Fallback", titled)

        untitled = ensure_standalone_html("<p>no title here</p>", title="Fallback")
        self.assertIn("<title>Fallback</title>", untitled)

    def test_comments_and_entities_survive_the_split(self):
        doc = ensure_standalone_html("<!-- keep me --><p>caf&eacute; &#38; more</p>")
        self.assertIn("<!-- keep me -->", doc)
        self.assertIn("caf&eacute;", doc)
        self.assertIn("&#38;", doc)

    def test_void_elements_do_not_unbalance_the_split(self):
        """An unclosed <br>/<img> must not leave the splitter stuck inside an element."""
        doc = ensure_standalone_html('<p>a<br>b</p><img src="x.png"><style>i{}</style>')
        head = doc[doc.index("<head>"):doc.index("</head>")]
        body = doc[doc.index("<body>"):doc.index("</body>")]
        self.assertIn("<style>i{}</style>", head)
        self.assertIn("<br>", body)
        self.assertIn('<img src="x.png">', body)


if __name__ == "__main__":
    unittest.main()
