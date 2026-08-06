import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.web_propose import render_propose_page  # noqa: E402


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def test_render_propose_page_shows_review_only_workflow():
    html = render_propose_page("link", "raw/first-memory.md", layout=_layout)

    assert "<title>草擬記憶</title>" in html
    assert "不會寫入任何內容" in html
    assert "只儲存你核可的偏好" in html
    assert "審核關卡" in html
    assert "儲存記憶之前" in html
    assert "一般事實留在 wiki 頁面" in html
    assert "記憶提案流程" in html
    assert "明確核可" in html
    assert "這一步永遠不會寫入長期記憶" in html
    assert "核可之後" in html
    assert "開啟記憶待審清單" in html
    assert "開啟記憶稽核" in html
    assert 'data-copy-text="先跟 BrainHub 對一下，我們再繼續"' in html
    assert 'data-copy-text="跟 BrainHub 查詢你記得關於這件事的內容"' in html
    assert 'data-proposal-sources' in html
    assert 'data-proposal-form' in html
    assert 'data-initial-source="raw/first-memory.md"' in html
    assert 'data-proposal-results' in html
    assert 'value="link"' in html


def test_render_propose_page_escapes_seed_values():
    html = render_propose_page('<project>', 'raw/<source>.md', layout=_layout)

    assert 'value="&lt;project&gt;"' in html
    assert 'data-initial-source="raw/&lt;source&gt;.md"' in html
    assert "<project>" not in html
    assert "raw/<source>.md" not in html
