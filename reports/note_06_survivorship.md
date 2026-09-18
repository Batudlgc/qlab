# Research Note 06 — You Cannot Fix Survivorship Bias With Survivorship-Biased Data

**August 2026 · Batu Dallıağaç · revised September 2026**

> **Revision notice.** Re-run in September 2026 against live data. Every figure
> moved slightly and no conclusion changed. The reason the figures moved is
> itself the subject of this note and is recorded in the last section. One bug
> was fixed: `research/08_survivorship.py` called `fillna(method="ffill")`, which
> pandas 3.0 removed, so experiment 2 crashed on any current install. It now
> calls `.ffill()`.

## Summary

Note 01 ended with a caveat I could not remove: the universe consisted of
companies that are large *today*, so any result was inflated by survivorship.
This note goes after that.

Two findings, and the second is more important than the first.

**One.** Survivorship bias is large and easily measured in direction. Companies
removed from the S&P 500 underperformed the index by **−46.23% over the twelve
months before removal** (t = −15.05, n = 56). 96.4% of them underperformed.
Dropping them from a backtest is not a rounding error.

**Two.** The correction cannot be completed with free data. Of 105 S&P 500
removals between April 2020 and May 2026, **only 56 (53.3%) still return enough
price history to measure.** The 49 that do not are not a random sample — they
are disproportionately the acquisitions and the failures. The data source
deletes precisely the observations that create the bias.

Every survivorship correction built on this data is therefore a **lower bound**.
That is worth knowing before quoting one.

## What is missing, and why it matters

The removals with no retrievable history include:

- **Bank failures:** SIVB (Silicon Valley Bank), SBNY (Signature Bank), FRC
  (First Republic) — all three placed into FDIC receivership in March–May 2023.
- **Acquisitions:** TWTR, ATVI, XLNX, PXD, CERN, ANSS, JNPR, ALXN, MXIM, CTXS,
  ABMD, HES, WBA, DFS, KSU, TIF, VAR, FLIR, RTN.
- **Mergers and structural changes:** DISCA, DISCK, INFO, NBL, ETFC, AGN.

Notice the pattern. A company removed for "market capitalisation change" usually
keeps trading under the same ticker, so its history survives in the data. A
company removed because it was **acquired or failed** stops having a ticker, and
the free source drops it.

The observations that vanish are therefore the ones with the most extreme
outcomes — total loss in the receivership cases, and a terminal price jump in
the acquisitions. The residual 53.3% is a *sanitised* sample of removals: the
ones that merely shrank.

So the measured bias below is understated by an unknown but certainly positive
amount.

## Experiment 1 — the run-up to removal

For each removal with sufficient data, total return versus SPY over the window
ending on the removal date:

| Horizon | n | Mean stock return | Mean SPY return | Mean excess | Median excess | % underperforming |
|---|---|---|---|---|---|---|
| 3 months | 56 | −11.94% | +3.07% | **−15.01%** | −16.00% | 82.1% |
| 6 months | 56 | −19.43% | +9.67% | **−29.10%** | −30.46% | 87.5% |
| 12 months | 56 | −27.12% | +19.11% | **−46.23%** | −46.71% | 96.4% |

One-sample t-tests against zero excess return:

| Horizon | Mean excess | t | p |
|---|---|---|---|
| 3m | −0.1501 | −5.87 | < 0.0001 |
| 6m | −0.2910 | −9.09 | < 0.0001 |
| 12m | −0.4623 | −15.05 | < 0.0001 |

At the twelve-month horizon, 54 of 56 names underperformed. This is not a subtle
effect and it does not need a careful test to see; the t-statistic is only there
to make the size of it precise.

The direction is mechanically unsurprising — index removal for market-cap
reasons is close to a definition of having underperformed. What the table gives
is the **magnitude**, which is what determines how much a backtest is flattered
by ignoring these names.

## Experiment 2 — the same strategy on two universes

