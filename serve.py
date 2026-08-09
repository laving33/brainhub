#!/usr/bin/env python3
"""BrainHub — local wiki viewer. python serve.py → http://127.0.0.1:3000"""
from __future__ import annotations

import errno
import html
import http.server
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from collections import Counter
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_BUNDLED_CORE = ROOT / "mcp_package"
if (_BUNDLED_CORE / "brainhub_core").exists():
    sys.path.insert(0, str(_BUNDLED_CORE))

from brainhub_core.memory import (
    add_capture_review_to_brief as _core_add_capture_review_to_brief,
    count_values as _core_count_values,
    is_active_memory as _core_is_active_memory,
    memory_action_hints as _core_memory_action_hints,
    memory_brief as _core_memory_brief,
    memory_explanation as _core_memory_explanation,
    memory_inbox as _core_memory_inbox,
    memory_profile as _core_memory_profile,
    memory_audit_report as _core_memory_audit_report,
    memory_audit_next_actions as _core_memory_audit_next_actions,
    memory_records as _core_memory_records,
    memory_review_issues as _core_memory_review_issues,
    memory_duplicate_candidates as _core_memory_duplicate_candidates,
    memory_visible_for_project as _core_memory_visible_for_project,
    mark_memory_reviewed as _core_mark_memory_reviewed,
    normalize_project as _core_normalize_project,
    propose_memories_from_text as _core_propose_memories_from_text,
    set_memory_status as _core_set_memory_status,
    update_memory_page as _core_update_memory_page,
    write_memory_page as _core_write_memory_page,
)
from brainhub_core.frontmatter import (
    parse_frontmatter as _parse_frontmatter,
)
from brainhub_core.ingest import (
    collect_ingest_status as _core_collect_ingest_status,
)
from brainhub_core.log import (
    append_log as _core_append_log,
    utc_timestamp as _core_utc_timestamp,
)
from brainhub_core.memory_log import (
    memory_log_payload as _core_memory_log_payload,
)
from brainhub_core.memory_wins import (
    memory_wins_payload as _core_memory_wins_payload,
)
from brainhub_core.markdown import (
    markdown_to_html as _core_markdown_to_html,
)
from brainhub_core.security import (
    clean_text_input as _clean_text_input,
)
from brainhub_core.query import (
    query_link as _core_query_link,
)
from brainhub_core.prompts import (
    starter_prompt_payload as _core_starter_prompt_payload,
)
from brainhub_core.mcp_connect import (
    supported_agents as _core_supported_agents,
)
from brainhub_core.validation import (
    validate_wiki as _core_validate_wiki,
)
from brainhub_core.doctor import (
    raw_source_refs as _core_raw_source_refs,
)
from brainhub_core.version import (
    BRAINHUB_VERSION,
)
from brainhub_core.mcp_verify import (
    set_bh_command_override as _core_set_bh_command_override,
)
from brainhub_core.web_assets import CSS  # noqa: F401 - kept as serve.CSS for tests and compatibility
from brainhub_core.text import slugify
from brainhub_core.web_memory import (
    memory_dashboard_next_actions as _core_memory_dashboard_next_actions,
    render_memory_card as _core_render_memory_card,
    render_memory_section as _core_render_memory_section,
)
from brainhub_core.web_memory_pages import (
    render_brief_page as _core_render_brief_page,
    render_captures_page as _core_render_captures_page,
    render_inbox_page as _core_render_inbox_page,
    render_memory_explanation_page as _core_render_memory_explanation_page,
    render_memory_log_page as _core_render_memory_log_page,
    render_memory_audit_page as _core_render_memory_audit_page,
    render_memory_dashboard_page as _core_render_memory_dashboard_page,
    render_memory_wins_page as _core_render_memory_wins_page,
    render_profile_page as _core_render_profile_page,
)
from brainhub_core.web_layout import (
    render_footer_html as _core_render_footer_html,
    render_header_html as _core_render_header_html,
    render_layout as _core_render_layout,
)
from brainhub_core.web_dashboard import (
    DASHBOARD_CSS as _core_dashboard_css,
    render_bounds_section as _core_render_bounds_section,
    render_empty_state as _core_render_dashboard_empty_state,
    render_kpi_row as _core_render_kpi_row,
    render_kpi_tile as _core_render_kpi_tile,
    render_priority_section as _core_render_priority_section,
    render_staleness_banner as _core_render_staleness_banner,
    render_trend_section as _core_render_trend_section,
)
from brainhub_core.dashboard_history import (
    HISTORY_FILENAME as _core_history_filename,
    PENDING_KEY as _core_pending_key,
    baseline_for as _core_history_baseline_for,
    build_snapshot as _core_build_snapshot,
    compute_deltas as _core_compute_deltas,
    history_path as _core_history_path,
    read_history as _core_read_history,
    record_snapshot as _core_record_snapshot,
    snapshot_key as _core_snapshot_key,
    trend_series as _core_trend_series,
)
from brainhub_core.config import (
    config_path as _core_config_path,
    memory_disabled_notice as _core_memory_disabled_notice,
    memory_layer_enabled as _core_memory_layer_enabled,
)
from brainhub_core.web_graph import (
    GRAPH_CATEGORY_COLORS as _core_graph_category_colors,
    GRAPH_INITIAL_SUMMARY_EDGE_LIMIT as _core_graph_initial_summary_edge_limit,
    GRAPH_INITIAL_SUMMARY_NODE_LIMIT as _core_graph_initial_summary_node_limit,
    graph_category_options as _core_graph_category_options,
    graph_initial_payload as _core_graph_initial_payload,
    graph_legend_items as _core_graph_legend_items,
    graph_needs_bounded_overview as _core_graph_needs_bounded_overview,
    render_graph_empty_body as _core_render_graph_empty_body,
    render_graph_page_body as _core_render_graph_page_body,
    render_graph_script as _core_render_graph_script,
)
from brainhub_core.web_home import (
    plural_type_label as _core_plural_type_label,
    ONBOARDING_PAGE_THRESHOLD as _core_ONBOARDING_PAGE_THRESHOLD,
    render_home_page as _core_render_home_page,
)
from brainhub_core.decision_audit import (
    audit_decisions as _core_audit_decisions,
)
from brainhub_core.web_health import (
    render_health_page as _core_render_health_page,
)
from brainhub_core.web_onboard import (
    render_onboard_page as _core_render_onboard_page,
)
from brainhub_core.web_ingest import (
    render_ingest_page as _core_render_ingest_page,
)
from brainhub_core.web_http import (
    ARTIFACT_CONTENT_SECURITY_POLICY as _core_artifact_content_security_policy,
    artifact_security_headers as _core_artifact_security_headers,
    BoundedThreadPoolTCPServer as _CoreBoundedThreadPoolTCPServer,
    CONTENT_SECURITY_POLICY as _core_content_security_policy,
    env_bounded_int as _core_env_bounded_int,
    is_allowed_static_file as _core_is_allowed_static_file,
    is_relative_to as _core_is_relative_to,
    LocalRateLimiter as _CoreLocalRateLimiter,
    local_no_store_headers as _core_local_no_store_headers,
    local_security_headers as _core_local_security_headers,
    parse_bounded_int as _core_parse_bounded_int,
    PERMISSIONS_POLICY as _core_permissions_policy,
    resolve_raw_static_path as _core_resolve_raw_static_path,
    safe_resolve as _core_safe_resolve,
    SVG_CONTENT_SECURITY_POLICY as _core_svg_content_security_policy,
    validate_local_browser_source_headers as _core_validate_local_browser_source_headers,
    validate_local_host_header as _core_validate_local_host_header,
    ViewerTransportConfig as _CoreViewerTransportConfig,
)
from brainhub_core.render.pdf import (
    find_pdf_renderer as _core_find_pdf_renderer,
    pdf_unavailable_reason as _core_pdf_unavailable_reason,
)
from brainhub_core.web_proposals import (
    create_raw_source_payload as _core_create_raw_source_payload,
    proposal_source_payload as _core_proposal_source_payload,
    proposal_sources as _core_proposal_sources,
)
from brainhub_core.web_propose import (
    render_propose_page as _core_render_propose_page,
)
from brainhub_core.web_prompts import (
    render_prompts_page as _core_render_prompts_page,
)
from brainhub_core.web_pages import (
    render_all_pages as _core_render_all_pages,
    render_wiki_page as _core_render_wiki_page,
)
from brainhub_core.ui_classes import ALERT
from brainhub_core.web_artifacts import (
    render_artifacts_page as _core_render_artifacts_page,
    render_documents_page as _core_render_documents_page,
)
from brainhub_core.web_search import (
    render_search_page as _core_render_search_page,
)
from brainhub_core.status import (
    link_status as _core_link_status,
)
from brainhub_core.operations import (
    operation_report as _core_operation_report,
)
from brainhub_core.capture import (
    capture_inbox as _core_capture_inbox,
    capture_records as _core_capture_records,
    capture_review_summary as _core_capture_review_summary,
    cli_capture_commands as _core_cli_capture_commands,
)
from brainhub_core.files import (
    atomic_write_json as _core_atomic_write_json,
)
from brainhub_core.artifacts import (
    ARTIFACT_DIRECTORIES,
    artifact_catalog as _core_artifact_catalog,
)
from brainhub_core.sid import (
    normalize_sid as _normalize_sid,
    generate_sid as _generate_sid,
    SID_TYPE_DECISION as _SID_TYPE_DECISION,
)
from brainhub_core import raw_ids as _raw_ids
from brainhub_core.addressing import (
    KIND_ARTIFACT as _KIND_ARTIFACT,
    KIND_PAGE as _KIND_PAGE,
    KIND_RAW as _KIND_RAW,
    Reference,
    canonical_path as _canonical_path,
    kind_for_sid as _kind_for_sid,
    legacy_path as _legacy_path,
    parse_path as _parse_address,
    with_query as _with_query,
)
from brainhub_core.wiki import (
    build_backlinks_from_cache as _core_build_backlinks_from_cache,
    build_wiki_cache as _core_build_wiki_cache,
    close_wiki_cache as _core_close_wiki_cache,
    context_for_topic as _core_context_for_topic,
    graph_data as _core_graph_data,
    graph_summary as _core_graph_summary,
    list_pages as _core_list_pages,
    load_backlinks_index as _core_load_backlinks_index,
    page_link_summary as _core_page_link_summary,
    rebuild_index as _core_rebuild_index,
    search_pages as _core_search_pages,
    wiki_mtime as _core_wiki_mtime,
)
del _BUNDLED_CORE

WIKI_DIR = ROOT / "wiki"
RAW_DIR = ROOT / "raw"
PORT = 3000
BIND_HOST = "127.0.0.1"
API_VERSION = "1"
MAX_POST_BYTES = 64 * 1024
MAX_QUERY_TEXT = 500
MAX_PROPOSAL_SOURCE_BYTES = 64 * 1024
MAX_RAW_SOURCE_BYTES = 60 * 1024
LOCAL_ACTION_HEADER = "X-BrainHub-Local-Action"
LOCAL_ACTION_VALUES = {"1", "true", "yes"}
# Mutation budget per client IP. Env-overridable because the per-IP assumption
# breaks behind a reverse proxy: every reader then arrives as the proxy's single
# address and shares one budget, so a shared deployment needs to raise it.
MUTATION_RATE_LIMIT = _core_env_bounded_int("BRAINHUB_MUTATION_RATE_LIMIT", 180, 1, 100_000)
MUTATION_RATE_WINDOW_SECONDS = _core_env_bounded_int("BRAINHUB_MUTATION_RATE_WINDOW", 60, 1, 86_400)
# Socket-layer sizing (accept backlog, worker ceiling, timeouts) with the
# BRAINHUB_* environment overrides applied. Read once at import so every request
# sees the same limits.
TRANSPORT = _CoreViewerTransportConfig.from_env()
REQUEST_TIMEOUT_SECONDS = TRANSPORT.request_timeout_seconds
KEEPALIVE_IDLE_TIMEOUT_SECONDS = TRANSPORT.keepalive_idle_timeout_seconds
CONTENT_SECURITY_POLICY = _core_content_security_policy
PERMISSIONS_POLICY = _core_permissions_policy
SVG_CONTENT_SECURITY_POLICY = _core_svg_content_security_policy
ARTIFACT_CONTENT_SECURITY_POLICY = _core_artifact_content_security_policy
# Directory names that hold servable artifacts, derived from the catalog's
# kind→subdir map so a per-tenant root reuses the same confinement set.
ARTIFACT_SUBDIRS = frozenset(Path(rel).name for rel in ARTIFACT_DIRECTORIES.values())
# Memory-layer surfaces gated by the workspace config (brainhub.config.json).
MEMORY_PAGE_PATHS = frozenset({
    "/brief", "/propose", "/memory", "/audit", "/inbox", "/captures",
    "/explain-memory", "/profile", "/wins", "/memory-log",
})
MEMORY_API_GET_PATHS = frozenset({
    "/api/memory-profile", "/api/memory-dashboard", "/api/memory-brief",
    "/api/query-link", "/api/memory-audit", "/api/memory-inbox", "/api/wins",
    "/api/memory-log", "/api/capture-inbox", "/api/explain-memory",
    "/api/propose-memories", "/api/review-memory", "/api/archive-memory",
    "/api/restore-memory",
})
MEMORY_API_POST_PATHS = frozenset({
    "/api/propose-memories", "/api/remember-memory", "/api/update-memory",
    "/api/review-memory", "/api/archive-memory", "/api/restore-memory",
})
# Decision board (Phase-1 MVP) — a parallel, additive surface. It reuses the
# viewer's local-action guard, mutation rate limit, atomic-write and log
# helpers, but owns its own storage dir (decisions/), its own POST allowlist,
# and touches no MEMORY_* code. Data contract + forward-compat LAWS live in
# core/brainhub/decisions/SCHEMA.md.
DECISIONS_DIRNAME = "decisions"
# batch_id charset is locked to ^[a-z0-9-]{1,64}$. Checked as an allowlist (not a
# regex) so it reads as the path-confinement identifier gate it is, and so it
# never resembles a CJK-deleting text-slug regex (see tests/test_cjk.py).
DECISION_BATCH_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")
DECISION_BATCH_ID_MAX_LEN = 64
# "skipped" is an outcome, not a blank. Closing a batch that still has undecided
# items used to leave `decision: null` behind a `status: "decided"` — and a blank
# reads identically whether the human deliberately passed or never saw the item.
# It is a first-class action so the pass leaves a trace with the same provenance
# and timestamp rules as any other decision.
DECISION_ACTIONS = frozenset(
    {"approve", "reject", "pick", "pick-multi", "edit", "respond", "skipped"}
)
DECISION_API_POST_PATHS = frozenset({"/api/decision-board/decide"})
# Status dashboard (SPoG) — read-only, rendered from dashboard/spog.json plus
# one section derived straight from decisions/. It replaces a hand-authored HTML
# artifact that had to be regenerated by hand and was five days stale with the
# old date printed inside it. Two properties are the whole point: the page
# states its own age (and warns past 48h), and the derived section cannot go
# stale because nobody maintains it.
DASHBOARD_DIRNAME = "dashboard"
DASHBOARD_FILENAME = "spog.json"
DASHBOARD_TITLE = "公司狀況 SPoG"
PROPOSAL_SOURCE_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".text",
    ".rst",
    ".adoc",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
}
RAW_STATIC_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}

# ---------------------------------------------------------------------------
# In-memory caches — invalidated on each request by mtime check
# ---------------------------------------------------------------------------
CACHE_MTIME_CHECK_INTERVAL_SECONDS = 0.5
_pages_cache: list | None = None
_pages_cache_mtime: float = 0.0
_pages_cache_checked_at: float = 0.0
_page_index: dict[str, Path] = {}  # stem.lower() → path
_fulltext_index: dict[str, str] = {}  # stem.lower() → full text (for search)
_normalized_fulltext_index: dict[str, str] = {}  # punctuation-normalized full text
_text_words_index: dict[str, set[str]] = {}  # stem.lower() → normalized fulltext words
_meta_words_index: dict[str, set[str]] = {}  # stem.lower() → normalized metadata words
_snippet_index: dict[str, str] = {}  # stem.lower() → pre-extracted first snippet
_token_index: dict[str, set[str]] = {}  # token → set of page stems that contain it
_page_map: dict[str, dict] = {}  # stem.lower() → page dict (for O(1) lookup in search)
_meta_token_index: dict[str, set[str]] = {}  # token → stems with that token in title/alias/tag/tldr
_forward_links_index: dict[str, list[str]] = {}  # page name → canonical outbound wikilinks
_fts_index = None
_search_backend = "token-index"
_cache_read_warnings: list[dict[str, str]] = []
_cache_lock = threading.RLock()
_rate_limiter_lock = threading.Lock()
_mutation_rate_limiter = _CoreLocalRateLimiter(
    max_events=MUTATION_RATE_LIMIT,
    window_seconds=MUTATION_RATE_WINDOW_SECONDS,
)


class ThreadingLocalTCPServer(_CoreBoundedThreadPoolTCPServer):
    """The viewer's server: the shared bounded pool, sized from the environment.

    Everything about how connections are queued and served lives in
    ``brainhub_core.web_http``; this binds it to the viewer's transport config and
    keeps the historical name.
    """

    transport = TRANSPORT


def _invalidate_pages_cache() -> None:
    global _pages_cache, _pages_cache_mtime, _pages_cache_checked_at, _forward_links_index, _fts_index, _search_backend, _cache_read_warnings
    with _cache_lock:
        _core_close_wiki_cache({"fts_index": _fts_index})
        _pages_cache = None
        _pages_cache_mtime = 0.0
        _pages_cache_checked_at = 0.0
        _forward_links_index = {}
        _fts_index = None
        _search_backend = "token-index"
        _cache_read_warnings = []


def _wiki_mtime() -> float:
    return _core_wiki_mtime(WIKI_DIR)


def _get_all_pages(force_check: bool = False) -> list:
    global _pages_cache, _pages_cache_mtime, _pages_cache_checked_at, _page_index, _fulltext_index, _normalized_fulltext_index, _text_words_index, _meta_words_index, _snippet_index, _token_index, _page_map, _meta_token_index, _forward_links_index, _fts_index, _search_backend, _cache_read_warnings
    with _cache_lock:
        now = time.monotonic()
        if (
            _pages_cache is not None
            and not force_check
            and CACHE_MTIME_CHECK_INTERVAL_SECONDS > 0
            and now - _pages_cache_checked_at < CACHE_MTIME_CHECK_INTERVAL_SECONDS
        ):
            return _pages_cache
        mtime = _wiki_mtime()
        _pages_cache_checked_at = now
        if _pages_cache is not None and mtime == _pages_cache_mtime:
            return _pages_cache
        _core_close_wiki_cache({"fts_index": _fts_index})
        cache = _core_build_wiki_cache(WIKI_DIR)
        _pages_cache = cache["pages"]
        _pages_cache_mtime = mtime
        _page_index = cache["page_index"]
        _fulltext_index = cache["fulltext"]
        _normalized_fulltext_index = cache["normalized_fulltext"]
        _text_words_index = cache["text_words_index"]
        _meta_words_index = cache["meta_words_index"]
        _snippet_index = cache["snippet_index"]
        _token_index = cache["token_index"]
        _meta_token_index = cache["meta_token_index"]
        _page_map = cache["page_map"]
        _forward_links_index = cache.get("forward_links_index", {})
        _fts_index = cache.get("fts_index")
        _search_backend = str(cache.get("search_backend") or "token-index")
        _cache_read_warnings = cache.get("read_warnings") if isinstance(cache.get("read_warnings"), list) else []
        return _pages_cache


