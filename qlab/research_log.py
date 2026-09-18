"""Research log - the honest counter of how many strategies you have tested.

Every backtest you run gets appended here. The count feeds `deflated_sharpe`.
If you do not log your failures, your Sharpe is a lie.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "reports" / "research_log.jsonl"
LOG.parent.mkdir(parents=True, exist_ok=True)


def record(name: str, params: dict, stats: dict, notes: str = "") -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name": name, "params": params, "stats": stats, "notes": notes,
    }
    with LOG.open("a") as fh:
        fh.write(json.dumps(entry, default=float) + "\n")


def n_trials() -> int:
    if not LOG.exists():
        return 0
    return sum(1 for line in LOG.open() if line.strip())


def entries() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(line) for line in LOG.open() if line.strip()]
