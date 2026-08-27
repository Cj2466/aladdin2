"""CAPABILITY DEMONSTRATION ON SYNTHETIC DATA -- NOT A FINDING ABOUT REAL TRIALS.

The real experiment_runs table holds 0 rows, so there is no stored trial
population to shrink. This script instead answers the methodological question
the task poses -- "would shrinkage meaningfully reorder a raw-Sharpe ranking,
and would it rescue any DSR-rejected trial?" -- on populations built at this
project's own realistic scale, with truth we injected ourselves.

Scenario A mirrors the 212-pattern intraday run's reported signature (commit
5e5a0c4: 204/212 negative pooled Sharpe, best +0.79) under a TRUE null.
Scenario B plants exactly one genuinely-skilled trial in an otherwise-null
population, to check the method can still find real edge when it exists.
"""

import sys

import numpy as np

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-ae4c6e712670defb9/backend")

from app.services.research_lab.empirical_bayes_shrinkage import (  # noqa: E402
    TrialObservation,
    fit_empirical_bayes,
    sharpe_standard_error_annualized,
)

PPY = 1638.0  # ~6.5 hourly bars/day x 252 -- the intraday family's scale


def build(k, true_sharpes, n_bars, seed):
    rng = np.random.default_rng(seed)
    obs, truth = [], []
    for i in range(k):
        n = int(n_bars[i])
        se = sharpe_standard_error_annualized(true_sharpes[i], n, periods_per_year=PPY)
        obs.append(TrialObservation(f"p{i:03d}", float(true_sharpes[i] + rng.normal(0, se)), se,
                                    label=f"pattern_{i:03d} (n={n})"))
        truth.append(true_sharpes[i])
    return obs, np.array(truth)


def report(title, obs, truth):
    print("=" * 96)
    print(title)
    print("=" * 96)
    res = fit_empirical_bayes(obs)
    print(f"  n={res.n_trials}  mu_hat={res.mu_hat:+.4f}  tau_hat={res.tau_hat:.4f}  "
          f"Q={res.q_statistic:.1f} df={res.q_df} p={res.heterogeneity_p_value:.4g}  I^2={res.i_squared:.1%}")
    print(f"  mean shrinkage weight = {res.mean_shrinkage_weight:.3f}")
    raw = np.array([t.theta_hat for t in res.trials])
    sh = np.array([t.theta_shrunk for t in res.trials])
    print(f"  MSE vs injected truth: raw {np.mean((raw-truth)**2):.4f} -> shrunk {np.mean((sh-truth)**2):.4f} "
          f"({1 - np.mean((sh-truth)**2)/np.mean((raw-truth)**2):.1%} reduction)")
    print(f"  raw Sharpe range: {raw.min():+.3f} .. {raw.max():+.3f}   "
          f"shrunk range: {sh.min():+.3f} .. {sh.max():+.3f}")
    print(f"\n  {'rk_s':>4} {'rk_raw':>6} {'shrunk':>8} {'raw':>8} {'se':>6} {'wt':>5} {'P(>0)':>7}  {'TRUE':>7}  label")
    for t in sorted(res.trials, key=lambda x: x.rank_shrunk)[:8]:
        i = int(t.trial_id[1:])
        print(f"  {t.rank_shrunk:>4d} {t.rank_raw:>6d} {t.theta_shrunk:>8.4f} {t.theta_hat:>8.4f} "
              f"{t.se:>6.3f} {t.shrinkage_weight:>5.3f} {t.prob_positive:>7.1%}  {truth[i]:>+7.3f}  {t.label}")
    moved = sum(1 for t in res.trials if t.rank_raw != t.rank_shrunk)
    top10_raw = {t.trial_id for t in res.trials if t.rank_raw <= 10}
    top10_sh = {t.trial_id for t in res.trials if t.rank_shrunk <= 10}
    print(f"\n  ranks changed: {moved}/{res.n_trials}   top-10 overlap raw vs shrunk: {len(top10_raw & top10_sh)}/10")
    print(f"\n  {res.interpretation}\n")
    return res


rng = np.random.default_rng(2024)

# --- A: TRUE NULL, 212 patterns, heterogeneous trade counts -----------------
K = 212
n_bars = rng.integers(40, 3400, K)  # wildly uneven, as in the real family
obs_a, truth_a = build(K, np.zeros(K), n_bars, seed=1)
report("SCENARIO A [SYNTHETIC] -- 212 intraday patterns, EVERY true Sharpe = 0", obs_a, truth_a)

# --- B: one real edge planted in an otherwise-null population ---------------
true_b = np.zeros(K)
true_b[137] = 1.10  # one genuinely skilled pattern
obs_b, truth_b = build(K, true_b, n_bars, seed=2)
res_b = report("SCENARIO B [SYNTHETIC] -- same population, ONE pattern with a true Sharpe of +1.10", obs_b, truth_b)
winner = [t for t in res_b.trials if t.trial_id == "p137"][0]
print(f"  planted trial p137: raw rank {winner.rank_raw}, shrunk rank {winner.rank_shrunk}, "
      f"shrunk estimate {winner.theta_shrunk:+.3f} (true +1.100), P(>0)={winner.prob_positive:.1%}")
