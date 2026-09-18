"""Point-in-time universe construction.

A universe of "companies that are in the index today" is not a universe you
could have traded in 2020. Names that were dropped - because they were acquired,
shrank, or failed - are missing, and they are not missing at random. They are
missing precisely because something bad happened to them.

This module supplies the removal record needed to build a membership series that
respects what was knowable at each date.

KNOWN LIMITATION, quantified in reports/note_06_survivorship.md: of 105 S&P 500
removals recorded between April 2020 and May 2026, only 57 (54.3%) still return
price history from the free data source. The 48 that do not are disproportionately
acquisitions and failures - SIVB, SBNY, FRC, TWTR, ATVI, XLNX, PXD, RTN. The data
source loses exactly the observations that cause the bias. Corrections built on
it are therefore lower bounds, never full fixes.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent / "universes"


def removals(with_data_only: bool = True) -> pd.DataFrame:
    """S&P 500 removals, April 2020 - May 2026. Columns: ticker, removal_date.

    with_data_only=True returns the 57 for which price history is retrievable.
    """
    f = "removed_with_data.csv" if with_data_only else "sp500_removals.csv"
    df = pd.read_csv(DATA / f, parse_dates=["removal_date"])
    return df[["ticker", "removal_date"]].sort_values("removal_date")


def membership_mask(index: pd.DatetimeIndex, columns: list[str],
                    removal_dates: dict[str, pd.Timestamp] | None = None,
                    added_dates: dict[str, pd.Timestamp] | None = None) -> pd.DataFrame:
    """Boolean frame: True where a name was an index member on that date.

    Multiply weights by this before backtesting to enforce point-in-time membership.
    """
    mask = pd.DataFrame(True, index=index, columns=columns)
    for t, d in (removal_dates or {}).items():
        if t in mask.columns:
            mask.loc[mask.index > pd.Timestamp(d), t] = False
    for t, d in (added_dates or {}).items():
        if t in mask.columns:
            mask.loc[mask.index < pd.Timestamp(d), t] = False
    return mask


def apply_membership(weights: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    """Zero out weights in names that were not index members at that time."""
    return weights.where(mask.reindex_like(weights).fillna(False), 0.0)
