import sys, pickle, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.cross_sectional import CrossSectionalData, screen_cross_sectional_universe
from app.services.research_lab.cross_sectional_buyback import (
    BUYBACK_FAMILY, default_buyback_config, build_point_in_time_share_counts)
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
splits = d["splits"]
close = pd.read_pickle(f"{SP}/audit_bb_close.pkl")
PADDED = pd.Timestamp(date(2018,1,2) - pd.Timedelta(days=800))
# FAITHFUL control: restrict the shares dict to buyback's own fetch window, as production did.
shares = {t: s[pd.DatetimeIndex(s.index) >= PADDED] for t,s in d["shares"].items()}
shares = {t:s for t,s in shares.items() if len(s)}
print("padded_start", PADDED.date(), "| tickers with shares in window:", len(shares))

GRACE = 10
def gate_a(sh, close, only=None):
    out, touched = {}, []
    for t, s in sh.items():
        if t not in close.columns or (only is not None and t not in only): out[t]=s; continue
        px = close[t].dropna()
        if px.empty: out[t]=s; continue
        lo, hi = px.index[0]-pd.Timedelta(days=GRACE), px.index[-1]+pd.Timedelta(days=GRACE)
        idx = pd.DatetimeIndex(s.index); keep=(idx>=lo)&(idx<=hi)
        if (~keep).any(): touched.append(t)
        out[t]=s[keep]
    return out, touched

def run(fr, label):
    cfg = default_buyback_config(); cfg.formation_start = date(2018,1,2)
    r = screen_cross_sectional_universe(CrossSectionalData(close=close, shares_outstanding=fr), BUYBACK_FAMILY, cfg)
    return {x.pattern_id:(x.sharpe_annualized, x.deflated_sharpe.dsr) for x in r}

f0,_ = build_point_in_time_share_counts(close, shares, splits)
shA, touched = gate_a(shares, close)
print(f"CHECK A (faithful window) touches {len(touched)} tickers: {sorted(touched)}")
fA,_ = build_point_in_time_share_counts(close, shA, splits)

CONFIRMED = {"FOX","FOXA","IR","PARA","DOW","STI","SBNY","BNY","COL","MRNA","UA","SOLS","Q","SNDK","AVB","EQR","EA","APC","CSRA","FB","INFO","LB","NFX","TE","NE"}
shA_conf,_ = gate_a(shares, close, only=CONFIRMED)
fA_conf,_ = build_point_in_time_share_counts(close, shA_conf, splits)
shA_rest,_ = gate_a(shares, close, only=set(shares)-CONFIRMED)
fA_rest,_ = build_point_in_time_share_counts(close, shA_rest, splits)

out = {"control": run(f0,"c"), "A_all": run(fA,"a"),
       "A_confirmed_only": run(fA_conf,"ac"), "A_others_only": run(fA_rest,"ar")}
json.dump(out, open(f"{SP}/audit_decomp.json","w"), indent=1)
print(f"\n{'spec':28} {'control':>15} {'A_all':>15} {'A_confirmed':>15} {'A_others':>15}")
for s in sorted(out["control"]):
    row=f"{s:28}"
    for k in ["control","A_all","A_confirmed_only","A_others_only"]:
        sh_,dsr_ = out[k][s]; row += f"  {sh_:+7.3f}/{(dsr_ or float('nan')):5.3f}"
    print(row)
