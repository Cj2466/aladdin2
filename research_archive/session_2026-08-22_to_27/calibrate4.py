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

for lb in (126, 252, 504):
    w = lb + 1
    first = frame.shift(lb)
    ok = frame.notna() & first.notna() & (frame > 0) & (first > 0)
    cov = frame.notna().rolling(w).sum() >= int(w * 0.8)
    n = (ok & cov).sum(axis=1)
    n = n.loc[n.index >= "2018-01-02"]
    low = n[n < 200]
    print(f"lb={lb}: days below 200 rankable: {len(low)} of {len(n)}")
    if len(low):
        runs = []
        s = None
        p = None
        for d in low.index:
            if s is None:
                s = d
            elif (n.index.get_loc(d) - n.index.get_loc(p)) > 1:
                runs.append((s, p))
                s = d
            p = d
        runs.append((s, p))
        for a, b in runs:
            print(f"     run {a.date()} .. {b.date()}  min={int(n.loc[a:b].min())}")
    n2 = ok.sum(axis=1)
    n2 = n2.loc[n2.index >= "2018-01-02"]
    print(f"     endpoints-only (no 0.8 window guard): min={int(n2.min())} on {n2.idxmin().date()}, "
          f"days<200: {int((n2 < 200).sum())}")
    print()
