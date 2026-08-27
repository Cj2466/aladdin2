import re
import sys
import pandas as pd

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
TICKER_RE = re.compile(r"^[A-Z]{1,5}(-[A-Z]{1,2})?$")


def norm(x):
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


t = pd.read_html(f"{SCRATCH}/sp600.html")[1]
t.columns = ["date", "add_t", "add_s", "rem_t", "rem_s", "reason"]
t = t[t["date"] != "Date"].copy()
t["d"] = pd.to_datetime(t["date"], format="mixed").dt.date

for probe in ["ALSK", "MPW", "SIX", "IAC", "BBT", "VSCO", "ATGE"]:
    print(f"=== {probe} ===")
    for _, r in t.iterrows():
        if probe in norm(r["add_t"]) or probe in norm(r["rem_t"]):
            print("  ", r["d"], "add=", norm(r["add_t"]), "rem=", norm(r["rem_t"]), "|", str(r["reason"])[:90])
