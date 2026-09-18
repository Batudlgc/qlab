"""Reconstruct S&P 500 removals from the revision history of the Wikipedia
article "List of S&P 500 companies".

Why this exists
---------------
A list of index removals is not something you can take on trust. S&P Dow Jones
Indices publishes each change as a press release, but there is no free bulk
endpoint. The Wikipedia article is edited within days of each announcement, so
its revision history is a usable proxy: sample one revision per month, extract
the constituent set, and diff consecutive months. A ticker present in month N
and absent in month N+1 was removed somewhere in between.

What this buys you: every row is traceable to two Wikipedia revision IDs, both
written into the output. The provenance is checkable by anyone.

What it costs you, stated plainly:
  - Dates are DETECTION dates, not effective dates. They lag the real index
    change by however long it took an editor to update the article, typically
    days. Do not use this series for event studies around the announcement.
  - Monthly sampling means a name added and removed inside one month is missed.
  - Ticker changes (a rename, not a removal) show up as one removal plus one
    addition. The `same_month_additions` column lists what entered that month so
    such pairs can be spotted by hand.
  - Wikipedia is not authoritative. Errors in the article become errors here.

Usage
-----
    python3 build_removals.py --start 2020-01 --end 2026-09 --out removals.csv

Revisions are cached under .cache/ so reruns are free.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

API = "https://en.wikipedia.org/w/api.php"
TITLE = "List of S&P 500 companies"
UA = (
    "qlab-research/0.1 (https://github.com/Batudlgc/qlab; dalliagacbatu@gmail.com) "
    "python-urllib"
)
CACHE = Path(__file__).resolve().parent / ".cache" / "wikirevs"


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

def _api(params: dict, tries: int = 6, pause: float = 1.5) -> dict:
    """GET the MediaWiki API with backoff on 429/503."""
    params = {**params, "format": "json", "formatversion": "2", "maxlag": "5"}
    url = API + "?" + urllib.parse.urlencode(params)
    delay = 4.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.loads(r.read())
            if "error" in body and body["error"].get("code") == "maxlag":
                time.sleep(delay)
                delay *= 1.7
                continue
            time.sleep(pause)
            return body
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503):
                time.sleep(delay)
                delay *= 1.7
                continue
            raise
        except urllib.error.URLError:
            time.sleep(delay)
            delay *= 1.7
    raise RuntimeError(f"API refused after {tries} attempts: {url}")


def revision_at(when: date) -> tuple[int, str, str]:
    """First revision at or after `when`. Returns (revid, timestamp, wikitext)."""
    key = CACHE / f"{when.isoformat()}.json"
    if key.exists():
        d = json.loads(key.read_text())
        return d["revid"], d["timestamp"], d["content"]

    body = _api({
        "action": "query", "prop": "revisions", "titles": TITLE,
        "rvstart": f"{when.isoformat()}T00:00:00Z", "rvdir": "newer",
        "rvlimit": 1, "rvprop": "content|ids|timestamp", "rvslots": "main",
    })
    pages = body["query"]["pages"]
    if not pages or "revisions" not in pages[0]:
        raise RuntimeError(f"no revision found at or after {when}")
    rev = pages[0]["revisions"][0]
    out = {
        "revid": rev["revid"],
        "timestamp": rev["timestamp"],
        "content": rev["slots"]["main"]["content"],
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps(out))
    return out["revid"], out["timestamp"], out["content"]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

# The article's first column has used several markups over the years.
_TICKER_PATTERNS = [
    re.compile(r"\{\{\s*(?:Nyse|Nasdaq|Bats|NYSE|NASDAQ|BATS)[A-Za-z]*\s*\|\s*([A-Z][A-Z.\-]{0,6})\s*[|}]"),
    re.compile(r"\[\[(?:NYSE|NASDAQ|Nasdaq|BATS)\s*:\s*([A-Z][A-Z.\-]{0,6})"),
    re.compile(r"\[\[[^\]|]*\|\s*([A-Z][A-Z.\-]{0,6})\s*\]\]"),
    re.compile(r"\[\[\s*([A-Z][A-Z.\-]{0,6})\s*\]\]"),
    re.compile(r"^\s*\|*\s*([A-Z][A-Z.\-]{0,6})\s*$"),
]

# Words that look like tickers but are markup or section noise.
_NOT_TICKERS = {
    "GICS", "CIK", "NYSE", "NASDAQ", "BATS", "SEC", "USA", "US", "UK", "CEO",
    "ETF", "SP", "S", "P", "REIT", "LLC", "INC", "CO", "NA", "TBD",
}


def _constituents_table(wikitext: str) -> str:
    """Slice out the constituents table, tolerating id= and caption variants."""
    m = re.search(r'\{\|[^\n]*id\s*=\s*"?constituents"?', wikitext)
    start = m.start() if m else wikitext.find("{|")
    if start < 0:
        raise RuntimeError("no wikitable found")
    end = wikitext.find("\n|}", start)
    return wikitext[start: end if end > 0 else len(wikitext)]


def tickers(wikitext: str) -> set[str]:
    """Extract the constituent ticker set from one revision's wikitext."""
    table = _constituents_table(wikitext)
    found: set[str] = set()
    for row in table.split("\n|-"):
        # first data cell of the row
        cells = re.split(r"\n\s*\|\||\n\s*\|(?!\|)", row)
        cells = [c for c in cells if c.strip()]
        if not cells:
            continue
        cell = cells[0].strip()
        if cell.startswith("!"):          # header row
            continue
        for pat in _TICKER_PATTERNS:
            hit = pat.search(cell)
            if hit:
                t = hit.group(1).strip().upper()
                if t and t not in _NOT_TICKERS and not t.endswith("."):
                    found.add(t)
                break
    return found


