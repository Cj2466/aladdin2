"""THE production screening run: both re-run families, real yfinance data,
real point-in-time S&P 600 universe, 2020-01-01 .. today."""
import sys
import time
import warnings
from datetime import date

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_82071471-600-1/backend")

from app.services.research_lab import cross_sectional_small_mid_cap as sc
from app.services.research_lab import small_cap_membership_history as scm

START, END = date(2020, 1, 1), date.today()


def show(results, n_trials, label):
    print(f"\n===== {label}: {len(results)} of the specs returned a usable replay "
          f"(n_trials={n_trials}) =====", flush=True)
    print(f"{'pattern_id':42s} {'SR':>7s} {'DSR':>7s} {'PSR':>6s} {'form':>5s} {'leg':>5s} "
          f"{'days':>5s} {'costdrag':>9s}", flush=True)
    for r in results:
        d = r.deflated_sharpe
        dsr = f"{d.dsr:.3f}" if d.dsr is not None else "  n/a"
        psr = f"{d.psr_vs_zero:.2f}" if d.psr_vs_zero is not None else " n/a"
        print(f"{r.pattern_id:42s} {r.sharpe_annualized:+7.3f} {dsr:>7s} {psr:>6s} "
              f"{r.n_formations:5d} {r.avg_names_per_leg:5.0f} {r.n_trading_days:5d} "
              f"{r.total_cost_drag:9.4f}", flush=True)
    if results:
        best = max(results, key=lambda r: r.sharpe_annualized)
        print(f"  best raw Sharpe: {best.pattern_id} {best.sharpe_annualized:+.3f}; "
              f"DSR={best.deflated_sharpe.dsr}; floor_met={best.deflated_sharpe.dsr_floor_met}",
              flush=True)
        print(f"  sigma_sr(annualized) across siblings: "
              f"{best.deflated_sharpe.sigma_sr_annualized}", flush=True)


print("=" * 78, flush=True)
print("S&P 600 SMALL-CAP RE-RUN OF EXISTING CROSS-SECTIONAL FAMILIES", flush=True)
print(f"window {START} .. {END}   cost {sc.SMALL_CAP_COST_BPS}bps one-way   "
      f"holds {sc.SMALL_CAP_HOLDING_DAYS}", flush=True)
print("=" * 78, flush=True)

q = scm.membership_data_quality()
print("\n--- point-in-time S&P 600 membership data quality ---", flush=True)
for k, v in q.items():
    print(f"  {k}: {v}", flush=True)
print(f"  point-in-time union universe: {len(scm.get_universe_over(START, END))} tickers", flush=True)

print("\n--- FAMILY A: Round C disposition core (George-Hwang + Grinblatt-Han) ---", flush=True)
print(f"  reused family size {sc.REUSED_DISPOSITION_FAMILY_SIZE}, "
      f"specs re-run {len(sc.SMALL_CAP_DISPOSITION_FAMILY)}, "
      f"n_trials {sc.DISPOSITION_N_TRIALS}", flush=True)
t0 = time.time()
res_d, missing_d, recycled_d, trunc_d = sc.run_small_cap_disposition_screening(START, END)
print(f"  fetched+screened in {time.time() - t0:.0f}s | no price: {len(missing_d)} | "
      f"recycled dropped: {len(recycled_d)} | truncated: {len(trunc_d)}", flush=True)
print(f"  recycled tickers dropped: {recycled_d}", flush=True)
show(res_d, sc.DISPOSITION_N_TRIALS, "DISPOSITION (n_trials=36)")

print("\n\n--- FAMILY B: Build D1 idiosyncratic volatility (value-weighted) ---", flush=True)
print(f"  reused family size {sc.REUSED_IVOL_FAMILY_SIZE}, "
      f"specs re-run {len(sc.SMALL_CAP_IVOL_FAMILY)}, "
      f"n_trials {sc.IVOL_N_TRIALS}", flush=True)
t0 = time.time()
res_i, missing_i, recycled_i, trunc_i, no_shares = sc.run_small_cap_ivol_screening(START, END)
print(f"  fetched+screened in {time.time() - t0:.0f}s | no price: {len(missing_i)} | "
      f"recycled dropped: {len(recycled_i)} | truncated: {len(trunc_i)} | "
      f"no share history: {len(no_shares)}", flush=True)
show(res_i, sc.IVOL_N_TRIALS, "IVOL (n_trials=42)")
if res_i:
    tot_legs = sum(r.n_value_weighted_legs for r in res_i)
    tot_fb = sum(r.n_value_weight_fallbacks for r in res_i)
    print(f"\n  value-weighting fallback rate: {tot_fb}/{tot_legs} legs "
          f"({tot_fb / max(tot_legs, 1) * 100:.1f}%) fell back to magnitude weighting", flush=True)

print("\nDONE", flush=True)
