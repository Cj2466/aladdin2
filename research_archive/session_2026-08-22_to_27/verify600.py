import re
import pandas as pd

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
TICKER_RE = re.compile(r"^[A-Z]{1,5}(-[A-Z]{1,2})?$")


def norm(x):
    s = str(x).strip()
    if s in ("nan", "", "None"):
        return []
    s = re.sub(r"\[[^\]]*\]", "", s)
    return [p.strip().replace(".", "-").upper() for p in re.split(r"[,/]| and ", s)
            if TICKER_RE.match(p.strip().replace(".", "-").upper())]


t = pd.read_html(f"{SCRATCH}/sp600.html")[1]
t.columns = ["date", "add_t", "add_s", "rem_t", "rem_s", "reason"]
t = t[t["date"] != "Date"].copy()
t["d"] = pd.to_datetime(t["date"], format="mixed").dt.date

# Well-known small-cap index events with independently-known real dates.
PROBES = ["GME", "AMC", "SIVB", "FRC", "PRTY", "BBBY", "TUP", "WW", "CVNA", "SMCI", "APPS", "RILY"]
for p in PROBES:
    hits = [(r["d"], norm(r["add_t"]), norm(r["rem_t"]), str(r["reason"])[:110])
            for _, r in t.iterrows() if p in norm(r["add_t"]) or p in norm(r["rem_t"])]
    if hits:
        print(f"=== {p} ===")
        for h in hits:
            print("  ", h[0], "add=", h[1], "rem=", h[2], "|", h[3])

print("\n=== reason-text sanity: how many rows cite a real corporate action? ===")
reasons = t["reason"].astype(str)
for kw in ["acquired", "merg", "S&P 400", "S&P 500", "spun off", "bankrupt", "market cap"]:
    print(f"  {kw!r}: {reasons.str.contains(kw, case=False).sum()} rows")
print(f"  rows with a [n] footnote citation: {reasons.str.contains(r'\[\d+\]').sum()} of {len(t)}")
