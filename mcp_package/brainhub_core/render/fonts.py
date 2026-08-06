"""Embed the brand faces INTO the file, subset to the glyphs actually used.

Why this is not a styling concern (and so cannot be left to ``--css``):

A CSS ``font-family`` declaration is a *request*. On the machine that produced the
document the font is installed, so the request is granted and the page looks right
— forever, to its author. On the recipient's machine it is not installed, the
request silently falls back to a system face, and the document they see is not the
document you approved. **You can never see this bug on your own screen.** It is
only visible to the person you sent it to, which is the client.

So: for anything print/client-facing, the bytes ride along. A full Noto Sans TC is
~9 MB, which is why we subset to exactly the characters the document contains —
a typical contract needs a few hundred glyphs and lands around 500 KB total.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import sys
from pathlib import Path

# White-label: point BRAINHUB_BRAND_FONTS at a directory of .ttf/.woff2 files to
# embed your own faces. Absent fonts degrade gracefully (no embed, no error).
BRAND_FONTS = Path(
    os.environ.get("BRAINHUB_BRAND_FONTS", "/home/aworkr/aworkr/core/library/brand/assets/fonts")
)

_TAG = re.compile(r"<[^>]+>")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _subset_cjk(font_path: Path, text: str) -> bytes | None:
    """Subset the variable CJK face to `text`, as woff2. None if fontTools absent."""
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError:  # pragma: no cover - depends on the install
        return None

    options = subset.Options(flavor="woff2", layout_features=["*"], drop_tables=[])
    options.desubroutinize = True
    font = TTFont(str(font_path), lazy=True)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    buffer = io.BytesIO()
    font.flavor = "woff2"
    font.save(buffer)
    font.close()
    return buffer.getvalue()


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


def embedded_font_css(html_body: str, *, fonts_dir: Path = BRAND_FONTS) -> str:
    """Return a <style> block with the brand faces inlined as data: URIs.

    Returns "" when the brand fonts are not on this machine (standalone install) —
    the document still renders, it just cannot guarantee its own typography.
    """
    if not fonts_dir.is_dir():
        return ""

    inter_light = fonts_dir / "Inter-Light.woff2"
    inter_regular = fonts_dir / "Inter-Regular.woff2"
    noto = fonts_dir / "NotoSansTC-var.ttf"
    if not (inter_light.is_file() and inter_regular.is_file() and noto.is_file()):
        return ""

    faces = [
        f'@font-face {{ font-family:"Inter"; font-weight:300; font-display:swap;'
        f' src:url(data:font/woff2;base64,{_b64(_case_only_face(inter_light))}) format("woff2"); }}',
        f'@font-face {{ font-family:"Inter"; font-weight:400 700; font-display:swap;'
        f' src:url(data:font/woff2;base64,{_b64(_case_only_face(inter_regular))}) format("woff2"); }}',
    ]

    # Subset to the document's own characters (plus digits, which tables grow later).
    used = "".join(sorted(set(_TAG.sub("", html_body)) | set("0123456789")))
    cjk = _subset_cjk(noto, used)
    if cjk:
        faces.append(
            f'@font-face {{ font-family:"Noto Sans TC"; font-weight:100 900; font-display:swap;'
            f' src:url(data:font/woff2;base64,{_b64(cjk)}) format("woff2-variations"); }}'
        )
    elif any(ord(char) > 0x2E7F for char in used):
        # Degrading here is silent on the machine that renders — it has system
        # CJK fonts, so the page looks right — and only shows up on the reader's,
        # as tofu or PUA garbage. That reader is usually a client holding a PDF
        # we sent them. Say so loudly rather than ship a document whose
        # font-family is a request the file cannot honour.
        print(
            "warning: this document contains CJK but no CJK face could be embedded "
            "(fontTools not importable). It will fall back to whatever fonts the "
            "reader's machine happens to have. Install fontTools before rendering "
            "anything a client will open.",
            file=sys.stderr,
        )

    return "<style>" + "\n".join(faces) + "\nbody { font-weight: 300; }</style>"
