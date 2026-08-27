"""Probe 3: (i) contract-ticker availability for term structure, (ii) self-contained
roll fingerprint via overnight gaps in the =F series (no ETF proxy needed)."""
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)

print("=== C (fixed): individual contract tickers ===")
cands = ["CLZ26.NYM", "CLF27.NYM", "CLM27.NYM", "GCZ26.CMX", "GCG27.CMX",
         "NGZ26.NYM", "NGF27.NYM", "ZCZ26.CBT", "ZCH27.CBT", "HGZ26.CMX",
         "CLZ26.CME", "^SPGSCI", "^BCOM", "CL=F"]
for c in cands:
    try:
        h = yf.Ticker(c).history(period="6mo")
        n = 0 if h is None or h.empty else int(h["Close"].dropna().shape[0])
        last = None if n == 0 else round(float(h["Close"].dropna().iloc[-1]), 3)
        print(f"  {c}: bars={n} last={last}")
    except Exception as e:  # noqa: BLE001
        print(f"  {c}: ERROR {type(e).__name__}: {str(e)[:90]}")

print("\n=== D: self-contained roll fingerprint — overnight gap |log(Open_t/Close_t-1)| ===")
futs = ["CL=F", "NG=F", "RB=F", "HO=F", "GC=F", "SI=F", "HG=F", "ZC=F", "ZS=F", "ZW=F",
        "KC=F", "SB=F", "CC=F", "CT=F", "LE=F", "HE=F"]
raw = yf.download(futs, start="2010-01-01", end="2026-08-26", auto_adjust=False,
                  progress=False, threads=True)
op, cl = raw["Open"], raw["Close"]
rows = []
for t in futs:
    o, c = op[t].dropna(), cl[t].dropna()
    idx = o.index.intersection(c.index)
    o, c = o.reindex(idx), c.reindex(idx)
    gap = np.log(o / c.shift(1)).dropna()
    intraday = np.log(c / o).reindex(gap.index).dropna()
    gap = gap.reindex(intraday.index)
    scale = gap.abs().median()
    huge = gap[gap.abs() > max(8 * scale, 0.02)]
    dom = pd.Series(huge.index.day).value_counts()
    conc = float(dom.head(4).sum() / len(huge)) if len(huge) else np.nan
    rows.append({
        "ticker": t,
        "med_abs_gap_bp": round(float(scale) * 1e4, 1),
        "med_abs_intraday_bp": round(float(intraday.abs().median()) * 1e4, 1),
        "n_huge_gaps": int(len(huge)),
        "max_gap": round(float(gap.abs().max()), 4),
        "top4_dom": dict(dom.head(4)),
        "frac_in_top4_dom": round(conc, 2) if conc == conc else None,
        "frac_expected_top4": 0.13,
    })
print(pd.DataFrame(rows).to_string())

print("\n=== E: roll-yield omission — annualised drift of =F vs matched ETF (net of ETF fee) ===")
FEES = {"GLD": 0.0040, "SLV": 0.0050, "USO": 0.0060, "UNG": 0.0135, "CPER": 0.0097,
        "CORN": 0.0100, "WEAT": 0.0122, "SOYB": 0.0122, "BNO": 0.0100, "PPLT": 0.0060,
        "DBC": 0.0087}
PAIRS = [("GC=F", "GLD"), ("SI=F", "SLV"), ("CL=F", "USO"), ("NG=F", "UNG"),
         ("HG=F", "CPER"), ("ZC=F", "CORN"), ("ZW=F", "WEAT"), ("ZS=F", "SOYB"),
         ("BZ=F", "BNO"), ("PL=F", "PPLT")]
tk = sorted({x for p in PAIRS for x in p})
px = yf.download(tk, start="2012-01-01", end="2026-08-26", auto_adjust=True,
                 progress=False, threads=True)["Close"]
out = []
for f, e in PAIRS:
    d = px[[f, e]].dropna()
    yrs = (d.index[-1] - d.index[0]).days / 365.25
    df_ = (np.log(d[f].iloc[-1] / d[f].iloc[0]) - np.log(d[e].iloc[-1] / d[e].iloc[0])) / yrs
    out.append({"pair": f"{f}/{e}", "ann_drift_diff": round(float(df_), 4),
                "etf_fee": FEES[e],
                "implied_omitted_roll_yield_pa": round(float(df_) - FEES[e], 4)})
print(pd.DataFrame(out).to_string())
