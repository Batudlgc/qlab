"""Binance spot 1-minute klines: download, verify, load, resample.

    python3 -m qlab.smc.data download          # development months for BTCUSDT and ETHUSDT

Source: the public archive at data.binance.vision, one zip per symbol and month, each with
a SHA-256 .CHECKSUM file beside it. Every zip is verified before it is kept.

The holdout (reports/smc_preregistration.md) is not on disk until it is asked for. Months
after DEV_END are refused unless holdout=True, and load() never mixes the two periods, so
nothing written during development can read the holdout by accident.

Frame: index 'date' = bar open time, UTC, tz-naive; cols open, high, low, close, volume.
Binance switched spot timestamps from milliseconds to microseconds on 1 Jan 2025; both
are read.
"""
from __future__ import annotations

import hashlib
import io
import logging
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

import pandas as pd

log = logging.getLogger(__name__)

ARCHIVE = "https://data.binance.vision/data/spot/monthly/klines"
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "binance"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
COLUMNS = ["open", "high", "low", "close", "volume"]
RAW_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
               "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]

FIRST_MONTH = "2017-08"
DEV_END = pd.Timestamp("2025-04-30 23:59")      # last development minute
HOLDOUT_START = pd.Timestamp("2025-05-08")      # after a one-week embargo
HOLDOUT_END = pd.Timestamp("2026-10-31 23:59")
MIN_COVERAGE = 0.8                              # a bar needs 80% of its minutes


def months(first: str, last: str) -> list[str]:
    """Every 'YYYY-MM' from first to last, inclusive."""
    return [p.strftime("%Y-%m") for p in pd.period_range(first, last, freq="M")]


def dev_months() -> list[str]:
    return months(FIRST_MONTH, DEV_END.strftime("%Y-%m"))


def holdout_months() -> list[str]:
    return months(HOLDOUT_START.strftime("%Y-%m"), HOLDOUT_END.strftime("%Y-%m"))


def _guard(month: str, holdout: bool) -> None:
    if month > DEV_END.strftime("%Y-%m") and not holdout:
        raise PermissionError(f"{month} is after the development period; "
                              "pass holdout=True only once a variant has been chosen and committed")


# ---------------------------------------------------------------- download

def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "qlab"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def verify(blob: bytes, checksum_file: str) -> None:
    """Raise unless blob matches the SHA-256 in a Binance .CHECKSUM file."""
    expected = checksum_file.split()[0].lower()
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise ValueError(f"checksum mismatch: expected {expected}, got {actual}")


def raw_path(symbol: str, month: str) -> Path:
    return CACHE / "raw" / symbol / f"{symbol}-1m-{month}.zip"


def download(symbol: str, month_list: list[str], holdout: bool = False,
             fetch: Callable[[str], bytes] = _http_get) -> int:
    """Fetch and verify any month not already on disk. Returns the number fetched."""
    for m in month_list:
        _guard(m, holdout)
    n = 0
    for m in month_list:
        path = raw_path(symbol, m)
        if path.exists():
            continue
        url = f"{ARCHIVE}/{symbol}/1m/{path.name}"
        blob = fetch(url)
        verify(blob, fetch(url + ".CHECKSUM").decode())
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(blob)
        tmp.rename(path)
        n += 1
        log.info("fetched %s %s (%d bytes)", symbol, m, len(blob))
    return n


# ---------------------------------------------------------------- parse and load

def parse(blob: bytes, month: str) -> pd.DataFrame:
    """One monthly zip as the canonical frame. Raises if any row falls outside its month."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        (name,) = z.namelist()
        raw = pd.read_csv(z.open(name), header=None, names=RAW_COLUMNS, dtype=str)
    if not raw.empty and not raw.iloc[0, 0].strip().isdigit():
        raw = raw.iloc[1:]                      # a header row, if a file ever has one
    t = raw["open_time"].astype("int64")
    unit = "us" if t.max() > 10**14 else "ms"
    df = raw[COLUMNS].astype("float64")
    df.index = pd.to_datetime(t.to_numpy(), unit=unit)
    df.index.name = "date"
    df = df[~df.index.duplicated(keep="last")].sort_index()

    start = pd.Timestamp(month + "-01")
    outside = (df.index < start) | (df.index >= start + pd.offsets.MonthBegin(1))
    if outside.any():
        raise ValueError(f"{month}: {outside.sum()} rows outside the month")
    if (df.index != df.index.floor("min")).any():
        raise ValueError(f"{month}: timestamps not on minute boundaries")
    return df


def frame_path(symbol: str, holdout: bool) -> Path:
    return CACHE / f"{symbol}-1m-{'holdout' if holdout else 'dev'}.parquet"


def build(symbol: str, holdout: bool = False) -> pd.DataFrame:
    """Parse every downloaded month of one period into a single parquet file."""
    month_list = holdout_months() if holdout else dev_months()
    for m in month_list:
        _guard(m, holdout)
    missing = [m for m in month_list if not raw_path(symbol, m).exists()]
    if missing:
        raise FileNotFoundError(f"{symbol}: {len(missing)} months not downloaded, "
                                f"first {missing[0]}; run download() first")
    df = pd.concat([parse(raw_path(symbol, m).read_bytes(), m) for m in month_list])
    lo, hi = (HOLDOUT_START, HOLDOUT_END) if holdout else (df.index[0], DEV_END)
    df = df[(df.index >= lo) & (df.index <= hi)]
    df.to_parquet(frame_path(symbol, holdout))
    return df


def load(symbol: str, start: str | None = None, end: str | None = None,
         holdout: bool = False) -> pd.DataFrame:
    """1-minute bars for one period. Development by default; the holdout only on request."""
    if not holdout and end is not None and pd.Timestamp(end) > DEV_END:
        raise PermissionError(f"end={end} is after the development period")
    path = frame_path(symbol, holdout)
    if not path.exists():
        raise FileNotFoundError(f"{path.name} not built; run build('{symbol}')")
    df = pd.read_parquet(path)
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]
    return df


# ---------------------------------------------------------------- resample

def resample(df: pd.DataFrame, rule: str,
             min_coverage: float = MIN_COVERAGE) -> tuple[pd.DataFrame, int]:
    """1-minute bars to `rule` bars ('5min', '15min', '1h', '4h'), labelled by open time.

    A bar built from fewer than min_coverage of its minutes is dropped rather than
    trusted. Returns (bars, number of bars dropped), counting bars with no minutes at all.
    """
    expected = pd.Timedelta(rule) / pd.Timedelta("1min")
    g = df.resample(rule, label="left", closed="left")
    bars = g.agg({"open": "first", "high": "max", "low": "min",
                  "close": "last", "volume": "sum"})
    keep = g["close"].count() >= min_coverage * expected
    return bars[keep], int((~keep).sum())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if sys.argv[1:] != ["download"]:
        sys.exit("usage: python3 -m qlab.smc.data download")
    for s in SYMBOLS:
        n = download(s, dev_months())
        df = build(s)
        print(f"{s}: fetched {n} months, {len(df):,} minutes "
              f"{df.index[0]} .. {df.index[-1]} -> {frame_path(s, False).name}")
