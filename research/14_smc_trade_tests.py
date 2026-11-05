"""Correctness tests for orders and simulated fills. Offline: hand-built minutes and a random walk."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from qlab.smc import trades as tr

fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


T0 = pd.Timestamp("2024-01-01 00:00")
FLAT = (100.5, 100.8, 100.2, 100.5)        # never reaches entry 100, stop 99 or target 103


def minutes(bars, pad=10):
    rows = list(bars) + [FLAT] * pad
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.index = pd.date_range(T0, periods=len(df), freq="min")
    df["volume"] = 1.0
    return df


def order(d=1, entry=100.0, stop=99.0, target=103.0, at=0, life=30):
    return {"known": T0 + pd.Timedelta(minutes=at), "direction": d, "entry": entry, "stop": stop,
            "target": target, "risk": d * (entry - stop),
            "expires": T0 + pd.Timedelta(minutes=at + life), "atr": 1.0, "fvg_pos": 0}


def run(bars, *orders, pad=10):
    return tr.simulate(pd.DataFrame(list(orders)), minutes(bars, pad))


# 1. a limit that is touched but not traded through never fills
r = run([(100.5, 100.8, 100.0, 100.5)], order(life=5)).iloc[0]
check("touch is not a fill", r.status == "expired", f"({r.status})")

# 2. fill, then target: +3R gross, fees on both sides
r = run([(100.5, 100.8, 99.9, 100.2), (102.0, 103.5, 101.9, 103.2)], order()).iloc[0]
check("fill then target", (r.status, r.exit_reason, r.exit_price) == ("filled", "target", 103.0))
check("target R net of fees", np.isclose(r.r_gross, 3.0) and np.isclose(r.r_net, 3.0 - 0.001 * 203),
      f"(gross {r.r_gross:.4f}, net {r.r_net:.4f})")

# 3. fill, then stop: -1R less slippage and fees
r = run([(100.5, 100.8, 99.9, 100.2), (99.5, 99.6, 98.8, 98.9)], order()).iloc[0]
stop_px = 99 * (1 - 0.0002)
check("fill then stop at stop less 2 bps", r.exit_reason == "stop" and np.isclose(r.exit_price, stop_px))
check("stop R net of slippage and fees",
      np.isclose(r.r_net, (stop_px - 100) - 0.001 * (100 + stop_px)), f"({r.r_net:.4f})")

# 4. a minute spanning both stop and target books the stop
r = run([(100.5, 100.8, 99.9, 100.2), (100.5, 103.5, 98.5, 101.0)], order()).iloc[0]
check("stop and target in one minute: stop", r.exit_reason == "stop")

# 5. the fill minute reaching the stop is a loss
r = run([(100.5, 100.8, 98.9, 99.5)], order()).iloc[0]
check("fill minute reaches stop: loss", r.exit_reason == "stop" and r.r_net < -1)

# 6. a target touched in the fill minute does not count; the next minute's does
r = run([(100.5, 103.5, 99.9, 101.0), (101.0, 103.5, 100.8, 103.2)], order()).iloc[0]
check("target in the fill minute ignored", r.exit_reason == "target" and r.end == T0 + pd.Timedelta("2min"),
      f"(end {r.end})")

# 7. price reaching the target before the fill cancels the order
r = run([(100.5, 103.0, 100.2, 102.5), (100.5, 100.8, 99.5, 100.0)], order()).iloc[0]
check("target before fill cancels", r.status == "cancelled", f"({r.status})")

# 8. a gap through the stop exits at the open, not at the stop
r = run([(100.5, 100.8, 99.9, 100.2), (98.0, 98.5, 97.5, 98.2)], order()).iloc[0]
check("gap through stop exits at the open", r.exit_reason == "stop" and r.exit_price == 98.0)

# 9. an order expires at its expiry minute, exclusive
r = run([FLAT] * 5 + [(100.5, 100.8, 99.9, 100.2)], order(life=5)).iloc[0]
check("no fill at or after expiry", r.status == "expired")
r = run([FLAT] * 4 + [(100.5, 100.8, 99.9, 100.2)], order(life=5)).iloc[0]
check("fill in the last live minute", r.status == "filled")

# 10. one at a time: an order known while a position is open is skipped
bars = [(100.5, 100.8, 99.9, 100.2)] + [FLAT] * 5 + [(102.0, 103.5, 101.9, 103.2)] + [FLAT] * 3
res = run(bars, order(at=0), order(at=3), order(at=7, target=100.7, stop=99.5))
check("busy while a position is open, free once it closes",
      list(res.status) == ["filled", "busy", "cancelled"], f"({list(res.status)})")

# 11. shorts mirror longs
r = run([(99.5, 100.1, 99.2, 99.8), (98.0, 98.1, 96.5, 96.8)], order(-1, 100, 101, 97)).iloc[0]
check("short: fill then target", (r.exit_reason, r.exit_price) == ("target", 97.0)
      and np.isclose(r.r_gross, 3.0))
r = run([(99.5, 100.1, 99.2, 99.8), (100.5, 101.2, 100.4, 101.1)], order(-1, 100, 101, 97)).iloc[0]
check("short: stop above, slippage up",
      r.exit_reason == "stop" and np.isclose(r.exit_price, 101 * 1.0002))

# 12. a position still open when the data ends is closed at the last close
r = run([(100.5, 100.8, 99.9, 100.2)], order(), pad=3).iloc[0]
check("open at the end of data: closed at last close", r.exit_reason == "end")

# 13. opposing-liquidity target: nearest pool still active, far enough, same segment
P = tr.Prepared(ltf=None, setups=None, seg=np.zeros(30, dtype=int), pools={
    "high": (np.array([5, 10, 15, 20]), np.array([104.0, 101.0, 106.0, 110.0]),
             np.array([10**9, 10**9, 18, 10**9]), np.zeros(4, dtype=int)),
    "low": (np.array([6, 12]), np.array([95.0, 97.0]), np.array([10**9, 14]), np.array([0, 0]))})
check("nearest active pool beyond 2R", tr._liquidity_target(P, 19, 1, 103.0) == 104.0)
check("a pool already traded through is skipped", tr._liquidity_target(P, 19, 1, 105.0) != 106.0)
check("a pool active at the time is used", tr._liquidity_target(P, 17, 1, 105.0) == 106.0)
check("a pool not yet known is not used", np.isnan(tr._liquidity_target(P, 19, 1, 107.0)))
check("short side uses lows", tr._liquidity_target(P, 13, -1, 98.0) == 97.0
      and tr._liquidity_target(P, 15, -1, 98.0) == 95.0)
P.seg[19] = 1
check("pools from before a gap are not used", np.isnan(tr._liquidity_target(P, 19, 1, 103.0)))

# 14. Silver Bullet hours follow New York time through daylight saving
t = pd.DatetimeIndex(["2024-07-01 14:00", "2024-01-15 15:00", "2024-01-15 14:00",
                      "2024-07-01 07:55", "2024-07-01 08:00", "2024-01-15 19:30"])
check("Silver Bullet windows, DST-aware",
      list(tr.in_silver_bullet(t)) == [True, True, False, True, False, True])

# 15. plan: stop beyond the sweep extreme, entry at the proximal edge or midpoint, targets
ltf = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
                   index=pd.date_range("2024-01-01", periods=50, freq="5min"))
setup = pd.DataFrame([{"known": ltf.index[20] + pd.Timedelta("5min"), "direction": 1,
                       "known_pos": 20, "fvg_pos": 20, "sweep_extreme": 97.0, "fvg_top": 100.0,
                       "fvg_bottom": 99.0, "atr": 2.0}])
P2 = tr.Prepared(ltf=ltf, setups=setup, seg=np.zeros(50, dtype=int), pools=P.pools)
o = tr.plan(P2, tr.Variant("5min", "1h", "3r", "proximal", "all")).iloc[0]
check("stop is 0.1 ATR beyond the sweep extreme", np.isclose(o.stop, 96.8))
check("proximal entry and 3R target",
      o.entry == 100.0 and np.isclose(o.risk, 3.2) and np.isclose(o.target, 109.6))
o = tr.plan(P2, tr.Variant("5min", "1h", "3r", "mid", "all")).iloc[0]
check("midpoint entry", o.entry == 99.5)
check("expiry 24 entry bars after the setup", o.expires == setup.known[0] + pd.Timedelta("120min"))
o = tr.plan(P2, tr.Variant("5min", "1h", "liquidity", "proximal", "all"))
check("liquidity target: nearest active pool beyond 2R (106.4)", len(o) == 1 and o.target[0] == 110.0)
P2.pools = {"high": tuple(a[:3] for a in P.pools["high"]), "low": P.pools["low"]}
check("no liquidity 2R away: no order",
      tr.plan(P2, tr.Variant("5min", "1h", "liquidity", "proximal", "all")).empty)

# 16. on a driftless random walk: no free lunch, costs bite, the control agrees
rng = np.random.default_rng(11)
n = 400_000
logp = np.log(30_000) + np.cumsum(rng.normal(0, 0.0005, n))
close = np.exp(logp)
op = np.r_[close[0], close[:-1]]
noise = np.abs(rng.normal(0, 0.0002, (2, n)))
m1 = pd.DataFrame({"open": op, "high": np.maximum(op, close) * (1 + noise[0]),
                   "low": np.minimum(op, close) * (1 - noise[1]), "close": close, "volume": 1.0},
                  index=pd.date_range("2021-01-01", periods=n, freq="min"))
prep = tr.prepare(m1, "5min", "1h")
v = tr.Variant("5min", "1h", "3r", "proximal", "all")
res = tr.simulate(tr.plan(prep, v), m1)
f = res[res.status == "filled"]
se = f.r_gross.std() / np.sqrt(len(f))
check("random walk gives enough trades to test", len(f) >= 100, f"({len(f)})")
check("no edge before costs on a driftless walk", abs(f.r_gross.mean()) < 3 * se,
      f"(mean {f.r_gross.mean():+.3f}R, se {se:.3f})")
check("costs are charged exactly", np.allclose(f.r_gross - f.r_net,
                                               0.001 * (f.entry + f.exit_price) / f.risk))
check("after costs it loses", f.r_net.mean() + 3 * se < 0, f"(mean {f.r_net.mean():+.3f}R)")
ctrl = tr.control(res, m1, seeds=20)
check("the random-entry control matches it", abs(f.r_net.mean() - ctrl.mean()) < 3 * se,
      f"(strategy {f.r_net.mean():+.3f}R, control {ctrl.mean():+.3f}R)")

print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