# --------------------------------------------------------------------------
# Diff
# --------------------------------------------------------------------------

def months(start: str, end: str) -> list[date]:
    y0, m0 = (int(x) for x in start.split("-"))
    y1, m1 = (int(x) for x in end.split("-"))
    out, y, m = [], y0, m0
    while (y, m) <= (y1, m1):
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


SANITY_MIN, SANITY_MAX = 480, 520
CHURN_MAX = 25  # a month that swaps more than this is a parse failure, not news


def build(start: str, end: str) -> tuple[list[dict], list[dict]]:
    """Returns (removal rows, per-month audit rows)."""
    removals: list[dict] = []
    audit: list[dict] = []
    prev: set[str] | None = None
    prev_meta: tuple[int, str] | None = None

    for d in months(start, end):
        revid, ts, text = revision_at(d)
        cur = tickers(text)
        note = ""
        if not (SANITY_MIN <= len(cur) <= SANITY_MAX):
            note = f"IMPLAUSIBLE_COUNT({len(cur)}) - parse suspect, month skipped"
            audit.append({"month": d.isoformat(), "revid": revid, "timestamp": ts,
                          "n_constituents": len(cur), "n_removed": 0, "note": note})
            print(f"  {d:%Y-%m}  rev {revid}  n={len(cur):>3}  {note}")
            continue

        if prev is not None:
            gone = sorted(prev - cur)
            added = cur - prev
            if len(gone) > CHURN_MAX:
                note = f"CHURN({len(gone)}) exceeds {CHURN_MAX} - parse suspect, month skipped"
                audit.append({"month": d.isoformat(), "revid": revid, "timestamp": ts,
                              "n_constituents": len(cur), "n_removed": 0, "note": note})
                print(f"  {d:%Y-%m}  rev {revid}  n={len(cur):>3}  {note}")
                prev, prev_meta = cur, (revid, ts)
                continue
            for t in gone:
                removals.append({
                    "ticker": t,
                    "detected_date": ts[:10],
                    "prev_revid": prev_meta[0],
                    "revid": revid,
                    "same_month_additions": " ".join(sorted(added)),
                })
            note = f"{len(gone)} removed, {len(added)} added"
        audit.append({"month": d.isoformat(), "revid": revid, "timestamp": ts,
                      "n_constituents": len(cur),
                      "n_removed": len(prev - cur) if prev else 0, "note": note})
        print(f"  {d:%Y-%m}  rev {revid}  n={len(cur):>3}  {note}")
        prev, prev_meta = cur, (revid, ts)

    return removals, audit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2020-01", help="first month, YYYY-MM")
    ap.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m"))
    ap.add_argument("--out", default="sp500_removals_wiki.csv")
    ap.add_argument("--audit", default="sp500_removals_audit.csv")
    a = ap.parse_args()

    print(f"reconstructing S&P 500 membership {a.start} .. {a.end}")
    removals, audit = build(a.start, a.end)

    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "detected_date", "prev_revid",
                                          "revid", "same_month_additions"])
        w.writeheader()
        w.writerows(removals)
    with open(a.audit, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["month", "revid", "timestamp",
                                          "n_constituents", "n_removed", "note"])
        w.writeheader()
        w.writerows(audit)

    print(f"\n{len(removals)} removals -> {a.out}")
    print("same_month_additions lists names that entered in the same month; a")
    print("removal whose ticker merely changed will pair with one of them.")
    print(f"per-month audit -> {a.audit}")
    print("\nSource: English Wikipedia, 'List of S&P 500 companies', revision history.")
    print("Text licensed CC BY-SA 4.0. Dates are detection dates, not effective dates.")


if __name__ == "__main__":
    main()
