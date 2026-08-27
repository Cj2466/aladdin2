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

lb = 252
earlier = frame.shift(lb)
both = frame.notna() & earlier.notna() & (frame > 0) & (earlier > 0)
keep = both & (frame != earlier)
sub = slice("2018-01-02", None)
n_both = both.loc[sub].sum(axis=1)
n_keep = keep.loc[sub].sum(axis=1)

lost = n_keep[(n_keep < 50) & (n_both >= 50)]
print(f"days pushed below 50 ranked BY the refusal: {len(lost)}")
print("their date range:", lost.index.min().date() if len(lost) else None,
      "..", lost.index.max().date() if len(lost) else None)
print("by month:", dict(lost.groupby(lost.index.to_period("M")).size()))
print()
already = n_both[n_both < 50]
print(f"days already below 50 WITHOUT the refusal: {len(already)}  range "
      f"{already.index.min().date()} .. {already.index.max().date()}")
print()
print(f"total days below 50 WITH refusal: {int((n_keep < 50).sum())}; WITHOUT: {int((n_both < 50).sum())}")
