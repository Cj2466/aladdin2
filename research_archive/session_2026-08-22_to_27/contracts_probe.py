"""Do EXPIRED Yahoo contract tickers retain history? Decisive for term-structure + clean roll."""
import warnings

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
MON = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M", 7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}

tests = []
for yr in [2015, 2018, 2020, 2022, 2024, 2025, 2026]:
    y2 = str(yr)[-2:]
    tests += [f"CLZ{y2}.NYM", f"GCZ{y2}.CMX", f"NGZ{y2}.NYM", f"ZCZ{y2}.CBT", f"HGZ{y2}.CMX"]

rows = []
for t in tests:
    try:
        h = yf.Ticker(t).history(period="max")
        if h is None or h.empty:
            rows.append({"ticker": t, "bars": 0, "start": None, "end": None})
            continue
        s = h["Close"].dropna()
        rows.append({"ticker": t, "bars": len(s), "start": str(s.index[0].date()),
                     "end": str(s.index[-1].date()), "last": round(float(s.iloc[-1]), 2)})
    except Exception as e:  # noqa: BLE001
        rows.append({"ticker": t, "bars": -1, "start": f"ERR {type(e).__name__}"})
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).to_string())

print("\n--- full CL curve today: how many deferred months are live? ---")
live = []
for yr, m in [(2026, m) for m in range(9, 13)] + [(2027, m) for m in range(1, 13)] + [(2028, m) for m in range(1, 13)]:
    t = f"CL{MON[m]}{str(yr)[-2:]}.NYM"
    try:
        h = yf.Ticker(t).history(period="1mo")
        if h is not None and not h.empty:
            s = h["Close"].dropna()
            if len(s):
                live.append((t, len(s), round(float(s.iloc[-1]), 2)))
    except Exception:  # noqa: BLE001, S110
        pass
print(live)
