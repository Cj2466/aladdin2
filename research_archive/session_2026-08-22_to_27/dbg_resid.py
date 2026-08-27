import numpy as np, pandas as pd
import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_5806e4c5-4df-1/backend")
import app.services.research_lab.vol_regime_timing as vrt
from datetime import date

index = pd.bdate_range("2010-01-04", periods=1600)
rng = np.random.default_rng(41)
holding = 21
raw = pd.Series(np.sin(np.arange(len(index)) * 2 * np.pi / 210), index=index)
vol = pd.DataFrame({t: np.full(len(index), 20.0) for t in vrt.VOL_INDEX_UNIVERSE}, index=index)
vol[vrt.MOVE] = 20.0 * np.exp(raw * 0.3)
vol[vrt.VIX] = 20.0

spread_daily = np.zeros(len(index))
for p in range(0, len(index) - holding, holding):
    spread_daily[p+1:p+1+holding] = -np.sign(raw.iloc[p]) * 0.0016 + rng.normal(0, 0.0025, holding)
ief = pd.Series(100.0, index=index)
spy = pd.Series(100.0 * np.exp(np.cumsum(spread_daily)), index=index)
traded = pd.DataFrame({"SPY": spy, "IEF": ief, "HYG": spy}, index=index)

data = vrt.align_vol_regime_data(vol, traded)
spec = vrt.TimingSpec(spec_id="t", state_key="t", citation="c"*50, hypothesis="h"*20,
                      state_fn=vrt.partial(vrt.state_ratio, numerator=vrt.MOVE, denominator=vrt.VIX),
                      holding_days=holding, target=vrt.TARGET_EQUITY_VS_DURATION)
cfg = vrt.VolRegimeConfig(formation_start=date(2010,1,4))
r = vrt.run_timing_backtest(data, spec, cfg)
print("status", r.status, "n", len(r.daily_returns))
pos = r.positions
print("unique positions:", np.unique(np.round(pos.values, 6))[:20], "n_unique", pos.nunique())
print("pos abs mean", pos.abs().mean(), "min", pos.min(), "max", pos.max())
sp = r.spread_returns
print("corr(strat, spread):", r.daily_returns.corr(sp))
b, a = vrt._ols_beta_alpha(r.daily_returns, sp)
print("beta", b, "alpha", a)
resid = r.daily_returns - (a + b*sp)
print("resid std", resid.std(), "strat std", r.daily_returns.std())
# is position essentially +-1?
print("frac |pos|==1:", (pos.abs() > 0.999).mean())
