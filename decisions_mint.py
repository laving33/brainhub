#!/usr/bin/env python3
"""Mint a fresh decision-board sid (D-prefixed) for a new batch.

Usage: python3 decisions_mint.py <workspace>
  <workspace> = the brainhub workspace, e.g. /home/aworkr/aworkr/core/brainhub

Prints a sid like D3K7MX to stdout. Author the batch as decisions/<sid>.json and
set the batch's "batch_id" field to the same sid. The sid never repeats, and the
leading D marks it a decision board (mirrors wiki W / artifact A). Legacy slug
batch_ids still resolve, but new batches should use a sid.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "mcp_package"))
from brainhub_core.sid import generate_sid, normalize_sid, SID_TYPE_DECISION


def existing_decision_sids(decisions_dir: Path) -> set[str]:
    """Every already-issued decision sid, so a fresh mint avoids collisions."""
    out: set[str] = set()
    if decisions_dir.is_dir():
        for path in decisions_dir.glob("*.json"):
            sid = normalize_sid(path.stem)
            if sid:
                out.add(sid)
    return out


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: decisions_mint.py <workspace>", file=sys.stderr)
        raise SystemExit(1)
    decisions_dir = Path(sys.argv[1]).expanduser() / "decisions"
    print(generate_sid(SID_TYPE_DECISION, existing_decision_sids(decisions_dir)))


if __name__ == "__main__":
    main()
