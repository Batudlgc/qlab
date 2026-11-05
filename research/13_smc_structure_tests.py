"""Correctness tests for structure detection. Offline: hand-built charts and a seeded random walk."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from qlab.smc import structure as st

fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


def frame(bars, start="2024-01-01", freq="5min"):
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"])
    df.index = pd.date_range(start, periods=len(df), freq=freq)
    df["volume"] = 1.0
    return df


# A textbook long setup. Bars 0-19 are flat (ATR = 1, equal lows: no swings).
# 22 is a swing high at 103, 26 a swing low at 98. Bar 32 wicks to 97.4 and closes back at
# 98.6 (sweep). 33-34 displace upward; 34 closes at 103.5 above the swing high (MSS) and
# leaves an FVG between high[32] = 99.0 and low[34] = 100.7.
FLAT = [(100, 100.5, 99.5, 100)] * 20
SETUP = FLAT + [
    (100.0, 101.0, 99.8, 100.8), (100.8, 102.0, 100.5, 101.8), (101.8, 103.0, 101.5, 102.5),
    (102.5, 102.8, 101.2, 101.5), (101.5, 101.8, 100.2, 100.4), (100.4, 100.6, 99.0, 99.3),
    (99.3, 99.5, 98.0, 98.4), (98.4, 99.4, 98.3, 99.2), (99.2, 100.2, 99.0, 100.0),
    (100.0, 100.1, 99.4, 99.6), (99.6, 99.8, 98.9, 99.0), (99.0, 99.2, 98.5, 98.8),
    (98.8, 99.0, 97.4, 98.6),                                   # 32 sweep
    (98.6, 101.0, 98.5, 100.9), (100.9, 103.8, 100.7, 103.5),  # 33, 34 displacement, MSS
] + [(103.5, 104.0, 103.2, 103.8)] * 8
df = frame(SETUP)


def mirror(d):
    m = d.copy()
    m["open"], m["close"] = 200 - d["open"], 200 - d["close"]
    m["high"], m["low"] = 200 - d["low"], 200 - d["high"]
    return m


# 1. swings are reported when they become known, k bars after the extreme
sw = st.swings(df)
h22 = sw[(sw.kind == "high") & (sw.pos == 22)]
l26 = sw[(sw.kind == "low") & (sw.pos == 26)]
check("swing high found at its extreme", len(h22) == 1 and h22.level.iloc[0] == 103.0)
check("swing known k bars later, not at the extreme",
      h22.known.iloc[0] == 25 and l26.known.iloc[0] == 29)
check("equal lows are not swings", not (sw.pos < 20).any())

# 2. the textbook long setup is found with the expected levels
s = st.setups(df)
longs = s[s.direction == 1]
check("long setup found", len(longs) == 1, f"({len(longs)})")
if len(longs) == 1:
    r = longs.iloc[0]
    check("sweep, MSS and FVG at the right bars",
          (r.sweep_pos, r.mss_pos, r.fvg_pos, r.known_pos) == (32, 34, 34, 34),
          f"({r.sweep_pos}, {r.mss_pos}, {r.fvg_pos}, {r.known_pos})")
    check("levels", (r.sweep_level, r.sweep_extreme, r.ref_level, r.fvg_bottom, r.fvg_top)
          == (98.0, 97.4, 103.0, 99.0, 100.7))
    check("known at the close of the MSS bar", r.known == df.index[34] + pd.Timedelta("5min"))

# 3. the mirror image is the same setup as a short
ms = st.setups(mirror(df))
shorts = ms[ms.direction == -1]
check("mirrored chart gives the mirrored short", len(shorts) == 1 and len(ms[ms.direction == 1]) == 0)
if len(shorts) == 1:
    r = shorts.iloc[0]
    check("short levels mirror the long ones",
          np.allclose([r.sweep_level, r.sweep_extreme, r.ref_level, r.fvg_top, r.fvg_bottom],
                      [102.0, 102.6, 97.0, 101.0, 99.3]))

# 4. each rule, when it fails, removes the setup
wick = [list(b) for b in SETUP]
wick[34] = [100.9, 103.8, 100.7, 102.9]                     # wick through 103, close below
late_close = st.setups(frame(wick))
check("a close above on the next bar is the shift",
      (late_close.direction == 1).sum() == 1 and late_close.mss_pos.iloc[0] == 35)
wick[35:] = [[102.5, 102.9, 102.0, 102.5]] * (len(SETUP) - 35)   # and never closes above
check("wick through the level is not a shift", (st.setups(frame(wick)).direction == 1).sum() == 0)
check("no displacement, no setup", (st.setups(df, displacement=5.0).direction == 1).sum() == 0)
check("gap too small, no setup", (st.setups(df, fvg_min=5.0).direction == 1).sum() == 0)
check("shift outside the window, no setup", (st.setups(df, mss_window=1).direction == 1).sum() == 0)
late = [list(b) for b in SETUP]
late[32] = [98.8, 99.0, 97.4, 97.6]                         # no reclaim on the breach bar
check("reclaim one bar late: found with N=3", (st.setups(frame(late)).direction == 1).sum() == 1)
check("reclaim one bar late: refused with N=1",
      (st.setups(frame(late), n_reclaim=1).direction == 1).sum() == 0)

# 4b. the reference high must be known before the sweep begins. Bar 29 becomes a swing high
# at 100.3, but it is only known at the close of bar 32, the sweep bar itself, so the shift
# must still be measured against 103 (bar 34), not 100.3 (bar 33).
recent = [list(b) for b in SETUP]
recent[29] = [100.0, 100.3, 99.4, 99.6]
rs = st.setups(frame(recent))
check("a swing known only at the sweep is not the reference",
      len(rs) == 1 and (rs.ref_level.iloc[0], rs.mss_pos.iloc[0]) == (103.0, 34),
      f"({list(zip(rs.ref_level, rs.mss_pos))})")

# 5. a data gap inside the pattern removes it; nothing is built across a gap
gapped = df.drop(df.index[33])
check("no setup across a gap", (st.setups(gapped).direction == 1).sum() == 0)
check("no swing across a gap",
      not ((st.swings(df.drop(df.index[24])).pos.between(21, 27))).any())
# 6. causality: cutting the data at any bar never changes what was known before the cut
rng = np.random.default_rng(7)
n = 4000
close = 100 + np.cumsum(rng.normal(0, 0.3, n))
op = np.r_[100, close[:-1]]
hi = np.maximum(op, close) + rng.exponential(0.15, n)
lo = np.minimum(op, close) - rng.exponential(0.15, n)
rw = frame(np.c_[op, hi, lo, close])
full_s, full_sw, full_a = st.setups(rw), st.swings(rw), st.atr(rw)
check("random walk produces setups to test", len(full_s) >= 10, f"({len(full_s)})")
a = st.atr(rw.drop(rw.index[1000]))           # position 1000 now starts a new segment
check("ATR restarts after a gap", np.isnan(a[1000:1013]).all() and not np.isnan(a[1013]))
same = True
for cut in sorted(rng.choice(np.arange(200, n), 40, replace=False)):
    part = rw.iloc[:cut]
    ps, psw, pa = st.setups(part), st.swings(part), st.atr(part)
    same &= ps.equals(full_s[full_s.known_pos < cut].reset_index(drop=True))
    same &= psw.equals(full_sw[full_sw.known < cut].reset_index(drop=True))
    same &= np.array_equal(pa, full_a[:cut], equal_nan=True)
check("setups, swings and ATR unchanged by truncation (40 cuts)", same)
# the sharper form: each setup is found, identically, from the data up to its own close
missing = 0
for _, row in full_s.iterrows():
    last = st.setups(rw.iloc[:row.known_pos + 1]).iloc[-1:].reset_index(drop=True)
    missing += not last.equals(full_s.loc[[_]].reset_index(drop=True))
check("every setup is computable at the bar it is known", missing == 0,
      f"({missing} of {len(full_s)} not)")

# 7. higher-timeframe bias: an HTF bar is used only after it has closed
htf = rw.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
b = st.bias(htf)
check("bias takes both signs", set(b.unique()) >= {1, -1}, f"({sorted(b.unique())})")
al = st.align(b, rw.index)
t = 30                                       # an hour boundary well inside the series
hour_open = htf.index[t]
inside = rw.index[(rw.index >= hour_open) & (rw.index < hour_open + pd.Timedelta("1h"))]
check("within an hour, LTF bars before its close see the previous hour's bias",
      (al[inside[:-1]] == b.iloc[t - 1]).all())
check("the LTF bar that closes with the hour sees that hour's bias", al[inside[-1]] == b.iloc[t])
tampered = htf.copy()
tampered.iloc[t:, tampered.columns.get_loc("close")] += 50   # rewrite hour t onward
al2 = st.align(st.bias(tampered), rw.index)
check("changing an unclosed HTF bar changes nothing before its close",
      al2[rw.index < inside[-1]].equals(al[rw.index < inside[-1]]))

print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
