"""Market making: separating spread capture from adverse selection.

A first attempt measured adverse selection as "PnL falls when informed flow
rises". That measurement was confounded: informed traders both extract value
from the maker AND supply price discovery it would otherwise lack, and at these
parameters the second effect dominated. Total PnL therefore *rose* with informed
intensity - a real effect, but not the one being tested.

The clean instrument is markout: for each fill, compare the traded price to the
true fair value k steps later, signed by the maker's direction. Negative markout
means the price moved against the maker after it traded. Splitting markout by
counterparty isolates adverse selection from everything else.

Run:  python3 research/04_market_making.py
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from qlab.lob.agents import MarketMaker
from qlab.lob.exchange import simulate

SEEDS = [0, 1, 2, 3, 4]
STEPS = 4_000
HORIZON = 200
pd.set_option("display.width", 170)


def run_many(half_spread, skew, informed_intensity, seeds=SEEDS):
    att, cp = [], []
    for s in seeds:
        res = simulate(n_steps=STEPS, seed=s,
                       mm=MarketMaker(half_spread=half_spread, skew=skew,
                                      size=10, max_inv=50),
                       informed_intensity=informed_intensity)
        att.append(res.attribution())
        g = res.markout_by_counterparty(HORIZON)
        cp.append({f"{k}_{c}": g.loc[c, k]
                   for c in g.index for k in ("markout_per_unit", "units")})
    a, c = pd.DataFrame(att), pd.DataFrame(cp)
    out = {"total_pnl": a["total_pnl"].mean(), "pnl_std": a["total_pnl"].std(ddof=1),
           "spread_capture": a["spread_capture"].mean(),
           "inventory_pnl": a["inventory_pnl"].mean(),
           "inv_vol": a["inventory_vol"].mean()}
    for c_name in ("informed", "noise"):
        col = f"markout_per_unit_{c_name}"
        out[f"mkt_vs_{c_name}"] = c[col].mean() if col in c else float("nan")
        u = f"units_{c_name}"
        out[f"units_{c_name}"] = c[u].mean() if u in c else 0.0
    return out


def main() -> None:
    print("=" * 118)
    print(f"EXPERIMENT A - quoting parameters.  markout horizon = {HORIZON} steps, "
          f"{len(SEEDS)} seeds x {STEPS} steps")
    print("=" * 118)
    rows = [{"half_spread": hs, "skew": sk, **run_many(hs, sk, 0.30)}
            for hs, sk in itertools.product([0.02, 0.05, 0.10, 0.20], [0.0, 0.01, 0.05])]
    a = pd.DataFrame(rows).sort_values("total_pnl", ascending=False)
    print(a.to_string(index=False, float_format=lambda x: f"{x:10.3f}"))

    best = a.iloc[0]
    robust = abs(best["total_pnl"]) > 2 * best["pnl_std"]
    print(f"\nbest: half_spread={best['half_spread']} skew={best['skew']}  "
          f"PnL {best['total_pnl']:.1f} +/- {best['pnl_std']:.1f}  "
          f"-> {'robust across seeds' if robust else 'NOT distinguishable from noise'}")

    print("\n" + "=" * 118)
    print("EXPERIMENT B - adverse selection isolated by markout")
    print("=" * 118)
    rows = [{"informed_intensity": ii,
             **run_many(float(best["half_spread"]), float(best["skew"]), ii)}
            for ii in [0.0, 0.1, 0.3, 0.5, 0.7]]
    b = pd.DataFrame(rows)
    cols = ["informed_intensity", "total_pnl", "spread_capture", "inventory_pnl",
            "mkt_vs_informed", "units_informed", "mkt_vs_noise", "units_noise"]
    print(b[cols].to_string(index=False, float_format=lambda x: f"{x:10.3f}"))

    hi = b[b["informed_intensity"] == 0.7].iloc[0]
    print(f"\nAt 70% informed intensity, per unit traded:")
    print(f"  against informed flow : {hi['mkt_vs_informed']:+.4f}  ({hi['units_informed']:.0f} units)")
    print(f"  against noise flow    : {hi['mkt_vs_noise']:+.4f}  ({hi['units_noise']:.0f} units)")
    ratio = abs(hi["mkt_vs_informed"] / hi["mkt_vs_noise"]) if hi["mkt_vs_noise"] else float("nan")
    print(f"  the informed counterparty costs {ratio:.1f}x more per unit than "
          f"the uninformed one pays")

    print("""
Reading:
  Markout against informed flow is consistently negative and markout against
  noise flow consistently positive. That is adverse selection, measured directly
  and independent of inventory drift or reference-price staleness.

  Total PnL does not fall as informed intensity rises, because informed order
  flow also drags the maker's reference price toward fair value. The maker pays
  for information on every fill and receives it on every print. Whether that
  trade is worth taking is a parameter question, not a universal law - which is
  precisely why it has to be measured rather than assumed.

  Note that spread capture stays positive in every configuration. A maker can be
  earning its quoted spread on every single fill and still lose money.""")


if __name__ == "__main__":
    main()
