import json,sys,os,pickle
sys.path.insert(0,'.')
from datetime import date, timedelta
from app.services.research_lab.vol_regime_timing import *
from app.services.research_lab.vol_regime_timing import _STATE_VARIABLES, VOL_INDEX_UNIVERSE, TRADED_UNIVERSE, VOL_REGIME_HISTORY_PADDING_CALENDAR_DAYS
from app.services.market_data.yfinance_provider import YFinanceProvider
S='/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/'
P=S+'volregime_verify_data.pkl'
if os.path.exists(P):
    vol_close,traded_close=pickle.load(open(P,'rb'))
else:
    pv=YFinanceProvider(); st=VOL_REGIME_FORMATION_START; ps=st-timedelta(days=VOL_REGIME_HISTORY_PADDING_CALENDAR_DAYS)
    vol_close,_=pv.get_price_history(list(VOL_INDEX_UNIVERSE),ps,date(2026,8,27))
    traded_close,_=pv.get_price_history(list(TRADED_UNIVERSE),ps,date(2026,8,27))
    assert len(vol_close.columns)==7 and len(traded_close.columns)==3,(vol_close.columns,traded_close.columns)
    pickle.dump((vol_close,traded_close),open(P,'wb'))
data=align_vol_regime_data(vol_close,traded_close)
cfg=default_vol_regime_config()
res=screen_vol_regime_timing(data,VOL_REGIME_FAMILY,cfg)
rows=[]
for r in res:
    ds=r.deflated_sharpe
    rows.append(dict(spec_id=r.spec_id,state=r.state_key,tgt=r.target_key,hold=r.holding_days,cross=r.is_cross_asset,
      sharpe=r.sharpe_annualized,dsr=ds.dsr,emax=ds.expected_max_sharpe_noise_annualized,psr=ds.psr_vs_zero,
      ntrials=ds.n_trials,sigsr=ds.sigma_sr_annualized,nf=r.n_formations,nsk=r.n_skipped_formations,nd=r.n_trading_days,
      bp=r.confound.bootstrap_p_value,resid=r.confound.residual_sharpe,sbeta=r.confound.spread_beta,
      eqb=r.confound.equity_beta,rb=r.confound.rates_beta,mp=getattr(r.confound,'mean_position',None),
      sub=getattr(r.confound,'subperiod_sharpes',None)))
json.dump(rows,open(S+'res2.json','w'),indent=1,default=str)
print('N',len(rows))
