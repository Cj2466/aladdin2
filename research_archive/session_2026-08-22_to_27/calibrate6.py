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

print("direct check: what the *signal* endpoints look like, per lookback, from 2018-01-02")
for lb in (126, 252, 504):
    first = frame.shift(lb)
    both = frame.notna() & first.notna() & (frame > 0) & (first > 0)
    identical = both & (frame == first)
    sub = slice("2018-01-02", None)
    n_both = both.loc[sub].sum(axis=1)
    n_id = identical.loc[sub].sum(axis=1)
    print(f"  lb={lb}: mean endpoints-usable/day={n_both.mean():.0f}  "
          f"mean bit-identical endpoints/day={n_id.mean():.1f} ({100*n_id.mean()/n_both.mean():.2f}%)  "
          f"worst={int(n_id.max())} on {n_id.idxmax().date()} (usable that day={int(n_both.loc[n_id.idxmax()])})")

print()
print("what the identical-endpoint refusal costs in leg size (lb=252, decile legs):")
lb = 252
first = frame.shift(lb)
both = frame.notna() & first.notna() & (frame > 0) & (first > 0)
keep = both & (frame != first)
sub = slice("2018-01-02", None)
n_both = both.loc[sub].sum(axis=1)
n_keep = keep.loc[sub].sum(axis=1)
print(f"  n_ranked without refusal: mean={n_both.mean():.0f} min={int(n_both.min())}")
print(f"  n_ranked with    refusal: mean={n_keep.mean():.0f} min={int(n_keep.min())}")
print(f"  decile leg size without={int(n_both.mean()*0.1)} with={int(n_keep.mean()*0.1)}")
print(f"  days where refusal drops n_ranked below 50 (leg<5 -> formation skipped): "
      f"{int((n_keep < 50).sum())} vs {int((n_both < 50).sum())} without")
