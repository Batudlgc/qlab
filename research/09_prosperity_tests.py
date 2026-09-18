"""Correctness tests for the Prosperity harness. Run before trusting any score."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from qlab.prosperity import Order, ProductSpec, TradingState, run_trader
from qlab.prosperity.traders import DoNothing, MarketMaker

fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


SPEC = [ProductSpec("X", fair0=10_000, sigma=1.2, position_limit=20)]
LIM = {"X": 20}

# 1. control
r = run_trader(DoNothing(), SPEC, n_ticks=800, seed=0)
check("DoNothing scores exactly zero", r.score()["total_pnl"] == 0.0)

# 2. position limits are never breached
r = run_trader(MarketMaker(size=50, limits=LIM), SPEC, n_ticks=1500, seed=1)
mx = r.pnl["pos_X"].abs().max()
check("position limit respected", mx <= 20, f"(max |pos| = {mx})")

# 3. an order that would breach the limit is rejected, not silently clipped
class Overreach:
    def run(self, state: TradingState):
        return {"X": [Order("X", 99_999, 500)]}, 0, ""
r = run_trader(Overreach(), SPEC, n_ticks=50, seed=0)
check("oversized order rejected", r.score()["rejected_orders"] > 0,
      f"(rejected={r.score()['rejected_orders']})")

# 4. a raising strategy is recorded as an error, not swallowed
class Broken:
    def run(self, state):
        raise RuntimeError("boom")
r = run_trader(Broken(), SPEC, n_ticks=30, seed=0)
check("exceptions recorded", r.score()["errors"] == 30, f"({r.score()['errors']})")

# 5. crossing the spread must cost money
class Crosser:
    """Buys at the ask and sells at the bid every tick. Must lose the spread."""
    def run(self, state: TradingState):
        b = state.order_depths["X"]
        pos = state.position.get("X", 0)
        if b.best_ask is None or b.best_bid is None:
            return {}, 0, ""
        if pos <= 0:
            return {"X": [Order("X", b.best_ask, 5)]}, 0, ""
        return {"X": [Order("X", b.best_bid, -5)]}, 0, ""
r = run_trader(Crosser(), SPEC, n_ticks=1200, seed=3)
check("paying the spread loses money", r.score()["total_pnl"] < 0,
      f"(pnl={r.score()['total_pnl']:.0f})")

# 6. unknown symbols are rejected
class BadSymbol:
    def run(self, state):
        return {"NOPE": [Order("NOPE", 100, 1)]}, 0, ""
r = run_trader(BadSymbol(), SPEC, n_ticks=20, seed=0)
check("unknown symbol rejected", r.score()["rejected_orders"] == 20)

# 7. traderData round-trips
class Counter:
    def run(self, state: TradingState):
        n = int(state.traderData) if state.traderData else 0
        return {}, 0, str(n + 1)
class Peek:
    seen = []
    def run(self, state: TradingState):
        Peek.seen.append(state.traderData)
        n = int(state.traderData) if state.traderData else 0
        return {}, 0, str(n + 1)
run_trader(Peek(), SPEC, n_ticks=10, seed=0)
check("traderData persists across ticks", Peek.seen[-1] == "9", f"(last={Peek.seen[-1]})")

# 8. adverse selection: a maker facing only informed flow must lose
clean = [ProductSpec("X", fair0=10_000, sigma=1.2, position_limit=20, bot_informed=0.0)]
toxic = [ProductSpec("X", fair0=10_000, sigma=1.2, position_limit=20, bot_informed=1.0)]
pc = np.mean([run_trader(MarketMaker(limits=LIM), clean, n_ticks=1500, seed=s).score()["total_pnl"]
              for s in range(5)])
pt = np.mean([run_trader(MarketMaker(limits=LIM), toxic, n_ticks=1500, seed=s).score()["total_pnl"]
              for s in range(5)])
check("uninformed flow is profitable for a maker", pc > 0, f"({pc:.0f})")
check("fully informed flow is not", pt < pc, f"(toxic={pt:.0f} vs clean={pc:.0f})")

print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
