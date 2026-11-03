"""Walk one trade through the event loop, then summarise a full run.

    python3 research/12_event_demo.py

Simulated prices only (seeded random walk). The point is the mechanism, not the PnL:
the strategy is a control and on a random walk it has no edge (see 11_event_tests.py, check 10).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qlab.events import MACross, RiskLimits, run, synthetic_ticks
from qlab.events.core import ORDER_FILLED

PX = synthetic_ticks(3000, seed=1)
r = run(PX, MACross(fast=5, slow=20, size=10),
        RiskLimits(position_limit=20, max_order=25, max_drawdown=30.0))
log = r.bus.log


def chain(ev):
    out = [ev]
    while out[-1].parent is not None:
        out.append(log[out[-1].parent])
    return out[::-1]


print("One trade, from the tick that closed the bar to the fill:\n")
first_fill = r.bus.of_type(ORDER_FILLED)[0]
for e in chain(first_fill):
    p = {k: round(v, 4) if isinstance(v, float) else v for k, v in e.payload.items()}
    print(f"  t={e.ts:<5} {e.type:<16} {e.source:<12} {e.reason:<34} {p}")

s = r.score()
print("\nFull run:")
for k in ("pnl", "fees", "fills", "final_position", "max_drawdown", "halted", "rejected"):
    print(f"  {k:<15} {s[k]}")
print("\nEvents published:")
for k, v in s["events"].items():
    print(f"  {k:<16} {v}")
