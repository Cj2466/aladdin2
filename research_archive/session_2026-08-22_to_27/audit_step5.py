import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.cross_sectional_ivol import build_point_in_time_market_cap

SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, mcap_close, shares, splits = d["close"], d["mcap_close"], d["shares"], d["splits"]
el = pickle.load(open(f"{SP}/audit_elig.pkl","rb")); elig, days = el["elig"], el["days"]

mcap_close = mcap_close.reindex(index=close.index, columns=close.columns)
market_cap, never = build_point_in_time_market_cap(mcap_close, shares, splits)
market_cap.to_pickle(f"{SP}/audit_mcap.pkl")
print("market_cap frame:", market_cap.shape, "| tickers never resolving shares:", len(never))

# Eligible-cell mask (member AND finite close), D1 formation window
E = pd.DataFrame({t: elig[t] for t in close.columns}, index=close.index)
E = E & (pd.Series(days, index=close.index) >= date(2015,1,7)).to_numpy()[:,None]
mc = market_cap.where(E)
vals = mc.stack()
print(f"\neligible cells: {int(E.to_numpy().sum()):,} | with a finite market cap: {len(vals):,}")

LO, HI = 1e9, 6e12   # $1B .. $6T: the plausible range for an S&P 500 member
bad = vals[(vals < LO) | (vals > HI)]
print(f"IMPLAUSIBLE market caps on eligible cells (<$1B or >$6T): {len(bad):,} cells over {bad.index.get_level_values(1).nunique()} tickers")
per = bad.groupby(level=1).agg(n="size", lo="min", hi="max")
per["first"] = bad.reset_index().groupby("level_1")["level_0"].min().dt.date
per["last"]  = bad.reset_index().groupby("level_1")["level_0"].max().dt.date
per = per.sort_values("n", ascending=False)
print(f"\n{'tick':7} {'n_cells':>8} {'min_cap':>12} {'max_cap':>12}  window")
for t,r in per.iterrows():
    print(f"{t:7} {r.n:8} {r.lo/1e9:11.3f}B {r.hi/1e9:11.3f}B  {r['first']}..{r['last']}")
pickle.dump(per, open(f"{SP}/audit_badcaps.pkl","wb"))
