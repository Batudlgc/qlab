"""Strategy selection for a competition round, done with the discipline from note 01.

A competition tempts you to sweep parameters until the leaderboard score looks
good. That is exactly the procedure note 01 showed produces a 0.91 Sharpe out of
noise. So the sweep here is run the same way as a research sweep: every
configuration is logged, and the winner is judged after correcting for how many
were tried.

Also tested: whether the winner survives a market regime it was not tuned on.

Run:  python3 research/10_prosperity_tournament.py
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from qlab import research_log, validation
from qlab.prosperity import ProductSpec, run_trader
from qlab.prosperity.traders import DoNothing, MarketMaker, MeanReversion

pd.set_option("display.width", 165)
TICKS = 1_500
TUNE_SEEDS = list(range(8))
HOLD_SEEDS = list(range(100, 108))     # never used for selection

REGIMES = {
    "calm":      dict(sigma=0.8, bot_informed=0.25, jump_prob=0.0),
    "normal":    dict(sigma=1.2, bot_informed=0.35, jump_prob=0.0),
    "jumpy":     dict(sigma=1.2, bot_informed=0.35, jump_prob=0.01, jump_size=8.0),
    "toxic":     dict(sigma=1.2, bot_informed=0.70, jump_prob=0.0),
}


def specs(regime: str) -> list[ProductSpec]:
    return [ProductSpec("KELP", fair0=10_000, position_limit=20, **REGIMES[regime])]


LIM = {"KELP": 20}


def evaluate(make_trader, regime: str, seeds) -> dict:
    pnls, dds, vols = [], [], []
    for s in seeds:
        r = run_trader(make_trader(), specs(regime), n_ticks=TICKS, seed=s)
        sc = r.score()
        pnls.append(sc["total_pnl"]); dds.append(sc["max_drawdown"]); vols.append(sc["volume"])
    return {"mean_pnl": float(np.mean(pnls)), "sd_pnl": float(np.std(pnls, ddof=1)),
            "worst_seed": float(np.min(pnls)), "mean_dd": float(np.mean(dds)),
            "volume": float(np.mean(vols)),
            "t_stat": float(np.mean(pnls) / (np.std(pnls, ddof=1) / np.sqrt(len(pnls))))
            if np.std(pnls, ddof=1) else float("nan")}


def main() -> None:
    print("=" * 108)
    print("STEP 1 - baselines on the tuning regime")
    print("=" * 108)
    base = {}
    for name, mk in [("DoNothing", lambda: DoNothing()),
                     ("MarketMaker(default)", lambda: MarketMaker(limits=LIM)),
                     ("MeanReversion", lambda: MeanReversion(limits=LIM))]:
        base[name] = evaluate(mk, "normal", TUNE_SEEDS)
    print(pd.DataFrame(base).T.to_string(float_format=lambda x: f"{x:10.2f}"))

    print("\n" + "=" * 108)
    print("STEP 2 - parameter sweep, every configuration logged")
    print("=" * 108)
    grid = list(itertools.product([1, 2, 3], [4, 8, 12, 16], [0.0, 0.5, 1.0, 2.0]))
    rows = []
    for edge, size, skew in grid:
        def mk(e=edge, z=size, k=skew):
            return MarketMaker(edge=e, size=z, max_skew_ticks=k, limits=LIM)
        r = evaluate(mk, "normal", TUNE_SEEDS)
        rows.append({"edge": edge, "size": size, "skew": skew, **r})
        research_log.record("prosperity_mm", {"edge": edge, "size": size, "skew": skew},
                            r, notes="prosperity tuning sweep, regime=normal")
    sw = pd.DataFrame(rows).sort_values("mean_pnl", ascending=False)
    print(f"configurations tested: {len(sw)}\n")
    print(sw.head(6).to_string(index=False, float_format=lambda x: f"{x:10.2f}"))
    print("\nworst 3:")
    print(sw.tail(3).to_string(index=False, float_format=lambda x: f"{x:10.2f}"))

    best = sw.iloc[0]
    b_edge, b_size, b_skew = int(best["edge"]), int(best["size"]), float(best["skew"])
    b_pnl, b_sd = float(best["mean_pnl"]), float(best["sd_pnl"])
    print(f"\nbest on tuning seeds: edge={b_edge} size={b_size} skew={b_skew} "
          f" pnl {b_pnl:.0f} +/- {b_sd:.0f}")
    print(f"dispersion of mean_pnl across the {len(sw)} configs: "
          f"{sw['mean_pnl'].std(ddof=1):.0f}")

    print("\n" + "=" * 108)
    print("STEP 3 - does the winner hold up on seeds it was not selected on?")
    print("=" * 108)
    def champ():
        return MarketMaker(edge=b_edge, size=b_size, max_skew_ticks=b_skew, limits=LIM)
    tune = evaluate(champ, "normal", TUNE_SEEDS)
    hold = evaluate(champ, "normal", HOLD_SEEDS)
    med = sw.iloc[len(sw) // 2]
    m_edge, m_size, m_skew = int(med["edge"]), int(med["size"]), float(med["skew"])
    def median_cfg():
        return MarketMaker(edge=m_edge, size=m_size, max_skew_ticks=m_skew, limits=LIM)
    hold_med = evaluate(median_cfg, "normal", HOLD_SEEDS)

    cmp = pd.DataFrame({"champion_tuning": tune, "champion_holdout": hold,
                        "median_config_holdout": hold_med}).T
    print(cmp.to_string(float_format=lambda x: f"{x:10.2f}"))
    decay = (tune["mean_pnl"] - hold["mean_pnl"]) / abs(tune["mean_pnl"]) * 100
    print(f"\nselection decay: {decay:+.1f}% of tuning PnL lost out of sample")
    print(f"champion beats median config out of sample by "
          f"{hold['mean_pnl'] - hold_med['mean_pnl']:+.0f} "
          f"({'meaningful' if hold['mean_pnl'] - hold_med['mean_pnl'] > hold['sd_pnl'] else 'inside one sd - not meaningful'})")

    print("\n" + "=" * 108)
    print("STEP 4 - regime robustness (champion, holdout seeds)")
    print("=" * 108)
    reg = {r: evaluate(champ, r, HOLD_SEEDS) for r in REGIMES}
    rd = pd.DataFrame(reg).T
    print(rd.to_string(float_format=lambda x: f"{x:10.2f}"))
    losing = rd[rd["mean_pnl"] <= 0].index.tolist()
    print(f"\nregimes where the champion does not make money: "
          f"{losing if losing else 'none'}")
    print("A configuration tuned on one regime and deployed into another is the"
          "\nmost common way a competition entry dies on the day.")

    n = research_log.n_trials()
    print(f"\ntotal configurations in the research log (all projects): {n}")


if __name__ == "__main__":
    main()
