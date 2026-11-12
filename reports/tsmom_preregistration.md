# Pre-registration — Time-Series Momentum on BTC and ETH, Long or Flat

**12 November 2026 · Batu Dallıağaç · written before any return of this strategy was computed**

## Why this test, and why now

Note 08 rejected the sweep / structure-shift / fair-value-gap model. It found two problems. The entries carried no information, and the tight stop made fees cost 0.26–0.80R on every trade. Both point to the same lesson: an intraday strategy on spot fees must have a large edge per trade before it can break even.

Time-series momentum inverts that. It holds a position for days to months, so a 0.2% round trip is small next to the moves it tries to capture. It is also one of the most studied systematic strategies.

The rules, variants, periods, controls and pass bar below are fixed in a commit before any return of this strategy is computed. Later decisions go in the changelog with their date and what had been seen, as in `reports/smc_preregistration.md`.

**What was already known when this was written.** The development data (January 2018 – April 2025) was downloaded for note 08. Its quality was checked, and setup counts, fills and costs of that unrelated strategy were computed on it. No trend signal and no daily return series of BTC or ETH were computed on it. Both authors do know the broad path of crypto prices over these years from general knowledge, such as the 2018 and 2022 bear markets. That knowledge cannot be removed. The lookbacks below are round numbers chosen without reference to it. The random-exposure control and the deflated Sharpe are the defences against it. The holdout (May 2025 – October 2026) has still not been downloaded.

## Prior evidence

The evidence is mixed. It is listed so the prior is on record before the result is.

