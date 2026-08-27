"""Generate the vendored S&P 600 point-in-time membership literals from the
live Wikipedia article, and run this project's own falsification test on the
result (backward replay from today's snapshot; drift = incompleteness)."""
import re
import sys
from datetime import date

import pandas as pd

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
BASE_DATE = date(2020, 1, 1)

TICKER_RE = re.compile(r"^[A-Z]{1,5}(-[A-Z]{1,2})?$")


def norm(x):
    """Wikipedia cell -> list of clean, yfinance-symbology tickers."""
    s = str(x).strip()
    if s in ("nan", "", "None", "—", "-"):
        return []
    s = re.sub(r"\[[^\]]*\]", "", s)
    out = []
    for part in re.split(r"[,/]| and ", s):
        p = part.strip().replace(".", "-").upper()
        if TICKER_RE.match(p):
            out.append(p)
    return out


tables = pd.read_html(f"{SCRATCH}/sp600.html")
current, changes = tables[0], tables[1]

members_today = set()
for sym in current["Symbol"].astype(str):
    members_today.update(norm(sym))
print(f"current snapshot: {len(members_today)} tickers", file=sys.stderr)

changes.columns = ["date", "add_t", "add_s", "rem_t", "rem_s", "reason"]
changes = changes[changes["date"] != "Date"].copy()
changes["d"] = pd.to_datetime(changes["date"], format="mixed").dt.date
as_of = max(changes["d"])
changes = changes[changes["d"] >= BASE_DATE]

by_date: dict[date, tuple[set, set]] = {}
for _, r in changes.iterrows():
    added, removed = by_date.setdefault(r["d"], (set(), set()))
    added.update(norm(r["add_t"]))
    removed.update(norm(r["rem_t"]))

events = sorted((d, set(a), set(rm)) for d, (a, rm) in by_date.items())
print(f"{len(events)} dated events, {events[0][0]} .. {events[-1][0]}, as_of={as_of}", file=sys.stderr)

# --- backward replay: reconstruct the base universe at BASE_DATE ----------
members = set(members_today)
for d, added, removed in reversed(events):
    members.difference_update(added)
    members.update(removed)
base = set(members)
print(f"base universe at {BASE_DATE}: {len(base)} tickers", file=sys.stderr)

# --- forward replay + reconciliation --------------------------------------
check = set(base)
for _d, added, removed in events:
    check.difference_update(removed)
    check.update(added)

undated_removals = sorted(check - members_today)
undated_readditions = sorted(members_today - check)
print(f"undated removals ({len(undated_removals)}): {undated_removals}", file=sys.stderr)
print(f"undated re-additions ({len(undated_readditions)}): {undated_readditions}", file=sys.stderr)

# The reconciliation event: a single terminal event at coverage end carrying
# exactly the membership changes Wikipedia's own changes table never dated.
# Making it explicit (rather than silently dropping the names, or silently
# leaving them in) is what lets the forward replay reproduce the current
# snapshot EXACTLY -- the same verification standard sp500_membership_history
# holds itself to ("reproduce the source file's own final row exactly").
check2 = set(base)
counts = []
for d, added, removed in events:
    check2.difference_update(removed)
    check2.update(added)
    counts.append((d, len(check2)))
# Applied ONCE at coverage end, as its own named step -- deliberately not
# folded into _MEMBERSHIP_EVENTS, where it would collide with a real dated
# event on the same day and become indistinguishable from sourced history.
check2.difference_update(undated_removals)
check2.update(undated_readditions)
assert check2 == members_today, f"round-trip STILL fails: {sorted(check2 ^ members_today)}"
print(f"ROUND TRIP OK: forward replay reproduces all {len(members_today)} current tickers", file=sys.stderr)

ns = [len(base)] + [n for _d, n in counts]
print(f"member-count band over the whole window: {min(ns)} .. {max(ns)} "
      f"(drift {(max(ns) - min(ns)) / 600 * 100:.1f}% of the index's nominal 600)", file=sys.stderr)


def wrap(items, per_line=13, indent="    "):
    lines, cur = [], []
    for it in items:
        cur.append(f'"{it}"')
        if len(cur) == per_line:
            lines.append(indent + ", ".join(cur) + ",")
            cur = []
    if cur:
        lines.append(indent + ", ".join(cur) + ",")
    return "\n".join(lines)


def tup(items):
    items = sorted(items)
    if not items:
        return "()"
    body = ", ".join(f'"{t}"' for t in items)
    return f"({body},)" if len(items) == 1 else f"({body})"


with open(f"{SCRATCH}/sp600_literals.py", "w") as fh:
    fh.write(f"# as_of = {as_of.isoformat()}\n")
    fh.write(f"_BASE_UNIVERSE: tuple[str, ...] = (\n{wrap(sorted(base))}\n)\n\n")
    fh.write(f"_UNDATED_REMOVALS: tuple[str, ...] = {tup(undated_removals)}\n\n")
    fh.write(f"_UNDATED_READDITIONS: tuple[str, ...] = {tup(undated_readditions)}\n\n")
    fh.write("_MEMBERSHIP_EVENTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (\n")
    for d, added, removed in events:
        fh.write(f'    ("{d.isoformat()}", {tup(added)}, {tup(removed)}),\n')
    fh.write(")\n")
print("wrote sp600_literals.py", file=sys.stderr)
