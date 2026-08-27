import sys, numpy as np, pandas as pd
from datetime import date
sys.path.insert(0,"/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from app.services.research_lab import cross_sectional as cs

# (1) fixed_universe_membership
m = cs.fixed_universe_membership(["AGG","LQD","TLT"])
print("member all dates:", all(m(t,date(y,1,3)) for t in ["AGG","LQD","TLT"] for y in (1990,2005,2026,2099)))
print("non-member False:", m("SPY",date(2020,1,1)), "case-sensitive:", m("agg",date(2020,1,1)))
try:
    cs.fixed_universe_membership([]); print("EMPTY: NOT REJECTED (BAD)")
except ValueError as e: print("empty rejected OK")
print("generator ok:", cs.fixed_universe_membership(t for t in ["A","B"])("B",date(2020,1,1)))

rng=np.random.default_rng(3); n=400; tk=[f"E{i}" for i in range(10)]
idx=pd.bdate_range("2018-01-02",periods=n)
px=pd.DataFrame(100*np.exp(np.cumsum(rng.normal(0,0.01,(n,len(tk))),axis=0)),index=idx,columns=tk)
data=cs.CrossSectionalData(close=px,open=px*0.999,volume=pd.DataFrame(1e6,index=idx,columns=tk))
sig=lambda d: d.close.iloc[-1]/d.close.iloc[-21]-1.0
spec=cs.CrossSectionalSpec(pattern_id="p",family="f",citation="c",signal_fn=sig,lookback_days=60,holding_days=21,rank_fraction=0.2,portfolio="long_short")
cfg=cs.CrossSectionalConfig(cost_bps=10.0,min_names_per_leg=2)
r_fix=cs.run_cross_sectional_backtest(data,spec,cfg,cs.fixed_universe_membership(tk))
r_none=cs.run_cross_sectional_backtest(data,spec,cfg,None)
print("with fixed_universe:",r_fix.status,"n_form",len(r_fix.formations),"nonzero rets",int((r_fix.daily_returns!=0).sum()))
print("with None (default gate):",r_none.status,"n_zero_elig",r_none.n_zero_eligible_formations)
try:
    cs.screen_cross_sectional_universe(data,[spec],cfg,None); print("screen(None): returned [] (NO RAISE)")
except cs.EmptyEligibleUniverseError: print("screen(None): raised EmptyEligibleUniverseError OK")
print("screen(fixed) ->",len(cs.screen_cross_sectional_universe(data,[spec],cfg,cs.fixed_universe_membership(tk))),"results")

# (3) legitimate zero-formation cases must stay quiet
allm=lambda t,o: True
tiny=cs.CrossSectionalData(close=px.iloc[:,:2],open=None,volume=None)
c2=cs.CrossSectionalConfig(cost_bps=10.0,min_names_per_leg=5)
r=cs.run_cross_sectional_backtest(tiny,spec,c2,allm)
print("min_names too big ->",r.status, "n_zero_elig",r.n_zero_eligible_formations)
print("  screen ->",cs.screen_cross_sectional_universe(tiny,[spec],c2,allm))
short=cs.CrossSectionalData(close=px.iloc[:30],open=None,volume=None)
r2=cs.run_cross_sectional_backtest(short,spec,cfg,allm)
print("thin history ->",r2.status,"n_form",len(r2.formations))
print("  screen ->",cs.screen_cross_sectional_universe(short,[spec],cfg,allm))
spec_ov=cs.CrossSectionalSpec(pattern_id="ov",family="f",citation="c",signal_fn=sig,lookback_days=60,holding_days=21,rank_fraction=0.5,portfolio="long_short")
r3=cs.run_cross_sectional_backtest(data,spec_ov,cfg,allm)
print("rank_fraction 0.5 ->",r3.status)
# mixed: one dead spec + one live spec must NOT raise
print("mixed screen ->",len(cs.screen_cross_sectional_universe(data,[spec],cfg,lambda t,o: t in tk[:6])),"results (no raise)")

# (2) financing
for rate in (0.0,100.0,200.0):
    rr=cs.run_cross_sectional_backtest(data,spec,cs.CrossSectionalConfig(cost_bps=10.0,min_names_per_leg=2,financing_bps_per_year=rate),allm)
    print(f"rate={rate}: fin={rr.total_financing_cost:.6f} cost={rr.total_cost:.6f} sum_ret={rr.daily_returns.sum():.8f}")
b=cs.run_cross_sectional_backtest(data,spec,cs.CrossSectionalConfig(cost_bps=10.0,min_names_per_leg=2),allm)
f1=cs.run_cross_sectional_backtest(data,spec,cs.CrossSectionalConfig(cost_bps=10.0,min_names_per_leg=2,financing_bps_per_year=100.0),allm)
print("delta net == financing?", abs((b.daily_returns.sum()-f1.daily_returns.sum())-f1.total_financing_cost)<1e-12)
cal=(f1.daily_returns.index[-1]-b.daily_returns.index[0]).days
print("expected ~ 0.01*2*caldays/365 =",0.01*2*cal/365,"actual",f1.total_financing_cost)
