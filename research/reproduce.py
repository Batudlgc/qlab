"""Regenerate the experiment output the research notes quote, and check it still holds.

    python3 research/reproduce.py           # write reports/output/<script>.txt
    python3 research/reproduce.py --check   # re-run and compare; exit 1 on any drift

Note 03 was published with figures its own script no longer produced: the engine
changed underneath it and nothing re-ran the experiment. This script closes that gap.

Every output file starts with a header naming the commit that produced it. --check fails if
  1. a script's output today differs from the committed file, number by number, by more
     than one unit in the last printed digit (so a float wobble between platforms is not
     drift, but any real change is);
  2. a number in a note's table does not appear in the output it cites, at the precision
     the note prints it. A note cites its output with a line
         <!-- source: reports/output/05_queue_competition.txt -->
     and every table after that line is checked against it. Columns that hold an
     experiment's inputs rather than its results are named just above their table:
         <!-- inputs: Half-spread -->
     and skipped;
  3. an output file was written from uncommitted code, or the code it depends on (qlab/,
     its script, requirements.txt) has changed since the commit in its header.

Only the seeded, offline experiments are covered. 01, 02 and 08 pull live market data,
which changes between runs (note 06), so their figures cannot be re-checked this way.
Sweeps write to a throwaway copy of the research log, so re-running never inflates the
trial count that the deflated Sharpe depends on.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "output"
LOG = ROOT / "reports" / "research_log.jsonl"
SCRIPTS = ["04_market_making", "05_queue_competition", "06_staleness_and_fees",
           "07_latency", "09_prosperity_tests", "10_prosperity_tournament"]

NUM = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
SOURCE = re.compile(r"<!--\s*source:\s*(\S+)\s*-->")
INPUTS = re.compile(r"<!--\s*inputs:\s*(.+?)\s*-->")
END_OF_HEADER = "# ---"


def git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def code_paths(name: str) -> list[str]:
    return ["qlab", f"research/{name}.py", "requirements.txt"]


def run_script(name: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "research_log.jsonl"
        if LOG.exists():
            shutil.copy(LOG, log)
        env = {**os.environ, "QLAB_RESEARCH_LOG": str(log), "PYTHONHASHSEED": "0"}
        r = subprocess.run([sys.executable, f"research/{name}.py"], cwd=ROOT, env=env,
                           capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"research/{name}.py exited {r.returncode}:\n{r.stderr[-2000:]}")
    return r.stdout


def run_all() -> dict[str, str]:
    with ThreadPoolExecutor(max_workers=len(SCRIPTS)) as ex:
        return dict(zip(SCRIPTS, ex.map(run_script, SCRIPTS)))


def header(name: str) -> str:
    import numpy, pandas
    sha = git("rev-parse", "HEAD") or "unknown"
    dirty = git("status", "--porcelain", "--", *code_paths(name))
    v = sys.version_info
    return "\n".join([
        f"# research/{name}.py",
        f"# commit {sha}" + (" (uncommitted changes)" if dirty else ""),
        f"# python {v.major}.{v.minor}.{v.micro}, numpy {numpy.__version__}, "
        f"pandas {pandas.__version__}",
        "# Regenerate with: python3 research/reproduce.py",
        END_OF_HEADER,
    ]) + "\n"


def split(text: str) -> tuple[list[str], str]:
    head, _, body = text.partition(END_OF_HEADER + "\n")
    return head.splitlines(), body


# ---------------------------------------------------------------- comparisons

def _tol(token: str) -> float:
    decimals = len(token.split(".")[1]) if "." in token and "e" not in token.lower() else 0
    return 1.0001 * 10.0 ** -decimals


def diff_outputs(old: str, new: str) -> list[str]:
    """Lines that differ in text, or in any number by more than one unit in its last digit."""
    a, b = old.splitlines(), new.splitlines()
    if len(a) != len(b):
        return [f"line count {len(a)} -> {len(b)}"]
    out = []
    for i, (x, y) in enumerate(zip(a, b), 1):
        if " ".join(NUM.sub("#", x).split()) != " ".join(NUM.sub("#", y).split()):
            out.append(f"line {i}: {x.strip()!r} -> {y.strip()!r}")
            continue
        for p, q in zip(NUM.findall(x), NUM.findall(y)):
            if abs(float(p) - float(q)) > max(_tol(p), _tol(q)):
                out.append(f"line {i}: {p} -> {q}   ({y.strip()[:90]})")
                break
    return out


def cell_value(cell: str) -> tuple[float, int, bool] | None:
    """A table cell as (value, decimals, is_percent), or None if it is not a number."""
    s = cell.strip().strip("*`").replace("−", "-").replace(" ", "")
    pct = s.endswith("%")
    s = s.rstrip("%")
    if re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    if not re.fullmatch(r"[-+]?\d+(\.\d+)?", s):
        return None
    return float(s), len(s.split(".")[1]) if "." in s else 0, pct


def found(cell: tuple[float, int, bool], numbers: list[float]) -> bool:
    v, d, pct = cell
    targets = [(v, d)] + ([(v / 100, d + 2)] if pct else [])
    return any(abs(x - t) <= 0.5 * 10.0 ** -dd + 1e-9 for t, dd in targets for x in numbers)


def check_note(note: Path, outputs: dict[str, str]) -> tuple[int, list[str]]:
    """Check every numeric cell of every table after a source line. Returns (cells, misses)."""
    numbers, cells, misses = None, 0, []
    inputs: set[str] = set()      # column names declared as inputs for the next table
    skip: set[int] = set()        # their positions, once the table's header row is read
    in_table = False
    for i, line in enumerate(note.read_text().splitlines(), 1):
        row = line.lstrip().startswith("|")
        if in_table and not row:
            in_table, inputs, skip = False, set(), set()
        m = SOURCE.search(line)
        if m:
            src = m.group(1)
            name = Path(src).stem
            if name not in outputs:
                misses.append(f"{note.name}:{i} cites {src}, which reproduce.py does not produce")
                numbers = None
                continue
            numbers = [float(t) for t in NUM.findall(outputs[name])]
            continue
        m = INPUTS.search(line)
        if m:
            inputs = {c.strip().lower() for c in m.group(1).split(",")}
            continue
        if numbers is None or not row:
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if not in_table:
            in_table = True
            skip = {j for j, c in enumerate(cols) if c.strip("*").lower() in inputs}
            continue
        if re.fullmatch(r"\s*\|[\s|:-]+\|\s*", line):
            continue
        for j, cell in enumerate(cols):
            val = cell_value(cell)
            if val is None or j in skip:
                continue
            cells += 1
            if not found(val, numbers):
                misses.append(f"{note.name}:{i} {cell.strip()!r} not in {name}.txt")
    return cells, misses


# ---------------------------------------------------------------- modes

def write() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, body in run_all().items():
        (OUT / f"{name}.txt").write_text(header(name) + body)
        print(f"wrote reports/output/{name}.txt")
    if git("status", "--porcelain", "--", "qlab", "research", "requirements.txt"):
        print("\nWARNING: code has uncommitted changes, so these files cannot name the commit "
              "that\nproduced them. Commit the code first, then re-run this script.")


def check() -> int:
    fails = []

    def report(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
        if not ok:
            fails.append(name)

    committed = {}
    for name in SCRIPTS:
        f = OUT / f"{name}.txt"
        if not f.exists():
            report(f"{name}: output committed", False, "(missing; run research/reproduce.py)")
            continue
        committed[name] = split(f.read_text())

    fresh = run_all()
    head = git("rev-parse", "HEAD")
    for name, (hdr, body) in committed.items():
        d = diff_outputs(body, fresh[name])
        report(f"{name}: output reproduces", not d, "" if not d else "\n    " + "\n    ".join(d[:8]))

        stamp = next((h.split()[2] for h in hdr if h.startswith("# commit ")), None)
        if stamp is None or "uncommitted" in " ".join(hdr):
            report(f"{name}: produced by a commit", False, "(written from uncommitted code)")
        elif head and git("cat-file", "-e", f"{stamp}^{{commit}}") is not None:
            changed = git("diff", "--name-only", stamp, "HEAD", "--", *code_paths(name))
            report(f"{name}: code unchanged since {stamp[:7]}", not changed,
                   "" if not changed else f"({changed.replace(chr(10), ', ')})")
        else:
            print(f"[SKIP] {name}: commit {stamp[:7]} not in local history")

    for note in sorted((ROOT / "reports").glob("note_*.md")):
        if not SOURCE.search(note.read_text()):
            continue
        cells, misses = check_note(note, fresh)
        report(f"{note.name}: table figures match output", not misses and cells > 0,
               f"({cells} cells)" if not misses else "\n    " + "\n    ".join(misses[:12]))

    print()
    print("ALL CHECKS PASSED" if not fails else f"{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="re-run and compare, write nothing")
    sys.exit(check() if ap.parse_args().check else write())