def _current_wiki_cache() -> dict[str, object]:
    with _cache_lock:
        _get_all_pages()
        return {
            "pages": _pages_cache or [],
            "page_index": _page_index,
            "fulltext": _fulltext_index,
            "normalized_fulltext": _normalized_fulltext_index,
            "text_words_index": _text_words_index,
            "meta_words_index": _meta_words_index,
            "snippet_index": _snippet_index,
            "token_index": _token_index,
            "meta_token_index": _meta_token_index,
            "page_map": _page_map,
            "forward_links_index": _forward_links_index,
            "fts_index": _fts_index,
            "search_backend": _search_backend,
            "read_warning_count": len(_cache_read_warnings),
            "read_warnings": _cache_read_warnings,
        }


def _find_page(name: str) -> Path | None:
    # Ensure cache is warm — _get_all_pages populates _page_index as a side effect
    _get_all_pages()
    return _page_index.get(name.strip().lower())


# Keep _all_pages as alias for API compatibility
def _all_pages() -> list:
    return _get_all_pages()


def _page_list_payload(
    category: str = "",
    page_type: str = "",
    maturity: str = "",
    limit: int = 100,
    offset: int = 0,
    include_all: bool = False,
) -> dict:
    return _core_list_pages(
        _current_wiki_cache(),
        category=category,
        page_type=page_type,
        maturity=maturity,
        limit=limit,
        offset=offset,
        include_all=include_all,
    )


def _load_backlinks_index() -> tuple[dict, str | None]:
    return _core_load_backlinks_index(WIKI_DIR / "_backlinks.json")


def _page_links_payload(
    page_name: str,
    limit: int = 100,
    offset: int = 0,
    include_all: bool = False,
) -> tuple[dict, int]:
    backlinks, error = _load_backlinks_index()
    if error:
        return {"error": error}, 500
    if not page_name.strip():
        return {"error": "page parameter required", "inbound": [], "forward": []}, 400
    return _core_page_link_summary(
        backlinks,
        page_name,
        limit=limit,
        offset=offset,
        include_all=include_all,
    ), 200


def _parse_search_limit(raw: object) -> tuple[int | None, str | None]:
    return _core_parse_bounded_int(raw, "limit", 20, 1, 50)


def _query_text(query: dict[str, list[str]], *names: str, max_len: int = MAX_QUERY_TEXT) -> str:
    for name in names:
        values = query.get(name)
        if values:
            text = _clean_text_input(values[0], max_len=max_len)
            if text:
                return text
    return ""


def _utc_timestamp() -> str:
    return _core_utc_timestamp()


def _append_log(timestamp: str, operation: str, description: str, lines: list[str]) -> None:
    _core_append_log(WIKI_DIR, timestamp, operation, description, lines)


def _sid_for_page_name(name: str) -> str:
    """The sid recorded on a page, or "" when it has none yet."""
    _get_all_pages()  # warms _page_map
    entry = _page_map.get(name.strip().lower())
    return _normalize_sid(entry.get("sid")) if isinstance(entry, dict) else ""


def _page_href(name: str) -> str:
    """Canonical page URL, falling back to the legacy shape for sid-less pages."""
    name = name.strip()
    sid = _sid_for_page_name(name)
    if sid:
        return _canonical_path(_KIND_PAGE, sid, name)
    return _legacy_path(_KIND_PAGE, name)


def _artifact_record_by_sid(sid: str) -> dict | None:
    """The stored artifact record carrying this sid, or None."""
    for record in _artifact_records():
        if _normalize_sid(record.get("sid")) == sid:
            return record
    return None


def _artifact_records() -> list[dict]:
    artifacts = _artifact_catalog().get("artifacts", [])
    assert isinstance(artifacts, list)
    return [record for record in artifacts if isinstance(record, dict)]


def _artifact_subpath(record: dict) -> str:
    """The <subdir>/<file> locator a stored artifact record points at."""
    return str(record.get("stored_path", "")).removeprefix("artifacts/")


def _artifact_record_by_subpath(subpath: str) -> dict | None:
    """The stored artifact record for a legacy <subdir>/<file> locator."""
    wanted = str(subpath or "").strip("/")
    for record in _artifact_records():
        if _artifact_subpath(record) == wanted:
            return record
    return None


def _graph_href(name: str, *, depth: int = 2) -> str:
    return f"/graph?focus={urllib.parse.quote(name.strip(), safe='')}&depth={depth}"


def _proposal_href(raw_path: str) -> str:
    return "/propose?source=" + urllib.parse.quote(raw_path.strip(), safe="")


def _plural_type_label(page_type: str) -> str:
    return _core_plural_type_label(page_type)


def _memory_records() -> list[dict[str, object]]:
    return _core_memory_records(WIKI_DIR, include_body=False)


def _count_values(records: list[dict[str, object]], field: str) -> dict[str, int]:
    return _core_count_values(records, field)


def _is_active_memory(record: dict[str, object]) -> bool:
    return _core_is_active_memory(record)


def _memory_review_issues(record: dict[str, object]) -> list[dict[str, str]]:
    return _core_memory_review_issues(record, review_command="review-memory")


def _project_visible_records(project: str | None = None) -> list[dict[str, object]]:
    project_name = _core_normalize_project(project)
    return [
        record
        for record in _memory_records()
        if _core_memory_visible_for_project(record, project_name)
    ]


def _ingest_status() -> dict[str, object]:
    return _core_collect_ingest_status(WIKI_DIR.parent)


def _memory_inbox(limit: int = 20, include_archived: bool = False, project: str | None = None) -> dict[str, object]:
    return _core_memory_inbox(
        _project_visible_records(project),
        limit=limit,
        include_archived=include_archived,
        review_command="review-memory",
        project=project,
        command_target=WIKI_DIR.parent,
    )


def _slugify(value: str, fallback: str = "memory") -> str:
    return slugify(value, fallback=fallback)


def _memory_title(text: str, explicit_title: str | None = None) -> str:
    if explicit_title and explicit_title.strip():
        return explicit_title.strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Memory")
    first_sentence = re.split(r"(?<=[.!?])\s+", first_line, maxsplit=1)[0].strip()
    if len(first_sentence) <= 70:
        return first_sentence.rstrip(".")
    return first_sentence[:67].rstrip() + "..."


def _memory_duplicate_candidates(
    text: str,
    title: str | None,
    memory_type: str,
    scope: str,
    limit: int = 3,
) -> list[dict[str, object]]:
    return _core_memory_duplicate_candidates(
        _memory_records(),
        text,
        title,
        memory_type,
        scope,
        limit=limit,
    )


def _propose_memories_from_text(
    text: str,
    source: str = "http",
    limit: int = 10,
    project: str | None = None,
) -> dict[str, object]:
    return _core_propose_memories_from_text(
        text,
        _memory_records(),
        source=source,
        limit=limit,
        writes_memory=False,
        project=project,
        command_target=WIKI_DIR.parent,
    )


def _memory_explanation(identifier: str) -> dict[str, object]:
    return _core_memory_explanation(
        WIKI_DIR,
        identifier,
        records=_memory_records(),
        review_command="review-memory",
        command_target=WIKI_DIR.parent,
    )


def _memory_profile(limit: int = 10, project: str | None = None) -> dict[str, object]:
    return _core_memory_profile(_memory_records(), limit=limit, review_command="review-memory", project=project)


def _mark_memory_reviewed(identifier: str, note: str = "") -> dict[str, object]:
    result = _core_mark_memory_reviewed(
        WIKI_DIR,
        _clean_text_input(identifier, max_len=300),
        note=_clean_text_input(note, max_len=500),
        timestamp=_utc_timestamp(),
        records=_memory_records(),
        review_command="review-memory",
        log_writer=_append_log,
    )
    if result["updated"]:
        _invalidate_pages_cache()
    return result


def _set_memory_status(identifier: str, status: str, reason: str = "") -> dict[str, object]:
    result = _core_set_memory_status(
        WIKI_DIR,
        _clean_text_input(identifier, max_len=300),
        status,
        reason=_clean_text_input(reason, max_len=500),
        timestamp=_utc_timestamp(),
        records=_memory_records(),
        log_writer=_append_log,
    )
    if result["updated"]:
        _invalidate_pages_cache()
    return result


def _remember_memory_from_web(payload: dict[str, object]) -> dict[str, object]:
    result = _core_write_memory_page(
        WIKI_DIR,
        _clean_text_input(payload.get("memory") or payload.get("text"), max_len=MAX_POST_BYTES),
        _clean_text_input(payload.get("title"), max_len=160) or None,
        _clean_text_input(payload.get("memory_type") or payload.get("type") or "note", max_len=30),
        _clean_text_input(payload.get("scope") or "user", max_len=30),
        _clean_text_input(payload.get("tags"), max_len=500) or None,
        _clean_text_input(payload.get("source") or "web approval", max_len=500),
        _utc_timestamp(),
        project=_clean_text_input(payload.get("project"), max_len=80) or None,
        visibility=_clean_text_input(payload.get("visibility"), max_len=30) or None,
        review_after=_clean_text_input(payload.get("review_after"), max_len=40) or None,
        expires_at=_clean_text_input(payload.get("expires_at"), max_len=40) or None,
        records=_memory_records(),
        allow_duplicate=False,
        allow_conflict=False,
        log_writer=_append_log,
        rebuild_backlinks=lambda: bool(_rebuild_backlinks_payload().get("rebuilt")),
    )
    if result.get("created"):
        _invalidate_pages_cache()
    return result


def _update_memory_from_web(payload: dict[str, object]) -> dict[str, object]:
    result = _core_update_memory_page(
        WIKI_DIR,
        _clean_text_input(payload.get("memory") or payload.get("identifier"), max_len=300),
        _clean_text_input(payload.get("text"), max_len=MAX_POST_BYTES),
        _clean_text_input(payload.get("source") or "web approval", max_len=500),
        _utc_timestamp(),
        records=_memory_records(),
        review_command="review-memory",
        allow_conflict=False,
        project=_clean_text_input(payload.get("project"), max_len=80) or None,
        log_writer=_append_log,
        rebuild_backlinks=lambda: bool(_rebuild_backlinks_payload().get("rebuilt")),
    )
    if result.get("updated"):
        _invalidate_pages_cache()
    return result


def _memory_activity_key(record: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(record.get("updated_at") or record.get("date_captured") or ""),
        str(record.get("date_captured") or ""),
        str(record.get("title") or "").lower(),
    )


def _memory_action_hints(record: dict[str, object]) -> list[dict[str, object]]:
    hints: list[dict[str, object]] = []
    for action in _core_memory_action_hints(record, review_command="review-memory"):
        item = {
            "kind": str(action.get("kind") or ""),
            "label": str(action.get("label") or ""),
            "href": "",
            "command": str(action.get("command") or ""),
            "description": str(action.get("description") or ""),
            "priority": str(action.get("priority") or ""),
            "arguments": action.get("arguments") if isinstance(action.get("arguments"), dict) else {},
        }
        if action.get("kind") == "explain":
            name = str(record.get("name") or "")
            item["href"] = f"/explain-memory?memory={urllib.parse.quote(name, safe='')}"
        hints.append(item)
    return hints


def _memory_with_actions(record: dict[str, object]) -> dict[str, object]:
    item = dict(record)
    item["actions"] = _memory_action_hints(record)
    return item


def _memory_dashboard_next_actions(
    memory_count: int,
    review_count: int,
    updated_count: int,
    archived_count: int,
    capture_count: int = 0,
    capture_warning_count: int = 0,
) -> list[dict[str, str]]:
    return _core_memory_dashboard_next_actions(
        memory_count=memory_count,
        review_count=review_count,
        updated_count=updated_count,
        archived_count=archived_count,
        capture_count=capture_count,
        capture_warning_count=capture_warning_count,
    )


# ---------------------------------------------------------------------------
# Decision board (Phase-1 MVP) — storage, write-back, and page renderer.
# Fully parallel to the memory layer: zero MEMORY_* calls, its own decisions/
# dir. See core/brainhub/decisions/SCHEMA.md for the data contract + LAWS.
# ---------------------------------------------------------------------------

def _decisions_dir() -> Path:
    return WIKI_DIR.parent / DECISIONS_DIRNAME


def _valid_batch_id(batch_id: object) -> bool:
    return (
        isinstance(batch_id, str)
        and 1 <= len(batch_id) <= DECISION_BATCH_ID_MAX_LEN
        and all(ch in DECISION_BATCH_ID_CHARS for ch in batch_id)
    )


def _decision_batch_path(batch_id: object) -> Path | None:
    """The confined on-disk path for a batch, or None when the id is invalid.

    The id charset (^[a-z0-9-]{1,64}$) forbids '/', '.', and every separator, so
    this join can never escape decisions/. This is the path-confinement gate and
    it is applied everywhere batch_id reaches a path.
    """
    # A decision-type sid (D-prefixed) resolves to <sid>.json. normalize_sid folds
    # case + Crockford confusables and verifies the check symbol, so the result is a
    # fixed [0-9A-Z]{6} string — path-safe, the same guarantee the slug charset gives.
    sid = _normalize_sid(batch_id)
    if sid and sid[0] == _SID_TYPE_DECISION:
        return _decisions_dir() / f"{sid}.json"
    if not _valid_batch_id(batch_id):
        return None
    assert isinstance(batch_id, str)
    return _decisions_dir() / f"{batch_id}.json"


def _load_decision_batch(batch_id: object) -> dict | None:
    path = _decision_batch_path(batch_id)
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _undecided_item_ids(batch: object) -> list[str]:
    """Ids of items with no outcome recorded — the one definition of 'undecided'.

    The close gate, the board's progress header, and the standing audit all ask
    this same question, so they ask it in one place. A batch whose `status` is
    "decided" while this returns a non-empty list is the invariant violation
    `brainhub_core.decision_audit` reports.
    """
    if not isinstance(batch, dict):
        return []
    items = batch.get("items")
    if not isinstance(items, list):
        return []
    return [
        str(entry.get("id") or f"item-{index + 1}")
        for index, entry in enumerate(items)
        if isinstance(entry, dict) and not isinstance(entry.get("decision"), dict)
    ]


def _decision_option_text(option: object) -> str:
    """The human-facing label for one option entry (string or {"text": ...})."""
    if isinstance(option, dict):
        return str(option.get("text") or option.get("label") or json.dumps(option, ensure_ascii=False))
    return str(option)


def _decision_option_preview(option: object) -> str | None:
    """Optional per-option preview (AskUserQuestion-style): a monospace box shown under
    the option for visual comparison (ASCII mockups, snippets). Only dict options carry it."""
    if isinstance(option, dict):
        preview = option.get("preview")
        if isinstance(preview, str) and preview.strip():
            return preview
    return None


def _apply_decision_delta(payload: dict) -> tuple[dict[str, object], int]:
    """Merge one decision (or a close) into a batch file, preserving unknowns.

    Returns (json_response, http_status). The whole batch dict is loaded and only
    the targeted item's `decision` (or the batch status/decided_at on close) is
    touched, so every field this MVP does not understand — top-level and per-item
    — round-trips untouched (SCHEMA.md LAW 2/3). Writes are atomic (tmp+rename via
    _core_atomic_write_json) and logged via _append_log.
    """
    batch_id = payload.get("batch_id")
    path = _decision_batch_path(batch_id)
    if path is None:
        return {"saved": False, "error": "invalid batch_id; must match ^[a-z0-9-]{1,64}$"}, 400
    batch = _load_decision_batch(batch_id)
    if batch is None:
        return {"saved": False, "error": "batch not found"}, 404
    now = _utc_timestamp()

    if payload.get("close") is True:
        # A close used to be whatever the client asserted: `status` claimed every
        # item had an outcome and nothing checked it, so a batch could go
        # `decided` with blank items inside. That state cost a real decision —
        # two items on studio-pilot-2026-08-01 were closed having never been
        # answered, and a blank looks exactly like a deliberate pass.
        # `status: "decided"` is now a *derived* state: reachable only when every
        # item carries an outcome, or when the caller says in the payload what to
        # do with the ones that do not.
        undecided = _undecided_item_ids(batch)
        skip_undecided = payload.get("skip_undecided") is True
        if undecided and not skip_undecided:
            return {
                "saved": False,
                "error": (
                    f"還有 {len(undecided)} 項沒決定，不能標記完成。"
                    "回去決完，或送 skip_undecided:true 把它們明確記成「略過」。"
                ),
                "undecided": undecided,
            }, 409

        decided_by = payload.get("decided_by")
        if not isinstance(decided_by, str) or not decided_by:
            decided_by = "self-declared:owner"
        elif not decided_by.startswith("self-declared:"):
            # LAW 1 applies to a skip exactly as it does to a decision.
            return {"saved": False,
                    "error": "decided_by must be 'self-declared:<name>' in this MVP"}, 400
        skip_note = payload.get("skip_note")
        if skip_note is not None and not isinstance(skip_note, str):
            return {"saved": False, "error": "skip_note must be a string"}, 400

        skipped_ids: list[str] = []
        if undecided:
            for entry in batch.get("items") or []:
                if not isinstance(entry, dict) or entry.get("decision") is not None:
                    continue
                skip: dict[str, object] = {
                    "action": "skipped",
                    "decided_by": decided_by,
                    "decided_at": now,
                }
                if skip_note:
                    skip["note"] = skip_note
                entry["decision"] = skip
                skipped_ids.append(str(entry.get("id") or ""))

        batch["status"] = "decided"
        batch["decided_at"] = now
        try:
            _core_atomic_write_json(path, batch)
        except OSError as exc:
            return {"saved": False, "error": f"write failed: {exc}"}, 500
        detail = [f"batch_id: {batch_id}", "status: decided"]
        if skipped_ids:
            detail.append(f"skipped: {', '.join(skipped_ids)}")
        _append_log(now, "decision-board", f"close {batch_id}", detail)
        return {"saved": True, "closed": True, "batch_id": batch_id,
                "status": "decided", "decided_at": now, "skipped": skipped_ids}, 200

    item_id = payload.get("item_id")
    if not isinstance(item_id, str) or not item_id:
        return {"saved": False, "error": "item_id required"}, 400
    items = batch.get("items")
    target = None
    if isinstance(items, list):
        for entry in items:
            if isinstance(entry, dict) and entry.get("id") == item_id:
                target = entry
                break
    if target is None:
        return {"saved": False, "error": "item_id not found"}, 404

    raw_decision = payload.get("decision")
    # Clearing a decision: an explicit `decision: null` returns the item to
    # undecided. Only the targeted item's `decision` is set to None; every other
    # field — top-level, item-level, and unknown — round-trips untouched (LAW 3).
    if raw_decision is None and "decision" in payload:
        target["decision"] = None
        try:
            _core_atomic_write_json(path, batch)
        except OSError as exc:
            return {"saved": False, "error": f"write failed: {exc}"}, 500
        _append_log(now, "decision-board", f"clear {batch_id}/{item_id}",
                    [f"batch_id: {batch_id}", f"item_id: {item_id}", "decision: cleared"])
        return {"saved": True, "batch_id": batch_id, "item_id": item_id, "decision": None}, 200
    if not isinstance(raw_decision, dict):
        return {"saved": False, "error": "decision object required"}, 400
    action = raw_decision.get("action")
    if action not in DECISION_ACTIONS:
        return {"saved": False,
                "error": f"action must be one of: {', '.join(sorted(DECISION_ACTIONS))}"}, 400

    # Copy the writer's decision so unknown keys round-trip (LAW 3); then
    # validate/normalise only the fields this MVP owns.
    decision = dict(raw_decision)
    decision["action"] = action

    if action == "pick":
        option = raw_decision.get("option")
        options = target.get("options")
        if not isinstance(option, int) or isinstance(option, bool):
            return {"saved": False, "error": "pick requires an integer 'option'"}, 400
        if not isinstance(options, list) or not (0 <= option < len(options)):
            return {"saved": False, "error": "option out of range for this item"}, 400
        decision["option"] = option
    if action == "pick-multi":
        selected = raw_decision.get("options_selected")
        options = target.get("options")
        if not isinstance(options, list):
            return {"saved": False, "error": "this item has no options to pick"}, 400
        if not isinstance(selected, list) or not selected:
            return {"saved": False,
                    "error": "pick-multi requires a non-empty 'options_selected' list"}, 400
        norm: list[int] = []
        for opt in selected:
            if not isinstance(opt, int) or isinstance(opt, bool) or not (0 <= opt < len(options)):
                return {"saved": False, "error": "options_selected has an out-of-range index"}, 400
            if opt not in norm:
                norm.append(opt)
        decision["options_selected"] = sorted(norm)
    if action == "edit":
        if not isinstance(raw_decision.get("edited_text"), str):
            return {"saved": False, "error": "edit requires a string 'edited_text'"}, 400
    if action == "respond":
        text = raw_decision.get("text")
        if not isinstance(text, str) or not text.strip():
            return {"saved": False, "error": "respond requires a non-empty 'text'"}, 400

    note = raw_decision.get("note")
    if note is not None and not isinstance(note, str):
        return {"saved": False, "error": "note must be a string"}, 400

    # LAW 1: decided_by is "<provenance>:<name>". This MVP writes only
    # self-declared:* (no login yet); reject any other provenance so a board POST
    # can never claim verification it did not perform.
    decided_by = raw_decision.get("decided_by")
    if not isinstance(decided_by, str) or not decided_by:
        decided_by = "self-declared:owner"
    elif not decided_by.startswith("self-declared:"):
        return {"saved": False,
                "error": "decided_by must be 'self-declared:<name>' in this MVP"}, 400
    decision["decided_by"] = decided_by
    # Server owns the timestamp; the client value (if any) is overwritten.
    decision["decided_at"] = now

    target["decision"] = decision
    try:
        _core_atomic_write_json(path, batch)
    except OSError as exc:
        return {"saved": False, "error": f"write failed: {exc}"}, 500
    _append_log(now, "decision-board", f"decide {batch_id}/{item_id}",
                [f"batch_id: {batch_id}", f"item_id: {item_id}",
                 f"action: {action}", f"decided_by: {decided_by}"])
    return {"saved": True, "batch_id": batch_id, "item_id": item_id, "decision": decision}, 200


