import json, sys
sys.path.insert(0,'.')
from app.services.research_lab.vol_regime_timing import run_vol_regime_screening, VOL_REGIME_FAMILY, VOL_REGIME_N_TRIALS
print("FAMILY SIZE", len(VOL_REGIME_FAMILY), "N_TRIALS", VOL_REGIME_N_TRIALS)
print("HOLDS", sorted({s.holding_days for s in VOL_REGIME_FAMILY}))
print("DIRS", sorted({s.direction for s in VOL_REGIME_FAMILY}))
s = run_vol_regime_screening()
rows=[]
for r in s.results:
    rows.append(dict(spec_id=r.spec_id, sharpe=r.sharpe_annualized, dsr=r.deflated_sharpe.deflated_sharpe if hasattr(r.deflated_sharpe,'deflated_sharpe') else None,
        n_form=r.n_formations, nd=r.n_trading_days, cross=r.is_cross_asset, hold=r.holding_days,
        first=str(r.first_formation), last=str(r.last_formation),
        resid=r.confound.residual_sharpe, sbeta=r.confound.spread_beta, eqb=r.confound.equity_beta, rb=r.confound.rates_beta))
print("N_RESULTS", len(rows))
print("MISSING_VOL", s.missing_vol_indices)
print("STARTS", {k:str(v) for k,v in s.vol_index_starts.items()})
print("CAL", s.formation_calendar_start, s.formation_calendar_end)
json.dump(rows, open('/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prod_results.json','w'), indent=1)
