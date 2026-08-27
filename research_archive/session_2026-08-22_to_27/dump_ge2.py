import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.research_lab.cross_sectional_ivol import split_adjust_share_counts  # noqa: E402

OUT = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
splits = pickle.load(open(f"{OUT}/splits.pkl", "rb"))["splits"]
shares = pickle.load(open(f"{OUT}/shares.pkl", "rb"))["shares"]

ge = shares["GE"]
print("GE around the 2023-01-04 (1.281) and 2024-04-02 (1.253) spin-off 'splits':")
print(ge.loc["2022-10-01":"2023-04-01"].to_string())
print("...")
print(ge.loc["2024-01-15":"2024-06-01"].head(12).to_string())

adj = split_adjust_share_counts(ge, splits["GE"])
print()
print("GE adjusted vs raw: largest consecutive-step ratios in the ADJUSTED series")
r = (adj / adj.shift(1)).dropna()
print(r.sort_values().head(4).to_string())
print(r.sort_values().tail(4).to_string())
print()
print("raw series largest steps:")
rr = (ge / ge.shift(1)).dropna()
print(rr.sort_values().head(3).to_string())
print(rr.sort_values().tail(3).to_string())
print()
print("how many GE observations were changed by the adjustment:",
      int((~np.isclose(adj.to_numpy(), ge.to_numpy())).sum()), "of", len(ge))
print("adjusted value on 2021-07-28:", adj.loc["2021-07-28"], " raw:", ge.loc["2021-07-28"])
print("adjusted value on 2021-08-02:", adj.loc["2021-08-02"], " raw:", ge.loc["2021-08-02"])
