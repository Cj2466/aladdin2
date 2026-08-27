import sys, pickle, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.cross_sectional import CrossSectionalData, CrossSectionalConfig, screen_cross_sectional_universe
from app.services.research_lab.cross_sectional_ivol import (
    ROUND_D1_FAMILY, build_point_in_time_market_cap,
    restrict_share_counts_to_price_lifecycle, implausible_market_cap_mask)
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, shares, splits = d["close"], d["shares"], d["splits"]
mcap_close = d["mcap_close"].reindex(index=close.index, columns=close.columns)
def run(mc):
    cfg=CrossSectionalConfig(); cfg.formation_start=date(2015,1,7)
    r=screen_cross_sectional_universe(CrossSectionalData(close=close, market_cap=mc), ROUND_D1_FAMILY, cfg)
    return {x.pattern_id:(x.sharpe_annualized, x.deflated_sharpe.dsr) for x in r}
before,_ = build_point_in_time_market_cap(mcap_close, shares, splits)
sh2, dropped = restrict_share_counts_to_price_lifecycle(shares, close)
after,_ = build_point_in_time_market_cap(mcap_close, sh2, splits)
mask = implausible_market_cap_mask(after); after = after.mask(mask)
b,a = run(before), run(after)
prod = {r["pattern_id"]: r["sharpe_annualized"] for r in json.load(open(f"{SP}/d1_production_result_fixed.json"))["results"]}
deltas = sorted(((a[s][0]-b[s][0], s) for s in b), key=lambda x: -abs(x[0]))
print(f"lifecycle dropped {sum(dropped.values())} obs / {len(dropped)} tickers; magnitude masked {int(mask.to_numpy().sum())} cells")
print(f"control == shipped production for all 21: {all(abs(b[s][0]-prod[s])<5e-4 for s in b)}")
print(f"all 21 negative before: {all(v[0]<0 for v in b.values())} | after: {all(v[0]<0 for v in a.values())}")
print(f"max DSR before {max(v[1] or 0 for v in b.values()):.3f} | after {max(v[1] or 0 for v in a.values()):.3f}")
print("\nlargest movements:")
for dv, s in deltas[:5]:
    print(f"  {s:32} {b[s][0]:+.3f} -> {a[s][0]:+.3f}  ({dv:+.3f})")
