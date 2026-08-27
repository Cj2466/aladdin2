"""Print the exact synthetic-validation numbers for the final report."""

import sys

import numpy as np

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-ae4c6e712670defb9/backend")

from app.services.research_lab.empirical_bayes_shrinkage import (  # noqa: E402
    TrialObservation,
    fit_empirical_bayes,
)


def simulate(mu, tau2, k, seed, se_lo=0.25, se_hi=0.55):
    rng = np.random.default_rng(seed)
    se = rng.uniform(se_lo, se_hi, k)
    theta_true = rng.normal(mu, np.sqrt(tau2), k)
    theta_hat = theta_true + rng.normal(0.0, se)
    obs = [TrialObservation(f"t{i}", float(theta_hat[i]), float(se[i])) for i in range(k)]
    return obs, theta_true


print("=" * 100)
print("PARAMETER RECOVERY  (k=200 trials per population, 60 independent populations, se_i ~ U(0.25,0.55))")
print("=" * 100)
print(f"{'true mu':>9} {'true tau^2':>11} | {'mu_hat':>9} {'err':>8} | {'tau2_hat':>9} {'rel err':>9} | {'tau_hat':>8} {'true tau':>9}")
for mu, tau2 in [(0.0, 0.0), (0.30, 0.01), (0.0, 0.09), (0.35, 0.09), (-0.20, 0.25), (0.0, 1.00), (0.0, 9.00)]:
    mus, t2s = [], []
    for seed in range(60):
        obs, _ = simulate(mu, tau2, 200, seed)
        r = fit_empirical_bayes(obs)
        mus.append(r.mu_hat)
        t2s.append(r.tau2_hat)
    mm, tt = float(np.mean(mus)), float(np.mean(t2s))
    rel = f"{(tt - tau2) / tau2:+.1%}" if tau2 > 0 else "n/a (0)"
    print(f"{mu:>9.2f} {tau2:>11.2f} | {mm:>9.4f} {mm-mu:>+8.4f} | {tt:>9.4f} {rel:>9} | {np.sqrt(tt):>8.3f} {np.sqrt(tau2):>9.3f}")

print()
print("=" * 100)
print("MSE AGAINST KNOWN TRUE theta_i  (k=100 per population, 80 populations, se_i ~ U(0.25,0.55))")
print("=" * 100)
print(f"{'true mu':>9} {'true tau^2':>11} | {'MSE raw':>10} {'MSE shrunk':>11} {'reduction':>10} | {'mean shrink wt':>15} | {'Q p<.05 rate':>13}")
for mu, tau2 in [(0.0, 0.0), (0.30, 0.01), (0.0, 0.09), (-0.15, 0.25), (0.0, 1.00), (0.0, 9.00)]:
    raw_t, sh_t, wts, rej = 0.0, 0.0, [], []
    for seed in range(80):
        obs, truth = simulate(mu, tau2, 100, 3000 + seed)
        r = fit_empirical_bayes(obs)
        raw = np.array([t.theta_hat for t in r.trials])
        sh = np.array([t.theta_shrunk for t in r.trials])
        raw_t += float(np.mean((raw - truth) ** 2))
        sh_t += float(np.mean((sh - truth) ** 2))
        wts.append(r.mean_shrinkage_weight)
        rej.append(r.heterogeneity_p_value < 0.05)
    print(
        f"{mu:>9.2f} {tau2:>11.2f} | {raw_t/80:>10.4f} {sh_t/80:>11.4f} {1-sh_t/raw_t:>9.1%} | "
        f"{np.mean(wts):>15.3f} | {np.mean(rej):>12.1%}"
    )

print()
print("=" * 100)
print("EXTREME HETEROSKEDASTICITY  se_i ~ U(0.05, 1.50)  (the varying-sample-length case)")
print("=" * 100)
for mu, tau2 in [(0.1, 0.09), (0.0, 0.0)]:
    raw_t, sh_t = 0.0, 0.0
    for seed in range(80):
        obs, truth = simulate(mu, tau2, 100, 5000 + seed, se_lo=0.05, se_hi=1.50)
        r = fit_empirical_bayes(obs)
        raw = np.array([t.theta_hat for t in r.trials])
        sh = np.array([t.theta_shrunk for t in r.trials])
        raw_t += float(np.mean((raw - truth) ** 2))
        sh_t += float(np.mean((sh - truth) ** 2))
    print(f"  mu={mu}, tau^2={tau2}: MSE raw {raw_t/80:.4f} -> shrunk {sh_t/80:.4f}   ({1-sh_t/raw_t:.1%} reduction)")

print()
print("=" * 100)
print("CHEN & DIM (arXiv:2311.10685) Eq.15 CLOSED-FORM CROSS-CHECK, se_i = 1 (t-stat space)")
print("=" * 100)
rng = np.random.default_rng(99)
t_stats = rng.normal(0.4, 1.8, 300)
obs = [TrialObservation(f"t{i}", float(v), 1.0) for i, v in enumerate(t_stats)]
r = fit_empirical_bayes(obs, prior_mean=0.0)
paper = 1.0 - 1.0 / np.var(t_stats, ddof=1)
mine = r.trials[0].shrinkage_weight
print(f"  paper's 1 - 1/Var_hat(t) = {paper:.15f}")
print(f"  this module's B_i        = {mine:.15f}")
print(f"  absolute difference      = {abs(paper - mine):.3e}")
