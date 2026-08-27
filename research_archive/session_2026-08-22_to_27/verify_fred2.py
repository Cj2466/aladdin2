"""FRED verification with generous timeouts/retries (the project's own
FredProvider uses a 10s timeout, too short for these long histories)."""
import sys, time
from datetime import date, datetime

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_9fd00b72-30a-7/backend")

import httpx
import numpy as np
import pandas as pd
from scipy import stats

from app.config import settings

CODES = {"EUR": "EZ", "GBP": "GB", "JPY": "JP", "AUD": "AU", "CHF": "CH",
         "CAD": "CA", "NZD": "NZ", "SEK": "SE", "NOK": "NO", "USD": "US"}
URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch(series_id, attempts=5):
    params = {"series_id": series_id, "api_key": settings.fred_api_key,
              "file_type": "json", "units": "lin",
              "observation_start": "1995-01-01", "observation_end": "2026-12-31"}
    last = None
    for a in range(attempts):
        try:
            with httpx.Client(timeout=60) as c:
                r = c.get(URL, params=params)
                r.raise_for_status()
                payload = r.json()
            out = {}
            for o in payload.get("observations", []):
                v = o.get("value")
                if v in (None, "."):
                    continue
                out[datetime.strptime(o["date"], "%Y-%m-%d").date()] = float(v)
            return pd.Series(out).sort_index()
        except Exception as e:
            last = type(e).__name__
            time.sleep(2 * (a + 1))
    raise RuntimeError(f"{series_id}: {last}")


series = {}
for ccy, cc in CODES.items():
    sid = f"IR3TIB01{cc}M156N"
    try:
        s = fetch(sid)
        series[ccy] = s
        print(f"{ccy} {sid:>18}: n={len(s):4d}  {s.index[0]} .. {s.index[-1]}  last={s.iloc[-1]:.4f}")
    except Exception as e:
        print(f"{ccy} {sid:>18}: FAILED {e}")

if len(series) < 10:
    print("\nINCOMPLETE PANEL — cannot proceed with carry design as specified.")
    sys.exit(1)

TODAY = date(2026, 8, 27)
print(f"\n=== REAL PUBLICATION LAG (today = {TODAY}) ===")
worst = 0
for ccy, s in series.items():
    last = s.index[-1]
    months = (TODAY.year - last.year) * 12 + (TODAY.month - last.month)
    worst = max(worst, months)
    print(f"  {ccy}: last obs {last}  -> {months} months stale")
print(f"  WORST LAG ACROSS THE PANEL: {worst} months")

df = pd.DataFrame({c: pd.Series({pd.Timestamp(k): v for k, v in s.items()}) for c, s in series.items()}).sort_index()
diff = df.drop(columns=["USD"]).sub(df["USD"], axis=0).dropna(how="any")
print(f"\ndifferential panel: {diff.shape}  {diff.index[0].date()} .. {diff.index[-1].date()}")
print(diff.tail(3).round(3))

print("\n=== Cross-sectional rank correlation: diff_t vs diff_{t-k months} ===")
for k in (1, 3, 6, 7, 9, 12, 18):
    cors = []
    for i in range(k, len(diff)):
        a, b = diff.iloc[i].values, diff.iloc[i - k].values
        if np.all(np.isfinite(a)) and np.all(np.isfinite(b)):
            rho, _ = stats.spearmanr(a, b)
            if np.isfinite(rho):
                cors.append(rho)
    print(f"  lag {k:2d} months: mean cross-sectional Spearman = {np.mean(cors):.4f}  (n={len(cors)})")

print("\n=== Differential levels (annualized %) ===")
print(diff.describe().T[["mean", "std", "min", "max"]].round(3))

diff.to_csv("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/rate_diff.csv")
df.to_csv("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/rates_raw.csv")
print("\nsaved rate panels to scratchpad")
