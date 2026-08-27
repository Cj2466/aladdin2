"""Data-quality scan of the 11-ETF commodity panel: are there FX-style
reversing bad prints, or is this exchange-traded data clean? Also measure
the inputs to the holding-period cost arithmetic and the no-BNO breadth."""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import yfinance as yf

UNIVERSE = ["GLD", "SLV", "PPLT", "PALL", "CPER", "USO", "UNG", "UGA", "CORN", "WEAT", "SOYB"]
close = yf.download(UNIVERSE, start="2010-01-01", auto_adjust=True, progress=False)["Close"][UNIVERSE]
panel = close.dropna(how="any")
print(f"panel: {panel.index[0].date()} .. {panel.index[-1].date()}, {len(panel)} rows")

r = panel.pct_change()
nxt = r.shift(-1)
two_day = (1 + r) * (1 + nxt) - 1
# FX-style reversing-spike test at commodity-scale thresholds: a >=10% move
# (6+ sigma for most of these) where >half round-trips the next day.
flags = (r.abs() >= 0.10) & (two_day.abs() <= 0.5 * r.abs())
print("reversing >=10% spikes per ticker:", {c: int(flags[c].sum()) for c in flags.columns if flags[c].sum()})
for c in flags.columns:
    for ts in flags.index[flags[c]]:
        print(f"  {c} {ts.date()}: {r.loc[ts, c]:+.2%} then {nxt.loc[ts, c]:+.2%}")

# biggest single-day moves, for eyeballing (are they real events?)
big = r.abs().stack().sort_values(ascending=False).head(8)
print("\nlargest |daily moves|:")
for (ts, c), v in big.items():
    print(f"  {c} {ts.date()}: {r.loc[ts, c]:+.2%}")

# holes: interior NaNs inside the common panel (should be zero by construction)
print("\ninterior NaNs in panel:", int(panel.isna().sum().sum()))

# effective breadth without BNO
rets = r.dropna(how="any")
corr = rets.corr()
lam = np.linalg.eigvalsh(corr.values)
neff = float(lam.sum() ** 2 / (lam ** 2).sum())
print(f"\n11-name effective independent bets: {neff:.2f}")
mx = corr.where(~np.eye(len(corr), dtype=bool)).abs().max().max()
pairs = corr.where(np.triu(np.ones_like(corr, dtype=bool), 1)).stack().sort_values(ascending=False)
print("max |pair corr|:", f"{mx:.3f}", "top pairs:", pairs.head(3).round(3).to_dict())

# long-short book vol preview for cost arithmetic: equal-weight legs of 3,
# random-ish proxy: cross-sectional dispersion scale
vols = rets.std(ddof=1) * np.sqrt(252)
print("\nannualized vols:", (vols * 100).round(1).to_dict())
# typical 3-name leg vol range: use mean pairwise corr
mean_corr = float(corr.where(np.triu(np.ones_like(corr, dtype=bool), 1)).stack().mean())
print(f"mean pairwise corr: {mean_corr:.3f}")
