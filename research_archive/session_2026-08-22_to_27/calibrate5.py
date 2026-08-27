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
frame, _ = build_point_in_time_share_counts(close, shares, splits)

print("raw panel coverage (populated tickers per day), monthly mean, 2017-2020:")
cov = frame.notna().sum(axis=1)
print(cov.loc["2017-01":"2020-12"].resample("ME").mean().round(0).to_string())

print()
print("=" * 78)
print("STALE-ENDPOINT ZEROS: how often does a window contain NO new filing?")
print("=" * 78)
for lb in (126, 252, 504):
    first = frame.shift(lb)
    ok = frame.notna() & first.notna() & (frame > 0) & (first > 0)
    # no new filing in the window <=> the step series never changed value in it
    changed = (frame.diff() != 0) & frame.notna() & frame.shift(1).notna()
    n_changes = changed.rolling(lb + 1).sum()
    stale = ok & (n_changes.fillna(0) == 0)
    n_ok = ok.sum(axis=1)
    n_stale = stale.sum(axis=1)
    sub = slice("2018-01-02", None)
    print(f"lb={lb}: mean rankable={n_ok.loc[sub].mean():.0f}  "
          f"mean with NO new filing in window={n_stale.loc[sub].mean():.1f} "
          f"({100*n_stale.loc[sub].mean()/max(n_ok.loc[sub].mean(),1):.2f}%)  "
          f"worst day={int(n_stale.loc[sub].max())} on {n_stale.loc[sub].idxmax().date()}")
    # do those stale ones actually read exactly 0?
    with np.errstate(divide="ignore", invalid="ignore"):
        sig = -np.log(frame / first)
    z = (sig.abs() < 1e-12) & ok
    print(f"        cells reading EXACTLY 0.0: mean/day={z.loc[sub].sum(axis=1).mean():.1f}")
