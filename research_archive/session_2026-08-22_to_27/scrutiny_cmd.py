"""Second-pass scrutiny of cmd_momentum_l126_h126_inverse_vol.

(1) Per-formation leg composition + exact per-ticker P&L attribution
    (via instrumenting _leg_weighted_return, so the numbers are the
    harness's own, not a reconstruction).
(2) Counterfactual universes: drop UNG, drop WEAT, drop both.
(3) Effective independent trials across the 24-spec grid, from the real
    daily return streams, and the DSR recomputed at that effective N.
"""
import sys, warnings, pickle
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-1/backend")
import numpy as np
import pandas as pd
from datetime import date
from collections import Counter, defaultdict

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab import cross_sectional as CS
from app.services.research_lab.cross_sectional import (
    run_cross_sectional_backtest, fixed_universe_membership, CrossSectionalData,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_commodities import (
    COMMODITIES_UNIVERSE, build_commodities_family, build_commodities_price_panel,
    build_inverse_vol_basis, default_commodities_config, COMMODITIES_N_TRIALS,
)
from app.services.research_lab.metrics import sharpe_ratio, TRADING_DAYS_PER_YEAR
from app.services.research_lab import deflated_sharpe as DS

OUT = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
BEST = "cmd_momentum_l126_h126_inverse_vol"

provider = YFinanceProvider()
panel, flags, missing = build_commodities_price_panel(provider, end=date.today())
print(f"panel {panel.index[0].date()}..{panel.index[-1].date()} rows={len(panel)} missing={missing}")
pickle.dump(panel, open(f"{OUT}/cmd_panel.pkl", "wb"))

basis = build_inverse_vol_basis(panel)
data = CrossSectionalData(close=panel, leg_weight_basis=basis)
membership = fixed_universe_membership(COMMODITIES_UNIVERSE)
config = default_commodities_config()
specs = {s.pattern_id: s for s in build_commodities_family()}

# ---------------- instrumented replay for exact attribution ----------------
records = []          # (ts, side, {ticker: weight}, {ticker: contrib})
_orig = CS._leg_weighted_return
def _instr(day, weights):
    val = _orig(day, weights)
    if weights:
        contrib = {t: float(weights[t]) * float(day.get(t, np.nan)) for t in weights}
        records.append((day.name, dict(weights), contrib))
    else:
        records.append((day.name, {}, {}))
    return val
CS._leg_weighted_return = _instr
res = run_cross_sectional_backtest(data, specs[BEST], config, membership)
CS._leg_weighted_return = _orig

r = res.daily_returns
print(f"\n{BEST}: sharpe {sharpe_ratio(r):+.4f} n_days={len(r)} "
      f"cum(sum)={r.sum():+.2%} ann_vol={r.std(ddof=1)*np.sqrt(252):.1%}")
formed = [f for f in res.formations if f.skipped_reason is None]
print(f"formations formed={len(formed)} skipped={len(res.formations)-len(formed)}")

# records come in (long, short) pairs per realized day, in order
assert len(records) % 2 == 0
longC, shortC = defaultdict(float), defaultdict(float)
longW, shortW = defaultdict(list), defaultdict(list)
for k in range(0, len(records), 2):
    ts, lw, lc = records[k]
    ts2, sw, sc = records[k+1]
    assert ts == ts2
    for t, v in lc.items():
        if np.isfinite(v): longC[t] += v
    for t, v in sc.items():
        if np.isfinite(v): shortC[t] -= v   # short leg is subtracted in `gross`
    for t, w in lw.items(): longW[t].append(w)
    for t, w in sw.items(): shortW[t].append(w)

gross_total = sum(longC.values()) + sum(shortC.values())
print(f"\nattribution check: sum of per-ticker contributions (gross, pre-cost) = {gross_total:+.2%}; "
      f"net daily sum = {r.sum():+.2%}; cost_drag={res.total_cost:.2%} fin={res.total_financing_cost:.2%}")

print("\n--- LONG-leg cumulative arithmetic contribution (sum of w*ret) ---")
for t, v in sorted(longC.items(), key=lambda x: -x[1]):
    print(f"  {t:5s} {v:+8.2%}  (avg wt {np.mean(longW[t]):.3f}, days held {len(longW[t])})")
print("--- SHORT-leg cumulative arithmetic contribution (-w*ret) ---")
for t, v in sorted(shortC.items(), key=lambda x: -x[1]):
    print(f"  {t:5s} {v:+8.2%}  (avg wt {np.mean(shortW[t]):.3f}, days held {len(shortW[t])})")

lc_ung = longC.get("UNG", 0.0) + longC.get("WEAT", 0.0)
sc_ung = shortC.get("UNG", 0.0) + shortC.get("WEAT", 0.0)
print(f"\nUNG+WEAT total contribution: long {lc_ung:+.2%} short {sc_ung:+.2%} "
      f"combined {lc_ung+sc_ung:+.2%} of gross {gross_total:+.2%} "
      f"= {100*(lc_ung+sc_ung)/gross_total:.1f}%")
print(f"SHORT-leg total {sum(shortC.values()):+.2%}; LONG-leg total {sum(longC.values()):+.2%}")

print("\n--- per-formation legs ---")
lcount, scount = Counter(), Counter()
for f in formed:
    lcount.update(f.long_tickers); scount.update(f.short_tickers)
    print(f"  {f.date.date()}  L={sorted(f.long_tickers)}  S={sorted(f.short_tickers)}")
print(f"long-leg counts:  {dict(lcount.most_common())}")
print(f"short-leg counts: {dict(scount.most_common())}")

pickle.dump({"records": records, "formations": [(f.date, f.long_tickers, f.short_tickers, f.skipped_reason) for f in res.formations],
             "daily": r}, open(f"{OUT}/cmd_attrib.pkl", "wb"))

# ---------------- counterfactual universes ----------------
print("\n=== COUNTERFACTUALS (same spec, name removed from the universe) ===")
for drop in ([], ["UNG"], ["WEAT"], ["UNG", "WEAT"]):
    keep = [t for t in COMMODITIES_UNIVERSE if t not in drop]
    p2 = panel[keep]
    d2 = CrossSectionalData(close=p2, leg_weight_basis=build_inverse_vol_basis(p2))
    m2 = fixed_universe_membership(tuple(keep))
    r2 = run_cross_sectional_backtest(d2, specs[BEST], default_commodities_config(), m2)
    leg = max(1, int(len(keep) / 3))
    lab = "none" if not drop else "+".join(drop)
    if r2.status != "ok":
        print(f"  drop {lab:10s}: status={r2.status}")
        continue
    s2 = r2.daily_returns
    print(f"  drop {lab:10s}: n={len(keep)} leg={leg} sharpe {sharpe_ratio(s2):+.3f} "
          f"cum {s2.sum():+.2%} vol {s2.std(ddof=1)*np.sqrt(252):.1%} nform={len([f for f in r2.formations if f.skipped_reason is None])}")

# ---------------- passive short baselines ----------------
print("\n=== PASSIVE BASELINES over the same replay window ===")
win = panel.loc[r.index[0]:r.index[-1]]
dr = win.pct_change(fill_method=None)
yrs = (win.index[-1]-win.index[0]).days/365.25
for t in ("UNG", "WEAT", "USO", "CORN", "SOYB"):
    x = dr[t].dropna()
    cagr = float(np.exp(np.log1p(x).sum()/yrs)-1)
    print(f"  {t:5s} CAGR {cagr:+.2%}/yr  arithmetic-sum {x.sum():+.2%}  sharpe of SHORT {sharpe_ratio(-x):+.3f}")
# static short UNG+WEAT, inverse-vol-ish equal, vs long the rest
short_bk = -0.5*(dr["UNG"].fillna(0)+dr["WEAT"].fillna(0))
print(f"  static equal short UNG+WEAT (gross 1.0): sharpe {sharpe_ratio(short_bk):+.3f} sum {short_bk.sum():+.2%}")
rest = [t for t in COMMODITIES_UNIVERSE if t not in ("UNG","WEAT")]
ls = dr[rest].mean(axis=1).fillna(0) - 0.5*(dr["UNG"].fillna(0)+dr["WEAT"].fillna(0))
print(f"  long EW(other 9) / short EW(UNG,WEAT), NO signal at all: sharpe {sharpe_ratio(ls):+.3f} sum {ls.sum():+.2%}")

# ---------------- effective independent trials ----------------
print("\n=== EFFECTIVE INDEPENDENT TRIALS in the 24-spec grid ===")
daily_by = {}
for pid, sp in specs.items():
    rr = run_cross_sectional_backtest(data, sp, default_commodities_config(), membership)
    if rr.status == "ok":
        daily_by[pid] = rr.daily_returns
M = pd.DataFrame(daily_by).dropna(how="any")
print(f"aligned matrix {M.shape}")
C = M.corr()
lam = np.linalg.eigvalsh(C.to_numpy())
neff_eig = float(lam.sum()**2/(lam**2).sum())
off = C.where(np.triu(np.ones_like(C, dtype=bool), 1)).stack()
mean_corr = float(off.mean())
n = C.shape[0]
neff_kaiser = int((lam > 1.0).sum())
# variance explained: components needed for 95%
lam_s = np.sort(lam)[::-1]
cum = np.cumsum(lam_s)/lam_s.sum()
n95 = int(np.searchsorted(cum, 0.95)+1)
# Meff (Cheverud/Nyholt): 1 + (M-1)*(1 - var(lambda)/M)
meff_ny = 1 + (n-1)*(1 - np.var(lam, ddof=0)/n)
print(f"n={n} specs; mean pairwise corr {mean_corr:+.3f}, median {float(off.median()):+.3f}, "
      f"min {float(off.min()):+.3f}, max {float(off.max()):+.3f}")
print(f"eigenvalue effective N (sum^2/sumsq): {neff_eig:.2f}")
print(f"Kaiser (lambda>1): {neff_kaiser}   PCs for 95% var: {n95}   Nyholt-Cheverud Meff: {meff_ny:.2f}")
print("top eigenvalues:", np.round(lam_s[:8], 2).tolist())

# correlation among the near-duplicate pairs the prompt flags
print("\npairs sharing lookback+hold, differing only in leg_weighting:")
for base in [p[:-len("_equal")] for p in daily_by if p.endswith("_equal")]:
    a, b = base+"_equal", base+"_inverse_vol"
    if a in C.index and b in C.index:
        print(f"  {base:32s} corr {C.loc[a,b]:+.3f}")

sharpes = pd.Series({p: sharpe_ratio(s) for p, s in daily_by.items()}).sort_values(ascending=False)
print("\nall 24 Sharpes:"); print(sharpes.round(3).to_string())
sigma_sr = float(sharpes.std(ddof=1))
print(f"\nsigma_sr(annualized, across 24 siblings) = {sigma_sr:.4f}")

best_r = daily_by[BEST]
for N in (24, int(round(neff_eig)), neff_kaiser, n95, 8, 6, 5):
    d = DS.compute_deflated_sharpe(best_r, n_trials=int(N), sigma_sr_annualized=sigma_sr)
    print(f"  n_trials={N:3d} -> DSR {d.dsr if d.dsr is None else round(d.dsr,4)}  "
          f"SR0_ann={None if d.sr0_annualized is None else round(d.sr0_annualized,3)}")
