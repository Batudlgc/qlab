# Research Note 07 — The Same Discipline, The Opposite Answer

**August 2026 · Batu Dallıağaç**

## Summary

This note covers a local practice harness for IMC Prosperity-style algorithmic rounds, and then does something the rest of the repository has not yet done: applies the note 01 selection-bias machinery to a case where **the edge turns out to be real**.

In note 01 a 66-configuration sweep produced a best out-of-sample Sharpe of 0.91 that deflated to 0.052. Nothing survived. Here a 48-configuration sweep produces a champion that loses only **4.7%** of its tuning performance out of sample, beats the median configuration by more than one standard deviation, and stays profitable across four market regimes it was not tuned on.

That contrast is the point. A validation procedure that rejects everything is not rigour, it is pessimism. The value of the discipline is that it distinguishes.

## The harness

`qlab/prosperity/` reimplements the Prosperity strategy interface — **unofficially**, from the public format description, and it has not been validated against IMC's engine. It should be re-checked against the official wiki when Prosperity 5 opens.

The contract:

```python
class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        return orders, conversions, trader_data
```

`trader_data` is a string round-tripped between timestamps — the only state a strategy may carry. That is a real constraint and the `MeanReversion` baseline is written to respect it, serialising its rolling window to JSON every tick.

What the engine enforces:

- **Position limits per product**, checked against worst-case exposure of all outstanding orders. An order that *could* breach the limit is rejected outright, not silently clipped.
- **Marketable orders** fill immediately against resting depth.
- **Non-marketable orders rest** and are filled either by the next tick's book moving through them, or by bot market orders sweeping them. Without this a market maker gets no fills at all — the first version of the engine treated every order as immediate-or-cancel and the baseline maker traded 23 times in 1,500 ticks.
- **A fraction of bot flow is informed**, trading in the direction the fair value is about to move. This is what makes passive fills adversely selected.
- **A strategy that raises is recorded as an error**, not swallowed.

Nine tests in `research/09_prosperity_tests.py`. The two that matter most:

| Test | Result |
|---|---|
| Crossing the spread every tick | −13,665 — paying the spread must cost |
| Maker vs 0% informed flow | +2,970 |
| Maker vs 100% informed flow | −120 |

If the last two had not separated, the harness would be a machine for generating fake profits.

## Selection, done properly

**Baselines** on the tuning regime, 8 seeds × 1,500 ticks:

| Strategy | Mean PnL | SD | Worst seed | t |
|---|---|---|---|---|
| DoNothing | 0 | 0 | 0 | — |
| MarketMaker (default) | 2,117.9 | 605.5 | 1,239 | 9.89 |
| MeanReversion | −2,123.4 | 501.9 | −2,832 | −11.97 |

Mean reversion loses reliably. Its t-statistic of −11.97 is as informative as a positive one would be: it is not noise, the strategy is genuinely wrong for this market.

**Sweep**, 48 configurations over edge × size × skew, every one written to the research log:

| Edge | Size | Skew | Mean PnL | SD | Worst seed | t |
|---|---|---|---|---|---|---|
| 2 | 12 | 1.0 | **2,968** | 520 | 2,228 | 16.16 |
| 2 | 8 | 0.5 | 2,965 | 582 | 1,975 | 14.41 |
| 2 | 16 | 0.5 | 2,962 | 586 | 1,970 | 14.29 |
| … | | | | | | |
| 1 | 16 | 2.0 | 644 | 332 | 334 | 5.48 |

Dispersion of mean PnL across the 48 configurations: **605**, against a champion value of 2,968. Compare note 01, where trial dispersion was 0.66 against a best Sharpe of 0.91 — dispersion was 72% of the signal there, and 20% of it here.

That ratio is what decides whether a sweep result is real, and it can be computed *before* any out-of-sample test.

**Holdout**, on eight seeds never used for selection:

| | Mean PnL | SD | Worst seed |
|---|---|---|---|
| Champion, tuning seeds | 2,968 | 520 | 2,228 |
| Champion, holdout seeds | 2,830 | 545 | 1,948 |
| Median configuration, holdout | 1,928 | 662 | 1,074 |

Selection decay: **4.7%**. The champion beats the median configuration out of sample by 902, which exceeds one standard deviation, so the parameter choice is doing real work rather than fitting seed noise.

**Regime robustness**, champion on holdout seeds:

| Regime | Mean PnL | SD | Worst seed |
|---|---|---|---|
| calm (σ=0.8, 25% informed) | 4,552 | 432 | 3,926 |
| normal (σ=1.2, 35% informed) | 2,830 | 545 | 1,948 |
| jumpy (σ=1.2, jumps) | 2,057 | 506 | 1,310 |
| toxic (σ=1.2, 70% informed) | 2,274 | 554 | 1,514 |

Profitable in all four, with no negative seed anywhere. Performance halves between the calm and jumpy regimes, which is the honest read: this is a real edge with a real sensitivity, not an edge that only exists under one setting.

## Why this one survived and note 01's did not

Three things separate them, and all three are checkable in advance:

1. **Effect size relative to trial dispersion.** 2,968 against 605 here; 0.91 against 0.66 there.
2. **A mechanism stated before the test.** Market making earns the spread from uninformed flow — a claim that predicts *which* regimes should be worse, and the toxic and jumpy regimes are in fact worse. Note 01's momentum sweep had no such prediction; it searched for whatever scored highest.
3. **Sign consistency.** All 48 configurations here are profitable. In note 01 the median configuration had a Sharpe of −0.63, meaning the winner was drawn from a distribution centred on failure.

The third is the cheapest diagnostic of the three and I had it available in note 01 without using it properly.

## Limits

The market is synthetic. The fair value is a diffusion with optional jumps, the bot flow is Poisson with a fixed informed fraction, and the book is generated around fair value rather than emerging from participants. A strategy that works here has cleared a low bar — a coherent one, but low.

The interface is reconstructed from public description, not from IMC's code. Field semantics may differ. The `conversions` return value is accepted and ignored, since conversion mechanics vary by round.

And Prosperity rounds include manual challenges worth roughly half the score, which this addresses not at all.

---

*Code: `qlab/prosperity/` — datamodel, market, engine, traders. Tests: `research/09_prosperity_tests.py` (9 checks). Tournament: `research/10_prosperity_tournament.py`.*
