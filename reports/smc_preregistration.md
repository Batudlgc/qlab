# Pre-registration — A Liquidity-Sweep, Structure-Shift, Fair-Value-Gap Strategy on BTC and ETH

**3 November 2026 · Batu Dallıağaç · written before any of the data below was downloaded**

## Why this document exists

Note 01 found a 0.91 out-of-sample Sharpe that deflated to 0.052 once the 66 attempts behind it were counted. Note 07's champion survived its holdout, but no acceptance threshold had been written down before the holdout was opened. This strategy is tested the other way round. The rules, the variants, the test periods and the bar a result has to clear are fixed here, in a commit, before any price is looked at. Anything changed after that is recorded in the changelog at the bottom, with its date, and counted as another trial.

The strategy is the "2022 model" taught by Michael Huddleston (ICT) and described across the smart-money-concepts (SMC) community: liquidity is swept, structure shifts the other way, and price is entered on its return to the fair value gap the shift left behind. There is no authoritative written specification of it. Practitioners disagree on timeframes, on how strict the structure shift must be, and on stop placement. No independently verified track record of it was found. The definitions below are one faithful, mechanical reading of the common core, and the disagreements that matter are kept as pre-registered variants rather than settled by looking at results.

Published mechanical tests found no robust edge on daily bars of equities and ETFs. StatOasis found that 0 of 648 backtests on four US index ETFs beat buy-and-hold. IndicatorEdge found negative average alpha for every SMC family across 738 assets. No published cost-inclusive, out-of-sample test was found for intraday crypto, which is the case tested here. The prior is therefore that this fails, and a pass has to be convincing.

## Data

- **Source.** Binance spot 1-minute klines for **BTCUSDT** and **ETHUSDT**, from the public archive at `data.binance.vision`. The monthly archive runs from August 2017 to October 2026.
- **Clock.** All timestamps are UTC. A bar is labelled by its open time.
- **Resampling.** 5m, 15m, 1h and 4h bars are built from the 1m bars: open is the first open, high the max, low the min, close the last close, and volume the sum. An incomplete higher-timeframe bar is never used.
- **Gaps.** Missing minutes are left missing, not filled. Any resampled bar built from fewer than 80% of its minutes is dropped, and the drops are counted and reported.
- **Periods.**

| Period | Dates (UTC) | Use |
|---|---|---|
| Warm-up | start of archive (August 2017) – 2017-12-31 | indicators only, no trades |
| Development | 2018-01-01 – 2025-04-30 | build, debug, choose one variant |
| Embargo | 2025-05-01 – 2025-05-07 | discarded |
| **Holdout** | **2025-05-08 – 2026-10-31** | evaluated **once**, at the end |

The holdout is not loaded by any script until a variant has been chosen and that choice committed. The loader refuses dates after 2025-04-30 unless it is called with an explicit `holdout=True`.

## Definitions

Each timeframe has its own ATR: Wilder's average true range over 14 bars. "Known at" is the first moment a rule may act on a quantity. All logic below is written for a long setup; a short setup is the mirror image.

**Swing points.** Bar *i* is a swing low if its low is strictly below the lows of the *k* bars before it and the *k* bars after it. Swing highs mirror this. A swing is **known at the close of bar *i + k***, not at bar *i*. This delay is the most common lookahead bug in SMC backtests, and it has its own test. The default is *k* = 3 on both the entry and the bias timeframe.

**Liquidity pools.** Every known swing low is a sell-side pool and every known swing high a buy-side pool. A pool stays active until price trades through it.

**Sweep.** A bullish sweep happens when a bar trades below an active sell-side pool and price then closes back above the pool level within **N = 3** bars, the first such bar included. The sweep extreme is the lowest low between the first bar through the level and the reclaiming close. The sweep is known at that close. A bar that trades through and closes back above in the same bar counts as a sweep.

**Market structure shift (MSS).** After a bullish sweep, the reference level is the most recent swing high that was known when the sweep began. An MSS is the first bar that **closes** above that level within **M = 12** bars of the sweep. A wick through the level does not count. The MSS is known at that close. If no MSS comes within M bars, the sweep is discarded.

**Displacement.** The move from the sweep extreme to the MSS close must contain at least one bar whose body, |close − open|, is at least **1.0 × ATR**. A shift without displacement is discarded.

**Fair value gap (FVG).** Three consecutive bars *j−2*, *j−1*, *j* form a bullish FVG when low[*j*] > high[*j−2*]. The gap spans from high[*j−2*] (the bottom) to low[*j*] (the top). It counts only if it is at least **0.25 × ATR** tall. It is known at the close of bar *j*. Only FVGs whose middle bar *j−1* lies in the displacement leg, from the sweep bar to the MSS bar inclusive, are eligible.

**Bias (higher timeframe).** On the bias timeframe, the bias is bullish if the most recent close beyond a known swing point broke a swing high, and bearish if it broke a swing low. Before the first such break there is no bias and no trades. Only longs are taken under a bullish bias and only shorts under a bearish one. A bias bar's information becomes available on the entry timeframe only after that bias bar has closed.

