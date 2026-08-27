import sys, pickle, json, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.cross_sectional import CrossSectionalData, CrossSectionalConfig, screen_cross_sectional_universe
from app.services.research_lab.cross_sectional_ivol import ROUND_D1_FAMILY, build_point_in_time_market_cap
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, shares, splits = d["close"], d["shares"], d["splits"]
mcap_close = d["mcap_close"].reindex(index=close.index, columns=close.columns)
GRACE=10; MIN_CAP,MAX_CAP=1e9,6e12
def gate_a(sh):
    out={}
    for t,s in sh.items():
        px = close[t].dropna() if t in close.columns else None
        if px is None or px.empty: out[t]=s; continue
        i=pd.DatetimeIndex(s.index)
        out[t]=s[(i>=px.index[0]-pd.Timedelta(days=GRACE))&(i<=px.index[-1]+pd.Timedelta(days=GRACE))]
    return out
def run(mc, label):
    cfg=CrossSectionalConfig(); cfg.formation_start=date(2015,1,7)
    t0=time.time()
    r=screen_cross_sectional_universe(CrossSectionalData(close=close, market_cap=mc), ROUND_D1_FAMILY, cfg)
    print(f"  {label}: {time.time()-t0:.0f}s")
    return {x.pattern_id:(x.sharpe_annualized, x.deflated_sharpe.dsr, x.n_value_weighted_legs, x.n_value_weight_fallbacks) for x in r}
mc0,_ = build_point_in_time_market_cap(mcap_close, shares, splits)
mcA,_ = build_point_in_time_market_cap(mcap_close, gate_a(shares), splits)
def gate_b(mc):
    bad = mc.notna() & ((mc<MIN_CAP)|(mc>MAX_CAP)); return mc.mask(bad), int(bad.to_numpy().sum())
mcAB, nb = gate_b(mcA); print("check B masks", nb, "market-cap cells on top of A")
out={"control":run(mc0,"control"), "A+B":run(mcAB,"A+B")}
json.dump(out, open(f"{SP}/audit_d1_out.json","w"), indent=1)
prod = {r["pattern_id"]:(r["sharpe_annualized"], r["dsr"], r["n_value_weighted_legs"], r["n_value_weight_fallbacks"])
        for r in json.load(open(f"{SP}/d1_production_result_fixed.json"))["results"]}
print(f"\n{'spec':34} {'PRODUCTION':>21} {'control(repro)':>21} {'A+B (fix)':>21}")
for s in sorted(out["control"]):
    p=prod.get(s); c=out["control"][s]; f=out["A+B"][s]
    ps = f"{p[0]:+6.3f}/{(p[1] if p[1] is not None else float('nan')):5.3f}/{p[3]:4}" if p else " "*18
    print(f"{s:34} {ps:>21}  {c[0]:+6.3f}/{(c[1] or float('nan')):5.3f}/{c[3]:4}  {f[0]:+6.3f}/{(f[1] or float('nan')):5.3f}/{f[3]:4}")
