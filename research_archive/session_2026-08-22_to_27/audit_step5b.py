import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date

SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close = d["close"]
market_cap = pd.read_pickle(f"{SP}/audit_mcap.pkl")
el = pickle.load(open(f"{SP}/audit_elig.pkl","rb")); elig, days = el["elig"], el["days"]

E = pd.DataFrame({t: np.asarray(elig[t], dtype=bool) for t in close.columns}, index=close.index)
in_win = pd.Series(days >= date(2015,1,7), index=close.index)
E = E.mul(in_win, axis=0).astype(bool)
print("eligible (member & priced) cells in D1 window:", int(E.to_numpy().sum()))

mc = market_cap.where(E)
vals = mc.stack().rename("cap")
print("eligible cells carrying a finite market cap:", len(vals))

LO, HI = 1e9, 6e12
bad = vals[(vals < LO) | (vals > HI)].reset_index()
bad.columns = ["dt","tick","cap"]
print(f"\nIMPLAUSIBLE (<$1B or >$6T) on eligible cells: {len(bad)} cells over {bad.tick.nunique()} tickers")
g = bad.groupby("tick").agg(n=("cap","size"), lo=("cap","min"), hi=("cap","max"),
                            first=("dt","min"), last=("dt","max")).sort_values("n", ascending=False)
print(f"\n{'tick':7} {'n_cells':>8} {'min_cap':>13} {'max_cap':>13}  window")
for t,r in g.iterrows():
    print(f"{t:7} {r.n:8} {r.lo/1e9:12.4f}B {r.hi/1e9:12.4f}B  {r['first'].date()}..{r['last'].date()}")
bad.to_pickle(f"{SP}/audit_badcells.pkl"); E.to_pickle(f"{SP}/audit_E.pkl")
