r"""CJK-aware text handling — the SSOT for every subsystem that touches words.

This module exists because the same bug shipped three times in three places: text
normalization that whitelists ASCII (``[^a-z0-9]``) DELETES Chinese, and word
rules that assume spaces (``\W+`` splits, ``len >= 3`` filters) collapse a whole
Chinese sentence into one meaningless token. Every failure was silent — empty
sets, zero results, never an exception.

If you are about to write a regex over user text, import from here instead.
"""
from __future__ import annotations

import re
import unicodedata


# Scripts written WITHOUT spaces between words: Hiragana/Katakana, Bopomofo, Han
# (Ext-A, Unified, Compatibility, and the astral Ext-B..F planes — 𠮷 is a real
# surname character). A whole phrase in these arrives as ONE token, so these are
# the scripts that need bigram decomposition.
# ⚠ Hangul is deliberately absent: Korean puts spaces between words, so it
# tokenizes like English. It still has to SURVIVE normalization — it used to be
# deleted outright — which is handled by keeping every unicode letter below.
_NO_SPACE = "぀-ヿ㄀-ㄯ㐀-䶿一-鿿豈-﫿\U00020000-\U0002fa1f"
_NO_SPACE_SCRIPT = re.compile(f"[{_NO_SPACE}]")
_NO_SPACE_RUN = re.compile(f"[{_NO_SPACE}]+")



def _token_ok(word: str) -> bool:
    """Minimum useful token length. 3 suits English stopword-ish noise, but most
    Chinese words are exactly 2 characters (保存 / 憑證 / 時效) — a flat >=3 rule
    silently drops nearly every Chinese term. Keyed on is-it-ASCII rather than on
    a list of scripts, so Japanese/Korean/Greek don't each need to be remembered.
    """
    if not word:
        return False
    return len(word) >= 3 if word.isascii() else len(word) >= 2


def normalized_search_text(value: object) -> str:
    """Fold width and punctuation differences so natural queries match the text.

    Two rules, both learned the hard way:

    1. **NFKC first.** Chinese/Japanese IMEs emit full-width forms (Ｅｘｃｅｌ,
       １２３, half-width ｶﾅ). Unfolded, "Ｅｘｃｅｌ" and "excel" are simply
       different strings, and one of them finds nothing. (Same job as Lucene's
       CJKWidthFilter.)
    2. **Keep every unicode letter/digit — do NOT whitelist ranges.** The original
       rule was ``[^a-z0-9]+``, which erased Chinese outright. The first repair
       whitelisted the Han ranges we happened to think of, and that just moved the
       hole: kana, Hangul (한국어 -> ""), and astral CJK (𠮷 -> "") were all still
       being deleted. Enumerating scripts is how you KEEP this bug. ``[^\\w]``
       keeps them all, and it matches what the slug layer already does
       (wiki_publish.slugify), so queries and handles agree by construction.
    """
    text = unicodedata.normalize("NFKC", str(value)).lower()
    # `_` counts as a word char to `\w`, but it is a separator to us (and to the
    # slug layer), so snake_case keeps splitting the way it always has.
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def _expand_units(text: str) -> list[str]:
    """Split normalized text into matchable units, without a segmenter.

    Chinese is written without spaces, so the query an agent actually types
    ("客戶資料要怎麼隔離") arrives as ONE token and matches nothing unless that
    exact run appears verbatim. Overlapping bigrams recover word-ish units with
    no dictionary: 訊號驗證 -> 訊號 / 號驗 / 驗證. The cross-boundary ones (號驗)
    match nothing by construction, so callers score by HOW MANY units land and
    never require all of them. Same trick as Lucene's CJKBigramFilter.

    ASCII/Hangul chunks are left whole — bigramming them would match inside words.
    """
    units: list[str] = []
    for term in text.split():
        pos = 0
        for run in _NO_SPACE_RUN.finditer(term):
            head = term[pos:run.start()]
            if head:
                units.append(head)
            phrase = run.group()
            if len(phrase) <= 2:
                units.append(phrase)
            else:
                units.extend(phrase[i:i + 2] for i in range(len(phrase) - 1))
            pos = run.end()
        tail = term[pos:]
        if tail:
            units.append(tail)
    return units


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _query_units(q_normalized: str) -> list[str]:
    return _dedupe(_expand_units(q_normalized))


def fts_text(value: object) -> str:
    """Rewrite text for FTS5's ``unicode61`` tokenizer, which cannot segment CJK.

    Measured on sqlite 3.45.1: a whole Han run indexes as a SINGLE token, so
    ``客戶`` gets 0 hits inside ``客戶資料隔離模型``. Feeding overlapping bigrams
    into the index (and expanding the query the same way) makes the FTS
    pre-filter actually work for Chinese — no segmenter, no ICU build.

    ⚠ The ``trigram`` tokenizer is NOT the fix here, despite being the usual
    advice online: it needs >=3 characters, and most Chinese words are exactly 2
    (measured: ``資料`` -> 0 hits under trigram).
    """
    return " ".join(_expand_units(normalized_search_text(value)))


def search_words(value: object) -> set[str]:
    """The indexing vocabulary — and it MUST be the same vocabulary the query is
    decomposed into (`query_units`), or the lookup can never hit.

    ⚠ This used to split on ``\W+``, which stores an unsegmented Chinese run as a
    single term ("客戶資料要怎麼隔離"). The query side then asked for bigrams and
    missed every time — two tokenizers that disagree are worse than one bad one,
    because each looks correct on its own.
    """
    return {token for token in _expand_units(normalized_search_text(value)) if _token_ok(token)}


def _search_terms(value: object) -> list[str]:
    return [term for term in _query_units(normalized_search_text(value)) if _token_ok(term)]


# Public aliases. The underscore-prefixed names above predate this module being
# extracted out of search.py; other subsystems import these.
token_ok = _token_ok
expand_units = _expand_units
query_units = _query_units


def slugify(value: str, fallback: str = "page", max_len: int | None = None) -> str:
    """Unicode-aware slug — the ONE implementation.

    ⚠ Nine modules each carried their own ``[^a-z0-9]+`` copy of this, so every
    Chinese title collapsed to the fallback word: every artifact became
    "artifact.html" (the second one then failed with a misleading "already
    exists"), every Chinese memory slugged to "memory" (and looked like a
    duplicate of the previous one), every Chinese tag slugged to "" and vanished.
    Import this instead of writing a tenth copy.
    """
    lowered = unicodedata.normalize("NFKC", str(value)).lower()
    slug = re.sub(r"[^\w]+", "-", lowered, flags=re.UNICODE).replace("_", "-").strip("-")
    if max_len is not None:
        slug = slug[:max_len].strip("-")
    return slug or fallback


def short_date(value: object) -> str:
    """`2026-07-21T19:14:10.232791+00:00` -> `2026-07-21`, for anything a human reads.

    It lives here, next to the other text rules, because the first version lived
    in web_home and the page view kept printing the full stamp — the fix reached
    the one screen where the problem was noticed and not the 271 pages where it
    actually showed (2026-07-22). A full ISO stamp wraps to a second line on a
    phone and pushes aside the title it annotates.

    Machine-facing output (JSON APIs, snapshots) deliberately keeps the full
    precision and must NOT call this.
    """
    text = str(value or "").strip()
    return text[:10] if len(text) > 10 and text[4] == "-" and text[7] == "-" else text
