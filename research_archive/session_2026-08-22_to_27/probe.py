import sys, json, hashlib
import numpy as np, pandas as pd
sys.path.insert(0, sys.argv[1])
from app.services.research_lab import cross_sectional as cs

rng = np.random.default_rng(7)
n_days, tickers = 500, [f"T{i}" for i in range(12)]
idx = pd.bdate_range("2015-01-05", periods=n_days)
px = pd.DataFrame(100*np.exp(np.cumsum(rng.normal(0,0.01,(n_days,len(tickers))),axis=0)), index=idx, columns=tickers)
vol = pd.DataFrame(rng.uniform(1e6,5e6,(n_days,len(tickers))), index=idx, columns=tickers)
data = cs.CrossSectionalData(close=px, open=px*0.999, volume=vol)

def sig(d):
    c = d.close
    return (c.iloc[-1]/c.iloc[-21] - 1.0)

out = {}
allmem = lambda t, on: True
for pf in ("long_short","long_universe_hedged"):
    spec = cs.CrossSectionalSpec(pattern_id=f"p_{pf}", family="fam", citation="cit",
        signal_fn=sig, lookback_days=60, holding_days=21, rank_fraction=0.2, portfolio=pf)
    cfg = cs.CrossSectionalConfig(cost_bps=10.0, min_names_per_leg=2)
    r = cs.run_cross_sectional_backtest(data, spec, cfg, allmem)
    out[pf] = dict(status=r.status, cost=round(r.total_cost,12), n=len(r.daily_returns),
        rets=hashlib.sha256(np.asarray(r.daily_returns.values,dtype=float).tobytes()).hexdigest(),
        idxh=hashlib.sha256(str(list(r.daily_returns.index)).encode()).hexdigest(),
        forms=hashlib.sha256(json.dumps([[str(f.date),f.n_eligible,sorted(f.long_tickers),sorted(f.short_tickers),f.skipped_reason] for f in r.formations],sort_keys=True).encode()).hexdigest())
# screening pass
specs=[cs.CrossSectionalSpec(pattern_id=f"s{k}",family="fam",citation="c",signal_fn=sig,lookback_days=60,holding_days=h,rank_fraction=0.25,portfolio="long_short") for k,h in enumerate((5,10,21))]
res = cs.screen_cross_sectional_universe(data, specs, cs.CrossSectionalConfig(cost_bps=5.0,min_names_per_leg=2), allmem)
out["screen"]=[[r.pattern_id, round(r.sharpe_annualized,10), r.n_formations, round(r.total_cost_drag,12), repr(r.deflated_sharpe)] for r in res]
print(json.dumps(out, sort_keys=True))
