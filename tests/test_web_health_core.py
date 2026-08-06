import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.web_health import render_health_page  # noqa: E402


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def test_render_health_page_shows_readiness_operations_and_commands(tmp_path):
    wiki = tmp_path / "wiki"
    html = render_health_page(
        {
            "wiki": str(wiki),
            "ready": False,
            "content_page_count": 12,
            "memory_count": 2,
            "active_memory_count": 2,
            "needs_review_count": 1,
            "search_backend": "sqlite-fts",
            "fts_index": {"available": True, "persistent": True, "reused": True},
            "persistent_cache": {"enabled": True, "reused_records": 10, "total_records": 12},
            "schema": {"status": "current"},
            "validation": {"checked": True, "passed": False},
            "warnings": [{"code": "stale_operations", "message": "1 operation needs review.", "detail": "remember"}],
            "next_actions": [{"label": "validate wiki", "tool": "validate_wiki"}],
        },
        {
            "wiki": str(wiki),
            "operation_count": 1,
            "stale_count": 1,
            "active_count": 0,
            "next_actions": [
                {
                    "label": "inspect operation marker files before deleting them",
                    "command": f"bh operations {tmp_path}",
                }
            ],
            "operations": [{"operation": "remember", "description": "Save memory", "marker": "remember-1.json"}],
        },
        layout=_layout,
    )

    assert "<h1>健康度</h1>" in html
    assert 'aria-label="健康度總覽"' in html
    assert '<strong>就緒狀態</strong><span>需要處理</span><small>12 個內容頁面</small>' in html
    assert '<strong>驗證</strong><span>未通過</span><small>0 個錯誤 · 0 個警告</small>' in html
    assert '<strong>操作</strong><span>需要檢視</span><small>1 個過期 · 0 個進行中</small>' in html
    assert '<strong>記憶審核</strong><span>1 筆待處理</span><small>2 則使用中的記憶</small>' in html
    assert "下一個安全動作" in html
    assert "在做更多修復之前，應該先檢查中斷的寫入。" in html
    assert "sqlite-fts" in html
    assert "全文檢索索引" in html
    assert "持久化" in html
    assert "持久化快取" in html
    assert "重複使用 10/12 個頁面" in html
    assert "stale_operations" in html
    assert "remember-1.json" in html
    assert "操作的下一步" in html
    assert str(tmp_path) in html
    assert "bh onboard" in html
    assert "bh operations" in html
    assert "bh benchmark" in html
    assert "agent memory" in html


def test_render_health_page_maps_ready_actions_to_targeted_commands(tmp_path):
    wiki = tmp_path / "wiki"
    html = render_health_page(
        {
            "wiki": str(wiki),
            "ready": True,
            "content_page_count": 4,
            "memory_count": 1,
            "active_memory_count": 1,
            "needs_review_count": 0,
            "search_backend": "sqlite-fts",
            "schema": {"status": "current"},
            "validation": {"checked": True, "passed": True},
            "warnings": [],
            "next_actions": [{"label": "answer with compact local context", "tool": "query_link"}],
        },
        {
            "wiki": str(wiki),
            "operation_count": 0,
            "stale_count": 0,
            "active_count": 0,
            "next_actions": [],
            "operations": [],
        },
        layout=_layout,
    )

    assert "下一個安全動作" in html
    assert "bh query" in html
    assert "what should I know before continuing?" in html
    assert str(tmp_path) in html


def test_render_health_page_targets_memory_review_command(tmp_path):
    wiki = tmp_path / "wiki"
    html = render_health_page(
        {
            "wiki": str(wiki),
            "ready": True,
            "content_page_count": 4,
            "memory_count": 1,
            "active_memory_count": 1,
            "needs_review_count": 1,
            "search_backend": "sqlite-fts",
            "schema": {"status": "current"},
            "validation": {"checked": True, "passed": True},
            "warnings": [],
            "next_actions": [],
        },
        {
            "wiki": str(wiki),
            "operation_count": 0,
            "stale_count": 0,
            "active_count": 0,
            "next_actions": [],
            "operations": [],
        },
        layout=_layout,
    )

    assert "審核待處理的記憶" in html
    assert "bh memory-inbox" in html
    assert str(tmp_path) in html
