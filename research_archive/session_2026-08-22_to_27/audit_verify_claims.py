import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb")); shares, close = d["shares"], d["close"]
for t in ["FOXA","FOX","IR","BNY"]:
    s = shares[t]; px = close[t].dropna()
    print(f"\n{t}: price {px.index[0].date()}..{px.index[-1].date()} | shares {pd.Timestamp(s.index[0]).date()}..{pd.Timestamp(s.index[-1]).date()}")
    pre = s[pd.DatetimeIndex(s.index) < px.index[0]]
    post = s[pd.DatetimeIndex(s.index) >= px.index[0]]
    if len(pre): print(f"   BEFORE first price bar: n={len(pre)} range {pre.min():,.0f}..{pre.max():,.0f}")
    if len(post): print(f"   AFTER  first price bar: n={len(post)} range {post.min():,.0f}..{post.max():,.0f}")
    if len(pre) and len(post):
        print(f"   ratio pre.median/post.median = {pre.median()/post.median():.3f}  -> log issuance if differenced: {-np.log(post.median()/pre.median()):+.3f}")
print("\n--- BNY 2021 step ---")
b = shares["BNY"]; w = b[(b.index>="2021-04-01")&(b.index<="2021-07-01")]
print(w.to_string()); print("  step ratio:", 24608900/12976100, "log issuance signal:", -np.log(24608900/12976100))
