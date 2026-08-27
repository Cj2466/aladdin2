import sys, pickle, time, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.cross_sectional import CrossSectionalData, screen_cross_sectional_universe
from app.services.research_lab.cross_sectional_buyback import BUYBACK_FAMILY, default_buyback_config
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
frame = pd.read_pickle(f"{SP}/audit_bb_shares.pkl"); close = pd.read_pickle(f"{SP}/audit_bb_close.pkl")
cfg = default_buyback_config(); cfg.formation_start = date(2018,1,2)
t0=time.time()
res = screen_cross_sectional_universe(CrossSectionalData(close=close, shares_outstanding=frame), BUYBACK_FAMILY, cfg)
print(f"elapsed {time.time()-t0:.0f}s")
out = {r.pattern_id: dict(sharpe=r.sharpe_annualized, dsr=r.deflated_sharpe.dsr, n_form=r.n_formations,
                          skipped=r.n_skipped_formations, avg_leg=r.avg_names_per_leg) for r in res}
json.dump(out, open(f"{SP}/audit_control.json","w"), indent=1)
print(f"{'spec':28} {'sharpe':>8} {'dsr':>7} {'n_form':>7} {'avg_leg':>8}")
for k,v in sorted(out.items()):
    print(f"{k:28} {v['sharpe']:+8.3f} {(v["dsr"] if v["dsr"] is not None else float("nan")):7.3f} {v['n_form']:7} {v['avg_leg']:8.1f}")
