"""Data-quality report for the downloaded development period. Reads no holdout data.

    python3 -m qlab.smc.data download     # first
    python3 research/12_smc_data_quality.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from qlab.smc import data

TIMEFRAMES = ["5min", "15min", "1h", "4h"]


def report(symbol: str) -> bool:
    df = data.load(symbol)
    full = pd.date_range(df.index[0], df.index[-1], freq="min")
    missing = full.difference(df.index)
    print(f"\n== {symbol}: {df.index[0]} .. {df.index[-1]}")
    print(f"minutes {len(df):,} of {len(full):,} expected; missing {len(missing):,} "
          f"({len(missing) / len(full):.3%})")

    # longest gaps: runs of consecutive missing minutes
    if len(missing):
        s = pd.Series(missing)
        run = (s.diff() != pd.Timedelta("1min")).cumsum()
        gaps = s.groupby(run).agg(["first", "count"]).sort_values("count", ascending=False)
        for _, g in gaps.head(5).iterrows():
            print(f"  gap of {g['count']:>5,} min from {g['first']}")

    by_year = df.groupby(df.index.year).size()
    exp_year = pd.Series(full.year).value_counts().sort_index()
    print("coverage by year: " + ", ".join(f"{y} {by_year[y] / exp_year[y]:.2%}" for y in by_year.index))

    ok = True
    bad_ohlc = ((df.high < df[["open", "close"]].max(axis=1)) |
                (df.low > df[["open", "close"]].min(axis=1)) | (df[data.COLUMNS[:4]] <= 0).any(axis=1))
    print(f"inconsistent OHLC rows: {bad_ohlc.sum()}")
    ok &= bad_ohlc.sum() == 0
    after = (df.index > data.DEV_END).sum()
    print(f"rows after the development period: {after}")
    ok &= after == 0

    # only across consecutive minutes: the first bar after a gap is not a 1-minute move
    consecutive = df.index.to_series().diff() == pd.Timedelta("1min")
    r = df.close.pct_change().abs()[consecutive]
    big = r[r > 0.05].sort_values(ascending=False)
    print(f"1-minute moves above 5%: {len(big)}" +
          "".join(f"\n  {t}  {v:.1%}" for t, v in big.head(5).items()))

    for tf in TIMEFRAMES:
        bars, dropped = data.resample(df, tf)
        print(f"{tf:>5}: {len(bars):,} bars, {dropped:,} dropped ({dropped / (len(bars) + dropped):.3%})")
    return ok


if __name__ == "__main__":
    ok = all([report(s) for s in data.SYMBOLS])
    print("\n" + ("DATA CHECKS PASSED" if ok else "DATA CHECKS FAILED"))
    sys.exit(0 if ok else 1)
