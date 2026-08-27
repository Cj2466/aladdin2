"""The REAL production screening run of the Commodities family against live
yfinance data. Prints every spec (no cherry-picking) plus the full summary."""
import logging
import sys

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-1/backend")
logging.basicConfig(level=logging.WARNING)

from app.services.research_lab.cross_sectional_commodities import run_commodities_screening

summary = run_commodities_screening()

print("=" * 78)
print("PANEL:", summary.panel_start, "..", summary.panel_end, f"({summary.n_panel_rows} rows)")
print("missing price data:", summary.missing_price_data)
print("bad prints scrubbed:", summary.n_bad_prints_scrubbed, summary.bad_prints_by_ticker)
print(f"effective breadth: {summary.effective_breadth:.2f} of 11; max pair "
      f"{summary.max_pair} at {summary.max_pair_correlation:+.3f}")
print("excluded redundant:", summary.excluded_redundant)
print("signal-kind correlations:", {k: round(v, 3) for k, v in summary.signal_kind_correlations.items()})
print("warnings:", summary.warnings)
print("n_trials:", summary.n_trials, "| specs returned:", len(summary.results))
print("=" * 78)
header = f"{'pattern_id':38s} {'sharpe':>7s} {'DSR':>6s} {'PSR0':>6s} {'nform':>5s} {'skip':>4s} {'days':>5s} {'cost':>7s} {'fin':>7s} {'ivolFB':>6s}"
print(header)
for r in summary.results:
    d = r.deflated_sharpe
    dsr = f"{d.dsr:.3f}" if d.dsr is not None else "  n/a"
    psr = f"{d.psr_vs_zero:.3f}" if d.psr_vs_zero is not None else "  n/a"
    fb = f"{r.n_value_weight_fallbacks}/{r.n_value_weighted_legs}" if r.n_value_weighted_legs else "-"
    print(f"{r.pattern_id:38s} {r.sharpe_annualized:+7.3f} {dsr:>6s} {psr:>6s} "
          f"{r.n_formations:5d} {r.n_skipped_formations:4d} {r.n_trading_days:5d} "
          f"{r.total_cost_drag:7.4f} {r.total_financing_drag:7.4f} {fb:>6s}")
import numpy as np
sharpes = [r.sharpe_annualized for r in summary.results]
print("-" * 78)
print(f"mean sharpe {np.mean(sharpes):+.3f} | median {np.median(sharpes):+.3f} | "
      f"{sum(1 for s in sharpes if s > 0)}/{len(sharpes)} positive | "
      f"best DSR {max((r.deflated_sharpe.dsr or 0) for r in summary.results):.3f}")
print("=" * 78)
print(summary.text)
