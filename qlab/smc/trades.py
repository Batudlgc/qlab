"""Orders and simulated fills for the pre-registered strategy, in R net of costs.

    prep = prepare(m1, "5min", "1h")          # setups, bias and pools for one timeframe pair
    orders = plan(prep, Variant("5min", "1h", "liquidity", "proximal", "all"))
    trades = simulate(orders, m1)             # one row per order, filled or not

Fills are simulated on 1-minute bars, pessimistically (reports/smc_preregistration.md):
a limit fills only when price trades strictly through it, and fills at the limit; a minute
that could have hit both stop and target books the stop; a fill minute that reaches the
stop is a loss; a target touched in the fill minute does not count, since the order of
events inside a minute is unknown.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from . import data, structure as st

FEE = 0.001             # per side: Binance regular-user spot, maker and taker alike
SLIP = 0.0002           # stop-market slippage, 2 bps
STOP_BUFFER = 0.1       # stop beyond the sweep extreme, in ATR
EXPIRY_BARS = 24        # entry-timeframe bars a limit order works before it is cancelled
MIN_R_LIQUIDITY = 2.0   # opposing-liquidity target must be at least this far
FIXED_R = 3.0
SILVER_BULLET_HOURS = (3, 10, 14)   # New York time; each window is one hour
MINUTE = pd.Timedelta("1min")


@dataclass(frozen=True)
class Variant:
    entry_tf: str       # "5min" | "15min"
    bias_tf: str        # "1h" | "4h"
    target: str         # "liquidity" | "3r"
    entry: str          # "proximal" | "mid"
    session: str        # "all" | "silver"

    @property
    def name(self) -> str:
        return f"{self.entry_tf}/{self.bias_tf} {self.target} {self.entry} {self.session}"


VARIANTS = [Variant(e, b, t, x, s) for (e, b), t, x, s in product(
    [("5min", "1h"), ("15min", "4h")], ["liquidity", "3r"], ["proximal", "mid"], ["all", "silver"])]


# ---------------------------------------------------------------- search helper

def _first(cond, lo: int, hi: int, chunk: int = 512) -> int:
    """First i in [lo, hi) where cond(i, j)[i - lo] is true, searching in growing chunks."""
    i = lo
    while i < hi:
        j = min(hi, i + chunk)
        m = cond(i, j)
        k = int(m.argmax())
        if m[k]:
            return i + k
        i, chunk = j, chunk * 4
    return -1


# ---------------------------------------------------------------- prepare and plan

@dataclass
class Prepared:
    ltf: pd.DataFrame
    setups: pd.DataFrame
    pools: dict          # side -> arrays (known, level, taken, segment), sorted by known
    seg: np.ndarray


def _pools(ltf: pd.DataFrame, seg: np.ndarray) -> dict:
    """Swing highs and lows with the bar at which price first trades through each."""
    sw = st.swings(ltf, seg=seg)
    h, l = ltf["high"].to_numpy(), ltf["low"].to_numpy()
    seg_end = pd.Series(np.arange(len(ltf))).groupby(seg).transform("max").to_numpy()
    out = {}
    for kind in ("high", "low"):
        s = sw[sw.kind == kind]
        known, level = s.known.to_numpy(), s.level.to_numpy()
        taken = np.empty(len(s), dtype=np.int64)
        for i, (kn, lv) in enumerate(zip(known, level)):
            end = seg_end[kn] + 1
            hit = (_first(lambda a, b: h[a:b] > lv, kn + 1, end) if kind == "high"
                   else _first(lambda a, b: l[a:b] < lv, kn + 1, end))
            taken[i] = hit if hit >= 0 else np.iinfo(np.int64).max
        out[kind] = (known, level, taken, seg[known])
    return out


def prepare(m1: pd.DataFrame, entry_tf: str, bias_tf: str) -> Prepared:
    """Everything the variants of one timeframe pair share."""
    ltf, _ = data.resample(m1, entry_tf)
    htf, _ = data.resample(m1, bias_tf)
    seg = st.segments(ltf.index)
    s = st.setups(ltf)
    b = st.align(st.bias(htf), ltf.index).to_numpy()
    s = s[b[s.known_pos.to_numpy()] == s.direction.to_numpy()].reset_index(drop=True)
    return Prepared(ltf, s, _pools(ltf, seg), seg)


def _liquidity_target(prep: Prepared, kp: int, direction: int, threshold: float) -> float:
    """Nearest active opposing pool at least `threshold` away, as known at bar kp; NaN if none."""
    known, level, taken, segs = prep.pools["high" if direction == 1 else "low"]
    hi = np.searchsorted(known, kp, side="right")
    m = (segs[:hi] == prep.seg[kp]) & (taken[:hi] > kp)
    m &= (level[:hi] >= threshold) if direction == 1 else (level[:hi] <= threshold)
    if not m.any():
        return np.nan
    return level[:hi][m].min() if direction == 1 else level[:hi][m].max()


def in_silver_bullet(t: pd.DatetimeIndex) -> np.ndarray:
    """Bars that open inside a Silver Bullet hour, New York time (DST applied)."""
    ny = t.tz_localize("UTC").tz_convert("America/New_York")
    return np.isin(ny.hour, SILVER_BULLET_HOURS)


def plan(prep: Prepared, v: Variant) -> pd.DataFrame:
    """One limit order per setup that survives the variant's filters, in time order."""
    s = prep.setups
    if v.session == "silver":
        s = s[in_silver_bullet(prep.ltf.index[s.fvg_pos.to_numpy()])]
    rows = []
    bar = pd.Timedelta(v.entry_tf)
    for r in s.itertuples(index=False):
        d = r.direction
        proximal = r.fvg_top if d == 1 else r.fvg_bottom
        entry = proximal if v.entry == "proximal" else (r.fvg_top + r.fvg_bottom) / 2
        stop = r.sweep_extreme - d * STOP_BUFFER * r.atr
        risk = d * (entry - stop)
        if not risk > 0:
            continue
        if v.target == "3r":
            target = entry + d * FIXED_R * risk
        else:
            target = _liquidity_target(prep, r.known_pos, d, entry + d * MIN_R_LIQUIDITY * risk)
            if np.isnan(target):
                continue
        rows.append({"known": r.known, "direction": d, "entry": entry, "stop": stop,
                     "target": target, "risk": risk, "expires": r.known + EXPIRY_BARS * bar,
                     "atr": r.atr, "fvg_pos": r.fvg_pos})
    cols = ["known", "direction", "entry", "stop", "target", "risk", "expires", "atr", "fvg_pos"]
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------- simulate

