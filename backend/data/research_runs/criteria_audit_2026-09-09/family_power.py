"""Per-family: best Sharpe/DSR actually persisted, and the MINIMUM Sharpe the as-coded
gate would have needed (DSR>=0.95 and >=0.50 at n_local), using the project's own
deflated_sharpe functions (no formula re-typed). Normal returns assumed for the inversion
(skew 0, kurt 3) -- stated, not hidden."""
import json, numpy as np, pandas as pd
from collections import defaultdict
from app.db import SessionLocal
from app.models.cross_sectional_trial_result import CrossSectionalTrialResult as T
from app.services.research_lab.deflated_sharpe import probabilistic_sharpe_ratio, expected_max_sharpe_under_noise
db = SessionLocal()
rows = db.query(T).all()
print("total rows:", len(rows))
# keys of one full_result_json
j = json.loads(rows[0].full_result_json); print("sample json keys:", sorted(j.keys())[:40])
# latest run_tag per family
by_fam = defaultdict(list)
for r in rows: by_fam[r.family_key].append(r)
def req_sharpe(target, n_obs, n_trials, sigma_sr_ann, ppy=252.0):
    if sigma_sr_ann is None or n_trials < 5: return None
    sr0_d = expected_max_sharpe_under_noise(sigma_sr_ann/np.sqrt(ppy), n_trials)
    lo, hi = 0.0, 10.0
    for _ in range(60):
        mid=(lo+hi)/2
        p = probabilistic_sharpe_ratio(mid/np.sqrt(ppy), sr0_d, n_obs, 0.0, 3.0)
        if p is None or p < target: lo=mid
        else: hi=mid
    return hi
out=[]
for fam, rs in sorted(by_fam.items()):
    latest = max(r.run_tag for r in rs)
    rr = [r for r in rs if r.run_tag==latest]
    sh = np.array([r.sharpe_annualized for r in rr]); 
    best = max(rr, key=lambda r: (r.dsr if r.dsr is not None else -1))
    sigma = float(np.std(sh, ddof=1)) if len(sh)>=2 else None
    n_obs = int(np.median([r.n_observations for r in rr]))
    n_tr = best.n_trials
    ppy = 365.0 if 'crypto' in fam else 252.0
    out.append(dict(family=fam, n_specs=len(rr), n_trials=n_tr, n_obs=n_obs, sigma_sr=sigma,
        best_sharpe=float(max(sh)), best_dsr=best.dsr, best_dsr_sharpe=best.sharpe_annualized,
        req_sharpe_095=req_sharpe(0.95,n_obs,n_tr,sigma,ppy), req_sharpe_050=req_sharpe(0.50,n_obs,n_tr,sigma,ppy)))
df = pd.DataFrame(out)
pd.set_option('display.width',250); pd.set_option('display.max_rows',200)
print(df.round(3).to_string(index=False))
df.to_csv('backend/data/research_runs/criteria_audit_2026-09-09/family_power.csv', index=False)
