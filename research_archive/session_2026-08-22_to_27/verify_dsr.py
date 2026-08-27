"""Independent re-derivation of PSR / SR0 / DSR formulas against Bailey &
Lopez de Prado (2014) "The Sharpe Ratio Efficient Frontier", computed from
scratch (NOT importing the module under test), then cross-checked against
the actual module.
"""
import numpy as np
from scipy.stats import norm

# ---- Case 1: PSR formula, textbook normal case (skew=0, kurt=3) ----
# BLdP eq 5/8 (Mertens 2002 asymptotic form, textbook reduction):
# PSR(SR*) = Phi( (SRhat - SR*) * sqrt(n-1) / sqrt(1 - gamma3*SRhat + (gamma4-1)/4 * SRhat^2) )
def psr_textbook(sr_hat, sr_star, n, skew, kurt_pearson):
    denom = np.sqrt(1 - skew*sr_hat + ((kurt_pearson - 1)/4)*sr_hat**2)
    z = (sr_hat - sr_star) * np.sqrt(n - 1) / denom
    return norm.cdf(z)

sr_hat, n = 0.3, 500
val_normal = psr_textbook(sr_hat, 0.0, n, skew=0.0, kurt_pearson=3.0)
print("Case1 PSR normal-case (skew=0,kurt=3), sr_hat=0.3,n=500:", repr(val_normal))
# Compare to plain Mertens asymptotic normal form: Phi(SRhat*sqrt(n-1))
val_mertens = norm.cdf(sr_hat * np.sqrt(n - 1))
print("Case1 plain Mertens normal-only form:               ", repr(val_mertens))
print("Match to 12 decimals:", abs(val_normal - val_mertens) < 1e-12)
print()

# ---- Case 2: PSR with real skew/kurtosis, hand arithmetic ----
sr_hat2, sr_star2, n2, skew2, kurt2 = 0.05, 0.0, 250, -0.8, 5.5
denom_sq2 = 1 - skew2*sr_hat2 + ((kurt2-1)/4)*sr_hat2**2
z2 = (sr_hat2 - sr_star2) * np.sqrt(n2-1) / np.sqrt(denom_sq2)
psr2 = norm.cdf(z2)
print("Case2 hand PSR: denom_sq=%.6f z=%.6f PSR=%.6f" % (denom_sq2, z2, psr2))
print()

# ---- Case 3: expected_max_sharpe_under_noise (SR0), BLdP eq 10 ----
# E[max SR] = sigma_SR * ( (1-gamma)*Phi^-1(1 - 1/N) + gamma*Phi^-1(1 - 1/(N*e)) )
def sr0_textbook(sigma_sr, n_trials):
    gamma = np.euler_gamma
    return sigma_sr * ((1-gamma)*norm.ppf(1 - 1/n_trials) + gamma*norm.ppf(1 - 1/(n_trials*np.e)))

for N in [2, 5, 10, 100, 1000]:
    print(f"Case3 SR0 sigma_sr=0.3 N={N}: {sr0_textbook(0.3, N):.6f}")

print()
# ---- Case 4: DSR = PSR(SR_hat, benchmark=SR0) ----
sigma_sr_c4, n_trials_c4 = 0.25, 50
sr0_c4 = sr0_textbook(sigma_sr_c4, n_trials_c4)
sr_hat_c4, n_obs_c4, skew_c4, kurt_c4 = 0.08, 300, 0.2, 4.0
dsr_c4 = psr_textbook(sr_hat_c4, sr0_c4, n_obs_c4, skew_c4, kurt_c4)
print(f"Case4 SR0(sigma=0.25,N=50)={sr0_c4:.6f}, DSR(sr_hat=0.08,n=300)={dsr_c4:.6f}")
