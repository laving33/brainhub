"""Dashboard history — the append-only file that makes "better or worse?" answerable.

Why this module exists: ``dashboard/spog.json`` is a point-in-time snapshot and
nothing else. The board could say P1 is 4; it could not say whether 4 is an
improvement on last week. Measured before this was written: ``grep`` for trend /
↑ / ↓ / 比上週 across the dashboard returned zero hits. A board with no time
dimension answers "what is happening" and silently declines "is this getting
worse", which is the question a CXO actually asks.

THE FORMAT IS THE POINT
-----------------------
One JSON object per line in ``dashboard/history.jsonl`` — append-only, no
database, no migration, ``tail -1`` readable, and a corrupt line costs one point
rather than the file. Each line carries counts only, never item text: the board
already holds the prose, and copying it per snapshot would turn a trend log into
a slowly growing duplicate of the board.

    {"counts": {"P0": 1, "P1": 4}, "kpis": {"待決策": 1},
     "recorded_at": "2026-08-02T…+00:00", "updated_at": "2026-07-28T…+08:00"}

Two stamps, because they answer different questions. ``updated_at`` is the
BOARD's own stamp — the version of reality this row describes, and the x-axis.
``recorded_at`` is when the row was written, which is the only stamp available
when a board arrives with no ``updated_at`` at all.

APPENDING IS IDEMPOTENT, WHICH IS WHAT MAKES IT SAFE TO CALL FROM A RENDER
-------------------------------------------------------------------------
:func:`record_snapshot` writes only when the board's data version differs from
the last row (see :func:`snapshot_key`), so calling it on every page view
records one point per data update rather than one point per reader. That is also
what lets a future cron/worker append without touching the renderer: it builds a
snapshot and calls :func:`record_snapshot` on the same path. Nothing in this
module renders, and nothing in the renderer writes.

Writes are best-effort by construction — a read-only workspace loses the trend,
not the dashboard.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

from .web_dashboard import parse_timestamp

HISTORY_FILENAME = "history.jsonl"

# The rendering window, NOT a retention policy: the file keeps everything, the
# chart shows the tail. Thirty daily points is roughly a month, which is the
# span "better or worse than last week" is asked over.
HISTORY_WINDOW = 30

# The derived KPI that has no section of its own (it is computed from
# ``decisions/``, not typed into the board), kept under ``kpis`` so a reader can
# tell a derived number from a section count.
PENDING_KEY = "待決策"

# What the trend chart plots. The four priority buckets plus the one derived
# KPI — the numbers the board is steered by.
TREND_KEYS: tuple[str, ...] = ("P0", "P1", "P2", "P3", PENDING_KEY)


def history_path(dashboard_dir: Path) -> Path:
    """Where the log lives, next to the data file it describes."""
    return Path(dashboard_dir) / HISTORY_FILENAME


def build_snapshot(
    data: Mapping | None,
    *,
    pending: int = 0,
    now: datetime | None = None,
) -> dict:
    """One compact row from a loaded ``spog.json`` — counts only, no item text.

    A section contributes its id (falling back to its title) and how many items
    it holds. ``pending`` is the derived open-decision count the caller already
    computed for the KPI row; it rides in ``kpis`` so the two kinds of number
    stay distinguishable downstream.
    """
    moment = (now or datetime.now(timezone.utc))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    counts: dict[str, int] = {}
    sections = (data or {}).get("sections") if isinstance(data, Mapping) else None
    for section in sections or ():
        if not isinstance(section, Mapping):
            continue
        key = str(section.get("id") or section.get("title") or "").strip()
        if not key:
            continue
        items = [it for it in (section.get("items") or ()) if isinstance(it, Mapping)]
        counts[key] = len(items)
    updated_at = ""
    if isinstance(data, Mapping):
        updated_at = str(data.get("updated_at") or "").strip()
    return {
        "updated_at": updated_at,
        "recorded_at": moment.astimezone(timezone.utc).isoformat(),
        "counts": counts,
        "kpis": {PENDING_KEY: int(pending)},
    }


def snapshot_key(snapshot: Mapping) -> str:
    """The data version a row describes — the dedupe key.

    The board's own ``updated_at`` when it has one. When it does not, the
    recording DATE (not time), so a board that never stamps itself still records
    at most one point per day instead of one per page view.
    """
    stamp = str(snapshot.get("updated_at") or "").strip()
    if stamp:
        return stamp
    return str(snapshot.get("recorded_at") or "")[:10]


def read_history(path: Path, *, limit: int | None = None) -> list[dict]:
    """Rows oldest-first, tolerating damage. Unreadable file -> ``[]``.

    A line that is not a JSON object is skipped rather than fatal: this file is
    appended to by more than one process over time, and a half-written final
    line must cost one point, not the whole trend.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    if limit is not None and limit >= 0:
        rows = rows[-limit:] if limit else []
    return rows


