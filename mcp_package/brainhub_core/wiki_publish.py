"""Wiki DOCUMENT layer: publish / read / search / link source-backed pages.

This module is the wiki *document* surface that coexists with the memory layer.
It is built ON TOP OF the existing BrainHub page store — it does NOT introduce a
parallel store:

* pages are Markdown files under ``wiki/documents/<handle>.md`` written with the
  same :func:`atomic_write_text` primitive the memory/seed writers use;
* indexes are regenerated with the same :func:`rebuild_index` +
  ``_backlinks.json`` rebuild the project seeder uses
  (see ``project_seed._rebuild_graph_indexes``);
* search reuses :func:`search.search_pages` over :func:`wiki.build_wiki_cache`;
* backlinks reuse the shared ``[[wikilink]]`` graph.

Identity / update-in-place
--------------------------
A document's **handle** is the slug of its title. Re-publishing the same title
resolves to the same handle and UPDATES the page in place (it does not create a
``title-2`` copy). This deliberately avoids the "rename = new copy" failure
mode. Links added later via :func:`link_documents` are merged back in on
re-publish so a republish never silently drops the page's outbound links.

The memory layer (``write_memory_page`` and friends) is untouched; nothing here
imports it.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifacts import artifact_catalog
from .files import atomic_write_json, atomic_write_text
from .frontmatter import FRONTMATTER_RE, frontmatter_string, parse_frontmatter, yaml_list
from .log import append_log
from .sid import SID_TYPE_DOCUMENT, generate_sid, normalize_sid
from .search import close_wiki_cache, search_pages
from .wiki import (
    WIKILINK_RE,
    build_backlinks_from_cache,
    build_wiki_cache,
    load_backlinks_index,
    rebuild_index,
)

DOCUMENTS_DIR = "documents"
DOCUMENT_TYPE = "document"


def slugify(value: str, fallback: str = "document") -> str:
    """Unicode-aware slug: keeps CJK/letters/digits, other runs collapse to ``-``.

    The fleet publishes CJK-titled documents, so an ASCII-only slug (as the
    memory layer uses) is data loss here: distinct titles like ``brainhub 架構``
    and ``brainhub 部署`` would both degenerate to ``brainhub`` and silently
    overwrite. We keep unicode word characters so distinct titles get distinct,
    human-readable handles. ``_`` is normalized to ``-``; empty -> ``fallback``.
    """
    lowered = str(value).lower()
    slug = re.sub(r"[^\w]+", "-", lowered, flags=re.UNICODE).replace("_", "-")
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or fallback


def normalize_handle(handle: str) -> str:
    """Accept a title, a bare handle, ``documents/x`` or ``x.md`` -> stable slug."""
    text = str(handle or "").strip()
    text = text.removesuffix(".md")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return slugify(text)


def wiki_dir_for(workspace: Path) -> Path:
    return workspace.expanduser().resolve() / "wiki"


def document_path(wiki_dir: Path, handle: str) -> Path:
    return wiki_dir / DOCUMENTS_DIR / f"{handle}.md"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _rebuild_graph_indexes(wiki_dir: Path) -> set[str]:
    """Regenerate wiki/index.md and wiki/_backlinks.json (seeder's approach).

    Returns the known page stems + aliases so callers can flag dead wikilinks.
    """
    rebuild_index(wiki_dir)
    cache = build_wiki_cache(wiki_dir, use_persistent_cache=False)
    try:
        backlinks = build_backlinks_from_cache(cache, body_only=False)
        known = {str(key).lower() for key in cache.get("page_index", {})}
        known.update(str(page.get("name") or "").lower() for page in cache.get("pages", []))
    finally:
        close_wiki_cache(cache)
    atomic_write_json(wiki_dir / "_backlinks.json", backlinks)
    return known


SID_LINE_RE = re.compile(r"(?m)^sid:\s*\"?([0-9A-Za-z*~$=]{6})\"?\s*$")


def _existing_page_sids(wiki_dir: Path) -> set[str]:
    """Collect every sid already assigned in this wiki (for uniqueness)."""
    sids: set[str] = set()
    if not wiki_dir.is_dir():
        return sids
    for path in wiki_dir.rglob("*.md"):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = FRONTMATTER_RE.match(text)
        if not match:
            continue
        found = SID_LINE_RE.search(match.group(1))
        if found:
            normalized = normalize_sid(found.group(1))
            if normalized:
                sids.add(normalized)
    return sids


def _find_document_by_sid(wiki_dir: Path, sid: str) -> Path | None:
    """Resolve a document-page path by its sid (W type), or None."""
    documents_dir = wiki_dir / DOCUMENTS_DIR
    if not documents_dir.is_dir():
        return None
    for path in sorted(documents_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = FRONTMATTER_RE.match(text)
        if not match:
            continue
        found = SID_LINE_RE.search(match.group(1))
        if found and normalize_sid(found.group(1)) == sid:
            return path
    return None


def _existing_link_targets(wiki_dir: Path, handle: str) -> list[str]:
    """Return the ``[[wikilink]]`` targets already present in a document body."""
    path = document_path(wiki_dir, handle)
    if not path.exists():
        return []
    _, body = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    seen: list[str] = []
    for match in WIKILINK_RE.finditer(body):
        target = match.group(1).strip().lower()
        if target and target not in seen:
            seen.append(target)
    return seen


def _merge_link_targets(handle: str, *groups: list[str]) -> list[str]:
    """Slugify + dedupe link targets across groups, dropping self-links.

    A sid target keeps its exact (lowercased) form — slugify would strip a
    ``*~$=`` check symbol and break resolution.
    """
    merged: list[str] = []
    for group in groups:
        for raw in group or []:
            sid = normalize_sid(raw)
            target = sid.lower() if sid else normalize_handle(raw)
            if target and target != handle and target not in merged:
                merged.append(target)
    return merged


def _resolve_artifact_reference(workspace: Path, reference: str) -> dict[str, Any]:
    """Resolve a related-artifact reference against the workspace catalog.

    Fail-open: an unknown reference is still recorded (as ``resolved: False``) so
    a page can point at an artifact that has not been built yet, but a match
    upgrades the reference to the canonical ``stored_path``.
    """
    ref = str(reference or "").strip()
    if not ref:
        return {}
    catalog = artifact_catalog(workspace.expanduser().resolve())
    artifacts = catalog.get("artifacts", [])
    assert isinstance(artifacts, list)
    for record in artifacts:
        assert isinstance(record, dict)
        stored = str(record.get("stored_path") or "")
        if ref in (stored, Path(stored).name, Path(stored).stem):
            return {
                "reference": ref,
                "stored_path": stored,
                "kind": record.get("kind"),
                "resolved": True,
            }
    return {"reference": ref, "stored_path": ref, "kind": None, "resolved": False}


def normalize_document_tags(tags: list[str] | None) -> list[str]:
    """Stored tag list: 'document' + slugified tags (colon convention 'from:catalog' -> stored dash form 'from-catalog')."""
    tag_values = ["document"]
    for tag in tags or []:
        slug_tag = slugify(tag, fallback="")
        if slug_tag and slug_tag not in tag_values:
            tag_values.append(slug_tag)
    return tag_values


def build_document_markdown(
    title: str,
    body_markdown: str,
    *,
    handle: str,
    link_targets: list[str],
    artifact: dict[str, Any] | None,
    date_published: str,
    date_updated: str,
    agent: str,
    tags: list[str],
    sid: str = "",
) -> str:
    """Render a document page: frontmatter + body + Links + Provenance sections."""
    tag_values = normalize_document_tags(tags)

    clean_body = (body_markdown or "").strip()
    first_line = next((line.strip() for line in clean_body.splitlines() if line.strip()), title)
    # Bodies often open with their own "> **TLDR:** ..." blockquote; strip the
    # quote marker and any TLDR label so the excerpt never nests into
    # "> **TLDR:** > **TLDR:** ...".
    first_line = re.sub(r"^(?:>\s*)+", "", first_line)
    first_line = re.sub(r"^\*\*TLDR:?\*\*:?\s*", "", first_line, flags=re.IGNORECASE).strip()
    # Drop a leading Markdown heading marker (bodies that open with "# Title")
    # so the auto TLDR excerpt is plain text, not "> **TLDR:** # Title".
    first_line = re.sub(r"^#{1,6}\s+", "", first_line).strip() or title
    tldr = first_line if len(first_line) <= 180 else first_line[:177].rstrip() + "..."

    artifact_line = ""
    if artifact:
        artifact_line = f'related_artifact: "{frontmatter_string(artifact.get("stored_path") or "")}"\n'

    sid_line = f'sid: "{sid}"\n' if sid else ""
    frontmatter = (
        "---\n"
        "type: document\n"
        f'title: "{frontmatter_string(title)}"\n'
        f"handle: {handle}\n"
        f"{sid_line}"
        "status: active\n"
        f'date_published: "{date_published}"\n'
        f'date_updated: "{date_updated}"\n'
        f"{artifact_line}"
        f'published_by: "{frontmatter_string(agent)}"\n'
        f"tags: {yaml_list(tag_values)}\n"
        "---\n"
    )

    parts = [
        frontmatter,
        "",
        f"# {title}",
        "",
        f"> **TLDR:** {tldr}",
        "",
        clean_body,
        "",
    ]

    if link_targets:
        parts.append("## Links")
        parts.append("")
        parts.extend(f"- [[{target}]]" for target in link_targets)
        parts.append("")

    parts.append("## Provenance")
    parts.append("")
    parts.append(f"- Published via bh-publish by `{agent}`.")
    parts.append(f"- First published: {date_published}")
    parts.append(f"- Last updated: {date_updated}")
    if artifact:
        state = "resolved" if artifact.get("resolved") else "unresolved (not yet in artifact catalog)"
        parts.append(f"- Related artifact ({state}): `{artifact.get('stored_path')}`")
    parts.append("")

    return "\n".join(parts)


def publish_document(
    workspace: Path,
    title: str,
    body_markdown: str,
    *,
    links: list[str] | None = None,
    related_artifact: str | None = None,
    agent: str = "bh-publish",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Publish or UPDATE-IN-PLACE a wiki document page and refresh indexes."""
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("document title required")

    workspace = workspace.expanduser().resolve()
    wiki_dir = wiki_dir_for(workspace)
    if not wiki_dir.is_dir():
        raise ValueError(f"BrainHub workspace is not initialized: {workspace}")

    handle = slugify(clean_title)
    documents_dir = wiki_dir / DOCUMENTS_DIR
    documents_dir.mkdir(parents=True, exist_ok=True)
    path = document_path(wiki_dir, handle)

    updated = path.exists()
    prior_meta: dict[str, object] = {}
    if updated:
        prior_meta, _ = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))

    now = _now_iso()
    date_published = str(prior_meta.get("date_published") or now).strip() or now
    # A page keeps its sid across republishes; new pages get a fresh unique one.
    sid_value = normalize_sid(prior_meta.get("sid")) or generate_sid(
        SID_TYPE_DOCUMENT, _existing_page_sids(wiki_dir)
    )
    # Preserve links added since the last publish (e.g. via bh-link).
    link_targets = _merge_link_targets(handle, list(links or []), _existing_link_targets(wiki_dir, handle))
    # [[wikilinks]] written inline in the new body are part of the graph too;
    # report them so callers never re-add them with bh-link.
    body_link_targets = _merge_link_targets(
        handle,
        [match.group(1) for match in WIKILINK_RE.finditer(body_markdown or "")],
    )

    artifact = _resolve_artifact_reference(workspace, related_artifact) if related_artifact else None

    page = build_document_markdown(
        clean_title,
        body_markdown,
        handle=handle,
        link_targets=link_targets,
        artifact=artifact,
        date_published=date_published,
        date_updated=now,
        agent=agent,
        tags=list(tags or []),
        sid=sid_value,
    )
    atomic_write_text(path, page)
    known_pages = _rebuild_graph_indexes(wiki_dir)

    all_links = list(link_targets)
    for target in body_link_targets:
        if target not in all_links:
            all_links.append(target)
    # Dead targets do not fail the publish (the page may come later), but they
    # are surfaced so dead-wikilink batches get caught at the source.
    unresolved = [target for target in all_links if target not in known_pages]
    warnings = [
        f"unresolved wikilink: [[{target}]] — target page does not exist yet"
        for target in unresolved
    ]

    append_log(
        wiki_dir,
        now,
        "publish",
        clean_title,
        [
            f"{'Updated' if updated else 'Created'}: documents/{path.name}",
            f"Handle: {handle}",
            f"Links: {len(all_links)}",
            *([f"Unresolved links: {len(unresolved)}"] if unresolved else []),
            *([f"Artifact: {artifact.get('stored_path')}"] if artifact else []),
        ],
    )

    return {
        "published": True,
        "updated": updated,
        "created": not updated,
        "handle": handle,
        "sid": sid_value,
        "title": clean_title,
        "path": f"wiki/{DOCUMENTS_DIR}/{path.name}",
        "links": all_links,
        "tags": normalize_document_tags(list(tags or [])),
        "warnings": warnings,
        "unresolved_links": unresolved,
        "related_artifact": artifact.get("stored_path") if artifact else None,
        "date_published": date_published,
        "date_updated": now,
    }


