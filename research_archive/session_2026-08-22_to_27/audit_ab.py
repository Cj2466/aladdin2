import sys, pickle, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.cross_sectional import CrossSectionalData, screen_cross_sectional_universe
from app.services.research_lab.cross_sectional_buyback import (
    BUYBACK_FAMILY, default_buyback_config, build_point_in_time_share_counts)
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb")); splits=d["splits"]
close = pd.read_pickle(f"{SP}/audit_bb_close.pkl")
PADDED = pd.Timestamp(date(2018,1,2)-pd.Timedelta(days=800))
shares = {t:s[pd.DatetimeIndex(s.index)>=PADDED] for t,s in d["shares"].items()}
shares = {t:s for t,s in shares.items() if len(s)}
GRACE=10; MIN_CAP, MAX_CAP = 1e9, 6e12
def gate_a(sh):
    out={}
    for t,s in sh.items():
        px = close[t].dropna() if t in close.columns else None
        if px is None or px.empty: out[t]=s; continue
        i=pd.DatetimeIndex(s.index)
        out[t]=s[(i>=px.index[0]-pd.Timedelta(days=GRACE))&(i<=px.index[-1]+pd.Timedelta(days=GRACE))]
    return out
def gate_b(fr):
    imp = fr*close
    bad = imp.notna() & ((imp<MIN_CAP)|(imp>MAX_CAP))
    return fr.mask(bad), bad
def run(fr):
    cfg=default_buyback_config(); cfg.formation_start=date(2018,1,2)
    r=screen_cross_sectional_universe(CrossSectionalData(close=close, shares_outstanding=fr), BUYBACK_FAMILY, cfg)
    return {x.pattern_id:(x.sharpe_annualized, x.deflated_sharpe.dsr) for x in r}
f0,_ = build_point_in_time_share_counts(close, shares, splits)
fA,_ = build_point_in_time_share_counts(close, gate_a(shares), splits)
fB,bB = gate_b(f0); fAB,bAB = gate_b(fA)
print("CHECK B masks", int(bB.to_numpy().sum()), "cells on control;", int(bAB.to_numpy().sum()), "on top of A")
per = bAB.sum(); per=per[per>0].sort_values(ascending=False)
print("  by ticker:", ", ".join(f"{t}({n})" for t,n in per.items()))
out={"control":run(f0),"A":run(fA),"B":run(fB),"A+B":run(fAB)}
json.dump(out, open(f"{SP}/audit_ab.json","w"), indent=1)
print(f"\n{'spec':28} {'control':>15} {'A_lifecycle':>15} {'B_impliedcap':>15} {'A+B (fix)':>15}")
for s in sorted(out["control"]):
    row=f"{s:28}"
    for k in ["control","A","B","A+B"]:
        sh_,ds_=out[k][s]; row+=f"  {sh_:+7.3f}/{(ds_ or float('nan')):5.3f}"
    print(row)
b=max(out["control"], key=lambda s: out["control"][s][0])
print(f"\nbest control spec {b}: {out['control'][b][0]:+.3f}/{out['control'][b][1]:.3f} -> A+B {out['A+B'][b][0]:+.3f}/{out['A+B'][b][1]:.3f}")