def _exit(m1a, d: int, f: int, stop: float, target: float, slip: float,
          fill_minute: bool = True):
    """Exit (index, price, reason) for a position that is live from minute f.

    With fill_minute, f is the minute the limit filled in: its stop counts, its target does
    not (the order of events inside it is unknown). Without, the position was opened at the
    close of minute f - 1 and all of minute f counts.
    """
    t, o, h, l, c = m1a
    n = len(c)

    def stopped(i):
        gap = o[i] <= stop if d == 1 else o[i] >= stop
        return i, (o[i] if gap else stop * (1 - d * slip)), "stop"

    if fill_minute:
        if (l[f] <= stop) if d == 1 else (h[f] >= stop):
            return stopped(f)
        f += 1
    if d == 1:
        s = _first(lambda a, b: l[a:b] <= stop, f, n)
        g = _first(lambda a, b: h[a:b] > target, f, n if s < 0 else s + 1)
    else:
        s = _first(lambda a, b: h[a:b] >= stop, f, n)
        g = _first(lambda a, b: l[a:b] < target, f, n if s < 0 else s + 1)
    if s >= 0 and (g < 0 or s <= g):
        return stopped(s)
    if g >= 0:
        return g, target, "target"
    return n - 1, c[n - 1], "end"


def simulate(orders: pd.DataFrame, m1: pd.DataFrame, fee: float = FEE,
             slip: float = SLIP) -> pd.DataFrame:
    """Work each order on 1-minute bars, one order or position at a time."""
    t = m1.index.to_numpy()
    m1a = (t, *(m1[x].to_numpy() for x in ("open", "high", "low", "close")))
    _, o, h, l, c = m1a
    busy_until = None
    out = []
    for r in orders.itertuples(index=False):
        row = r._asdict()
        if busy_until is not None and r.known < busy_until:
            out.append(dict(row, status="busy"))
            continue
        d, entry, stop, target = r.direction, r.entry, r.stop, r.target
        i0 = np.searchsorted(t, np.datetime64(r.known))
        ie = np.searchsorted(t, np.datetime64(r.expires))
        if d == 1:
            f = _first(lambda a, b: l[a:b] < entry, i0, ie)
            x = _first(lambda a, b: (h[a:b] >= target) | (l[a:b] <= stop), i0, ie if f < 0 else f)
        else:
            f = _first(lambda a, b: h[a:b] > entry, i0, ie)
            x = _first(lambda a, b: (l[a:b] <= target) | (h[a:b] >= stop), i0, ie if f < 0 else f)
        if x >= 0:
            busy_until = pd.Timestamp(t[x]) + MINUTE
            out.append(dict(row, status="cancelled", end=busy_until))
            continue
        if f < 0:
            busy_until = r.expires
            out.append(dict(row, status="expired", end=r.expires))
            continue
        e, price, reason = _exit(m1a, d, f, stop, target, slip)
        busy_until = pd.Timestamp(t[e]) + MINUTE
        gross = d * (price - entry) / r.risk
        cost = fee * (entry + price) / r.risk
        out.append(dict(row, status="filled", fill=pd.Timestamp(t[f]), end=busy_until,
                        exit_price=price, exit_reason=reason, r_gross=gross, cost_r=cost,
                        r_net=gross - cost))
    cols = list(orders.columns) + ["status", "fill", "end", "exit_price", "exit_reason",
                                   "r_gross", "cost_r", "r_net"]
    return pd.DataFrame(out, columns=cols)


