"""A Chinese document must never be rendered without an embedded CJK face.

The bug this replaces a human promise for — reported 2026-08-09, after the
documents had already gone out:

The print pipeline took its CJK face from a brand asset directory that is not in
the distributed package, and needed fontTools (an optional extra) to subset it. So
on a clean install neither was present, and Chinese documents rendered with no CJK
face at all. Two consequences, and the reason nobody caught them for a whole
production run is that **both pass a page-by-page human review**:

  * CJK bold silently stops working — ``<strong>`` is still in the markup, the
    paper looks the same.
  * The PDF text layer records whatever codepoint the *substituted* font's glyph
    happened to be reachable by. Observed: Kangxi Radicals, ``山`` U+5C71 arriving
    as ``⼭`` U+2F2D. The glyph on the page is the correct shape, so it is
    invisible to the eye; the client simply cannot search the document, and
    copy-paste yields broken characters.

Whoever renders can never see either one: their machine has system CJK fonts to
fall back on. Only the recipient sees it, and the recipient is the client.

Every assertion here is paired with the negative control that makes it mean
something — a check that cannot go red proves nothing.
"""
from __future__ import annotations

import sys
import unittest.mock
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.render import fonts  # noqa: E402

VENDORED = ROOT / "mcp_package" / "brainhub_core" / "vendor" / fonts.VENDORED_CJK_FACE
# The exact words the report found unsearchable.
REPORTED = "華山大安龍山寺士林夜市"
# Rare given-name characters that ARE in Big5 — the kind a hand-kept "common
# characters" list drops while a codec-derived repertoire keeps.
RARE_NAME_CHARS = "瑄嬛鑫"


