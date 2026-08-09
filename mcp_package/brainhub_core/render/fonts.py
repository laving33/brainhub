"""Embed the brand faces INTO the file, subset to the glyphs actually used.

Why this is not a styling concern (and so cannot be left to ``--css``):

A CSS ``font-family`` declaration is a *request*. On the machine that produced the
document the font is installed, so the request is granted and the page looks right
— forever, to its author. On the recipient's machine it is not installed, the
request silently falls back to a system face, and the document they see is not the
document you approved. **You can never see this bug on your own screen.** It is
only visible to the person you sent it to, which is the client.

So: for anything print/client-facing, the bytes ride along. The vendored CJK face
is 12 MB, which is why we subset to exactly the characters the document contains —
a typical contract needs a few hundred glyphs and lands around 10 KB of font.

For CJK this is not even a typography question. A Chinese document that falls back
loses bold silently AND can record the wrong codepoint in the PDF text layer, so
the page looks perfect while the client cannot search it. See embedded_font_css.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import sys
from pathlib import Path

from .. import brand as _brand

# The Latin brand faces. A brand pack's ``fonts/`` wins, then BRAINHUB_BRAND_FONTS,
# then the bundled theme's own location -- an absolute path that only exists on the
# machines owning the brand source. Absent, these degrade gracefully: the document
# renders in a system Latin face, which is a typography loss and nothing worse.
# The CJK face below is deliberately NOT treated this way.
BUNDLED_BRAND_FONTS = Path("/home/aworkr/aworkr/core/library/brand/assets/fonts")
BRAND_FONTS = _brand.fonts_dir(BUNDLED_BRAND_FONTS)

# The CJK face BrainHub ships with: Noto Sans CJK TC, subset to Big5 plus the
# Ext-A/Ext-B/compatibility han the source carries. Unlike the Latin brand faces
# this is not optional -- see embedded_font_css for what its absence does to a
# client's PDF. The pan-CJK face rather than Noto Sans TC for two reasons: it
# covers 99.8% of Ext-A instead of 8.7%, and being CFF-based it has no `gvar`
# table, which makes subsetting it ~25x faster (0.3s vs 7.4s per document).
_VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"
VENDORED_CJK_FACE = "NotoSansCJKtc-subset.woff2"

_TAG = re.compile(r"<[^>]+>")

# Subsetting a CJK face costs real time, and the result is a pure function of the
# face bytes and the characters asked for -- so it is cached the same way the Latin
# repair is, and for the same reason. Cached hits are ~2ms.
#
# Kept even though the current face subsets in ~0.3s: the cache is what makes the
# cost independent of which face is vendored, and a TrueType-flavoured brand face
# pointed at by BRAINHUB_BRAND_FONTS still pays seconds for its `gvar` table.
# Nothing interactive pays it either way -- the viewer serves artifacts whose font
# was embedded when they were rendered.
_SUBSET_CACHE = Path(
    os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
) / "brainhub" / "cjk-subsets"
_subset_memo: dict[str, bytes] = {}


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _subset_cjk(font_path: Path, text: str) -> bytes | None:
    """Subset the CJK face to `text`, as woff2. None if fontTools absent.

    Cached, because on a TrueType-flavoured face this costs seconds — enough to
    dominate a render. Keyed by the content hash
    of the source face plus the exact character set, so changing either changes the
    key: a cache keyed by path would go on serving a subset of the previous font,
    which is the silent-drift failure ``_case_only_face`` documents.
    """
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError:  # pragma: no cover - depends on the install
        return None

    try:
        raw = font_path.read_bytes()
    except OSError:
        return None
    key = hashlib.sha256(
        hashlib.sha256(raw).digest() + "".join(sorted(set(text))).encode("utf-8")
    ).hexdigest()
    if key in _subset_memo:
        return _subset_memo[key]

    cached = _SUBSET_CACHE / f"{key}.woff2"
    try:
        if cached.is_file():
            data = cached.read_bytes()
            _subset_memo[key] = data
            return data
    except OSError:
        pass

    options = subset.Options(flavor="woff2", layout_features=["*"], drop_tables=[])
    options.desubroutinize = True
    font = TTFont(io.BytesIO(raw), lazy=True)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    buffer = io.BytesIO()
    font.flavor = "woff2"
    font.save(buffer)
    font.close()
    data = buffer.getvalue()

    _subset_memo[key] = data
    try:  # a read-only or full cache dir must not break rendering
        _SUBSET_CACHE.mkdir(parents=True, exist_ok=True)
        scratch = cached.with_name(cached.name + ".tmp")
        scratch.write_bytes(data)
        scratch.replace(cached)
    except OSError:
        pass
    return data


# Patching one face takes ~0.7s, and it is pure function of the file's bytes, so it
# is keyed by content hash: change the brand font and the key changes with it. That
# matters more than speed — a cache keyed by path or mtime is exactly the "drifts
# from the source font, and nobody can see the moment it drifts" failure the
# sales-kit .gitignore warns about.
_CASE_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "brainhub" / "fonts"
_case_memo: dict[str, bytes] = {}


def _remap_case_punctuation(raw: bytes) -> bytes | None:
    """Remap PUA-only ``.case`` punctuation twins onto their real codepoints.

    Inter ships case-sensitive punctuation (dashes, ≥, brackets — forms drawn for
    all-caps settings) whose only cmap entry is a Private Use codepoint. Chrome picks
    them during layout, so the glyph on the page is the right shape and the document
    looks perfect to every human who opens it — but the character behind it is
    U+E0xx, and text extraction gets garbage. ``doc-release`` has a gate for exactly
    this: PUA means *printed but unreadable*, which is not the same as *not printed*.

    Touches the cmap only. Outlines, advance widths and glyph order are untouched, so
    nothing reflows. Deliberately does NOT do the tnum/tabular-figure half of
    sales-kit's ``build_readable_face``: brainhub never asks for tabular figures, and
    baking them in would widen every digit by 59% — curing a disease it does not have.

    Returns None when the face should be shipped unchanged.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:  # pragma: no cover - depends on the install
        return None

    in_pua = lambda cp: 0xE000 <= cp <= 0xF8FF  # noqa: E731
    font = TTFont(io.BytesIO(raw))
    best = font.getBestCmap()

    reachable_by: dict[str, list[int]] = {}
    for codepoint, glyph in best.items():
        reachable_by.setdefault(glyph, []).append(codepoint)

    # A .case twin is a trap only when PUA is the *sole* way to reach it.
    orphans = {
        glyph: cps
        for glyph, cps in reachable_by.items()
        if glyph.endswith(".case") and cps and all(in_pua(cp) for cp in cps)
    }
    redirect = {
        codepoint: glyph + ".case"
        for codepoint, glyph in best.items()
        if not in_pua(codepoint) and (glyph + ".case") in orphans
    }
    if not redirect:
        # A white-label face pointed at by BRAINHUB_BRAND_FONTS may simply not have
        # this trap. That is not an error here (it is in sales-kit's build, which
        # ships one known font); embed it as it came.
        font.close()
        return None
    if any(0x30 <= codepoint <= 0x39 for codepoint in redirect):
        # Digits must never move: that is the tnum failure mode, and a silently
        # 59%-wider digit is worse than the PUA we came to fix. Ship the original.
        font.close()
        return None

    drop = {cp for glyph in redirect.values() for cp in orphans[glyph]}
    for table in font["cmap"].tables:
        for codepoint in list(table.cmap):
            if codepoint in redirect:
                table.cmap[codepoint] = redirect[codepoint]
            elif codepoint in drop:
                del table.cmap[codepoint]

    buffer = io.BytesIO()
    font.flavor = "woff2"
    font.save(buffer)
    font.close()
    return buffer.getvalue()


