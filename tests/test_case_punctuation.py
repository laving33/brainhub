"""The embedded brand face must not print characters that cannot be read back.

The bug this replaces a human promise for — 2026-07-24, found because a fix that
landed 07-15 was still reproducing on 07-24:

Inter ships case-sensitive punctuation (dashes, ≥, brackets — forms drawn to align
with capitals) whose *only* cmap entry is a Private Use codepoint. Chrome picks them
during layout with no CSS asking for it, so the glyph on the page is the right shape
and the page looks perfect to every human who opens it — but the character behind it
is U+E0xx. `pypdf` extracts garbage, `doc-release` blocks the document ("printed but
unreadable ≠ not printed"), and no amount of looking finds it.

sales-kit fixed this in its own build (`commercial/render/build_doc.py`) and brainhub
never got the fix, because the two product lines reach the same font family down two
different paths. The fix now lives here as CODE, not as a second copy of the font
bytes: a copy would be a frozen mirror of the brand face, and mirrors drift silently
(see `test_brand_assets.py` for what that costs).

WHY THESE ASSERTIONS ARE AT THE FONT LEVEL, NOT THE DOCUMENT LEVEL
------------------------------------------------------------------
Chrome's `.case` pick is CONTEXTUAL. Two test documents written on 2026-07-24
surfaced *different* PUA sets ({E089, E0A1, E1D7} and {E088}) from the same font.
So "I rendered a document and it extracted cleanly" is never coverage — it samples
whichever codepoints that one sentence happened to trigger, out of 188.

`test_no_pua_only_case_glyphs_survive` asserts over the WHOLE cmap instead. That is
coverage no document sample can give, and it is the reason this file is the thing
that stops a recurrence rather than a decoration on top of one.

⚠ Two traps for anyone editing this file:
  * `fonts._CASE_CACHE` is bound at IMPORT time from $XDG_CACHE_HOME. Setting that
    env var inside a test is TOO LATE — the module is already imported, and the test
    would silently assert against the developer's real ~/.cache. Patch the module
    attribute (see `setUp`), and clear `fonts._case_memo` as well.
  * Every "after repair is clean" assertion is paired with a negative control that
    the UNREPAIRED input is dirty. A checker that cannot go red proves nothing.
"""
from __future__ import annotations

import base64
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_package"))

from brainhub_core.render import fonts  # noqa: E402

CANON = [
    fonts.BRAND_FONTS / "Inter-Light.woff2",
    fonts.BRAND_FONTS / "Inter-Regular.woff2",
]
DIGITS = range(0x30, 0x3A)


def _in_pua(codepoint: int) -> bool:
    return 0xE000 <= codepoint <= 0xF8FF


def _cmap(raw: bytes) -> dict[int, str]:
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(raw))
    best = dict(font.getBestCmap())
    font.close()
    return best


def _pua_only_case_glyphs(raw: bytes) -> dict[str, list[int]]:
    """`.case` glyphs whose only route in the cmap is a Private Use codepoint.

    This is the trap itself, counted directly — not a document that might or might
    not happen to use one of them.
    """
    reachable: dict[str, list[int]] = {}
    for codepoint, glyph in _cmap(raw).items():
        reachable.setdefault(glyph, []).append(codepoint)
    return {
        glyph: cps
        for glyph, cps in reachable.items()
        if glyph.endswith(".case") and cps and all(_in_pua(cp) for cp in cps)
    }


def _advance_widths(raw: bytes) -> dict[str, int]:
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(raw))
    widths = {glyph: font["hmtx"][glyph][0] for glyph in font.getGlyphOrder()}
    font.close()
    return widths


def _font_with_a_digit_trap(raw: bytes) -> bytes:
    """Synthesize the one input the digit guard exists for.

    Inter has no `one.case`, so the guard can never fire on the real brand face —
    shipping it untested would be shipping a guard nobody has ever seen work.

    Rather than graft a new glyph (which means keeping `glyf`, `hmtx`, the glyph
    order and `maxp` consistent by hand), point U+0031 at the `endash` glyph: that
    one already has a PUA-only `.case` twin, so the repair now computes a redirect
    for U+0031 and the guard's precondition is real. Pure cmap edit — the same class
    of change the repair itself makes, so it round-trips.
    """
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(raw))
    for table in font["cmap"].tables:
        if 0x31 in table.cmap:
            table.cmap[0x31] = "endash"
    buffer = io.BytesIO()
    font.flavor = "woff2"
    font.save(buffer)
    font.close()
    return buffer.getvalue()


