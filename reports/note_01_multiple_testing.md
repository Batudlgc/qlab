# Research Note 01 — When a Sharpe of 0.91 Is Worth Nothing

**August 2026 · Batu Dallıağaç**

## Summary

I ran a 66-configuration parameter sweep over three standard equity signal families on 24 US large caps, 2013–2023, using walk-forward out-of-sample evaluation net of transaction costs.

The best configuration produced an out-of-sample Sharpe of **0.91**. Its Probabilistic Sharpe Ratio — the probability the true Sharpe exceeds zero — was **0.988**. On the face of it, a strong result.

After correcting for the fact that it was the best of 66 attempts, the Deflated Sharpe Ratio fell to **0.052**.

The result is selection bias. There is no edge here. This note documents why, because the correction is the part most student backtests omit.

## Setup

| | |
|---|---|
| Universe | 24 US large caps, liquid, survivorship-biased by construction |
| Research window | 2013-01-02 → 2023-11-06 |
| Holdout | 2023-11-07 → 2026-07-30, **not evaluated** |
| Validation | 6 walk-forward folds, 4y train / 1y test, 10-day embargo |
| Costs | 4 bps per side (1 commission + 2 spread + 1 slippage) |
| Portfolio | Dollar-neutral long/short, unit gross exposure |

Signal families: cross-sectional momentum (skip-21), short-term reversal, and inverse realised volatility. Grid over lookback {21, 63, 126, 252}, top-N {3, 5, 8}, rebalance {weekly, monthly}.

## Results

Top configurations, ranked by out-of-sample Sharpe:

| Family | Lookback | Top-N | Rebal | OOS Sharpe | Max DD | Ann. turnover |
|---|---|---|---|---|---|---|
| momentum | 126 | 3 | monthly | 0.910 | −25.9% | 7.4× |
| momentum | 126 | 5 | monthly | 0.864 | −22.9% | 7.0× |
| momentum | 126 | 8 | monthly | 0.855 | −25.0% | 6.4× |
| momentum | 252 | 8 | weekly | 0.839 | −28.7% | 9.2× |

Bottom configurations:

| Family | Lookback | Top-N | Rebal | OOS Sharpe | Max DD |
|---|---|---|---|---|---|
| lowvol | 63 | 3 | monthly | −0.893 | −91.8% |
| reversal | 252 | 8 | weekly | −0.901 | −81.2% |
| lowvol | 63 | 3 | weekly | −0.978 | −93.6% |

**Median OOS Sharpe across all 66 configurations: −0.63. Cross-sectional standard deviation: 0.66.**

That dispersion is the whole story. When your trials scatter with a standard deviation of 0.66, drawing a 0.91 from 66 attempts is close to what you would expect from noise alone.

## The correction

The Deflated Sharpe Ratio (Bailey & López de Prado, 2014) asks: given that I selected the maximum from N trials whose Sharpes have dispersion σ, what is the probability the winner's true Sharpe exceeds the expected maximum of N draws from a zero-skill distribution?

| Metric | Value | What it assumes |
|---|---|---|
| PSR | 0.988 | This was the only strategy tested |
| DSR | 0.052 | This was the best of 66 tested |

The gap between those two numbers is the cost of searching. Reporting the first while having done the second is not a modelling error; it is a reporting failure.

## What this rules out, and what it doesn't

**Ruled out:** that any single configuration in this grid has a demonstrable edge on this universe over this period, net of costs.

**Not ruled out:** that momentum works. The consistency of the top of the table — every one of the top eight is a momentum variant, and the sign is stable across lookbacks and rebalance frequencies — is itself weak evidence, and consistent with the published cross-sectional momentum literature. But "the family has a positive tilt" is a much weaker claim than "this configuration is tradeable", and only the second one would justify capital.

**A caveat I cannot remove:** the universe is survivorship-biased. It consists of companies that are large today. Any long-side result is inflated by that. The dollar-neutral construction mitigates but does not eliminate it. Fixing this requires point-in-time index constituents, which I do not currently have.

## Method note

Every one of the 66 configurations was written to an append-only research log at the moment it was run, including the failures. The trial count fed into the DSR calculation comes from that log, not from memory.

This matters. The multiple-testing correction is only meaningful if the denominator is honest, and the temptation to forget the strategies that did not work is exactly what the log exists to defeat.

## Next

1. Point-in-time universe construction to remove survivorship bias.
2. A limit order book simulator — a different problem class from cross-sectional alpha, and the one that market-making competitions actually test.
3. Signals with an economic mechanism behind them rather than price transformations, so that the hypothesis is falsifiable before the backtest rather than after.

---

*Code: `qlab/` — data, signals, backtest, validation, research_log. Engine sanity checks in `research/00_sanity_checks.py` verify absence of lookahead bias: a perfect-foresight signal yields Sharpe 65.5, a same-bar signal yields −0.52.*

*References: Bailey, D. & López de Prado, M. (2014), "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality", Journal of Portfolio Management. López de Prado, M. (2018), Advances in Financial Machine Learning, ch. 7.*
