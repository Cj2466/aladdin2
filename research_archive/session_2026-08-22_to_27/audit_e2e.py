import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.cross_sectional_buyback import run_buyback_screening
from app.services.research_lab.cross_sectional_ivol import run_round_d1_screening
from app.services.research_lab.cross_sectional import CrossSectionalConfig
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))

class Replay:
    """Serves Build D1's own saved production fetch — real yfinance data,
    no network. The exact bytes both families were screened on tonight."""
    def __init__(s): s.close, s.mcap, s.shares, s.splits = d["close"], d["mcap_close"], d["shares"], d["splits"]
    def _cut(s, fr, tickers, start, end):
        cols=[t for t in tickers if t in fr.columns]
        sub=fr.loc[(fr.index>=pd.Timestamp(start))&(fr.index<pd.Timestamp(end)), cols].dropna(axis=1, how="all")
        return sub, [t for t in tickers if t not in sub.columns]
    def get_price_history(s,t,a,b): return s._cut(s.close,t,a,b)
    def get_market_cap_basis(s,t,a,b):
        c,m = s._cut(s.mcap,t,a,b); return c, {k:v for k,v in s.splits.items() if k in c.columns}, m
    def get_shares_outstanding(s,t,a,b):
        out={}
        for k in t:
            v=s.shares.get(k)
            if v is None or v.empty: continue
            i=pd.DatetimeIndex(v.index); w=v[(i>=pd.Timestamp(a))&(i<pd.Timestamp(b))]
            if len(w): out[k]=w
        return out, [k for k in t if k not in out]

print("=== BUYBACK, through the shipped entry point ===")
s = run_buyback_screening(start=date(2018,1,2), end=date(2026,8,26), provider=Replay())
print(f"  universe {s.universe_size}, missing price {len(s.missing_price_data)}, no share history {len(s.tickers_without_share_history)}")
print(f"  lifecycle refusals: {s.n_share_observations_outside_price_lifecycle} obs")
print(f"  magnitude refusals: {s.n_implausible_market_cap_cells} cells")
print(f"  split correction: {s.n_tickers_with_splits} tickers / {s.n_split_adjusted_observations} obs restated")
print(f"  median share-count age {s.median_signal_endpoint_age_days:.0f}d")
for r in s.results[:4]:
    print(f"    {r.pattern_id:26} sharpe {r.sharpe_annualized:+.3f}  dsr {r.deflated_sharpe.dsr:.3f}")
print("  disclosure has defect-3 line:", "CROSS-ENDPOINT CONSISTENCY (defect 3" in s.disclosure)
for w in s.warnings: print("    WARN:", w[:150])

print("\n=== BUILD D1, through the shipped entry point ===")
res, miss, no_shares = run_round_d1_screening(date(2015,1,7), date(2026,8,26), provider=Replay(), config=CrossSectionalConfig())
print(f"  {len(res)} results, missing price {len(miss)}, without shares {len(no_shares)}")
print(f"  all negative: {all(r.sharpe_annualized < 0 for r in res)}  | max sharpe {max(r.sharpe_annualized for r in res):+.3f}")
print(f"  max dsr {max((r.deflated_sharpe.dsr or 0) for r in res):.3f}  | any dsr_floor_met: {any(r.deflated_sharpe.dsr_floor_met for r in res)}")
for r in res[:3]:
    print(f"    {r.pattern_id:30} sharpe {r.sharpe_annualized:+.3f} vw_legs {r.n_value_weighted_legs} fallbacks {r.n_value_weight_fallbacks}")
