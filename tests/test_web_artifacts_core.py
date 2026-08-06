import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.web_artifacts import (  # noqa: E402
    render_artifacts_page,
    render_documents_page,
)


def _layout(title, body):
    return f"<!doctype html><title>{title}</title><body>{body}</body>"


def _href(stored_path, sid=""):
    if sid:
        return f"/artifact/{sid}/" + stored_path.rsplit("/", 1)[-1]
    return "/artifact/" + stored_path.removeprefix("artifacts/")


class WebArtifactsCoreTests(unittest.TestCase):
    def test_gallery_groups_by_kind_with_zh_labels(self):
        catalog = {
            "count": 2,
            "artifacts": [
                {
                    "kind": "chart",
                    "agent": "bh-build",
                    "renderer": "line-chart",
                    "task": "mcp:bh_build",
                    "created_at": "2026-07-10T19:34:52+00:00",
                    "stored_path": "artifacts/charts/mcp.html",
                },
                {
                    "kind": "report",
                    "title": "季度回顧",
                    "agent": "chief",
                    "created_at": "2026-07-09T00:00:00+00:00",
                    "stored_path": "artifacts/reports/q3.html",
                },
            ],
        }
        html = render_artifacts_page(catalog, layout=_layout, artifact_href=_href)

        # Grouped headings use zh-TW labels.
        self.assertIn("圖表", html)
        self.assertIn("報告", html)
        # Fallback title from filename stem when meta lacks a title.
        self.assertIn(">mcp<", html)
        # Explicit meta title is used when present.
        self.assertIn("季度回顧", html)
        # Provenance surfaced.
        self.assertIn("bh-build", html)
        self.assertIn("line-chart", html)
        self.assertIn("2026-07-10T19:34:52+00:00", html)
        # Open link points at the serve-artifact route.
        self.assertIn('href="/artifact/charts/mcp.html"', html)
        self.assertIn('href="/artifact/reports/q3.html"', html)
        # Count reflected in heading.
        self.assertIn("產出 (2)", html)

    def test_gallery_empty_state(self):
        html = render_artifacts_page({"count": 0, "artifacts": []}, layout=_layout, artifact_href=_href)
        self.assertIn("目前還沒有任何產出", html)
        self.assertIn("產出 (0)", html)

    def test_gallery_escapes_hostile_metadata(self):
        catalog = {
            "artifacts": [
                {
                    "kind": "chart",
                    "title": "<script>alert(1)</script>",
                    "agent": "<b>x</b>",
                    "stored_path": "artifacts/charts/evil.html",
                }
            ]
        }
        html = render_artifacts_page(catalog, layout=_layout, artifact_href=_href)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<b>x</b>", html)

    def test_documents_list_renders_links(self):
        docs = [
            {
                "name": "診斷樣板",
                "title": "診斷樣板：廣告投放連續性",
                "href": "/page/%E8%A8%BA%E6%96%B7",
                "date": "2026-07-10T19:39:20+00:00",
                "tags": ["document", "bd"],
            }
        ]
        html = render_documents_page(docs, layout=_layout)
        self.assertIn("診斷樣板：廣告投放連續性", html)
        self.assertIn('href="/page/%E8%A8%BA%E6%96%B7"', html)
        self.assertIn("2026-07-10T19:39:20+00:00", html)
        self.assertIn("document", html)
        self.assertIn("文件 (1)", html)

    def test_documents_empty_state(self):
        html = render_documents_page([], layout=_layout)
        self.assertIn("目前還沒有發佈任何文件", html)


if __name__ == "__main__":
    unittest.main()