- **Futures.** Moskowitz, Ooi and Pedersen ([2012, *Journal of Financial Economics* 104(2), 228–250](https://econpapers.repec.org/RePEc:eee:jfinec:v:104:y:2012:i:2:p:228-250)) find 12-month time-series momentum profits positive for every one of 58 futures and forward contracts. The effect persists for one to twelve months and partially reverses after that.
- **Crypto, supportive.**
  - Liu and Tsyvinski ([2021, *Review of Financial Studies* 34(6), 2689–2727](https://econpapers.repec.org/RePEc:oup:rfinst:v:34:y:2021:i:6:p:2689-2727.)) report a strong time-series momentum effect in cryptocurrency.
  - Detzel, Liu, Strauss, Zhou and Zhu ([2021, *Financial Management* 50(1), 107–137](https://ideas.repec.org/a/bla/finmgt/v50y2021i1p107-137.html)) find that price-to-moving-average ratios forecast daily Bitcoin returns in and out of sample. A summary of the working-paper version notes its returns are gross of costs.
  - Huang, Sangiorgi and Urquhart ([SSRN 4825389](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4825389)) report a volume-weighted crypto momentum strategy with a Sharpe ratio of 2.17 in their sample.
- **Crypto, skeptical.**
  - A study of about 15,000 technical rules ([*Annals of Operations Research* 297, 191–220, 2021](https://link.springer.com/content/pdf/10.1007/s10479-019-03357-1.pdf)) reports negative out-of-sample returns and Sharpe ratios. It names Bitcoin possibly the least profitable cryptocurrency out of sample and puts its breakeven transaction cost around 50 bps.
  - A study of simple moving-average rules in Bitcoin ([ScienceDirect, 2024](https://www.sciencedirect.com/science/article/abs/pii/S1059056024003010)) finds no out-of-sample outperformance after realistic costs, although another version of the same work states the opposite.

The prior is that a long-or-flat trend rule on BTC and ETH may reduce drawdowns relative to holding. Whether it adds risk-adjusted return after costs, out of sample, is genuinely uncertain.

## Data

These reuse the files and periods of `reports/smc_preregistration.md`.

- **Source.** Binance spot 1-minute klines for BTCUSDT and ETHUSDT, already on disk for the development period, verified against Binance's checksums. Bars offset from the minute were dropped, as recorded in that changelog.
- **Daily bars.** Built from the 1-minute bars over each UTC calendar day: open is the first open, high the max, low the min, close the last close. A day with fewer than 80% of its minutes is dropped, as before.
- **Periods.**

| Period | Dates (UTC) | Use |
|---|---|---|
| Warm-up | start of archive (17 Aug 2017) – 28 Feb 2018 | signals only |
| Development | 1 Mar 2018 – 30 Apr 2025 | evaluate all variants, choose at most one |
| Embargo | 1 May 2025 – 7 May 2025 | discarded |
| **Holdout** | **8 May 2025 – 31 Oct 2026** | evaluated **once**, at the end |

Evaluation starts on 1 March 2018 because that is the first month in which every variant has its full lookback. The longest lookback is 180 days, and 180 days after 17 August 2017 is 13 February 2018. Starting every variant on the same day matters: if a variant were simply flat before its signal existed, it would get credit for missing whatever happened in those weeks.

## Definitions

All times are UTC. A daily signal is computed from bars that have **closed**. A decision made at the close of day *t* is executed at the open of the first minute of day *t + 1*.

**Signals**, for lookback *L* days:

- **Return sign.** Long if the close of day *t* is above the close *L* calendar days earlier. The earlier close is the last available close at or before that day. Otherwise flat.
- **Moving average.** Long if the close of day *t* is above the simple average of the daily closes of the *L* calendar days ending at *t*, counting the days present. Otherwise flat.

**Position.** Spot only, so long or flat. Each symbol is a separate sleeve that is fully invested when long. There is no leverage, no shorting and no volatility scaling.

**Rebalancing.**
- **Daily:** the position may change at every daily close.
- **Weekly:** it may change only at the close of Sunday, UTC, and is held otherwise.

**Missing data.** If day *t* is missing, or its signal cannot be computed, the position is held unchanged.

**Execution and costs.**
- A switch fills at the open of the first minute of the next day. A buy pays that price plus 2 bps of slippage; a sell gets that price minus 2 bps.
- Each switch is charged the Binance regular-user spot fee of **0.100%** on the traded value. This is the same fee schedule as in note 08.

**Returns.** Each sleeve's daily net return is measured from execution price to execution price, so from first-minute open to first-minute open, minus fees on switch days. The portfolio return is the equal-weight average of the BTC and ETH sleeves' daily returns. Rebalancing between the two sleeves is assumed costless, and that assumption is stated wherever results are reported.

## Pre-registered variants

There are three choices: signal (2 options) × lookback (3) × rebalance (2), which gives **12 variants**. All 12 are run, all 12 are logged to `reports/research_log.jsonl`, and the deflated Sharpe counts all 12.

| Choice | Values |
|---|---|
| Signal | return sign · moving average |
| Lookback *L* | 30 · 90 · 180 days |
| Rebalance | daily · weekly (Sunday close) |

The lookbacks are round numbers near one, three and six months. The 0.100% fee, the 2 bps slippage and the execution timing are fixed. Changing any of them after development results exist creates a new variant, which goes into the changelog and the trial count.

## Benchmarks and controls

- **Buy and hold.** Each sleeve buys at the first execution of the development period and holds, paying one fee. The portfolio is the equal-weight average, as above.
- **Random exposure.** For each variant and symbol, the strategy's run lengths are kept and shuffled: how many days it was long, how many flat, in alternating runs. They are placed in a random order with a random starting state, 1,000 times. This keeps each variant's time in the market and its number of switches, and so its costs, but removes the timing. A trend rule that beats buy and hold only by being flat on average is not timing anything, and this control is what shows that.

## Selection and acceptance

**Metrics** use the portfolio's daily net returns, with Sharpe ratios annualised over 365 days, and the maximum drawdown of the portfolio's equity curve. Per-symbol figures are reported alongside.

**Selection, on development only.** A variant qualifies only if **all** of the following hold over 1 March 2018 – 30 April 2025:

1. Its net Sharpe is above the 95th percentile of its own random-exposure control.
2. Its deflated Sharpe, over 12 trials, is at least 0.95.
3. Its maximum drawdown is smaller than buy and hold's.
4. Its net Sharpe is positive on BTC and on ETH separately.

Among qualifying variants, the one with the highest net Sharpe is chosen. If none qualifies, the strategy has failed, the holdout is not downloaded, and the result is written up as a negative finding.

**Acceptance, on the holdout, evaluated once.** The holdout is 18 months of daily data. That is too short to establish a Sharpe ratio: its standard error is roughly 0.8. So the holdout is a check that the chosen variant has not collapsed, not a second proof. The chosen variant passes only if **all** of the following hold:

1. Its net Sharpe is positive.
2. Its net Sharpe is above the median of its own random-exposure control over the holdout.
3. Its maximum drawdown is no larger than buy and hold's over the holdout.
4. No more than one of the two sleeves has a negative net return.

Failing any one condition means the strategy has failed this test. The holdout is then spent. A pass does not mean trading real money either. It leads to paper trading with frozen rules for at least three months, and whether real money is ever used is Batu's decision.

## Tests to pass before any result is read

All run offline on hand-built or random-walk series:

- **No lookahead.** Truncating the data at any day leaves every earlier position unchanged.
- **Execution timing.** A signal at the close of day *t* changes the position at the open of day *t + 1*, never at day *t*'s own prices.
- **Weekly rebalancing.** The position changes only on Sunday closes.
- **Costs.** Every switch is charged exactly fee plus slippage, and a day without a switch is charged nothing.
- **Missing days.** A missing day holds the position.
- **Control.** It preserves each variant's time in the market and number of switches exactly.
- **No free lunch.** On a driftless random walk, no variant's Sharpe is distinguishable from its random-exposure control.

## What is not tested

- **Shorting, leverage, futures and funding.** This is spot only.
- **Volatility targeting and position sizing.** Each sleeve is fully in or fully out.
- **Other coins, cross-sectional momentum, and combining lookbacks.** Each would be a separate pre-registered test.
- **Market impact.** Sizes are assumed small.

## Changelog

| Date | Change | Counted as new trial? |
|---|---|---|
| 12 Nov 2026 | Initial pre-registration. | — |

---

*Sources are linked in "Prior evidence"; they were read through their abstracts and summaries on 12 November 2026, not in full. Fees: [Binance fee schedule](https://www.binance.com/en/fee/schedule), read 3 November 2026. Data and periods: `reports/smc_preregistration.md`.*
