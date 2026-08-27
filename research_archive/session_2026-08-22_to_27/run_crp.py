import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a6fc3015debbbe27e/backend")

from app.services.research_lab.cross_sectional_correlation_risk_premium import (
    CRP_N_TRIALS,
    run_crp_screening,
)

s = run_crp_screening(include_pit_crosscheck=False)

print("=== CBOE DATA AS CONSUMED BY THE MODULE ===")
print("starts:", s.cboe_starts, " rows:", s.cboe_rows)
print("missing instruments:", s.missing_instruments)
print("formations:", s.formation_calendar_start, "->", s.formation_calendar_end)
print(f"\nn_trials (pre-declared) = {CRP_N_TRIALS}; specs replayed = {len(s.results)}")

hdr = (f"{'spec_id':<26}{'Shrp':>7}{'DSR':>8}{'PSR':>7}{'boot_p':>8}{'resid':>8}"
       f"{'spy_b':>7}{'meanPos':>8}{'lvlVIX':>8}{'chgVIX':>8}{'retVIX':>8}{'n_form':>7}{'susp':>6}")
print("\n" + hdr)
print("-" * len(hdr))
for r in s.results:
    d = r.deflated_sharpe
    c = r.confound
    o = r.overlap
    f = lambda v, p=3: ("  n/a" if v is None else f"{v:.{p}f}")
    print(f"{r.spec_id:<26}{r.sharpe_annualized:>7.3f}{f(d.dsr):>8}{f(d.psr_vs_zero):>7}"
          f"{f(c.bootstrap_p_value):>8}{c.residual_sharpe:>8.3f}{c.spy_beta:>7.3f}"
          f"{c.mean_position:>8.3f}{f(o.signal_level_corr_vs_vix):>8}"
          f"{f(o.signal_change_corr_vs_vix):>8}{f(o.return_corr_vs_vix_spec):>8}"
          f"{c.n_formations:>7}{'YES' if o.is_suspect else 'no':>6}")

print("\n=== SUBPERIOD SHARPES (equal thirds) + buy&hold ===")
for r in s.results:
    sp = ", ".join(f"{x:+.2f}" for x in r.confound.subperiod_sharpes)
    print(f"{r.spec_id:<26} [{sp}]   B&H SPY Sharpe={r.confound.buy_and_hold_sharpe:.3f}  "
          f"fracLong={r.confound.fraction_long:.3f}  meanAbsPos={r.confound.mean_abs_position:.3f}")

print("\n=== sigma_sr / SR0 (shared across family) ===")
if s.results:
    d = s.results[0].deflated_sharpe
    print("sigma_sr_annualized =", d.sigma_sr_annualized)
    print("SR0 (expected max Sharpe from 15 zero-edge trials) =",
          d.expected_max_sharpe_noise_annualized)
    print("n_obs of best:", d.n_observations, "skew", round(d.skewness, 3), "kurt", round(d.kurtosis, 3))

print("\n=== DISCLOSURE ===")
for line in s.disclosure:
    print(" -", line)

print("\n=== BEST CRP-HYPOTHESIS SPEC (not best overall) ===")
crp_only = [r for r in s.results if r.is_crp_hypothesis]
if crp_only:
    b = crp_only[0]
    print(b.spec_id, "Sharpe", round(b.sharpe_annualized, 4), "DSR", b.deflated_sharpe.dsr)
    print(b.overlap.reason)
    print(b.deflated_sharpe.interpretation)
