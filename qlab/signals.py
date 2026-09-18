"""Signal library. Every function returns a cross-sectional score, higher = more attractive.

Rules:
  - a signal at row t may only use data available at t (use .shift() where in doubt)
  - signals are unitless scores, not weights; conversion happens in to_weights()
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def zscore(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score, row by row."""
    mu = df.mean(axis=1)
    sd = df.std(axis=1, ddof=1).replace(0, np.nan)
    return df.sub(mu, axis=0).div(sd, axis=0)


def momentum(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """Classic 12-1 momentum: total return over `lookback`, skipping the last `skip` days.

    The skip removes short-term reversal contamination.
    """
    return prices.shift(skip) / prices.shift(skip + lookback) - 1


def reversal(prices: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """Short-term reversal: recent losers score high."""
    return -(prices / prices.shift(lookback) - 1)


def volatility(prices: pd.DataFrame, lookback: int = 63) -> pd.DataFrame:
    """Realised vol. Returned as-is (low-vol anomaly means you usually invert it)."""
    return prices.pct_change(fill_method=None).rolling(lookback).std(ddof=1) * np.sqrt(252)


def to_weights(score: pd.DataFrame, long_only: bool = False,
               top_n: int | None = None, gross: float = 1.0) -> pd.DataFrame:
    """Convert scores to portfolio weights.

    long_only=False -> dollar-neutral long/short, gross exposure = `gross`
    top_n           -> keep only the top (and bottom) N names per row
    """
    s = zscore(score)
    if top_n:
        ranks = s.rank(axis=1, ascending=False)
        n_valid = s.notna().sum(axis=1)
        keep_top = ranks.le(top_n, axis=0)
        keep_bot = ranks.gt(n_valid - top_n, axis=0)
        s = s.where(keep_top | keep_bot if not long_only else keep_top)
    s = s.fillna(0.0)
    if long_only:
        s = s.clip(lower=0)
    else:
        s = s.sub(s.mean(axis=1), axis=0)   # enforce dollar neutrality
    norm = s.abs().sum(axis=1).replace(0, np.nan)
    return s.div(norm, axis=0).fillna(0.0) * gross
