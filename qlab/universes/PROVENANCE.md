# Provenance — `sp500_removals.csv`

## What this file is

`sp500_removals.csv` lists 105 S&P 500 constituent removals between 2020-04-06
and 2026-05-07, as `removal_date, ticker`. `removed_with_data.csv` is the subset
of 57 for which the free price source still returns history; `universe.py`
defaults to that subset and `reports/note_06_survivorship.md` quantifies what the
other 48 cost you.

## Where it came from

The removal record was compiled in August 2026 from the **S&P 500
constituent-changes table on the English Wikipedia article *List of S&P 500
companies***. That attribution was recorded at the time, in the footer of
`reports/note_06_survivorship.md`.

There is a complication: **that table no longer exists.** It has since been
removed from the article, which now carries only the current constituent list.
The source cannot be re-opened and the file cannot be regenerated from it.

A citation that points at something nobody can look at is weak. So the file was
checked against an independent reconstruction built from a source that cannot
disappear the same way.

## The independent check

`build_removals.py` rebuilds a point-in-time constituent series from the
**revision history** of that same article. The changes table is gone, but every
past revision of the page is permanent, so the constituent set on any past date
is still recoverable.
One revision is sampled per month, the constituent set is parsed from the
wikitext, and consecutive months are diffed. Every output row carries the two
Wikipedia revision IDs it was derived from, so any row can be re-checked by
opening those revisions.

Run over 2020-01 .. 2026-09 — 81 monthly samples, constituent count between 501
and 503 in every sample, no month rejected by the parser's sanity or churn
guards — it produced **147 removals**.

Restricted to the window this CSV covers, widened by 45 days on each side to
absorb Wikipedia's edit lag (2020-02-21 .. 2026-06-21), the reconstruction has
136 rows against this file's 105.

## Result

**Every one of the 105 rows appears in the independent reconstruction. Zero rows
in this file are unmatched.** Nothing here is invented, and the recorded
attribution holds up: a list compiled from the article's changes table agrees
with a list rebuilt from the article's revision history, which is what it should
do.

Dates agree, with a consistent and explainable offset. For the 105 matched
tickers, the Wikipedia detection date falls **+15 days median (+16.0 mean)**
after the date in this file:

| offset | count |
|---|---|
| 0–7 days | 11 |
| 8–30 days | 81 |
| 31–90 days | 9 |
| more than 90 days | 0 |
| negative (Wikipedia earlier) | 4 |

That is the shape you expect when this file holds effective or announcement
dates and the reconstruction holds *article-edit* dates. The dates in this file
are the better ones; the reconstruction is the corroboration, not the source.

## Where the two disagree, and why this file is right

The reconstruction has 33 extra rows (31 distinct tickers) inside the comparison
window. Most are **not removals at all** — they are ticker changes, which a
naive set-diff cannot distinguish from a removal. The `same_month_additions`
column makes each pair visible:

| reconstruction says "removed" | entered the same month | what actually happened |
|---|---|---|
| `FB` | `META` | Facebook renamed |
| `ANTM` | `ELV` | Anthem → Elevance |
| `COG` | `CTRA` | Cabot → Coterra |
| `CTL` | `LUMN` | CenturyLink → Lumen |
| `MYL` | `VTRS` | Mylan → Viatris |
| `VIAC` | `PARA` | ViacomCBS → Paramount |
| `WLTW` | `WTW` | Willis Towers Watson |
| `NLOK` | `GEN` | NortonLifeLock → Gen Digital |
| `PKI` | `RVTY` | PerkinElmer → Revvity |
| `FISV` | `FI` | Fiserv |
| `RE` | `EG` | Everest Re |
| `CDAY` | `DAY` | Ceridian → Dayforce |
| `PEAK` | `DOC` | Healthpeak |
| `FLT` | `CPAY` | FleetCor → Corpay |
| `BLL` | `BALL` | Ball Corporation |
| `LB` | `BBWI` | L Brands → Bath & Body Works |
| `MMC` | `MRSH` | Marsh McLennan |
| `BK` | `BNY` | Bank of New York Mellon |
| `PARA` | `PSKY` | Paramount Skydance |
| `UTX`, `ARNC` | `RTX`, `CARR`, `OTIS`, `HWM` | 2020 United Technologies / Arconic restructurings |

`BRK.B` and `BRK-B` account for four further rows: the article's punctuation for
Berkshire's B shares flipped back and forth. Not an index event.

**This file excludes all of these. That is correct behaviour** — treating a
rename as a removal contaminates a survivorship study with names that never
left.

## Known gaps

The check is not a clean bill of health. Two things remain open.

**Possible genuine removals missing from this file.** Four reconstruction rows
have no rename partner and may be real removals this file does not carry:
`VNT` (2021-04), `WRK` (2024-08), `AMTM` (2025-01), `PARA` (2025-09, if the
Skydance transaction is treated as a removal rather than a rename). These have
not been resolved against a primary source.

**Reconstruction artefacts.** `AAA`, `SOLS` and `XEC` (2020-04) appear in the
reconstruction but are parser or transient-edit artefacts, not index events.
They are noted so nobody adds them later thinking they were overlooked.

## Bottom line

This file is corroborated, not merely asserted, and its stated source is
consistent with the corroboration. Its dates are better than the
free reconstruction's, and it is cleaner on ticker renames. It is probably
missing a small number of genuine removals, which — consistent with
`universe.py` — means any survivorship correction built on it is a **lower
bound** on the true bias, never a full correction.

To re-run the check:

    python3 build_removals.py --start 2020-01 --end 2026-09 \
        --out /tmp/removals_wiki.csv --audit /tmp/audit.csv

Revisions are cached, so a second run costs nothing.

---

Source of the cross-check: English Wikipedia, *List of S&P 500 companies*,
revision history. Text licensed CC BY-SA 4.0. Wikipedia is not an authoritative
index source and is used here only as an independent second opinion.