class _IsolatedFontCache(unittest.TestCase):
    """Base class: every test here runs against a cache of its own.

    This is a BASE CLASS rather than a `setUp` copied into each test class, because
    forgetting it does not raise — it silently serves a previously-cached face. That
    is not hypothetical: the first draft of this file isolated only the cmap tests,
    and the end-to-end red control then "proved" an unrepaired render was clean. It
    was reading the repaired face straight out of the developer's real ~/.cache.

    `_case_only_face` has TWO caches (module dict + disk) and `_CASE_CACHE` is bound
    at import from $XDG_CACHE_HOME, so setting that env var here would be too late.
    Patch the attribute; clear the dict.
    """

    def setUp(self) -> None:
        self._cache_dir = tempfile.mkdtemp(prefix="brainhub-font-test-")
        self._real_cache = fonts._CASE_CACHE
        self._real_memo = fonts._case_memo
        fonts._CASE_CACHE = Path(self._cache_dir)
        fonts._case_memo = {}

    def tearDown(self) -> None:
        fonts._CASE_CACHE = self._real_cache
        fonts._case_memo = self._real_memo
        shutil.rmtree(self._cache_dir, ignore_errors=True)


class CasePunctuationRepairTest(_IsolatedFontCache):
    """The cmap-level contract. Runs anywhere fontTools does."""

    def _repaired(self, path: Path) -> bytes:
        """Repair, failing legibly if it declined.

        Without this, a disabled repair surfaces as `TTLibError: not enough data`
        from deep inside fontTools — technically red, but it sends the next reader
        looking for a corrupt font instead of a missing fix.
        """
        out = fonts._remap_case_punctuation(path.read_bytes())
        self.assertIsNotNone(
            out,
            f"{path.name}: the repair returned None (declined to patch). Expected this "
            f"face to carry the .case trap — the fix may have been removed or the "
            f"brand font may have changed.",
        )
        return out

    def test_canon_face_actually_has_the_trap(self) -> None:
        """Negative control. Without this, "0 after repair" could just mean "0 always"."""
        for path in CANON:
            with self.subTest(face=path.name):
                trapped = _pua_only_case_glyphs(path.read_bytes())
                self.assertGreater(
                    len(trapped),
                    0,
                    f"{path.name}: no PUA-only .case glyphs found in the UNREPAIRED "
                    f"face. Either the brand font changed or this checker is broken — "
                    f"stop and re-check before trusting any green below.",
                )

    def test_no_pua_only_case_glyphs_survive(self) -> None:
        """The invariant, over the whole cmap — not over a sampled document."""
        for path in CANON:
            with self.subTest(face=path.name):
                repaired = self._repaired(path)
                left = _pua_only_case_glyphs(repaired)
                self.assertEqual(
                    left,
                    {},
                    f"{path.name}: {len(left)} .case glyphs are still reachable only "
                    f"through PUA: {sorted(left)[:5]}",
                )

    def test_digits_never_move(self) -> None:
        """The tnum half of sales-kit's fix must never arrive here.

        Baking tabular figures in would widen `one` from 833 to 1328 units (+59%) —
        a visible restyle of every number in every document, curing a disease
        brainhub does not have (it never requests `tnum`).
        """
        for path in CANON:
            with self.subTest(face=path.name):
                raw = path.read_bytes()
                before, after = _cmap(raw), _cmap(self._repaired(path))
                for codepoint in DIGITS:
                    self.assertEqual(
                        before.get(codepoint),
                        after.get(codepoint),
                        f"{path.name}: U+{codepoint:04X} moved "
                        f"{before.get(codepoint)} -> {after.get(codepoint)}",
                    )

    def test_nothing_reflows(self) -> None:
        """Advance widths and glyph order are the layout contract; only cmap may move."""
        for path in CANON:
            with self.subTest(face=path.name):
                raw = path.read_bytes()
                self.assertEqual(_advance_widths(raw), _advance_widths(self._repaired(path)))

    def test_repair_is_idempotent_and_white_label_safe(self) -> None:
        """A face with no trap ships unchanged — None, not an exception.

        This is deliberately NOT sales-kit's fail-loud behaviour: that build ships one
        known font, while `BRAINHUB_BRAND_FONTS` may point at any face. It also means
        feeding the repaired face back in is safe, which is exactly the loop that
        would have crashed sales-kit's build had we baked the fix into brand assets.
        """
        repaired = fonts._remap_case_punctuation(CANON[0].read_bytes())
        self.assertIsNone(fonts._remap_case_punctuation(repaired))

    def test_digit_trap_makes_the_repair_bail_out(self) -> None:
        """The guard chief added must be observed firing, not assumed."""
        grafted = _font_with_a_digit_trap(CANON[0].read_bytes())
        self.assertEqual(_cmap(grafted).get(0x31), "endash", "graft failed — the guard was never exercised")
        self.assertIsNone(
            fonts._remap_case_punctuation(grafted),
            "a redirect that would move U+0031 must abandon the repair and ship the original",
        )

    def test_cached_face_is_the_repaired_one(self) -> None:
        """`_case_only_face` is what `embedded_font_css` actually calls."""
        served = fonts._case_only_face(CANON[0])
        self.assertEqual(_pua_only_case_glyphs(served), {})
        self.assertEqual(served, fonts._case_only_face(CANON[0]), "second call disagreed with the first")

    def test_embedded_css_carries_the_repaired_face(self) -> None:
        """End of the road: the bytes that actually land in a document.

        Asserting merely that *a* woff2 is inlined would stay green even if
        `embedded_font_css` were reverted to embedding the raw face — which is the
        one regression this whole file exists to catch, and the assertion's own name
        would still claim otherwise. So decode what was inlined and check both
        directions: no raw face present, and the repaired faces are.
        """
        def digest(blob: bytes) -> str:
            # Compare by hash, never by raw bytes: a failed set-comparison on woff2
            # blobs prints ~600 KB of binary into the log, which buries the one fact
            # the reader needs. Same reason `_repaired()` exists above.
            return hashlib.sha256(blob).hexdigest()[:12]

        css = fonts.embedded_font_css("<p>甲方（以下簡稱「甲方」）：2026–2027 ±5% ≥ 90%</p>")
        inlined = {
            digest(base64.b64decode(blob))
            for blob in re.findall(r"data:font/woff2;base64,([A-Za-z0-9+/=]+)", css)
        }
        self.assertTrue(inlined, "no font was embedded at all")

        leaked = [p.name for p in CANON if digest(p.read_bytes()) in inlined]
        self.assertFalse(
            leaked,
            f"UNREPAIRED face(s) inlined: {leaked} — embedded_font_css() no longer "
            f"routes through _case_only_face()",
        )
        absent = [p.name for p in CANON if digest(fonts._case_only_face(p)) not in inlined]
        self.assertFalse(absent, f"repaired face(s) never reached the document: {absent}")


