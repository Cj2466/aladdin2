"""A2 diagnostic: does EDGE carry information ABOUT SPREAD, or is it just the
volatility noise floor wearing a spread's clothes?

The 2026-09-15 synthetic validation showed that at a TRUE spread of zero EDGE
returns roughly 5% of daily volatility as a fake positive spread. If that floor
dominates on real daily bars, then `edge_raw_half_bp` is a volatility proxy and
must not be used to rank tickers by cost.

Test: per ticker, regress log(EDGE raw) on log(daily volatility) and on
log(dollar volume) and log(1/price). If volatility explains nearly all of it and
liquidity adds nothing once volatility is controlled, EDGE is not informative here.
"""
import csv, gzip, os
import numpy as np
import pandas as pd

STORE = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_START = "2025-09-01"

rows = pd.read_csv(os.path.join(HERE, "a2_raw_rows.csv"))
rows = rows.dropna(subset=["edge_raw_half_bp"])
print(f"tickers with an EDGE estimate: {len(rows):,}")

vols = {}
for sym in rows["symbol"]:
    try:
        with gzip.open(os.path.join(STORE, sym + ".csv.gz"), "rt") as fh:
            rd = csv.DictReader(fh)
            cl = [(r["date"], float(r["close"])) for r in rd
                  if r["date"] >= EVAL_START and r["close"] not in ("", "NA")]
    except Exception:
        continue
    if len(cl) < 120:
        continue
    c = np.array([x[1] for x in cl])
    c = c[c > 0]
    if len(c) < 120:
        continue
    r = np.diff(np.log(c))
    r = r[np.abs(r) < np.log(1.8)]          # drop split-like bars
    if len(r) < 100:
        continue
    vols[sym] = float(np.std(r) * 1e4)      # daily vol in bp

rows["daily_vol_bp"] = rows["symbol"].map(vols)
d = rows.dropna(subset=["daily_vol_bp"]).copy()
d = d[(d["edge_raw_half_bp"] > 0) & (d["daily_vol_bp"] > 0) &
      (d["median_dollar_volume"] > 0) & (d["median_close"] > 0)]
print(f"usable for the test: {len(d):,}")

y = np.log(d["edge_raw_half_bp"].to_numpy())
xv = np.log(d["daily_vol_bp"].to_numpy())
xl = np.log(d["median_dollar_volume"].to_numpy())
xp = np.log(1.0 / d["median_close"].to_numpy())

def ols(y, Xcols):
    X = np.column_stack([np.ones(len(y))] + list(Xcols))
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    r2 = 1.0 - resid.var() / y.var()
    return beta, r2

print("\n=== what explains log(EDGE raw half-spread)? ===")
b, r2 = ols(y, [xv])
print(f"  volatility alone        : R^2 = {r2:.4f}   slope on log(vol)     = {b[1]:+.4f}")
b, r2 = ols(y, [xl])
print(f"  dollar volume alone     : R^2 = {r2:.4f}   slope on log($vol)    = {b[1]:+.4f}")
b, r2 = ols(y, [xp])
print(f"  1/price alone           : R^2 = {r2:.4f}   slope on log(1/price) = {b[1]:+.4f}")
b, r2 = ols(y, [xv, xl])
print(f"  volatility + $volume    : R^2 = {r2:.4f}   vol {b[1]:+.4f}  $vol {b[2]:+.4f}")
b, r2 = ols(y, [xv, xl, xp])
print(f"  vol + $volume + 1/price : R^2 = {r2:.4f}   vol {b[1]:+.4f}  $vol {b[2]:+.4f}  1/p {b[3]:+.4f}")

bv, r2v = ols(y, [xv])
resid = y - np.column_stack([np.ones(len(y)), xv]) @ bv
_, r2_extra = ols(resid, [xl])
print(f"\n  incremental R^2 of $volume AFTER volatility is removed: {r2_extra:.4f}")

print("\n=== the pure-noise prediction ===")
print("  synthetic test: at TRUE spread 0, EDGE half-spread ~ 0.5 x (0.05 x daily vol)")
pred = 0.5 * 0.05 * d["daily_vol_bp"]
ratio = d["edge_raw_half_bp"] / pred
print(f"  observed / noise-floor prediction:  median {ratio.median():.2f}   "
      f"p10 {ratio.quantile(0.10):.2f}   p90 {ratio.quantile(0.90):.2f}")
print("  (a median near 1.0 means EDGE is returning the noise floor and nothing more)")

d[["symbol", "median_dollar_volume", "median_close", "daily_vol_bp",
   "tick_floor_half_bp", "edge_raw_half_bp"]].to_csv(
    os.path.join(HERE, "a2_edge_vs_volatility.csv"), index=False)
print("\nwrote a2_edge_vs_volatility.csv")
