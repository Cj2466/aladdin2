"""Empirical roll-artifact test for Yahoo '=F' front-month series.

Tests:
 A) futures-vs-ETF return divergence, and whether divergence days cluster by day-of-month
 B) cumulative-return divergence vs the ETF that pays the real roll (contango fingerprint)
 C) whether individual-contract tickers (e.g. CLZ25.NYM) are fetchable -> term structure
"""
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)

PAIRS = [("GC=F", "GLD"), ("SI=F", "SLV"), ("CL=F", "USO"), ("NG=F", "UNG"),
         ("HG=F", "CPER"), ("ZC=F", "CORN"), ("ZW=F", "WEAT"), ("ZS=F", "SOYB"),
         ("BZ=F", "BNO"), ("PL=F", "PPLT")]

tk = sorted({t for p in PAIRS for t in p})
raw = yf.download(tk, start="2012-01-01", end="2026-08-26", auto_adjust=True,
                  progress=False, threads=True)["Close"]

print("=== A/B: front-month futures vs ETF proxy ===")
out = []
for fut, etf in PAIRS:
    df = raw[[fut, etf]].dropna()
    rf = np.log(df[fut]).diff()
    re_ = np.log(df[etf]).diff()
    d = (rf - re_).dropna()
    # exclude fx/expense drift by looking at tail behaviour
    big = d[d.abs() > 0.05]
    dom = big.index.day
    # day-of-month concentration of big divergences
    hist = pd.Series(dom).value_counts().sort_index()
    top3 = hist.sort_values(ascending=False).head(3)
    yrs = (df.index[-1] - df.index[0]).days / 365.25
    out.append({
        "pair": f"{fut}/{etf}", "yrs": round(yrs, 1), "n": len(d),
        "corr": round(float(rf.corr(re_)), 3),
        "resid_ann_vol": round(float(d.std() * np.sqrt(252)), 4),
        "n_div_gt5pct": int(len(big)),
        "max_div": round(float(d.abs().max()), 4),
        "cum_fut": round(float(np.exp(rf.sum()) - 1), 3),
        "cum_etf": round(float(np.exp(re_.sum()) - 1), 3),
        "ann_drift_fut_minus_etf": round(float(d.mean() * 252), 4),
        "top_div_days_of_month": dict(top3),
    })
print(pd.DataFrame(out).to_string())

print("\n=== A2: do big single-day moves in =F cluster by day-of-month? (roll fingerprint) ===")
allfut = ["CL=F", "NG=F", "GC=F", "HG=F", "ZC=F", "SI=F", "RB=F", "HO=F", "ZS=F", "ZW=F"]
f2 = yf.download(allfut, start="2005-01-01", end="2026-08-26", auto_adjust=True,
                 progress=False, threads=True)["Close"]
for t in allfut:
    s = f2[t].dropna()
    r = np.log(s).diff().dropna()
    z = r / r.rolling(60).std().shift(1)
    z = z.dropna()
    big = z[z.abs() > 4]
    dom = pd.Series(big.index.day).value_counts().sort_index()
    exp = len(big) / 31
    top = dom.sort_values(ascending=False).head(4)
    print(f"{t}: n_big={len(big)} exp_per_day={exp:.2f} top_days={dict(top)}")

print("\n=== C: individual contract tickers (term structure feasibility) ===")
cands = ["CLZ26.NYM", "CLF27.NYM", "CLM27.NYM", "GCZ26.CMX", "GCM27.CMX",
         "NGZ26.NYM", "NGF27.NYM", "ZCZ26.CBT", "ZCH27.CBT", "HGZ26.CMX",
         "CLZ26", "GCZ26", "CL=F"]
for c in cands:
    try:
        h = yf.download(c, start="2026-01-01", end="2026-08-26", progress=False,
                        auto_adjust=True, threads=False)
        n = 0 if h is None or h.empty else int(h["Close"].dropna().shape[0])
        last = None if n == 0 else float(h["Close"].dropna().iloc[-1])
        print(f"{c}: bars={n} last={last}")
    except Exception as e:  # noqa: BLE001
        print(f"{c}: ERROR {type(e).__name__} {e}")
