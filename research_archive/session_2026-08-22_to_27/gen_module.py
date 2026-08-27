"""Generates the vendored data literals for sp500_membership_history.py."""
import json
import textwrap

import pandas as pd

d = json.load(open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/events.json"))
BASE_DATE = d["base_date"]
base = sorted(t.replace(".", "-") for t in d["base"])
events = [(dt, sorted(t.replace(".", "-") for t in a), sorted(t.replace(".", "-") for t in r)) for dt, a, r in d["events"]]

# --- intervals (ticker-keyed, straight from the reconstruction) ---
iv = {}
cur = {t: BASE_DATE for t in base}
for dt, a, r in events:
    for t in r:
        if t in cur:
            iv.setdefault(t, []).append((cur.pop(t), dt))
    for t in a:
        if t not in cur:
            cur[t] = dt
for t, s in cur.items():
    iv.setdefault(t, []).append((s, None))

# --- Wikipedia company-level "Date added" override, only where it is EARLIER
# than the ticker's own first appearance AND that first appearance is after
# the data window's start (i.e. not just a censored pre-window member). ---
w = pd.read_html("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/wiki.html")[0]
wd = {s.replace(".", "-"): str(x)[:10] for s, x in zip(w["Symbol"], w["Date added"])}
overrides = {}
for t, spans in iv.items():
    if spans[-1][1] is not None:
        continue  # not a current member
    first = spans[0][0]
    if first == BASE_DATE:
        continue  # censored at the data window's start; no correction needed
    wdate = wd.get(t)
    if wdate and wdate < first:
        overrides[t] = wdate

print("base", len(base), "events", len(events), "overrides", len(overrides))


def fmt_tickers(tickers, indent):
    body = ", ".join(f'"{t}"' for t in tickers)
    return textwrap.fill(body, width=100, initial_indent=indent, subsequent_indent=indent)


lines = []
lines.append("_BASE_UNIVERSE: tuple[str, ...] = (")
lines.append(fmt_tickers(base, "    "))
lines.append(")")
base_block = "\n".join(lines)

ev_lines = ["_MEMBERSHIP_EVENTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = ("]
for dt, a, r in events:
    added = "(" + ", ".join(f'"{t}"' for t in a) + ("," if len(a) == 1 else "") + ")"
    removed = "(" + ", ".join(f'"{t}"' for t in r) + ("," if len(r) == 1 else "") + ")"
    entry = f'    ("{dt}", {added}, {removed}),'
    if len(entry) <= 110:
        ev_lines.append(entry)
    else:
        ev_lines.append(f'    ("{dt}",')
        ev_lines.append(f"        {added},")
        ev_lines.append(f"        {removed},")
        ev_lines.append("    ),")
ev_lines.append(")")
ev_block = "\n".join(ev_lines)

ov_lines = ["_EARLIEST_MEMBERSHIP_OVERRIDES: dict[str, str] = {"]
for t in sorted(overrides):
    ov_lines.append(f'    "{t}": "{overrides[t]}",')
ov_lines.append("}")
ov_block = "\n".join(ov_lines)

open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/data_blocks.py", "w").write(
    base_block + "\n\n" + ev_block + "\n\n" + ov_block + "\n"
)
print("overrides:", overrides)