def append_snapshot(path: Path, snapshot: Mapping) -> bool:
    """Append one row. Returns whether it was written (never raises).

    ``sort_keys`` so two runs over the same numbers produce the same bytes — the
    log is diffable for the same reason the SVGs are.
    """
    try:
        line = json.dumps(dict(snapshot), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return False
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        return False
    return True


def record_snapshot(path: Path, snapshot: Mapping) -> list[dict]:
    """Idempotent append; returns the history INCLUDING the row if it was added.

    Only a new data version is written. Called on every render, this seeds the
    first point from whatever the board currently says (so a fresh install has
    one honest point rather than none) and then records one point per update.
    """
    history = read_history(path)
    if history and snapshot_key(history[-1]) == snapshot_key(snapshot):
        return history
    if append_snapshot(path, snapshot):
        history.append(dict(snapshot))
    return history


def metric(snapshot: Mapping, key: str) -> int | float | None:
    """A row's number for ``key``, or None when that row does not carry it.

    None is a real answer and callers must keep it: a key absent from an old
    snapshot means the board had no such row then, which is NOT the same claim
    as zero. Booleans are rejected explicitly — ``isinstance(True, int)``.
    """
    for holder in ("counts", "kpis"):
        source = snapshot.get(holder)
        if not isinstance(source, Mapping):
            continue
        value = source.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
    return None


def point_label(snapshot: Mapping, index: int = 0) -> str:
    """"07-28" for the x-axis — the board's stamp, else the recording stamp."""
    for field in ("updated_at", "recorded_at"):
        stamp = parse_timestamp(snapshot.get(field))
        if stamp is not None:
            return stamp.strftime("%m-%d")
    return f"#{index + 1}"


def trend_series(
    history: Sequence[Mapping],
    *,
    keys: Sequence[str] = TREND_KEYS,
    window: int = HISTORY_WINDOW,
) -> tuple[list[dict], list[str], list[str]]:
    """``(series, x_labels, omitted)`` shaped for ``report_chart.line``.

    A key is charted only when EVERY point in the window carries it. The
    alternative — substituting 0 for a missing key — draws a line saying "this
    was at zero back then" when what actually happened is that the board had no
    such section, and a fabricated zero in a trend is indistinguishable from a
    measured one. Keys that cannot be drawn come back in ``omitted`` so the page
    can say so out loud instead of quietly plotting four series where five were
    asked for.
    """
    rows = list(history)[-window:] if window and window > 0 else list(history)
    labels = [point_label(row, i) for i, row in enumerate(rows)]
    series: list[dict] = []
    omitted: list[str] = []
    for key in keys:
        values = [metric(row, key) for row in rows]
        if not rows or any(value is None for value in values):
            omitted.append(key)
            continue
        series.append({"name": key, "values": list(values)})
    return series, labels, omitted


def baseline_for(history: Sequence[Mapping], current_key: str) -> dict | None:
    """The newest row that is NOT the current data version, or None.

    None means there is no baseline, and that has to stay distinguishable from
    "a baseline with the same numbers": the first is "we cannot say", the second
    is "no change". Callers render the first as nothing at all.
    """
    for row in reversed(list(history)):
        if isinstance(row, Mapping) and snapshot_key(row) != current_key:
            return dict(row)
    return None


def compute_deltas(current: Mapping, baseline: Mapping | None) -> dict[str, int | float]:
    """``{key: current - baseline}`` for keys BOTH rows carry. No baseline -> ``{}``.

    An empty dict is the whole no-baseline contract: the tile renderer draws
    nothing for a key that is not in here, so absence of history reads as absence
    rather than as a confident "±0".
    """
    if not isinstance(baseline, Mapping):
        return {}
    deltas: dict[str, int | float] = {}
    keys: list[str] = []
    for holder in ("counts", "kpis"):
        source = current.get(holder)
        if isinstance(source, Mapping):
            keys.extend(str(k) for k in source)
    for key in keys:
        now_value = metric(current, key)
        was_value = metric(baseline, key)
        if now_value is None or was_value is None:
            continue
        deltas[key] = now_value - was_value
    return deltas


_USAGE = "usage: python -m brainhub_core.dashboard_history <workspace-root> [pending-count]"


def _main(argv: Sequence[str]) -> int:
    """``python -m brainhub_core.dashboard_history <workspace> [pending]`` — the cron entry.

    Appends one point for the workspace's current ``spog.json`` if that version
    is not logged yet, and prints what it did. No rendering, no server, no import
    of either: this is the path a scheduled worker takes, and it exercises the
    same two public functions the renderer uses.

    ``pending`` (the open-decision KPI) is DERIVED from ``decisions/`` by the
    server, which owns what "undecided" means. Rather than restate that rule
    here and let the two drift, an unsupplied count is left out of the row
    entirely — the trend then reports 待決策 as un-drawable for that stretch
    instead of charting a zero nobody measured.
    """
    if len(argv) not in (2, 3):
        print(_USAGE)
        return 2
    root = Path(argv[1]).expanduser().resolve()
    dashboard_dir = root / "dashboard"
    data_path = dashboard_dir / "spog.json"
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {data_path}: {exc}")
        return 1
    if not isinstance(data, dict):
        print(f"{data_path}: top level must be a JSON object")
        return 1
    path = history_path(dashboard_dir)
    before = len(read_history(path))
    if len(argv) == 3:
        try:
            snapshot = build_snapshot(data, pending=int(argv[2]))
        except ValueError:
            print(_USAGE)
            return 2
    else:
        snapshot = build_snapshot(data)
        snapshot.pop("kpis", None)
        print(f"note: no pending-count given -> {PENDING_KEY} not logged for this point")
    history = record_snapshot(path, snapshot)
    added = len(history) - before
    print(f"{path}: {len(history)} point(s), {added} appended")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    import sys

    raise SystemExit(_main(sys.argv))
