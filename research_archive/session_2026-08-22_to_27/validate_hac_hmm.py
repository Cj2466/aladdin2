import sys
sys.path.insert(0, ".")
import numpy as np
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

# --- HAC significance check ---
rng = np.random.default_rng(42)
n = 90
t = np.arange(n, dtype=float)
log_price = np.cumsum(rng.normal(0.003, 0.0005, n))  # strong trend
X = add_constant(t)
model = OLS(log_price, X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
print("HAC trend case: pvalues=", model.pvalues, "params=", model.params)

flat = 4.6 + rng.normal(0, 0.01, n)
model2 = OLS(flat, X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
print("HAC flat case: pvalues=", model2.pvalues)

# --- HMM check ---
n2 = 500
rng2 = np.random.default_rng(1)
# construct two-regime volatility series: alternating high/low vol blocks
regime_labels = np.concatenate([np.zeros(250), np.ones(250)]).astype(int)
returns = np.where(regime_labels == 0, rng2.normal(0, 0.005, n2), rng2.normal(0, 0.02, n2))
mod = MarkovRegression(returns, k_regimes=2, switching_variance=True)
res = mod.fit(disp=False)
print("HMM params:", res.params)
print("param names:", mod.param_names)
print("smoothed_marginal_probabilities shape:", res.smoothed_marginal_probabilities.shape)
print("last-day smoothed probs:", res.smoothed_marginal_probabilities.iloc[-1] if hasattr(res.smoothed_marginal_probabilities, "iloc") else res.smoothed_marginal_probabilities[-1])
print("expected durations:", res.expected_durations)
