"""Production run of Build D2 (long-horizon price reversal, De Bondt &
Thaler 1985) -- the first real production run of screen_d2_reversal_family,
against real yfinance data. No synthetic provider, no fake data.

Pre-specified BEFORE seeing any result (this project's standing p-hacking
discipline): start = MEMBERSHIP_DATA_START, end = today, the full
pre-declared 4-definition D2_FAMILY as already committed in
cross_sectional_patterns_d2.py. No parameter here is chosen after peeking
at output.

Delisting-return imputation: config=None is passed deliberately, so
screen_d2_reversal_family constructs its OWN default
CrossSectionalConfig(impute_delisting_returns=True) -- i.e. Shumway
imputation IS ON for this run. Reasoning (matches the module's own audited
design, re-affirmed here rather than second-guessed): D2's long leg is, by
construction, the extreme past LOSERS (the reversal signal is negated
trailing return, see signal_long_horizon_reversal), which is exactly the
sub-population most likely to delist mid-hold via bankruptcy/distress. The
harness's own default (impute_delisting_returns=False, silently dropping a
delisted name at its last price) would understate precisely the risk this
family's long leg is adversely selected for, flattering its Sharpe. Leaving
config=None keeps that opt-in live for this real run rather than reverting
to the generic harness default.
"""
import sys
import time
import traceback
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

from app.services.research_lab.cross_sectional_patterns_d2 import (
    D2_FAMILY,
    D2_N_TRIALS,
    screen_d2_reversal_family,
)
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

REPORT_PATH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/d2_production_raw.txt"

start = MEMBERSHIP_DATA_START
end = date.today()

print(f"Starting D2 (long-horizon price reversal) production screening: {start} -> {end}", flush=True)
print(f"Family size (pre-declared n_trials): {D2_N_TRIALS} -- {[s.pattern_id for s in D2_FAMILY]}", flush=True)
print("Delisting imputation: config=None -> function's own default, impute_delisting_returns=True", flush=True)

start_time = time.time()
try:
    summary = screen_d2_reversal_family(start=start, end=end, provider=None, config=None)
except Exception:
    elapsed = time.time() - start_time
    with open(REPORT_PATH, "w") as f:
        f.write(f"D2 production screening FAILED after {elapsed:.1f}s\n")
        f.write(traceback.format_exc())
    print(f"FAILED after {elapsed:.1f}s", flush=True)
    traceback.print_exc()
    sys.exit(1)

elapsed = time.time() - start_time

lines = []
lines.append(f"D2 (long-horizon price reversal) production screening -- completed in {elapsed:.1f}s")
lines.append(f"Window: {start.isoformat()} -> {end.isoformat()}")
lines.append(f"n_trials (family size, pre-declared): {D2_N_TRIALS}")
lines.append(f"Delisting-return imputation: ON (impute_delisting_returns=True, function default)")
lines.append(f"Tickers requested but unresolved (no price data at all): {len(summary.missing_price_data)}")
lines.append(f"Specs that produced a usable replay (>= MIN_REPLAY_TRADING_DAYS): {len(summary.results)} / {D2_N_TRIALS}")
lines.append("")
lines.append(
    f"{'pattern_id':<32} {'n_form':>7} {'n_days':>7} {'sharpe':>9} "
    f"{'n_trials':>9} {'dsr':>8} {'psr0':>8} {'dsr_floor_met':>14}"
)
for r in summary.results:
    ds = r.deflated_sharpe
    dsr_val = f"{ds.dsr:.4f}" if ds.dsr is not None else "None"
    psr_val = f"{ds.psr_vs_zero:.4f}" if ds.psr_vs_zero is not None else "None"
    lines.append(
        f"{r.pattern_id:<32} {r.n_formations:>7} {r.n_trading_days:>7} {r.sharpe_annualized:>9.4f} "
        f"{ds.n_trials:>9} {dsr_val:>8} {psr_val:>8} {str(ds.dsr_floor_met):>14}"
    )

lines.append("")
lines.append("Full per-result detail:")
for r in summary.results:
    ds = r.deflated_sharpe
    lines.append(f"--- {r.pattern_id} ---")
    lines.append(f"  family: {r.family}")
    lines.append(f"  citation: {r.citation}")
    lines.append(f"  n_formations: {r.n_formations}")
    lines.append(f"  n_skipped_formations: {r.n_skipped_formations}")
    lines.append(f"  avg_names_per_leg: {r.avg_names_per_leg:.3f}")
    lines.append(f"  n_trading_days: {r.n_trading_days}")
    lines.append(f"  sharpe_annualized: {r.sharpe_annualized:.6f}")
    lines.append(f"  total_cost_drag: {r.total_cost_drag:.6f}")
    lines.append(f"  n_value_weighted_legs: {r.n_value_weighted_legs}")
    lines.append(f"  n_value_weight_fallbacks: {r.n_value_weight_fallbacks}")
    lines.append(f"  deflated_sharpe.sharpe_net_annualized: {ds.sharpe_net_annualized:.6f}")
    lines.append(f"  deflated_sharpe.sharpe_net_daily: {ds.sharpe_net_daily:.6f}")
    lines.append(f"  deflated_sharpe.n_observations: {ds.n_observations}")
    lines.append(f"  deflated_sharpe.skewness: {ds.skewness:.6f}")
    lines.append(f"  deflated_sharpe.kurtosis: {ds.kurtosis:.6f}")
    lines.append(f"  deflated_sharpe.psr_vs_zero: {ds.psr_vs_zero}")
    lines.append(f"  deflated_sharpe.n_trials: {ds.n_trials}")
    lines.append(f"  deflated_sharpe.sigma_sr_annualized: {ds.sigma_sr_annualized}")
    lines.append(f"  deflated_sharpe.expected_max_sharpe_noise_annualized: {ds.expected_max_sharpe_noise_annualized}")
    lines.append(f"  deflated_sharpe.dsr: {ds.dsr}")
    lines.append(f"  deflated_sharpe.dsr_floor_met: {ds.dsr_floor_met}")
    lines.append(f"  deflated_sharpe.interpretation: {ds.interpretation}")
    lines.append("")

# Which pre-declared specs did NOT produce a usable replay at all
produced_ids = {r.pattern_id for r in summary.results}
missing_specs = [s.pattern_id for s in D2_FAMILY if s.pattern_id not in produced_ids]
lines.append(f"Pre-declared specs with NO usable replay result: {missing_specs if missing_specs else '(none -- all 4 produced results)'}")
lines.append("")

lines.append("=== INDEPENDENT-WINDOW DISCLOSURE (typed field, verbatim) ===")
d = summary.independent_window_disclosure
lines.append(f"n_trading_days_replayed: {d.n_trading_days_replayed}")
lines.append(f"holding_days: {d.holding_days}")
lines.append(f"n_full_independent_windows: {d.n_full_independent_windows}")
lines.append(f"partial_window_fraction: {d.partial_window_fraction:.4f}")
lines.append("text:")
lines.append(d.text)
lines.append("")

lines.append("Missing tickers (no price data resolved at all):")
lines.append(", ".join(sorted(summary.missing_price_data)) if summary.missing_price_data else "(none)")
lines.append("")
lines.append(f"n missing tickers: {len(summary.missing_price_data)}")

report = "\n".join(lines)
print(report, flush=True)
with open(REPORT_PATH, "w") as f:
    f.write(report + "\n")

print(f"\nRaw report written to {REPORT_PATH}", flush=True)
