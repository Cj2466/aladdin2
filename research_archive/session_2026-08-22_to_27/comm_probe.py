"""Real yfinance probe for commodity exposure: history length, gaps, roll artifacts."""
import json
import sys
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

FUT = ["GC=F", "SI=F", "HG=F", "PL=F", "PA=F", "CL=F", "BZ=F", "NG=F", "RB=F", "HO=F",
       "ZC=F", "ZS=F", "ZW=F", "ZL=F", "ZM=F", "KC=F", "SB=F", "CC=F", "CT=F", "LE=F",
       "HE=F", "OJ=F", "ZO=F", "ZR=F"]
ETF = ["GLD", "SLV", "USO", "DBC", "IAU", "PPLT", "PALL", "CPER", "UNG", "BNO",
       "CORN", "WEAT", "SOYB", "DBA", "DBB", "DBO", "DBE", "GSG", "PDBC", "COMT",
       "USCI", "FTGC", "SGOL", "UGA", "JJC", "NIB", "CANE", "BAL", "JO", "GLTR"]

tickers = FUT + ETF
raw = yf.download(tickers, start="1990-01-01", end="2026-08-26", interval="1d",
                  auto_adjust=False, progress=False, group_by="column", threads=True)

close = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw
adj = raw["Adj Close"] if "Adj Close" in raw.columns.get_level_values(0) else None
vol = raw["Volume"] if "Volume" in raw.columns.get_level_values(0) else None

rows = []
for t in tickers:
    if t not in close.columns:
        rows.append({"ticker": t, "status": "MISSING"})
        continue
    s = close[t].dropna()
    if len(s) < 50:
        rows.append({"ticker": t, "status": "TOO_SHORT", "n": len(s)})
        continue
    r = np.log(s).diff().dropna()
    v = vol[t].reindex(s.index).dropna() if vol is not None else pd.Series(dtype=float)
    med_dv = float((v.tail(500) * s.reindex(v.tail(500).index)).median()) if len(v) else float("nan")
    # gap structure: trading-day coverage vs NYSE-ish expectation
    span_days = (s.index[-1] - s.index[0]).days
    exp_bars = span_days / 365.25 * 252
    rows.append({
        "ticker": t,
        "status": "OK",
        "start": str(s.index[0].date()),
        "end": str(s.index[-1].date()),
        "n": int(len(s)),
        "years": round(span_days / 365.25, 1),
        "coverage": round(len(s) / exp_bars, 3) if exp_bars > 0 else None,
        "ann_vol": round(float(r.std() * np.sqrt(252)), 3),
        "med_dollar_vol_M": round(med_dv / 1e6, 2) if med_dv == med_dv else None,
        "max_abs_1d_ret": round(float(r.abs().max()), 4),
        "n_ret_gt_15pct": int((r.abs() > 0.15).sum()),
        "n_ret_gt_25pct": int((r.abs() > 0.25).sum()),
        "zero_ret_frac": round(float((r == 0).mean()), 4),
        "has_adj": bool(adj is not None and t in adj.columns and adj[t].dropna().shape[0] > 0),
        "adj_equals_close": (
            bool(np.allclose(adj[t].dropna().tail(2000), close[t].reindex(adj[t].dropna().tail(2000).index), rtol=1e-6))
            if adj is not None and t in adj.columns and adj[t].dropna().shape[0] > 100 else None
        ),
    })

print(json.dumps(rows, indent=0))
close.to_pickle(sys.argv[1] if len(sys.argv) > 1 else "/tmp/comm_close.pkl")
