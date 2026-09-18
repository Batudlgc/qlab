# Research Note 03 — What Two Ticks of Price Improvement Actually Buy

**August 2026 · Batu Dallıağaç · revised September 2026**

> **Revision notice.** The August version of this note opened with the claim that
> "the maker that captured 98% of the flow lost money, while a maker that
> captured 1.9% of it made money." That result is not reproducible from the
> current code. `qlab/lob/exchange.py` and `qlab/lob/agents.py` were modified
> roughly eight hours after this note was first written, and the note was never
> regenerated against them. Every table below is the output of
> `research/05_queue_competition.py` as it stands today. The headline finding has
> changed; the two methodological findings have not. Section E records what
> changed and what it costs the earlier conclusion.

## Summary

Note 02 measured a single market maker, which never competes for queue position.
This note adds competing makers and tests three claims.

The result worth stating first: **two ticks of price improvement take 93% of the
flow, and the maker that wins it earns the most — but gives back 31% of its
spread capture in inventory PnL.** Winning the flow is not free. The cost does
not show up as fewer fills; it shows up as inventory.

## The control failed, and that was the useful part

The first version of this script set inventory skew to 0.01 with an inventory
cap of 50 for every experiment. The control — three identical makers, which
should split flow evenly — came back at 38% / 27% / 35%. (Those numbers are
recorded as observed at the time; the configuration that produced them is no
longer in the script, so they cannot be regenerated. The confound itself is
documented in the script's own module docstring.)

The diagnosis is arithmetic. Skew displaces a maker's quotes by
`skew × inventory`. At full inventory that is 0.01 × 50 = **0.50**, against
half-spreads of 0.08–0.12 and price differences between makers of 0.02. The
inventory term was an order of magnitude larger than the effect being measured.
Random early inventory imbalances fed back into quote placement and compounded.

Re-run today with `skew = 0` and no inventory cap:

| Maker | Flow share | Total PnL | Spread capture | Inventory PnL |
|---|---|---|---|---|
| mm0 | 34.2% | +151.2 | +218.1 | −67.0 |
| mm1 | 33.3% | +154.1 | +212.1 | −58.1 |
| mm2 | 32.5% | +160.0 | +207.6 | −47.5 |

A 1.7 percentage point spread across three identical agents. The engine has no
structural bias in requote ordering. The experiment design had a confound.

The general form of the mistake: **a control parameter set to a
plausible-looking value silently became the dominant variable.** Nothing in the
output flagged it. Only a control experiment with a known expected answer
surfaced it.

All priority experiments below therefore run at `skew = 0`. Skew is examined
separately in experiment D, where it is the variable of interest.

## B — Price priority is close to absolute

Three makers at half-spreads 0.08, 0.10, 0.12, no inventory constraints:

| Maker | Half-spread | Flow share | Total PnL | Spread capture | Inventory PnL |
|---|---|---|---|---|---|
| tight | 0.08 | **93.1%** | **+373.0** | +542.8 | −169.8 |
| mid | 0.10 | 6.9% | +28.8 | +38.6 | −9.8 |
| wide | 0.12 | 0.0% | +0.4 | +0.1 | +0.3 |

Two ticks inside takes essentially all the flow. The makers behind the top of
book are not competing; they are collecting the residual that walks past.

The tight maker earns its quoted spread on every fill — **+542.8 of spread
capture** — and returns **169.8** of it in inventory PnL. Being first in the
queue means being first to absorb whatever the market is about to do, and that
absorption costs roughly a third of gross spread revenue here.

The useful reading is not "top of book wins" or "top of book loses." It is that
**the two components move independently.** Spread capture scales with fill
volume. Inventory PnL scales with how adverse the flow is. A venue, a wider
informed share, or a jumpier price process changes only the second term, and
there is no fill count at which the first term guarantees the sign of the total.
"We are top of book and our fill rate is high" is a statement about market
share; the sign of the PnL is decided elsewhere.

## C — Staleness: the hypothesis did not hold

The prediction was that a maker requoting rarely would keep queue priority but
be punished for stale prices via worse markout against informed flow.

| Maker | Requote every | Flow share | Total PnL | Avg. queue ahead | Markout vs informed |
|---|---|---|---|---|---|
| every_step | 1 | 45.6% | +190.1 | 2.82 | −0.088 |
| every_10 | 10 | 39.1% | +150.6 | 2.90 | −0.128 |
| every_50 | 50 | 15.3% | +60.6 | 4.53 | −0.106 |

Markout against informed flow is flat and non-monotonic across the three:
−0.088, −0.128, −0.106. The middle maker is the worst off and the freshest is
the best off, which is neither the predicted ladder nor its reverse. There is no
ordering here to read.

I am reporting this as a null result rather than tuning the parameters until it
inverts. The likely reason the effect does not appear is that a stale quote is
usually *outside* the current market rather than inside it, so it simply does
not trade — the position that never fills cannot be picked off. Testing the
hypothesis properly needs a fair-value process with jumps, where a stale quote
is left standing on the wrong side of a sudden move. The current driftless
Gaussian walk rarely produces that. **Note 04 runs exactly that test.**

What the table does show is that flow share tracks requote frequency almost
mechanically, and — consistent with experiment B — that PnL tracks flow share
here rather than running against it.

## D — Skew, studied on purpose

Same experiment, inventory cap 50, skew as the variable:

| Maker | Skew | Flow share | Total PnL | Markout/unit | Avg. queue ahead |
|---|---|---|---|---|---|
| skew_0.00 | 0.000 | 28.6% | +47.1 | +0.015 | 1.58 |
| skew_0.002 | 0.002 | 31.0% | −10.9 | −0.006 | 1.64 |
| skew_0.01 | 0.010 | 40.4% | **+71.3** | +0.023 | 1.16 |

With a binding inventory cap, the highest skew produces both the most flow and
the most PnL: it keeps the maker from pinning against the cap and going silent
on one side. The middle setting is the worst of the three on PnL, so this is not
a clean monotonic relationship either — with three points and this dispersion,
the honest claim is that skew at 0.01 beats skew at 0, not that PnL rises in
skew.

The same parameter that ruined the control experiment is useful once it is the
thing being measured rather than an uncontrolled background setting. Both
statements are true simultaneously, which is the point. A parameter is not good
or bad; it is correctly or incorrectly scaled relative to what else is going on.

## E — What the revision changed

The August run of this script produced, for experiment B, a tight maker at 98.0%
flow share and −98.6 total PnL, with +616.6 of spread capture against −715.2 of
inventory PnL. Today the same experiment gives 93.1%, +373.0, +542.8 and −169.8.
Spread capture moved 12%; inventory PnL moved 76% and changed the sign of the
total.

The change is in the matching and agent code, not in this script — both
`exchange.py` and `agents.py` were edited after the August note was written, and
no experiment was re-run afterwards. I have not reconstructed which specific
edit is responsible; the August binaries are not recoverable from the repository
as it stands.

Two things follow, and the second matters more than the first.

**The earlier headline is withdrawn.** "Flow share and profitability are close
to unrelated" was a claim about one engine version and does not survive the
change. What survives is weaker and better supported: winning the flow costs
inventory PnL, and that term is large enough — a third of gross spread revenue
here, more than all of it in the August run — to determine the sign.

**A research note is a snapshot of a codebase, and it decays silently.** Nothing
warned me. The note sat in the repository for six weeks reading as current while
its central number had stopped being true. Everything in this repository about
lookahead, embargoes and deflated Sharpe guards against fooling yourself with
statistics; none of it guards against a report drifting out of sync with the
code beneath it. `research_log.jsonl` records the strategy sweeps, but nothing
records which commit produced a figure in a note.

That gap is now the top open item: every table in every note should be
generated from a script run, tagged with the commit hash that produced it, and
re-checked in CI.

## What is and is not established

**Established here:** price priority dominates queue priority; spread capture
and inventory PnL move independently, and the second is large enough to
determine the sign; inventory skew must be scaled against quoted spread or it
becomes the pricing policy.

**Not established:** that flow share predicts profitability in either direction
— the August and September runs disagree on the sign, which is itself the
reason to distrust the question as posed. Also not established: anything about
latency, exchange fees, or maker rebates. None are modelled here. Note 04 adds
fees; note 05 adds latency.

**Still unresolved as of this note:** the staleness hypothesis, which needs a
jump-diffusion fair value to test honestly.

---

*Code: `qlab/lob/exchange.py` (`simulate_multi`), `qlab/lob/book.py`
(`queue_ahead`, `queue_rank`). Experiments: `research/05_queue_competition.py`.
All tables regenerated September 2026; 5 seeds × 4,000 steps.*
