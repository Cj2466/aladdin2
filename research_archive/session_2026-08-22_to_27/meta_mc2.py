import json, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np
from app.services.research_lab.deflated_sharpe import (
    expected_max_sharpe_under_noise, probabilistic_sharpe_ratio)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR as TD
rng = np.random.default_rng(7)
NSIM = 40000

def se(p): return (p * (1 - p) / NSIM) ** 0.5

# Upper-bound sensitivity: pretend the whole night was ONE flat family of
# N trials sharing the pooled cross-family Sharpe dispersion.
for N, sig, n_obs, sk, ku, lab in (
    (147, 0.2544, 2454, -1.0193, 14.2643, "flat 147-trial pool, pooled sigma=0.2544, Commodities' own tails"),
    (147, 0.3358, 2454, -1.0193, 14.2643, "flat 147-trial pool, Commodities' sigma=0.3358"),
):
    draws = rng.normal(0, sig, size=(NSIM, N))
    best = draws.max(axis=1); sh = draws.std(axis=1, ddof=1)
    d = np.array([probabilistic_sharpe_ratio(best[i]/np.sqrt(TD),
                  expected_max_sharpe_under_noise(sh[i]/np.sqrt(TD), N), n_obs, sk, ku) or 0.0
                  for i in range(NSIM)])
    p = float((d >= 0.7674).mean())
    print(f"{lab}\n   null median best DSR={np.median(d):.4f} | P(>=0.7674)={p:.4f} (SE {se(p):.4f})")

print()
for lab, p in (("Commodities study-wise (7 families)", 0.1313),
               ("Buyback study-wise (7 families)", 0.6909),
               ("Commodities family-internal calibrated", 0.0519),
               ("Buyback family-internal calibrated", 0.1546)):
    print(f"{lab:42s} p={p:.4f} +/- {1.96*se(p):.4f} (95% MC)")
