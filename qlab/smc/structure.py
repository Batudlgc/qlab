"""Market-structure detection: ATR, swings, sweeps, structure shifts, fair value gaps, bias.

Every definition follows reports/smc_preregistration.md. Each detection carries the bar
position at whose *close* it becomes known, and nothing is reported before then. A
swing at bar i is known at bar i + k, not at i.

Data gaps break the series into segments (consecutive bars exactly one bar length
apart). No pattern spans a gap and all state resets at one: a level that was not watched
across the gap cannot be said to have been swept or held.

Short setups are found by running the long logic on the price-mirrored series, so the
two directions cannot drift apart.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

K = 3                 # swing: bars on each side
N_RECLAIM = 3         # sweep: bars allowed to close back over the level, breach bar included
MSS_WINDOW = 12       # structure shift: bars allowed after the sweep confirms
DISPLACEMENT = 1.0    # min body, in ATR, of one bar in the sweep-to-shift leg
FVG_MIN = 0.25        # min gap height, in ATR
ATR_N = 14


def bar_length(index: pd.DatetimeIndex) -> pd.Timedelta:
    """The most common spacing between bars."""
    return pd.Series(index).diff().mode().iloc[0]


def segments(index: pd.DatetimeIndex, bar: pd.Timedelta | None = None) -> np.ndarray:
    """Segment id per bar; a new segment starts after every gap."""
    bar = bar or bar_length(index)
    return (pd.Series(index).diff() != bar).cumsum().to_numpy()


def atr(df: pd.DataFrame, n: int = ATR_N, seg: np.ndarray | None = None) -> np.ndarray:
    """Wilder ATR, restarted at every gap; NaN for the first n - 1 bars of each segment."""
    seg = segments(df.index) if seg is None else seg
    h, l, c = (df[x].to_numpy() for x in ("high", "low", "close"))
    out = np.full(len(df), np.nan)
    run, start, value = 0, 0, np.nan
    trs = np.empty(len(df))
    for t in range(len(df)):
        if t == 0 or seg[t] != seg[t - 1]:
            run, start = 0, t
        trs[t] = h[t] - l[t] if run == 0 else max(h[t] - l[t], abs(h[t] - c[t - 1]),
                                                   abs(l[t] - c[t - 1]))
        run += 1
        if run == n:
            value = trs[start:t + 1].mean()
        elif run > n:
            value = (value * (n - 1) + trs[t]) / n
        out[t] = value if run >= n else np.nan
    return out


def _swing_mask(x: np.ndarray, seg: np.ndarray, k: int, low: bool) -> np.ndarray:
    """Bars strictly below (low=True) or above all k bars on each side, within one segment."""
    s = pd.Series(-x if not low else x)
    left = s.shift(1).rolling(k).min()
    right = s[::-1].shift(1).rolling(k).min()[::-1]
    sseg = pd.Series(seg)
    same = (sseg.shift(k) == sseg) & (sseg.shift(-k) == sseg)
    return ((s < left) & (s < right) & same).to_numpy()


def swings(df: pd.DataFrame, k: int = K, seg: np.ndarray | None = None) -> pd.DataFrame:
    """Swing points: pos (bar of the extreme), known (pos + k), kind ('high'|'low'), level."""
    seg = segments(df.index) if seg is None else seg
    rows = []
    for kind, col, low in (("high", "high", False), ("low", "low", True)):
        x = df[col].to_numpy()
        for i in np.flatnonzero(_swing_mask(x, seg, k, low)):
            rows.append((i, i + k, kind, x[i]))
    out = pd.DataFrame(rows, columns=["pos", "known", "kind", "level"])
    return out.sort_values(["known", "pos"]).reset_index(drop=True)


def _long_setups(o, h, l, c, a, seg, k, n_reclaim, mss_window, displacement, fvg_min):
    """Long setups on raw arrays. Short setups call this on the mirrored series."""
    n = len(c)
    sw_low = _swing_mask(l, seg, k, low=True)
    sw_high = _swing_mask(h, seg, k, low=False)
    out = []
    for t in range(n):
        if t == 0 or seg[t] != seg[t - 1]:
            pools, last_high, cands, seq = [], None, [], None

        # 1. sweeps: a bar trades below an active pool, then a close back above it
        for lvl in [p for p in pools if l[t] < p]:
            pools.remove(lvl)
            cands.append({"level": lvl, "start": t, "extreme": l[t],
                          "expires": t + n_reclaim - 1, "ref": last_high})
        for cd in cands:
            cd["extreme"] = min(cd["extreme"], l[t])
        done = [cd for cd in cands if c[t] > cd["level"]]
        if done:
            best = max(done, key=lambda cd: cd["level"])
            seq = {"start": min(cd["start"] for cd in done), "sweep": t,
                   "extreme": min(cd["extreme"] for cd in done), "level": best["level"],
                   "ref": best["ref"], "deadline": t + mss_window, "mss": None}
        cands = [cd for cd in cands if all(cd is not d for d in done) and t < cd["expires"]]

        # 2. structure shift with displacement, then the first eligible FVG
        if seq is not None:
            if seq["mss"] is None:
                if seq["ref"] is None:
                    seq = None
                elif c[t] > seq["ref"]:
                    leg = range(seq["start"], t + 1)
                    if any(abs(c[x] - o[x]) >= displacement * a[x - 1] for x in leg
                           if x >= 1 and seg[x - 1] == seg[t]):
                        seq["mss"] = t
                    else:
                        seq = None
                elif t >= seq["deadline"]:
                    seq = None
            if seq is not None and seq["mss"] is not None:
                last_j = seq["mss"] + 1           # middle bar may be the MSS bar itself
                for j in range(seq["start"] + 1, min(t, last_j) + 1):
                    if j < 2 or seg[j - 2] != seg[t]:
                        continue
                    gap = l[j] - h[j - 2]
                    if gap > 0 and gap >= fvg_min * a[j - 1]:
                        out.append({"known_pos": t, "sweep_start_pos": seq["start"],
                                    "sweep_pos": seq["sweep"], "mss_pos": seq["mss"],
                                    "fvg_pos": j, "sweep_level": seq["level"],
                                    "sweep_extreme": seq["extreme"], "ref_level": seq["ref"],
                                    "fvg_top": l[j], "fvg_bottom": h[j - 2], "atr": a[t]})
                        seq = None
                        break
                else:
                    if t >= last_j:
                        seq = None

        # 3. swings that become known at this close are usable from the next bar
        if sw_low[t - k] if t >= k else False:
            pools.append(l[t - k])
        if sw_high[t - k] if t >= k else False:
            last_high = h[t - k]
    return out


def setups(df: pd.DataFrame, k: int = K, n_reclaim: int = N_RECLAIM,
           mss_window: int = MSS_WINDOW, displacement: float = DISPLACEMENT,
           fvg_min: float = FVG_MIN, atr_n: int = ATR_N) -> pd.DataFrame:
    """Sweep -> structure shift with displacement -> FVG, both directions.

    One row per setup, known at the close of bar known_pos (timestamp `known`). Prices are
    in the original series; for a short, the FVG's proximal edge is fvg_bottom.
    """
    seg = segments(df.index)
    a = atr(df, atr_n, seg)
    o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
    params = (k, n_reclaim, mss_window, displacement, fvg_min)
    rows = [dict(r, direction=1) for r in _long_setups(o, h, l, c, a, seg, *params)]
    for r in _long_setups(-o, -l, -h, -c, a, seg, *params):
        rows.append(dict(r, direction=-1, sweep_level=-r["sweep_level"],
                         sweep_extreme=-r["sweep_extreme"], ref_level=-r["ref_level"],
                         fvg_top=-r["fvg_bottom"], fvg_bottom=-r["fvg_top"]))
    cols = ["known", "direction", "known_pos", "sweep_start_pos", "sweep_pos", "mss_pos",
            "fvg_pos", "sweep_level", "sweep_extreme", "ref_level", "fvg_top", "fvg_bottom", "atr"]
    out = pd.DataFrame(rows, columns=cols[1:])
    bar = bar_length(df.index)
    out.insert(0, "known", df.index[out["known_pos"].to_numpy()] + bar if len(out) else [])
    return out.sort_values(["known_pos", "direction"]).reset_index(drop=True)


def bias(df: pd.DataFrame, k: int = K) -> pd.Series:
    """+1 / -1 / 0 after each bar's close: the side of the latest close beyond a known swing.

    0 until the first such break in each segment.
    """
    seg = segments(df.index)
    h, l, c = (df[x].to_numpy() for x in ("high", "low", "close"))
    sw_low, sw_high = _swing_mask(l, seg, k, True), _swing_mask(h, seg, k, False)
    out = np.zeros(len(df), dtype=int)
    for t in range(len(df)):
        if t == 0 or seg[t] != seg[t - 1]:
            state, hi, lo = 0, None, None
        if hi is not None and c[t] > hi:
            state = 1
        elif lo is not None and c[t] < lo:
            state = -1
        out[t] = state
        if t >= k and sw_high[t - k]:
            hi = h[t - k]
        if t >= k and sw_low[t - k]:
            lo = l[t - k]
    return pd.Series(out, index=df.index, name="bias")


def align(htf: pd.Series, ltf_index: pd.DatetimeIndex) -> pd.Series:
    """Higher-timeframe values as known at the close of each lower-timeframe bar.

    An HTF bar's value is usable only once that bar has closed (open + its length).
    """
    known = pd.Series(htf.to_numpy(), index=htf.index + bar_length(htf.index)).sort_index()
    at = ltf_index + bar_length(ltf_index)
    pos = known.index.searchsorted(at, side="right") - 1
    vals = np.where(pos >= 0, known.to_numpy()[np.clip(pos, 0, None)], 0)
    return pd.Series(vals, index=ltf_index, name=htf.name)
