import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.web_prompts import render_prompts_page  # noqa: E402


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def test_render_prompts_page_shows_project_and_commands():
    payload = {
        "project": "client-launch",
        "shortcut": "bh next /tmp/link",
        "prompts": [{"label": "Readiness", "prompt": "is Link ready?", "when": "Before work"}],
        "commands": ["bh health"],
    }

    html = render_prompts_page(payload, layout=_layout)

    assert "<title>入門提示詞</title>" in html
    assert "以下範例僅限於專案 <code>client-launch</code>" in html
    assert "一鍵指令" in html
    assert "忘記接下來該問什麼時，隨時可以用這個。" in html
    assert "bh next /tmp/link" in html
    assert 'data-copy-text="bh next /tmp/link"' in html
    assert "詢問你的 Agent" in html
    assert "本機檢查" in html
    assert "is Link ready?" in html
    assert 'data-copy-text="is Link ready?"' in html
    assert "Before work" in html
    assert "bh health" in html
    assert 'data-copy-text="bh health"' in html


def test_render_prompts_page_escapes_payload_fields():
    payload = {
        "project": "<project>",
        "prompts": [{"label": "<label>", "prompt": "ingest raw/<file>", "when": "<when>"}],
        "commands": ["bh query '<topic>'"],
    }

    html = render_prompts_page(payload, layout=_layout)

    assert "&lt;project&gt;" in html
    assert "&lt;label&gt;" in html
    assert "ingest raw/&lt;file&gt;" in html
    assert 'data-copy-text="ingest raw/&lt;file&gt;"' in html
    assert "&lt;when&gt;" in html
    assert "bh query &#x27;&lt;topic&gt;&#x27;" in html
    assert "<project>" not in html


def test_render_prompts_page_uses_personal_copy_without_project():
    html = render_prompts_page({"prompts": [], "commands": []}, layout=_layout)

    assert "個人 BrainHub wiki" in html
    assert "?project=slug" in html
