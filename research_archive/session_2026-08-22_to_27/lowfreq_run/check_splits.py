"""Data verification: is the cached 15-min data split-adjusted?

Scans every cached ticker's daily overnight (close->open) return for
moves > 35% in magnitude, which would be the signature of an unadjusted
stock split (e.g. NVDA's 10-for-1 on 2024-06-10 would show as ~-90%).
"""

import glob
import os
import pickle

import pandas as pd

BASE = (
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/bars_cache/"
)


def daily(path: str) -> pd.DataFrame:
    with open(path, "rb") as f:
        df = pickle.load(f)
    g = df.groupby(df.index.date)
    d = pd.DataFrame({"open": g["open"].first(), "close": g["close"].last()})
    d.index = pd.DatetimeIndex(d.index)
    d["on"] = d["open"] / d["close"].shift(1) - 1
    return d


nv = daily(BASE + "NVDA_15Min.pkl")
print(nv.loc["2024-06-05":"2024-06-12"])

worst = []
for f in sorted(glob.glob(BASE + "*_15Min.pkl")):
    t = os.path.basename(f).replace("_15Min.pkl", "")
    d = daily(f)
    m = d["on"].abs().max()
    if m > 0.35:
        idx = d["on"].abs().idxmax()
        worst.append((t, round(float(d.loc[idx, "on"]), 3), str(idx.date())))
print("overnight |move|>35%:", worst)