def _character_the_face_cannot_draw() -> str | None:
    """A CJK character genuinely outside the shipped coverage, found at run time.

    Derived rather than hard-coded: the coverage has been widened once already, and
    a hard-coded "rare" character silently becomes a covered one, at which point the
    test passes for the wrong reason. Noto Sans TC carries only part of Ext-A, so
    something in that block is always missing.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    font = TTFont(str(VENDORED))
    cmap = font.getBestCmap()
    font.close()
    for codepoint in range(0x3400, 0x4DC0):  # CJK Ext-A
        if codepoint not in cmap:
            return chr(codepoint)
    return None


class VendoredCjkFaceTests(unittest.TestCase):
    """The face has to be in the tree, because that is what a fresh install gets."""

    def test_the_face_ships_with_the_package(self):
        self.assertTrue(
            VENDORED.is_file(),
            f"{fonts.VENDORED_CJK_FACE} is missing — a fresh install cannot embed CJK. "
            "Rebuild it with scripts/build_cjk_subset.py.",
        )
        # A truncated or placeholder file passes is_file() and fails at render.
        self.assertGreater(VENDORED.stat().st_size, 1_000_000)

    def test_the_licence_travels_with_it(self):
        """The OFL requires this; shipping the font without it is a licence breach."""
        self.assertTrue(VENDORED.with_suffix("").with_suffix(".LICENSE.txt").is_file()
                        or (VENDORED.parent / f"{VENDORED.stem}.LICENSE.txt").is_file())

    def test_the_reported_characters_are_reachable_by_their_own_codepoint(self):
        """The heart of it: 山 must be reachable as U+5C71, not only as a radical."""
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest("fontTools not installed; cmap cannot be inspected")
        font = TTFont(str(VENDORED))
        cmap = font.getBestCmap()
        font.close()

        for char in REPORTED + RARE_NAME_CHARS:
            with self.subTest(char=char):
                self.assertIn(
                    ord(char), cmap,
                    f"{char!r} U+{ord(char):04X} is not in the vendored face — it would "
                    "fall back to the reader's fonts and may land in the text layer as "
                    "some other codepoint entirely",
                )

    def test_no_glyph_is_reachable_only_through_a_kangxi_radical(self):
        """The mechanism of the reported corruption, asserted over the whole cmap.

        A glyph whose *only* cmap entry is a Kangxi Radical is one Chrome can pick
        during layout, which puts U+2Fxx in the text layer while the page looks
        perfect. Asserting over every glyph is coverage no sample document can
        give: which codepoints a given sentence triggers is contextual.
        """
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest("fontTools not installed; cmap cannot be inspected")
        font = TTFont(str(VENDORED))
        cmap = font.getBestCmap()
        font.close()

        reachable: dict[str, list[int]] = {}
        for codepoint, glyph in cmap.items():
            reachable.setdefault(glyph, []).append(codepoint)
        trapped = {
            glyph: cps
            for glyph, cps in reachable.items()
            if cps and all(0x2F00 <= cp <= 0x2FDF for cp in cps)
        }
        self.assertEqual(trapped, {}, f"glyphs reachable only via Kangxi Radicals: {trapped}")

    def test_the_weight_axis_survived_subsetting(self):
        """Instancing to one weight is how CJK bold silently stops working."""
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest("fontTools not installed; fvar cannot be inspected")
        font = TTFont(str(VENDORED))
        has_fvar = "fvar" in font
        axes = [axis.axisTag for axis in font["fvar"].axes] if has_fvar else []
        font.close()
        self.assertTrue(has_fvar, "not a variable font — font-weight:100 900 cannot work")
        self.assertIn("wght", axes)


class EmbeddedFontCssTests(unittest.TestCase):
    def test_cjk_content_always_gets_a_face_even_with_no_brand_fonts(self):
        """The clean-install case that shipped broken documents for a whole run."""
        css = fonts.embedded_font_css(
            f"<p>{REPORTED}</p>", fonts_dir=Path("/nonexistent-brand-fonts")
        )
        self.assertIn("Noto Sans TC", css)
        self.assertIn("font-weight:100 900", css)
        self.assertIn("base64,", css)

    def test_latin_only_content_embeds_no_cjk_face(self):
        """Negative control: proves the assertion above is not vacuously true.

        Also the size guard — a CJK face in every English document would put
        megabytes into files that do not need a single glyph of it.
        """
        css = fonts.embedded_font_css(
            "<p>plain ASCII only</p>", fonts_dir=Path("/nonexistent-brand-fonts")
        )
        self.assertNotIn("Noto Sans TC", css)

    def test_the_embedded_face_is_subset_to_the_document(self):
        """Embedding the whole repertoire would add ~5 MB to every document."""
        try:
            import fontTools  # noqa: F401
        except ImportError:
            self.skipTest("fontTools not installed; the whole face is embedded by design")
        css = fonts.embedded_font_css(
            f"<p>{REPORTED}</p>", fonts_dir=Path("/nonexistent-brand-fonts")
        )
        self.assertLess(
            len(css), 400_000,
            "the CJK face was embedded whole rather than subset to the document",
        )

    def test_has_cjk_reads_the_text_not_the_markup(self):
        self.assertTrue(fonts.has_cjk("山"))
        self.assertTrue(fonts.has_cjk("mixed 中文 text"))
        self.assertFalse(fonts.has_cjk("ASCII and punctuation -- only!"))

    def test_a_character_beyond_the_subset_is_named_not_silently_dropped(self):
        """Embedding a face is not the same as covering the document.

        The subset stops at Big5, so a rarer character still falls back — the same
        corruption, narrower. What must not happen is it doing so quietly: the
        renderer's own machine has system CJK fonts and shows it correctly.
        """
        import io
        from contextlib import redirect_stderr

        uncovered = _character_the_face_cannot_draw()
        if uncovered is None:
            self.skipTest("fontTools unavailable, or the face covers all of Ext-A")

        captured = io.StringIO()
        with redirect_stderr(captured):
            css = fonts.embedded_font_css(
                f"<p>王{uncovered}先生</p>", fonts_dir=Path("/nonexistent-brand-fonts")
            )
        warning = captured.getvalue()

        self.assertIn("Noto Sans TC", css, "the covered characters must still be embedded")
        self.assertIn("does not cover", warning)
        self.assertIn(uncovered, warning, "the warning must name the character")
        self.assertIn("build_cjk_subset.py", warning, "and say how to fix it")

    def test_a_fully_covered_document_warns_about_nothing(self):
        """Negative control: otherwise the warning above could fire on everything."""
        import io
        from contextlib import redirect_stderr

        captured = io.StringIO()
        with redirect_stderr(captured):
            fonts.embedded_font_css(
                f"<p>{REPORTED}{RARE_NAME_CHARS}</p>", fonts_dir=Path("/nonexistent-brand-fonts")
            )
        self.assertEqual(captured.getvalue(), "")


class CjkReadinessTests(unittest.TestCase):
    def test_reports_ready_while_the_vendored_face_is_present(self):
        readiness = fonts.cjk_readiness()
        self.assertTrue(readiness["ready"])
        self.assertIsNone(readiness["remedy"])
        self.assertEqual(readiness["vendored_face"], str(VENDORED))

    def test_an_unready_install_names_the_remedy(self):
        """What someone hitting this actually needs: which of the two causes it is."""
        with unittest.mock.patch.object(fonts, "_VENDOR_DIR", Path("/nonexistent-vendor")):
            with unittest.mock.patch.object(fonts, "BRAND_FONTS", Path("/nonexistent-brand")):
                readiness = fonts.cjk_readiness()
        self.assertFalse(readiness["ready"])
        self.assertIn("build_cjk_subset.py", readiness["remedy"])


class PdfRendererDiscoveryTests(unittest.TestCase):
    """The download-PDF button used to depend on one absolute in-house path."""

    def setUp(self) -> None:
        from brainhub_core.render import pdf
        self.pdf = pdf

    def test_a_configured_wrapper_always_wins(self):
        renderer = self.pdf.find_pdf_renderer({self.pdf.CHROME_PDF_ENV: "/opt/house/chrome-pdf"})
        self.assertEqual(renderer.kind, "wrapper")
        command = renderer.command(Path("/tmp/in.html"), Path("/tmp/out.pdf"))
        self.assertEqual(command, ["/opt/house/chrome-pdf", "/tmp/in.html", "/tmp/out.pdf", "20000"])

    def test_a_configured_wrapper_is_honoured_even_when_absent(self):
        """Reporting "what you configured is missing" beats silently using something else."""
        renderer = self.pdf.find_pdf_renderer({self.pdf.CHROME_PDF_ENV: "/nope/chrome-pdf"})
        self.assertEqual(renderer.kind, "wrapper")

    def test_a_discovered_browser_is_driven_with_print_to_pdf(self):
        import shutil
        with unittest.mock.patch.object(
            shutil, "which", lambda name: "/usr/bin/chromium" if name == "chromium" else None
        ):
            renderer = self.pdf.find_pdf_renderer({})
        self.assertIsNotNone(renderer, "discovery found nothing with chromium on PATH")
        self.assertEqual(renderer.kind, "chrome")
        command = renderer.command(Path("/tmp/in.html"), Path("/tmp/out.pdf"))
        self.assertIn("--headless=new", command)
        self.assertIn("--print-to-pdf=/tmp/out.pdf", command)
        # Chrome's own header/footer would print over the artifact's @media print layout.
        self.assertIn("--no-pdf-header-footer", command)
        self.assertTrue(command[-1].startswith("file://"))

    def test_no_browser_and_no_config_reports_an_actionable_reason(self):
        import shutil
        with unittest.mock.patch.object(shutil, "which", lambda _name: None):
            with unittest.mock.patch.object(self.pdf, "CHROME_FALLBACK_PATHS", ()):
                self.assertIsNone(self.pdf.find_pdf_renderer({}))
        reason = self.pdf.pdf_unavailable_reason()
        self.assertIn("Chromium", reason)
        self.assertIn(self.pdf.CHROME_PDF_ENV, reason)


if __name__ == "__main__":
    unittest.main()
