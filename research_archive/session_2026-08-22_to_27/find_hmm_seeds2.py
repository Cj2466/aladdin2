import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
from app.services.research_lab.regime_hmm import classify_regime_hmm, HMM_WINDOW_TRADING_DAYS

def two_regime_price_series_reversed(n, seed, low_std=0.005, high_std=0.02, switch_at=None):
    rng = np.random.default_rng(seed)
    if switch_at is None:
        switch_at = n // 2
    returns = np.concatenate([
        rng.normal(0, high_std, switch_at),
        rng.normal(0, low_std, n - switch_at),
    ])
    log_price = np.cumsum(returns)
    return 100 * np.exp(log_price)

n = HMM_WINDOW_TRADING_DAYS + 1
for seed in range(5):
    prices = pd.Series(two_regime_price_series_reversed(n, seed))
    result = classify_regime_hmm(prices)
    print(seed, result)

# also test insufficient history -> None
short = pd.Series(np.linspace(100, 110, HMM_WINDOW_TRADING_DAYS))
print("short:", classify_regime_hmm(short))

# constant price -> zero variance -> None
constant = pd.Series(np.full(HMM_WINDOW_TRADING_DAYS + 1, 100.0))
print("constant:", classify_regime_hmm(constant))