_GENERATED_TAIL_LINE = re.compile(
    r"^(?:## (?:Links|Provenance)\s*|- \[\[[^\]]*\]\]\s*|"
    r"- (?:Published via|First published|Last updated|Related artifact).*|\s*)$"
)


def authored_body(title: str, body: str) -> str:
    """Strip what `compose_document_page` added, leaving what a human wrote.

    The composer wraps an authored body in a generated head (``# <title>`` plus
    a ``> **TLDR:**`` excerpt) and a generated tail (``## Links`` /
    ``## Provenance``). Reading a page back therefore returns engine output
    mixed with authored text, and publishing that straight back stacks another
    copy of both. It is not hypothetical: 38 pages had stacked heads and 19
    stacked tails when this was written, one at ten layers deep, and the
    documented remedy was an `awk` incantation every author had to remember —
    which only ever covered the tail (cospec, 2026-07-22).

    Stripping loops, so republishing an already-stacked page heals it.

    ⚠ Deliberately conservative at the tail: it cuts only when everything after
    the cut point matches generated shapes. Some pages carry real content below
    a ``## Links`` heading, and eating an author's text would be far worse than
    leaving one duplicate block behind.
    """
    lines = (body or "").strip("\n").split("\n")

    # Head: drop repeated generated blocks, which are always the *pair*
    # "# <title>" + "> **TLDR:** …" (see compose_document_page — it never emits
    # one without the other).
    #
    # 🔴 Only a pair whose heading is exactly this page's title is removed, and a
    # TLDR is never removed on its own. Authors write their own TLDR line as the
    # first line of a body, which sits directly under the generated one and is
    # indistinguishable by position. An earlier version of this stripped by
    # position and silently ate it, degrading the summary a little more on every
    # read-edit-publish round (cospec, 2026-07-22, caught on its own worklog).
    #
    # The cost of being strict is that a page whose title was later renamed keeps
    # its stale generated heads, because they no longer match. That is the right
    # side to err on: a duplicate block is visible and harmless, a deleted
    # sentence is neither.
    heading = f"# {title}".strip()

    def next_content(start):
        while start < len(lines) and not lines[start].strip():
            start += 1
        return start

    def is_tldr(index):
        return index < len(lines) and re.match(
            r"^>\s*\*\*TLDR:?\*\*", lines[index].strip(), re.IGNORECASE
        )

    # Exactly one pair is removed — never a loop.
    #
    # Publishing re-adds one head, so removing one is all it takes to stop the
    # stacking. Removing more is where the danger lives: once a page has been
    # stacked, the author's own summary ends up sitting in a later pair's TLDR
    # slot, structurally identical to a generated one, and no positional rule can
    # tell them apart. Two attempts to be cleverer here (shape matching, then
    # derivation heuristics) each ate authored text or broke another case.
    #
    # So an already-stacked page sheds one layer per round trip instead of
    # healing in one pass. That is the deliberate trade: slower cleanup in
    # exchange for never deleting a sentence a human wrote.
    index = next_content(0)
    if index < len(lines) and lines[index].strip() == heading:
        after_heading = next_content(index + 1)
        if is_tldr(after_heading):
            lines = lines[after_heading + 1:]

    # Tail: cut at the earliest heading whose remainder is entirely generated.
    for index, line in enumerate(lines):
        if line.strip() in ("## Links", "## Provenance") and all(
            _GENERATED_TAIL_LINE.match(rest) for rest in lines[index:]
        ):
            lines = lines[:index]
            break

    return "\n".join(lines).strip("\n")


