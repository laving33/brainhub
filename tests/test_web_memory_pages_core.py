import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.web_memory_pages import (  # noqa: E402
    render_brief_page,
    render_captures_page,
    render_inbox_page,
    render_memory_explanation_page,
    render_memory_log_page,
    render_memory_audit_page,
    render_memory_dashboard_page,
    render_memory_wins_page,
    render_profile_page,
)


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def _page_href(name: str) -> str:
    return f"/page/{name}"


def _action_hints(_record: dict[str, object]) -> list[dict[str, object]]:
    return []


def test_render_brief_page_escapes_query_and_project():
    payload = {
        "project": "<alpha>",
        "profile": {"active_count": 2},
        "captures": {"count": 0, "items": []},
        "review": {"count": 1, "items": []},
        "relevant_count": 1,
        "agent_guidance": ["Use <Link> first"],
        "relevant_memories": [],
    }

    html = render_brief_page(payload, "<task>", page_href=_page_href, action_hints=_action_hints, layout=_layout)

    assert "<title>記憶簡報</title>" in html
    assert "value=\"&lt;task&gt;\"" in html
    assert 'data-copy-text="跟 BrainHub 要一份關於 &lt;task&gt; 的簡報（專案 &lt;alpha&gt;）"' in html
    assert "複製簡報提示詞" in html
    assert 'data-copy-text="跟 BrainHub 查詢 &lt;task&gt;"' in html
    assert "複製查詢提示詞" in html
    assert "專案：</strong> &lt;alpha&gt;" in html
    assert "Use &lt;Link&gt; first" in html
    assert "<task>" not in html


def test_render_brief_page_guides_empty_memory_recovery():
    payload = {
        "project": "",
        "profile": {"active_count": 0},
        "captures": {"count": 0, "items": []},
        "review": {"count": 0, "items": []},
        "relevant_count": 0,
        "agent_guidance": [],
        "relevant_memories": [],
    }

    html = render_brief_page(payload, "release notes", page_href=_page_href, action_hints=_action_hints, layout=_layout)

    assert "目前沒有相關記憶。" in html
    assert "在產生下一份簡報前，先讓 BrainHub 學會這些" in html
    assert 'href="/ingest"' in html
    assert 'href="/propose"' in html
    assert 'data-copy-text="跟 BrainHub 草擬關於 release notes 的記憶提案（依 raw 來源）"' in html
    assert "複製記憶提案提示詞" in html


def test_render_memory_dashboard_page_shows_counts_next_actions_and_sections():
    payload = {
        "project": "alpha",
        "memory_count": 3,
        "active_count": 2,
        "review_count": 1,
        "updated_count": 1,
        "capture_count": 0,
        "archived_count": 0,
        "by_type": {"preference": 2},
        "by_scope": {"project": 1},
        "next_actions": [{"label": "Review", "detail": "Confirm memory", "command": "bh memory-inbox"}],
        "review": [],
        "captures": [],
        "recent_updates": [],
        "active": [],
        "archived": [],
    }

    html = render_memory_dashboard_page(payload, page_href=_page_href, action_hints=_action_hints, layout=_layout)

    assert "記憶儀表板" in html
    assert '<span class="num">3</span><span class="label">記憶</span>' in html
    assert 'data-copy-text="BrainHub 記得關於專案 alpha 的哪些事？"' in html
    assert 'data-copy-text="跟 BrainHub 要一份專案 alpha 的簡報"' in html
    assert 'data-copy-text="稽核 BrainHub 專案 alpha 的記憶"' in html
    assert "<strong>類型：</strong> preference: 2" in html
    assert "bh memory-inbox" in html
    assert "目前沒有記憶需要審核。" in html