## The trade

1. **Setup.** Under a bullish bias, a bullish sweep is followed by a bullish MSS with displacement, and at least one eligible FVG exists.
2. **Entry order.** At the close of the MSS bar, place a limit buy at the entry level of the chosen FVG. Its default is the FVG's top, the edge price reaches first. The other variant is its midpoint ("consequent encroachment").
3. **Stop.** Set the stop at the sweep extreme minus **0.1 × ATR**.
4. **Target.** The target variant decides it. Under **opposing liquidity**, the target is the nearest active buy-side pool on the entry timeframe that is at least **2R** above entry, and if none is that far the setup is skipped. Under **fixed 3R**, the target is entry + 3 × (entry − stop).
5. **Expiry.** The order is cancelled if it has not filled within **24** entry-timeframe bars. It is also cancelled if price reaches the target or the stop before the order fills.
6. **One at a time.** There is at most one open position or working order per symbol. A new setup is ignored while one is live.

**Simulated fills.** Fills are simulated on the 1-minute bars inside each entry-timeframe bar, even when signals are computed on 5m or 15m bars.
- **Limit entry.** A limit buy fills only if a later minute trades **strictly below** the limit. Merely touching the limit is not enough, because it would assume a place in the queue that the order might not have.
- **Stop.** The stop is a stop-market order. It fills at the stop price minus **2 bps** of slippage, or at the minute's open if price gapped through.
- **Target.** The target is a resting limit and fills at the target price once a minute trades strictly through it.
- **Same minute.** If one minute could have hit both the stop and the target, the stop is assumed to have hit first. If the minute that fills the entry also reaches the stop, the trade is a loss.

**Costs.** Binance's regular-user spot fee is 0.100% for maker and taker orders alike, or 0.075% when paid in BNB (binance.com fee schedule, read 3 November 2026). The test charges **0.100% per side** with no BNB discount, plus the stop slippage above. A round trip costs at least 0.2%. With a tight stop that is a large share of the risk: on a stop 0.4% away, it is half of 1R before the trade moves. Costs are always deducted. No setup is filtered out because of them, so the cost burden shows in the results instead of being designed out. Results are also reported by cost-to-risk bucket.

**Sizing.** Every trade risks 1R, and results are reported in R net of costs. A notional equity curve that risks 1% of equity per trade is shown for illustration only.

## Pre-registered variants

Four choices are left open. Each takes one of two values, which gives 2 × 2 × 2 × 2 = **16 variants**. All 16 are run, all 16 are logged to `reports/research_log.jsonl`, and the deflated Sharpe counts all 16.

| Choice | Value A | Value B |
|---|---|---|
| Timeframes (entry / bias) | 5m / 1h | 15m / 4h |
| Target | opposing liquidity, ≥ 2R | fixed 3R |
| Entry level | FVG top (proximal edge) | FVG midpoint |
| Session | all hours | Silver Bullet windows only |

When an MSS has more than one eligible FVG, the one that formed **first** is used. This choice is fixed and is not a variant.

Silver Bullet windows mean the FVG must be known inside 03:00–04:00, 10:00–11:00 or 14:00–15:00 New York time, with daylight saving applied. These are ICT's US-session windows. Crypto trades around the clock, so this tests whether the timing claim survives outside the markets it was taught on.

Every other parameter is fixed at the value written above: *k*, N, M, the displacement and FVG size thresholds, the stop buffer, the expiry, the slippage and the fees. These are round numbers chosen before seeing data, not tuned values. Changing any of them after development results exist creates a new variant, which goes into the changelog and into the trial count.

## Controls

- **Random entry, same geometry.** For each real trade, a control trade is placed on the same symbol and in the same direction, with the same stop and target distances in percent and the same costs. Its entry is a uniformly random minute in the same calendar month. This is repeated with 200 seeds. At a risk-to-reward ratio of 1:3, the break-even win rate is 25% before costs and higher after them. This control shows what win rate the geometry produces on its own.
- **Buy and hold** BTC and ETH over the same period, for context only. The strategy is mostly flat, so this is not a pass/fail benchmark.

## Selection and acceptance

**Selection, on development only.** The 16 variants are ranked by mean R per trade over the whole development period, net of costs. Only variants with at least 300 development trades and positive mean R in at least 5 of the 7 full calendar years 2018–2024 qualify. The top qualifying variant is chosen. If none qualifies, the strategy has failed, the holdout is never opened, and the result is written up as a negative finding.

**Acceptance, on the holdout, evaluated once.** The chosen variant passes only if **all** of the following hold:

1. **Enough trades.** There are at least 100 holdout trades across BTC and ETH combined. With fewer, the result is inconclusive, not a pass.
2. **Positive after costs.** Mean R per trade is at least **+0.10R**, and the lower bound of its 95% bootstrap interval (10,000 resamples of trades) is above zero.
3. **Beats its own geometry.** Mean R is above the 95th percentile of the random-entry control's mean R.
4. **Both symbols.** Mean R is positive on BTC and on ETH separately.
5. **Limited decay.** Holdout mean R is at least half of the development mean R.
6. **Survives the search.** The deflated Sharpe of the variant's daily R series over the development period is at least 0.95, with `n_trials` = 16 plus any variants added later.

If any condition fails, the strategy has failed this test. The holdout is then spent: no parameter is retuned on it and no second variant is tried on it. A new idea needs new data, either the months after October 2026 or another market.

**Passing does not mean trading real money.** A pass leads to paper trading on live data for at least three months, with the same rules frozen. Whether real money is ever used is Batu's decision, not an output of this test.

## Lookahead tests, to pass before any result is read

Each runs on small hand-built price series with a known answer:

- **Swing timing.** A swing low is reported at bar *i + k*, never at bar *i*.
- **No future in signals.** Truncating the data at any bar and recomputing gives the same sweeps, MSSs and FVGs up to that bar.
- **Bias timing.** Changing the price of a bias bar that has not yet closed does not change any entry-timeframe decision.
- **No touch fills.** A limit that is touched but never traded through does not fill.
- **Pessimistic minute.** A minute that spans both the stop and the target books a loss.
- **Costs bite.** A strategy that is profitable before costs in a frictionless random walk loses money after them.
- **No free lunch.** On a driftless random walk, every variant's mean R is indistinguishable from the random-entry control.

## What is not tested

- Order blocks, breaker blocks, premium/discount zones, "draw on liquidity" read by a discretionary trader, and news filters. These are part of how ICT is taught but are left out to keep the trial count honest. Each would be a separate pre-registered test.
- Futures, leverage and funding rates. Spot only.
- Market impact. Sizes are assumed small enough not to move the price, so results do not scale indefinitely.

## Changelog

| Date | Change | Counted as new trial? |
|---|---|---|
| 3 Nov 2026 | Initial pre-registration. | — |
| 5 Nov 2026 | Data handling, found while building the development data and before any strategy code exists: two blocks in the Binance archive have bars offset from the minute by a constant (20.799 s, 4–18 Dec 2017; 14.789 s, 9–10 Feb 2018; both symbols). They are dropped and treated as missing minutes rather than floored, which would let a bar carry part of the next minute. The first block lies in the warm-up. | No: no strategy rule or parameter changes. |
| 5 Nov 2026 | Detection details the rules above leave open, fixed while writing `qlab/smc/structure.py` and before any trade or PnL is computed: (1) no pattern spans a data gap, and all state, ATR and bias restart after one; (2) the displacement and FVG thresholds use the ATR of the bar before; (3) when one bar breaches several pools there is one sweep, with the lowest extreme and the highest reclaimed level; (4) the MSS window counts from the bar that confirms the sweep, and that bar may itself be the MSS; (5) a new sweep while an MSS is awaited replaces the pending one; (6) if the first eligible FVG has its middle bar on the MSS bar, the setup becomes known one bar later, when that FVG completes; (7) the bias compares each close with the most recent known swing high and low, and is 0 after a gap until the first break; (8) a higher-timeframe value is usable from the lower-timeframe bar that closes at or after the higher-timeframe bar's close. | No: these fix ambiguities in the written rules; no parameter changes and no results had been seen. |
| 5 Nov 2026 | Simulation details, fixed while writing `qlab/smc/trades.py` and before any PnL was looked at (fill counts and cost-to-risk were checked; returns were not): (1) a limit fills at its price even if the minute opened through it; (2) the order is cancelled if a minute before the fill minute reaches the target or the stop, and in the fill minute the fill takes precedence; (3) a stop gapped through exits at the minute's open with no further slippage, the fill minute included; (4) the stop buffer uses the ATR known at the setup's bar; (5) fees are charged on notional at entry and exit, so a trade costs fee × (entry + exit) / risk in R; (6) "Silver Bullet" means the FVG's completing bar opens inside the window hour, New York time; (7) opposing-liquidity pools are entry-timeframe swings known by the setup's bar, in the same data segment, not yet traded through; (8) a position still open when the data ends is closed at the last close; (9) the control enters at the close of a random minute in the month of the real trade's fill, live for all of the next minute, seeded. | No: no parameter changes and no returns seen. |

---

*Sources: ICT model descriptions, [LuxAlgo — Model 2022](https://www.luxalgo.com/library/concept/model-2022/) and [Silver Bullet](https://www.luxalgo.com/library/concept/silver-bullet/). Prior mechanical tests, [StatOasis](https://statoasis.com/overfit/research/ict-backtest-what-survives) and [IndicatorEdge](https://indicatoredge.io/smart-money). Reference implementation of the definitions, [smart-money-concepts](https://github.com/joshyattridge/smart-money-concepts) (MIT). Fees, [Binance fee schedule](https://www.binance.com/en/fee/schedule), read 3 November 2026. Data, [data.binance.vision](https://data.binance.vision).*