def read_document(workspace: Path, handle: str, *, body_only: bool = False) -> dict[str, Any]:
    """Read a published document page back as markdown + parsed metadata.

    ``body_only`` drops the full-markdown + metadata duplication (large pages
    otherwise return the same text twice) and keeps just handle/title/path/
    body/links. Default behavior is unchanged.
    """
    workspace = workspace.expanduser().resolve()
    wiki_dir = wiki_dir_for(workspace)
    sid_input = normalize_sid(handle)
    if sid_input:
        sid_path = _find_document_by_sid(wiki_dir, sid_input)
        if sid_path is None:
            raise ValueError(f"document not found: {handle}")
        resolved = sid_path.stem
        path = sid_path
    else:
        resolved = normalize_handle(handle)
        path = document_path(wiki_dir, resolved)
        if not path.exists():
            raise ValueError(f"document not found: {handle}")

    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse_frontmatter(text)
    forward = []
    for match in WIKILINK_RE.finditer(body):
        target = match.group(1).strip().lower()
        if target and target not in forward:
            forward.append(target)

    result: dict[str, Any] = {
        "handle": resolved,
        "sid": normalize_sid(meta.get("sid")),
        "title": str(meta.get("title") or resolved),
        "path": f"wiki/{DOCUMENTS_DIR}/{path.name}",
        "body": body.strip(),
        "links": forward,
    }
    if body_only:
        # `--body-only` exists to be edited and published back, so it returns the
        # authored body only. Returning the rendered page here is what made every
        # read-edit-publish round trip stack another generated head and tail.
        result["body"] = authored_body(result["title"], body)
        result["body_only"] = True
        return result
    result.update({
        "markdown": text,
        "metadata": meta,
        "related_artifact": meta.get("related_artifact"),
    })
    return result


