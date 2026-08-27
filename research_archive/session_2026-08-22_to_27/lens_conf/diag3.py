"""A more defensible best-of-14 null than an iid random signal: permute the
SHARE PANEL'S TICKER LABELS globally, once per rep. Each pseudo-name keeps a
real name's full signal PATH (so the signal's persistence across formations,
its cross-sectional dispersion and its missingness structure all survive);
only the link between a name's issuance history and that name's returns is
destroyed. Then run the real 14 specs and record the best Sharpe."""
import pickle, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")
from app.services.research_lab.cross_sectional import CrossSectionalData, run_cross_sectional_backtest
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.cross_sectional_buyback import (
    BUYBACK_FAMILY, BUYBACK_FORMATION_START, default_buyback_config,
)

D = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/lens_conf/"
blob = pickle.load(open(D + "data.pkl", "rb"))
close = blob["close"]
panel = pd.read_pickle(D + "panel.pkl")
cols = list(panel.columns)
cfg = default_buyback_config(); cfg.formation_start = BUYBACK_FORMATION_START
OBS = 0.4204
t0 = time.time()
maxes, sigmas, bests = [], [], []
B = 80
for rep in range(1, B + 1):
    rng = np.random.default_rng(10_000 + rep)
    perm = list(rng.permutation(cols))
    p = panel.copy(); p.columns = perm
    p = p[cols]
    data = CrossSectionalData(close=close, shares_outstanding=p)
    shs = {}
    for spec in BUYBACK_FAMILY:
        r = run_cross_sectional_backtest(data, spec, cfg)
        shs[spec.pattern_id] = sharpe_ratio(r.daily_returns)
    v = list(shs.values())
    maxes.append(max(v)); sigmas.append(float(np.std(v, ddof=1)))
    bests.append(max(shs, key=shs.get))
    if rep % 5 == 0:
        m = np.array(maxes)
        print(f"  rep {rep:3d}: E[max] {m.mean():+.4f} sd {m.std(ddof=1):.4f} "
              f"p90 {np.percentile(m,90):+.4f} P(max>={OBS:.3f})={np.mean(m>=OBS):.4f} "
              f"mean sigma_sr {np.mean(sigmas):.4f}  t={time.time()-t0:.0f}s", flush=True)
m = np.array(maxes)
print(f"\nLABEL-PERMUTATION NULL, B={B}: E[max over 14] {m.mean():+.4f} sd {m.std(ddof=1):.4f} "
      f"p50 {np.median(m):+.4f} p90 {np.percentile(m,90):+.4f} p95 {np.percentile(m,95):+.4f}")
print(f"  EMPIRICAL P(best-of-14 >= {OBS:+.4f}) = {np.mean(m >= OBS):.4f}")
print(f"  mean null sigma_sr {np.mean(sigmas):.4f}")
from collections import Counter
print("  which spec won, under the null:", Counter(bests).most_common())
pickle.dump({"maxes": maxes, "sigmas": sigmas, "bests": bests}, open(D + "null_perm.pkl", "wb"))
print(f"DONE t={time.time()-t0:.0f}s", flush=True)
