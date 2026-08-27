"""Calibrate the study-wise (whole-night) multiple-comparisons correction by
Monte Carlo, using THIS project's own deflated_sharpe.py functions on
simulated pure-noise nights. Nothing here reimplements the DSR math."""
import json, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np
from app.services.research_lab.deflated_sharpe import (
    expected_max_sharpe_under_noise, probabilistic_sharpe_ratio, MIN_TRIALS_FOR_DSR)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR as TD

D = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
bonds = json.load(open(f"{D}/bonds_meta_result.json"))
n_bonds = bonds["results"][0]["n"]
sig_bonds = float(np.std([r["sharpe"] for r in bonds["results"]], ddof=1))

# (name, k trials, n daily obs, realized sigma_sr annualized, skew, kurt)
NORMAL = (0.0, 3.0)
FAMS = [
    ("RoundC",      30, 2924, 0.2520, None),
    ("D1_ivol",     21, 2924, 0.0974, None),
    ("D2_reversal",  4, 2924, 0.0926, None),   # k<5 -> no DSR, cannot be the max
    ("Bonds",       18, n_bonds, sig_bonds, None),
    ("FX",          36, 3843, 0.1228, None),
    ("Commodities", 24, 2454, 0.3358, (-1.0193, 14.2643)),
    ("Buyback",     14, 2173, 0.1884, (0.23436, 4.40191)),
]
OBS_CMD, OBS_BB = 0.7674, 0.5981
NSIM = 40000
rng = np.random.default_rng(20260827)

def one_family_dsr(k, n_obs, sigma_true, sk, ku, size):
    """Vectorised replay of the harness's own pipeline under H0 (true SR=0
    for every sibling): draw k sibling Sharpes, re-estimate sigma_sr from
    them exactly as cross_sectional.py line 1549 does, take the family's
    best spec, and run it through the project's DSR functions."""
    if k < MIN_TRIALS_FOR_DSR:
        return np.full(size, -np.inf)          # harness returns dsr=None
    draws = rng.normal(0.0, sigma_true, size=(size, k))
    best = draws.max(axis=1)
    sig_hat = draws.std(axis=1, ddof=1)
    out = np.empty(size)
    for i in range(size):
        sr0d = expected_max_sharpe_under_noise(sig_hat[i] / np.sqrt(TD), k)
        d = probabilistic_sharpe_ratio(best[i] / np.sqrt(TD), sr0d, n_obs, sk, ku)
        out[i] = -np.inf if d is None else d
    return out

for tail_label, fill in (("normal tails for the 4 families whose skew/kurt weren't retained", NORMAL),
                         ("commodities-like fat tails (-1.0, 14.3) for those 4", (-1.0193, 14.2643))):
    per = {}
    for name, k, n_obs, sig, mom in FAMS:
        sk, ku = mom if mom is not None else fill
        per[name] = one_family_dsr(k, n_obs, sig, sk, ku, NSIM)
    night_max = np.max(np.vstack([per[n] for n, *_ in FAMS]), axis=0)
    print("=" * 78)
    print(f"MONTE CARLO ({NSIM:,} simulated pure-noise nights) -- {tail_label}")
    print("=" * 78)
    print("Median best-family DSR on a night where EVERYTHING is noise: "
          f"{np.median(night_max):.4f}   (mean {night_max.mean():.4f})")
    print(f"  P(best-family DSR >= {OBS_CMD} | whole night is noise) = "
          f"{(night_max >= OBS_CMD).mean():.4f}   <-- study-wise p for Commodities")
    print(f"  P(best-family DSR >= {OBS_BB} | whole night is noise) = "
          f"{(night_max >= OBS_BB).mean():.4f}   <-- study-wise p for Buyback")
    print(f"  study-wise meta-DSR, Commodities = {1-(night_max >= OBS_CMD).mean():.4f}")
    print(f"  study-wise meta-DSR, Buyback     = {1-(night_max >= OBS_BB).mean():.4f}")
    c = per["Commodities"]; b = per["Buyback"]
    print(f"\n  Sanity, family-internal only (is DSR even calibrated within a family?):")
    print(f"    Commodities family alone: P(its own best-spec DSR >= {OBS_CMD}) = {(c >= OBS_CMD).mean():.4f}"
          f"  | null median DSR = {np.median(c):.4f}")
    print(f"    Buyback     family alone: P(its own best-spec DSR >= {OBS_BB}) = {(b >= OBS_BB).mean():.4f}"
          f"  | null median DSR = {np.median(b):.4f}")
    print(f"  Per-family null median best-spec DSR (shows DSR is NOT U(0,1) for a family max):")
    print("   ", {n: round(float(np.median(per[n][np.isfinite(per[n])])), 3) if np.isfinite(per[n]).any() else "n/a" for n, *_ in FAMS})
    print()
