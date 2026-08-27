"""Re-verify tonight's scout findings before designing the commodities family.

1. Which liquid commodity ETF proxies actually resolve on yfinance, and how
   much common clean history they share.
2. Roll-yield contamination of the naive front-month futures splice (NG=F):
   compare its chained-return CAGR against UNG (a real, investable natgas
   proxy whose NAV pays the true roll cost) over the same window, and look
   at where the biggest NG=F daily "returns" land within the month.
3. Cross-correlation among the ETF basket (the USO/BNO 0.95 claim) and the
   basket's effective number of independent bets.
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import yfinance as yf

CANDIDATES = [
    "GLD", "IAU", "SLV", "PPLT", "PALL", "CPER",           # metals
    "USO", "BNO", "UNG", "UGA",                            # energy
    "CORN", "WEAT", "SOYB",                                # grains
    "DBC", "DBA", "DBB", "DBE", "GSG",                     # baskets (reference)
]

close = yf.download(CANDIDATES, start="2000-01-01", auto_adjust=True, progress=False)["Close"]
print("=== 1. ETF history ===")
for t in CANDIDATES:
    if t not in close.columns or close[t].dropna().empty:
        print(f"{t:6s} NO DATA")
        continue
    s = close[t].dropna()
    print(f"{t:6s} first={s.index[0].date()} last={s.index[-1].date()} rows={len(s)}")

singles = ["GLD", "SLV", "PPLT", "PALL", "CPER", "USO", "BNO", "UNG", "UGA", "CORN", "WEAT", "SOYB"]
sub = close[[t for t in singles if t in close.columns]].dropna(how="any")
print(f"\ncommon window for 12 single-commodity ETFs: {sub.index[0].date()} .. {sub.index[-1].date()}, "
      f"{len(sub)} rows = {len(sub)/252:.1f} years")

print("\n=== 2. NG=F naive splice vs UNG (investable) ===")
fut = yf.download(["NG=F", "CL=F"], start="2010-01-01", auto_adjust=True, progress=False)["Close"]
both = pd.concat([fut["NG=F"].rename("NGF"), close["UNG"].rename("UNG")], axis=1).dropna()
years = (both.index[-1] - both.index[0]).days / 365.25
for col in ("NGF", "UNG"):
    r = both[col].pct_change().dropna()
    # chained-return CAGR: what a backtest realizing pct_change() would credit
    cagr = float(np.exp(np.log1p(r).sum() / years) - 1.0)
    print(f"{col:4s} chained pct_change CAGR over {years:.1f}y: {cagr:+.2%}")
ngf_r = both["NGF"].pct_change().dropna()
ung_r = both["UNG"].pct_change().dropna()
gap = float(np.exp((np.log1p(ngf_r).sum() - np.log1p(ung_r).sum()) / years) - 1.0)
print(f"NG=F splice credits {gap:+.2%}/yr MORE than the investable proxy over the same days")

# where in the month do NG=F's largest daily moves land? NG futures expire
# 3 business days before the 1st of the delivery month -> rolls cluster
# late-month. A real market's big moves have no day-of-month pattern.
big = ngf_r[ngf_r.abs() >= 0.05]
print(f"NG=F days with |return| >= 5%: {len(big)}; by day-of-month bucket:")
buckets = pd.cut(pd.Series(big.index.day, index=big.index), bins=[0, 10, 20, 31], labels=["1-10", "11-20", "21-31"])
print(buckets.value_counts().to_string())
ung_big = ung_r[ung_r.abs() >= 0.05]
b2 = pd.cut(pd.Series(ung_big.index.day, index=ung_big.index), bins=[0, 10, 20, 31], labels=["1-10", "11-20", "21-31"])
print(f"UNG days with |return| >= 5%: {len(ung_big)}; by bucket:")
print(b2.value_counts().to_string())

print("\n=== 3. cross-correlations, common window ===")
rets = sub.pct_change().dropna(how="any")
corr = rets.corr()
pairs = []
cols = list(corr.columns)
for i, a in enumerate(cols):
    for b in cols[i + 1:]:
        pairs.append((a, b, corr.loc[a, b]))
pairs.sort(key=lambda x: -abs(x[2]))
print("top 10 |corr| pairs:")
for a, b, c in pairs[:10]:
    print(f"  {a}/{b}: {c:+.3f}")
lam = np.linalg.eigvalsh(corr.values)
neff = float(lam.sum() ** 2 / (lam ** 2).sum())
print(f"effective number of independent bets (eigenvalue-based, {len(cols)} tickers): {neff:.2f}")

vols = rets.std(ddof=1) * np.sqrt(252)
print("\nannualized daily vol per ETF:")
print((vols * 100).round(1).sort_values().to_string())
