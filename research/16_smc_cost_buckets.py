"""Development trades of the 16 SMC variants, split by cost-to-risk. Reporting only.

    python3 research/16_smc_cost_buckets.py    # needs the downloaded data

The pre-registration asks for results by cost-to-risk bucket, so the cost burden shows in
the results instead of being designed out. This selects nothing, logs nothing and reads no
holdout data: it re-simulates the same trades as research/15_smc_development.py and groups
them by how much of 1R the fees and slippage took.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from qlab.smc import data, trades as tr

NAME = "16_smc_cost_buckets"
DEV_START = pd.Timestamp("2018-01-01")
BUCKETS = [0, 0.1, 0.25, 0.5, 1.0, np.inf]
LABELS = ["<0.10R", "0.10-0.25R", "0.25-0.50R", "0.50-1.00R", ">=1.00R"]


def main() -> str:
    m1s = {s: data.load(s) for s in data.SYMBOLS}
    preps = {(s, e): tr.prepare(m, e, b) for s, m in m1s.items()
             for e, b in [("5min", "1h"), ("15min", "4h")]}
    rows = []
    for v in tr.VARIANTS:
        for s, m in m1s.items():
            o = tr.plan(preps[(s, v.entry_tf)], v)
            res = tr.simulate(o[o.known >= DEV_START].reset_index(drop=True), m)
            f = res[res.status == "filled"]
            rows.append(f.assign(variant=v.name, tf=f"{v.entry_tf}/{v.bias_tf}", symbol=s))
    t = pd.concat(rows, ignore_index=True)
    t["bucket"] = pd.cut(t.cost_r, BUCKETS, right=False, labels=LABELS)

    lines = []
    say = lambda x="": lines.append(x) or print(x)
    say("Development trades 2018-01-01 .. 2025-04-30, BTCUSDT + ETHUSDT, all 16 variants pooled "
        "by timeframe pair. cost = fees + stop slippage, in R.")
    for tf, g in t.groupby("tf", sort=False):
        say(f"\n{tf}: {len(g):,} trades")
        say(f"{'cost bucket':<12} {'trades':>7} {'gross R':>8} {'se':>6} {'net R':>7} {'win':>6}")
        for b, h in g.groupby("bucket", observed=False):
            if len(h) == 0:
                say(f"{b:<12} {0:>7}")
                continue
            se = h.r_gross.std(ddof=1) / np.sqrt(len(h)) if len(h) > 1 else np.nan
            say(f"{b:<12} {len(h):>7,} {h.r_gross.mean():>+8.3f} {se:>6.3f} "
                f"{h.r_net.mean():>+7.3f} {(h.r_net > 0).mean():>6.1%}")
    say("\nThe same trade appears once per variant that takes it, so buckets pooled across "
        "variants overlap and their standard errors are understated.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    text = main()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from reproduce import header
    stamp = header(NAME).replace("python3 research/reproduce.py",
                                 f"python3 research/{NAME}.py (needs the downloaded data)")
    (Path(__file__).resolve().parent.parent / "reports" / "output" / f"{NAME}.txt").write_text(stamp + text)
