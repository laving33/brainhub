#!/usr/bin/env python3
"""Build the vendored CJK face that ships with BrainHub.

Why BrainHub vendors a CJK font at all — the most expensive kind of silent bug
we have, twice over:

The print pipeline needs a CJK face to embed, and it used to take one from the
brand asset directory on the machine that happened to render. That directory is
not in the distributed package, so on **any other install** there was no CJK face
to embed and every Chinese document fell back to whatever fonts the reader's
machine had. Two consequences, both of which pass a page-by-page human review:

* CJK bold silently stops working (``<strong>`` is still there; the paper looks
  the same).
* The PDF *text layer* records whatever codepoint the substituted font's glyph was
  reachable by — in the reported case Kangxi Radicals (``山`` U+5C71 arriving as
  ``⼭`` U+2F2D). The glyph on the page is correct, so nobody sees it, but the
  client cannot search the document and copy-paste gives broken characters.

A vendored subset removes the dependency on luck: whoever installs BrainHub has a
CJK face, so the renderer never has to fall back.

The repertoire comes from Python's own ``big5`` codec rather than a hand-kept
character list, because a hand-kept list is exactly what silently misses the rare
character in a client's name — and a missing character looks fine on the machine
that rendered it, which has system CJK fonts to fall back on.

Usage (only needed when refreshing the face):

    python3 scripts/build_cjk_subset.py path/to/NotoSansCJKtc-VF.otf
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "mcp_package" / "brainhub_core" / "vendor"
OUTPUT_NAME = "NotoSansCJKtc-subset.woff2"

# Han beyond Big5. Requested as ranges and silently narrowed to what the source
# face actually has. Noto Sans CJK TC carries 99.8% of Ext-A but only ~4.9% of
# Ext-B, so this takes what is there without pretending to complete either block —
# rare given names and place names are the reason it is worth doing at all. (Noto
# Sans *TC*, which this used to build from, had only 8.7% of Ext-A.)
HAN_RANGES = (
    (0x3400, 0x4DBF),    # CJK Ext-A
    (0x4E00, 0x9FFF),    # CJK unified (superset of Big5's han, plus what Big5 lacks)
    (0x20000, 0x2A6DF),  # CJK Ext-B
    (0xF900, 0xFAFF),    # CJK compatibility ideographs
)

# U+2F00–2FDF (Kangxi Radicals) is deliberately EXCLUDED, and must stay that way.
#
# Noto Sans CJK shares one glyph between a radical and its han character, naming it
# after the radical: 山 U+5C71 and ⼭ U+2F2D both map to the glyph `uni2F2D`. When a
# PDF's text layer is built by reverse-mapping glyphs to codepoints, a shared glyph
# is ambiguous and the lower codepoint wins — so including the radical block makes
# 山 extract as ⼭. That is the exact corruption this file exists to prevent, and it
# would hit 207 characters including 一 U+4E00. Excluding the block leaves each
# glyph reachable only by its han codepoint, which is unambiguous.
# `_assert_no_radical_ambiguity` enforces this; do not "complete the coverage" here.
KANGXI_RADICALS = (0x2F00, 0x2FDF)

# Codepoints outside Big5 that a Traditional Chinese document still needs: ASCII,
# the Latin-1 punctuation range, CJK punctuation, fullwidth forms, and the few
# marks that turn up in prices and ranges.
EXTRA_RANGES = (
    (0x0020, 0x007E),  # ASCII
    (0x00A0, 0x00FF),  # Latin-1 supplement (©, °, ±, ×, ÷)
    (0x2010, 0x203B),  # dashes, quotes, ellipsis, dagger
    (0x2044, 0x2044),  # fraction slash
    (0x20A0, 0x20BF),  # currency symbols (NT$, €, ¥)
    (0x2100, 0x214F),  # letterlike (№, ™)
    (0x2190, 0x21FF),  # arrows
    (0x2200, 0x22FF),  # maths (≥, ≤, ≠, ∞)
    (0x2460, 0x24FF),  # enclosed alphanumerics
    (0x25A0, 0x25FF),  # geometric shapes (bullets in tables)
    (0x2600, 0x26FF),  # misc symbols
    (0x3000, 0x303F),  # CJK punctuation（。、「」）
    (0xFE30, 0xFE4F),  # CJK compatibility forms (vertical punctuation)
    (0xFF00, 0xFFEF),  # fullwidth forms
)


def big5_repertoire() -> set[str]:
    """Every character the Big5 codec can decode: level 1 + level 2 + symbols."""
    chars: set[str] = set()
    for lead in range(0xA1, 0xFA):
        for trail in list(range(0x40, 0x7F)) + list(range(0xA1, 0xFF)):
            try:
                chars.add(bytes((lead, trail)).decode("big5"))
            except UnicodeDecodeError:
                continue
    return chars


def extra_repertoire() -> set[str]:
    return {chr(cp) for start, end in EXTRA_RANGES for cp in range(start, end + 1)}


def han_beyond_big5(cmap: dict[int, str]) -> set[str]:
    """Han from HAN_RANGES that the source face can actually draw."""
    return {
        chr(cp)
        for start, end in HAN_RANGES
        for cp in range(start, end + 1)
        if cp in cmap
    }


def _assert_no_radical_ambiguity(cmap: dict[int, str], wanted: set[str]) -> list[str]:
    """Find requested characters whose glyph a Kangxi Radical would out-rank.

    The build must refuse rather than produce a face where reverse-mapping a glyph
    yields a radical instead of the han character — see KANGXI_RADICALS for why the
    block is excluded and what including it did.
    """
    lo, hi = KANGXI_RADICALS
    reachable: dict[str, list[int]] = {}
    for char in wanted:
        glyph = cmap.get(ord(char))
        if glyph:
            reachable.setdefault(glyph, []).append(ord(char))
    return [
        glyph
        for glyph, codepoints in reachable.items()
        if lo <= min(codepoints) <= hi and len(codepoints) > 1
    ]


def build(source: Path, output: Path) -> int:
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError:
        print(
            "fontTools is required to build the subset: pip install fonttools brotli",
            file=sys.stderr,
        )
        return 1

    probe = TTFont(str(source), lazy=True)
    source_cmap = probe.getBestCmap()
    probe.close()

    big5 = big5_repertoire()
    beyond = han_beyond_big5(source_cmap)
    chars = big5 | beyond | extra_repertoire()

    ambiguous = _assert_no_radical_ambiguity(source_cmap, chars)
    if ambiguous:
        print(
            "refusing to build: these glyphs would reverse-map to a Kangxi Radical "
            f"instead of their han character: {ambiguous[:10]}. "
            "The radical block must not be in the requested repertoire.",
            file=sys.stderr,
        )
        return 1

    text = "".join(sorted(chars))

    options = subset.Options(flavor="woff2")
    # Keep the weight axis: the shell asks for `font-weight: 100 900`, and an
    # instanced single-weight face would make CJK bold silently stop working —
    # one half of the bug this file exists to prevent.
    options.retain_gids = False
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    options.drop_tables = []

    font = TTFont(str(source), lazy=True)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    output.parent.mkdir(parents=True, exist_ok=True)
    font.flavor = "woff2"
    font.save(str(output))
    font.close()

    kept = TTFont(str(output))
    cmap = kept.getBestCmap()
    variable = "fvar" in kept
    kept.close()

    print(f"  source      : {source.name} ({source.stat().st_size / 1e6:.1f} MB)")
    print(f"  Big5        : {len(big5)} characters")
    print(f"  beyond Big5 : {len(beyond)} characters (Ext-A/Ext-B/compat present in source)")
    print(f"  requested   : {len(chars)} characters")
    print(f"  in cmap     : {len(cmap)} codepoints")
    print(f"  variable    : {'yes (wght axis kept)' if variable else 'NO — bold would break'}")
    print(f"  output      : {output} ({output.stat().st_size / 1e6:.1f} MB)")
    return 0 if variable else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Noto Sans CJK TC variable font (.otf/.ttf)")
    parser.add_argument("--output", type=Path, default=VENDOR / OUTPUT_NAME)
    args = parser.parse_args()
    if not args.source.is_file():
        print(f"source font not found: {args.source}", file=sys.stderr)
        return 1
    return build(args.source, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
