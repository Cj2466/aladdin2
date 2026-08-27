"""Post-run reporting: prints the measured Phase C numbers needed for the
module docstring and commit message, straight from the saved summary and
frequency-comparison pickles — nothing hand-entered."""

import os
import pickle
import sys

import numpy as np

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a2520e5862565ddbf/backend")
SCRATCH = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(SCRATCH, "lowfreq_screening_summary.pkl"), "rb") as f:
    summary = pickle.load(f)
with open(os.path.join(SCRATCH, "freq_compare_results.pkl"), "rb") as f:
    freq = pickle.load(f)

print(f"n_trials={summary.n_trials}")
print(f"sigma_SR_annualized={summary.sigma_sr_annualized:.4f}")
print(f"SR0_annualized={summary.sr0_annualized:.4f}")
print(f"n_results={len(summary.results)}")

neg = sum(1 for r in summary.results if r.sharpe_annualized < 0)
print(f"negative-sharpe patterns: {neg}/{len(summary.results)}")

tpys = [r.trades_per_ticker_year for r in summary.results]
print(f"measured trades/ticker-yr across results: mean {np.mean(tpys):.1f}, median {np.median(tpys):.1f}, max {np.max(tpys):.1f}")

old_means = {pid: float(np.mean(v)) for pid, v in freq["old"].items()}
old_vals = np.array(list(old_means.values()))
print(f"old-212 family (same bars, sample): mean {old_vals.mean():.1f}, median {np.median(old_vals):.1f}, max {old_vals.max():.1f}")

best = summary.results[0]
d = best.deflated_sharpe
print("\nBEST PATTERN:")
print(f"  {best.pattern_id}: sharpe {best.sharpe_annualized:.3f}, n_days {best.n_trading_days}, n_trades {best.n_trades}, t/t-yr {best.trades_per_ticker_year:.1f}")
print(f"  hit {best.hit_rate}, PSR0 {d.psr_vs_zero}, DSR {d.dsr}, SR0 {d.expected_max_sharpe_noise_annualized}")

print("\nFULL TABLE (sorted by sharpe):")
for r in summary.results:
    d = r.deflated_sharpe
    dsr = f"{d.dsr:.3g}" if d.dsr is not None else "n/a"
    psr = f"{d.psr_vs_zero:.3f}" if d.psr_vs_zero is not None else "n/a"
    hit = f"{r.hit_rate:.3f}" if r.hit_rate is not None else "n/a"
    print(
        f"  {r.pattern_id:45s} SR {r.sharpe_annualized:7.2f}  DSR {dsr:>9s}  PSR0 {psr:>6s}  "
        f"trades {r.n_trades:6d}  t/t-yr {r.trades_per_ticker_year:5.1f}  hit {hit:>6s}  fired {r.n_tickers_fired:3d}/{r.n_tickers_in_basket}"
    )

import app.services.research_lab.low_frequency_patterns as lf

missing = {p.pattern_id for p in lf.LOW_FREQUENCY_PATTERN_FAMILY} - {r.pattern_id for r in summary.results}
print(f"\nno-result patterns (never fired / too few pooled days): {sorted(missing) if missing else 'none'}")

cleared = [r for r in summary.results if r.deflated_sharpe.dsr is not None and r.deflated_sharpe.dsr >= 0.5]
print(f"patterns with DSR >= 0.5: {[r.pattern_id for r in cleared] if cleared else 'none'}")
