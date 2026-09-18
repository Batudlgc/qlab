"""Baseline: cross-sectional 12-1 momentum on liquid US large caps.

This is NOT an edge - it is a control. Every future strategy must beat this
net of costs, out of sample, or it is not worth trading.

Run:  python3 research/01_momentum_baseline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from qlab import backtest, data, research_log, signals, validation

UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA",
            "JPM", "V", "UNH", "XOM", "JNJ", "PG", "HD", "COST",
            "MRK", "ABBV", "PEP", "KO", "WMT", "CVX", "ADBE", "CRM"]

START, END = "2012-01-01", "2026-07-31"
LOOKBACK, SKIP, TOP_N = 252, 21, 5


def rebalance_monthly(w: pd.DataFrame) -> pd.DataFrame:
    """Hold weights constant between the last trading day of each month."""
    rebal_days = w.groupby([w.index.year, w.index.month]).apply(
        lambda g: g.index[-1]).values
    mask = pd.Series(w.index.isin(rebal_days), index=w.index)
    return w.where(mask, other=pd.NA).ffill().fillna(0.0).astype(float)


def main() -> None:
    px = data.panel(UNIVERSE, start=START, end=END)
    px = px.dropna(axis=1, thresh=int(len(px) * 0.9)).ffill().dropna()
    print(f"universe={px.shape[1]} names  bars={len(px)}  "
          f"{px.index[0].date()} -> {px.index[-1].date()}")

    research_idx, holdout_idx = validation.lock_holdout(px.index, frac=0.2)
    print(f"research: {research_idx[0].date()}..{research_idx[-1].date()}  "
          f"HOLDOUT (locked): {holdout_idx[0].date()}..{holdout_idx[-1].date()}")

    px_r = px.loc[research_idx]
    score = signals.momentum(px_r, lookback=LOOKBACK, skip=SKIP)
    w = signals.to_weights(score, long_only=False, top_n=TOP_N, gross=1.0)

    # monthly rebalance - daily rebalancing on a 12-month signal is pure cost
    w = rebalance_monthly(w)

    res = backtest.run(w, px_r, costs=backtest.Costs())
    st = res.stats()

    print("\n--- in-sample / research window (net of costs) ---")
    for k, v in st.items():
        print(f"{k:>18}: {v:,.4f}" if isinstance(v, float) else f"{k:>18}: {v}")

    print("\n--- walk-forward, out-of-sample only ---")
    splits = validation.walk_forward(px_r.index, train_years=4, test_years=1, embargo_days=10)
    oos = pd.concat([res.returns.loc[s.test] for s in splits]).sort_index()
    oos = oos[~oos.index.duplicated()]
    print(f"folds={len(splits)}  oos_days={len(oos)}")
    print(f"{'oos_sharpe':>18}: {validation.sharpe(oos):,.4f}")
    print(f"{'psr(vs 0)':>18}: {validation.probabilistic_sharpe(oos):,.4f}")

    n = max(research_log.n_trials(), 1)
    print(f"{'n_trials_logged':>18}: {n}")
    print(f"{'deflated_sharpe':>18}: {validation.deflated_sharpe(oos, n_trials=n):,.4f}")

    research_log.record(
        name="momentum_12_1_xs",
        params={"lookback": LOOKBACK, "skip": SKIP, "top_n": TOP_N,
                "rebalance": "monthly", "universe": len(px_r.columns)},
        stats={**st, "oos_sharpe": validation.sharpe(oos)},
        notes="baseline control; holdout untouched",
    )
    print("\nlogged to reports/research_log.jsonl")
    print("HOLDOUT NOT EVALUATED - by design.")


if __name__ == "__main__":
    main()
