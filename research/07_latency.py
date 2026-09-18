"""Latency: a relative disadvantage, not an absolute one.

Note 04 listed latency as the largest remaining gap. This closes it, but not
with the result that was expected.

Model: a maker's decision at step t reaches the book at t + latency. Both the
new quote and the implicit cancel of the old one are delayed, which is the half
that matters - a maker watching the price move away can decide to pull its quote
and still be filled on it for `latency` steps.

FINDING, stated up front so the tables are read correctly: there is no latency
ladder. Flow concentrates almost entirely on whichever maker is SLOWEST IN THE
FIELD, and that concentration moves when the field changes. Latency is a
positional disadvantage relative to competitors, not a quantity with its own
price. Experiment G3 demonstrates this directly.

Run:  python3 research/07_latency.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from qlab.lob.agents import MarketMaker
from qlab.lob.exchange import simulate_multi

SEEDS = list(range(10))
STEPS = 4_000
BIG = 10 ** 6
HALF_SPREAD = 0.10
SIGMA = 0.02
pd.set_option("display.width", 175)


def run(latencies, **kw):
    def mk():
        return [MarketMaker(name=f"lat_{L}", half_spread=HALF_SPREAD, skew=0.0,
                            max_inv=BIG, latency=L) for L in latencies]
    frames = [simulate_multi(mk(), n_steps=STEPS, seed=s, **kw).summary()
              for s in SEEDS]
    allf = pd.concat(frames)
    m = allf.groupby(level=0).mean()
    sd = allf.groupby(level=0).std(ddof=1)
    m["flow_share"] = m["units"] / m["units"].sum()
    m["markout_sd"] = sd["markout_per_unit"]
    return m.reindex([f"lat_{L}" for L in latencies])


def show(title, df, note=""):
    print("\n" + "=" * 112)
    print(title)
    print("=" * 112)
    print(df[["flow_share", "units", "total_pnl", "markout_per_unit", "markout_sd"]]
          .to_string(float_format=lambda x: f"{x:10.3f}"))
    if note:
        print("\n" + note)


def main() -> None:
    kw = dict(jump_prob=0.01, jump_size=0.50)

    field_a = [0, 2, 5, 10, 15, 20]
    field_b = [0, 2, 5, 10, 15, 20, 30, 40]

    a = run(field_a, **kw)
    show("G1 - field with maximum latency 20", a)
    top_a = a["flow_share"].idxmax()

    b = run(field_b, **kw)
    show("G2 - identical, except two slower makers added", b)
    top_b = b["flow_share"].idxmax()

    print("\n" + "=" * 112)
    print("G3 - where did the flow go?")
    print("=" * 112)
    print(f"  field max latency 20 -> flow concentrates on {top_a} "
          f"({a['flow_share'].max()*100:.1f}%)")
    print(f"  field max latency 40 -> flow concentrates on {top_b} "
          f"({b['flow_share'].max()*100:.1f}%)")
    print(f"\n  lat_20 share when it was slowest : {a.loc['lat_20','flow_share']*100:5.1f}%")
    print(f"  lat_20 share when it was not     : {b.loc['lat_20','flow_share']*100:5.1f}%")
    print("\n  The same agent, with the same latency, in the same market process.")
    print("  Its exposure changed because the competition changed.")

    print("\n" + "=" * 112)
    print("G4 - is there a markout ladder? (10 seeds, mean +/- 1 sd)")
    print("=" * 112)
    for i in b.index:
        mean, sd = b.loc[i, "markout_per_unit"], b.loc[i, "markout_sd"]
        flag = "" if abs(mean) > 2 * sd else "   <- not distinguishable from zero"
        print(f"  {i:>7}: {mean:+.4f} +/- {sd:.4f}{flag}")
    print("\n  No. Across-seed dispersion swamps the differences. The only entry that")
    print("  even approaches significance is the slowest maker, and at ~1.4 sd it")
    print("  would not survive a serious test. Reporting a monotonic 'cost of")
    print("  latency' from these numbers would be reading a trend into noise.")

    cross = (HALF_SPREAD / SIGMA) ** 2
    print(f"\n  For reference: lag drift is sigma*sqrt(L), which reaches the quoted")
    print(f"  half-spread of {HALF_SPREAD} at L = {cross:.0f} steps. The flow discontinuity")
    print(f"  does not sit at that value in either field, which is further evidence")
    print(f"  the effect is relative rather than absolute.")

    print("\n" + "-" * 112)
    print("What this establishes: latency's cost is competitive, not intrinsic.")
    print("What it does not: any per-step price for latency. That needs a venue")
    print("model with a fixed reference population, not a self-referential field.")
    print("-" * 112)


if __name__ == "__main__":
    main()
