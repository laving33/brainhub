"""Stable ids for raw source files.

Raw files are the one addressable thing in BrainHub with no place to keep
metadata: a wiki page has frontmatter and an artifact has a ``.meta.json``
sidecar, but a raw file is whatever the client sent us — a PDF, an audio file,
a text dump. So the ids live in one hidden registry, ``raw/.sids.json``.

Why hidden and not a sidecar per file: ``ingest.raw_source_files()`` walks
``raw/`` with ``rglob("*")`` and treats every file it finds as a source to
ingest, skipping only dotfiles. A ``x.pdf.meta.json`` sidecar would therefore
be ingested as if it were a source document; ``.sids.json`` is skipped by the
rule that already exists.

Each entry keeps a sha256 next to the path, which is what makes the id worth
having: today a source page cites its raw file **by path substring**
(``ingest.source_matches_by_raw``), so renaming the file silently detaches the
page from its evidence. Resolution here falls back to the digest, so a renamed
or moved file is still found — and a file whose bytes changed under a stable
name is visible rather than silently swapped.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from .files import atomic_write_json
from .sid import SID_TYPE_RAW, generate_sid, normalize_sid

REGISTRY_NAME = ".sids.json"


def raw_dir(root: Path) -> Path:
    return root.expanduser().resolve() / "raw"


def registry_path(root: Path) -> Path:
    return raw_dir(root) / REGISTRY_NAME


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_registry(root: Path) -> dict[str, dict]:
    """Read the registry, tolerating absence and corruption (never raises)."""
    path = registry_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        sid: entry
        for sid, entry in data.items()
        if normalize_sid(sid) == sid and isinstance(entry, dict)
    }


def _save_registry(root: Path, registry: dict[str, dict]) -> None:
    raw_dir(root).mkdir(parents=True, exist_ok=True)
    atomic_write_json(registry_path(root), registry)


def sid_for_path(root: Path, rel_path: str) -> str:
    """The sid already assigned to this relative path, or ""."""
    for sid, entry in load_registry(root).items():
        if entry.get("path") == rel_path:
            return sid
    return ""


def assign(root: Path, path: Path) -> str:
    """Assign (or return) the sid for a raw file. Idempotent.

    Re-running on an unchanged file returns the same sid and rewrites nothing
    of consequence; on changed bytes it keeps the sid and refreshes the digest,
    so the id follows the file rather than the version.
    """
    root = root.expanduser().resolve()
    path = path.expanduser().resolve()
    rel = path.relative_to(root).as_posix()
    registry = load_registry(root)

    existing = sid_for_path(root, rel)
    digest = _digest(path)
    if existing:
        entry = registry[existing]
        if entry.get("sha256") != digest:
            entry["sha256"] = digest
            entry["updated_at"] = datetime.now(UTC).isoformat()
            _save_registry(root, registry)
        return existing

    sid = generate_sid(SID_TYPE_RAW, set(registry))
    registry[sid] = {
        "path": rel,
        "sha256": digest,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _save_registry(root, registry)
    return sid


def resolve(root: Path, sid: object) -> Path | None:
    """The file a raw sid points at: by path, else by digest when it moved."""
    root = root.expanduser().resolve()
    normalized = normalize_sid(sid)
    if not normalized:
        return None
    entry = load_registry(root).get(normalized)
    if not entry:
        return None
    recorded = root / str(entry.get("path", ""))
    if recorded.is_file():
        return recorded
    digest = str(entry.get("sha256", ""))
    if not digest:
        return None
    for candidate in sorted(raw_dir(root).rglob("*")):
        if candidate.is_file() and not candidate.name.startswith("."):
            try:
                if _digest(candidate) == digest:
                    return candidate
            except OSError:
                continue
    return None


def backfill(root: Path) -> dict[str, object]:
    """Assign ids to every raw file lacking one (engine op, idempotent)."""
    root = root.expanduser().resolve()
    directory = raw_dir(root)
    assigned: list[dict[str, str]] = []
    if not directory.is_dir():
        return {"count": 0, "assigned": assigned}
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(root).as_posix()
        if sid_for_path(root, rel):
            continue
        assigned.append({"sid": assign(root, path), "path": rel})
    return {"count": len(assigned), "assigned": assigned}
