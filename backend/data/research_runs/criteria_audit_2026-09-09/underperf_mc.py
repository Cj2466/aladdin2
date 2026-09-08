# Monte Carlo of the AS-CODED underperformance rule (forward_validation_service.check_underperformance):
# every tick, trailing 60 realized days, annualized Sharpe <= -0.5 -> permanent "underperforming".
# Question: for a strategy with TRUE annual Sharpe S, what is P(flagged at least once) within H days?
import numpy as np
rng = np.random.default_rng(0)
LOOK=60; THR=-0.5; PPY=252
def p_flag(true_sr_annual, horizon_days, n_sims=20000, daily_vol=0.01):
    mu = true_sr_annual/np.sqrt(PPY)*daily_vol
    r = rng.normal(mu, daily_vol, size=(n_sims, horizon_days))
    # rolling 60-day sharpe (annualized), ddof=1 like metrics.sharpe_ratio
    cs = np.cumsum(r, axis=1); cs2 = np.cumsum(r*r, axis=1)
    flagged = np.zeros(n_sims, bool)
    for end in range(LOOK, horizon_days+1):
        s = cs[:,end-1] - (cs[:,end-LOOK-1] if end-LOOK-1>=0 else 0)
        s2 = cs2[:,end-1] - (cs2[:,end-LOOK-1] if end-LOOK-1>=0 else 0)
        mean = s/LOOK; var = (s2 - LOOK*mean**2)/(LOOK-1)
        sr = mean/np.sqrt(var)*np.sqrt(PPY)
        flagged |= (sr <= THR)
    return flagged.mean()
print("true_SR  H=126  H=252  H=504  (P at least one permanent 'underperforming' flag)")
for S in [0.0, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0]:
    print(f"{S:6.2f}  {p_flag(S,126):.3f}  {p_flag(S,252):.3f}  {p_flag(S,504):.3f}")
