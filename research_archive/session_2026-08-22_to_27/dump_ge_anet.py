import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")
import pandas as pd  # noqa: E402

OUT = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
splits = pickle.load(open(f"{OUT}/splits.pkl", "rb"))["splits"]
shares = pickle.load(open(f"{OUT}/shares.pkl", "rb"))["shares"]

for t in ("GE", "ANET"):
    s = shares[t]
    sub = s.loc["2020-11-01":"2022-03-01"]
    print(f"--- {t} shares 2020-11..2022-03 ({len(sub)} rows) ---")
    for d, v in sub.items():
        print(f'   ("{d.date()}", {v!r}),')
    print(f"--- {t} splits (all) ---")
    for d, v in splits.get(t, pd.Series(dtype=float)).items():
        print(f'   ("{d.date()}", {float(v)!r}),')