def test_render_profile_page_lists_memory_sections_and_explain_links():
    record = {
        "name": "prefer-short-notes",
        "title": "Prefer short notes",
        "memory_type": "preference",
        "scope": "user",
        "tldr": "Keep release notes short.",
    }
    payload = {
        "project": "",
        "memory_count": 1,
        "active_count": 1,
        "review_count": 0,
        "by_type": {"preference": 1},
        "by_scope": {"user": 1},
        "by_status": {"active": 1},
        "recent": [record],
        "preferences": [record],
        "decisions": [],
        "projects": [],
        "archived": [],
    }

    html = render_profile_page(payload, page_href=_page_href, layout=_layout)

    assert "記憶總覽" in html
    assert 'data-copy-text="BrainHub 記得我的哪些事？"' in html
    assert 'data-copy-text="先跟 BrainHub 對一下，再繼續"' in html
    assert "/page/prefer-short-notes" in html
    assert "/explain-memory?memory=prefer-short-notes" in html
    assert "Keep release notes short." in html


def test_render_profile_page_guides_first_memory_recovery():
    payload = {
        "project": "alpha",
        "memory_count": 0,
        "active_count": 0,
        "review_count": 0,
        "by_type": {},
        "by_scope": {},
        "by_status": {},
        "recent": [],
        "preferences": [],
        "decisions": [],
        "projects": [],
        "archived": [],
    }

    html = render_profile_page(payload, page_href=_page_href, layout=_layout)

    assert "目前還沒有長期記憶" in html
    assert 'href="/ingest"' in html
    assert 'href="/propose"' in html
    assert 'data-copy-text="記住 &lt;偏好或決策&gt;，屬於專案 alpha"' in html
    assert "複製記住提示詞" in html


def test_render_memory_audit_page_reports_risks():
    payload = {
        "project": "alpha",
        "status": "needs_attention",
        "profile": {"memory_count": 1, "active_count": 1, "review_count": 1},
        "captures": {"count": 0, "warning_count": 0, "read_warning_count": 0, "items": []},
        "risk_factors": [{"code": "stale", "message": "Review <memory>"}],
        "next_actions": [],
        "inbox": {"items": []},
    }

    html = render_memory_audit_page(payload, page_href=_page_href, action_hints=_action_hints, layout=_layout)

    assert "記憶稽核" in html
    assert 'data-copy-text="稽核 BrainHub 專案 alpha 的記憶"' in html
    assert 'data-copy-text="審核 BrainHub 專案 alpha 的記憶待審清單"' in html
    assert "needs_attention" in html
    assert "Review &lt;memory&gt;" in html


def test_render_memory_log_page_shows_lifecycle_events():
    payload = {
        "count": 1,
        "total_matching": 1,
        "privacy_note": "Memory bodies are not included.",
        "entries": [
            {
                "timestamp": "2026-05-25T00:00:00Z",
                "operation": "remember",
                "category": "memory",
                "description": "Prefer local memory",
                "summary": "Created memory: wiki/memories/prefer-local-memory.md",
                "memory_paths": ["wiki/memories/prefer-local-memory.md"],
                "details": ["Created: memories/prefer-local-memory.md"],
            }
        ],
    }

    html = render_memory_log_page(payload, layout=_layout)

    assert "記憶異動紀錄" in html
    assert "Prefer local memory" in html
    assert "Memory bodies are not included" in html


def test_render_captures_page_shows_redaction_and_read_warnings():
    payload = {
        "project": "alpha",
        "count": 1,
        "warning_count": 1,
        "read_warning_count": 1,
        "captures": [],
        "read_warnings": [{"capture": "raw/memory-captures/bad.md", "error": "<denied>"}],
    }

    html = render_captures_page(payload, layout=_layout)

    assert "Raw 擷取紀錄待審清單" in html
    assert 'data-copy-text="審核 BrainHub 專案 alpha 的 raw 擷取紀錄"' in html
    assert "有 1 筆 raw 擷取紀錄疑似包含機密內容。" in html
    assert "raw/memory-captures/bad.md" in html
    assert "&lt;denied&gt;" in html


