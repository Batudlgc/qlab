"""Two gaps closed from note 03: quote staleness under jumps, and maker rebates.

Note 03 failed to find a staleness penalty and said so. The proposed reason was
that under a pure diffusion a stale quote drifts out of the market and simply
stops trading - it cannot be picked off if it never fills. Jumps should change
that, by leaving a stale quote standing on the wrong side of a sudden move.

Experiment E tests exactly that, with jumps off and on, changing nothing else.
Experiment F asks what a maker rebate does to the economics.

Run:  python3 research/06_staleness_and_fees.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from qlab.lob.agents import MarketMaker
from qlab.lob.exchange import Fees, simulate_multi

SEEDS = [0, 1, 2, 3, 4]
STEPS = 4_000
BIG = 10 ** 6
pd.set_option("display.width", 175)


def makers():
    return [MarketMaker(name="every_step", half_spread=0.10, skew=0.0,
                        max_inv=BIG, requote_every=1),
            MarketMaker(name="every_10", half_spread=0.10, skew=0.0,
                        max_inv=BIG, requote_every=10),
            MarketMaker(name="every_50", half_spread=0.10, skew=0.0,
                        max_inv=BIG, requote_every=50)]


def run(**kw) -> pd.DataFrame:
    frames = [simulate_multi(makers(), n_steps=STEPS, seed=s, **kw).summary()
              for s in SEEDS]
    out = pd.concat(frames).groupby(level=0).mean()
    out["flow_share"] = out["units"] / out["units"].sum()
    return out


COLS = ["flow_share", "total_pnl", "units", "markout_per_unit", "markout_vs_informed"]


def show(title, df, note=""):
    print("\n" + "=" * 118)
    print(title)
    print("=" * 118)
    print(df[[c for c in COLS if c in df.columns]].to_string(
        float_format=lambda x: f"{x:10.3f}"))
    if note:
        print("\n" + note)


def main() -> None:
    print("EXPERIMENT E - does staleness cost anything, and under what price process?")

    diff = run(jump_prob=0.0)
    show("E1 - pure diffusion (note 03 conditions, reproduced)", diff)

    jump = run(jump_prob=0.01, jump_size=0.50)
    show("E2 - same setup, plus jumps (1% of steps, size 0.50)", jump)

    print("\n" + "-" * 118)
    print(f"{'maker':>12} | {'markout/unit diffusion':>22} | {'markout/unit w/ jumps':>21} | {'change':>9}")
    print("-" * 118)
    for m in ["every_step", "every_10", "every_50"]:
        d, j = diff.loc[m, "markout_per_unit"], jump.loc[m, "markout_per_unit"]
        print(f"{m:>12} | {d:>22.4f} | {j:>21.4f} | {j - d:>+9.4f}")
    print("-" * 118)

    spread_d = diff.loc["every_50", "markout_per_unit"] - diff.loc["every_step", "markout_per_unit"]
    spread_j = jump.loc["every_50", "markout_per_unit"] - jump.loc["every_step", "markout_per_unit"]
    print(f"\nstale-minus-fresh markout gap, diffusion : {spread_d:+.4f}")
    print(f"stale-minus-fresh markout gap, with jumps: {spread_j:+.4f}")
    print("\nIf the second is materially more negative than the first, the note 03\n"
          "explanation was right: staleness is only expensive when prices gap.")

    # ---- F: fees ----
    print("\n\nEXPERIMENT F - maker rebates")
    rows = []
    for rebate in [0.0, 0.005, 0.01, 0.02]:
        r = run(jump_prob=0.01, jump_size=0.50, fees=Fees(maker_rebate=rebate))
        for m in r.index:
            rows.append({"rebate": rebate, "maker": m,
                         "total_pnl": r.loc[m, "total_pnl"],
                         "units": r.loc[m, "units"]})
    f = pd.DataFrame(rows).pivot(index="rebate", columns="maker", values="total_pnl")
    u = pd.DataFrame(rows).pivot(index="rebate", columns="maker", values="units")
    print("\ntotal PnL by rebate level:")
    print(f.to_string(float_format=lambda x: f"{x:10.2f}"))
    print("\nunits traded (unchanged by rebate - the rebate does not alter behaviour here):")
    print(u.to_string(float_format=lambda x: f"{x:10.0f}"))

    print("\nThe rebate is paid per unit resting-side filled, so it scales with volume,\n"
          "not with edge. That is precisely why it changes who is profitable: the\n"
          "high-volume maker collects the most rebate regardless of whether its\n"
          "fills were any good. A strategy that is only viable at a given rebate\n"
          "tier is a strategy whose edge is the rebate.")


if __name__ == "__main__":
    main()
