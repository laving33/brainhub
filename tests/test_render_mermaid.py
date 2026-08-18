import unittest

from mcp_package.brainhub_core import render
from mcp_package.brainhub_core.render.registry import RendererError


class MermaidRendererTests(unittest.TestCase):
    def test_registered(self):
        self.assertIn("mermaid", render.registry.kinds())
        entry = render.registry.get("mermaid")
        self.assertEqual(entry.output_kind, "chart")
        self.assertTrue(entry.description)

    def test_build_document_basic(self):
        result = render.build_document(
            "mermaid", {"diagram": "graph TD; A-->B"}, title="My Diagram"
        )
        self.assertEqual(result.output_kind, "chart")
        self.assertEqual(result.title, "My Diagram")
        doc = result.html
        self.assertTrue(doc.startswith("<!DOCTYPE html>"))
        self.assertIn("graph TD; A--&gt;B", doc)
        self.assertIn("__esbuild_esm_mermaid_nm", doc)
        self.assertIn("Content-Security-Policy", doc)
        # No externally-referencing tags anywhere in the artifact (the vendored
        # mermaid bundle's own inert license/error-message text may still
        # contain "https://" substrings in comments/strings, which is fine —
        # those are never loaded; the CSP's default-src 'none' with no
        # connect-src blocks any egress regardless).
        for needle in ('src="http', 'href="http', 'src="//', "<script src="):
            self.assertNotIn(needle, doc)

    def test_definition_alias(self):
        result = render.build_document(
            "mermaid", {"definition": "sequenceDiagram; Alice->>Bob: Hi"}
        )
        self.assertIn("sequenceDiagram", result.html)

    def test_default_title(self):
        result = render.build_document("mermaid", {"diagram": "graph TD; A-->B"})
        self.assertEqual(result.title, "Diagram")

    def test_missing_diagram_raises(self):
        with self.assertRaises(ValueError):
            render.build_document("mermaid", {})

    def test_blank_diagram_raises(self):
        with self.assertRaises(ValueError):
            render.build_document("mermaid", {"diagram": "   "})

    def test_static_mode_flattens_motion(self):
        result = render.build_document(
            "mermaid", {"diagram": "graph TD; A-->B"}, static=True
        )
        self.assertIn("data-brainhub-static", result.html)

    def test_untrusted_text_is_escaped(self):
        result = render.build_document(
            "mermaid", {"diagram": "graph TD; A[<script>alert(1)</script>]-->B"}
        )
        # The <pre class="mermaid"> body copy must be HTML-escaped.
        self.assertNotIn("<script>alert(1)</script>", result.html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", result.html)
        self.assertNotIn("</script>alert(1)", result.html)

    def test_diagram_with_literal_close_script_tag_stays_self_contained(self):
        # The diagram source reaches the page only as html-escaped text inside
        # the <pre class="mermaid"> block — never inside a JS string literal —
        # so a literal "</script>" cannot close any inline <script> tag or
        # inject a live DOM element.
        evil = "graph TD; A[</script><img src=x onerror=alert(1)>]-->B"
        result = render.build_document("mermaid", {"diagram": evil})
        doc = result.html
        # The raw, HTML-tokenizer-breaking sequence must never appear as-is.
        self.assertNotIn("</script><img src=x onerror=alert(1)>", doc)
        # It survives only in html-escaped form, which the parser reads as text.
        self.assertIn("&lt;/script&gt;&lt;img src=x onerror=alert(1)&gt;", doc)

    def test_init_script_resolves_api_and_defers_until_dom_ready(self):
        # Regression: the bundle's shim exposes the API on
        # __esbuild_esm_mermaid_nm.mermaid.default (the bare .mermaid is the
        # module namespace), and the init script lives in <head>, so it must
        # wait for DOMContentLoaded before touching the container.
        doc = render.build_document("mermaid", {"diagram": "graph TD; A-->B"}).html
        self.assertIn("ns.mermaid.default", doc)
        self.assertIn("DOMContentLoaded", doc)
        self.assertIn("securityLevel: 'strict'", doc)

    def test_generated_svg_is_named_from_the_title(self):
        # Mermaid's own <svg> is role="graphics-document" with no accessible
        # name; the init script names it instead of the shell wrapping it.
        result = render.build_document(
            "mermaid", {"diagram": "graph TD; A-->B"}, title="流程圖"
        )
        # The name applied to the <svg> must be the document's own title, not
        # the renderer's "Diagram" fallback.
        marker = "setAttribute('aria-label', "
        start = result.html.find(marker)
        self.assertNotEqual(start, -1)
        self.assertEqual(
            result.html[start + len(marker) : start + len(marker) + 20],
            '"\\u6d41\\u7a0b\\u5716"',
        )
        self.assertNotIn('<figure role="img"', result.html)

    def test_hostile_title_cannot_break_out_of_the_init_script(self):
        evil = "</script><img src=x onerror=alert(1)>"
        doc = render.build_document(
            "mermaid", {"diagram": "graph TD; A-->B"}, title=evil
        ).html
        # Nowhere may the raw tokenizer-breaking sequence appear: the <title>
        # copies are html-escaped, and the init script's copy is slash-escaped.
        self.assertNotIn("</script><img src=x onerror=alert(1)>", doc)
        self.assertIn('"<\\/script><img src=x onerror=alert(1)>"', doc)

    def test_unknown_kind_still_raises_registry_error(self):
        with self.assertRaises(RendererError):
            render.build_document("not-a-real-kind", {"diagram": "graph TD; A-->B"})


if __name__ == "__main__":
    unittest.main()
