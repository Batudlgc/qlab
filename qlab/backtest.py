"""Vectorised backtester with mandatory, non-optional transaction costs.

Conventions that prevent lookahead:
  - `weights` at row t are the positions you INTEND to hold over t+1
  - the engine shifts them by one bar before applying returns
  - costs are charged on the turnover that happens at the open of t+1
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .validation import sharpe


@dataclass
class Costs:
    """Round-trip cost model. Defaults are deliberately pessimistic."""
    commission_bps: float = 1.0    # broker fee per side, in bps of notional
    spread_bps: float = 2.0        # half-spread paid per side
    slippage_bps: float = 1.0      # market impact per side

    @property
    def per_side_bps(self) -> float:
        return self.commission_bps + self.spread_bps + self.slippage_bps


@dataclass
class Result:
    returns: pd.Series
    gross_returns: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    costs_paid: pd.Series
    meta: dict = field(default_factory=dict)

    @property
    def equity(self) -> pd.Series:
        return (1 + self.returns).cumprod()

    def stats(self, periods: int = 252) -> dict:
        r = self.returns.dropna()
        if r.empty:
            return {}
        eq = (1 + r).cumprod()
        dd = eq / eq.cummax() - 1
        years = len(r) / periods
        cagr = eq.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan
        downside = r[r < 0].std(ddof=1)
        return {
            "cagr": float(cagr),
            "vol": float(r.std(ddof=1) * np.sqrt(periods)),
            "sharpe": sharpe(r, periods),
            "sharpe_gross": sharpe(self.gross_returns.dropna(), periods),
            "sortino": float(r.mean() / downside * np.sqrt(periods)) if downside else np.nan,
            "max_dd": float(dd.min()),
            "calmar": float(cagr / abs(dd.min())) if dd.min() < 0 else np.nan,
            "hit_rate": float((r > 0).mean()),
            "ann_turnover": float(self.turnover.mean() * periods),
            "cost_drag_ann": float(self.costs_paid.mean() * periods),
            "n_days": int(len(r)),
        }


def run(weights: pd.DataFrame, prices: pd.DataFrame,
        costs: Costs | None = None, max_gross: float = 1.0) -> Result:
    """Backtest a weight matrix against a price panel.

    weights : rows=dates, cols=symbols. Intended holdings, decided using data up to t.
    prices  : same shape/index. Close prices.
    """
    costs = costs or Costs()
    prices = prices.reindex(columns=weights.columns).sort_index()
    weights = weights.reindex(prices.index).fillna(0.0)

    gross = weights.abs().sum(axis=1)
    scale = np.where(gross > max_gross, max_gross / gross.replace(0, np.nan), 1.0)
    weights = weights.mul(pd.Series(scale, index=weights.index).fillna(1.0), axis=0)

    asset_rets = prices.pct_change(fill_method=None).fillna(0.0)

    # decide at t, hold over t+1  ->  shift
    held = weights.shift(1).fillna(0.0)
    gross_ret = (held * asset_rets).sum(axis=1)

    turnover = (held - held.shift(1).fillna(0.0)).abs().sum(axis=1)
    cost_series = turnover * (costs.per_side_bps / 10_000.0)
    net_ret = gross_ret - cost_series

    return Result(
        returns=net_ret, gross_returns=gross_ret, weights=held,
        turnover=turnover, costs_paid=cost_series,
        meta={"costs_bps_per_side": costs.per_side_bps, "max_gross": max_gross},
    )