# Inline board behaviour. Vanilla JS, no framework/build step. `__BATCH_ID__` is
# replaced with a JSON-quoted batch id (charset ^[a-z0-9-]{1,64}$, so it is safe
# to inline into a <script>). Behaviour: OPTIMISTIC — every control click updates
# the item's visual state immediately, then POSTs in the background; a per-item
# "已儲存 ✓" flashes near the control; approve/reject and pick are re-choosable
# toggles (clicking the chosen side clears via a `decision:null` POST); a decided
# item collapses to a one-line summary you can click to re-expand and change.
_DECISION_BOARD_JS = r"""
(function(){
var BATCH_ID=__BATCH_ID__;
function post(body){
return fetch('/api/decision-board/decide',{method:'POST',
headers:{'Content-Type':'application/json','X-BrainHub-Local-Action':'true'},
body:JSON.stringify(body)}).then(function(r){
return r.json().catch(function(){return {};}).then(function(d){return {ok:r.ok,data:d};});});
}
function show(el,on){if(el){el.hidden=!on;}}
var items=Array.prototype.slice.call(document.querySelectorAll('.decision-item'));
function actionLabel(a){return a==='approve'?'核准':a==='reject'?'退回':(a==='pick'||a==='pick-multi')?'已選':a==='edit'?'已編輯':a==='respond'?'自己作答':a==='skipped'?'略過':'';}
function updateProgress(){
var n=items.length,decided=0,c={approve:0,reject:0,pick:0,edit:0,skipped:0};
items.forEach(function(it){var a=it.getAttribute('data-decision');if(!a)return;var b=(a==='pick-multi')?'pick':(a==='respond')?'edit':a;if(c.hasOwnProperty(b)){decided++;c[b]++;}});
var undecided=n-decided;
var line='已決定 '+decided+' / '+n+' · 核准 '+c.approve+' · 退回 '+c.reject+' · 已選 '+c.pick+' · 編輯 '+c.edit+(c.skipped?' · 略過 '+c.skipped:'')+' · 未處理 '+undecided;
var el=document.getElementById('decision-progress-line');if(el){el.textContent=line;}
var allDone=document.getElementById('decision-all-done');if(allDone){show(allDone,n>0&&undecided===0);}
}
function flash(el,text){
if(!el)return;el.textContent=text;el.hidden=false;
el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');
clearTimeout(el._t);el._t=setTimeout(function(){el.hidden=true;el.classList.remove('flash');},1600);
}
items.forEach(function(item){
var itemId=item.getAttribute('data-item-id');
var summary=item.querySelector('.decision-summary');
var controls=item.querySelector('.decision-controls');
var savedEl=item.querySelector('.decision-saved');
var errEl=item.querySelector('.decision-error');
var noteEl=item.querySelector('.decision-note-text');
var ta=item.querySelector('.decision-edit-text');
var collapseTimer=null;
function curAction(){return item.getAttribute('data-decision')||'';}
function curOption(){var o=item.getAttribute('data-option');return (o===null||o==='')?null:parseInt(o,10);}
function curSelected(){var s=item.getAttribute('data-selected');if(!s)return [];return s.split(',').filter(function(x){return x!=='';}).map(function(x){return parseInt(x,10);});}
function summaryText(){
var a=curAction();
if(a==='pick'){var opt=curOption();var b=item.querySelector('.decision-opt[data-option="'+opt+'"]');
var name=b?(b.getAttribute('data-label')||('選項 '+(opt+1))):('選項 '+(opt+1));return '已選：'+name+' · 已儲存';}
if(a==='pick-multi'){var names=curSelected().map(function(idx){var bm=item.querySelector('.decision-optm[data-option="'+idx+'"]');return bm?(bm.getAttribute('data-label')||('選項 '+(idx+1))):('選項 '+(idx+1));});return '已選：'+(names.join('、')||'—')+' · 已儲存';}
if(a==='respond'){var rt=item.querySelector('.decision-respond-text');var tv=rt?rt.value:'';return '自己輸入：'+(tv.length>16?tv.slice(0,16)+'…':(tv||'—'))+' · 已儲存';}
return actionLabel(a)+' · 已儲存';
}
function paint(){
var a=curAction();
item.querySelectorAll('.decision-seg').forEach(function(seg){
var on=seg.getAttribute('data-action')===a;
seg.classList.toggle('chosen',on);seg.classList.toggle('dim',a!==''&&!on);});
var opt=curOption();
item.querySelectorAll('.decision-opt:not(.decision-optm)').forEach(function(o){
var on=a==='pick'&&parseInt(o.getAttribute('data-option'),10)===opt;
o.classList.toggle('chosen',on);o.classList.toggle('dim',a==='pick'&&!on);});
var sel=curSelected();
item.querySelectorAll('.decision-optm').forEach(function(o){
var on=a==='pick-multi'&&sel.indexOf(parseInt(o.getAttribute('data-option'),10))!==-1;
o.classList.toggle('chosen',on);o.setAttribute('aria-checked',on?'true':'false');});
var es=item.querySelector('.decision-edit-save');if(es){es.classList.toggle('chosen',a==='edit');}
var rs=item.querySelector('.decision-respond-save');if(rs){rs.classList.toggle('chosen',a==='respond');}
}
function collapse(){if(curAction()===''){expand();return;}summary.textContent=summaryText();show(summary,true);show(controls,false);}
function expand(){show(summary,false);show(controls,true);}
function scheduleCollapse(){if(collapseTimer)clearTimeout(collapseTimer);if(curAction()===''){expand();return;}collapseTimer=setTimeout(collapse,1400);}
function send(newAction,newOption,edited){
if(collapseTimer)clearTimeout(collapseTimer);
if(newAction===null){item.setAttribute('data-decision','');item.removeAttribute('data-option');item.removeAttribute('data-selected');}
else{item.setAttribute('data-decision',newAction);
if(newAction==='pick'){item.setAttribute('data-option',String(newOption));item.removeAttribute('data-selected');}
else if(newAction==='pick-multi'){item.setAttribute('data-selected',(newOption||[]).join(','));item.removeAttribute('data-option');}
else{item.removeAttribute('data-option');item.removeAttribute('data-selected');}}
item.removeAttribute('data-savestate');paint();expand();updateProgress();show(errEl,false);errEl.onclick=null;
var body={batch_id:BATCH_ID,item_id:itemId};
if(newAction===null){body.decision=null;}
else{var d={action:newAction,decided_by:'self-declared:owner'};
var note=noteEl&&noteEl.value.trim();if(note){d.note=note;}
if(newAction==='pick'){d.option=newOption;}
if(newAction==='pick-multi'){d.options_selected=newOption||[];}
if(newAction==='edit'){d.edited_text=edited||'';}
if(newAction==='respond'){d.text=edited||'';}
body.decision=d;}
post(body).then(function(res){
if(res.ok){flash(savedEl,newAction===null?'已清除 ✓':'已儲存 ✓');if(newAction!=='pick-multi'){scheduleCollapse();}}
else{item.setAttribute('data-savestate','failed');show(errEl,true);
errEl.textContent=(res.data&&res.data.error)?('儲存失敗，點一下重試（'+res.data.error+'）'):'儲存失敗，點一下重試';
errEl.onclick=function(){send(newAction,newOption,edited);};}
});
}
// Clicking the choice you already made means "yes, that one" — never "undo".
// Those two intents shared one affordance, and the board hides the state 1.4s
// after saving, so a human re-clicking to check their answer had really saved
// silently erased it. Undo has its own button (清除（回未處理）).
function reaffirm(){flash(savedEl,'已儲存 ✓（沒有變動）');scheduleCollapse();}
paint();if(curAction()!==''){collapse();}
if(summary){summary.addEventListener('click',function(){expand();});}
item.querySelectorAll('.decision-seg').forEach(function(seg){
seg.addEventListener('click',function(){var a=seg.getAttribute('data-action');
if(curAction()===a){reaffirm();return;}send(a);});});
item.querySelectorAll('.decision-opt:not(.decision-optm)').forEach(function(o){
o.addEventListener('click',function(){var idx=parseInt(o.getAttribute('data-option'),10);
if(curAction()==='pick'&&curOption()===idx){reaffirm();return;}send('pick',idx);});});
item.querySelectorAll('.decision-optm').forEach(function(o){
o.addEventListener('click',function(){var idx=parseInt(o.getAttribute('data-option'),10);
var sel=curSelected();var pos=sel.indexOf(idx);
if(pos===-1){sel.push(idx);}else{sel.splice(pos,1);}
sel.sort(function(x,y){return x-y;});
if(sel.length===0){send(null);}else{send('pick-multi',sel);}});});
var es=item.querySelector('.decision-edit-save');
if(es){es.addEventListener('click',function(){send('edit',null,ta?ta.value:'');});}
var rta=item.querySelector('.decision-respond-text');
var rs=item.querySelector('.decision-respond-save');
if(rs){rs.addEventListener('click',function(){send('respond',null,rta?rta.value:'');});}
var restore=item.querySelector('.decision-restore');
if(restore&&ta){restore.addEventListener('click',function(e){e.preventDefault();ta.value=ta.getAttribute('data-original')||'';ta.focus();});}
var clearBtn=item.querySelector('.decision-clear');
if(clearBtn){clearBtn.addEventListener('click',function(){send(null);});}
});
updateProgress();
var closeBtn=document.getElementById('decision-close');
var skipBtn=document.getElementById('decision-close-skip');
var ctick=document.getElementById('decision-close-tick');
var cerr=document.getElementById('decision-close-error');
function closed(){show(ctick,true);show(cerr,false);show(skipBtn,false);
var st=document.getElementById('batch-status');if(st){st.textContent='decided';}}
// A close is refused (409) while items are still blank. The skip is then a
// second, explicit click — never something the first button did quietly.
function doClose(skip){
var body={batch_id:BATCH_ID,close:true};
if(skip){body.skip_undecided=true;body.decided_by='self-declared:owner';
body.skip_note='整批完成時明確略過（未作答）';}
post(body).then(function(res){
if(res.ok){closed();return;}
show(cerr,true);
cerr.textContent=(res.data&&res.data.error)||'標記完成失敗';
var un=res.data&&res.data.undecided;
if(un&&un.length&&skipBtn){skipBtn.textContent='把這 '+un.length+' 項記成「略過」並完成';show(skipBtn,true);}
});}
if(closeBtn){closeBtn.addEventListener('click',function(){show(skipBtn,false);doClose(false);});}
if(skipBtn){skipBtn.addEventListener('click',function(){doClose(true);});}
var copyBtn=document.getElementById('decision-copy-notify');
if(copyBtn){copyBtn.addEventListener('click',function(){
var ta=document.getElementById('decision-notify-text');var tick=document.getElementById('decision-copy-tick');
var txt=ta?ta.value:'';
function done(){if(tick){tick.hidden=false;setTimeout(function(){tick.hidden=true;},2200);}}
function fallback(){if(ta){ta.focus();ta.select();try{document.execCommand('copy');}catch(e){}}done();}
if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(txt).then(done,fallback);}else{fallback();}
});}
})();
"""


def _decision_progress(items: list) -> dict[str, int]:
    """Live counts for the sticky progress header (also recomputed in the JS)."""
    counts = {"total": 0, "decided": 0, "approve": 0, "reject": 0, "pick": 0, "edit": 0,
              "skipped": 0}
    for item in items:
        if not isinstance(item, dict):
            continue
        counts["total"] += 1
        decision = item.get("decision")
        action = decision.get("action") if isinstance(decision, dict) else None
        if action in DECISION_ACTIONS:
            counts["decided"] += 1
            counts[{"pick-multi": "pick", "respond": "edit"}.get(action, action)] += 1
    counts["undecided"] = counts["total"] - counts["decided"]
    return counts


def _decision_progress_text(c: dict) -> str:
    # 略過 is only printed when it happened — a standing "略過 0" would advertise
    # skipping as a normal move on every board.
    skipped = f' · 略過 {c["skipped"]}' if c.get("skipped") else ""
    return (
        f'已決定 {c["decided"]} / {c["total"]} · 核准 {c["approve"]} · 退回 {c["reject"]}'
        f' · 已選 {c["pick"]} · 編輯 {c["edit"]}{skipped} · 未處理 {c["undecided"]}'
    )


