# Research Note 08 — A Pre-Registered Test of Sweeps, Structure Shifts and Fair Value Gaps

**November 2026 · Batu Dallıağaç**

## Summary

The "2022 model" taught by ICT and the smart-money-concepts community says to wait for liquidity to be swept, for structure to shift the other way with displacement, and then to enter on price's return to the fair value gap the shift left behind. Stops sit beyond the swept extreme, and targets sit at opposing liquidity or a multiple of the risk. This note tests that model mechanically on Binance spot BTCUSDT and ETHUSDT, 5- and 15-minute entries, from January 2018 to April 2025.

The rules, 16 variants, the data periods, the controls and the bar for success were committed in `reports/smc_preregistration.md` before any price was downloaded. Every detail decided later was recorded in its changelog before any return was looked at.

**Result: all 16 variants lose money after costs, and none qualifies for the holdout.** The best loses 0.148R per trade. Before costs the variants range from −0.21R to +0.12R per trade, and none of them is significantly above zero. None beats the 95th percentile of a control that enters at random minutes with the same stop and target, and 14 of 16 do worse than that control's average. Under the pre-registration the strategy has failed, and the holdout (May 2025 – October 2026) has not been opened or downloaded.

Notes 01 and 07 showed one search that found nothing and one that found something real. This one adds a third case: a claim that is widely taught and visually persuasive, tested before anyone looked at the data, and rejected.

## What was tested

The definitions are in the pre-registration and in `qlab/smc/structure.py`. In short:

- **Swing:** a bar whose low (or high) is strictly beyond the 3 bars on each side. It becomes known 3 bars later, not at the bar itself.
- **Sweep:** price trades through a known swing and closes back within 3 bars.
- **Market structure shift:** a close beyond the most recent swing high that was known when the sweep began, within 12 bars, with a bar of at least 1 ATR body on the way.
- **Fair value gap:** the first one of at least 0.25 ATR whose middle bar lies on that leg.
- **Bias:** trades are taken only in the direction of the last structure break on the higher timeframe, read only after that timeframe's bar has closed.

The orders are as follows:

- **Entry:** a limit at the gap's proximal edge or its midpoint, cancelled after 24 bars.
- **Stop:** 0.1 ATR beyond the swept extreme.
- **Target:** the nearest active opposing pool at least 2R away, or a fixed 3R.

Four choices with two values each give the 16 variants:

- Timeframes: 5m entry with 1h bias, or 15m with 4h.
- Target: opposing liquidity or 3R.
- Entry: proximal edge or midpoint.
- Session: all hours, or only ICT's Silver Bullet hours in New York time.

Fills are simulated on 1-minute bars and resolved pessimistically:

- A limit fills only when price trades through it, never on a touch.
- A minute that spans both stop and target books the stop.
- A target touched in the minute of the fill does not count.

Costs are Binance's regular-user spot fee of 0.100% per side, plus 2 bps of slippage on stops.

## Results

Development period, 2018-01-01 to 2025-04-30, BTCUSDT and ETHUSDT together. R per trade is net of costs unless marked gross.

| Variant | Trades | Net R | se | Gross R | Cost R | Win | Years + | Control | Control p95 |
|---|---|---|---|---|---|---|---|---|---|
| 15m/4h 3R proximal silver | 267 | −0.148 | 0.112 | +0.120 | 0.267 | 28.5% | 2 | −0.159 | +0.003 |
| 15m/4h 3R mid silver | 229 | −0.204 | 0.120 | +0.097 | 0.300 | 27.9% | 3 | −0.233 | −0.028 |
| 15m/4h 3R proximal all | 1,365 | −0.247 | 0.048 | +0.008 | 0.255 | 25.7% | 0 | −0.174 | −0.099 |
| 15m/4h 3R mid all | 1,208 | −0.280 | 0.051 | +0.018 | 0.298 | 26.0% | 0 | −0.238 | −0.153 |
| 15m/4h liquidity proximal silver | 243 | −0.345 | 0.129 | +0.009 | 0.354 | 27.6% | 2 | −0.261 | −0.066 |
| 15m/4h liquidity mid silver | 219 | −0.347 | 0.134 | +0.016 | 0.363 | 26.0% | 2 | −0.299 | −0.054 |
| 15m/4h liquidity proximal all | 1,249 | −0.369 | 0.051 | −0.067 | 0.302 | 25.7% | 0 | −0.256 | −0.159 |
| 15m/4h liquidity mid all | 1,161 | −0.386 | 0.056 | −0.019 | 0.367 | 26.2% | 0 | −0.320 | −0.228 |
| 5m/1h 3R proximal all | 4,140 | −0.587 | 0.028 | −0.053 | 0.534 | 24.6% | 0 | −0.540 | −0.498 |
| 5m/1h 3R proximal silver | 580 | −0.628 | 0.075 | −0.110 | 0.518 | 23.1% | 0 | −0.519 | −0.391 |
| 5m/1h 3R mid all | 3,546 | −0.671 | 0.031 | −0.055 | 0.616 | 24.6% | 0 | −0.630 | −0.581 |
| 5m/1h liquidity proximal all | 4,087 | −0.697 | 0.054 | −0.069 | 0.628 | 25.0% | 0 | −0.637 | −0.594 |
| 5m/1h 3R mid silver | 485 | −0.741 | 0.083 | −0.148 | 0.593 | 22.5% | 0 | −0.606 | −0.481 |
| 5m/1h liquidity mid all | 3,633 | −0.810 | 0.048 | −0.081 | 0.729 | 23.9% | 0 | −0.749 | −0.700 |
| 5m/1h liquidity mid silver | 482 | −0.864 | 0.085 | −0.198 | 0.666 | 22.4% | 0 | −0.694 | −0.545 |
| 5m/1h liquidity proximal silver | 559 | −1.005 | 0.283 | −0.206 | 0.799 | 23.3% | 0 | −0.780 | −0.687 |

