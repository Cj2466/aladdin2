import numpy as np, pandas as pd
from app.services.research_lab.deflated_sharpe import probabilistic_sharpe_ratio, expected_max_sharpe_under_noise
def req(target,n_obs,N,sigma,ppy):
    sr0=expected_max_sharpe_under_noise(sigma/np.sqrt(ppy),N); lo,hi=0.0,15.0
    for _ in range(60):
        mid=(lo+hi)/2; p=probabilistic_sharpe_ratio(mid/np.sqrt(ppy),sr0,n_obs,0.0,3.0)
        lo,hi=(mid,hi) if (p is None or p<target) else (lo,mid)
    return hi
df=pd.read_csv('backend/data/research_runs/criteria_audit_2026-09-09/family_power.csv')
for fam in ['dumb_money','firesale_pressure','inelastic_markets','margin_credit','small_cap_dumb_money','small_cap_firesale_pressure']:
    r=df[df.family==fam].iloc[0]
    print(f"{fam:28s} n_obs={int(r.n_obs):4d} (monthly, ppy=12) N={int(r.n_trials)} sigma={r.sigma_sr:.3f} best_sharpe={r.best_sharpe:.3f} req@0.95={req(0.95,int(r.n_obs),int(r.n_trials),r.sigma_sr,12):.2f} req@0.50={req(0.50,int(r.n_obs),int(r.n_trials),r.sigma_sr,12):.2f}")
