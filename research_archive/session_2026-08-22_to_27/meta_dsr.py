import json, re, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np, pandas as pd
from scipy.stats import norm
from app.services.research_lab.deflated_sharpe import (
    expected_max_sharpe_under_noise, probabilistic_sharpe_ratio)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR as TD

D = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
fam = {}

# Round C (30) - magnitude-weighted production log
txt = open(f"{D}/round_c_weighted_run.log").read()
rc = [float(m) for m in re.findall(r"^\S+\s+\S+\s+\d+\s+\d+\s+(-?\d+\.\d+)\s+\d+\.\d+\s+\d+\.\d+$", txt, re.M)]
fam["RoundC"] = rc
# D1 (21)
d1 = [float(m) for m in re.findall(r"^ivol_\S+\s+(-?\d+\.\d+)\s+21\s", open(f"{D}/d1_production_report.txt").read(), re.M)]
fam["D1_ivol"] = d1
# D2 (4)
fam["D2_reversal"] = [-0.0716, -0.1228, -0.2160, -0.2782]
# Bonds (18)
b = json.load(open(f"{D}/bonds_meta_result.json"))
fam["Bonds"] = [r["sharpe"] for r in b["results"]]
# FX (36)
fx = pd.read_csv(f"{D}/fx_production_results.csv")
fam["FX"] = list(fx["sharpe"].astype(float))
# Commodities (24)
cm = json.load(open(f"{D}/commodities_meta_result.json"))
fam["Commodities"] = [r["sharpe"] for r in cm["results"]]
CM = [r for r in cm["results"] if r["pattern_id"] == "cmd_momentum_l126_h126_inverse_vol"][0]["dsr"]
# Buyback (14)
bb = json.load(open(f"{D}/buyback_production_result.json"))
fam["Buyback"] = [r["sharpe"] for r in bb["results"]]
BB = [r for r in bb["results"] if r["pattern_id"] == "nsi_l504_ls_h126"][0]["deflated_sharpe"]

print("=" * 76)
print("STEP 1 -- VERIFIED FAMILY SIZES AND WITHIN-FAMILY SHARPE DISPERSION")
print("=" * 76)
print(f"{'family':14s} {'k':>4s} {'sigma_sr(own)':>14s} {'maxSR':>8s} {'meanSR':>8s}")
tot = 0
for k, v in fam.items():
    tot += len(v)
    print(f"{k:14s} {len(v):4d} {np.std(v, ddof=1):14.4f} {max(v):+8.3f} {np.mean(v):+8.3f}")
print(f"{'TOTAL':14s} {tot:4d}   (+ LPS-intraday-only: an explicit FILTER over RoundC's 30, 0 new trials)")
allsr = [s for v in fam.values() for s in v]
sig_pool = float(np.std(allsr, ddof=1))
print(f"\npooled sigma_sr across all {len(allsr)} annualized Sharpes = {sig_pool:.4f}")
print(f"largest single-family sigma_sr = {max(np.std(v, ddof=1) for v in fam.values()):.4f}")

def meta(name, R, n_family, sig_own):
    sr_d = R["sharpe_net_annualized"] / np.sqrt(TD)
    n, sk, ku = R["n_observations"], R["skewness"], R["kurtosis"]
    print("\n" + "=" * 76)
    print(f"STEP 2 -- {name}: SR={R['sharpe_net_annualized']:+.4f}  n={n}  skew={sk:+.3f}  kurt={ku:.2f}")
    print(f"  as-run: n_trials={n_family}, sigma_sr={sig_own:.4f} -> SR0={R['expected_max_sharpe_noise_annualized']:.4f}, DSR={R['dsr']:.4f}")
    print("=" * 76)
    print(f"{'sigma_sr basis':22s} {'N':>5s} {'SR0_ann':>9s} {'meta-DSR':>9s}")
    rows = []
    for lab, sg in (("own family", sig_own), ("pooled cross-family", sig_pool)):
        for N in (n_family, 7, 129, 147, 177, 359):
            sr0d = expected_max_sharpe_under_noise(sg / np.sqrt(TD), N)
            dsr = probabilistic_sharpe_ratio(sr_d, sr0d, n, sk, ku)
            rows.append((lab, N, sr0d * np.sqrt(TD), dsr))
            print(f"{lab:22s} {N:5d} {sr0d*np.sqrt(TD):9.4f} {dsr:9.4f}")
    return rows

meta("COMMODITIES cmd_momentum_l126_h126_inverse_vol", CM, 24, CM["sigma_sr_annualized"])
meta("BUYBACK nsi_l504_ls_h126", BB, 14, BB["sigma_sr_annualized"])

print("\n" + "=" * 76)
print("STEP 3 -- FAMILY-LEVEL SIDAK (best-of-7-families), the cleanest framing")
print("=" * 76)
print("Under the null true_SR = SR0(family), the PSR z-stat is asymptotically")
print("N(0,1), so DSR ~ U(0,1) and (1-DSR) is a valid p-value. Selecting the")
print("max over k near-independent families: P(max DSR <= u) = u^k.")
for name, d, k in (("Commodities", CM["dsr"], 7), ("Buyback", BB["dsr"], 7)):
    for kk in (5, 7, 8):
        print(f"  {name:12s} DSR={d:.4f}  k={kk}  study-wise meta-DSR = {d**kk:.4f}  (p_studywise={1-d**kk:.4f})")

print("\n" + "=" * 76)
print("STEP 4 -- DIRECT MAX-STATISTIC CHECK (no DSR nesting)")
print("=" * 76)
print("Under H0: all N trials have true SR=0 and observed SRs ~ N(0, sigma_sr),")
print("P(max >= x) = 1 - Phi(x/sigma_sr)^N.")
for lab, sg in (("own-family sigma", CM["sigma_sr_annualized"]), ("pooled sigma", sig_pool)):
    for N in (24, 147):
        p = 1 - norm.cdf(0.9069 / sg) ** N
        print(f"  Commodities SR=+0.9069  {lab:18s} ({sg:.4f})  N={N:3d}  P(max>=SR)={p:.4f}")
for lab, sg in (("own-family sigma", BB["sigma_sr_annualized"]), ("pooled sigma", sig_pool)):
    for N in (14, 147):
        p = 1 - norm.cdf(0.4120 / sg) ** N
        print(f"  Buyback     SR=+0.4120  {lab:18s} ({sg:.4f})  N={N:3d}  P(max>=SR)={p:.4f}")
