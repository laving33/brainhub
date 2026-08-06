"""Shared first-run prompt helpers for BrainHub."""
from __future__ import annotations

from pathlib import Path

from .memory import default_project_for_target, normalize_project
from .mcp_verify import display_command


def _command_target(target: Path) -> Path:
    if target.name == "wiki" and (target / "index.md").exists():
        return target.parent
    return target


def starter_prompt_payload(target: Path, project: str | None = None) -> dict[str, object]:
    """Return natural agent prompts and local checks for a BrainHub user."""
    target = target.expanduser().resolve()
    command_target = str(_command_target(target))
    project_name = normalize_project(project) if project is not None else default_project_for_target(target)
    remember_prompt = (
        "記住這個專案用 BrainHub 做內部 wiki 與 agent 記憶"
        if project_name
        else "記住我偏好本地優先的 agent 記憶"
    )
    query_prompt = (
        "BrainHub 記得這個專案的什麼？"
        if project_name
        else "BrainHub 對我了解多少？"
    )
    prompts = [
        {
            "label": "檢查就緒",
            "prompt": "BrainHub 準備好了嗎？",
            "when": "剛安裝完、或排查問題之前",
        },
        {
            "label": "用 BrainHub 開場",
            "prompt": "繼續之前先用 BrainHub 開場",
            "when": "session 或任務的開頭",
        },
        {
            "label": "灌入專案脈絡",
            "prompt": "把這個專案灌進 BrainHub",
            "when": "在 repo 裡安裝後、第一次專案 recall 之前",
        },
        {
            "label": "存明確記憶",
            "prompt": remember_prompt,
            "when": "想讓之後的 agent 記住某個偏好、決策或專案事實時",
        },
        {
            "label": "帶脈絡提問",
            "prompt": query_prompt,
            "when": "想從記憶與 wiki 脈絡拿到精簡、可直接回答的包時",
        },
        {
            "label": "匯入來源",
            "prompt": "把 raw/<檔案> 匯入 BrainHub",
            "when": "把來源檔丟進 raw/ 之後",
        },
        {
            "label": "審查記憶建議",
            "prompt": "從 raw/<檔案> 提出記憶建議",
            "when": "當某個來源可能含偏好、決策或專案脈絡時",
        },
    ]
    return {
        "target": str(target),
        "project": project_name,
        "shortcut": display_command(["link", "next", command_target]),
        "prompts": prompts,
        "commands": [
            display_command(["link", "seed", ".", command_target]),
            display_command(["link", "health", command_target]),
            display_command(["link", "ingest-status", command_target]),
            display_command(["link", "memory-inbox", command_target]),
            display_command(["link", "benchmark", "agent memory", command_target]),
        ],
    }


def welcome_payload(target: Path, project: str | None = None) -> dict[str, object]:
    """Return a short first-use path for a human trying BrainHub with an agent."""
    starter = starter_prompt_payload(target, project=project)
    command_target = str(_command_target(target.expanduser().resolve()))
    prompts = [
        item for item in starter.get("prompts", [])
        if isinstance(item, dict)
    ]
    proof = [
        "Agent 能找到 BrainHub 並確認就緒狀態。",
        "Agent 能用精簡的本地記憶為自己暖身。",
        "Agent 只在你要求時才存明確記憶。",
    ]
    steps = []
    for index, item in enumerate(prompts[:3], start=1):
        steps.append({
            "step": index,
            "label": item.get("label", ""),
            "prompt": item.get("prompt", ""),
            "proves": proof[index - 1],
        })
    return {
        "target": starter["target"],
        "project": starter["project"],
        "steps": steps,
        "commands": [
            display_command(["link", "health", command_target]),
            display_command(["link", "serve", command_target]),
            display_command(["link", "ingest-status", command_target]),
            display_command(["link", "prompts", command_target]),
        ],
        "urls": [
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3000/onboard",
            "http://127.0.0.1:3000/health",
            "http://127.0.0.1:3000/graph",
        ],
    }
