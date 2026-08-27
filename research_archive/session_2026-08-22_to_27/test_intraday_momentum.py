"""
Illustrative, PRE-SPECIFIED replication check (not a fishing expedition):
Gao, Han, Xie, Yang (2018) "Market Intraday Momentum" (J. Financial Economics)
finding: the first half-hour return predicts the last half-hour return,
pooled across stocks. This is a real, published, peer-reviewed pattern, not
one invented for this test -- chosen specifically because it's a single,
principled hypothesis (matching the "bounded, principled search" discipline
the plan will require), not a search over many candidate patterns.

Method: pooled OLS of last-30-min return on first-30-min return across
tickers and days (real 5-minute bars, ~59 days, the max free yfinance
window), then a placebo/permutation null: shuffle which day's first-half-hour
return is paired with which day's last-half-hour return (within each ticker,
so each ticker's own marginal distributions are preserved) and recompute the
pooled correlation 2000 times -- same "synthetic control, compare to a null
built from the real data's own structure" methodology already used
throughout this codebase (e.g. screening.py's cointegration spurious-pair
control).
"""
import numpy as np
import pandas as pd
import yfinance as yf

UNIVERSE = [
    "AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","JPM","V","UNH",
    "XOM","JNJ","WMT","PG","MA","HD","CVX","MRK","ABBV","KO",
    "PEP","BAC","AVGO","COST","MCD","CSCO","ADBE","CRM","TMO","ACN",
    "DIS","NFLX","INTC","AMD","QCOM","TXN","HON","UPS","CAT","GE",
]

print(f"Fetching 5m bars for {len(UNIVERSE)} tickers, last ~59 days...")
df = yf.download(UNIVERSE, period="60d", interval="5m", auto_adjust=True, progress=False)
print("Fetched shape:", df.shape)

close = df["Close"]
close.index = close.index.tz_convert("America/New_York")

rows = []
for ticker in UNIVERSE:
    if ticker not in close.columns:
        continue
    s = close[ticker].dropna()
    if s.empty:
        continue
    s_df = s.to_frame("close")
    s_df["date"] = s_df.index.date
    s_df["time"] = s_df.index.time
    for day, group in s_df.groupby("date"):
        group = group.sort_index()
        try:
            open_px = group.loc[group["time"] == pd.Timestamp("09:30").time(), "close"]
            t1000 = group.loc[group["time"] == pd.Timestamp("10:00").time(), "close"]
            t1530 = group.loc[group["time"] == pd.Timestamp("15:30").time(), "close"]
            close_px = group.loc[group["time"] == pd.Timestamp("15:55").time(), "close"]
            if open_px.empty or t1000.empty or t1530.empty or close_px.empty:
                continue
            first30 = float(t1000.iloc[0]) / float(open_px.iloc[0]) - 1.0
            last30 = float(close_px.iloc[0]) / float(t1530.iloc[0]) - 1.0
            rows.append({"ticker": ticker, "date": day, "first30": first30, "last30": last30})
        except Exception:
            continue

panel = pd.DataFrame(rows)
print(f"\nPooled panel: {len(panel)} ticker-day observations across {panel['ticker'].nunique()} tickers, "
      f"{panel['date'].nunique()} distinct days")

real_corr = panel["first30"].corr(panel["last30"])
n = len(panel)
t_stat = real_corr * np.sqrt(n - 2) / np.sqrt(1 - real_corr**2)
print(f"\nReal pooled correlation(first30, last30): {real_corr:.4f}  (n={n}, naive t={t_stat:.2f})")

# OLS with slope/intercept for economic magnitude
slope, intercept = np.polyfit(panel["first30"], panel["last30"], 1)
print(f"OLS slope (last30 ~ first30): {slope:.4f}, intercept: {intercept:.5f}")

# Permutation null: within each ticker, shuffle the date->first30 pairing
# relative to last30 (breaks the SAME-DAY link but preserves each ticker's
# own marginal distribution of first30/last30 values and cross-ticker
# structure on a given day is NOT what we're testing here, so this is a
# same-ticker-only shuffle).
rng = np.random.default_rng(42)
n_perm = 2000
perm_corrs = np.empty(n_perm)
for i in range(n_perm):
    shuffled = panel.copy()
    shuffled["first30"] = shuffled.groupby("ticker")["first30"].transform(
        lambda s: s.sample(frac=1.0, random_state=rng.integers(0, 2**31 - 1)).to_numpy()
    )
    perm_corrs[i] = shuffled["first30"].corr(shuffled["last30"])

p_value_perm = float(np.mean(np.abs(perm_corrs) >= abs(real_corr)))
print(f"\nPermutation null (n={n_perm}, same-ticker shuffle): "
      f"mean={perm_corrs.mean():.4f}, std={perm_corrs.std():.4f}")
print(f"Two-sided permutation p-value: {p_value_perm:.4f}")
print(f"Real correlation percentile within null distribution: "
      f"{100*np.mean(perm_corrs < real_corr):.1f}th percentile")
