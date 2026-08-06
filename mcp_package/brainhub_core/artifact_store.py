"""Shared build+store and export-with-provenance-strip helpers.

Single source of truth for two operations that must behave identically whether
they are reached through the ``brainhub`` CLI verbs (``bh-build`` / ``bh-export``)
or through the MCP tools (``bh_build`` / ``bh_export``):

* :func:`build_and_store_artifact` renders a spec via the shared
  :func:`render.build_document` pipeline and writes the self-contained HTML plus
  a provenance sidecar into the workspace artifact bucket;
* :func:`export_stored_artifact` copies a stored artifact to a target path with
  the embedded provenance block stripped (fail-closed: it refuses to write if
  any provenance survives).

Neither the CLI nor the MCP layer reimplements this logic; both import these
functions. The render itself is NOT reimplemented here — it delegates to
:func:`render.build_document`, the same call the CLI already used.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import render
from .artifacts import ARTIFACT_DIRECTORIES, existing_artifact_sids
from .text import slugify
from .sid import SID_TYPE_ARTIFACT, generate_sid


def slugify_filename(text: str) -> str:
    """Turn a title into a safe artifact filename stem."""
    return slugify(text, fallback="artifact")


def build_and_store_artifact(
    spec: dict,
    workspace: Path,
    *,
    renderer: str,
    task: str,
    agent: str,
    related: list[str],
    static: bool,
    title: str | None,
    name: str | None,
) -> dict[str, Any]:
    """Render ``spec`` and store the self-contained artifact with provenance.

    Returns a structured record (kind, renderer, title, stored_path, sha256,
    absolute path). Raises ``ValueError`` (including ``render.RendererError``)
    for an unknown renderer, a rejected spec, an uninitialized workspace, or a
    name collision — the same fail-closed contract the CLI verb had.
    """
    workspace = workspace.expanduser().resolve()
    created_at = datetime.now(UTC).isoformat()
    embedded_provenance = {
        "task": task,
        "agent": agent,
        "renderer": renderer,
        "related": related,
        "static": static,
        "created_at": created_at,
    }
    result = render.build_document(
        renderer,
        spec,
        title=title,
        static=static,
        provenance=embedded_provenance,
    )
    if result.output_kind not in ARTIFACT_DIRECTORIES:
        raise ValueError(f"renderer produced unsupported artifact kind: {result.output_kind}")
    destination_dir = workspace / ARTIFACT_DIRECTORIES[result.output_kind]
    if not destination_dir.is_dir():
        raise ValueError(f"BrainHub workspace is not initialized: {workspace}")

    filename = name or f"{slugify_filename(result.title)}.html"
    if not filename.endswith(".html"):
        filename += ".html"
    destination = destination_dir / filename
    if destination.exists():
        raise ValueError(f"Artifact already exists: {destination}")
    destination.write_text(result.html, encoding="utf-8")
    metadata = {
        "kind": result.output_kind,
        "sid": generate_sid(SID_TYPE_ARTIFACT, existing_artifact_sids(workspace)),
        "task": task,
        "agent": agent,
        "related": related,
        "renderer": renderer,
        "static": static,
        "generated_by": "bh-build",
        "source_name": None,
        "stored_path": destination.relative_to(workspace).as_posix(),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "created_at": created_at,
        **({k: v for k, v in result.meta.items() if k not in {"kind", "sid", "stored_path"}}),
    }
    metadata_path = destination.with_name(destination.name + ".meta.json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {
        "kind": result.output_kind,
        "sid": metadata["sid"],
        "renderer": renderer,
        "title": result.title,
        "filename": filename,
        "stored_path": metadata["stored_path"],
        "path": str(destination),
        "sha256": metadata["sha256"],
        "static": static,
        "self_contained": True,
    }


def export_stored_artifact(
    artifact: str | Path,
    workspace: Path,
    *,
    target: Path,
    force: bool,
) -> dict[str, Any]:
    """Write a stored artifact to ``target`` with provenance stripped.

    The source must resolve INSIDE ``workspace`` (rejects escape and refuses a
    ``*.meta.json`` sidecar); the exported copy has the embedded provenance
    block removed. Fail-closed: if any provenance survives the strip, nothing is
    written. Raises ``ValueError`` on any of these conditions.
    """
    workspace = workspace.expanduser().resolve()
    candidate = Path(artifact).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    source = candidate.resolve()
    if not source.is_relative_to(workspace):
        raise ValueError(f"Artifact is outside the workspace: {source}")
    if source.name.endswith(".meta.json"):
        raise ValueError("Refusing to export a provenance sidecar; export the artifact itself")
    if not source.is_file():
        raise ValueError(f"Artifact not found: {source}")

    target = Path(target).expanduser()
    if target.exists() and not force:
        raise ValueError(f"Export target already exists (use --force): {target}")

    document = source.read_text(encoding="utf-8")
    cleaned = render.strip_provenance(document)
    if render.has_provenance(cleaned):  # fail-closed: never ship provenance
        raise ValueError("Failed to strip provenance from artifact; refusing to export")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(cleaned, encoding="utf-8")
    return {
        "source": source.relative_to(workspace).as_posix(),
        "target": str(target),
        "provenance_stripped": True,
        "bytes": len(cleaned.encode("utf-8")),
    }
