"""Workspace-level BrainHub configuration (stored outside wiki/)."""
from __future__ import annotations

import json
from pathlib import Path


CONFIG_FILE = "brainhub.config.json"


def config_path(workspace: Path) -> Path:
    """Return the workspace-level config file path (workspace root, not wiki/)."""
    return Path(workspace).expanduser() / CONFIG_FILE


def load_workspace_config(workspace: Path) -> dict[str, object]:
    """Load workspace config; a missing or invalid file reads as empty config."""
    try:
        data = json.loads(config_path(workspace).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def memory_layer_enabled(workspace: Path) -> bool:
    """Whether the memory layer (remember/recall/review/captures) is enabled.

    Defaults to enabled when no config file exists, so plain wikis keep the
    historical behavior; set "memory_enabled": false to run documents-only.
    """
    return bool(load_workspace_config(workspace).get("memory_enabled", True))


def memory_disabled_notice(workspace: Path) -> str:
    """One-line explanation shared by CLI, MCP, and viewer when memory is off."""
    return (
        "memory layer disabled for this workspace; enable it by setting "
        f'"memory_enabled": true in {config_path(workspace)}'
    )