def _pypdf_available() -> bool:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


CHROME_PDF = Path("/home/aworkr/aworkr/tools/chrome/chrome-pdf")


@unittest.skipUnless(_pypdf_available(), "pypdf not installed in this venv")
@unittest.skipUnless(CHROME_PDF.is_file(), "chrome-pdf not available")
class RenderedDocumentTest(_IsolatedFontCache):
    """The end-to-end claim, with its own red control so the ruler is never assumed.

    Skipped where the deps are missing (brainhub's venv has no pypdf as of
    2026-07-24) — which is precisely why the real contract is asserted at the font
    level above and not here.
    """

    MARKDOWN = (
        "# 可讀性\n\n甲方（以下簡稱「甲方」）：金額 NT$ 210,000 — 期間 2026–2027，"
        "增減 ±5%，效率 ≥ 90%，流程 A → B。\n"
    )

    def _extract(self, *, repair: bool) -> str:
        from pypdf import PdfReader

        from brainhub_core.render.markdown_doc import render_markdown_document

        real = fonts._remap_case_punctuation
        # the disk cache is already redirected to a tmp dir by the base class; the
        # memo still has to be cleared BETWEEN the two renders or the second one
        # gets the first one's face.
        fonts._case_memo = {}
        if not repair:
            fonts._remap_case_punctuation = lambda raw: None
        try:
            html = render_markdown_document(self.MARKDOWN, title="可讀性", profile="a4", static=True)
            with tempfile.TemporaryDirectory() as tmp:
                page, pdf = Path(tmp) / "p.html", Path(tmp) / "p.pdf"
                page.write_text(html, encoding="utf-8")
                subprocess.run([str(CHROME_PDF), str(page), str(pdf)], check=True, capture_output=True)
                return "".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)
        finally:
            fonts._remap_case_punctuation = real

    def test_unrepaired_render_is_dirty(self) -> None:
        """Red control: prove this pipeline can detect the bug before trusting green."""
        pua = {c for c in self._extract(repair=False) if _in_pua(ord(c))}
        self.assertTrue(pua, "the unrepaired render extracted clean — this checker is blind")

    def test_repaired_render_extracts_cleanly(self) -> None:
        text = self._extract(repair=True)
        pua = sorted({f"U+{ord(c):04X}" for c in text if _in_pua(ord(c))})
        self.assertEqual(pua, [], f"unreadable characters survived: {pua}")
        self.assertIn("210,000", text)


if __name__ == "__main__":
    unittest.main()
