import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.research_lab.cross_sectional_buyback import (  # noqa: E402
    build_point_in_time_share_counts,
)

OUT = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
close = pickle.load(open(f"{OUT}/close.pkl", "rb"))["close"]
splits = pickle.load(open(f"{OUT}/splits.pkl", "rb"))["splits"]
shares = pickle.load(open(f"{OUT}/shares.pkl", "rb"))["shares"]

print("=" * 78)
print("A. the 20 tickers whose share series predates 2015-10-01")
print("=" * 78)
firsts = pd.Series({t: s.index[0] for t, s in shares.items() if not s.empty})
early = firsts[firsts < pd.Timestamp("2015-10-01")].sort_values()
for t, d in early.items():
    print(f"   {t}: first={d.date()}  n_before_2015_10={int((shares[t].index < pd.Timestamp('2015-10-01')).sum())}  n_total={len(shares[t])}")

print()
print("=" * 78)
print("B. staleness cap cost, measured in PANEL CELLS and RANKABLE TICKERS")
print("=" * 78)
for cap in (130, 200, 400, 730, 100000):
    frame, unusable = build_point_in_time_share_counts(close, shares, splits, max_staleness_days=cap)
    populated = frame.notna()
    # rankable on a date = populated
    by_year = populated.sum(axis=1).groupby(frame.index.year).mean()
    print(f"cap={cap:6d}: unusable_tickers={len(unusable):3d} populated_cells={populated.to_numpy().sum():8d} "
          f"({100*populated.to_numpy().mean():.1f}%)")
    print("            mean rankable tickers/day by year:",
          {int(y): int(v) for y, v in by_year.items()})

print()
print("=" * 78)
print("C. coverage of the ACTUAL SIGNAL per lookback, at max_staleness=400")
print("=" * 78)
frame, _ = build_point_in_time_share_counts(close, shares, splits)
for lb in (126, 252, 504):
    w = lb + 1
    first = frame.shift(lb)
    ok = frame.notna() & first.notna() & (frame > 0) & (first > 0)
    # coverage floor over the window
    cov = frame.notna().rolling(w).sum() >= int(w * 0.8)
    usable = ok & cov
    by_year = usable.sum(axis=1).groupby(frame.index.year).mean()
    print(f"lookback={lb}: mean names with a usable signal per day, by year:",
          {int(y): int(v) for y, v in by_year.items()})

print()
print("=" * 78)
print("D. earliest date >=50 names have a usable 504d signal (deciles need 2x5 min)")
print("=" * 78)
for lb in (126, 252, 504):
    w = lb + 1
    first = frame.shift(lb)
    ok = frame.notna() & first.notna() & (frame > 0) & (first > 0)
    cov = frame.notna().rolling(w).sum() >= int(w * 0.8)
    n = (ok & cov).sum(axis=1)
    for thresh in (50, 100, 200, 300):
        hit = n[n >= thresh]
        print(f"   lookback={lb} first date with >={thresh} rankable: "
              f"{hit.index[0].date() if len(hit) else 'never'}")