TAG_CONVENTION_PREFIXES = ("from", "domain", "project")


def normalize_tag(value: str) -> str:
    """Accept colon or dash convention ('from:catalog' / 'from-catalog') -> stored dash form."""
    return slugify(str(value or ""), fallback="")


def _extract_tag_filters(query: str) -> tuple[str, list[str], list[str]]:
    """Split a query into (free text, definite tag filters, dash-form candidates).

    ``tag:<value>`` and colon-convention tokens (``from:catalog`` /
    ``domain:lab`` / ``project:x``) are always tag filters. A bare dash token
    like ``from-catalog`` is only a *candidate*: the caller promotes it to a
    filter when the wiki actually has that tag, otherwise it stays search text
    (so a query like "domain-driven design" is not swallowed).
    """
    text_terms: list[str] = []
    filters: list[str] = []
    candidates: list[str] = []
    for token in str(query or "").split():
        lowered = token.lower()
        if lowered.startswith("tag:"):
            tag = normalize_tag(lowered[4:])
            if tag and tag not in filters:
                filters.append(tag)
            continue
        if any(lowered.startswith(f"{prefix}:") for prefix in TAG_CONVENTION_PREFIXES):
            tag = normalize_tag(lowered)
            if tag and tag not in filters:
                filters.append(tag)
            continue
        if any(lowered.startswith(f"{prefix}-") for prefix in TAG_CONVENTION_PREFIXES):
            candidates.append(lowered)
            continue
        text_terms.append(token)
    return " ".join(text_terms), filters, candidates


