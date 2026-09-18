# Research Note 02 — Measuring Adverse Selection Without Fooling Yourself

**August 2026 · Batu Dallıağaç**

## Summary

I built a limit order book with price-time priority and ran a market maker against a mix of uninformed and informed order flow, to measure where market-making PnL actually comes from.

The headline number: at the tightest informed-flow setting, the maker's markout is **−0.64 per unit against informed counterparties and +0.59 per unit against uninformed ones.** That gap is adverse selection, and it is the only thing in the simulation that a market maker is really being paid to price.

Getting to that number required discarding two earlier measurements that were wrong. Both failures are documented below, because they are more instructive than the result.

## The engine

`qlab/lob/` implements a limit order book with:

- price priority across levels, FIFO within a level
- aggressive orders walking multiple levels
- limit remainders resting, market remainders cancelled
- self-trade prevention
- depth-weighted microprice

16 correctness tests in `research/03_lob_tests.py` cover matching, priority, cancellation, and two conservation laws — net position across all agents must be zero, and cash must be conserved. Writing the self-trade prevention test surfaced an infinite loop: when every resting order at the best level belonged to the incoming order's own agent, the matcher skipped them all, restored them, and re-entered the same level forever. Found by the test, not by reading the code.

The cast of agents: a **noise trader** submitting random market orders, an **informed trader** that observes the true fair value and only lifts quotes mispriced by more than its edge, and a **market maker** quoting both sides around its own reference estimate.

## Failure 1 — the market maker could see the future

The first version had the maker quote around `fair` whenever the book was empty. Since the maker cancelled and re-quoted every step, the book was *always* empty at that moment. The maker was therefore quoting around the true fair value at all times.

Consequence: its quotes were never mispriced, so the informed trader never traded. Experiment B produced byte-identical results at every informed-flow intensity from 0% to 70%. The tell was not a subtle statistical anomaly — it was six identical rows.

Fix: the maker now carries its own reference, updated by an EWMA of observed prints. It never sees `fair`.

## Failure 2 — a confounded instrument

With the maker no longer cheating, I measured adverse selection as "total PnL falls when informed intensity rises."

It didn't fall. It rose slightly, from 1134 to 1165.

That is a real effect, not a bug: informed order flow drags the maker's reference price toward fair value. Without it, the maker's reference random-walks on noise prints and goes stale. Informed flow extracts value on each fill and supplies price discovery on each print, and at these parameters the second effect was the larger one.

So the measurement was confounded. "PnL versus informed intensity" cannot isolate adverse selection because informed intensity moves two things at once.

## The clean instrument: markout

For each maker fill, compare the traded price to the true fair value *k* steps later, signed by the direction the maker traded:

```
markout = (fair[t + k] − fill_price) × signed_qty
```

Negative means the price moved against the maker after it traded — it was picked off. Because markout is computed per fill and can be grouped by counterparty, it separates adverse selection from inventory drift, reference staleness, and spread capture.

## Results

5 seeds × 4,000 steps, markout horizon 200 steps.

Adverse selection isolated (half-spread 0.20, no inventory skew):

| Informed intensity | Total PnL | Spread capture | Markout vs informed | Markout vs noise |
|---|---|---|---|---|
| 0.0 | 1133.9 | 1136.7 | — | +0.197 |
| 0.1 | 1157.8 | 1112.0 | −0.619 | +0.300 |
| 0.3 | 1161.1 | 997.8 | −0.655 | +0.445 |
| 0.5 | 1165.5 | 949.1 | −0.645 | +0.518 |
| 0.7 | 1164.5 | 904.1 | −0.639 | +0.586 |

Markout against informed flow is negative at every setting and stable around −0.64. Markout against uninformed flow is positive at every setting. The sign separation is the finding.

Note the third column: **spread capture is positive in every configuration**, and it declines monotonically as informed flow rises. A maker can earn its quoted spread on every single fill and still lose money — which is why "we captured the spread" is not evidence of a working strategy.

Quoting parameters, all at 30% informed intensity:

| Half-spread | Skew | Total PnL | Inventory PnL | Inv. vol | Markout vs informed |
|---|---|---|---|---|---|
| 0.20 | 0.00 | 1161.1 | +163.3 | 16.8 | −0.655 |
| 0.20 | 0.01 | 999.8 | −397.9 | 14.2 | −0.149 |
| 0.10 | 0.00 | 568.1 | +72.9 | 18.2 | −0.727 |
| 0.20 | 0.05 | 333.4 | −1230.0 | 8.5 | −0.417 |
| 0.02 | 0.05 | −1136.4 | −1317.1 | 8.2 | −0.388 |

Inventory skew does what it is designed to do: it cuts inventory volatility from ~19 to ~8 and cuts adverse selection roughly four-fold, from −0.65 to −0.15 per unit. It also destroys total PnL, because leaning quotes to flatten inventory means systematically quoting away from where the flow is.

That trade-off — less adverse selection, worse fills — is the actual decision a market-making desk makes, and it is not resolvable in the abstract.

## Caveats

The fair value is a driftless Gaussian random walk and the informed trader observes it perfectly. Real informed flow is noisier and slower. The maker is the only liquidity provider, so it never competes for queue position, which is a large omission — queue priority is a first-order concern in real venues. There are no fees, no latency, and no partial information decay.

None of these are fixable by tuning; they need a richer simulation. What the current setup does support is the methodological claim: measure adverse selection with markouts by counterparty, not with aggregate PnL.

## Next

1. Multiple competing makers, so queue position matters.
2. Latency between quote decision and book arrival.
3. Fee tiers — maker rebates change the sign of marginal fills.

---

*Code: `qlab/lob/` — book, agents, exchange. Tests: `research/03_lob_tests.py` (16 checks). Experiments: `research/04_market_making.py`.*
