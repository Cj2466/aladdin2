"""How many YEARS of daily data does a strategy with TRUE annual Sharpe S need before the
as-coded gate (DSR>=target at n_local, sigma_sr as given) passes IN EXPECTATION (i.e. when the
realized Sharpe equals the true one)? Uses the module's own functions; normal returns assumed."""
import numpy as np
from app.services.research_lab.deflated_sharpe import probabilistic_sharpe_ratio, expected_max_sharpe_under_noise
def dsr(S, n_obs, N, sigma, ppy=252.0):
    sr0 = expected_max_sharpe_under_noise(sigma/np.sqrt(ppy), N)
    return probabilistic_sharpe_ratio(S/np.sqrt(ppy), sr0, n_obs, 0.0, 3.0)
def years_needed(S, target, N, sigma):
    for yrs in np.arange(1, 201, 1):
        d = dsr(S, int(yrs*252), N, sigma)
        if d is not None and d >= target: return int(yrs)
    return None
print("sigma_sr=0.20 (typical equity family), N=n_local")
print("true_SR | N=12: yrs@0.95 yrs@0.50 | N=36: yrs@0.95 yrs@0.50 | N=1031: yrs@0.95")
for S in [0.3,0.4,0.5,0.6,0.8,1.0,1.5]:
    print(f"{S:6.2f} |  {years_needed(S,0.95,12,0.2)!s:>6} {years_needed(S,0.50,12,0.2)!s:>6} |  {years_needed(S,0.95,36,0.2)!s:>6} {years_needed(S,0.50,36,0.2)!s:>6} |  {years_needed(S,0.95,1031,0.2)!s:>6}")
print()
print("SR0 (annualized expected max noise Sharpe) by N at sigma_sr=0.20 / 0.50:")
for N in [12,36,37,362,1031]:
    a=expected_max_sharpe_under_noise(0.2/np.sqrt(252),N)*np.sqrt(252); b=expected_max_sharpe_under_noise(0.5/np.sqrt(252),N)*np.sqrt(252)
    print(f"N={N:5d}: SR0={a:.3f} / {b:.3f}")