def _render_decision_item(item: dict, index: int) -> str:
    item_id = str(item.get("id") or f"item-{index + 1}")
    id_attr = html.escape(item_id, quote=True)
    content_md = item.get("content_md")
    content_md = content_md if isinstance(content_md, str) else ""
    content_html = _md_to_html(content_md)

    recommendation = item.get("recommendation") if isinstance(item.get("recommendation"), dict) else {}
    rec_action = recommendation.get("action")
    rec_option = recommendation.get("option")
    options = item.get("options") if isinstance(item.get("options"), list) else None
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else None

    # An existing decision (e.g. from a prior session) seeds the initial visual
    # state; a fresh batch has decision:null everywhere -> every item starts 未處理.
    init_action = decision.get("action") if decision else None
    if init_action not in DECISION_ACTIONS:
        init_action = ""
    init_option = decision.get("option") if (decision and init_action == "pick") else None
    # Multi-select: an item flagged `multiple` renders its options as checkboxes
    # (action "pick-multi", a set of indices) instead of one-of-N radios. Additive
    # and opt-in — items without the flag render exactly as before.
    multiple = bool(item.get("multiple")) and options is not None
    init_selected: list[int] = []
    if multiple and decision and init_action == "pick-multi":
        raw_sel = decision.get("options_selected")
        if isinstance(raw_sel, list):
            init_selected = [
                i for i in raw_sel
                if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(options)
            ]
    init_note = decision.get("note") if decision else None
    init_note = init_note if isinstance(init_note, str) else ""
    # An edit decision shows the human's saved text; otherwise the agent's draft.
    if init_action == "edit" and decision and isinstance(decision.get("edited_text"), str):
        edit_initial = decision["edited_text"]
    else:
        edit_initial = content_md
    # "Respond" escape: the human's own answer on an option card (action "respond").
    respond_initial = decision.get("text") if (decision and init_action == "respond") else None
    respond_initial = respond_initial if isinstance(respond_initial, str) else ""
    respond_open = " open" if init_action == "respond" else ""

    def rec_badge(action: str) -> str:
        return ' <span class="decision-rec-badge">建議</span>' if rec_action == action else ""

    option_attr = (
        f' data-option="{init_option}"'
        if isinstance(init_option, int) and not isinstance(init_option, bool)
        else ""
    )
    selected_attr = (
        f' data-selected="{",".join(str(i) for i in init_selected)}"' if init_selected else ""
    )
    open_attr = " open" if (rec_action == "edit" or init_action == "edit") else ""

    parts: list[str] = []
    parts.append(
        f'<section class="decision-item" data-item-id="{id_attr}" '
        f'data-decision="{html.escape(init_action, quote=True)}"{option_attr}{selected_attr}>'
    )
    parts.append(f'<div class="decision-content">{content_html}</div>')
    # Collapsed one-line summary: shown once decided; click to re-expand + change.
    parts.append('<button type="button" class="decision-summary" hidden></button>')

    parts.append('<div class="decision-controls">')

    if options and multiple:
        # Pick-many-of-N: checkbox toggles. Each click flips one option and the JS
        # POSTs the whole current selection set (action "pick-multi"); clearing the
        # last one returns the item to 未處理.
        parts.append('<div class="decision-options" role="group" aria-label="可複選，勾幾個都行">')
        for opt_index, option in enumerate(options):
            text = _decision_option_text(option)
            checked = opt_index in init_selected
            badge = (
                ' <span class="decision-rec-badge">建議</span>'
                if (rec_action == "pick-multi" and isinstance(rec_option, list) and opt_index in rec_option)
                else ""
            )
            parts.append(
                f'<button type="button" class="decision-opt decision-optm" data-action="pick-multi" '
                f'role="checkbox" aria-checked="{"true" if checked else "false"}" '
                f'data-option="{opt_index}" data-label="{html.escape(text, quote=True)}">'
                f'{html.escape(text)}{badge}</button>'
            )
            preview = _decision_option_preview(option)
            if preview:
                parts.append(f'<pre class="decision-opt-preview">{html.escape(preview)}</pre>')
        parts.append('</div>')
    elif options:
        # Pick-one-of-N: radio-style toggle buttons. Clicking the selected one
        # again clears it; clicking another switches (handled in the JS).
        parts.append('<div class="decision-options" role="group" aria-label="選一個選項">')
        for opt_index, option in enumerate(options):
            text = _decision_option_text(option)
            badge = (
                ' <span class="decision-rec-badge">建議</span>'
                if (rec_action == "pick" and rec_option == opt_index)
                else ""
            )
            parts.append(
                f'<button type="button" class="decision-opt" data-action="pick" '
                f'data-option="{opt_index}" data-label="{html.escape(text, quote=True)}">'
                f'{html.escape(text)}{badge}</button>'
            )
            preview = _decision_option_preview(option)
            if preview:
                parts.append(f'<pre class="decision-opt-preview">{html.escape(preview)}</pre>')
        parts.append('</div>')
    else:
        # Approve / reject two-segment toggle (clicking the chosen side clears).
        parts.append('<div class="decision-toggle" role="group" aria-label="核准或退回">')
        parts.append(f'<button type="button" class="decision-seg seg-approve" data-action="approve">核准{rec_badge("approve")}</button>')
        parts.append(f'<button type="button" class="decision-seg seg-reject" data-action="reject">退回{rec_badge("reject")}</button>')
        parts.append('</div>')

        # Editable text stays editable after saving; 還原原稿 restores the draft.
        parts.append(f'<details class="decision-edit"{open_attr}>')
        parts.append(f'<summary>修改文字{rec_badge("edit")}</summary>')
        parts.append(
            f'<textarea class="decision-edit-text" rows="4" '
            f'data-original="{html.escape(content_md, quote=True)}">{html.escape(edit_initial)}</textarea>'
        )
        parts.append('<div class="decision-edit-actions">')
        parts.append('<button type="button" class="decision-btn decision-edit-save" data-action="edit">儲存修改</button>')
        parts.append('<a href="#" class="decision-restore">還原原稿</a>')
        parts.append('</div>')
        parts.append('</details>')

    if options:
        # "Respond" escape (HITL 4th verb): on an option card, let the human reject
        # the listed options and type their own answer -> decision {action:"respond",text}.
        parts.append(f'<details class="decision-respond"{respond_open}>')
        parts.append('<summary>以上皆非，自己打</summary>')
        parts.append(
            f'<textarea class="decision-respond-text" rows="3" '
            f'placeholder="直接給你的答案（不選上面的選項）">{html.escape(respond_initial)}</textarea>'
        )
        parts.append('<div class="decision-edit-actions">')
        parts.append('<button type="button" class="decision-btn decision-respond-save" data-action="respond">用我的答案</button>')
        parts.append('</div>')
        parts.append('</details>')

    # Optional note, attached to whichever decision is saved next.
    note_val = f' value="{html.escape(init_note, quote=True)}"' if init_note else ""
    parts.append('<div class="decision-note">')
    parts.append(f'<input type="text" class="decision-note-text" placeholder="備註（選填）"{note_val}>')
    parts.append('</div>')

    parts.append('<div class="decision-actions-row">')
    parts.append('<button type="button" class="decision-clear" data-action="clear">清除（回未處理）</button>')
    parts.append('<span class="decision-saved" hidden></span>')
    parts.append('<span class="decision-error" hidden></span>')
    parts.append('</div>')

    parts.append('</div>')  # .decision-controls
    parts.append('</section>')
    return "".join(parts)


def _render_decision_board(batch_id: object) -> str | None:
    """Server-rendered decision board page, or None when the batch is missing.

    Follows the _render_* pattern: builds HTML with _layout + the engine's
    server-side markdown renderer. Vanilla inline JS only — no framework, no
    build step, and no MEMORY_* code.
    """
    batch = _load_decision_batch(batch_id)
    if batch is None:
        return None
    assert isinstance(batch_id, str)

    title = str(batch.get("title") or batch_id)
    status = str(batch.get("status") or "open")
    created_by = str(batch.get("created_by") or "")
    scope = str(batch.get("scope") or "")
    items = batch.get("items") if isinstance(batch.get("items"), list) else []

    item_dicts = [item for item in items if isinstance(item, dict)]
    counts = _decision_progress(item_dicts)
    n_items = counts["total"]

    header = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 決策板</div>'
        f'<h1>{html.escape(title)}</h1>'
        '<p class="summary">'
        f'批次 <code>{html.escape(batch_id)}</code>'
        f'{" · 來自 " + html.escape(created_by) if created_by else ""}'
        f'{" · scope=" + html.escape(scope) if scope else ""}'
        f' · 狀態 <span id="batch-status">{html.escape(status)}</span></p>'
        # The standing caveat, as the same alert panel the dashboard uses.
        #
        # The BARE `ALERT`, not `ALERT_WARNING`: this note is on every board,
        # every time, and a permanent amber banner is a warning that stops being
        # read. It takes base-200 plus a visible edge, and the caution INK below
        # (`.decision-scope-note{color}`) is what marks it as a caution.
        #
        # It is also the one thing on this page a daisyUI class actually
        # changes. Every other element here — `.decision-item`, `.decision-opt`,
        # `.decision-seg`, `.decision-btn` — already carries an unlayered
        # `.decision-*` rule declaring its own border, radius, padding and
        # background, and an unlayered rule outranks any layered component
        # style. Measured, not assumed (see the `.button-link` and
        # `.catalog-chip` probes): adding `card`/`btn` to those changes at most
        # a pixel of height. It would be class names that do nothing, on the one
        # live surface where markup churn is least welcome.
        f'<p class="summary decision-scope-note {ALERT}">scope 只是標記，不是授權：'
        '此處的核准絕不等於金流／對外發佈／不可逆動作的授權。</p>'
        '<p class="summary decision-help">每一項按一下就自動存好（會出現「已儲存 ✓」）。'
        '想改就按另一個選項；再按同一個不會取消它。要退回未處理，用該項的「清除」。'
        '全部按完，最後按最下面那顆告訴 agent 可以讀了。</p>'
    )

    # Sticky live progress — the reframe that stops 完成 reading as "submit all".
    progress = (
        '<div class="decision-progress" id="decision-progress">'
        f'<span id="decision-progress-line">{html.escape(_decision_progress_text(counts))}</span>'
        '</div>'
    )

    items_html = "".join(
        _render_decision_item(item, index)
        for index, item in enumerate(item_dicts)
    )

    # Copy-to-clipboard prompt: there is no auto-notify, so the human pastes this
    # to the agent (terminal / DC) to say "this batch is decided, go read it".
    notify_prompt = (
        f'決策板「{title}」已決完，請讀 core/brainhub/decisions/{batch_id}.json 逐項執行'
        f'（每項 decision 為最終：pick 的 option／pick-multi 的 options_selected／edit 的 edited_text／'
        f'respond 的 text／note 皆以檔案為準）。板：http://{BIND_HOST}:3000/decide/{batch_id}'
    )
    close_row = (
        '<div class="decision-close-row">'
        '<p class="decision-close-explain">上面每一項都已經自動存好了。'
        '這顆按鈕不是送出決定，只是告訴 agent「整批我看完了，可以去讀」。</p>'
        f'<button type="button" id="decision-close" data-batch-id="{html.escape(batch_id, quote=True)}">'
        '整批標記完成（告訴 agent 可以讀了）</button>'
        f'<p class="decision-all-done" id="decision-all-done" hidden>全部 {n_items} 項已決定 ✓ — 跟 agent 說「去讀」就行</p>'
        '<span id="decision-close-tick" hidden>✓ 已標記完成，agent 可以讀了</span>'
        '<span id="decision-close-error" hidden></span>'
        # Only appears after the server refuses a close that still has blanks.
        # Skipping is then one deliberate click, and it writes a real "skipped"
        # outcome — the file never carries a blank behind a decided status.
        '<button type="button" id="decision-close-skip" hidden></button>'
        '<div class="decision-copy-row">'
        '<button type="button" id="decision-copy-notify" class="decision-copy-notify">複製「通知 agent」訊息</button>'
        '<span id="decision-copy-tick" hidden>✓ 已複製，貼到 terminal／DC 給 agent 即可</span>'
        '</div>'
        f'<textarea id="decision-notify-text" readonly aria-hidden="true" '
        f'style="position:absolute;left:-9999px;top:0;width:1px;height:1px;">{html.escape(notify_prompt)}</textarea>'
        '</div>'
    )

    style = (
        "<style>"
        # Mobile-first, single column; all colors from BrainHub's design tokens.
        ".decision-item{border:1px solid var(--border);border-left:4px solid var(--border);"
        "border-radius:10px;padding:16px;margin:16px 0;background:var(--surface);}"
        '.decision-item[data-decision="approve"]{border-left-color:var(--success-border);background:var(--success-bg);}'
        '.decision-item[data-decision="reject"]{border-left-color:var(--caution-border);background:var(--caution-bg);}'
        '.decision-item[data-decision="pick"]{border-left-color:var(--accent);background:var(--surface-muted);}'
        '.decision-item[data-decision="edit"]{border-left-color:var(--accent);background:var(--surface-muted);}'
        # Skipped reads as an outcome, but a muted one — it must not look like an
        # answered item, and it must not look like a blank either.
        '.decision-item[data-decision="skipped"]{border-left-style:dashed;'
        "border-left-color:var(--muted);background:var(--surface-muted);}"
        '.decision-item[data-savestate="failed"]{border-left-style:dashed;border-left-color:var(--accent);}'
        ".decision-content{margin-bottom:12px;}"
        ".decision-summary{display:block;width:100%;text-align:left;min-height:44px;"
        "padding:12px 14px;font-size:1rem;font-weight:600;color:var(--text);"
        "background:var(--button-bg);border:1px solid var(--border-strong);border-radius:8px;cursor:pointer;}"
        '.decision-summary::after{content:" （點一下修改）";font-weight:400;'
        "color:var(--muted);font-size:0.85rem;}"
        # An author display rule beats the UA [hidden] rule — re-assert hidden for
        # the elements that carry both, so they stay hidden until the JS reveals.
        ".decision-summary[hidden],#decision-close-tick[hidden],"
        "#decision-close-error[hidden],#decision-close-skip[hidden]{display:none;}"
        ".decision-controls{display:flex;flex-direction:column;gap:12px;}"
        ".decision-toggle{display:flex;gap:10px;}"
        ".decision-seg{flex:1;min-height:44px;padding:10px 12px;font-size:1rem;cursor:pointer;"
        "color:var(--button-text);background:var(--button-bg);"
        "border:1px solid var(--border-strong);border-radius:8px;}"
        ".decision-seg:hover{background:var(--button-hover);}"
        ".decision-seg.seg-approve.chosen{background:var(--ok);color:var(--accent-fg);border-color:var(--ok);}"
        ".decision-seg.seg-reject.chosen{background:var(--caution);color:var(--accent-fg);border-color:var(--caution);}"
        ".decision-options{display:flex;flex-direction:column;gap:10px;}"
        ".decision-opt{display:block;width:100%;text-align:left;min-height:44px;padding:12px 14px;"
        "font-size:1rem;cursor:pointer;color:var(--button-text);background:var(--button-bg);"
        "border:1px solid var(--border-strong);border-radius:8px;}"
        ".decision-opt:hover{background:var(--button-hover);}"
        ".decision-opt.chosen{background:var(--accent);color:var(--accent-fg);border-color:var(--accent);}"
        ".decision-optm::before{content:'☐ ';margin-right:4px;font-weight:700;}"
        ".decision-optm.chosen::before{content:'☑ ';}"
        ".decision-opt-preview{margin:2px 0 8px;padding:8px 10px;background:var(--chip-bg);"
        "border:1px solid var(--border);border-radius:6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
        "font-size:0.82rem;white-space:pre-wrap;overflow-x:auto;color:var(--text);}"
        ".dim{opacity:0.45;}"
        ".decision-edit>summary{cursor:pointer;font-weight:600;min-height:36px;padding:8px 0;color:var(--text);}"
        ".decision-respond>summary{cursor:pointer;font-weight:600;min-height:36px;padding:8px 0;color:var(--text);}"
        ".decision-respond-text{width:100%;box-sizing:border-box;font-size:1rem;padding:10px;border:1px solid var(--border-strong);border-radius:8px;background:var(--bg);color:var(--text);}"
        ".decision-edit-text{width:100%;box-sizing:border-box;font-size:1rem;padding:10px;"
        "border:1px solid var(--border-strong);border-radius:8px;background:var(--bg);color:var(--text);}"
        ".decision-edit-actions{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:8px;}"
        ".decision-btn{min-height:44px;padding:10px 16px;font-size:1rem;cursor:pointer;"
        "color:var(--button-text);background:var(--button-bg);"
        "border:1px solid var(--border-strong);border-radius:8px;}"
        ".decision-btn:hover{background:var(--button-hover);}"
        ".decision-btn.chosen{background:var(--accent);color:var(--accent-fg);border-color:var(--accent);}"
        ".decision-restore{color:var(--link);text-decoration:underline;min-height:44px;"
        "display:inline-flex;align-items:center;}"
        ".decision-note-text{width:100%;box-sizing:border-box;min-height:44px;font-size:1rem;padding:10px;"
        "border:1px solid var(--border-strong);border-radius:8px;background:var(--bg);color:var(--text);}"
        ".decision-actions-row{display:flex;flex-wrap:wrap;gap:14px;align-items:center;}"
        ".decision-clear{min-height:44px;padding:10px 16px;font-size:0.95rem;cursor:pointer;"
        "color:var(--muted);background:var(--button-bg);border:1px solid var(--border);border-radius:8px;}"
        ".decision-clear:hover{background:var(--button-hover);}"
        # 「建議」 — the one mark on this page that has to be found without
        # looking for it. Every option on a card is written to be choosable, so
        # the card only does its job (a decision, not a pile of options) if the
        # recommended one announces itself; grey-on-grey and it degrades back
        # into "you figure it out", which is the complaint the card was built
        # to answer. It ran on --chip-bg/--muted, i.e. the same neutrals as the
        # furniture around it. Moved onto the caution/gold family, which the
        # shell already defines a dark-mode pair for, so it reads as a mark
        # rather than as more chrome in both themes.
        # Still a badge, deliberately: the option button itself is untouched, so
        # nothing here can disturb the six actions bound to it.
        ".decision-rec-badge{font-size:11px;font-weight:700;letter-spacing:0.03em;"
        "background:var(--caution-bg-2);color:var(--caution-fg);"
        "border:1px solid var(--caution-border);"
        "border-radius:4px;padding:2px 7px;margin-left:6px;}"
        ".decision-saved{color:var(--ok-fg);font-weight:600;}"
        ".decision-saved.flash{animation:decisionSaved 1.6s ease-out;}"
        "@keyframes decisionSaved{0%{opacity:0;}15%{opacity:1;}70%{opacity:1;}100%{opacity:0;}}"
        ".decision-error{color:var(--accent);font-weight:600;cursor:pointer;text-decoration:underline;}"
        ".decision-progress{position:sticky;top:0;z-index:10;background:var(--bg);"
        "border-bottom:1px solid var(--border);padding:10px 0;margin:8px 0 4px;"
        "font-size:0.9rem;font-weight:600;color:var(--text);line-height:1.5;}"
        ".decision-help{color:var(--muted);}"
        # Ink only. The panel (surface, edge, radius, padding) is the `alert`
# component — restating any of it here would outrank the component and
# put this note quietly out of step with the dashboard again.
        ".decision-scope-note{color:var(--caution-fg);}"
        ".decision-close-row{margin-top:28px;padding-top:16px;border-top:1px solid var(--border);}"
        ".decision-copy-row{margin-top:12px;}"
        ".decision-copy-notify{min-height:44px;padding:10px 16px;font-size:0.95rem;cursor:pointer;"
        "color:var(--button-text);background:var(--button-bg);border:1px solid var(--border-strong);border-radius:8px;}"
        ".decision-copy-notify:hover{background:var(--button-hover);}"
        "#decision-copy-tick{display:inline-block;margin-left:10px;color:var(--ok-fg);font-weight:600;}"
        "#decision-copy-tick[hidden]{display:none;}"
        ".decision-close-explain{color:var(--muted);font-size:0.9rem;margin:0 0 12px;}"
        "#decision-close{min-height:48px;width:100%;padding:12px 16px;font-size:1rem;font-weight:600;"
        "cursor:pointer;color:var(--accent-fg);background:var(--accent);"
        "border:1px solid var(--accent);border-radius:10px;}"
        "#decision-close:hover{opacity:0.92;}"
        ".decision-all-done{color:var(--ok-fg);font-weight:600;margin:12px 0 0;}"
        "#decision-close-skip{display:block;margin-top:12px;min-height:44px;padding:10px 14px;"
        "font-size:0.95rem;font-weight:600;color:var(--text);background:var(--button-bg);"
        "border:1px solid var(--caution-border);border-radius:8px;cursor:pointer;}"
        "#decision-close-tick{display:inline-block;margin-top:12px;color:var(--ok-fg);font-weight:600;}"
        "#decision-close-error{display:inline-block;margin-top:12px;color:var(--accent);font-weight:600;}"
        "@media(min-width:640px){#decision-close{width:auto;}"
        ".decision-opt,.decision-summary{max-width:640px;}}"
        "</style>"
    )

    script_js = _DECISION_BOARD_JS.replace("__BATCH_ID__", json.dumps(batch_id))
    script = "<script>" + script_js + "</script>"

    body = header + progress + style + items_html + close_row + script
    return _layout(title, body, page_class="decision-board")


def _open_decision_batches() -> list[tuple[str, dict]]:
    """(batch_id, batch) for every decision batch not yet closed, newest first."""
    out: list[tuple[str, dict]] = []
    ddir = _decisions_dir()
    if ddir.is_dir():
        for path in ddir.glob("*.json"):
            try:
                batch = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(batch, dict) and batch.get("status") != "decided":
                out.append((path.stem, batch))
    out.sort(key=lambda pair: str(pair[1].get("created_at") or ""), reverse=True)
    return out