def search_documents(
    workspace: Path,
    query: str,
    *,
    limit: int = 20,
    documents_only: bool = False,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search wiki pages; each result carries a stable handle + snippet.

    Within one workspace this returns titles/handles for the wiki's own content.
    By default it searches ALL wiki pages (documents and other categories); pass
    ``documents_only`` to restrict to the document layer.

    Tag filtering: pass ``tags`` explicitly and/or embed tokens in the query —
    ``tag:<value>``, the colon convention ``from:catalog`` / ``domain:lab`` /
    ``project:x``, or the stored dash form ``from-catalog``. Colon and dash
    forms are equivalent (tags are stored slugified, i.e. dash form). All
    requested tags must match. Tags with no remaining free text return the
    most recently updated matching pages.
    """
    workspace = workspace.expanduser().resolve()
    wiki_dir = wiki_dir_for(workspace)
    if not wiki_dir.is_dir():
        return []

    text_query, tag_filters, tag_candidates = _extract_tag_filters(query)
    for raw in tags or []:
        tag = normalize_tag(raw)
        if tag and tag not in tag_filters:
            tag_filters.append(tag)

    bounded = max(1, int(limit))
    cache = build_wiki_cache(wiki_dir)
    try:
        if tag_candidates:
            known_tags = {
                normalize_tag(str(tag))
                for page in cache.get("pages", [])
                for tag in page.get("tags", [])
            }
            leftover: list[str] = []
            for candidate in tag_candidates:
                normalized = normalize_tag(candidate)
                if normalized in known_tags:
                    if normalized not in tag_filters:
                        tag_filters.append(normalized)
                else:
                    leftover.append(candidate)
            if leftover:
                text_query = " ".join(term for term in [text_query, *leftover] if term)

        if text_query:
            # With tag filters active, search wide first so the filter does not
            # starve the bounded result list.
            search_limit = max(bounded * 25, 200) if tag_filters else bounded
            matches = search_pages(text_query, cache, limit=search_limit)
        elif tag_filters:
            matches = [
                {**page, "score": 0, "snippet": str(page.get("tldr") or "")}
                for page in cache.get("pages", [])
            ]
            matches.sort(
                key=lambda page: (str(page.get("date_updated") or ""), str(page.get("title") or "").lower()),
                reverse=True,
            )
        else:
            matches = []
    finally:
        close_wiki_cache(cache)

    results: list[dict[str, Any]] = []
    for page in matches:
        category = str(page.get("category") or "")
        if documents_only and category != DOCUMENTS_DIR:
            continue
        if tag_filters:
            page_tags = {normalize_tag(str(tag)) for tag in page.get("tags", [])}
            if not all(tag in page_tags for tag in tag_filters):
                continue
        results.append(
            {
                "handle": str(page.get("name") or ""),
                "sid": str(page.get("sid") or ""),
                "title": str(page.get("title") or page.get("name") or ""),
                "category": category,
                "type": str(page.get("type") or ""),
                "tags": [str(tag) for tag in page.get("tags", [])],
                "path": str(page.get("path") or ""),
                "snippet": str(page.get("snippet") or ""),
                "score": page.get("score", 0),
                "is_document": category == DOCUMENTS_DIR,
            }
        )
        if len(results) >= bounded:
            break
    return results


def _page_exists(cache: dict[str, Any], stem: str) -> bool:
    page_index = cache.get("page_index")
    if isinstance(page_index, dict) and stem in page_index:
        return True
    for page in cache.get("pages", []):
        if str(page.get("name") or "").lower() == stem:
            return True
    return False


def link_documents(workspace: Path, from_handle: str, to_handle: str) -> dict[str, Any]:
    """Add a ``[[wikilink]]`` from a document to another existing wiki page.

    Only a *document* page is edited (the layer this module owns); memory and
    source pages are never mutated here. The target must already exist so no
    dead wikilink is introduced. Backlinks + index are rebuilt after the edit.
    """
    workspace = workspace.expanduser().resolve()
    wiki_dir = wiki_dir_for(workspace)

    # Both ends accept a handle, title, or 6-char sid; sids canonicalize to the
    # page's real handle so the written [[wikilink]] stays human-readable.
    from_sid = normalize_sid(from_handle)
    if from_sid:
        from_sid_path = _find_document_by_sid(wiki_dir, from_sid)
        if from_sid_path is None:
            raise ValueError(f"source document not found: {from_handle}")
        from_slug = from_sid_path.stem
    else:
        from_slug = normalize_handle(from_handle)

    to_sid = normalize_sid(to_handle)
    to_slug = normalize_handle(to_handle) if not to_sid else ""

    from_path = document_path(wiki_dir, from_slug)
    if not from_path.exists():
        raise ValueError(f"source document not found: {from_handle}")

    cache = build_wiki_cache(wiki_dir, use_persistent_cache=False)
    try:
        if to_sid:
            target_path = cache.get("page_index", {}).get(to_sid.lower())
            target_exists = target_path is not None
            if target_path is not None:
                to_slug = target_path.stem.lower()
        else:
            target_exists = _page_exists(cache, to_slug)
    finally:
        close_wiki_cache(cache)
    if not target_exists:
        raise ValueError(f"link target page not found: {to_handle} (would create a dead wikilink)")

    if from_slug == to_slug:
        raise ValueError("cannot link a document to itself")

    text = from_path.read_text(encoding="utf-8", errors="replace")
    match = FRONTMATTER_RE.match(text)
    header = text[: match.end()] if match else ""
    body = text[match.end():] if match else text

    already_linked = any(
        m.group(1).strip().lower() == to_slug for m in WIKILINK_RE.finditer(body)
    )
    added = False
    if not already_linked:
        link_line = f"- [[{to_slug}]]"
        section = re.search(r"^##\s+Links\s*$", body, flags=re.MULTILINE)
        if section:
            insert_at = section.end()
            body = body[:insert_at] + f"\n{link_line}" + body[insert_at:]
        else:
            body = body.rstrip() + f"\n\n## Links\n\n{link_line}\n"
        added = True
        atomic_write_text(from_path, header + body)
        # Log BEFORE rebuilding: the log line itself contains a [[wikilink]],
        # so rebuilding first would leave _backlinks.json permanently stale.
        append_log(
            wiki_dir,
            _now_iso(),
            "link",
            f"{from_slug} -> {to_slug}",
            [f"Added wikilink [[{to_slug}]] to documents/{from_path.name}"],
        )
        _rebuild_graph_indexes(wiki_dir)

    backlinks, _ = load_backlinks_index(wiki_dir / "_backlinks.json")
    inbound = backlinks.get("backlinks", {}).get(to_slug, [])

    return {
        "linked": True,
        "added": added,
        "already_linked": already_linked,
        "from_handle": from_slug,
        "to_handle": to_slug,
        "from_path": f"wiki/{DOCUMENTS_DIR}/{from_path.name}",
        "inbound_to_target": inbound,
    }


def backfill_document_sids(workspace: Path) -> dict[str, Any]:
    """One-time engine backfill: assign a sid to every document page lacking one.

    Only the frontmatter gains a ``sid:`` line (inserted before the closing
    fence); handle, title, body, and every other frontmatter line stay
    byte-identical. Indexes are rebuilt once at the end.
    """
    workspace = workspace.expanduser().resolve()
    wiki_dir = wiki_dir_for(workspace)
    if not wiki_dir.is_dir():
        raise ValueError(f"BrainHub workspace is not initialized: {workspace}")

    existing = _existing_page_sids(wiki_dir)
    assigned: list[dict[str, str]] = []
    documents_dir = wiki_dir / DOCUMENTS_DIR
    if documents_dir.is_dir():
        for path in sorted(documents_dir.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = FRONTMATTER_RE.match(text)
            if not match:
                continue
            meta, _body = parse_frontmatter(text)
            if normalize_sid(meta.get("sid")):
                continue
            sid_value = generate_sid(SID_TYPE_DOCUMENT, existing)
            existing.add(sid_value)
            header = match.group(0)
            fence_at = header.rfind("---")
            new_header = header[:fence_at] + f'sid: "{sid_value}"\n' + header[fence_at:]
            atomic_write_text(path, new_header + text[match.end():])
            assigned.append({"page": f"wiki/{DOCUMENTS_DIR}/{path.name}", "sid": sid_value})

    if assigned:
        _rebuild_graph_indexes(wiki_dir)
        append_log(
            wiki_dir,
            _now_iso(),
            "sid-backfill",
            f"{len(assigned)} document page(s)",
            [f"{item['sid']}: {item['page']}" for item in assigned],
        )
    return {"assigned": assigned, "count": len(assigned)}
