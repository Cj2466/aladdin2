"""Cross-endpoint contamination audit of the S&P 600 IVOL family, using the
SAME two checks already built for D1/Buyback (imported, not reimplemented).
"""
import pickle
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.research_lab.cross_sectional_ivol import (  # noqa: E402
    CROSS_ENDPOINT_PRICE_GRACE_DAYS,
    build_point_in_time_market_cap,
    implausible_market_cap_mask,
    restrict_share_counts_to_price_lifecycle,
)
from app.services.research_lab.small_cap_membership_history import (  # noqa: E402
    get_membership_intervals,
)

HERE = Path(__file__).parent
with (HERE / "sc600_fetch.pkl").open("rb") as fh:
    D = pickle.load(fh)

close = D["close"]
mcap_close = D["mcap_close"]
splits = D["splits"]
shares = D["shares"]
START = D["start"]

# reindex mcap_close exactly as the production entry point does
mcap_close = (
    pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    if mcap_close.empty
    else mcap_close.reindex(index=close.index, columns=close.columns)
)

print(f"priced tickers: {len(close.columns)}   rows: {len(close)}")
print(f"share series resolved: {len(shares)}   missing: {len(D['missing_shares'])}")
print(f"recycled dropped by mask_recycled_ticker_prices: {len(D['recycled'])} -> {D['recycled']}")
print(f"truncated: {len(D['truncated'])}")
print()

# ---------------------------------------------------------------- TIME AXIS
restricted, dropped = restrict_share_counts_to_price_lifecycle(shares, close)
n_dropped_obs = sum(dropped.values())
print("=" * 78)
print(f"TIME AXIS (restrict_share_counts_to_price_lifecycle, grace={CROSS_ENDPOINT_PRICE_GRACE_DAYS}d)")
print(f"  {n_dropped_obs} observation(s) dropped across {len(dropped)} ticker(s) "
      f"of {len(close.columns)} priced ({100*len(dropped)/len(close.columns):.2f}%)")
print("=" * 78)

rows = []
for ticker, n in sorted(dropped.items(), key=lambda kv: -kv[1]):
    raw = shares[ticker]
    priced_days = close[ticker].dropna()
    first_price, last_price = priced_days.index[0], priced_days.index[-1]
    kept = restricted[ticker]
    lead_gap = (first_price - raw.index[0]).days
    spans = get_membership_intervals(ticker)
    rows.append(
        {
            "ticker": ticker,
            "n_dropped": n,
            "n_total_obs": len(raw),
            "n_kept": len(kept),
            "shares_first_date": raw.index[0].date(),
            "shares_first_val": float(raw.iloc[0]),
            "price_first": first_price.date(),
            "price_last": last_price.date(),
            "lead_gap_days": lead_gap,
            "kept_first_val": float(kept.iloc[0]) if len(kept) else np.nan,
            "membership": spans,
        }
    )
det = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 300)
if len(det):
    print(det.drop(columns=["membership"]).to_string(index=False))
    print()
    print("  membership intervals:")
    for r in rows:
        print(f"    {r['ticker']:6s} {r['membership']}")
print()

# threshold sweep, so the >60d figure quoted for D1 is comparable
for thresh in (10, 30, 60, 90, 180, 365):
    n = 0
    for ticker in close.columns:
        raw = shares.get(ticker)
        if raw is None or raw.empty:
            continue
        pd_days = close[ticker].dropna()
        if pd_days.empty:
            continue
        if (pd_days.index[0] - raw.index[0]).days > thresh:
            n += 1
    print(f"  share history begins >{thresh:4d} days before first price bar: {n:4d} tickers "
          f"({100*n/len(close.columns):.2f}% of {len(close.columns)} priced)")
print()

# ----------------------------------------------------------- MAGNITUDE AXIS
mcap_before, no_shares_before = build_point_in_time_market_cap(mcap_close, shares, splits)
mcap_after_time, no_shares_after = build_point_in_time_market_cap(mcap_close, restricted, splits)

# eligibility: point-in-time member with a finite close, exactly the cells the
# harness can actually read
elig = pd.DataFrame(False, index=close.index, columns=close.columns)
for ticker in close.columns:
    spans = get_membership_intervals(ticker)
    if not spans:
        continue
    col = np.zeros(len(close.index), dtype=bool)
    idx_dates = close.index.date
    for started, ended in spans:
        col |= (idx_dates >= started) & ((idx_dates < ended) if ended is not None else True)
    elig[ticker] = col
elig &= close.notna()
# formations only happen from START onward
elig.loc[elig.index.date < START] = False
print(f"eligible (member & priced & >= {START}) cells: {int(elig.to_numpy().sum()):,}")

vals = mcap_before.where(elig).to_numpy().ravel()
vals = vals[np.isfinite(vals)]
print(f"eligible cells WITH a market cap: {len(vals):,} "
      f"({100*len(vals)/int(elig.to_numpy().sum()):.1f}% of eligible)")
qs = [0.0, 0.001, 0.005, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.995, 0.999, 1.0]
print("  market-cap distribution over eligible cells (USD bn):")
for q in qs:
    print(f"    p{q*100:7.3f}: {np.quantile(vals, q)/1e9:14.4f}")
print()

with (HERE / "audit_stage1.pkl").open("wb") as fh:
    pickle.dump(
        {
            "dropped": dropped,
            "detail_rows": rows,
            "restricted": restricted,
            "mcap_before": mcap_before,
            "mcap_after_time": mcap_after_time,
            "elig": elig,
            "no_shares_before": no_shares_before,
            "no_shares_after": no_shares_after,
        },
        fh,
    )
print("saved audit_stage1.pkl")