def _case_only_face(font_path: Path) -> bytes:
    """The face as it should be embedded: cmap-repaired, cached, never fatal."""
    raw = font_path.read_bytes()
    key = hashlib.sha256(raw).hexdigest()
    if key in _case_memo:
        return _case_memo[key]

    cached = _CASE_CACHE / f"{key}.woff2"
    try:
        if cached.is_file():
            data = cached.read_bytes()
            _case_memo[key] = data
            return data
    except OSError:
        pass

    data = _remap_case_punctuation(raw) or raw
    _case_memo[key] = data
    try:  # a read-only or full cache dir must not break rendering
        _CASE_CACHE.mkdir(parents=True, exist_ok=True)
        scratch = cached.with_name(cached.name + ".tmp")
        scratch.write_bytes(data)
        scratch.replace(cached)
    except OSError:
        pass
    return data


def has_cjk(text: str) -> bool:
    """Whether this text needs a CJK face to render its own characters."""
    return any(ord(char) > 0x2E7F for char in text)


def _vendored_cjk_woff2() -> bytes | None:
    """The CJK face that ships with BrainHub, already subset — no fontTools needed.

    This exists so a CJK face is never a matter of what the rendering machine
    happens to have installed. See ``scripts/build_cjk_subset.py`` for what it
    covers and why it is vendored rather than taken from a brand directory.
    """
    try:
        return (_VENDOR_DIR / VENDORED_CJK_FACE).read_bytes()
    except OSError:
        return None


