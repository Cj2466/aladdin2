import warnings, json
warnings.filterwarnings("ignore")
import yfinance as yf
import pandas as pd
import numpy as np

TICKERS = ["TLT","IEF","SHY","IEI","TLH","AGG","BND","LQD","HYG","JNK","TIP","SHV","BIL","GOVT","VCIT","VCSH","MBB","EMB","VGIT","VGLT","SPTL","STIP","VTIP","SCHO","SCHR","IGSB","EDV","ZROZ","BSV","BIV","BLV","VGSH","FLOT","SJNK","IEF"]
TICKERS = sorted(set(TICKERS))

out = {}
for adj in (True, False):
    df = yf.download(TICKERS, start="1990-01-01", end="2026-08-26", auto_adjust=adj,
                     progress=False, threads=True, group_by="column")
    key = "adj" if adj else "raw"
    try:
        close = df["Close"]
    except Exception as e:
        print("ERR", e); continue
    for t in TICKERS:
        if t not in close.columns:
            out.setdefault(t, {})[key] = None
            continue
        s = close[t].dropna()
        if len(s) == 0:
            out.setdefault(t, {})[key] = None
            continue
        out.setdefault(t, {})[key] = {
            "n": int(len(s)),
            "start": str(s.index[0].date()),
            "end": str(s.index[-1].date()),
            "first_px": round(float(s.iloc[0]), 4),
            "last_px": round(float(s.iloc[-1]), 4),
        }

# gap / integrity check on adjusted
df = yf.download(TICKERS, start="1990-01-01", end="2026-08-26", auto_adjust=True,
                 progress=False, threads=True, group_by="column")
close = df["Close"]
vol = df["Volume"]
print(f"{'TKR':6} {'n_adj':>6} {'start_adj':>11} {'end_adj':>11} {'n_raw':>6} {'start_raw':>11} {'maxgap_d':>8} {'n_intgap':>8} {'medDolVol20':>13} {'ann_vol%':>8} {'jump>8%':>7}")
rows = []
for t in TICKERS:
    a = out.get(t, {}).get("adj")
    r = out.get(t, {}).get("raw")
    if a is None:
        print(f"{t:6} MISSING/UNRESOLVED")
        continue
    s = close[t].dropna()
    idx = s.index
    # max calendar gap between consecutive observations
    d = np.diff(idx.values).astype("timedelta64[D]").astype(int)
    maxgap = int(d.max()) if len(d) else 0
    # internal NaNs between first and last valid
    seg = close[t].loc[idx[0]:idx[-1]]
    n_int = int(seg.isna().sum())
    v = vol[t].loc[idx[0]:idx[-1]]
    dv = (s * v).dropna()
    meddv = float(dv.tail(252).median()) if len(dv) else float("nan")
    ret = s.pct_change().dropna()
    annvol = float(ret.std() * np.sqrt(252) * 100)
    jumps = int((ret.abs() > 0.08).sum())
    print(f"{t:6} {a['n']:>6} {a['start']:>11} {a['end']:>11} {(r['n'] if r else 0):>6} {(r['start'] if r else '-'):>11} {maxgap:>8} {n_int:>8} {meddv:>13,.0f} {annvol:>8.2f} {jumps:>7}")
    rows.append((t, a, r, meddv, annvol))

print("\n--- auto_adjust divergence (dividend/split handling proof) ---")
for t in TICKERS:
    a = out.get(t, {}).get("adj"); r = out.get(t, {}).get("raw")
    if not a or not r: continue
    # total return vs price return over common window
    tr = a["last_px"]/a["first_px"] - 1
    pr = r["last_px"]/r["first_px"] - 1
    print(f"{t:6} adj_total_ret={tr*100:8.1f}%  raw_price_ret={pr*100:8.1f}%  income_contrib={((1+tr)/(1+pr)-1)*100:8.1f}%")