def _render_control_center() -> str:
    """Prototype control center (build-to-think): company status + every open
    decision surfaced on one native page. v0 = see-everything + link to decide;
    inline-decide is the next step if the direction is kept.
    """
    total_pending = 0
    cards: list[str] = []
    for batch_id, batch in _open_decision_batches():
        items = [it for it in (batch.get("items") or []) if isinstance(it, dict)]
        counts = _decision_progress(items)
        if counts["undecided"] == 0:
            continue  # exceptions only — a batch with nothing pending is not shown
        total_pending += counts["undecided"]
        rows = []
        for it in items:
            if isinstance(it.get("decision"), dict):
                continue
            first = str(it.get("content_md") or "").strip().splitlines()
            label = first[0].lstrip("# ").strip() if first else "(未命名項)"
            # Dashboard = scannable hints, not essays: strip markdown bold + BLUF
            # prefix and cap the length; full detail is one click away on the board.
            label = label.replace("**", "").replace("BLUF：", "").replace("BLUF:", "").strip()
            if len(label) > 32:
                label = label[:32] + "…"
            rows.append(f"<li>{html.escape(label)}</li>")
        cards.append(
            '<section class="cc-card">'
            '<div class="cc-head">'
            f"<h2>{html.escape(str(batch.get('title') or batch_id))}</h2>"
            f'<span class="cc-count">{counts["undecided"]} 待決</span>'
            "</div>"
            f'<ul class="cc-items">{"".join(rows)}</ul>'
            f'<a class="cc-decide" href="/decide/{html.escape(batch_id)}">去決策 →</a>'
            "</section>"
        )
    status = (
        f'<p class="cc-status"><strong>{total_pending}</strong> 項待決 · 跨 '
        f"<strong>{len(cards)}</strong> 個決策板</p>"
        if cards
        else '<p class="cc-status">目前沒有待決策 ✓（空＝健康）</p>'
    )
    intro = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 控制中心</div>'
        "<h1>控制中心</h1>"
        '<p class="summary decision-help">一頁看所有待你決的事；點「去決策」進該板決。'
        "（原型 v0；下一版可直接在這頁決。）</p>"
    )
    css = (
        "<style>"
        ".cc-status{font-size:1.05rem;font-weight:600;margin:8px 0 20px;}"
        ".cc-card{border:1px solid var(--border);border-left:4px solid var(--accent);"
        "border-radius:10px;padding:16px;margin:14px 0;background:var(--surface);}"
        ".cc-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;}"
        ".cc-head h2{margin:0;font-size:1.1rem;}"
        ".cc-count{flex-shrink:0;font-size:0.8rem;font-weight:700;color:var(--accent-fg);"
        "background:var(--accent);border-radius:999px;padding:3px 11px;white-space:nowrap;}"
        ".cc-items{margin:0 0 14px;padding-left:20px;color:var(--muted);font-size:0.92rem;}"
        ".cc-items li{margin:5px 0;}"
        ".cc-decide{display:inline-flex;align-items:center;min-height:40px;padding:8px 16px;"
        "font-weight:600;color:var(--accent-fg);background:var(--accent);border-radius:8px;"
        "text-decoration:none;}.cc-decide:hover{opacity:0.92;}"
        "</style>"
    )
    return _layout("控制中心", intro + css + status + "".join(cards), page_class="control-center")


# ---------------------------------------------------------------------------
# Status dashboard (SPoG) — data file in, brand-themed page out.
# ---------------------------------------------------------------------------

def _dashboard_path() -> Path:
    return WIKI_DIR.parent / DASHBOARD_DIRNAME / DASHBOARD_FILENAME


def _load_dashboard_data() -> tuple[dict | None, str]:
    """(data, reason). ``data`` is None when there is nothing renderable.

    A missing or broken file is an empty state, never a traceback: the page's
    derived half still has something true to show, and a 500 would hide it.
    """
    path = _dashboard_path()
    if not path.is_file():
        return None, "資料檔還不存在。"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"資料檔讀不到或不是合法 JSON：{exc}"
    if not isinstance(data, dict):
        return None, "資料檔最外層必須是一個 JSON object。"
    return data, ""


def _dashboard_decision_section() -> tuple[str, int]:
    """(section_html, pending_count) derived from decisions/ — never hand-kept.

    Same exceptions-only rule as the control center: a batch with nothing
    undecided is not news. This is the half of the dashboard that cannot rot,
    which is exactly why it is computed here rather than typed into the JSON.
    """
    items: list[dict[str, object]] = []
    pending = 0
    for batch_id, batch in _open_decision_batches():
        batch_items = [it for it in (batch.get("items") or []) if isinstance(it, dict)]
        counts = _decision_progress(batch_items)
        if counts["undecided"] == 0:
            continue
        pending += counts["undecided"]
        items.append({
            "text": str(batch.get("title") or batch_id),
            "owner": str(batch.get("created_by") or ""),
            "state": "blocked",
            "note": f'{counts["undecided"]} 項待決 · 共 {counts["total"]} 項',
            "href": f"/decide/{batch_id}",
        })
    section = _core_render_priority_section(
        "待決策（自動）",
        "直接讀 decisions/，不吃資料檔 ⇒ 這一區不會過期",
        items,
    )
    return section, pending


def _dashboard_section_tone(items: list[dict]) -> str:
    states = [str(it.get("state") or "").strip().lower() for it in items if isinstance(it, dict)]
    if "blocked" in states:
        return "caution"
    if states and all(state == "done" for state in states):
        return "ok"
    return "neutral"


def _dashboard_history(data: dict | None, pending: int) -> tuple[dict, list[dict]]:
    """(current_snapshot, history) — records one point per DATA VERSION.

    Called from the render because that is the surface that already knows both
    halves of a point: the file's section counts and the ``decisions/``-derived
    pending count. It is safe there because ``record_snapshot`` is idempotent on
    the board's ``updated_at`` — a thousand readers of an unchanged board write
    nothing. A cron can call the same pair without going through this function.

    A missing or broken data file records NOTHING. Writing a row of zeros for a
    board that failed to load would put a fabricated "everything cleared" point
    into the trend, and no reader could tell it from a real one.
    """
    snapshot = _core_build_snapshot(data, pending=pending)
    path = _core_history_path(_dashboard_path().parent)
    if data is None:
        return snapshot, _core_read_history(path)
    return snapshot, _core_record_snapshot(path, snapshot)


def _render_dashboard() -> str:
    """The company status board. Data-driven, brand-themed, self-dating."""
    data, reason = _load_dashboard_data()
    title = DASHBOARD_TITLE
    updated_at: object = None
    sections: list[dict] = []
    if data is not None:
        title = str(data.get("title") or DASHBOARD_TITLE)
        updated_at = data.get("updated_at")
        sections = [s for s in (data.get("sections") or []) if isinstance(s, dict)]

    banner = _core_render_staleness_banner(updated_at)
    decision_section, pending = _dashboard_decision_section()

    # The time dimension. Before this the board could say "P1 is 4" and had no
    # way to say whether 4 was better than last week — the single largest thing
    # it did not answer.
    snapshot, history = _dashboard_history(data, pending)
    baseline = _core_history_baseline_for(history, _core_snapshot_key(snapshot))
    # {} when there is no earlier point, which the tiles render as no delta at
    # all rather than as ±0.
    deltas = _core_compute_deltas(snapshot, baseline)
    series, x_labels, omitted = _core_trend_series(history)
    trend_section = _core_render_trend_section(
        series, x_labels, omitted=omitted, history_hint=_core_history_filename)

    tiles = []
    for section in sections:
        section_items = [it for it in (section.get("items") or []) if isinstance(it, dict)]
        # Same key the snapshot filed the count under, so a tile and its delta
        # cannot end up describing different rows.
        key = str(section.get("id") or section.get("title") or "").strip()
        tiles.append(_core_render_kpi_tile(
            key or "—",
            len(section_items),
            _dashboard_section_tone(section_items),
            deltas.get(key),
        ))
    tiles.append(_core_render_kpi_tile(
        "待決策（BH）", pending, "caution" if pending else "ok",
        deltas.get(_core_pending_key)))

    body_sections = [
        _core_render_priority_section(
            section.get("title") or section.get("id"),
            section.get("subtitle", ""),
            [it for it in (section.get("items") or []) if isinstance(it, dict)],
        )
        for section in sections
    ]
    if data is None:
        body_sections.insert(0, _core_render_dashboard_empty_state(_dashboard_path(), reason))

    # Last on the page, following the report library's own placement for the
    # honest-limits card: it is a statement about everything above it.
    bounds_section = _core_render_bounds_section(
        [b for b in ((data or {}).get("bounds") or []) if isinstance(b, dict)])

    intro = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 公司狀況</div>'
        f"<h1>{html.escape(title)}</h1>"
        '<p class="summary decision-help">從 '
        f"<code>{html.escape(str(_dashboard_path()))}</code> 渲染；"
        "「待決策」區直接讀 decisions/。上方橫幅顯示資料年齡——過 48 小時會警告。"
        f"每次資料更新會往 <code>{html.escape(_core_history_filename)}</code> "
        "追加一列計數，趨勢圖與 ↑↓ 差值都從那裡來。</p>"
    )
    body = (
        intro
        + _core_dashboard_css
        + banner
        + _core_render_kpi_row(tiles)
        + trend_section
        + decision_section
        + "".join(body_sections)
        + bounds_section
    )
    return _layout(title, body, page_class="dashboard")


def _capture_records(limit: int = 12, project: str | None = None) -> list[dict[str, object]]:
    root = WIKI_DIR.parent
    return _core_capture_records(
        root,
        limit=limit,
        project=project,
        commands_for=lambda rel_path: _core_cli_capture_commands(rel_path, root),
    )


def _capture_inbox(limit: int = 20, project: str | None = None) -> dict[str, object]:
    return _core_capture_inbox(
        WIKI_DIR.parent,
        limit=limit,
        project=project,
        commands_for=lambda rel_path: _core_cli_capture_commands(rel_path, WIKI_DIR.parent),
    )


def _capture_review_summary(project: str | None = None, limit: int = 3) -> dict[str, object]:
    project_name = _core_normalize_project(project)
    summary = _core_capture_review_summary(
        WIKI_DIR.parent,
        limit=limit,
        project=project_name,
        commands_for=lambda rel_path: _core_cli_capture_commands(rel_path, WIKI_DIR.parent),
    )
    project_query = f"?project={urllib.parse.quote(project_name, safe='')}" if project_name else ""
    project_arg = f' --project "{project_name}"' if project_name else ""
    summary["href"] = f"/captures{project_query}"
    summary["command"] = f'python3 brainhub_engine.py capture-inbox "{WIKI_DIR.parent}"{project_arg}'
    return summary


def _memory_brief(query: str = "", limit: int = 6, project: str | None = None) -> dict[str, object]:
    limit = max(1, min(limit, 20))
    project_name = _core_normalize_project(project)
    payload = _core_memory_brief(
        _memory_records(), query=query, limit=limit,
        review_command="review-memory", project=project_name,
        command_target=WIKI_DIR.parent,
    )
    return _core_add_capture_review_to_brief(
        payload,
        _capture_review_summary(project=project_name, limit=min(limit, 10)),
    )


def _memory_dashboard(limit: int = 12, project: str | None = None) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    project_name = _core_normalize_project(project)
    records = _project_visible_records(project_name)
    active_records = [record for record in records if _is_active_memory(record)]
    archived_records = [
        record for record in records
        if str(record.get("status") or "").lower() == "archived"
    ]
    recent_active = sorted(active_records, key=_memory_activity_key, reverse=True)
    recent_updates = sorted(
        [record for record in records if str(record.get("updated_at") or "").strip()],
        key=lambda record: (
            str(record.get("updated_at") or ""),
            str(record.get("title") or "").lower(),
        ),
        reverse=True,
    )
    archived = sorted(archived_records, key=_memory_activity_key, reverse=True)
    inbox = _memory_inbox(limit=limit, project=project_name)
    review_count = inbox["review_count"]
    updated_count = len(recent_updates)
    archived_count = len(archived_records)
    captures = _capture_records(limit=limit, project=project_name)
    capture_warning_count = sum(1 for capture in captures if capture["warning_count"])
    return {
        "memory_count": len(records),
        "active_count": len(active_records),
        "review_count": review_count,
        "archived_count": archived_count,
        "updated_count": updated_count,
        "capture_count": len(captures),
        "capture_warning_count": capture_warning_count,
        "project": project_name,
        "by_type": _count_values(records, "memory_type"),
        "by_scope": _count_values(records, "scope"),
        "counts_by_severity": inbox["counts_by_severity"],
        "next_actions": _memory_dashboard_next_actions(
            memory_count=len(records),
            review_count=review_count,
            updated_count=updated_count,
            archived_count=archived_count,
            capture_count=len(captures),
            capture_warning_count=capture_warning_count,
        ),
        "active": [_memory_with_actions(record) for record in recent_active[:limit]],
        "review": [_memory_with_actions(record) for record in inbox["items"][:limit]],
        "recent_updates": [_memory_with_actions(record) for record in recent_updates[:limit]],
        "archived": [_memory_with_actions(record) for record in archived[:limit]],
        "captures": captures,
    }


def _memory_audit(limit: int = 10, project: str | None = None) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    project_name = _core_normalize_project(project)
    profile = _memory_profile(limit=limit, project=project_name)
    inbox = _memory_inbox(limit=limit, include_archived=True, project=project_name)
    captures = _capture_review_summary(project=project_name, limit=min(limit, 10))
    payload = _core_memory_audit_report(profile, inbox, captures, [], project=project_name)
    payload["next_actions"] = _core_memory_audit_next_actions(
        mode="web",
        inbox=inbox,
        captures=captures,
        risk_factors=payload["risk_factors"],
        project=str(payload["project"]),
        root=WIKI_DIR.parent,
    )
    return payload


def _memory_log(limit: int = 50, include_captures: bool = True) -> dict[str, object]:
    return _core_memory_log_payload(
        WIKI_DIR,
        limit=max(1, min(limit, 200)),
        include_captures=include_captures,
    )


def _memory_wins(limit: int = 6, project: str | None = None) -> dict[str, object]:
    return _core_memory_wins_payload(
        WIKI_DIR,
        limit=max(1, min(limit, 50)),
        project=project,
        records=_memory_records(),
    )


def _json_for_script(data) -> str:
    """Serialize JSON for direct embedding inside a <script> tag."""
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _safe_resolve(path: Path) -> Path | None:
    return _core_safe_resolve(path)


def _is_relative_to(path: Path, root: Path) -> bool:
    return _core_is_relative_to(path, root)


def _is_allowed_static_file(path: Path) -> bool:
    root = Path(__file__).parent.resolve()
    link_root = WIKI_DIR.parent.resolve()
    return _core_is_allowed_static_file(
        path,
        RAW_DIR,
        (
            link_root / "logo.svg",
            link_root / "logo.png",
            root / "logo.svg",
            root / "logo.png",
        ),
        RAW_STATIC_TYPES,
    )


def _brand_file(name: str) -> Path:
    link_asset = WIKI_DIR.parent / name
    if link_asset.exists():
        return link_asset
    return Path(__file__).parent / name


def _resolve_raw_static_path(url_fragment: str) -> tuple[Path | None, str | None]:
    return _core_resolve_raw_static_path(RAW_DIR, url_fragment, RAW_STATIC_TYPES)


def _proposal_sources(limit: int = 50) -> dict[str, object]:
    return _core_proposal_sources(
        RAW_DIR,
        suffixes=PROPOSAL_SOURCE_SUFFIXES,
        max_bytes=MAX_PROPOSAL_SOURCE_BYTES,
        limit=limit,
    )


def _artifact_catalog(kind: str | None = None) -> dict[str, object]:
    """List artifact provenance records without exposing artifact contents."""
    return _core_artifact_catalog(WIKI_DIR.parent, kind=kind)


def _artifacts_root() -> Path:
    """The confinement root for all servable artifacts under the served root."""
    return WIKI_DIR.parent / "artifacts"


# Resolved per request rather than at import: a machine can gain a browser (or an
# operator can set BRAINHUB_CHROME_PDF) without restarting the viewer. See
# brainhub_core/render/pdf.py for why discovery exists at all -- the previous
# default was one absolute path to an in-house wrapper, so on every other install
# the download-PDF button was present but could never work.
# Injected before </body> at PDF-render time so the capture is complete even for
# artifacts rendered before any reveal logic existed. Modern Chrome hides
# <details> content via content-visibility (NOT child display:none), so CSS
# alone can't force it open — a script sets `.open` on every <details> and
# un-hides every tab panel. CSS just hides the now-inert nav + PDF button.
_PDF_REVEAL = (
    "<style data-brainhub-pdf-reveal>"
    ".brainhub-pdf-button{display:none !important}"
    ".brainhub-interactive .ih-tabnav{display:none !important}"
    "</style>"
    "<script data-brainhub-pdf-reveal>(function(){"
    "document.querySelectorAll('details').forEach(function(d){d.open=true});"
    "document.querySelectorAll('.ih-tabpanel[hidden]').forEach(function(p){p.removeAttribute('hidden');});"
    "})();</script>"
)
# Injected into the served HTML (http only) so a pre-existing window.print button
# routes through the server-side PDF endpoint instead. New artifacts already ship
# this behavior; re-pointing the onclick here is idempotent for them.
_PDF_BUTTON_UPGRADE = (
    b"<script data-brainhub-pdf-upgrade>(function(){"
    b"var b=document.querySelector('.brainhub-pdf-button');"
    b"if(b&&location.protocol!=='file:'){b.onclick=function(){"
    b"var u=new URL(location.href);u.searchParams.set('format','pdf');location.assign(u);return false;};}"
    b"})();</script>"
)


def _inject_before_body_end(data, payload):
    """Insert ``payload`` immediately before the document's closing </body>.

    Splices at the LAST </body>, never the first. A self-contained artifact
    inlines its vendored JS (mermaid.min.js is ~3.5 MB), and that source
    contains the literal bytes ``</body>`` inside a JS string — DOMPurify's
    ``'<html ...><head></head><body>'+x+"</body></html>"`` template. Replacing
    the FIRST match therefore spliced a ``<script>...</script>`` INTO the middle
    of the vendored <script> block; its ``</script>`` closed that block early and
    the remaining ~3.3 MB of JS was reparsed as markup — a ~482,000 px page that
    crashes Chrome's screenshotter. Every mermaid artifact was broken this way
    from the moment the injector shipped (2026-07-12) until 2026-07-17, and no
    check went red: build returned ok/self_contained/sha256 and the file itself
    (file://, uninjected) rendered fine.

    Works on both str and bytes; returns ``data`` unchanged when there is no
    closing tag to splice at.
    """
    marker = b"</body>" if isinstance(data, bytes) else "</body>"
    idx = data.rfind(marker)
    if idx == -1:
        return data
    return data[:idx] + payload + data[idx:]


