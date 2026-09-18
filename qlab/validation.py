"""Validation: the part that stops you fooling yourself.

Three defences, all mandatory:
  1. Purged + embargoed walk-forward splits (no lookahead via overlapping labels)
  2. A locked holdout you are allowed to touch ONCE
  3. Deflated Sharpe ratio - corrects the Sharpe for how many strategies you tried

Reference for (1) and (3): Bailey & Lopez de Prado, "The Deflated Sharpe Ratio" (2014)
and Lopez de Prado, "Advances in Financial Machine Learning" (2018), ch. 7.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class Split:
    train: pd.DatetimeIndex
    test: pd.DatetimeIndex

    def __repr__(self) -> str:
        return (f"Split(train={self.train[0].date()}..{self.train[-1].date()} n={len(self.train)}, "
                f"test={self.test[0].date()}..{self.test[-1].date()} n={len(self.test)})")


def walk_forward(index: pd.DatetimeIndex, train_years: float = 4.0,
                 test_years: float = 1.0, embargo_days: int = 10,
                 anchored: bool = False) -> list[Split]:
    """Rolling (or anchored) walk-forward splits with an embargo gap.

    The embargo drops `embargo_days` bars between train and test so that
    autocorrelated features / overlapping labels cannot leak across the boundary.
    """
    index = pd.DatetimeIndex(index).sort_values()
    tr = int(round(train_years * 252))
    te = int(round(test_years * 252))
    if tr + embargo_days + te > len(index):
        raise ValueError(f"index too short: need {tr + embargo_days + te}, have {len(index)}")

    splits, start = [], 0
    while True:
        tr_end = start + tr
        te_start = tr_end + embargo_days
        te_end = te_start + te
        if te_end > len(index):
            break
        train = index[0:tr_end] if anchored else index[start:tr_end]
        splits.append(Split(train=train, test=index[te_start:te_end]))
        start += te
    return splits


def lock_holdout(index: pd.DatetimeIndex, frac: float = 0.2) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Split off a final out-of-sample block. Do not look at it until the very end.

    Returns (research_index, holdout_index).
    """
    index = pd.DatetimeIndex(index).sort_values()
    cut = int(len(index) * (1 - frac))
    return index[:cut], index[cut:]


def sharpe(returns: pd.Series, periods: int = 252) -> float:
    r = pd.Series(returns).dropna()
    if len(r) < 2 or r.std(ddof=1) == 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=1) * np.sqrt(periods))


def probabilistic_sharpe(returns: pd.Series, benchmark_sr: float = 0.0,
                         periods: int = 252) -> float:
    """P(true Sharpe > benchmark), adjusting for skew and kurtosis of returns.

    Non-normal returns inflate the naive Sharpe's reliability; this corrects it.
    """
    r = pd.Series(returns).dropna()
    n = len(r)
    if n < 3:
        return float("nan")
    sr = sharpe(r, periods) / np.sqrt(periods)          # per-period Sharpe
    b = benchmark_sr / np.sqrt(periods)
    g3 = float(stats.skew(r, bias=False))
    g4 = float(stats.kurtosis(r, fisher=False, bias=False))
    denom = np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    if not np.isfinite(denom) or denom <= 0:
        return float("nan")
    return float(stats.norm.cdf((sr - b) * np.sqrt(n - 1) / denom))


def deflated_sharpe(returns: pd.Series, n_trials: int,
                    trial_sr_std: float | None = None, periods: int = 252) -> float:
    """Probability the observed Sharpe is real given you tested `n_trials` strategies.

    This is the number that separates a research process from curve fitting.
    Report it, and report `n_trials` honestly - see research_log.py.
    """
    r = pd.Series(returns).dropna()
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    if trial_sr_std is None:
        trial_sr_std = abs(sharpe(r, periods)) / np.sqrt(periods) or 0.01
    euler = 0.5772156649015329
    if n_trials == 1:
        sr0 = 0.0
    else:
        sr0 = trial_sr_std * (
            (1 - euler) * stats.norm.ppf(1 - 1 / n_trials)
            + euler * stats.norm.ppf(1 - 1 / (n_trials * np.e))
        )
    return probabilistic_sharpe(r, benchmark_sr=sr0 * np.sqrt(periods), periods=periods)
