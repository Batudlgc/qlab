# qlab

Quantitative research framework built around one principle: **the validation layer matters more than the strategy layer.**

Anyone can produce a backtest with a Sharpe of 2. The hard part is knowing whether it means anything. This repository is built so that self-deception is difficult, and so that when a result *does* survive, the survival means something.

Nothing here is a trading system. The one cross-sectional equity strategy in it is a control, and it fails its own tests.

## Setup

```bash
git clone https://github.com/Batudlgc/qlab.git && cd qlab
pip install -r requirements.txt
```

Python 3.10+. The order-book and competition work needs no market data and runs offline. The two equity experiments download daily bars from Yahoo via `yfinance` on first run and cache them to `data/cache/` as parquet.

Start with the three test suites. They take under a minute and they are what the rest of the repository rests on:

```bash
python3 research/00_sanity_checks.py      # engine cannot see the future      (7 checks)
python3 research/03_lob_tests.py          # order book matches correctly     (16 checks)
python3 research/09_prosperity_tests.py   # competition harness is sound      (9 checks)
```

Expected output is a list of `[PASS]` lines ending in `ALL CHECKS PASSED`. Among them:

```
[PASS] perfect foresight -> huge Sharpe (sharpe=65.5)
[PASS] no free lunch from same-bar signal (sharpe=-0.522)
[PASS] walk-forward embargo respected (7 folds)
[PASS] FIFO within price level (first)
[PASS] cash conserved across agents
[PASS] fully informed flow is not [profitable] (toxic=-120 vs clean=2970)
```

A perfect-foresight signal must produce an absurd Sharpe and a same-bar signal must produce roughly nothing. If either fails, the engine has a lookahead bug and no number below is worth reading.

Then the experiments, in order. `05`–`07` take a few minutes each; `08` and `10` take longer.

```bash
python3 research/01_momentum_baseline.py     python3 research/06_staleness_and_fees.py
python3 research/02_signal_sweep.py          python3 research/07_latency.py
python3 research/04_market_making.py         python3 research/08_survivorship.py
python3 research/05_queue_competition.py     python3 research/10_prosperity_tournament.py
```

Each prints its tables to stdout. The write-ups in `reports/` are those tables plus the reasoning.

## Layout

```
qlab/
  data.py          yfinance + IBKR ingestion, one schema, parquet-cached
  signals.py       signal library; scores in, weights out
  backtest.py      vectorised engine, transaction costs are not optional
  validation.py    walk-forward with embargo, PSR, deflated Sharpe
  universe.py      point-in-time index membership
  universes/       removal record + provenance + rebuild script
  research_log.py  append-only record of every strategy tested
  lob/             limit order book: matching, agents, markout analysis
  prosperity/      competition harness (unofficial IMC Prosperity interface)
research/          numbered experiment scripts
reports/           research notes
```

## Three problem classes

**Cross-sectional alpha** — does this signal predict relative returns, and does the answer survive multiple testing and a point-in-time universe?

**Market microstructure** — where does market-making PnL come from, and who takes it away?

**Competition harness** — a local environment for developing and stress-testing algorithmic trading entries under realistic constraints.

## Method

### Why walk-forward, and why with an embargo

A single train/test split gives one number with no error bar, and a k-fold split on time series leaks the future into the past. `validation.walk_forward()` rolls the window forward, and inserts an **embargo** between each train block and its test block. The embargo is not decoration: with a 126-day lookback, a feature computed on the last training day overlaps the first 126 days of the test set. Without the gap, autocorrelated features and overlapping labels cross the boundary and the test set is no longer out of sample.

### The five rules

1. **Locked holdout.** `validation.lock_holdout()` carves off the last 20% of history. You evaluate it once, at the end. Looking early destroys its value permanently.

2. **Purged walk-forward.** As above. Embargo between train and test.

