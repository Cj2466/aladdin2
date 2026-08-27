import warnings; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np

TICKERS = ["^VIX","^VIX3M","^VIX6M","^VXD","^VVIX","^SKEW","^MOVE","^OVX","^GVZ","^VIX9D","^VIX1D"]
raw = yf.download(TICKERS, start="1990-01-01", end="2026-08-27", auto_adjust=True, progress=False)
close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
close = close.dropna(axis=1, how="all")
print("resolved:", sorted(close.columns))
print("missing:", [t for t in TICKERS if t not in close.columns])
print()
for t in TICKERS:
    if t not in close.columns:
        print(f"{t:9s} MISSING"); continue
    s = close[t].dropna()
    print(f"{t:9s} first={s.index[0].date()} last={s.index[-1].date()} n={len(s)} min={s.min():.2f} max={s.max():.2f}")

core = [t for t in ["^VIX","^VIX3M","^VIX6M","^VXD","^VVIX","^SKEW","^MOVE","^OVX","^GVZ"] if t in close.columns]
sub = close[core].dropna(how="any")
print("\nCOMMON HISTORY (9 core, ex-VIX9D/VIX1D):", sub.index[0].date(), "->", sub.index[-1].date(), "n=", len(sub))
sub_all = close.dropna(how="any")
print("COMMON HISTORY (all 11 incl 9D/1D):", sub_all.index[0].date(), "->", sub_all.index[-1].date(), "n=", len(sub_all))
close.to_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/volidx.pkl")
