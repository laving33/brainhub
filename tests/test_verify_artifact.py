"""Tests for scripts/verify_artifact.py.

Two-polarity by design: every rule gets a case that MUST be caught and a
lookalike that must NOT be. A linter that only has violation tests drifts into
one that flags everything, and the first person to hit a false positive widens
the rule instead of fixing the artifact.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

from mcp_package.brainhub_core import render

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "verify_artifact", ROOT / "scripts" / "verify_artifact.py"
)
verify_artifact = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_artifact)

# Minimal valid spec per registered kind. Shares its shape with
# tests/test_render_report_charts.py; kept here so this file stands alone.
SPECS = {
    "bar": {"title": "T", "values": [3, 1], "labels": ["甲", "乙"]},
    "donut": {"title": "T", "values": [3, 1], "labels": ["甲", "乙"]},
    "gauge": {"title": "T", "value": 0.42},
    "heatmap": {"title": "T", "rows": [{"label": "列", "values": [1, 2]}],
                "col_labels": ["甲", "乙"]},
    "kpi": {"title": "T", "tiles": [{"label": "營收", "value": "1,234"}]},
    "line": {"title": "T", "series": [{"name": "s", "values": [1, 2]}],
             "x_labels": ["一", "二"]},
    "stacked-bar": {"title": "T", "rows": [{"label": "列", "segments": [1, 2]}],
                    "segment_names": ["甲", "乙"]},
    "funnel": {"title": "T", "stages": [{"label": "甲", "value": 10},
                                        {"label": "乙", "value": 5}]},
    "scatter": {"title": "T", "points": [{"x": 1, "y": 2, "label": "點"}]},
    "bar-chart": {"title": "T", "categories": ["甲", "乙"],
                  "series": [{"name": "s", "values": [1, 2]}]},
    "line-chart": {"title": "T", "x_labels": ["一", "二"],
                   "series": [{"name": "s", "points": [[0, 1], [1, 2]]}]},
    "mermaid": {"title": "T", "diagram": "graph TD; 甲-->乙;"},
    "interactive-html": {"title": "T", "sections": [{"heading": "節",
                                                     "body": "<p>中文</p>"}]},
}

# A structurally complete document, so element_count clears the meta-assert.
SHELL = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>t</title>"
    "<style>body {{ color: #000 }}</style></head>"
    "<body><main><p>text</p>{extra}</main></body></html>"
)


class ArtifactLinterTests(unittest.TestCase):
    def _findings(self, extra: str) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a.html"
            path.write_text(SHELL.format(extra=extra), encoding="utf-8")
            return verify_artifact.verify(path)

    def assertCaught(self, extra: str, needle: str):
        findings = self._findings(extra)
        self.assertTrue(
            any(needle in f for f in findings),
            f"expected a finding containing {needle!r}, got {findings}",
        )

    def assertClean(self, extra: str):
        self.assertEqual(self._findings(extra), [])

    # --- remote references ------------------------------------------------
    def test_remote_script_is_caught(self):
        self.assertCaught('<script src="https://cdn.example/x.js"></script>', "remote reference")

    def test_protocol_relative_reference_is_caught(self):
        self.assertCaught('<img src="//cdn.example/x.png">', "remote reference")

    def test_fragment_and_embedded_image_are_clean(self):
        self.assertClean('<a href="#top">top</a><img src="data:image/png;base64,iVBOR">')

    def test_no_op_favicon_data_url_is_clean(self):
        # The document layer emits exactly this so browsers stop probing
        # /favicon.ico; it carries no payload.
        self.assertClean('<link rel="icon" href="data:,">')

    # --- executable surface -----------------------------------------------
    def test_event_handler_attribute_is_caught(self):
        self.assertCaught('<button onclick="alert(1)">x</button>', "executable attribute")

    def test_javascript_url_is_caught(self):
        self.assertCaught('<a href="javascript:alert(1)">x</a>', "executable URL")

    def test_javascript_url_with_control_characters_is_caught(self):
        # The HTML navigation algorithm strips C0 characters before matching the
        # scheme, so a check that compares the raw value is trivially bypassed.
        self.assertCaught('<a href="jav\tascript:alert(1)">x</a>', "executable URL")

    def test_data_text_html_is_caught(self):
        self.assertCaught('<img src="data:text/html,<b>x">', "executable URL")

    def test_inline_script_without_src_is_clean(self):
        # Artifacts legitimately carry generated inline scripts; the CSP pins
        # them by hash. Only externally-sourced script is refused.
        self.assertClean("<script>var a = 1;</script>")

    # --- nested documents --------------------------------------------------
    def test_iframe_is_caught(self):
        self.assertCaught('<iframe src="x.html"></iframe>', "forbidden tag")

    def test_base_tag_is_caught(self):
        self.assertCaught('<base href="/x/">', "forbidden tag")

    def test_srcdoc_is_caught(self):
        self.assertCaught('<div srcdoc="<b>x</b>">y</div>', "srcdoc")

    # --- srcset candidate lists -------------------------------------------
    def test_remote_candidate_hidden_in_srcset_is_caught(self):
        self.assertCaught(
            '<img srcset="data:image/png;base64,iVBOR 1x, https://evil/x.png 2x">',
            "remote reference",
        )

    # --- CSS ---------------------------------------------------------------
    def test_css_import_is_caught(self):
        self.assertCaught("<style>@import url('https://evil/x.css');</style>", "@import")

    def test_css_remote_url_is_caught(self):
        self.assertCaught("<style>div { background: url(https://evil/x.png) }</style>", "CSS url()")

    def test_css_data_font_and_fragment_urls_are_clean(self):
        self.assertClean(
            "<style>@font-face { src: url(data:font/woff2;base64,d09) }"
            "rect { fill: url(#grad) }</style>"
        )

    # --- parser robustness -------------------------------------------------
    def test_script_source_text_is_not_scanned_as_markup(self):
        # A vendored bundle's own source contains attribute-looking strings.
        # The tokenizer treats script bodies as CDATA; a regex over raw text
        # would report a fleet of false positives here.
        self.assertClean(
            '<script>var t = \'<img src="https://example.com/x.png" onerror=1>\';</script>'
        )

    def test_unclosed_script_is_caught(self):
        findings = self._findings("<script>var a = 1;")
        self.assertTrue(any("unclosed <script>" in f for f in findings), findings)

    def test_non_document_input_is_reported_rather_than_passing(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a.html"
            path.write_text("not markup at all", encoding="utf-8")
            findings = verify_artifact.verify(path)
        self.assertTrue(any("not an HTML document" in f for f in findings), findings)

    def test_unreadable_file_is_reported(self):
        findings = verify_artifact.verify(Path("/nonexistent/nope.html"))
        self.assertTrue(any("unreadable" in f for f in findings), findings)


class EveryRendererProducesACleanArtifactTests(unittest.TestCase):
    """The gate that matters: real output of every registered kind."""

    def test_every_registered_kind_has_a_spec_here(self):
        missing = [k for k in render.registry.kinds() if k not in SPECS]
        self.assertEqual(missing, [], f"kinds with no spec in this test: {missing}")

    def test_every_kind_builds_a_clean_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            for kind in render.registry.kinds():
                with self.subTest(kind=kind):
                    path = Path(td) / f"{kind}.html"
                    path.write_text(
                        render.build_document(kind, SPECS[kind], title="標題").html,
                        encoding="utf-8",
                    )
                    self.assertEqual(verify_artifact.verify(path), [])


if __name__ == "__main__":
    unittest.main()
