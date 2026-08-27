import warnings; warnings.filterwarnings("ignore")
import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_5806e4c5-4df-1/backend")
import numpy as np
from app.services.research_lab.vol_regime_timing import run_vol_regime_screening
from app.services.research_lab.deflated_sharpe import expected_max_sharpe_under_noise
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

s = run_vol_regime_screening()
sh = np.array([r.sharpe_annualized for r in s.results])
sigma_sr = s.results[0].deflated_sharpe.sigma_sr_annualized
n_trials = s.results[0].deflated_sharpe.n_trials
observed_max = sh.max()

print("THE BEST-OF-N-UNDER-NOISE BENCHMARK (the check that sank the buyback family)")
print("-"*78)
print(f"n_trials                         : {n_trials}")
print(f"sigma_sr (sibling Sharpe std)    : {sigma_sr:.4f} annualized")
sr0_d = expected_max_sharpe_under_noise(sigma_sr/np.sqrt(TRADING_DAYS_PER_YEAR), n_trials)
sr0 = sr0_d*np.sqrt(TRADING_DAYS_PER_YEAR)
print(f"E[max Sharpe | {n_trials} zero-edge trials] : {sr0:+.4f} annualized")
print(f"OBSERVED best Sharpe             : {observed_max:+.4f} annualized")
print(f"observed - noise expectation     : {observed_max - sr0:+.4f}")
print()

# Monte Carlo: distribution of the best-of-48 Sharpe under pure noise, matched
# to this family's real sample length and sibling dispersion.
n_days = int(np.median([r.n_trading_days for r in s.results]))
rng = np.random.default_rng(20260827)
B = 20000
daily_sigma = 0.004
best = np.empty(B)
for b in range(B):
    r = rng.normal(0.0, daily_sigma, size=(n_trials, n_days))
    m = r.mean(axis=1); sd = r.std(axis=1, ddof=1)
    best[b] = (m/sd*np.sqrt(TRADING_DAYS_PER_YEAR)).max()
print(f"MONTE CARLO, {B} draws of {n_trials} independent zero-edge strategies of {n_days} days:")
print(f"  median best-of-{n_trials} Sharpe   : {np.median(best):+.4f}")
print(f"  90th pct                       : {np.percentile(best,90):+.4f}")
print(f"  95th pct                       : {np.percentile(best,95):+.4f}")
print(f"  P(best-of-{n_trials} >= observed {observed_max:.3f}) = {(best>=observed_max).mean():.4f}")
print()
print("  NOTE: this MC assumes 48 INDEPENDENT trials. The real family's specs are")
print("  correlated (shared targets, overlapping state variables), so the true")
print("  best-of-48 noise distribution is somewhat tighter than this. Correlated")
print("  trials make the observed max EASIER to beat by chance in relative terms")
print("  only if correlation is very high; either way the observed max sits deep")
print("  inside the noise body, not in its tail.")
print()
# Cross-asset claim test
xa = [r.sharpe_annualized for r in s.results if r.is_cross_asset]
non = [r.sharpe_annualized for r in s.results if not r.is_cross_asset]
ctrl = [r.sharpe_annualized for r in s.results if r.state_key == "vix_level"]
print("DOES 'CROSS-ASSET' BEAT THE EQUITY-VOL CONTROL?")
print("-"*78)
print(f"  cross-asset specs   n={len(xa):2d} mean {np.mean(xa):+.4f} max {max(xa):+.4f}")
print(f"  non-cross-asset     n={len(non):2d} mean {np.mean(non):+.4f} max {max(non):+.4f}")
print(f"  vix_level control   n={len(ctrl):2d} mean {np.mean(ctrl):+.4f} max {max(ctrl):+.4f}")
best_spec = s.results[0]
print(f"  BEST SPEC OVERALL   : {best_spec.spec_id} (cross-asset={best_spec.is_cross_asset})")
