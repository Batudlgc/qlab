"""Correctness tests for the Binance data layer. Offline: every zip here is built in memory."""
import hashlib
import io
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from qlab.smc import data

fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    return False


def make_zip(month, unit="ms", header=False, minutes=None, drop=()):
    """A Binance-format monthly zip: one row per minute, close = minute number."""
    start = pd.Timestamp(month + "-01")
    idx = pd.date_range(start, periods=minutes or 60, freq="min")
    idx = idx[~np.isin(np.arange(len(idx)), list(drop))]
    scale = 1_000 if unit == "ms" else 1_000_000
    rows = []
    for i, t in enumerate(idx):
        ot = int(t.timestamp()) * scale
        c = float(i)
        rows.append(f"{ot},{c},{c + 0.5},{c - 0.5},{c},1.0,{ot + 59 * scale},0,1,0,0,0")
    text = ("open_time,open,high,low,close,volume,close_time,qv,n,tb,tq,ig\n" if header else "")
    text += "\n".join(rows) + "\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"X-1m-{month}.csv", text)
    return buf.getvalue()


# 1. milliseconds (before 2025) and microseconds (from 2025) parse to the same clock
ms = data.parse(make_zip("2024-12", "ms"), "2024-12")
us = data.parse(make_zip("2025-01", "us"), "2025-01")
check("ms timestamps read", ms.index[0] == pd.Timestamp("2024-12-01 00:00"), f"({ms.index[0]})")
check("us timestamps read", us.index[0] == pd.Timestamp("2025-01-01 00:00"), f"({us.index[0]})")
check("bars labelled by open time, one per minute",
      (ms.index.to_series().diff().dropna() == pd.Timedelta("1min")).all() and len(ms) == 60)

# 2. a header row, if a file has one, is skipped rather than parsed
check("header row tolerated", len(data.parse(make_zip("2024-12", header=True), "2024-12")) == 60)

# 3. a file whose rows fall outside its month is refused
check("rows outside the month rejected",
      raises(lambda: data.parse(make_zip("2024-11"), "2024-12"), ValueError))

# 4. checksums: a match passes, a corrupted download is refused
blob = make_zip("2024-12")
good = hashlib.sha256(blob).hexdigest() + "  X-1m-2024-12.zip\n"
check("matching checksum accepted", not raises(lambda: data.verify(blob, good), ValueError))
check("corrupted download rejected", raises(lambda: data.verify(blob[:-1] + b"x", good), ValueError))

# 5. resampling: OHLCV of a 5-minute bar comes from its own five minutes only
bars, dropped = data.resample(ms, "5min")
b = bars.iloc[1]                             # 00:05-00:09, minutes 5..9
check("5m bar labelled by its open", bars.index[1] == pd.Timestamp("2024-12-01 00:05"))
check("5m open/high/low/close/volume",
      (b.open, b.high, b.low, b.close, b.volume) == (5.0, 9.5, 4.5, 9.0, 5.0),
      f"({b.open}, {b.high}, {b.low}, {b.close}, {b.volume})")
check("no bar dropped when complete", dropped == 0 and len(bars) == 12)

# 6. a bar missing more than 20% of its minutes is dropped and counted
gappy = data.parse(make_zip("2024-12", drop=(5, 6)), "2024-12")       # 3 of 5 minutes left
bars, dropped = data.resample(gappy, "5min")
check("incomplete bar dropped", pd.Timestamp("2024-12-01 00:05") not in bars.index)
check("drop counted", dropped == 1, f"(dropped={dropped})")
bars, dropped = data.resample(data.parse(make_zip("2024-12", drop=(5,)), "2024-12"), "5min")
check("bar at exactly 80% kept", pd.Timestamp("2024-12-01 00:05") in bars.index and dropped == 0)

# 7. hourly bars are built from that hour alone
h, _ = data.resample(data.parse(make_zip("2024-12", minutes=120), "2024-12"), "1h")
check("1h bars", list(h.close) == [59.0, 119.0] and list(h.open) == [0.0, 60.0])

# 8. download: fetched, verified, written; a bad checksum leaves nothing on disk
with tempfile.TemporaryDirectory() as tmp:
    data.CACHE = Path(tmp)
    store = {}
    for m in ["2024-11", "2024-12"]:
        z = make_zip(m)
        url = f"{data.ARCHIVE}/BTCUSDT/1m/BTCUSDT-1m-{m}.zip"
        store[url] = z
        store[url + ".CHECKSUM"] = (hashlib.sha256(z).hexdigest() + "  x\n").encode()
    n = data.download("BTCUSDT", ["2024-11", "2024-12"], fetch=store.__getitem__)
    check("months fetched and stored", n == 2 and data.raw_path("BTCUSDT", "2024-12").exists())
    n = data.download("BTCUSDT", ["2024-11", "2024-12"], fetch=store.__getitem__)
    check("months on disk are not fetched again", n == 0)

    url = f"{data.ARCHIVE}/ETHUSDT/1m/ETHUSDT-1m-2024-12.zip"
    store[url] = make_zip("2024-12")
    store[url + ".CHECKSUM"] = b"0" * 64 + b"  x\n"
    check("bad checksum refused",
          raises(lambda: data.download("ETHUSDT", ["2024-12"], fetch=store.__getitem__), ValueError))
    check("nothing kept after a bad checksum", not data.raw_path("ETHUSDT", "2024-12").exists())

# 9. the holdout stays closed unless asked for
check("holdout month refused on download",
      raises(lambda: data.download("BTCUSDT", ["2025-05"], fetch=store.__getitem__), PermissionError))
check("load past the development period refused",
      raises(lambda: data.load("BTCUSDT", end="2025-05-01"), PermissionError))
check("development months stop at April 2025",
      data.dev_months()[0] == "2017-08" and data.dev_months()[-1] == "2025-04")
check("holdout months are May 2025 to October 2026",
      data.holdout_months()[0] == "2025-05" and data.holdout_months()[-1] == "2026-10")

print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