def _artifact_pdf_bytes(artifact_path: Path) -> bytes | None:
    """Render a self-contained artifact HTML to PDF via headless chrome
    (``tools/chrome/chrome-pdf``, which honors the artifact's own @media print
    CSS for margins/colors). Injects :data:`_PDF_REVEAL_STYLE` so collapsed
    content appears. Returns None on any failure so the caller answers 404.
    Generated fresh per request (no cache) — chrome spawn is a few seconds and
    the viewer is internal/low-traffic."""
    import subprocess
    import tempfile
    try:
        html_text = artifact_path.read_text(encoding="utf-8")
        injected = (
            _inject_before_body_end(html_text, _PDF_REVEAL)
            if "</body>" in html_text
            else html_text + _PDF_REVEAL
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "artifact.html"
            src.write_text(injected, encoding="utf-8")
            out = Path(td) / "artifact.pdf"
            renderer = _core_find_pdf_renderer()
            if renderer is None:
                print(f"warning: {_core_pdf_unavailable_reason()}", file=sys.stderr)
                return None
            subprocess.run(
                renderer.command(src, out),
                check=True, capture_output=True, timeout=120,
            )
            if out.exists() and out.stat().st_size > 0:
                return out.read_bytes()
    except Exception:
        pass
    return None


def _resolve_artifact_path(subpath: str) -> Path | None:
    """Resolve /artifact/<subdir>/<name> to a confined .html artifact file.

    Path-confinement reuses web_http.safe_resolve/is_relative_to: the resolved
    target must stay under <root>/artifacts/, sit exactly one known artifact
    subdir deep (charts/html/reports/exports), and be an existing .html file.
    Everything else (traversal, encoded traversal, unknown dir, non-html,
    missing) returns None so the caller answers 404.
    """
    decoded = urllib.parse.unquote(subpath or "").lstrip("/")
    if not decoded or "\x00" in decoded:
        return None
    artifacts_root = _safe_resolve(_artifacts_root())
    candidate = _safe_resolve(_artifacts_root() / decoded)
    if not artifacts_root or not candidate:
        return None
    if not _is_relative_to(candidate, artifacts_root):
        return None
    try:
        rel = candidate.relative_to(artifacts_root)
    except ValueError:
        return None
    if len(rel.parts) != 2 or rel.parts[0] not in ARTIFACT_SUBDIRS:
        return None
    if candidate.suffix.lower() != ".html":
        return None
    if not (candidate.exists() and candidate.is_file()):
        return None
    return candidate


def _artifact_open_href(stored_path: str, sid: object = "") -> str:
    """Canonical artifact URL, falling back to the legacy <subdir>/<file> shape."""
    subpath = str(stored_path or "").removeprefix("artifacts/")
    normalized = _normalize_sid(sid)
    if not normalized:
        record = _artifact_record_by_subpath(subpath)
        normalized = _normalize_sid(record.get("sid")) if record else ""
    if normalized:
        return _canonical_path(_KIND_ARTIFACT, normalized, subpath.rsplit("/", 1)[-1])
    return _legacy_path(_KIND_ARTIFACT, subpath)


def _render_artifacts():
    return _core_render_artifacts_page(
        _artifact_catalog(),
        layout=_layout,
        artifact_href=_artifact_open_href,
    )


def _document_pages() -> list[dict[str, object]]:
    """Published wiki documents (category/type == document) for the /documents list."""
    docs: list[dict[str, object]] = []
    for page in _get_all_pages():
        if str(page.get("category")) != "documents" and str(page.get("type")) != "document":
            continue
        name = str(page.get("name") or "")
        docs.append({
            "name": name,
            "title": str(page.get("title") or name),
            "href": _page_href(name),
            "date": str(page.get("date_updated") or page.get("date_published") or ""),
            "tags": page.get("tags") or [],
        })
    docs.sort(key=lambda doc: str(doc.get("title") or ""))
    return docs


def _render_documents():
    return _core_render_documents_page(_document_pages(), layout=_layout)


def _proposal_source_payload(source_path: str) -> tuple[dict[str, object], int]:
    return _core_proposal_source_payload(
        RAW_DIR,
        source_path,
        suffixes=PROPOSAL_SOURCE_SUFFIXES,
        max_bytes=MAX_PROPOSAL_SOURCE_BYTES,
    )


def _create_raw_source_payload(payload: dict[str, object]) -> tuple[dict[str, object], int]:
    return _core_create_raw_source_payload(
        WIKI_DIR.parent,
        WIKI_DIR,
        payload,
        max_bytes=MAX_RAW_SOURCE_BYTES,
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _md_to_html(md):
    return _core_markdown_to_html(md, page_href=_page_href)


# ---------------------------------------------------------------------------
# CSS + layout
# ---------------------------------------------------------------------------

def _memory_enabled() -> bool:
    return _core_memory_layer_enabled(WIKI_DIR.parent)


def _workspace_populated() -> bool:
    """Has this workspace got enough in it that the setup entries are done?

    Same threshold the home page branches on, read from web_home rather than
    restated, so the nav and the front door can never disagree about whether
    this install is still being set up. _get_all_pages() is mtime-cached, so
    this costs a list length per render, not a scan.
    """
    return len(_get_all_pages()) >= _core_ONBOARDING_PAGE_THRESHOLD


def _header_html():
    return _core_render_header_html(
        memory_enabled=_memory_enabled(), populated=_workspace_populated()
    )


def _footer_html():
    return _core_render_footer_html()


def _layout(title, body, page_class: str = ""):
    return _core_render_layout(
        title,
        body,
        page_class=page_class,
        memory_enabled=_memory_enabled(),
        populated=_workspace_populated(),
    )


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _render_memory_disabled():
    config_display = html.escape(str(_core_config_path(WIKI_DIR.parent)))
    return _layout(
        "記憶層未啟用",
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 記憶</div>'
        "<h1>記憶層未啟用</h1>"
        '<p class="summary">這個 workspace 只使用 wiki 文件層與 artifact；memory 層（remember / recall / 審核）已由設定停用。</p>'
        f'<p>啟用方式：把 <code>{config_display}</code> 裡的 <code>"memory_enabled"</code> 改為 <code>true</code>。</p>',
    )


def _render_home():
    return _core_render_home_page(
        _get_all_pages(),
        starter_prompts=_starter_prompts_payload(),
        page_href=_page_href,
        layout=_layout,
        memory_enabled=_memory_enabled(),
    )


def _starter_prompts_payload(project: str | None = None) -> dict[str, object]:
    return _core_starter_prompt_payload(WIKI_DIR, project=project)


def _render_prompts(project: str | None = None):
    return _core_render_prompts_page(_starter_prompts_payload(project=project), layout=_layout)


def _render_more():
    links = [
        ("/onboard", "上手引導", "健康度、第一則記憶、agent 連接與提示詞的首次設定檢查清單。"),
        ("/prompts", "提示詞", "入門提示詞與可複製的下一步指令。"),
        ("/propose", "草擬記憶", "把筆記變成僅供審核的記憶候選。"),
        ("/audit", "稽核", "檢視記憶健康度、待處理量、擷取紀錄與安全的下一步。"),
        ("/inbox", "待審清單", "確認、更新、封存或說明待審核的記憶。"),
        ("/captures", "擷取紀錄", "在接受之前先檢查已儲存的 raw 工作階段擷取紀錄。"),
        ("/profile", "記憶總覽", "依類型、範圍、狀態與新舊程度檢視 BrainHub 記得什麼。"),
        ("/wins", "成效", "顯示 BrainHub 記憶帶來成效的本機證據。"),
        ("/memory-log", "記憶異動紀錄", "不用開原始紀錄文字，也能看到最近的記憶生命週期變化。"),
        ("/page/log", "操作紀錄", "閱讀只增不改的 wiki 操作紀錄。"),
        ("/all", "所有頁面", "用篩選與分頁瀏覽分組的 wiki 頁面。"),
    ]
    cards = "".join(
        '<article class="memory-card">'
        f'<h2><a href="{html.escape(href, quote=True)}">{html.escape(title)}</a></h2>'
        f'<p>{html.escape(description)}</p>'
        "</article>"
        for href, title, description in links
    )
    return _layout(
        "更多",
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 更多</div>'
        "<h1>更多工具</h1>"
        '<p class="summary">進階的 BrainHub 檢視畫面：提示詞、提案審核、稽核、擷取紀錄與完整 wiki 瀏覽。</p>'
        f'<section class="memory-grid">{cards}</section>',
    )


def _render_page(page_path):
    text = page_path.read_text(encoding="utf-8", errors="replace")
    meta, body = _parse_frontmatter(text)
    body_html = _md_to_html(body)

    title = meta.get("title", "")
    if not title:
        m = re.search(r"^#\s+(.+)", body, re.MULTILINE)
        title = m.group(1) if m else page_path.stem

    rel = page_path.relative_to(WIKI_DIR)
    cat = rel.parts[0] if len(rel.parts) > 1 else ""
    raw_refs = _core_raw_source_refs(body) if cat == "sources" else []
    proposal_prompt = f"從 {raw_refs[0]} 草擬記憶" if raw_refs else ""
    query_prompt = f"跟 BrainHub 查詢 {title}"
    return _core_render_wiki_page(
        str(title),
        category=cat,
        meta=meta,
        body_html=body_html,
        layout=_layout,
        graph_href=_graph_href(page_path.stem),
        proposal_href=_proposal_href(raw_refs[0]) if raw_refs else "",
        proposal_prompt=proposal_prompt,
        query_prompt=query_prompt,
        related_pages=_related_pages_for(page_path.stem),
    )


def _related_pages_for(page_name: str, max_items: int = 8) -> list[dict[str, str]]:
    """Return a compact inbound/forward page list for the wiki page footer."""
    with _cache_lock:
        pages = _get_all_pages()
        page_by_name = {str(page.get("name") or ""): page for page in pages}
        backlinks, _ = _load_backlinks_index()
        inbound = list(backlinks.get("backlinks", {}).get(page_name, []))
        forward = list(_forward_links_index.get(page_name) or backlinks.get("forward", {}).get(page_name, []))
    related: list[dict[str, str]] = []
    seen = {page_name}

    def take(relationship: str, names: list[str], budget: int) -> None:
        for name in names:
            if budget <= 0 or len(related) >= max_items:
                return
            if name in seen or name not in page_by_name:
                continue
            seen.add(name)
            page = page_by_name[name]
            related.append({
                "name": name,
                "title": str(page.get("title") or name),
                "href": _page_href(name),
                "relationship": relationship,
            })
            budget -= 1

    # Inbound first, and with a reserved share of the slots.
    #
    # A hub page — someone's home page — is exactly the page whose inbound list
    # matters and exactly the page with the most outbound links, so a single
    # shared budget filled outbound-first buries the thing the reader came for.
    # `bh link <page> <home>` only writes the edge on the source page, so the
    # home page's own body never grows; this footer is where the other direction
    # becomes visible at all (tam, 2026-07-22: home pages reading "(暫無)" while
    # 24 pages pointed at them).
    take("links here", inbound, max(max_items - 2, max_items // 2))
    take("links out", forward, max_items)
    return related


def _render_all(query: dict[str, list[str]] | None = None):
    query = query or {}
    pages = _get_all_pages()
    total = len(pages)
    limit_raw = query.get("limit", ["250"])[0]
    offset_raw = query.get("offset", ["0"])[0]
    limit, limit_error = _core_parse_bounded_int(limit_raw, "limit", 250, 1, 500)
    offset, offset_error = _core_parse_bounded_int(offset_raw, "offset", 0, 0, 1000000)
    error = limit_error or offset_error
    if error:
        limit = 250
        offset = 0
    assert limit is not None
    assert offset is not None
    sorted_pages = sorted(pages, key=lambda x: x["title"])
    type_counts = Counter(str(page.get("type") or page.get("category") or "root") for page in sorted_pages)
    active_type = _query_text(query, "type", "page_type", max_len=80).lower()
    visible_pages = [
        page for page in sorted_pages
        if not active_type or str(page.get("type") or page.get("category") or "root").lower() == active_type
    ]
    total = len(visible_pages)
    window = visible_pages[offset:offset + limit]
    return _core_render_all_pages(
        window,
        total=total,
        limit=limit,
        offset=offset,
        page_href=_page_href,
        layout=_layout,
        error=error or "",
        type_counts=type_counts,
        active_type=active_type,
    )


def _render_memory_card(record: dict[str, object], include_issues: bool = False) -> str:
    return _core_render_memory_card(
        record,
        page_href=_page_href,
        action_hints=_memory_action_hints,
        include_issues=include_issues,
    )


def _render_memory_section(title: str, records: list[dict[str, object]], empty: str, href: str = "", include_issues: bool = False) -> str:
    return _core_render_memory_section(
        title,
        records,
        empty,
        page_href=_page_href,
        action_hints=_memory_action_hints,
        href=href,
        include_issues=include_issues,
    )


def _render_brief(query: str = "", project: str | None = None):
    return _core_render_brief_page(
        _memory_brief(query=query, limit=8, project=project),
        query,
        page_href=_page_href,
        action_hints=_memory_action_hints,
        layout=_layout,
    )


def _render_memory_dashboard(project: str | None = None):
    return _core_render_memory_dashboard_page(
        _memory_dashboard(limit=8, project=project),
        page_href=_page_href,
        action_hints=_memory_action_hints,
        layout=_layout,
    )


def _render_profile(project: str | None = None):
    return _core_render_profile_page(_memory_profile(limit=12, project=project), page_href=_page_href, layout=_layout)


def _render_memory_audit(project: str | None = None):
    return _core_render_memory_audit_page(
        _memory_audit(limit=10, project=project),
        page_href=_page_href,
        action_hints=_memory_action_hints,
        layout=_layout,
    )


def _render_captures(project: str | None = None):
    return _core_render_captures_page(_capture_inbox(limit=50, project=project), layout=_layout)


def _render_propose(project: str | None = None, source: str | None = None):
    return _core_render_propose_page(
        _clean_text_input(project, max_len=80),
        _clean_text_input(source, max_len=500),
        layout=_layout,
    )


def _render_ingest():
    return _core_render_ingest_page(_ingest_status(), page_href=_page_href, layout=_layout)


def _render_inbox(project: str | None = None):
    return _core_render_inbox_page(_memory_inbox(limit=50, project=project), page_href=_page_href, layout=_layout)


def _render_memory_log():
    return _core_render_memory_log_page(_memory_log(limit=100), layout=_layout)


def _render_memory_wins(project: str | None = None):
    return _core_render_memory_wins_page(
        _memory_wins(limit=8, project=project),
        page_href=_page_href,
        layout=_layout,
    )


def _render_explain_memory(identifier: str):
    try:
        explanation = _memory_explanation(identifier)
    except ValueError as exc:
        return _layout("記憶說明", f'<h1>找不到記憶</h1><p>{html.escape(str(exc))}</p>')
    return _core_render_memory_explanation_page(
        explanation,
        body_html=_md_to_html(str(explanation.get("body") or "")),
        layout=_layout,
    )


def _render_graph(query: dict[str, list[str]] | None = None):
    query = query or {}
    focus = _query_text(query, "focus", "page", "node", max_len=300)
    graph_search = _query_text(query, "q", "search", max_len=200)
    graph_category = _query_text(query, "type", "category", max_len=80) or "all"
    graph_size = _query_text(query, "size", max_len=80) or "category"
    if graph_size not in {"category", "degree"}:
        graph_size = "category"
    graph_labels = _query_text(query, "labels", "label", max_len=80) or "sparse"
    if graph_labels not in {"sparse", "neighbors", "all"}:
        graph_labels = "sparse"
    focus_depth, focus_depth_error = _core_parse_bounded_int(query.get("depth", ["2"])[0], "depth", 2, 0, 3)
    if focus_depth_error:
        focus_depth = 2
    assert focus_depth is not None
    full_graph = _get_graph_data()
    summary_graph = None
    summary_topic = focus or graph_search
    if summary_topic:
        summary = _get_graph_summary(
            topic=summary_topic,
            limit=_core_graph_initial_summary_node_limit,
            depth=focus_depth if focus else 1,
            max_edges=_core_graph_initial_summary_edge_limit,
        )
        summary_graph = {
            "nodes": summary.get("nodes", []),
            "edges": summary.get("edges", []),
        }
    elif _core_graph_needs_bounded_overview(full_graph):
        summary = _get_graph_summary(
            limit=_core_graph_initial_summary_node_limit,
            depth=1,
            max_edges=_core_graph_initial_summary_edge_limit,
        )
        summary_graph = {
            "nodes": summary.get("nodes", []),
            "edges": summary.get("edges", []),
        }
    graph_view = _core_graph_initial_payload(full_graph, summary_graph=summary_graph)
    visible_nodes = graph_view["nodes"]
    visible_edges = graph_view["edges"]
    node_count = int(graph_view["node_count"])
    edge_count = int(graph_view["edge_count"])
    total_node_count = int(graph_view["total_node_count"])
    total_edge_count = int(graph_view["total_edge_count"])
    graph_mode = str(graph_view["graph_mode"])
    graph_note = str(graph_view["graph_note"])
    nodes_json = _json_for_script(visible_nodes)
    edges_json = _json_for_script(visible_edges)

    if node_count == 0:
        body = _core_render_graph_empty_body()
        return _layout("知識圖譜", body)

    cat_colors = _core_graph_category_colors
    category_options = _core_graph_category_options(visible_nodes)

    graph_js = _core_render_graph_script(
        nodes_json=nodes_json,
        edges_json=edges_json,
        cat_colors_json=_json_for_script(cat_colors),
        graph_mode_json=_json_for_script(graph_mode),
        focus_id_json=_json_for_script(focus or None),
        focus_depth=focus_depth,
        search_json=_json_for_script(graph_search),
        category_json=_json_for_script(graph_category),
        size_json=_json_for_script(graph_size),
        label_json=_json_for_script(graph_labels),
        total_node_count=total_node_count,
        total_edge_count=total_edge_count,
    )

    body = _core_render_graph_page_body(
        graph_js=graph_js,
        node_count=node_count,
        edge_count=edge_count,
        total_node_count=total_node_count,
        total_edge_count=total_edge_count,
        graph_mode=graph_mode,
        graph_note=graph_note,
        category_options=category_options,
        legend_items=_core_graph_legend_items(cat_colors),
        focus_label=focus,
        focus_depth=focus_depth,
        search_label=graph_search,
        category_label=graph_category,
        size_label=graph_size,
        label_label=graph_labels,
    )
    return _layout("知識圖譜", body, page_class="graph-page")


def _render_search(query, page_type: str = ""):
    q = query.lower().strip()
    results = _search_pages(q, limit=120) if q else []
    return _core_render_search_page(
        query,
        results,
        page_href=_page_href,
        layout=_layout,
        limit=30,
        active_type=page_type.lower().strip(),
    )


# ---------------------------------------------------------------------------
# Agent search helpers
# ---------------------------------------------------------------------------

def _search_pages(q: str, limit: int = 20) -> list:
    """Search pages by title, alias, tag, and full-text body.
    Uses token index to pre-filter candidates, snippet index for zero file I/O.
    """
    with _cache_lock:
        return _core_search_pages(q, _current_wiki_cache(), limit=limit)


def _query_link(query: str, budget: str = "medium", project: str | None = None) -> dict[str, object]:
    with _cache_lock:
        return _core_query_link(
            WIKI_DIR,
            query,
            _current_wiki_cache(),
            _memory_records(),
            budget=budget,
            project=project,
            review_command="review-memory",
        )


def _get_context(topic: str) -> dict:
    """Return everything an agent needs to answer a question about a topic.
    Finds the best matching page, then returns:
    - The page's full content
    - Its backlinks (pages that reference it)
    - Its forward links (pages it references)
    - Related pages (shared tags or backlink overlap)
    """
    with _cache_lock:
        return _core_context_for_topic(WIKI_DIR, topic, _current_wiki_cache())


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def _build_backlinks() -> dict[str, dict[str, list[str]]]:
    """Build graph indexes from a fresh parsed wiki cache."""
    cache = _core_build_wiki_cache(WIKI_DIR, use_persistent_cache=False)
    try:
        return _core_build_backlinks_from_cache(cache)
    finally:
        _core_close_wiki_cache(cache)


def _get_graph_data() -> dict:
    """Return graph nodes and edges for visualization.
    Uses in-memory fulltext index — no separate rglob scan.
    """
    with _cache_lock:
        return _core_graph_data(_current_wiki_cache())


def _get_graph_summary(topic: str = "", limit: int = 40, depth: int = 1, max_edges: int = 120) -> dict:
    """Return bounded graph context for agents and large local wikis."""
    with _cache_lock:
        return _core_graph_summary(
            _current_wiki_cache(),
            topic=topic,
            limit=limit,
            depth=depth,
            max_edges=max_edges,
        )


def _rebuild_backlinks_payload() -> dict[str, object]:
    try:
        result = _build_backlinks()
    except OSError as exc:
        return {"rebuilt": False, "error": f"Could not rebuild backlinks: {exc}"}
    bl_path = WIKI_DIR / "_backlinks.json"
    _core_atomic_write_json(bl_path, result)
    # Invalidate pages cache so next request picks up the new backlinks mtime.
    _invalidate_pages_cache()
    return {"rebuilt": True, "pages": len(result.get("backlinks", {}))}


def _rebuild_index_payload() -> dict[str, object]:
    try:
        with _cache_lock:
            result = _core_rebuild_index(WIKI_DIR, cache=_current_wiki_cache())
    except OSError as exc:
        return {"rebuilt": False, "error": f"Could not rebuild index: {exc}"}
    _invalidate_pages_cache()
    return result


def _validate_wiki_payload(strict: bool = False) -> dict[str, object]:
    return _core_validate_wiki(WIKI_DIR, strict=strict)


def _link_status_payload(include_validation: bool = False) -> dict[str, object]:
    payload = _core_link_status(
        WIKI_DIR,
        version=BRAINHUB_VERSION,
        include_validation=include_validation,
    )
    payload["api_version"] = API_VERSION
    return payload


def _operations_payload() -> dict[str, object]:
    payload = _core_operation_report(WIKI_DIR)
    payload["api_version"] = API_VERSION
    return payload


def _health_payload() -> dict[str, object]:
    status = _link_status_payload(include_validation=True)
    operations = _operations_payload()
    return {
        "api_version": API_VERSION,
        "ready": bool(status.get("ready")),
        "status": status,
        "operations": operations,
    }


def _api_discovery_payload() -> dict[str, object]:
    return {
        "api_version": API_VERSION,
        "name": "BrainHub local HTTP API",
        "description": "Loopback-only API for BrainHub's local wiki, artifacts, and agent memory.",
        "local_only": True,
        "recommended": {
            "readiness": "/api/health",
            "agent_context": "/api/query-link?q=<query>&budget=small",
            "graph_overview": "/api/graph-summary?limit=40&depth=1",
            "ingest_guidance": "/api/ingest-status",
        },
        "endpoints": {
            "read": [
                "/api/health",
                "/api/status?validate=true",
                "/api/prompts",
                "/api/ingest-status",
                "/api/page-list",
                "/api/query-link",
                "/api/memory-brief",
                "/api/memory-dashboard",
                "/api/memory-audit",
                "/api/memory-profile",
                "/api/memory-inbox",
                "/api/wins",
                "/api/memory-log",
                "/api/capture-inbox",
                "/api/explain-memory",
                "/api/validate",
                "/api/search",
                "/api/context",
                "/api/graph-summary",
                "/api/graph",
                "/api/page-links",
                "/api/operations",
            ],
            "write": [
                "/api/raw-source",
                "/api/propose-memories",
                "/api/remember-memory",
                "/api/update-memory",
                "/api/review-memory",
                "/api/archive-memory",
                "/api/restore-memory",
                "/api/rebuild-backlinks",
                "/api/rebuild-index",
            ],
        },
        "write_header": {"X-BrainHub-Local-Action": "true"},
    }


def _render_health():
    # The decision-board invariant is checked here rather than left to whoever
    # remembers to run a script: the health page is already the thing people open
    # when they want to know whether this workspace is sound.
    return _core_render_health_page(
        _link_status_payload(include_validation=True),
        _operations_payload(),
        layout=_layout,
        decision_violations=[v.describe() for v in _core_audit_decisions(WIKI_DIR.parent)],
    )


def _render_onboard(project: str | None = None):
    return _core_render_onboard_page(
        _link_status_payload(include_validation=True),
        _operations_payload(),
        _starter_prompts_payload(project=project),
        target=str(WIKI_DIR.parent),
        agents=_core_supported_agents(),
        layout=_layout,
    )


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    # BaseHTTPRequestHandler defaults to HTTP/1.0, which closes the socket
    # after every response -- so a single page view costs one fresh TCP
    # connection per request (document, then each API call). Keep-alive lets a
    # reader reuse one connection for the whole burst, cutting accept-queue
    # pressure by roughly the number of requests per page. Safe to enable
    # because every response path here sets Content-Length and suppresses the
    # body on HEAD, so the client can always find the message boundary.
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.request.settimeout(REQUEST_TIMEOUT_SECONDS)

    def handle_one_request(self):
        super().handle_one_request()
        # Past the first exchange this socket is only waiting to see whether a
        # follow-up request arrives. Leaving the full request timeout in place
        # would pin one thread per idle keep-alive connection for that long; a
        # shorter idle window recycles threads quickly while still covering a
        # browser's page-load burst.
        if not self.close_connection:
            try:
                self.request.settimeout(KEEPALIVE_IDLE_TIMEOUT_SECONDS)
            except OSError:
                pass

    def do_HEAD(self):
        """HEAD requests: send headers only, no body."""
        self._head_only = True
        try:
            self.do_GET()
        finally:
            self._head_only = False

    def do_OPTIONS(self):
        self._head_only = False
        if not self._require_allowed_host():
            return
        self._json(
            {"error": "CORS preflight is not supported; BrainHub is localhost-only"},
            status=405,
            headers={"Allow": "GET, HEAD, POST"},
        )

    def do_PUT(self):
        self._method_not_allowed()

    def do_PATCH(self):
        self._method_not_allowed()

    def do_DELETE(self):
        self._method_not_allowed()

    def do_TRACE(self):
        self._method_not_allowed()

    def do_CONNECT(self):
        self._method_not_allowed()

    def do_POST(self):
        self._head_only = False
        if not self._require_allowed_host():
            return
        if not self._require_mutation_rate_limit():
            return
        parsed = urllib.parse.urlparse(self.path)
        self._handle_api_post(parsed.path)

    def _handle_api_post(self, path: str) -> None:
        if path in MEMORY_API_POST_PATHS and not _memory_enabled():
            self._json({"ok": False, "error": _core_memory_disabled_notice(WIKI_DIR.parent)}, status=403)
            return
        if path == "/api/rebuild-index":
            self._handle_rebuild_post(_rebuild_index_payload)
            return
        if path == "/api/rebuild-backlinks":
            self._handle_rebuild_post(_rebuild_backlinks_payload)
            return
        if path == "/api/raw-source":
            if not self._require_local_action_header({"created": False}):
                return
            payload = self._read_json_or_reply({"created": False})
            if payload is None:
                return
            result, http_status = _create_raw_source_payload(payload)
            self._json(result, status=http_status)
            return
        if path == "/api/propose-memories":
            payload = self._read_json_or_reply({"proposed": False, "count": 0, "proposals": []})
            if payload is None:
                return
            text = _clean_text_input(payload.get("text"), max_len=MAX_POST_BYTES)
            if not text.strip():
                self._json({"proposed": False, "error": "text required", "count": 0, "proposals": []}, status=400)
                return
            source = _clean_text_input(payload.get("source") or "http", max_len=500) or "http"
            limit, limit_error = _parse_search_limit(str(payload.get("limit", "10")))
            if limit_error:
                self._json({"proposed": False, "error": limit_error, "count": 0, "proposals": []}, status=400)
                return
            result = _propose_memories_from_text(
                text,
                source=source,
                limit=min(limit, 20),
                project=_clean_text_input(payload.get("project"), max_len=80),
            )
            self._json(result)
            return
        if path in {"/api/remember-memory", "/api/update-memory"}:
            if not self._require_local_action_header({"saved": False}):
                return
            payload = self._read_json_or_reply({"saved": False})
            if payload is None:
                return
            try:
                if path == "/api/remember-memory":
                    result = _remember_memory_from_web(payload)
                    http_status = 200 if result.get("created") else 409
                    self._json({"saved": bool(result.get("created")), **result}, status=http_status)
                else:
                    result = _update_memory_from_web(payload)
                    http_status = 200 if result.get("updated") else 409
                    self._json({"saved": bool(result.get("updated")), **result}, status=http_status)
            except ValueError as exc:
                self._json({"saved": False, "error": str(exc)}, status=400)
            return
        if path in {"/api/review-memory", "/api/archive-memory", "/api/restore-memory"}:
            if not self._require_local_action_header():
                return
            payload = self._read_json_or_reply({"updated": False})
            if payload is None:
                return
            identifier = _clean_text_input(payload.get("memory") or payload.get("identifier"), max_len=300)
            if not identifier:
                self._json({"updated": False, "error": "memory required"}, status=400)
                return
            try:
                if path == "/api/review-memory":
                    result = _mark_memory_reviewed(
                        identifier,
                        note=_clean_text_input(payload.get("note"), max_len=500),
                    )
                elif path == "/api/archive-memory":
                    result = _set_memory_status(
                        identifier,
                        "archived",
                        reason=_clean_text_input(payload.get("reason"), max_len=500),
                    )
                else:
                    result = _set_memory_status(identifier, "active")
            except ValueError as exc:
                self._json({"updated": False, "error": str(exc)}, status=404)
                return
            self._json(result)
            return
        if path in DECISION_API_POST_PATHS:
            if not self._require_local_action_header({"saved": False}):
                return
            payload = self._read_json_or_reply({"saved": False})
            if payload is None:
                return
            result, http_status = _apply_decision_delta(payload)
            self._json(result, status=http_status)
            return
        self._json({"error": "POST endpoint not found"}, status=404)

    def do_GET(self):
        self._head_only = getattr(self, '_head_only', False)
        if not self._require_allowed_host():
            return
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path in MEMORY_PAGE_PATHS and not _memory_enabled():
            self._ok(_render_memory_disabled())
            return
        if path == "/logo.svg":
            self._file(_brand_file("logo.svg"), "image/svg+xml")
        elif path == "/logo.png":
            self._file(_brand_file("logo.png"), "image/png")
        elif path.startswith("/raw/"):
            self._serve_addressed(path, parsed.query, query)
        elif path in ("/", ""):
            self._ok(_render_home())
        elif path == "/onboard":
            self._ok(_render_onboard(project=_query_text(query, "project", max_len=80)))
        elif path == "/health":
            self._ok(_render_health())
        elif path == "/ingest":
            self._ok(_render_ingest())
        elif path == "/brief":
            self._ok(_render_brief(
                query=_query_text(query, "q", "query"),
                project=_query_text(query, "project", max_len=80),
            ))
        elif path == "/propose":
            self._ok(_render_propose(
                project=_query_text(query, "project", max_len=80),
                source=_query_text(query, "source", max_len=500),
            ))
        elif path == "/prompts":
            self._ok(_render_prompts(project=_query_text(query, "project", max_len=80)))
        elif path == "/more":
            self._ok(_render_more())
        elif path == "/memory":
            self._ok(_render_memory_dashboard(project=_query_text(query, "project", max_len=80)))
        elif path == "/audit":
            self._ok(_render_memory_audit(project=_query_text(query, "project", max_len=80)))
        elif path == "/inbox":
            self._ok(_render_inbox(project=_query_text(query, "project", max_len=80)))
        elif path == "/captures":
            self._ok(_render_captures(project=_query_text(query, "project", max_len=80)))
        elif path == "/explain-memory":
            identifier = _query_text(query, "memory", "name", max_len=300)
            self._ok(_render_explain_memory(identifier))
        elif path == "/profile":
            self._ok(_render_profile(project=_query_text(query, "project", max_len=80)))
        elif path == "/wins":
            self._ok(_render_memory_wins(project=_query_text(query, "project", max_len=80)))
        elif path == "/memory-log":
            self._ok(_render_memory_log())
        elif path == "/all":
            self._ok(_render_all(query))
        elif path == "/graph":
            self._ok(_render_graph(query))
        elif path == "/artifacts":
            self._ok(_render_artifacts())
        elif path == "/documents":
            self._ok(_render_documents())
        elif path == "/control":
            self._ok(_render_control_center())
        elif path == "/dashboard":
            self._ok(_render_dashboard())
        elif path.startswith("/artifact/"):
            self._serve_addressed(path, parsed.query, query)
        elif path == "/search":
            self._ok(_render_search(_query_text(query, "q"), page_type=_query_text(query, "type", "page_type", max_len=80)))
        elif path.startswith("/page/"):
            self._serve_addressed(path, parsed.query, query)
        elif path.startswith("/decide/"):
            # /decide/<id> and /decide/<id>/<title-decoration> (wiki-style): the first
            # path segment is the id (a decision sid or a legacy slug); the rest is a
            # human-readable title tail and is ignored for lookup.
            rest = urllib.parse.unquote(path[len("/decide/"):])
            board_id = rest.split("/", 1)[0]
            board_html = _render_decision_board(board_id)
            if board_html is None:
                self._err(board_id)
            else:
                self._ok(board_html)
        elif path == "/api" or path.startswith("/api/"):
            self._handle_api_get(path, query)
        else:
            self._err("page")

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path in MEMORY_API_GET_PATHS and not _memory_enabled():
            self._json({"ok": False, "error": _core_memory_disabled_notice(WIKI_DIR.parent)}, status=403)
            return
        if path in {"/api", "/api/"}:
            self._json(_api_discovery_payload())
        elif path == "/api/pages":
            self._json(_all_pages())
        elif path == "/api/page-list":
            limit, limit_error = _core_parse_bounded_int(query.get("limit", ["100"])[0], "limit", 100, 1, 1000)
            offset, offset_error = _core_parse_bounded_int(query.get("offset", ["0"])[0], "offset", 0, 0, 1000000)
            error = limit_error or offset_error
            if error:
                self._json({"error": error}, status=400)
            else:
                assert limit is not None
                assert offset is not None
                self._json(_page_list_payload(
                    category=query.get("category", [""])[0],
                    page_type=query.get("type", [""])[0] or query.get("page_type", [""])[0],
                    maturity=query.get("maturity", [""])[0],
                    limit=limit,
                    offset=offset,
                    include_all=query.get("all", ["false"])[0].lower() in {"1", "true", "yes"},
                ))
        elif path == "/api/status":
            include_validation = query.get("validate", ["false"])[0].lower() in {"1", "true", "yes"}
            self._json(_link_status_payload(include_validation=include_validation))
        elif path == "/api/health":
            self._json(_health_payload())
        elif path == "/api/operations":
            self._json(_operations_payload())
        elif path == "/api/prompts":
            self._json(_starter_prompts_payload(project=_query_text(query, "project", max_len=80)))
        elif path == "/api/ingest-status":
            self._json(_ingest_status())
        elif path == "/api/artifacts":
            kind = _query_text(query, "kind", max_len=20)
            if kind and kind not in ARTIFACT_DIRECTORIES:
                self._json({"error": f"kind must be one of: {', '.join(ARTIFACT_DIRECTORIES)}"}, status=400)
            else:
                self._json(_artifact_catalog(kind=kind or None))
        elif path == "/api/backlinks":
            data, error = _load_backlinks_index()
            if error:
                self._json({"error": error}, status=500)
            else:
                self._json(data)
        elif path == "/api/page-links":
            limit, limit_error = _core_parse_bounded_int(query.get("limit", ["100"])[0], "limit", 100, 1, 1000)
            offset, offset_error = _core_parse_bounded_int(query.get("offset", ["0"])[0], "offset", 0, 0, 1000000)
            error = limit_error or offset_error
            if error:
                self._json({"error": error}, status=400)
            else:
                assert limit is not None
                assert offset is not None
                payload, status = _page_links_payload(
                    query.get("page", [""])[0] or query.get("page_name", [""])[0],
                    limit=limit,
                    offset=offset,
                    include_all=query.get("all", ["false"])[0].lower() in {"1", "true", "yes"},
                )
                self._json(payload, status=status)
        elif path == "/api/rebuild-backlinks":
            self._json({"error": "use POST with JSON body: {}"}, status=405)
        elif path == "/api/rebuild-index":
            self._json({"error": "use POST with JSON body: {}"}, status=405)
        elif path == "/api/decision-board/decide":
            self._json({"error": "use POST with JSON body: {\"batch_id\":..,\"item_id\":..,\"decision\":{..}}"}, status=405)
        elif path == "/api/validate":
            strict = query.get("strict", ["false"])[0].lower() in {"1", "true", "yes"}
            payload = _validate_wiki_payload(strict=strict)
            self._json(payload, status=200 if payload.get("passed") else 422)
        elif path in {"/api/graph", "/api/graph-summary", "/api/search", "/api/context"}:
            self._handle_knowledge_api_get(path, query)
        elif path in {
            "/api/memory-profile",
            "/api/memory-dashboard",
            "/api/memory-brief",
            "/api/query-link",
            "/api/memory-audit",
            "/api/memory-inbox",
            "/api/wins",
            "/api/memory-log",
            "/api/capture-inbox",
        }:
            self._handle_memory_api_get(path, query)
        elif path == "/api/proposal-sources":
            limit = self._query_limit_or_reply(query, "50", {"sources": []})
            if limit is not None:
                self._json(_proposal_sources(limit=min(limit, 100)))
        elif path == "/api/proposal-source":
            source_path = query.get("path", [""])[0]
            payload, status = _proposal_source_payload(source_path)
            self._json(payload, status=status)
        elif path == "/api/raw-source":
            self._json({"error": "use POST with JSON body: {\"text\": \"...\"}"}, status=405)
        elif path == "/api/propose-memories":
            self._json({"error": "use POST with JSON body: {\"text\": \"...\"}"}, status=405)
        elif path in {"/api/review-memory", "/api/archive-memory", "/api/restore-memory"}:
            self._json({"error": "use POST with JSON body: {\"memory\": \"...\"}"}, status=405)
        elif path == "/api/explain-memory":
            identifier = _query_text(query, "memory", "name", max_len=300)
            if not identifier:
                self._json({"found": False, "error": "memory parameter required"}, status=400)
            else:
                try:
                    self._json(_memory_explanation(identifier))
                except ValueError as exc:
                    self._json({"found": False, "error": str(exc)}, status=404)
        else:
            self._err("page")

    def _handle_knowledge_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/graph":
            self._json(_get_graph_data())
        elif path == "/api/graph-summary":
            limit, limit_error = _core_parse_bounded_int(query.get("limit", ["40"])[0], "limit", 40, 1, 250)
            depth, depth_error = _core_parse_bounded_int(query.get("depth", ["1"])[0], "depth", 1, 0, 3)
            max_edges, edge_error = _core_parse_bounded_int(query.get("max_edges", ["120"])[0], "max_edges", 120, 0, 1000)
            error = limit_error or depth_error or edge_error
            if error:
                self._json({"error": error}, status=400)
            else:
                assert limit is not None
                assert depth is not None
                assert max_edges is not None
                self._json(_get_graph_summary(
                    topic=_query_text(query, "topic", "q"),
                    limit=limit,
                    depth=depth,
                    max_edges=max_edges,
                ))
        elif path == "/api/search":
            q = _query_text(query, "q")
            limit = self._query_limit_or_reply(query, "20", {"results": []})
            if limit is None:
                return
            if not q:
                self._json({"error": "q parameter required", "results": []}, status=400)
            else:
                results = _search_pages(q, limit=limit)
                self._json({"query": q, "count": len(results), "results": results})
        elif path == "/api/context":
            topic = _query_text(query, "topic", "q")
            if not topic:
                self._json({"error": "topic parameter required"}, status=400)
            else:
                self._json(_get_context(topic))

    def _handle_memory_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/memory-profile":
            limit = self._query_limit_or_reply(query, "10")
            if limit is not None:
                self._json(_memory_profile(limit=limit, project=_query_text(query, "project", max_len=80)))
        elif path == "/api/memory-dashboard":
            limit = self._query_limit_or_reply(query, "12")
            if limit is not None:
                self._json(_memory_dashboard(limit=limit, project=_query_text(query, "project", max_len=80)))
        elif path == "/api/memory-brief":
            limit = self._query_limit_or_reply(query, "6")
            if limit is not None:
                self._json(_memory_brief(
                    query=_query_text(query, "q", "query"),
                    limit=limit,
                    project=_query_text(query, "project", max_len=80),
                ))
        elif path == "/api/query-link":
            query_text = _query_text(query, "q", "query")
            if not query_text.strip():
                self._json({"found": False, "error": "query parameter required", "context_packet": []}, status=400)
            else:
                self._json(_query_link(
                    query=query_text,
                    budget=query.get("budget", ["medium"])[0],
                    project=_query_text(query, "project", max_len=80),
                ))
        elif path == "/api/memory-audit":
            limit = self._query_limit_or_reply(query, "10")
            if limit is not None:
                self._json(_memory_audit(limit=limit, project=_query_text(query, "project", max_len=80)))
        elif path == "/api/memory-inbox":
            limit = self._query_limit_or_reply(query, "20")
            if limit is not None:
                include_archived = query.get("include_archived", ["false"])[0].lower() in {"1", "true", "yes"}
                self._json(_memory_inbox(
                    limit=limit,
                    include_archived=include_archived,
                    project=_query_text(query, "project", max_len=80),
                ))
        elif path == "/api/wins":
            limit = self._query_limit_or_reply(query, "6")
            if limit is not None:
                self._json(_memory_wins(limit=limit, project=_query_text(query, "project", max_len=80)))
        elif path == "/api/memory-log":
            limit = self._query_limit_or_reply(query, "50")
            if limit is not None:
                include_captures = query.get("include_captures", ["true"])[0].lower() not in {"0", "false", "no"}
                self._json(_memory_log(limit=limit, include_captures=include_captures))
        elif path == "/api/capture-inbox":
            limit = self._query_limit_or_reply(query, "20")
            if limit is not None:
                self._json(_capture_inbox(
                    limit=limit,
                    project=_query_text(query, "project", max_len=80),
                ))

    def _ok(self, body: str):
        encoded = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._security_headers()
        self.send_header("Content-Length", str(len(encoded)))
        self._no_store_headers()
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _redirect(self, location: str):
        self.send_response(302)
        self.send_header("Location", location)
        self._security_headers()
        self.send_header("Content-Length", "0")
        self._no_store_headers()
        self.end_headers()

    def _serve_addressed(self, path: str, raw_query: str, query: dict[str, list[str]]) -> None:
        """Serve /<kind>/<SID>/<title>, and upgrade every legacy shape onto it.

        The sid decides what gets served; the title segment is decoration. Any
        request that is not already at the canonical path — wrong title, missing
        title, wrong kind prefix, or a legacy title/subpath locator — is
        redirected there, so links written before sids existed still work and
        end up showing the current URL.
        """
        reference = _parse_address(path)
        if reference is None:
            self._err("page")
            return

        if not reference.sid:
            # Pre-sid locator: upgrade it when the object has a sid, otherwise
            # keep serving it where it is — objects predating sids stay reachable.
            target = self._canonical_for_legacy(reference)
            if target is None:
                self._render_legacy(reference, query)
            else:
                self._redirect(_with_query(target, raw_query))
            return

        kind = _kind_for_sid(reference.sid)
        target = self._canonical_for_sid(kind, reference.sid) if kind else None
        if target is None:
            self._err(reference.sid)
            return
        if urllib.parse.unquote(path) != urllib.parse.unquote(target):
            self._redirect(_with_query(target, raw_query))
            return
        self._render_addressed(kind, reference.sid, query)

    def _canonical_for_sid(self, kind: str, sid: str) -> str | None:
        """Where this sid currently lives, or None when nothing carries it."""
        if kind == _KIND_PAGE:
            page = _find_page(sid)
            return _canonical_path(kind, sid, page.stem) if page else None
        if kind == _KIND_RAW:
            resolved = _raw_ids.resolve(WIKI_DIR.parent, sid)
            return _canonical_path(kind, sid, resolved.name) if resolved else None
        record = _artifact_record_by_sid(sid)
        if not record:
            return None
        return _canonical_path(kind, sid, _artifact_subpath(record).rsplit("/", 1)[-1])

    def _canonical_for_legacy(self, reference: Reference) -> str | None:
        """Upgrade a pre-sid locator to its canonical path, when it resolves."""
        if reference.kind == _KIND_RAW:
            root = WIKI_DIR.parent
            sid = _raw_ids.sid_for_path(root, "raw/" + reference.remainder.strip("/"))
            if not sid:
                return None
            resolved = _raw_ids.resolve(root, sid)
            return _canonical_path(_KIND_RAW, sid, resolved.name) if resolved else None
        if reference.kind == _KIND_PAGE:
            page = _find_page(reference.remainder)
            if not page:
                return None
            sid = _sid_for_page_name(page.stem)
            return _canonical_path(_KIND_PAGE, sid, page.stem) if sid else None
        record = _artifact_record_by_subpath(reference.remainder)
        sid = _normalize_sid(record.get("sid")) if record else ""
        if not sid:
            return None
        return _canonical_path(_KIND_ARTIFACT, sid, _artifact_subpath(record).rsplit("/", 1)[-1])

    def _render_legacy(self, reference: "Reference", query: dict[str, list[str]]) -> None:
        """Serve an object that has no sid yet, at its pre-sid URL."""
        if reference.kind == _KIND_RAW:
            self._serve_raw(reference.remainder)
            return
        if reference.kind == _KIND_PAGE:
            page = _find_page(reference.remainder)
            if page:
                self._ok(_render_page(page))
            else:
                self._err(reference.remainder)
            return
        if _query_text(query, "format", max_len=8) == "pdf":
            self._serve_artifact_pdf(reference.remainder)
        else:
            self._serve_artifact(reference.remainder)

    def _serve_raw(self, subpath: str) -> None:
        raw_path, content_type = _resolve_raw_static_path(subpath)
        if raw_path and content_type:
            self._file(raw_path, content_type)
        else:
            self._err("file")

    def _render_addressed(self, kind: str, sid: str, query: dict[str, list[str]]) -> None:
        if kind == _KIND_RAW:
            resolved = _raw_ids.resolve(WIKI_DIR.parent, sid)
            if not resolved:
                self._err(sid)
                return
            self._serve_raw(resolved.relative_to(WIKI_DIR.parent / "raw").as_posix())
            return
        if kind == _KIND_PAGE:
            page = _find_page(sid)
            if not page:
                self._err(sid)
                return
            self._ok(_render_page(page))
            return
        record = _artifact_record_by_sid(sid)
        if not record:
            self._err(sid)
            return
        subpath = _artifact_subpath(record)
        if _query_text(query, "format", max_len=8) == "pdf":
            self._serve_artifact_pdf(subpath)
        else:
            self._serve_artifact(subpath)

    def _err(self, name: str):
        encoded = _layout("找不到頁面", f"<h1>找不到頁面</h1><p>沒有這個頁面：{html.escape(name)}</p>").encode()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._security_headers()
        self.send_header("Content-Length", str(len(encoded)))
        self._no_store_headers()
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _json(self, data, status: int = 200, headers=None):
        encoded = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._security_headers()
        self._no_store_headers()
        for key, value in (headers or {}).items():
            self.send_header(str(key), str(value))
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _require_allowed_host(self) -> bool:
        # When explicitly bound to a non-loopback host (brainhub --host, opt-in
        # LAN viewer), accept the operator's chosen bind host too. Default path
        # stays localhost-only.
        if BIND_HOST not in ("127.0.0.1", "localhost", ""):
            return True
        allowed, error = _core_validate_local_host_header(self.headers.get("Host", ""))
        if allowed:
            return True
        self._json({"error": error}, status=403)
        return False

    def _require_local_action_header(self, error_payload: dict[str, object] | None = None) -> bool:
        value = self.headers.get(LOCAL_ACTION_HEADER, "").strip().lower()
        if value in LOCAL_ACTION_VALUES:
            # Accept the operator's opt-in LAN bind host as a browser source too,
            # mirroring _require_allowed_host — the viewer serves its own pages
            # from BIND_HOST, so same-origin writes carry that Origin/Referer.
            _allowed_src_hosts = {"127.0.0.1", "localhost"}
            if BIND_HOST not in ("127.0.0.1", "localhost", ""):
                _allowed_src_hosts.add(BIND_HOST)
            allowed, error = _core_validate_local_browser_source_headers(
                self.headers.get("Origin", ""),
                self.headers.get("Referer", ""),
                allowed_hosts=_allowed_src_hosts,
            )
            if allowed:
                return True
            payload = dict(error_payload or {"updated": False})
            payload["error"] = error
            self._json(payload, status=403)
            return False
        payload = dict(error_payload or {"updated": False})
        payload["error"] = f"{LOCAL_ACTION_HEADER} header required for local mutations"
        self._json({
            **payload,
        }, status=403)
        return False

    def _require_mutation_rate_limit(self) -> bool:
        client_host = self.client_address[0] if self.client_address else "local"
        with _rate_limiter_lock:
            allowed, retry_after = _mutation_rate_limiter.check(client_host)
        if allowed:
            return True
        self._json(
            {
                "error": "local mutation rate limit exceeded",
                "retry_after_seconds": retry_after,
            },
            status=429,
            headers={"Retry-After": str(retry_after)},
        )
        return False

    def _method_not_allowed(self) -> None:
        self._head_only = False
        if not self._require_allowed_host():
            return
        self._json(
            {"error": "method not allowed; BrainHub supports GET, HEAD, and POST"},
            status=405,
            headers={"Allow": "GET, HEAD, POST"},
        )

    def _read_json_or_reply(self, error_payload: dict[str, object]) -> dict | None:
        payload, error, status = self._read_json_body()
        if error:
            self._json({**error_payload, "error": error}, status=status)
            return None
        assert payload is not None
        return payload

    def _handle_rebuild_post(self, payload_builder: Callable[[], dict[str, object]]) -> None:
        if not self._require_local_action_header({"rebuilt": False}):
            return
        if self._read_json_or_reply({"rebuilt": False}) is None:
            return
        self._json(payload_builder())

    def _query_limit_or_reply(
        self,
        query: dict[str, list[str]],
        default: str,
        error_payload: dict[str, object] | None = None,
    ) -> int | None:
        limit, error = _parse_search_limit(query.get("limit", [default])[0])
        if error:
            self._json({**(error_payload or {}), "error": error}, status=400)
            return None
        assert limit is not None
        return limit

    def _read_json_body(self) -> tuple[dict | None, str | None, int]:
        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            return None, "Content-Type must be application/json", 415
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return None, "Content-Length required", 411
        try:
            length = int(raw_length)
        except ValueError:
            return None, "invalid Content-Length", 400
        if length < 0:
            return None, "invalid Content-Length", 400
        if length > MAX_POST_BYTES:
            return None, f"request body too large; max {MAX_POST_BYTES} bytes", 413
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "invalid JSON body", 400
        if not isinstance(payload, dict):
            return None, "JSON body must be an object", 400
        return payload, None, 200

    def _security_headers(self, content_security_policy: str = CONTENT_SECURITY_POLICY):
        for key, value in _core_local_security_headers(API_VERSION, content_security_policy):
            self.send_header(key, value)

    def _no_store_headers(self):
        for key, value in _core_local_no_store_headers():
            self.send_header(key, value)

    def _artifact_security_headers(self):
        for key, value in _core_artifact_security_headers(API_VERSION):
            self.send_header(key, value)

    def _serve_artifact(self, subpath: str):
        """Serve a stored artifact HTML sandboxed to an opaque origin.

        The artifact is served from the viewer's own port but the
        `sandbox allow-scripts` CSP (see artifact_security_headers) drops it
        into a unique opaque origin, so its inline chart/mermaid scripts render
        without being able to touch the viewer's origin, cookies, or APIs.
        """
        artifact_path = _resolve_artifact_path(subpath)
        if not artifact_path:
            self._err("artifact")
            return
        data = artifact_path.read_bytes()
        # Backward-compat: artifacts baked before the server-side PDF button
        # carry a window.print()-only button (incomplete for collapsed content).
        # When served over http, upgrade it to route through ?format=pdf; offline
        # (file://) opens keep the baked window.print fallback untouched.
        if b"brainhub-pdf-button" in data and b"</body>" in data:
            data = _inject_before_body_end(data, _PDF_BUTTON_UPGRADE)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._artifact_security_headers()
        self._no_store_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(data)

    def _serve_artifact_pdf(self, subpath: str):
        """Render a stored artifact to a real PDF (user-level headless chrome)
        and serve it as a download. Collapsed accordions / hidden tab panels are
        revealed first (see :func:`_artifact_pdf_bytes`) so the PDF is complete
        regardless of the live artifact's toggle state."""
        artifact_path = _resolve_artifact_path(subpath)
        if not artifact_path:
            self._err("artifact")
            return
        pdf_bytes = _artifact_pdf_bytes(artifact_path)
        if not pdf_bytes:
            self._err("pdf")
            return
        fn = artifact_path.stem + ".pdf"
        ascii_fn = fn.encode("ascii", "ignore").decode() or "artifact.pdf"
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{ascii_fn}"; '
            f"filename*=UTF-8''{urllib.parse.quote(fn)}",
        )
        self._no_store_headers()
        self.send_header("Content-Length", str(len(pdf_bytes)))
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(pdf_bytes)

    def _file(self, fpath, content_type):
        fpath = _safe_resolve(fpath)
        if not fpath or not _is_allowed_static_file(fpath):
            self._err("file")
            return
        if fpath.exists() and fpath.is_file():
            data = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            if content_type == "image/svg+xml":
                self._security_headers(content_security_policy=SVG_CONTENT_SECURITY_POLICY)
            else:
                self._security_headers()
            self._no_store_headers()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not getattr(self, '_head_only', False):
                self.wfile.write(data)
        else:
            self._err("file")

    def log_message(self, *a): pass


def _parse_serve_args(argv: list[str], default_port: int = PORT, default_root: Path = ROOT) -> tuple[int, Path, str]:
    port = default_port
    root = default_root
    host = "127.0.0.1"
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in {"--host", "--bind"}:
            if index + 1 >= len(argv):
                raise SystemExit("--host requires a value")
            host = argv[index + 1]
            index += 2
            continue
        if arg.startswith("--host=") or arg.startswith("--bind="):
            host = arg.split("=", 1)[1]
            index += 1
            continue
        if arg == "--port":
            if index + 1 >= len(argv):
                raise SystemExit("--port requires a value")
            try:
                port = int(argv[index + 1])
            except ValueError as exc:
                raise SystemExit("--port must be an integer") from exc
            index += 2
            continue
        elif arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1])
            except ValueError as exc:
                raise SystemExit("--port must be an integer") from exc
            index += 1
            continue
        elif arg == "--root":
            if index + 1 >= len(argv):
                raise SystemExit("--root requires a value")
            root = Path(argv[index + 1]).expanduser().resolve()
            index += 2
            continue
        elif arg.startswith("--root="):
            root = Path(arg.split("=", 1)[1]).expanduser().resolve()
            index += 1
            continue
        elif arg.startswith("-"):
            raise SystemExit(f"unknown option for serve.py: {arg}")
        raise SystemExit(
            "serve.py does not accept a positional target. "
            "Use 'python serve.py --root /path/to/link' or 'bh serve /path/to/link'."
        )
    if port < 1 or port > 65535:
        raise SystemExit("--port must be between 1 and 65535")
    return port, root, host


def _parse_serve_port(argv: list[str], default: int = PORT) -> int:
    port, _, _ = _parse_serve_args(argv, default_port=default, default_root=ROOT)
    return port


def _serve_bind_error_message(exc: OSError, port: int) -> str:
    if exc.errno in {errno.EADDRINUSE, 48, 98}:
        next_port = port + 1 if port < 65535 else 3000
        return (
            f"BrainHub could not start because 127.0.0.1:{port} is already in use.\n"
            f"Try another port, for example: python serve.py --port {next_port}"
        )
    return f"BrainHub could not start local server on 127.0.0.1:{port}: {exc}"


def _serve_startup_lines(port: int) -> list[str]:
    host = BIND_HOST or "127.0.0.1"
    base_url = f"http://{host}:{port}"
    is_loopback = host in ("127.0.0.1", "localhost")
    bind_line = (
        "  Local-only: bound to 127.0.0.1; no public host mode."
        if is_loopback
        else f"  ⚠ Bound to {host}: reachable by anything on this network segment, and there is NO AUTH."
    )
    return [
        f"  BrainHub -> {base_url}",
        "  Open:",
        f"    {base_url}/onboard  first-run checklist",
        f"    {base_url}/health   readiness and repair",
        f"    {base_url}/graph    knowledge graph",
        bind_line,
        "  No auth: do not expose this server without your own authentication layer.",
        "  MCP and CLI work without this viewer running.",
    ]


def main():
    global PORT, WIKI_DIR, RAW_DIR, BIND_HOST
    PORT, root, BIND_HOST = _parse_serve_args(sys.argv[1:], default_port=PORT, default_root=ROOT)
    if os.environ.get("BRAINHUB_CLI_COMMAND"):
        _core_set_bh_command_override(None)
    else:
        _core_set_bh_command_override([sys.executable, str(root / "brainhub_engine.py")])
    WIKI_DIR = root / "wiki"
    RAW_DIR = root / "raw"
    try:
        with ThreadingLocalTCPServer((BIND_HOST, PORT), Handler) as s:
            for line in _serve_startup_lines(PORT):
                print(line)
            try: s.serve_forever()
            except KeyboardInterrupt: print("\n  stopped.")
    except OSError as exc:
        print(_serve_bind_error_message(exc, PORT), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