# ---------------------------------------------------------------- control

def control(trades: pd.DataFrame, m1: pd.DataFrame, seeds: int = 200, fee: float = FEE,
            slip: float = SLIP) -> np.ndarray:
    """Mean net R of random-entry trades with the same geometry, one value per seed.

    Each filled trade is replayed from a uniformly random minute of the same calendar month,
    entering at that minute's close, in the same direction, with the same stop and target
    distances in percent and the same costs.
    """
    filled = trades[trades.status == "filled"]
    t = m1.index.to_numpy()
    m1a = (t, *(m1[x].to_numpy() for x in ("open", "high", "low", "close")))
    c = m1a[4]
    month = m1.index.to_period("M")
    bounds = {p: (np.searchsorted(t, np.datetime64(p.start_time)),
                  np.searchsorted(t, np.datetime64(p.end_time), side="right"))
              for p in month.unique()}
    rng = np.random.default_rng(0)
    means = np.empty(seeds)
    for k in range(seeds):
        rs = []
        for r in filled.itertuples(index=False):
            lo, hi = bounds[pd.Timestamp(r.fill).to_period("M")]
            i = int(rng.integers(lo, hi - 1))
            entry = c[i]
            stop = entry * (r.stop / r.entry)
            target = entry * (r.target / r.entry)
            risk = r.direction * (entry - stop)
            # entry at the close of minute i: the position is live for all of minute i + 1
            e, price, _ = _exit(m1a, r.direction, i + 1, stop, target, slip, fill_minute=False)
            rs.append(r.direction * (price - entry) / risk - fee * (entry + price) / risk)
        means[k] = np.mean(rs) if rs else np.nan
    return means