Cross-sectional 12-month momentum (126-day lookback, 21-day skip), top-5
long/short, monthly rebalance, 4 bps per side, 2019–2026.

- **Survivors only:** 24 current large caps.
- **Survivors plus removed:** the same 24 plus the removed names, each forced to
  zero weight after its removal date. 81 names in total.

| Metric | Survivors only | Survivors + removed | Change |
|---|---|---|---|
| CAGR | 13.84% | 11.02% | **−20.4%** |
| Volatility | 18.14% | 15.59% | −14.1% |
| **Sharpe** | **0.805** | **0.749** | **−7.0%** |
| Sortino | 1.183 | 0.948 | −19.9% |
| Max drawdown | −22.91% | −21.79% | +1.1pp |
| Calmar | 0.604 | 0.506 | −16.3% |
| Hit rate | 47.7% | 47.0% | −0.7pp |

Sharpe falls 7.0% and CAGR falls 20.4% from adding names that a naive universe
silently omits — and again, with the worst 46.7% of removals still missing.

Sortino falls further than Sharpe (−19.9% versus −7.0%), which is the tell: the
added names contribute disproportionately to *downside* deviation. That is what
including losers does.

## What this changes

The 0.91 Sharpe in note 01 was already deflated to 0.052 by the multiple-testing
correction. This note says the raw number was also inflated before that
correction ever ran, by a universe that quietly excluded the companies that
failed.

Two independent biases, in the same direction, stacked. Neither is visible in
the output of a backtest. Both require going outside the backtest to detect.

## The six-week re-run, and what it demonstrated

The August version of this note reported n = 57, a twelve-month excess return of
−45.96% and a Sharpe drop of 8.9%. Re-running the identical script in September
gives n = 56, −46.23%, and a Sharpe drop of 7.0%.

The name that dropped out is **LEG** (Leggett & Platt, removed 2021-12-20). It
still appears in the free source, but the source now returns fewer than 260
trading days for it, so it no longer clears the window this experiment requires.
Nothing about the company changed in those six weeks. The data did.

This is the note's own thesis happening to the note. The claim is that a free
data source silently deletes the observations that carry the bias; over six
weeks of doing nothing, it deleted one more, and the measured bias shrank by
roughly two percentage points of Sharpe as a result. The bias did not get
smaller. The ability to see it did.

Two practical consequences:

1. **`removed_with_data.csv` is not a fixed dataset.** It is a snapshot of what
   one source would serve on one day. It should be regenerated, and the count
   reported, on every run rather than trusted as a constant.
2. **A shrinking measured bias is not good news.** If this experiment is re-run
   in a year and reports a smaller number, the correct reading is that more
   names have gone missing, not that survivorship stopped mattering.

## Honest limits of this note

The removal record covers **April 2020 to May 2026 only** — that is as far back
as the source table went, so the 2013–2019 period in note 01 remains
uncorrected.

Additions are not handled: a name is treated as a member for the whole period up
to its removal, which ignores inclusion-timing bias. `qlab/universe.py` accepts
`added_dates` for this, but the dataset is not assembled.

And the central limitation stands: 46.7% of removals are absent, non-randomly,
in the direction that understates the bias. **Properly fixing this requires a
data source with delisted security history** — CRSP, Compustat, or an
equivalent. Until then, every figure in this note is a floor.

---

*Code: `qlab/universe.py`, `qlab/universes/sp500_removals.csv` (105 removals),
`qlab/universes/removed_with_data.csv` (57 listed, 56 usable as of September
2026). Experiment: `research/08_survivorship.py`. Removal record compiled from
the S&P 500 constituent-changes table on Wikipedia, August 2026; that table has
since been removed from the article, so `qlab/universes/build_removals.py`
reconstructs an equivalent series from the article's revision history as a
re-checkable substitute. See `qlab/universes/PROVENANCE.md`.*
