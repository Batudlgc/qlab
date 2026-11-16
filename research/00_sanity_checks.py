"""Sanity checks on the engine itself. Run this before trusting any result.

If these fail, every downstream number is meaningless.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from qlab import backtest, validation

rng = np.random.default_rng(42)
idx = pd.bdate_range("2015-01-01", "2025-01-01")
cols = [f"A{i}" for i in range(10)]
rets = pd.DataFrame(rng.normal(0.0003, 0.015, (len(idx), len(cols))), index=idx, columns=cols)
px = (1 + rets).cumprod() * 100

fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


# 1. Random signal on random data -> Sharpe indistinguishable from zero
w = pd.DataFrame(rng.normal(size=px.shape), index=px.index, columns=px.columns)
w = w.sub(w.mean(axis=1), axis=0)
w = w.div(w.abs().sum(axis=1), axis=0)
r = backtest.run(w, px, costs=backtest.Costs(0, 0, 0))
s = r.stats()["sharpe"]
check("random signal ~ zero Sharpe", abs(s) < 0.5, f"(sharpe={s:.3f})")

# 2. Perfect foresight -> enormous Sharpe. If NOT huge, the shift is broken.
fut = px.pct_change(fill_method=None).shift(-1)
wf = np.sign(fut).div(np.sign(fut).abs().sum(axis=1), axis=0).fillna(0.0)
rf = backtest.run(wf, px, costs=backtest.Costs(0, 0, 0))
sf = rf.stats()["sharpe"]
check("perfect foresight -> huge Sharpe", sf > 10, f"(sharpe={sf:.1f})")

# 3. Lookahead trap: using TODAY's return as the signal must NOT be profitable,
#    because the engine holds it only from tomorrow.
today = px.pct_change(fill_method=None)
wt = np.sign(today).div(np.sign(today).abs().sum(axis=1), axis=0).fillna(0.0)
rt = backtest.run(wt, px, costs=backtest.Costs(0, 0, 0))
st = rt.stats()["sharpe"]
check("no free lunch from same-bar signal", abs(st) < 1.0, f"(sharpe={st:.3f})")

# 4. Costs must reduce returns monotonically
cheap = backtest.run(w, px, costs=backtest.Costs(0, 0, 0)).stats()["cagr"]
dear = backtest.run(w, px, costs=backtest.Costs(5, 10, 5)).stats()["cagr"]
check("higher costs -> lower CAGR", dear < cheap, f"({dear:.4f} < {cheap:.4f})")

# 5. Walk-forward splits must not overlap and must respect the embargo
sp = validation.walk_forward(px.index, train_years=3, test_years=1, embargo_days=10)
gap_ok = all((s.test[0] - s.train[-1]).days >= 10 for s in sp)
no_leak = all(s.train.intersection(s.test).empty for s in sp)
check("walk-forward embargo respected", gap_ok, f"({len(sp)} folds)")
check("train/test disjoint", no_leak)

# 6. Deflated Sharpe must fall as trial count rises
d1 = validation.deflated_sharpe(rf.returns, n_trials=1)
d100 = validation.deflated_sharpe(rf.returns, n_trials=100)
check("deflated Sharpe penalises trials", d100 <= d1, f"({d100:.4f} <= {d1:.4f})")

# 7. With the default trial dispersion, the test must be able to say yes and no.
#    A strong, steady edge over ten years survives 20 trials; pure noise does not
#    survive 50. A default that sets the bar from the strategy's own Sharpe fails the
#    first of these from 4 trials up, because the bar then always sits above it.
days = pd.bdate_range("2010-01-01", periods=2500)
edge = pd.Series(rng.normal(0.0008, 0.008, len(days)), index=days)   # Sharpe ~1.6
noise = pd.Series(rng.normal(0.0, 0.010, len(days)), index=days)
de = validation.deflated_sharpe(edge, n_trials=20)
dn = validation.deflated_sharpe(noise, n_trials=50)
check("default DSR: real edge survives 20 trials", de > 0.95, f"(dsr={de:.4f})")
check("default DSR: noise fails 50 trials", dn < 0.5, f"(dsr={dn:.4f})")
#    Check 6 saturates at 1.0 on perfect foresight; repeat it where the value can move.
mid = pd.Series(rng.normal(0.0003, 0.010, len(days)), index=days)     # Sharpe ~0.5
m1, m100 = validation.deflated_sharpe(mid, n_trials=1), validation.deflated_sharpe(mid, n_trials=100)
check("default DSR: strictly lower with more trials", m100 < m1, f"({m100:.4f} < {m1:.4f})")

print("\n" + ("ALL CHECKS PASSED" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
