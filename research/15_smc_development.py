"""Development-period evaluation of the 16 pre-registered variants. Reads no holdout data.

    python3 -m qlab.smc.data download          # first
    python3 research/15_smc_development.py     # once: logs 16 trials, writes reports/output/

Selection follows reports/smc_preregistration.md: rank the variants by mean R per trade,
net of costs, over 2018-01-01 to 2025-04-30 on BTCUSDT and ETHUSDT together. A variant
qualifies only with at least 300 trades and positive mean R in at least 5 of the 7 full
years 2018-2024. If none qualifies, the strategy has failed and the holdout stays closed.

Run it once. Every variant is appended to reports/research_log.jsonl; a second run finds
those entries and refuses to append them again, so the trial count stays honest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from qlab import research_log, validation
from qlab.smc import data, trades as tr

NAME = "15_smc_development"
LOG_PREFIX = "smc_dev"
DEV_START = pd.Timestamp("2018-01-01")      # before this is warm-up: no trades
YEARS = range(2018, 2025)
MIN_TRADES, MIN_YEARS_POSITIVE = 300, 5
N_TRIALS = 16
SEEDS = 200
PERIODS = 365                               # crypto trades every day


def run_variant(m1s: dict, preps: dict, v: tr.Variant) -> pd.DataFrame:
    out = []
    for sym, m1 in m1s.items():
        orders = tr.plan(preps[(sym, v.entry_tf)], v)
        orders = orders[orders.known >= DEV_START].reset_index(drop=True)
        res = tr.simulate(orders, m1)
        out.append(res.assign(symbol=sym))
    return pd.concat(out, ignore_index=True)


def daily(f: pd.DataFrame, end: pd.Timestamp) -> pd.Series:
    """Net R per calendar day, booked on the exit day, zero on days without exits."""
    days = pd.date_range(DEV_START, end.normalize(), freq="D")
    return f.groupby(f.end.dt.normalize()).r_net.sum().reindex(days, fill_value=0.0)


def summarise(res: pd.DataFrame, m1s: dict) -> dict:
    f = res[res.status == "filled"].sort_values("end")
    r = f.r_net
    years = {y: r[f.end.dt.year == y].mean() for y in YEARS}
    cum = r.cumsum()
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    end = max(m.index[-1] for m in m1s.values())
    ctrl = {}
    for sym, m1 in m1s.items():
        part = res[res.symbol == sym]
        if (part.status == "filled").any():
            ctrl[sym] = ((part.status == "filled").sum(), tr.control(part, m1, seeds=SEEDS))
    n_c = sum(n for n, _ in ctrl.values())
    ctrl_means = sum(n * m for n, m in ctrl.values()) / n_c if n_c else np.full(SEEDS, np.nan)
    return {
        "trades": len(f), "mean_r": r.mean(), "se": r.std(ddof=1) / np.sqrt(len(r)),
        "mean_gross": f.r_gross.mean(), "mean_cost": f.cost_r.mean(),
        "win_rate": (r > 0).mean(), "profit_factor": wins / losses if losses else np.nan,
        "max_dd_r": float((cum.cummax() - cum).max()) if len(r) else np.nan,
        "years": years, "years_positive": sum(m > 0 for m in years.values() if pd.notna(m)),
        "by_symbol": {s: r[f.symbol == s].mean() for s in m1s},
        "control_mean": float(np.nanmean(ctrl_means)), "control_p95": float(np.nanpercentile(ctrl_means, 95)),
        "daily": daily(f, end),
        "status": res.status.value_counts().to_dict(),
    }


def main(m1s: dict, log: bool = True, out: Path | None = None) -> str:
    lines = []
    say = lambda s="": lines.append(s) or print(s)

    preps = {(sym, etf): tr.prepare(m1, etf, btf)
             for sym, m1 in m1s.items() for etf, btf in [("5min", "1h"), ("15min", "4h")]}
    stats = {v: summarise(run_variant(m1s, preps, v), m1s) for v in tr.VARIANTS}

    sharpes = {v: validation.sharpe(s["daily"], PERIODS) for v, s in stats.items()}
    trial_sr_std = np.nanstd(list(sharpes.values()), ddof=1) / np.sqrt(PERIODS)
    for v, s in stats.items():
        s["sharpe"] = sharpes[v]
        s["dsr"] = validation.deflated_sharpe(s["daily"], n_trials=N_TRIALS,
                                              trial_sr_std=trial_sr_std, periods=PERIODS)
        s["qualifies"] = s["trades"] >= MIN_TRADES and s["years_positive"] >= MIN_YEARS_POSITIVE

    say(f"Development {DEV_START.date()} .. {data.DEV_END}, {' + '.join(m1s)}, "
        f"costs {tr.FEE:.3%}/side + {tr.SLIP * 1e4:.0f} bps stop slippage, control {SEEDS} seeds")
    say()
    say(f"{'variant':<34} {'trades':>6} {'mean R':>7} {'se':>5} {'gross':>6} {'cost':>5} {'win':>5} "
        f"{'PF':>5} {'maxDD':>6} {'yrs+':>4} {'ctrl':>6} {'ctrl95':>6} {'Sharpe':>6} {'DSR':>5}  qualifies")
    ranked = sorted(stats.items(), key=lambda kv: -kv[1]["mean_r"])
    for v, s in ranked:
        say(f"{v.name:<34} {s['trades']:>6} {s['mean_r']:>+7.3f} {s['se']:>5.3f} {s['mean_gross']:>+6.3f} "
            f"{s['mean_cost']:>5.3f} {s['win_rate']:>5.1%} {s['profit_factor']:>5.2f} {s['max_dd_r']:>6.1f} "
            f"{s['years_positive']:>4} {s['control_mean']:>+6.3f} {s['control_p95']:>+6.3f} "
            f"{s['sharpe']:>+6.2f} {s['dsr']:>5.3f}  {'yes' if s['qualifies'] else 'no'}")
    say()
    say("mean R by year (2018-2024) and by symbol:")
    for v, s in ranked:
        yrs = " ".join(f"{s['years'][y]:+.2f}" if pd.notna(s['years'][y]) else "  n/a" for y in YEARS)
        sym = " ".join(f"{k[:3]} {m:+.3f}" for k, m in s["by_symbol"].items())
        say(f"{v.name:<34} {yrs}   {sym}")

    say()
    chosen = next((v for v, s in ranked if s["qualifies"]), None)
    if chosen is None:
        say("SELECTION: no variant qualifies (>= 300 trades and positive mean R in >= 5 of 7 years).")
        say("Under the pre-registration the strategy has failed. The holdout is not opened.")
    else:
        s = stats[chosen]
        say(f"SELECTION: {chosen.name}  (mean {s['mean_r']:+.3f}R over {s['trades']} trades, "
            f"positive in {s['years_positive']} of 7 years, DSR {s['dsr']:.3f})")
        say("This is the only variant that may be taken to the holdout, once this output is committed.")

    if log:
        logged = {e["name"] for e in research_log.entries()}
        new = [v for v in tr.VARIANTS if f"{LOG_PREFIX} {v.name}" not in logged]
        if len(new) < len(tr.VARIANTS):
            say(f"\nresearch log: {len(tr.VARIANTS) - len(new)} of 16 variants already logged; "
                f"appending only {len(new)}")
        for v in new:
            s = stats[v]
            research_log.record(
                f"{LOG_PREFIX} {v.name}",
                {"entry_tf": v.entry_tf, "bias_tf": v.bias_tf, "target": v.target,
                 "entry": v.entry, "session": v.session},
                {k: s[k] for k in ("trades", "mean_r", "se", "win_rate", "years_positive",
                                   "sharpe", "dsr", "control_mean", "control_p95")},
                notes="development 2018-01-01..2025-04-30, BTCUSDT+ETHUSDT, net of costs")
        say(f"research log: {research_log.n_trials()} entries")

    text = "\n".join(lines) + "\n"
    if out is not None:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from reproduce import header
        stamp = header(NAME).replace("python3 research/reproduce.py",
                                     f"python3 research/{NAME}.py (needs the downloaded data)")
        out.write_text(stamp + text)
    return text


if __name__ == "__main__":
    m1s = {s: data.load(s) for s in data.SYMBOLS}
    main(m1s, log=True, out=Path(__file__).resolve().parent.parent / "reports" / "output" / f"{NAME}.txt")
