"""Canonical URLs for addressable BrainHub objects.

Every addressable object carries a sid, and exactly one URL shape addresses it::

    /<kind>/<SID>/<title>

Only the sid is load-bearing. The title segment is decoration for humans, so a
stale, renamed, or plain wrong title still lands on the right object and gets
redirected to the current title. Legacy shapes (``/page/<title>`` and
``/artifact/<subdir>/<file>``) stay resolvable and redirect here, which is how
old links written into memories, worklogs, and CLAUDE.md files keep working
while everything published from now on carries a sid.

This module is deliberately pure: it builds and parses paths, and knows nothing
about which objects exist. The server owns resolution because it owns the
indexes.
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from .sid import SID_TYPE_ARTIFACT, SID_TYPE_DOCUMENT, SID_TYPE_RAW, normalize_sid

KIND_PAGE = "page"
KIND_ARTIFACT = "artifact"
KIND_RAW = "raw"

# One table, both directions — adding an addressable kind means adding a sid
# type char in sid.py and one entry here, not a new URL shape.
KIND_BY_SID_TYPE = {
    SID_TYPE_DOCUMENT: KIND_PAGE,
    SID_TYPE_ARTIFACT: KIND_ARTIFACT,
    SID_TYPE_RAW: KIND_RAW,
}
SID_TYPE_BY_KIND = {kind: sid_type for sid_type, kind in KIND_BY_SID_TYPE.items()}
ADDRESSABLE_KINDS = tuple(SID_TYPE_BY_KIND)


@dataclass(frozen=True)
class Reference:
    """What a request path is asking for.

    ``sid`` is empty for legacy shapes; ``remainder`` is whatever followed the
    kind prefix (the title segment for sid URLs, the old locator otherwise).
    """

    kind: str
    sid: str
    remainder: str

    @property
    def is_legacy(self) -> bool:
        return not self.sid


def kind_for_sid(sid: object) -> str:
    """The kind a sid addresses, or "" when it is not a valid sid."""
    normalized = normalize_sid(sid)
    if not normalized:
        return ""
    return KIND_BY_SID_TYPE.get(normalized[0], "")


def canonical_path(kind: str, sid: str, title: str = "") -> str:
    """Build ``/<kind>/<SID>/<title>``; the title segment is optional."""
    normalized = normalize_sid(sid)
    if not normalized or kind not in ADDRESSABLE_KINDS:
        raise ValueError(f"not an addressable object: kind={kind!r} sid={sid!r}")
    base = f"/{kind}/{normalized}"
    title = str(title or "").strip()
    if not title:
        return base
    return base + "/" + urllib.parse.quote(title, safe="")


def legacy_path(kind: str, locator: str) -> str:
    """Build the pre-sid URL for objects that have no sid yet."""
    if kind not in ADDRESSABLE_KINDS:
        raise ValueError(f"not an addressable kind: {kind!r}")
    # Artifacts and raw files are addressed by a multi-segment path in their
    # legacy form (<subdir>/<file>); a page's legacy locator is a single title.
    safe = "" if kind == KIND_PAGE else "/"
    return f"/{kind}/" + urllib.parse.quote(str(locator or "").strip(), safe=safe)


def parse_path(path: str) -> Reference | None:
    """Split a request path into kind + sid + remainder, or None if unaddressed.

    ``/page/W8XRAN/anything`` -> sid form. ``/page/some-title`` and
    ``/artifact/charts/x.html`` -> legacy form (sid empty). A first segment that
    looks like a sid but fails its check symbol is treated as a legacy locator,
    not silently accepted.
    """
    segments = [segment for segment in str(path or "").split("/") if segment]
    if len(segments) < 2 or segments[0] not in ADDRESSABLE_KINDS:
        return None
    kind = segments[0]
    sid = normalize_sid(urllib.parse.unquote(segments[1]))
    if sid:
        remainder = "/".join(segments[2:])
        return Reference(kind=kind, sid=sid, remainder=urllib.parse.unquote(remainder))
    return Reference(kind=kind, sid="", remainder=urllib.parse.unquote("/".join(segments[1:])))


def with_query(path: str, query: str) -> str:
    """Re-attach a query string to a redirect target (``?format=pdf`` etc.)."""
    return f"{path}?{query}" if query else path
