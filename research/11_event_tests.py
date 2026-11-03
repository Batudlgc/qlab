"""Correctness tests for the event-driven loop. Run before trusting any number it prints."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from qlab.events import DoNothing, MACross, RiskLimits, run, synthetic_ticks
from qlab.events.core import (MARKET_TICK, ORDER_FILLED, ORDER_SUBMITTED, RISK_PASSED,
                              SIGNAL_CREATED)

fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


PX = synthetic_ticks(3000, seed=1)
LOOSE = RiskLimits(position_limit=20, max_order=40, max_drawdown=1e9)

# 1. control
r = run(PX, DoNothing())
s = r.score()
check("DoNothing: zero PnL, zero fills", s["pnl"] == 0.0 and s["fills"] == 0)

# 2. replay is deterministic
a = run(PX, MACross(), LOOSE).bus.log
b = run(synthetic_ticks(3000, seed=1), MACross(), LOOSE).bus.log
same = [(e.type, e.ts, e.payload) for e in a] == [(e.type, e.ts, e.payload) for e in b]
check("replay reproduces the event log exactly", same, f"({len(a)} events)")

# 3. every event has a source, a reason, and a parent that happened no later
r = run(PX, MACross(), LOOSE)
log = r.bus.log
ok = all(e.source and e.reason for e in log)
ok &= all(e.type == MARKET_TICK or (e.parent is not None and log[e.parent].ts <= e.ts)
          for e in log)
check("schema: source, reason, causal parent on every event", ok)

# 4. no trading at the decision price: fills happen one tick after the order, at that tick
fills = r.bus.of_type(ORDER_FILLED)
nxt = all(f.ts == log[f.parent].ts + 1 and f.payload["mid"] == float(PX[f.ts]) for f in fills)
chain = all(log[log[log[f.parent].parent].parent].type in (SIGNAL_CREATED, "PNL_UPDATED")
            for f in fills)
check("fills at next tick's price, never the signal tick", nxt and chain and len(fills) > 0,
      f"({len(fills)} fills)")

# 5. position limit: a strategy asking for 50 is refused, not clipped
r = run(PX, MACross(size=50), RiskLimits(position_limit=20, max_drawdown=1e9))
s = r.score()
check("oversized target rejected, not clipped",
      s["fills"] == 0 and s["rejected"].get("position_limit", 0) > 0, f"({s['rejected']})")

# 6. max order size: flipping +15 -> -15 is a 30-lot order and must be refused
r = run(PX, MACross(size=15), RiskLimits(position_limit=20, max_order=25, max_drawdown=1e9))
s = r.score()
pos = np.cumsum([f.payload["qty"] for f in r.bus.of_type(ORDER_FILLED)])
check("max order size enforced",
      s["rejected"].get("max_order", 0) > 0 and (np.abs(pos) <= 20).all(), f"({s['rejected']})")

# 7. accounting: equity equals the PnL of every fill marked to the last price, minus fees
r = run(PX, MACross(), LOOSE)
last = float(PX[-1])
fills = r.bus.of_type(ORDER_FILLED)
expect = sum(f.payload["qty"] * (last - f.payload["price"]) - f.payload["fee"] for f in fills)
check("equity = sum of marked fills - fees", abs(r.portfolio.equity - expect) < 1e-8,
      f"({r.portfolio.equity:.6f} vs {expect:.6f})")

# 8. costs are charged: same decisions, the only difference in PnL is spread + fees
free = run(PX, MACross(), LOOSE, half_spread_bps=0, fee_bps=0)
paid = run(PX, MACross(), LOOSE)
cost = sum(abs(f.payload["qty"]) * abs(f.payload["price"] - f.payload["mid"]) + f.payload["fee"]
           for f in paid.bus.of_type(ORDER_FILLED))
diff = free.portfolio.equity - paid.portfolio.equity
check("costs reduce PnL by exactly spread + fees", cost > 0 and abs(diff - cost) < 1e-8,
      f"(cost={cost:.4f}, diff={diff:.4f})")

# 9. drawdown kill-switch: flattens once, then refuses everything
r = run(PX, MACross(), RiskLimits(position_limit=20, max_order=40, max_drawdown=1.0))
s = r.score()
passed = r.bus.of_type(RISK_PASSED)
halt_i = next(i for i, e in enumerate(passed) if "halt" in e.reason)
check("drawdown breach flattens and halts",
      s["halted"] and s["final_position"] == 0 and halt_i == len(passed) - 1
      and s["rejected"].get("halted", 0) > 0, f"({s['rejected']})")

# 10. no free lunch: on a driftless frictionless random walk, mean PnL is indistinguishable from 0
pnls = [run(synthetic_ticks(3000, seed=k), MACross(), LOOSE, half_spread_bps=0, fee_bps=0)
        .portfolio.equity for k in range(100, 160)]
m, se = np.mean(pnls), np.std(pnls, ddof=1) / np.sqrt(len(pnls))
check("no edge on a random walk without costs", abs(m) < 3 * se, f"(mean={m:.3f}, se={se:.3f})")

print()
print("ALL TESTS PASSED" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
