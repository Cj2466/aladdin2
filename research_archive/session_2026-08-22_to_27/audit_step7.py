import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, mcap_close = d["close"], d["mcap_close"].reindex(index=d["close"].index, columns=d["close"].columns)
mc = pd.read_pickle(f"{SP}/audit_mcap.pkl"); E = pd.read_pickle(f"{SP}/audit_E.pkl")

cap_r = (mc / mc.shift(1))
px_r  = (mcap_close / mcap_close.shift(1))
# implied share-count change = cap ratio / price ratio; a real share count cannot
# double or halve overnight -> anything beyond is a basis/entity break.
imp = cap_r / px_r
mask = E & E.shift(1).fillna(False) & imp.notna() & ((imp > 2.0) | (imp < 0.5))
hits = imp.where(mask).stack().dropna().rename("implied_share_ratio").reset_index()
hits.columns = ["dt","tick","ratio"]
print(f"Eligible-cell days where the implied share count jumped >2x or <0.5x overnight: {len(hits)} over {hits.tick.nunique()} tickers\n")
for t, g in hits.groupby("tick"):
    print(f"  {t:7} {len(g):3} event(s): " + ", ".join(f"{r.dt.date()} x{r.ratio:.4g}" for _,r in g.iterrows()))

# --- price-series splices: a return beyond +/- 60% on an eligible day
pr = (close / close.shift(1))
pm = E & E.shift(1).fillna(False) & pr.notna() & ((pr > 1.6) | (pr < 0.4))
ph = pr.where(pm).stack().dropna().reset_index(); ph.columns=["dt","tick","ratio"]
print(f"\nEligible-cell single-day price returns beyond +60%/-60%: {len(ph)} over {ph.tick.nunique()} tickers")
for t,g in ph.groupby("tick"):
    print(f"  {t:7} " + ", ".join(f"{r.dt.date()} x{r.ratio:.3g}" for _,r in g.iterrows()))
