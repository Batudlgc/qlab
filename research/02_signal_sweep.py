"""Multiple-testing demonstration: what happens when you search a parameter grid.

This script exists to make one point precisely: the best Sharpe out of N trials
is a biased estimate. It runs a grid, logs every trial, then shows how much of
the winner's apparent edge survives a multiple-testing correction.

The honest output of this script is usually "nothing survives". That is the point.

Run:  python3 research/02_signal_sweep.py
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from qlab import backtest, data, research_log, signals, validation

UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA",
            "JPM", "V", "UNH", "XOM", "JNJ", "PG", "HD", "COST",
            "MRK", "ABBV", "PEP", "KO", "WMT", "CVX", "ADBE", "CRM"]
START, END = "2012-01-01", "2026-07-31"

GRID = {
    "family":   ["momentum", "reversal", "lowvol"],
    "lookback": [21, 63, 126, 252],
    "top_n":    [3, 5, 8],
    "rebal":    ["W", "ME"],
}


def rebalance(w: pd.DataFrame, freq: str) -> pd.DataFrame:
    key = [w.index.year, w.index.isocalendar().week] if freq == "W" else [w.index.year, w.index.month]
    days = w.groupby(key).apply(lambda g: g.index[-1]).values
    mask = pd.Series(w.index.isin(days), index=w.index)
    return w.where(mask, other=pd.NA).ffill().fillna(0.0).astype(float)


def build(family: str, px: pd.DataFrame, lookback: int) -> pd.DataFrame:
    if family == "momentum":
        return signals.momentum(px, lookback=lookback, skip=21)
    if family == "reversal":
        return signals.reversal(px, lookback=lookback)
    if family == "lowvol":
        return -signals.volatility(px, lookback=lookback)
    raise ValueError(family)


def main() -> None:
    px = data.panel(UNIVERSE, start=START, end=END)
    px = px.dropna(axis=1, thresh=int(len(px) * 0.9)).ffill().dropna()
    research_idx, holdout_idx = validation.lock_holdout(px.index, frac=0.2)
    px_r = px.loc[research_idx]
    print(f"research window {px_r.index[0].date()}..{px_r.index[-1].date()}  "
          f"{px_r.shape[1]} names")
    print(f"HOLDOUT reserved {holdout_idx[0].date()}..{holdout_idx[-1].date()} (untouched)\n")

    splits = validation.walk_forward(px_r.index, train_years=4, test_years=1, embargo_days=10)
    combos = list(itertools.product(*GRID.values()))
    print(f"testing {len(combos)} configurations across {len(splits)} walk-forward folds\n")

    rows = []
    for family, lookback, top_n, rebal in combos:
        if family == "momentum" and lookback < 63:
            continue  # 12-1 style momentum needs a meaningful window
        score = build(family, px_r, lookback)
        w = rebalance(signals.to_weights(score, top_n=top_n, gross=1.0), rebal)
        res = backtest.run(w, px_r, costs=backtest.Costs())

        oos = pd.concat([res.returns.loc[s.test] for s in splits]).sort_index()
        oos = oos[~oos.index.duplicated()]
        st = res.stats()
        sr_oos = validation.sharpe(oos)

        params = {"family": family, "lookback": lookback, "top_n": top_n, "rebal": rebal}
        research_log.record(f"sweep_{family}", params,
                            {**st, "oos_sharpe": sr_oos}, notes="grid sweep")
        rows.append({**params, "oos_sharpe": sr_oos, "is_sharpe": st["sharpe"],
                     "max_dd": st["max_dd"], "ann_turnover": st["ann_turnover"],
                     "cost_drag": st["cost_drag_ann"], "_oos": oos})

    df = pd.DataFrame(rows).sort_values("oos_sharpe", ascending=False)
    show = df.drop(columns=["_oos"])
    pd.set_option("display.width", 140)
    print("top 8 by out-of-sample Sharpe:")
    print(show.head(8).to_string(index=False, float_format=lambda x: f"{x:7.3f}"))
    print("\nbottom 3:")
    print(show.tail(3).to_string(index=False, float_format=lambda x: f"{x:7.3f}"))

    n_trials = len(df)
    best = df.iloc[0]
    trial_sr_std = df["oos_sharpe"].std(ddof=1) / np.sqrt(252)

    print(f"\n{'='*68}")
    print("MULTIPLE-TESTING CORRECTION")
    print(f"{'='*68}")
    print(f"{'configurations tested':>34}: {n_trials}")
    print(f"{'best OOS Sharpe (raw)':>34}: {best['oos_sharpe']:.3f}")
    print(f"{'median OOS Sharpe':>34}: {df['oos_sharpe'].median():.3f}")
    print(f"{'std of Sharpe across trials':>34}: {df['oos_sharpe'].std(ddof=1):.3f}")

    psr = validation.probabilistic_sharpe(best["_oos"])
    dsr = validation.deflated_sharpe(best["_oos"], n_trials=n_trials,
                                     trial_sr_std=trial_sr_std)
    print(f"{'PSR of best (ignores search)':>34}: {psr:.3f}")
    print(f"{'DSR of best (accounts for search)':>34}: {dsr:.3f}")

    verdict = ("SURVIVES - worth taking to the holdout" if dsr > 0.95
               else "DOES NOT SURVIVE - this is selection bias, not an edge")
    print(f"\nVERDICT: {verdict}")
    print("\nHoldout still untouched.")


if __name__ == "__main__":
    main()
