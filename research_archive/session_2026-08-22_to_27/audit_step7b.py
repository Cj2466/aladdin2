import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close = d["close"]; mcap_close = d["mcap_close"].reindex(index=close.index, columns=close.columns)
mc = pd.read_pickle(f"{SP}/audit_mcap.pkl"); E = pd.read_pickle(f"{SP}/audit_E.pkl")

imp = (mc/mc.shift(1)) / (mcap_close/mcap_close.shift(1))
mask = E & E.shift(1).fillna(False) & imp.notna() & ((imp>2.0)|(imp<0.5))
h = imp.where(mask).stack().dropna()
print(f"Eligible days with implied overnight share-count change >2x or <0.5x: {len(h)} over {h.index.get_level_values(1).nunique()} tickers\n")
for (dt,t), v in h.items():
    print(f"  {t:7} {str(dt.date()):12} x{v:.5g}")

pr = close/close.shift(1)
pm = E & E.shift(1).fillna(False) & pr.notna() & ((pr>1.6)|(pr<0.4))
p = pr.where(pm).stack().dropna()
print(f"\nEligible days with a single-day price return beyond +60%/-60%: {len(p)} over {p.index.get_level_values(1).nunique()} tickers")
for (dt,t), v in p.items():
    print(f"  {t:7} {str(dt.date()):12} x{v:.4g}")
