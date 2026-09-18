"""Competing market makers: price priority, queue priority, and quote staleness.

The single-maker simulation in note 02 never competes for queue position, which
is a first-order concern on a real venue. This adds competing makers.

DESIGN NOTE - read before interpreting anything below.

The first version of this script ran every experiment with inventory skew set to
0.01 and an inventory cap of 50. Skew moves a maker's quotes by
`skew x inventory`, so at full inventory that is 0.50 - five times larger than
the half-spread differences the experiments were trying to measure. The skew
term completely swamped the price ladder, and the control experiment came back
asymmetric (38/27/35 instead of 33/33/33) because random inventory imbalances
fed back into quote placement.

Every experiment about price or queue priority therefore runs with skew = 0.
Skew is studied separately, in experiment D, where it is the variable of
interest rather than an uncontrolled nuisance.

Run:  python3 research/05_queue_competition.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from qlab.lob.agents import MarketMaker
from qlab.lob.exchange import simulate_multi

SEEDS = [0, 1, 2, 3, 4]
STEPS = 4_000
BIG = 10 ** 6          # effectively no inventory limit
pd.set_option("display.width", 175)

COLS = ["flow_share", "total_pnl", "spread_capture", "inventory_pnl",
        "units", "markout_per_unit", "markout_vs_informed", "avg_queue_ahead"]


def run(makers_fn, seeds=SEEDS) -> pd.DataFrame:
    frames = [simulate_multi(makers_fn(), n_steps=STEPS, seed=s).summary()
              for s in seeds]
    out = pd.concat(frames).groupby(level=0).mean()
    out["flow_share"] = out["units"] / out["units"].sum()
    return out


def show(title: str, df: pd.DataFrame, note: str = "") -> None:
    print("\n" + "=" * 120)
    print(title)
    print("=" * 120)
    print(df[[c for c in COLS if c in df.columns]].to_string(
        float_format=lambda x: f"{x:10.3f}"))
    if note:
        print("\n" + note)


def main() -> None:
    # ---- A: control ----
    a = run(lambda: [MarketMaker(name=f"mm{i}", half_spread=0.10, skew=0.0, max_inv=BIG)
                     for i in range(3)])
    spread = a["flow_share"].max() - a["flow_share"].min()
    show("EXPERIMENT A - control: three identical makers", a,
         f"flow share spread = {spread*100:.1f} percentage points.\n"
         f"{'PASS - no structural bias in requote ordering.' if spread < 0.05 else 'FAIL - investigate before reading on.'}")

    # ---- B: price priority ----
    b = run(lambda: [
        MarketMaker(name="wide", half_spread=0.12, skew=0.0, max_inv=BIG),
        MarketMaker(name="mid", half_spread=0.10, skew=0.0, max_inv=BIG),
        MarketMaker(name="tight", half_spread=0.08, skew=0.0, max_inv=BIG),
    ])
    show("EXPERIMENT B - price priority: what does two ticks of improvement buy?", b,
         "Price priority is close to absolute. Two ticks inside takes essentially\n"
         "all the flow; the makers behind it are not competing, they are queueing\n"
         "for the residual that walks past the top of book.")

    # ---- C: staleness vs queue position ----
    c = run(lambda: [
        MarketMaker(name="every_step", half_spread=0.10, skew=0.0, max_inv=BIG, requote_every=1),
        MarketMaker(name="every_10", half_spread=0.10, skew=0.0, max_inv=BIG, requote_every=10),
        MarketMaker(name="every_50", half_spread=0.10, skew=0.0, max_inv=BIG, requote_every=50),
    ])
    show("EXPERIMENT C - requote frequency: fresh price vs queue position", c,
         "Cancelling to refresh forfeits FIFO priority; holding a quote keeps the\n"
         "priority but leaves a stale price exposed. Compare markout_vs_informed\n"
         "across the three: that column is the price of staleness.")

    # ---- D: skew as the variable of interest ----
    d = run(lambda: [
        MarketMaker(name="skew_0.00", half_spread=0.10, skew=0.00, max_inv=50),
        MarketMaker(name="skew_0.002", half_spread=0.10, skew=0.002, max_inv=50),
        MarketMaker(name="skew_0.01", half_spread=0.10, skew=0.01, max_inv=50),
    ])
    show("EXPERIMENT D - inventory skew, studied deliberately (cap = 50)", d,
         "Skew x max_inventory must stay small relative to the spread you quote,\n"
         "or inventory management silently becomes your pricing policy.\n"
         "Here 0.01 x 50 = 0.50 against a half-spread of 0.10 - the tail wagging the dog.")

    print("\n" + "-" * 120)
    print("Summary of what is and is not established:")
    print("  established : price priority dominates queue priority; staleness is paid")
    print("                for in adverse selection; skew can swamp quoted spread.")
    print("  NOT established : anything about latency, fees, or maker rebates -")
    print("                none of which this simulation models.")
    print("-" * 120)


if __name__ == "__main__":
    main()