3. **Costs are mandatory.** `backtest.Costs` defaults to **4 bps per side** — 1 bp commission, 2 bps spread, 1 bp slippage — and is deliberately pessimistic for US large caps. Strategies are evaluated net. A strategy that only works at zero cost does not work. Both gross and net Sharpe are reported so the cost drag is visible rather than buried.

4. **Log every trial, including failures.** `reports/research_log.jsonl` holds 163 entries. An unlogged failure is a lie by omission — it silently shrinks the denominator of every multiple-testing correction you later compute.

5. **Deflate the Sharpe.** `validation.deflated_sharpe(returns, n_trials)` corrects for selection (Bailey & López de Prado, 2014). If you tried 66 strategies, the best one's Sharpe is inflated, and this quantifies by how much.

### Bias controls

| Bias | Control | Where |
|---|---|---|
| Lookahead | weights shifted before returns; perfect-foresight and same-bar tests | `backtest.py`, `research/00_sanity_checks.py` |
| Label/feature leakage | embargoed walk-forward | `validation.walk_forward()` |
| Holdout contamination | single-evaluation locked holdout | `validation.lock_holdout()` |
| Selection / multiple testing | PSR and deflated Sharpe over the logged trial count | `validation.py`, `research_log.py` |
| Survivorship | point-in-time membership from a removal record | `universe.py`, `universes/` |
| Cost optimism | mandatory 4 bps/side, gross and net both reported | `backtest.Costs` |

Two are **not** controlled and are named here rather than left to be found: inclusion-timing bias, and the non-random absence of delisted price history. Both are quantified in note 06.

## Results

Numbers below are the current output of the scripts named, regenerated September 2026. Where a note's figures were produced by an earlier version of the engine, the note carries a revision notice saying so.

| | |
|---|---|
| Momentum sweep, 66 configs (`02`) | best OOS Sharpe **0.910**, median **−0.630**, dispersion **0.659** → deflated Sharpe **0.052**. No edge. |
| Survivorship (`08`) | removed index members underperformed SPY by **−46.2%** over the 12 months before removal (t = −15.05, n = 56); adding them to the universe cuts Sharpe from **0.805 to 0.749** |
| Adverse selection (`04`) | maker markout **−0.639/unit** against informed flow, **+0.586/unit** against uninformed, at 70% informed intensity |
| Price priority (`05`) | two ticks inside takes **93.1%** of flow and **+373** PnL — of which **169.8** of **542.8** gross spread capture is returned as inventory PnL |
| Staleness (`06`) | stale-minus-fresh markout gap **−0.008** under diffusion, **−0.083** with jumps |
| Latency (`07`) | the same maker at the same latency took **59.9%** of flow in one field and **5.0%** in another; no markout ladder survives its own error bars |
| Prosperity sweep, 48 configs (`10`) | champion **2,968** against dispersion **605**; loses **4.7%** out of sample and stays profitable across four regimes |

The first row is the point of the repository. A 0.910 out-of-sample Sharpe looks like a result until you count the 66 attempts it took to find it and the 0.659 dispersion they scattered across; deflated, it is 0.052, which is nothing.

The last row is the control on that control: the same procedure applied where an effect is real does not reject it. A method that rejects everything is not rigour, it is a broken instrument.

## Research notes

- [`note_01_multiple_testing.md`](reports/note_01_multiple_testing.md) — a 0.91 Sharpe that deflates to 0.052 once you count the 66 attempts it took to find it.
- [`note_02_adverse_selection.md`](reports/note_02_adverse_selection.md) — building the order book, and the two measurement failures that preceded a usable number.
- [`note_03_queue_competition.md`](reports/note_03_queue_competition.md) — what two ticks of price improvement buy, and how a plausible-looking control parameter silently became the dominant variable. Revised: the original headline did not survive a change to the engine.
- [`note_04_staleness_and_fees.md`](reports/note_04_staleness_and_fees.md) — the null result from note 03, explained and then confirmed: quote staleness is a tail exposure, not a running cost. Also: a maker that is unprofitable at zero rebate and profitable at 2 bps, having changed nothing.
- [`note_05_latency.md`](reports/note_05_latency.md) — latency is a position relative to competitors, not a quantity with a price. Includes a retracted trend from an earlier draft.
- [`note_06_survivorship.md`](reports/note_06_survivorship.md) — index removals with no retrievable price history are the acquisitions and the failures. The data source deletes exactly the observations that cause the bias — and deleted one more between the August and September runs.
- [`note_07_prosperity_harness.md`](reports/note_07_prosperity_harness.md) — the same selection discipline applied to a case where the edge is real.

