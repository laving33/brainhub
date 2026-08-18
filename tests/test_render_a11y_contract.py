"""The accessible-name contract every chart artifact must satisfy.

Each chart renderer used to invent its own: report_chart emitted
``<title>``/``<desc>`` with no ids and nothing referencing them, while the
legacy bar/line renderers emitted an ``aria-label`` and no ``<desc>`` at all.
Both render identically on screen, which is why three conventions coexisted
unnoticed. These tests pin one.
"""
import re
import unittest

from mcp_package.brainhub_core import render

# Kinds whose <svg> this file owns. report_chart.py is a byte-frozen mirror of
# an upstream SSoT (see tests/test_brand_assets.py) — editing it here would be
# the exact silent drift that guard exists to catch, so its <svg> contract is
# tracked upstream and deliberately not asserted here.
OWNED = {
    "bar-chart": {"title": "T", "categories": ["甲", "乙"],
                  "series": [{"name": "s", "values": [1, 2]}]},
    "line-chart": {"title": "T", "x_labels": ["一", "二"],
                   "series": [{"name": "s", "points": [[0, 1], [1, 2]]}]},
}


def _chart_region(doc: str) -> str:
    """The <main> content, so the header's decorative logo <svg> is excluded."""
    return doc.split("<main", 1)[1]


class AccessibleNameContractTests(unittest.TestCase):
    def test_the_decorative_logo_is_hidden_from_assistive_tech(self):
        # It carries its own role="img"/aria-label, so it must be hidden at the
        # wrapper or it announces the vendor's name before the chart's.
        doc = render.build_document("line-chart", OWNED["line-chart"], title="標題").html
        header = doc.split("<main", 1)[0]
        if "brainhub-logo" in header:
            self.assertIn('class="brainhub-logo" aria-hidden="true"', header)

    def test_svg_names_itself_via_title_and_desc(self):
        for kind, spec in OWNED.items():
            with self.subTest(kind=kind):
                doc = render.build_document(kind, spec, title="標題").html
                svg = re.search(r"<svg\b[^>]*>", _chart_region(doc)).group(0)
                self.assertIn('role="img"', svg)
                self.assertIn("aria-labelledby=", svg)
                labelled = re.search(r'aria-labelledby="([^"]+)"', svg).group(1).split()
                self.assertEqual(len(labelled), 2, "expected a title id then a desc id")
                for element_id in labelled:
                    self.assertIn(f'id="{element_id}"', doc)

    def test_title_is_the_first_child_of_the_svg(self):
        # Assistive tech may ignore a <title> that is not first.
        for kind, spec in OWNED.items():
            with self.subTest(kind=kind):
                doc = render.build_document(kind, spec, title="標題").html
                after_open = _chart_region(doc).split("<svg", 1)[1].split(">", 1)[1]
                self.assertTrue(
                    after_open.lstrip().startswith("<title"),
                    f"{kind}: <svg> does not open with <title>",
                )

    def test_naming_ids_are_prefixed_not_bare(self):
        # Two charts on one page with id="title" would make the second announce
        # the first one's name.
        for kind, spec in OWNED.items():
            with self.subTest(kind=kind):
                region = _chart_region(render.build_document(kind, spec, title="標題").html)
                self.assertNotIn('id="title"', region)
                self.assertNotIn('id="desc"', region)

    def test_desc_is_not_empty(self):
        for kind, spec in OWNED.items():
            with self.subTest(kind=kind):
                region = _chart_region(render.build_document(kind, spec, title="標題").html)
                desc = re.search(r"<desc[^>]*>(.*?)</desc>", region, re.DOTALL)
                self.assertIsNotNone(desc)
                self.assertTrue(desc.group(1).strip())


class ReducedMotionTests(unittest.TestCase):
    def test_every_artifact_honours_prefers_reduced_motion(self):
        # Independent of --static: that is a build-time capture choice, while
        # this is the reader's OS accessibility setting.
        doc = render.build_document(
            "interactive-html",
            {"sections": [{"heading": "節", "body": "<p>x</p>"}]},
            title="T",
        ).html
        self.assertIn("@media (prefers-reduced-motion: reduce)", doc)
        self.assertIn("data-brainhub-reduced-motion", doc)
        self.assertNotIn("data-brainhub-static", doc)

    def test_static_build_still_flattens_unconditionally(self):
        doc = render.build_document(
            "mermaid", {"diagram": "graph TD; A-->B"}, title="T", static=True
        ).html
        self.assertIn("data-brainhub-static", doc)
        self.assertIn("data-brainhub-reduced-motion", doc)


if __name__ == "__main__":
    unittest.main()
