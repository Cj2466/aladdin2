"""(a) period control, (b) effective-trials from the real correlation matrix,
(c) EMPIRICAL best-of-14 null via a shared random signal."""
import pickle, sys, time
from datetime import date
from functools import partial

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")

from app.services.research_lab.cross_sectional import (
    CrossSectionalData, CrossSectionalSpec, run_cross_sectional_backtest,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.deflated_sharpe import (
    compute_deflated_sharpe, expected_max_sharpe_under_noise,
)
from app.services.research_lab.cross_sectional_buyback import (
    BUYBACK_FAMILY, BUYBACK_CITATION, BUYBACK_FORMATION_START, BUYBACK_RANK_FRACTION,
    BUYBACK_LOOKBACK_DAYS, BUYBACK_HOLDING_DAYS, BUYBACK_PORTFOLIOS,
    BUYBACK_WINSORIZE_QUANTILE,
    build_point_in_time_share_counts, default_buyback_config, signal_net_share_issuance,
)

D = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/lens_conf/"
blob = pickle.load(open(D + "data.pkl", "rb"))
close, shares, splits = blob["close"], blob["shares"], blob["splits"]
t0 = time.time()
shares_frame = pd.read_pickle(D + "panel.pkl")
AGE = pd.read_pickle(D + "age.pkl")
data = CrossSectionalData(close=close, shares_outstanding=shares_frame)


def run(spec, cfg):
    r = run_cross_sectional_backtest(data, spec, cfg)
    formed = [f for f in r.formations if f.skipped_reason is None]
    return sharpe_ratio(r.daily_returns), r.daily_returns, [f.date for f in formed]


def cfg_at(start):
    c = default_buyback_config()
    c.formation_start = start
    return c


# ---------- (a) PERIOD CONTROL: drop the 2018 coverage hole, no gate --------
print("=== (a) PERIOD CONTROL — ungated, formations start 2019-01-02 (2018 hole excluded) ===", flush=True)
c19 = cfg_at(date(2019, 1, 2))
s19 = {}
for spec in BUYBACK_FAMILY:
    sh, ret, dts = run(spec, c19)
    s19[spec.pattern_id] = (sh, ret, len(dts))
for pid in ["nsi_l126_ls_h126", "nsi_l252_ls_h126", "nsi_l504_ls_h126",
            "nsi_l126_hedged_h126", "nsi_l252_hedged_h126", "nsi_l504_hedged_h126",
            "nsi_l126_ls_h252", "nsi_l252_ls_h252", "nsi_l504_ls_h252"]:
    print(f"  {pid:24s} sharpe {s19[pid][0]:+.3f}  formations {s19[pid][2]}", flush=True)
sig19 = float(np.std([v[0] for v in s19.values()], ddof=1))
b = s19["nsi_l504_ls_h126"]
d19 = compute_deflated_sharpe(b[0], b[1], 14, sig19)
print(f"  sigma_sr {sig19:.4f}  nsi_l504_ls_h126 DSR {d19.dsr:.4f} SR0 {d19.expected_max_sharpe_noise_annualized:.4f}", flush=True)

# ---------- (b) EFFECTIVE TRIALS from the real correlation matrix -----------
print("\n=== (b) EFFECTIVE TRIALS ===", flush=True)
res = pickle.load(open(D + "results.pkl", "rb"))
rets = pd.DataFrame({k: v["ret"] for k, v in res["baseline"].items()}).dropna(how="all")
C = rets.corr()
n = len(C)
off = C.to_numpy()[~np.eye(n, dtype=bool)]
lam = np.linalg.eigvalsh(C.to_numpy())
pr = (lam.sum() ** 2) / (lam ** 2).sum()
kaiser = int((lam > 1.0).sum())
var90 = int(np.searchsorted(np.cumsum(sorted(lam)[::-1]) / lam.sum(), 0.90) + 1)
neff_cn = n / (1 + (n - 1) * off.mean())
print(f"  mean |pairwise corr| of the 14 daily nets: {off.mean():.3f} (min {off.min():.3f} max {off.max():.3f})")
print(f"  winsor vs plain sibling: h126 {C.loc['nsi_l504_ls_h126','nsi_l504_ls_h126_winsor']:.4f}  "
      f"h252 {C.loc['nsi_l504_ls_h252','nsi_l504_ls_h252_winsor']:.4f}")
print(f"  participation ratio (sum L)^2/sum L^2 : {pr:.2f}")
print(f"  eigenvalues > 1 (Kaiser)              : {kaiser}")
print(f"  components for 90% of variance        : {var90}")
print(f"  Cheverud/Nyholt n/(1+(n-1)rbar)       : {neff_cn:.2f}")
sig = res["sigma_sr"]
obs = res["baseline"]["nsi_l504_ls_h126"]["sharpe"]
print(f"  observed sharpe {obs:+.4f}, sigma_sr {sig:.4f}")
for N in (2, 3, 4, 5, 6, 7, 10, 14, 20, 50):
    sr0d = expected_max_sharpe_under_noise(sig / np.sqrt(252.0), N)
    if sr0d is None:
        continue
    dd = compute_deflated_sharpe(obs, res["baseline"]["nsi_l504_ls_h126"]["ret"], max(N, 5), sig)
    print(f"    N={N:3d}: SR0 {sr0d*np.sqrt(252.0):+.4f}  DSR {dd.dsr:.4f}")

# ---------- (c) EMPIRICAL BEST-OF-14 NULL -----------------------------------
print("\n=== (c) EMPIRICAL BEST-OF-14 NULL (shared random signal, real masks/dates) ===", flush=True)
SEED = [0]


def signal_random(history, *, lookback_days, winsorize_quantile=None):
    base = signal_net_share_issuance(history, lookback_days=lookback_days,
                                     winsorize_quantile=winsorize_quantile)
    d = history.close.index[-1]
    rng = np.random.default_rng((SEED[0] * 1_000_003 + int(d.value // 10 ** 9)) % (2 ** 62))
    cols = list(base.index)
    vals = pd.Series(rng.standard_normal(len(cols)), index=cols)
    return vals.where(base.notna())


def random_family():
    specs = []
    for lb in BUYBACK_LOOKBACK_DAYS:
        for pf in BUYBACK_PORTFOLIOS:
            tag = "ls" if pf == "long_short" else "hedged"
            for h in BUYBACK_HOLDING_DAYS:
                specs.append(CrossSectionalSpec(
                    pattern_id=f"rnd_l{lb}_{tag}_h{h}", family="net_share_issuance",
                    citation=BUYBACK_CITATION,
                    signal_fn=partial(signal_random, lookback_days=lb),
                    lookback_days=lb + 1, holding_days=h, portfolio=pf,
                    rank_fraction=BUYBACK_RANK_FRACTION, requires_shares_outstanding=True))
    for h in BUYBACK_HOLDING_DAYS:
        specs.append(CrossSectionalSpec(
            pattern_id=f"rnd_l504_ls_h{h}_winsor", family="net_share_issuance",
            citation=BUYBACK_CITATION,
            signal_fn=partial(signal_random, lookback_days=504,
                              winsorize_quantile=BUYBACK_WINSORIZE_QUANTILE),
            lookback_days=505, holding_days=h, portfolio="long_short",
            rank_fraction=BUYBACK_RANK_FRACTION, requires_shares_outstanding=True))
    return specs


RF = random_family()
cfull = cfg_at(BUYBACK_FORMATION_START)
maxes, sigmas, alls = [], [], []
B = 120
for rep in range(1, B + 1):
    SEED[0] = rep
    shs = []
    for spec in RF:
        sh, ret, _ = run(spec, cfull)
        shs.append(sh)
    maxes.append(max(shs))
    sigmas.append(float(np.std(shs, ddof=1)))
    alls.append(shs)
    if rep % 10 == 0:
        m = np.array(maxes)
        print(f"  rep {rep:3d}: E[max] {m.mean():+.4f}  sd {m.std(ddof=1):.4f}  "
              f"P(max >= {obs:.3f}) = {np.mean(m >= obs):.3f}  "
              f"mean sigma_sr {np.mean(sigmas):.4f}", flush=True)

m = np.array(maxes)
print(f"\n  EMPIRICAL, B={B}: E[max sharpe over the 14 | no edge] = {m.mean():+.4f} "
      f"(sd {m.std(ddof=1):.4f}, p50 {np.median(m):+.4f}, p90 {np.percentile(m,90):+.4f}, "
      f"p95 {np.percentile(m,95):+.4f})")
print(f"  DSR's parametric SR0 for N=14, sigma_sr={sig:.4f}: "
      f"{expected_max_sharpe_under_noise(sig/np.sqrt(252.), 14)*np.sqrt(252.):+.4f}")
print(f"  mean of the 14 null sigma_sr estimates: {np.mean(sigmas):.4f} (real run: {sig:.4f})")
print(f"  EMPIRICAL P(best-of-14 >= observed {obs:+.4f}) = {np.mean(m >= obs):.4f}")
pickle.dump({"maxes": maxes, "sigmas": sigmas, "alls": alls}, open(D + "null.pkl", "wb"))
print(f"DONE t={time.time()-t0:.0f}s", flush=True)