Most of the notes document a measurement that was wrong before it was right — an engine that could see the future, a confounded instrument, a control parameter that swamped the effect, a trend read into noise, an order type that never rested, a report that drifted out of sync with its code. In this domain the difference between a result and an artefact is usually a detail in the setup rather than anything visible in the output, so the setup is what the notes are about.

## Known limitations

Stated here rather than left to be discovered.

**This is a baseline, not an edge.** No claim is made that any strategy here makes money. The one equity strategy included is a control that fails its own deflated-Sharpe test. The Sharpe ratios in this repository are benchmarks for a method, not evidence of skill.

**Data.**
- Daily bars from a free source. No corporate-action audit, no point-in-time fundamentals, no intraday data.
- The removal record covers **April 2020 – May 2026 only**; earlier periods are uncorrected. Its source table no longer exists on Wikipedia; `universes/PROVENANCE.md` documents the cross-check that replaced it.
- **46.7% of index removals return no usable price history**, non-randomly — they are the acquisitions and failures. Every survivorship correction here is a lower bound.
- Inclusion-timing bias is not handled. `universe.py` accepts `added_dates`; the dataset is not assembled.

**Simulation.** The order book is a research instrument, not a venue model.
- The informed trader observes fair value **perfectly**. Real informed flow is noisy and partially wrong, so measured adverse selection here is an upper bound.
- Makers do not consider queue length when deciding whether to join a level.
- No fee tiers beyond a flat maker rebate; no exchange-specific matching rules.
- Jump parameters (1% frequency, size 0.50) are chosen, not calibrated. The mechanism is robust to them; the magnitudes are not estimates of anything real.
- Results are 5–10 seeds. Seed dispersion is reported where it matters and is often larger than the effect.

**Competition harness.** `prosperity/` is an **unofficial** reimplementation of the IMC Prosperity interface shape, written from public description. It is not IMC code, is not affiliated with or endorsed by IMC, and has not been validated against their engine. Manual-challenge rounds are not addressed at all.

**Process.** Note 03 was published with figures its own script no longer produced, because the engine changed underneath it and nothing re-ran the experiment. Tables are not yet generated with the commit hash that produced them, and nothing checks them in CI. That is the top open item on this repository's list.

## Reproducing the numbers

Every table in `reports/` is stdout from the script named in that note's footer. Strategy sweeps are additionally recorded in `reports/research_log.jsonl` with parameters and full statistics, which is what the multiple-testing corrections count.

Order-book and competition results are seeded and deterministic — the same command gives the same table. The two equity experiments are not: they pull live data, and as note 06 documents, that data changes.

## Not investment advice

This is a research repository. Nothing in it is investment advice, a recommendation, or an offer of any kind. The strategies here are not deployed, are not intended to be deployed, and are demonstrated failing as often as not. Backtested results are hypothetical and do not represent actual trading.

---

*References: Bailey, D. & López de Prado, M. (2014), "The Deflated Sharpe Ratio", Journal of Portfolio Management. López de Prado, M. (2018), Advances in Financial Machine Learning, ch. 7.*

*Parts of this repository were written with AI assistance. All results were reproduced by running the code before publication; the verification is recorded in the revision notices in `reports/` and in `qlab/universes/PROVENANCE.md`.*
