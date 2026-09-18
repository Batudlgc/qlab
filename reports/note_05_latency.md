# Research Note 05 — Latency Is a Position, Not a Quantity

**August 2026 · Batu Dallıağaç**

## Summary

Latency was the largest gap listed at the end of note 04. It is now modelled: a maker's decision at step *t* reaches the book at *t + latency*, and critically the cancel of the old quote is delayed too. A maker that sees the price move and decides to pull its quote is still fillable on it for `latency` steps.

The expected result was a ladder — slower makers progressively more adversely selected. That is not what happened.

**Flow concentrates almost entirely on whichever maker is slowest in the field, and that concentration follows the field rather than the latency.** The identical agent, at latency 20, in the identical market process, took **59.9% of flow in one field and 5.0% in another.** The only thing that changed was who else was competing.

## G1/G2 — the same ladder, two different fields

Ten seeds × 4,000 steps, jumps on, all makers at half-spread 0.10, no skew, no inventory cap. The only difference between makers is latency.

**Field A**, latencies {0, 2, 5, 10, 15, 20} → flow concentrates on **lat_20 at 59.9%**.

**Field B**, the same six makers plus lat_30 and lat_40 → flow concentrates on **lat_40 at 66.4%**, and lat_20 falls to 5.0%.

| Maker (field B) | Flow share | Units | Total PnL | Markout/unit |
|---|---|---|---|---|
| lat_0 | 5.1% | 478 | −320.4 | −0.310 |
| lat_2 | 5.0% | 468 | −186.4 | +0.151 |
| lat_5 | 4.2% | 391 | −236.0 | −0.157 |
| lat_10 | 4.4% | 417 | −224.8 | −0.262 |
| lat_15 | 4.9% | 458 | −256.9 | −0.103 |
| lat_20 | 5.0% | 467 | −254.9 | −0.039 |
| lat_30 | 5.2% | 486 | −215.9 | −0.066 |
| lat_40 | **66.4%** | 6245 | **−4201.8** | −0.524 |

Everyone except the slowest maker sits at roughly one-eighth of the flow. The slowest one absorbs the rest and loses roughly eighteen times as much money as anyone else.

## Why

A lagged quote is priced off a stale reference. Most of the time that puts it *outside* the current market, where it does not trade. Occasionally it puts it *inside* — and that happens precisely when the price has just moved, which is exactly when you do not want to be the best bid.

So the slowest maker is not filled more often because it is more competitive. It is filled more often because its quote is systematically the one left standing in the wrong place. Every faster maker has already moved.

This is the same mechanism as quote staleness in note 04, approached from the other side. Staleness is choosing not to update; latency is being unable to. The order book cannot tell the difference and neither can the markout.

But the mechanism is *comparative*. It requires someone faster to have moved first. In a field where everyone is equally slow, nobody is picked off for being slow.

## G4 — no markout ladder, and I am not going to claim one

Markout per unit, ten seeds, mean ± 1 standard deviation:

| Maker | Markout/unit | SD |
|---|---|---|
| lat_0 | −0.310 | 0.264 |
| lat_2 | +0.151 | 0.666 |
| lat_5 | −0.157 | 0.307 |
| lat_10 | −0.262 | 0.335 |
| lat_15 | −0.103 | 0.410 |
| lat_20 | −0.039 | 0.305 |
| lat_30 | −0.066 | 0.312 |
| lat_40 | −0.524 | 0.384 |

Not one of these clears two standard deviations. The series is not monotonic, and the largest value belongs to lat_0 rather than to any of the slow makers. The only entry that even approaches significance is lat_40, at roughly 1.4 sd.

An earlier version of this experiment used five seeds and a maximum latency of 20, and I wrote a summary line reporting that "markout degrades from −0.28 at zero latency to −0.25 at 20 steps." Both numbers were inside the noise, the direction was not even consistent across the intermediate points, and the sentence described a trend that was not there. It is removed.

As a further check: lag drift is σ√L, which reaches the quoted half-spread of 0.10 at L = 25 steps. If the effect were an absolute threshold, the flow discontinuity should sit near there. It sits at the field maximum in both fields instead — 20 in one, 40 in the other.

## What this does and does not establish

**Establishes:** latency's cost is competitive rather than intrinsic. Being slow is only expensive when someone else is fast, and the penalty falls disproportionately on the single slowest participant rather than being shared along a gradient.

**Does not establish:** any per-step price for latency. Getting that would require a venue model with a fixed exogenous reference population, not a field made entirely of the agents under test. The current design is self-referential — each maker's disadvantage is defined by the others — which is fine for the comparative claim and useless for an absolute one.

**Practical implication, if the mechanism generalises:** the relevant question for a market-making operation is not "what is our latency" but "are we the slowest quote in the book." Those have very different answers and only the second one predicts getting run over.

---

*Code: `qlab/lob/agents.py` (`MarketMaker.latency`), `qlab/lob/exchange.py` (pending-action queue). Experiment: `research/07_latency.py`.*
