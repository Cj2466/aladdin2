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
shares, splits = d["shares"], d["splits"]
close = pd.read_pickle(f"{SP}/audit_bb_close.pkl")

GRACE = 10
def gate_a(shares, close):
    """CHECK A: refuse share observations dated outside the ticker's own price lifecycle."""
    out, n = {}, 0
    for t, s in shares.items():
        if t not in close.columns: out[t]=s; continue
        px = close[t].dropna()
        if px.empty: out[t]=s; continue
        lo = px.index[0] - pd.Timedelta(days=GRACE); hi = px.index[-1] + pd.Timedelta(days=GRACE)
        idx = pd.DatetimeIndex(s.index)
        keep = (idx >= lo) & (idx <= hi)
        n += int((~keep).sum()); out[t] = s[keep]
    return out, n

sh_a, n_drop = gate_a(shares, close)
print(f"CHECK A dropped {n_drop} share observations outside the price lifecycle")
gone = sorted(t for t in shares if len(sh_a.get(t, [])) != len(shares[t]))
print(f"  tickers affected: {len(gone)} -> {gone}")

MIN_CAP, MAX_CAP = 1e9, 6e12
def gate_b(frame, close):
    """CHECK B: refuse panel cells whose implied market cap is impossible for an S&P 500 member."""
    imp = frame * close
    bad = imp.notna() & ((imp < MIN_CAP) | (imp > MAX_CAP))
    return frame.mask(bad), int(bad.to_numpy().sum()), bad

variants = {}
f0,_ = build_point_in_time_share_counts(close, shares, splits);            variants["control"]=f0
fA,_ = build_point_in_time_share_counts(close, sh_a, splits);              variants["A_lifecycle"]=fA
fB,nb,_ = gate_b(f0, close);                                              variants["B_impliedcap"]=fB
fAB,nab,_ = gate_b(fA, close);                                            variants["A+B"]=fAB
print(f"CHECK B masked {nb} panel cells (control basis), {nab} on top of A")

cfg_base = default_buyback_config()
res = {}
for name, fr in variants.items():
    cfg = default_buyback_config(); cfg.formation_start = date(2018,1,2)
    r = screen_cross_sectional_universe(CrossSectionalData(close=close, shares_outstanding=fr), BUYBACK_FAMILY, cfg)
    res[name] = {x.pattern_id: (x.sharpe_annualized, x.deflated_sharpe.dsr, x.n_formations) for x in r}
    print(f"  ran {name}")
json.dump({k:{p:[v[0],v[1],v[2]] for p,v in d_.items()} for k,d_ in res.items()}, open(f"{SP}/audit_variants.json","w"), indent=1)

specs = sorted(res["control"])
print(f"\n{'spec':28} {'control':>16} {'A_lifecycle':>16} {'B_impliedcap':>16} {'A+B':>16}")
for s in specs:
    row=f"{s:28}"
    for k in ["control","A_lifecycle","B_impliedcap","A+B"]:
        sh_, dsr_, _ = res[k][s]
        row += f"  {sh_:+7.3f}/{(dsr_ if dsr_ is not None else float('nan')):5.3f}"
    print(row)
