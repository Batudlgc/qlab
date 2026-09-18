# Research Note 04 — Staleness Is Nearly Free Until Prices Gap

**August 2026 · Batu Dallıağaç · revised September 2026**

> **Revision notice.** The August version of this note reported a
> stale-minus-fresh markout gap of **+0.0069 under diffusion**, and concluded
> that the least-frequently-requoting maker was marginally *better* off when
> prices do not gap. That is not reproducible from the current code:
> `qlab/lob/exchange.py` and `qlab/lob/agents.py` were modified after this note
> was written and the experiment was never re-run. The diffusion gap is now
> **−0.0084** — slightly negative rather than slightly positive, and in both
> cases indistinguishable from zero next to the jump result. The conclusion
> survives in a cleaner form. Every table below is current output from
> `research/06_staleness_and_fees.py`.

## Summary

Note 03 predicted that a market maker holding stale quotes would be adversely
selected, found no such effect, and reported the null rather than tuning until
it appeared. It offered an explanation: under a pure diffusion, a stale quote
drifts *out* of the market and stops trading, and a quote that never fills
cannot be picked off. Staleness should only be expensive when prices gap.

That explanation is now tested. It holds, and the effect is large.

Adding Poisson jumps to the fair value process — 1% of steps, size 0.50,
nothing else changed — moves the stale-minus-fresh markout gap from **−0.0084 to
−0.0825**. Under diffusion the gap is within noise of zero. With jumps it is ten
times larger and unambiguous.

## E — staleness, with and without jumps

Three makers, identical except requote frequency. Half-spread 0.10, no skew, no
inventory cap. 5 seeds × 4,000 steps.

**E1, pure diffusion:**

| Maker | Requote every | Flow share | Total PnL | Markout/unit |
|---|---|---|---|---|
| every_step | 1 | 45.6% | +190.1 | +0.0561 |
| every_10 | 10 | 39.1% | +150.6 | +0.0352 |
| every_50 | 50 | 15.3% | +60.6 | +0.0477 |

Markout per unit is positive for all three and non-monotonic in requote
frequency. There is no staleness ladder under diffusion.

**E2, same setup plus jumps:**

| Maker | Requote every | Flow share | Total PnL | Markout/unit |
|---|---|---|---|---|
| every_step | 1 | 47.8% | +266.7 | −0.0152 |
| every_10 | 10 | 39.0% | +170.8 | −0.0849 |
| every_50 | 50 | 13.2% | **−0.4** | **−0.0977** |

Change in markout per unit when jumps are introduced:

| Maker | Diffusion | With jumps | Change |
|---|---|---|---|
| every_step | +0.0561 | −0.0152 | −0.0713 |
| every_10 | +0.0352 | −0.0849 | −0.1200 |
| every_50 | +0.0477 | −0.0977 | **−0.1454** |

Every maker is hurt by jumps — that is expected, since a jump is a move nobody's
reference has priced yet. What matters is the ordering, which is now monotonic
and steep: **the stale maker is hurt roughly twice as much as the fresh one**
(−0.1454 against −0.0713). Under diffusion there was no ordering at all.

**Stale-minus-fresh markout gap: −0.0084 under diffusion, −0.0825 with jumps.**

The total-PnL column makes the same point in currency. Under diffusion all three
makers are profitable and `every_50` clears +60.6. Add jumps and `every_50`
lands at −0.4 — it trades a quarter of the volume of the fresh maker and ends
the run flat, having earned a spread on every fill.

The mechanism is now legible. A stale quote under diffusion is usually sitting
outside the current market, harmlessly. A stale quote when the price gaps is
sitting *inside* it, on the wrong side, and gets lifted immediately. Quote
staleness is not a cost you pay continuously; it is a tail exposure.

This also means the risk is badly measured by average markout in calm conditions
— which is the sort of thing that looks fine in a backtest right up until it
doesn't.

## F — maker rebates

Same jump setup, varying the per-unit rebate paid to the resting side:

| Rebate | every_step | every_10 | every_50 |
|---|---|---|---|
| 0.000 | 266.75 | 170.78 | **−0.39** |
| 0.005 | 286.13 | 186.63 | +4.96 |
| 0.010 | 305.51 | 202.47 | +10.31 |
| 0.020 | 344.28 | 234.15 | **+21.01** |

Units traded are identical across all rebate levels — 3,876 / 3,169 / 1,070 —
so the rebate does not change behaviour in this simulation, only the accounting.

That is the point. The rebate is paid per unit filled on the resting side, so it
scales with **volume, not with edge**. `every_50` is the clearest case: at zero
rebate it is a losing strategy, and at 2 bps it is a profitable one, without a
single change to what it does or to the quality of a single fill. Its entire
profit at that tier is the fee arrangement.

A strategy whose viability depends on a rebate tier does not have an edge; it
has a fee arrangement. Both can be worth having, but they should never appear in
the same number.

## Standing gaps

Latency is still not modelled here: a maker's decision reaches the book
instantly, which is the single largest remaining departure from a real venue.
Note 05 takes that up. Nor is there any queue-position-aware quoting logic — the
makers do not decide whether to join a queue based on how long it is.

The informed trader also still observes fair value perfectly. Real informed flow
is noisy and partially wrong, which would reduce measured adverse selection
across the board.

The jump parameters — 1% frequency, size 0.50 — are chosen, not calibrated. The
qualitative result is robust to them in the sense that any process with gaps
will produce the same mechanism, but the *magnitude* of the gap is a function of
those two numbers and should not be quoted as an estimate of anything real.

---

*Code: `qlab/lob/exchange.py` — `fair_value_path`, `Fees`. Experiments:
`research/06_staleness_and_fees.py`. All tables regenerated September 2026;
5 seeds × 4,000 steps.*