"Years +" counts the calendar years 2018–2024 in which the variant's mean R was positive. "Control" is the mean, over 200 seeds, of the same trades replayed from random minutes in the same month with the same geometry and costs. The deflated Sharpe over 16 trials is 0.000 for every variant.

To qualify for the holdout, a variant needed at least 300 trades and positive mean R in at least 5 of the 7 years. The most any variant managed was 3 years, and every 5-minute variant lost money in every year. No variant came close to the acceptance bar itself, which required a holdout mean of at least +0.10R per trade.

## Three findings

**1. The entries carry no information.** Gross of costs, the best variant earns +0.120R per trade, against a standard error of about 0.11. The eight all-hours variants, which have the most trades, sit between −0.081R and +0.018R. Where a variant does differ from zero before costs, it differs on the negative side. A setup that predicted direction would show up here, before costs, and it does not. The control makes the same point from the other side. Taking the same stop and target at a random minute does as well or better: the strategy is above its control's mean in only 2 of 16 variants, and never above its 95th percentile. The sweep, the shift and the gap time the entry no better than chance.

**2. The tight stop the model calls for is what makes it expensive.** A stop just beyond the swept extreme is close to the entry, and fees are charged on the whole position. On 5-minute entries, fees and slippage take 0.52–0.80R of every trade on average; on 15-minute entries, 0.26–0.37R. A tight stop does not lower the cost of being wrong. It raises the cost of every trade as a share of what is risked, so a strategy with no gross edge loses roughly its cost per trade.

**3. Wider stops do not rescue it.** One might hope that trades with wider stops, where costs are a small share of risk, hide an edge that costs drown elsewhere. They do not. Pooling all variants' trades by cost-to-risk, the cheapest bucket, under 0.10R of cost, is negative before costs on both timeframes, and on 5-minute entries it is the worst of all:

| Cost bucket | 5m/1h trades | Gross R | 15m/4h trades | Gross R |
|---|---|---|---|---|
| < 0.10R | 381 | −0.225 | 753 | −0.152 |
| 0.10–0.25R | 3,241 | −0.039 | 2,694 | +0.029 |
| 0.25–0.50R | 6,156 | −0.044 | 1,718 | +0.015 |
| 0.50–1.00R | 5,276 | −0.105 | 613 | +0.066 |
| ≥ 1.00R | 2,458 | −0.124 | 163 | −0.276 |

No bucket shows a positive gross edge; the buckets that differ from zero differ on the negative side. A trade appears once for each variant that takes it, so the pooled buckets overlap and their standard errors (in `reports/output/16_smc_cost_buckets.txt`) are too small. The sign pattern is the finding, not the precision. This breakdown was pre-registered as a report, not as a selection criterion, and nothing was chosen from it.

## What this does not show

The test covers one reading of the model. It is the reading the published descriptions converge on, but it is only one: the definitions, the 16 variants, two liquid crypto pairs, two pairs of timeframes, spot fees and seven years. Discretionary traders add context this leaves out on purpose to keep the trial count honest, such as order blocks, premium and discount zones, news, and judgement about which sweeps "matter". A rule set that encodes that judgement could behave differently. It would have to be written down first, and tested the same way.

The fees are those of an ordinary account. Futures fees, maker rebates or high-volume tiers would cut the cost per trade. They would not create the gross edge that finding 1 shows is missing.

The holdout is still unopened. Any new rule set chosen after seeing these results is a new trial. It goes into the research log and the deflated Sharpe, and only a fresh pre-registration may take it to the holdout.

## Why the process mattered

The first version of the plan already said the prior was that this would fail. What made the failure informative was everything that kept the test from being steered:

- the rules were written down before the data existed on disk;
- the holdout was physically absent;
- every later decision was dated in the changelog with a statement of what had and had not been seen;
- the evaluation was committed before it ran;
- its 16 trials were logged whatever they showed.

Without those, a 3-of-7-year variant with +0.12R gross is exactly the kind of number that invites a few more tweaks until it looks like a strategy.

Along the way, the test suites caught three classes of error before they could reach a result:

- **Archive data:** two blocks of Binance bars offset from the minute by 15–21 seconds.
- **Detection:** a structure shift decided on the next bar's close, and a reference high taken before it was known. Both were injected deliberately and caught.
- **Fills:** limits filled on a touch, targets credited on ties, and targets counted in the fill minute. All were injected and caught.

---

*Pre-registration: `reports/smc_preregistration.md`. Code: `qlab/smc/` (data, structure, trades). Tests: `research/11_smc_data_tests.py`, `research/13_smc_structure_tests.py`, `research/14_smc_trade_tests.py`. Evaluation: `research/15_smc_development.py`, output `reports/output/15_smc_development.txt`; cost breakdown `research/16_smc_cost_buckets.py`, output `reports/output/16_smc_cost_buckets.txt`. Both need the downloaded data and are not re-run in CI. Trials: 16 entries `smc_dev …` in `reports/research_log.jsonl`.*
