"""Independent re-verification of the scout's claimed FX data facts."""
import sys
import numpy as np
import pandas as pd
import yfinance as yf

PAIRS = {
    "EUR": "EURUSD=X",
    "GBP": "GBPUSD=X",
    "JPY": "USDJPY=X",
    "AUD": "AUDUSD=X",
    "CHF": "USDCHF=X",
    "CAD": "USDCAD=X",
    "NZD": "NZDUSD=X",
    "SEK": "USDSEK=X",
    "NOK": "USDNOK=X",
}

raw = yf.download(
    list(PAIRS.values()),
    start="2003-01-01",
    end="2026-08-27",
    auto_adjust=False,
    progress=False,
    group_by="column",
)
print("raw shape:", raw.shape)
print("fields:", sorted(set(raw.columns.get_level_values(0))))

close = raw["Close"]
high = raw["High"]
low = raw["Low"]
vol = raw["Volume"]

print("\n=== PER-PAIR COVERAGE ===")
for ccy, tk in PAIRS.items():
    s = close[tk].dropna()
    print(f"{ccy} {tk:>10}  n={len(s):5d}  first={s.index[0].date()}  last={s.index[-1].date()}")

# Common history
panel = close[list(PAIRS.values())].dropna(how="any")
print(f"\nCOMMON PANEL (all 9 non-NaN): n={len(panel)}  {panel.index[0].date()} .. {panel.index[-1].date()}")

print("\n=== DEFECT 1: Close outside [Low, High] ===")
for ccy, tk in PAIRS.items():
    df = pd.DataFrame({"c": close[tk], "h": high[tk], "l": low[tk]}).dropna()
    bad = (df["c"] > df["h"] * (1 + 1e-12)) | (df["c"] < df["l"] * (1 - 1e-12))
    print(f"{ccy}: {bad.sum():5d} / {len(df):5d} = {100*bad.mean():5.2f}% of days Close outside [Low,High]")

print("\n=== DEFECT 2: Volume ===")
for ccy, tk in PAIRS.items():
    v = vol[tk].dropna()
    nz = (v != 0).sum()
    print(f"{ccy}: n={len(v):5d}  nonzero={nz}  unique={v.unique()[:5]}")

print("\n=== DEFECT 3: return outliers on the common panel ===")
# Convert to foreign-per-USD -> USD-per-foreign consistent basis
usd_per_foreign = pd.DataFrame(index=panel.index)
INVERTED = {"JPY", "CHF", "CAD", "SEK", "NOK"}
for ccy, tk in PAIRS.items():
    usd_per_foreign[ccy] = 1.0 / panel[tk] if ccy in INVERTED else panel[tk]

rets = usd_per_foreign.pct_change().dropna(how="all")
print(rets.describe().T[["mean", "std", "min", "max"]])
print("\ndaily |return| > 5%% counts:")
print((rets.abs() > 0.05).sum())
print("\nlargest 8 abs moves overall:")
flat = rets.abs().stack().sort_values(ascending=False)
print(flat.head(8))

print("\n=== TRIANGULAR CROSS-RATE CONSISTENCY (scout claim: max err 2633bp) ===")
# EURGBP implied from EURUSD and GBPUSD, vs a directly-quoted EURGBP=X
try:
    cross = yf.download("EURGBP=X", start="2006-01-01", end="2026-08-27",
                        auto_adjust=False, progress=False)
    direct = cross["Close"]
    if isinstance(direct, pd.DataFrame):
        direct = direct.iloc[:, 0]
    implied = (panel["EURUSD=X"] / panel["GBPUSD=X"]).reindex(direct.index).dropna()
    common = implied.index.intersection(direct.dropna().index)
    err_bp = ((implied.loc[common] / direct.loc[common] - 1.0).abs() * 10_000)
    print(f"n={len(common)}  median={err_bp.median():.2f}bp  p99={err_bp.quantile(0.99):.1f}bp  MAX={err_bp.max():.1f}bp")
    print("worst 5:")
    print(err_bp.sort_values(ascending=False).head(5))
except Exception as e:
    print("cross-rate check failed:", e)
