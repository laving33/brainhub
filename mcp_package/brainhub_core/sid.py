"""Short stable IDs (sid) for BrainHub objects.

A sid is 6 characters: 1 type char + 4 random Crockford Base32 chars + 1
Crockford mod-37 check symbol computed over the first 5 chars. Type codes:
``W`` = wiki document page, ``A`` = stored artifact, ``R`` = raw source file,
``D`` = decision board batch (other letters reserved).

The engine owns sid assignment (publish/backfill) and guarantees uniqueness by
regenerating on collision. Sids live in page frontmatter (``sid:``), artifact
``*.meta.json`` sidecars, and the raw registry (``raw/.sids.json``), and resolve
wherever aliases resolve ([[sid]] wikilinks, bh_read/bh_link handles, and the
viewer's ``/<kind>/<sid>/<title>`` URLs).
"""
from __future__ import annotations

import secrets
from collections.abc import Collection


CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CHECK_ALPHABET = CROCKFORD32 + "*~$=U"
SID_TYPE_DOCUMENT = "W"
SID_TYPE_ARTIFACT = "A"
SID_TYPE_RAW = "R"
SID_TYPE_DECISION = "D"
SID_TYPES = (SID_TYPE_DOCUMENT, SID_TYPE_ARTIFACT, SID_TYPE_RAW, SID_TYPE_DECISION)
SID_LENGTH = 6
_DECODE = {char: index for index, char in enumerate(CROCKFORD32)}
# Crockford decoding folds easily-confused letters into their lookalike digits.
_DECODE.update({"I": 1, "L": 1, "O": 0})


def check_symbol(prefix: str) -> str:
    """Crockford mod-37 check symbol for a Base32 prefix (case-insensitive)."""
    value = 0
    for char in prefix.upper():
        value = value * 32 + _DECODE[char]
    return CHECK_ALPHABET[value % 37]


def normalize_sid(value: object) -> str:
    """Canonical uppercase sid, or "" when the value is not a valid sid.

    Accepts lowercase input and the Crockford confusables I/L (-> 1) and
    O (-> 0) in the random part; the check symbol must verify.
    """
    text = str(value or "").strip().upper()
    if len(text) != SID_LENGTH or text[0] not in SID_TYPES:
        return ""
    body = ""
    for char in text[1:5]:
        if char not in _DECODE:
            return ""
        body += CROCKFORD32[_DECODE[char]]
    prefix = text[0] + body
    if check_symbol(prefix) != text[5]:
        return ""
    return prefix + text[5]


def is_sid(value: object) -> bool:
    """Whether the value is a well-formed sid with a valid check symbol."""
    return bool(normalize_sid(value))


def generate_sid(type_code: str, existing: Collection[str] = ()) -> str:
    """Return a fresh sid of the given type, avoiding every sid in ``existing``."""
    if type_code not in SID_TYPES:
        raise ValueError(f"unknown sid type code: {type_code!r}")
    taken = {normalize_sid(sid) for sid in existing}
    while True:
        prefix = type_code + "".join(secrets.choice(CROCKFORD32) for _ in range(4))
        sid = prefix + check_symbol(prefix)
        # Crockford's check alphabet ends in *~$=U, so roughly one prefix in ten
        # yields a sid that is awkward in a URL and outside the 0-9A-Z set sids
        # are supposed to use. Re-roll instead of changing check_symbol, which
        # would invalidate every sid already issued.
        if not sid.isalnum():
            continue
        if sid not in taken:
            return sid
