import sys, pickle, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.cross_sectional import CrossSectionalData, screen_cross_sectional_universe
from app.services.research_lab.cross_sectional_buyback import (
    BUYBACK_FAMILY, default_buyback_config, build_point_in_time_share_counts, count_split_adjustments)
from app.services.research_lab.cross_sectional_ivol import (
    restrict_share_counts_to_price_lifecycle, implausible_market_cap_mask)
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb")); splits=d["splits"]
close = pd.read_pickle(f"{SP}/audit_bb_close.pkl")
PADDED = pd.Timestamp(date(2018,1,2)-pd.Timedelta(days=800))
shares = {t:s[pd.DatetimeIndex(s.index)>=PADDED] for t,s in d["shares"].items()}
shares = {t:s for t,s in shares.items() if len(s)}

def run(fr):
    cfg=default_buyback_config(); cfg.formation_start=date(2018,1,2)
    r=screen_cross_sectional_universe(CrossSectionalData(close=close, shares_outstanding=fr), BUYBACK_FAMILY, cfg)
    return {x.pattern_id:(x.sharpe_annualized, x.deflated_sharpe.dsr) for x in r}

before,_ = build_point_in_time_share_counts(close, shares, splits)
sh2, dropped = restrict_share_counts_to_price_lifecycle(shares, close)
after,_ = build_point_in_time_share_counts(close, sh2, splits)
mask = implausible_market_cap_mask(after * close)
after = after.mask(mask)
n_out = sum(dropped.values()); n_cells = int(mask.to_numpy().sum())
print(f"SHIPPED CHECKS on the real production fetch:")
print(f"  lifecycle: {n_out} observations dropped across {len(dropped)} tickers -> {sorted(dropped)}")
print(f"  magnitude: {n_cells} panel cells refused across {int((mask.to_numpy().sum(axis=0)>0).sum())} tickers")
per = mask.sum(); per=per[per>0].sort_values(ascending=False)
print("     " + ", ".join(f"{t}({n})" for t,n in per.head(12).items()))
b, a = run(before), run(after)
json.dump({"before":b,"after":a}, open(f"{SP}/audit_final.json","w"), indent=1)
print(f"\n{'spec':30} {'BEFORE (shipped prod)':>22} {'AFTER (fixed)':>20}   dSharpe")
for s in sorted(b):
    print(f"{s:30}   {b[s][0]:+7.3f} / DSR {(b[s][1] or float('nan')):5.3f}   {a[s][0]:+7.3f} / {(a[s][1] or float('nan')):5.3f}   {a[s][0]-b[s][0]:+.3f}")
bb=max(b,key=lambda s:b[s][0]); ba=max(a,key=lambda s:a[s][0])
print(f"\nbest BEFORE: {bb} {b[bb][0]:+.3f} DSR {b[bb][1]:.3f}")
print(f"best AFTER : {ba} {a[ba][0]:+.3f} DSR {a[ba][1]:.3f}")
print(f"positive raw Sharpe: before {sum(1 for s in b if b[s][0]>0)}/14, after {sum(1 for s in a if a[s][0]>0)}/14")
print(f"DSR>0.5: before {sum(1 for s in b if (b[s][1] or 0)>0.5)}/14, after {sum(1 for s in a if (a[s][1] or 0)>0.5)}/14")
mono = all(a[f"nsi_l504_{p}_h{h}"][0] > a[f"nsi_l252_{p}_h{h}"][0] > a[f"nsi_l126_{p}_h{h}"][0]
           for p in ["ls","hedged"] for h in [126,252])
print("lookback monotonicity (504>252>126 in every portfolio/hold cell) after fix:", mono)
