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
