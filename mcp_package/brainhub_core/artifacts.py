"""Read-only artifact catalog helpers for a local BrainHub workspace."""
from __future__ import annotations

import json
from pathlib import Path

from .sid import SID_TYPE_ARTIFACT, generate_sid, normalize_sid

ARTIFACT_DIRECTORIES = {
    "report": "artifacts/reports",
    "html": "artifacts/html",
    "chart": "artifacts/charts",
    "export": "artifacts/exports",
}


def artifact_store_problem(workspace: Path, kind: str) -> str | None:
    """Why this workspace cannot store a ``kind`` artifact, or None if it can.

    Worth distinguishing, because the two causes need opposite responses and the
    old single message ("workspace is not initialized") sent readers of a perfectly
    good workspace off to re-initialize it: a wiki-only workspace — what
    ``brainhub_engine.py demo`` produces — is initialized, it just has no artifact
    store, whereas a bare path is usually a typo in the path itself.
    """
    workspace = Path(workspace).expanduser()
    relative = ARTIFACT_DIRECTORIES.get(kind)
    if relative is None:
        known = ", ".join(sorted(ARTIFACT_DIRECTORIES))
        return f"unknown artifact kind: {kind!r} (expected one of: {known})"
    if (workspace / relative).is_dir():
        return None
    if not workspace.is_dir():
        return f"no BrainHub workspace at {workspace} — check the path, or create one with: bh init {workspace}"
    if (workspace / "wiki").is_dir():
        return (
            f"{workspace} is a wiki-only workspace with no artifact store "
            f"(missing {relative}) — add one with: bh init {workspace}"
        )
    return f"{workspace} is not a BrainHub workspace — create one with: bh init {workspace}"


def artifact_catalog(workspace: Path, kind: str | None = None) -> dict[str, object]:
    """List artifact provenance records without exposing artifact contents."""
    workspace = workspace.resolve()
    selected_kinds = (kind,) if kind else tuple(ARTIFACT_DIRECTORIES)
    records: list[dict[str, object]] = []
    for selected_kind in selected_kinds:
        artifact_dir = workspace / ARTIFACT_DIRECTORIES[selected_kind]
        if not artifact_dir.is_dir():
            continue
        for metadata_path in sorted(artifact_dir.glob("*.meta.json")):
            artifact_name = metadata_path.name.removesuffix(".meta.json")
            artifact_path = artifact_dir / artifact_name
            if not artifact_path.is_file():
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(metadata, dict):
                continue
            record = dict(metadata)
            record["kind"] = selected_kind
            record["stored_path"] = artifact_path.relative_to(workspace).as_posix()
            records.append(record)
    records.sort(key=lambda record: str(record["stored_path"]))
    return {"count": len(records), "artifacts": records}


def existing_artifact_sids(workspace: Path) -> set[str]:
    """Collect every sid already assigned to an artifact record."""
    sids: set[str] = set()
    for record in artifact_catalog(workspace.resolve())["artifacts"]:
        assert isinstance(record, dict)
        sid = normalize_sid(record.get("sid"))
        if sid:
            sids.add(sid)
    return sids


def backfill_artifact_sids(workspace: Path) -> dict[str, object]:
    """One-time engine backfill: assign a sid to every artifact record lacking one."""
    workspace = workspace.resolve()
    existing = existing_artifact_sids(workspace)
    assigned: list[dict[str, str]] = []
    for selected_kind in ARTIFACT_DIRECTORIES:
        artifact_dir = workspace / ARTIFACT_DIRECTORIES[selected_kind]
        if not artifact_dir.is_dir():
            continue
        for metadata_path in sorted(artifact_dir.glob("*.meta.json")):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(metadata, dict) or normalize_sid(metadata.get("sid")):
                continue
            sid = generate_sid(SID_TYPE_ARTIFACT, existing)
            existing.add(sid)
            metadata["sid"] = sid
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            assigned.append({
                "artifact": metadata_path.name.removesuffix(".meta.json"),
                "sid": sid,
            })
    return {"assigned": assigned, "count": len(assigned)}


# ---------------------------------------------------------------------------
# Capture: turn an agent-produced page into a storable, standalone document.
# ---------------------------------------------------------------------------

_HEAD_ELEMENTS = frozenset({"title", "style", "meta", "link", "base"})
_VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})


def is_standalone_html(text: str) -> bool:
    """Whether this is already a whole document rather than a fragment."""
    head = text.lstrip()[:512].lower()
    return head.startswith("<!doctype") or "<html" in head


def _split_head_and_body(text: str) -> tuple[str, str]:
    """Partition a fragment's top-level nodes into head-eligible and body content.

    Hoisting matters: ``<title>`` in the body is non-conforming and browsers drop
    it, so a captured page would lose its name in the tab and in the viewer's
    listing. Done with the parser rather than by finding the last ``</style>``,
    because that heuristic silently mis-splits any page whose stylesheet is not
    the last thing before the content.
    """
    from html.parser import HTMLParser

    class Splitter(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=False)
            self.head: list[str] = []
            self.body: list[str] = []
            self._depth = 0
            self._target: list[str] | None = None

        def _sink(self) -> list[str]:
            # Inside an element, everything belongs wherever that element went.
            return self._target if self._target is not None else self.body

        def handle_starttag(self, tag: str, attrs) -> None:
            markup = self.get_starttag_text() or f"<{tag}>"
            if self._depth == 0:
                self._target = self.head if tag in _HEAD_ELEMENTS else self.body
            self._sink().append(markup)
            if tag not in _VOID_ELEMENTS:
                self._depth += 1
            elif self._depth == 0:
                self._target = None

        def handle_startendtag(self, tag: str, attrs) -> None:
            markup = self.get_starttag_text() or f"<{tag}/>"
            (self.head if (self._depth == 0 and tag in _HEAD_ELEMENTS) else self._sink()).append(markup)

        def handle_endtag(self, tag: str) -> None:
            if tag in _VOID_ELEMENTS:
                return
            self._sink().append(f"</{tag}>")
            self._depth = max(0, self._depth - 1)
            if self._depth == 0:
                self._target = None

        def handle_data(self, data: str) -> None:
            if self._depth == 0 and not data.strip():
                return  # whitespace between top-level nodes
            self._sink().append(data)

        def handle_comment(self, data: str) -> None:
            self._sink().append(f"<!--{data}-->")

        def handle_entityref(self, name: str) -> None:
            self._sink().append(f"&{name};")

        def handle_charref(self, name: str) -> None:
            self._sink().append(f"&#{name};")

    splitter = Splitter()
    splitter.feed(text)
    splitter.close()
    return "".join(splitter.head), "".join(splitter.body)


def ensure_standalone_html(text: str, *, title: str = "", lang: str = "zh-Hant-TW") -> str:
    """Return ``text`` as a complete HTML document, wrapping it only if needed.

    Agent-authored pages often arrive as fragments, because the surface that
    rendered them supplied the document shell. A stored artifact has no such
    shell: it is opened straight from disk and served as-is, and without a doctype
    the browser falls back to quirks mode, which changes the box model out from
    under the page's layout.
    """
    if is_standalone_html(text):
        return text
    head, body = _split_head_and_body(text)
    if title and "<title" not in head.lower():
        head = f"<title>{title}</title>" + head
    return (
        "<!doctype html>\n"
        f'<html lang="{lang}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{head}\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )
