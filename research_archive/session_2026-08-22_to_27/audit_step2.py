import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np

SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, shares = d["close"], d["shares"]

rows=[]
for t in close.columns:
    px = close[t].dropna()
    sh = shares.get(t)
    if px.empty or sh is None or sh.empty: continue
    pf, pl = px.index[0], px.index[-1]
    sf, sl = pd.Timestamp(sh.index[0]), pd.Timestamp(sh.index[-1])
    rows.append(dict(t=t, pf=pf, pl=pl, sf=sf, sl=sl,
                     sh_before_px=(pf-sf).days,      # >0 => shares start BEFORE price exists
                     sh_after_px_end=(pl-sl).days,   # >0 => shares end BEFORE price ends
                     n_sh=len(sh)))
df = pd.DataFrame(rows).set_index("t")
print("priced+shares tickers:", len(df))
print("\n=== shares_first EARLIER than price_first (days). Positive = shares precede any price ===")
print(df["sh_before_px"].describe(percentiles=[.5,.9,.95,.99]).to_string())
bad = df[df["sh_before_px"] > 60].sort_values("sh_before_px", ascending=False)
print(f"\n{len(bad)} ticker(s) with share data starting >60d BEFORE the first price bar:")
for t,r in bad.iterrows():
    print(f"  {t:7} price {r.pf.date()}..{r.pl.date()}   shares {r.sf.date()}..{r.sl.date()}  (shares precede price by {r.sh_before_px}d, {r.n_sh} obs)")

print("\n=== shares series ends long BEFORE price series ends (still-listed ticker, dead share feed) ===")
stale = df[(df["sh_after_px_end"] > 400)].sort_values("sh_after_px_end", ascending=False)
print(f"{len(stale)} ticker(s) with >400d gap:")
for t,r in stale.head(25).iterrows():
    print(f"  {t:7} price ..{r.pl.date()}   shares ..{r.sl.date()}  (gap {r.sh_after_px_end}d)")
df.to_pickle(f"{SP}/audit_ranges.pkl")
