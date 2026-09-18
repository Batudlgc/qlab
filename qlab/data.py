"""Data layer.

Two sources:
  1. yfinance  -> bulk historical research data (free, survivorship-biased, adjust with care)
  2. IBKR MCP  -> live / verification data, pulled by the agent and dropped into data/cache
                  as parquet with the canonical schema below.

Canonical schema (all sources normalise to this):
    index : DatetimeIndex, tz-naive, UTC-normalised, name='date'
    cols  : open, high, low, close, volume   (float64, float64, float64, float64, float64)

Never mix adjusted and unadjusted series in one backtest.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

COLUMNS = ["open", "high", "low", "close", "volume"]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    df = df[COLUMNS].astype("float64")
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def load(symbol: str, start: str = "2005-01-01", end: str | None = None,
         refresh: bool = False) -> pd.DataFrame:
    """Load daily bars for one symbol, cached to parquet."""
    path = CACHE / f"{symbol.upper()}.parquet"
    if path.exists() and not refresh:
        df = pd.read_parquet(path)
        return _slice(df, start, end)

    import yfinance as yf
    raw = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    if raw is None or raw.empty:
        raise RuntimeError(f"no data returned for {symbol}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = _normalise(raw)
    df.to_parquet(path)
    log.info("cached %s rows=%d -> %s", symbol, len(df), path)
    return _slice(df, start, end)


def _slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]
    return df


def panel(symbols: list[str], field: str = "close", **kw) -> pd.DataFrame:
    """Wide panel: rows=dates, cols=symbols, values=`field`."""
    frames = {}
    for s in symbols:
        try:
            frames[s.upper()] = load(s, **kw)[field]
        except Exception as exc:  # noqa: BLE001
            log.warning("skipping %s: %s", s, exc)
    if not frames:
        raise RuntimeError("no symbols loaded")
    return pd.DataFrame(frames).sort_index()


def from_ibkr_json(payload: dict, symbol: str, save: bool = True) -> pd.DataFrame:
    """Convert an IBKR MCP get_price_history payload into the canonical frame."""
    df = pd.DataFrame({
        "open": payload["open"], "high": payload["high"], "low": payload["low"],
        "close": payload["close"], "volume": payload["volume"],
    }, index=pd.to_datetime(payload["time"]))
    df = _normalise(df)
    if save:
        df.to_parquet(CACHE / f"{symbol.upper()}_ibkr.parquet")
    return df