def test_render_inbox_page_lists_review_items_and_actions():
    payload = {
        "project": "",
        "review_count": 1,
        "counts_by_severity": {"warning": 1},
        "items": [
            {
                "name": "memory-one",
                "title": "Memory <One>",
                "memory_type": "preference",
                "scope": "user",
                "status": "pending",
                "tldr": "Needs review.",
                "issues": [{"severity": "warning", "code": "pending", "message": "Needs <review>"}],
                "primary_action": {"label": "Review", "description": "Confirm it"},
                "actions": [{"label": "Mark reviewed", "command": "bh review-memory memory-one"}],
            }
        ],
    }

    html = render_inbox_page(payload, page_href=_page_href, layout=_layout)

    assert "記憶審核收件匣" in html
    assert 'data-copy-text="審核 BrainHub 的記憶待審清單"' in html
    assert "Memory &lt;One&gt;" in html
    assert "Needs &lt;review&gt;" in html
    assert "/explain-memory?memory=memory-one" in html
    assert "bh review-memory memory-one" in html


def test_render_memory_explanation_page_shows_trust_context_actions_and_body():
    payload = {
        "memory": {
            "name": "prefer-reviewable-memory",
            "title": "Prefer <reviewable> memory",
            "tldr": "User prefers visible memory actions.",
        },
        "recall": {"state": "needs_review", "reason": "Pending review"},
        "review": {
            "status": "pending",
            "issue_count": 1,
            "issues": [{"severity": "warning", "code": "pending", "message": "Needs <review>"}],
            "primary_action": {"label": "Review", "description": "Confirm it"},
            "actions": [{"label": "Forget", "command": "bh forget-memory prefer-reviewable-memory"}],
        },
        "provenance": {
            "source": "<unit test>",
            "date_captured": "2026-05-05T00:00:00Z",
            "path": "wiki/memories/prefer-reviewable-memory.md",
        },
        "lifecycle": {"status": "active"},
        "graph": {"forward": ["agent-memory"], "inbound": [], "wikilinks": ["agent-memory"]},
        "log_entries": ["2026-05-05 remember <memory>"],
    }

    html = render_memory_explanation_page(payload, body_html="<p>Trusted body</p>", layout=_layout)

    assert "<h1>Prefer &lt;reviewable&gt; memory</h1>" in html
    assert "User prefers visible memory actions." in html
    assert "needs_review" in html
    assert "Needs &lt;review&gt;" in html
    assert "下一步：</strong> Review" in html
    assert "bh forget-memory prefer-reviewable-memory" in html
    assert "/graph?focus=prefer-reviewable-memory&amp;depth=2" in html
    assert "開啟本機知識圖譜" in html
    assert "agent-memory" in html
    assert "2026-05-05 remember &lt;memory&gt;" in html
    assert "<p>Trusted body</p>" in html
    assert "<unit test>" not in html


def test_render_memory_wins_page_shows_local_proof_signals():
    payload = {
        "active_count": 2,
        "reviewed_active_count": 1,
        "review_count": 1,
        "project_count": 1,
        "honest_note": "These are local wiki signals, not telemetry.",
        "wins": [
            {
                "label": "Reusable <context>",
                "count": 2,
                "description": "Active memories can appear in briefs.",
                "prompt": "start with Link before we continue",
            }
        ],
        "recent_memories": [
            {
                "name": "alpha",
                "title": "Alpha <memory>",
                "memory_type": "project",
                "scope": "project",
                "tldr": "Alpha context.",
            }
        ],
        "prompts": ["what does Link remember about me?"],
        "next_actions": [
            {"label": "Use memory", "reason": "Try the value loop.", "command": "bh brief current-task ."}
        ],
    }

    html = render_memory_wins_page(payload, page_href=_page_href, layout=_layout)

    assert "記憶成效" in html
    assert "not telemetry" in html
    assert "Reusable &lt;context&gt;" in html
    assert "Alpha &lt;memory&gt;" in html
    assert 'data-copy-text="what does Link remember about me?"' in html
    assert "bh brief current-task ." in html