def _uncovered_cjk(face: bytes, used: str) -> list[str]:
    """CJK characters in ``used`` that this face cannot draw, in document order.

    Checked against the bytes actually embedded rather than against the source
    font, because subsetting is where coverage is decided. Returns empty when
    fontTools is unavailable — the check is diagnostic, and failing to run it must
    not stop a render that is otherwise fine.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:  # pragma: no cover - depends on the install
        return []
    try:
        font = TTFont(io.BytesIO(face))
        cmap = font.getBestCmap()
        font.close()
    except Exception:  # noqa: BLE001 - a diagnostic must never break rendering
        return []
    seen: dict[str, None] = {}
    for char in used:
        if has_cjk(char) and ord(char) not in cmap:
            seen.setdefault(char, None)
    return list(seen)


def _cjk_face(brand_face: Path | None, used: str) -> bytes | None:
    """The CJK bytes to embed, cheapest adequate source first.

    Order matters for document size, not just availability. Subsetting to the
    document's own characters is what keeps a contract around 8 KB of font instead
    of the whole 3.9 MB repertoire, so both real faces are subset when fontTools is
    there. Embedding the vendored face whole is the last resort: it makes every
    document ~5 MB, which is bad, and is still the right trade against shipping a
    PDF whose text layer cannot be searched.
    """
    vendored = _VENDOR_DIR / VENDORED_CJK_FACE

    # 1. The brand's own variable face, subset — best fidelity where it exists.
    if brand_face is not None and brand_face.is_file():
        subset = _subset_cjk(brand_face, used)
        if subset:
            return subset

    # 2. The vendored face, subset to this document. The normal path on any install.
    if vendored.is_file():
        subset = _subset_cjk(vendored, used)
        if subset:
            return subset

    # 3. The vendored face whole, when fontTools is absent. Correct but heavy.
    return _vendored_cjk_woff2()


def embedded_font_css(html_body: str, *, fonts_dir: Path = BRAND_FONTS) -> str:
    """Return a <style> block with the document's faces inlined as data: URIs.

    The Latin faces are brand assets and may legitimately be absent (a standalone
    install has none). **A CJK face is not optional**, because its absence is not a
    typography preference — it corrupts the output in two ways that both survive a
    page-by-page human review, and only surface on the reader's machine:

    * CJK bold stops working (``<strong>`` is still in the markup; the paper looks
      the same), and
    * the PDF text layer records whatever codepoint the *substituted* font's glyph
      was reachable by. Kangxi Radicals are the observed case — ``山`` U+5C71
      arriving as ``⼭`` U+2F2D. The glyph is right, so nobody sees it; the client
      just cannot search the document and copy-paste yields broken characters.

    So CJK content always gets a face: the brand's variable one when it is present
    and fontTools can subset it, otherwise the vendored subset, which needs no
    fontTools. :func:`cjk_readiness` reports when neither is possible, and callers
    that produce client-facing output refuse rather than ship the corruption.
    """
    used = "".join(sorted(set(_TAG.sub("", html_body)) | set("0123456789")))
    faces: list[str] = []

    inter_light = fonts_dir / "Inter-Light.woff2"
    inter_regular = fonts_dir / "Inter-Regular.woff2"
    if fonts_dir.is_dir() and inter_light.is_file() and inter_regular.is_file():
        faces.extend((
            f'@font-face {{ font-family:"Inter"; font-weight:300; font-display:swap;'
            f' src:url(data:font/woff2;base64,{_b64(_case_only_face(inter_light))}) format("woff2"); }}',
            f'@font-face {{ font-family:"Inter"; font-weight:400 700; font-display:swap;'
            f' src:url(data:font/woff2;base64,{_b64(_case_only_face(inter_regular))}) format("woff2"); }}',
        ))

    if has_cjk(used):
        brand_noto = fonts_dir / "NotoSansTC-var.ttf" if fonts_dir.is_dir() else None
        cjk = _cjk_face(brand_noto, used)
        if cjk:
            faces.append(
                f'@font-face {{ font-family:"Noto Sans TC"; font-weight:100 900; font-display:swap;'
                f' src:url(data:font/woff2;base64,{_b64(cjk)}) format("woff2-variations"); }}'
            )
            uncovered = _uncovered_cjk(cjk, used)
            if uncovered:
                # Embedding a face is not the same as covering the document. The
                # vendored face is the Big5 repertoire, so a name or place using a
                # rarer character (CJK Ext-A/B) still falls back for exactly those
                # characters — the same corruption as having no face at all, just
                # narrower. Name them, because the renderer's own machine has
                # system CJK fonts and will show them correctly.
                print(
                    "warning: the embedded CJK face does not cover "
                    f"{len(uncovered)} character(s) in this document: {''.join(uncovered)}. "
                    "Those will fall back to the reader's fonts, which breaks their "
                    "weight and can put a different codepoint in the PDF text layer. "
                    "Widen the subset (scripts/build_cjk_subset.py) or point "
                    "BRAINHUB_BRAND_FONTS at a face that covers them.",
                    file=sys.stderr,
                )
        else:
            # Nothing to embed and the document needs one. Loud, because the
            # machine rendering this has system CJK fonts and will look fine.
            print(
                f"warning: this document contains CJK but no CJK face could be embedded. "
                f"The vendored face {VENDORED_CJK_FACE} is missing from "
                f"{_VENDOR_DIR}, so the document will fall back to whatever fonts the "
                f"reader's machine has — which silently breaks CJK bold and the PDF "
                f"text layer. Do not send the output to anyone until this is fixed.",
                file=sys.stderr,
            )

    if not faces:
        return ""
    return "<style>" + "\n".join(faces) + "\nbody { font-weight: 300; }</style>"


def cjk_readiness() -> dict[str, object]:
    """Can this install embed a CJK face? Used to refuse before producing output.

    A boolean would be enough to gate on, but the reason is what lets whoever hits
    it fix it in one step instead of guessing which of the two causes applies.
    """
    vendored = (_VENDOR_DIR / VENDORED_CJK_FACE)
    brand = BRAND_FONTS / "NotoSansTC-var.ttf"
    try:
        from fontTools import subset  # noqa: F401
        fonttools = True
    except ImportError:
        fonttools = False
    return {
        "ready": vendored.is_file() or (brand.is_file() and fonttools),
        "vendored_face": str(vendored) if vendored.is_file() else None,
        "brand_face": str(brand) if brand.is_file() else None,
        "fonttools": fonttools,
        "remedy": (
            None
            if vendored.is_file() or (brand.is_file() and fonttools)
            else (
                f"restore {VENDORED_CJK_FACE} under {_VENDOR_DIR} "
                "(rebuild it with scripts/build_cjk_subset.py), or install fontTools "
                "so the brand face can be subset"
            )
        ),
    }
