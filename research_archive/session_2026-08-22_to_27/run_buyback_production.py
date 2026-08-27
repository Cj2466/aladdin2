"""THE real production screening for the buyback / net-share-issuance family.

Live yfinance, real point-in-time S&P 500 universe, no cache, no fixtures.
"""
import json
import pickle
import sys
import time
import warnings
from dataclasses import asdict
from datetime import date

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")

from app.services.research_lab.cross_sectional_buyback import (  # noqa: E402
    BUYBACK_FAMILY,
    BUYBACK_FORMATION_START,
    run_buyback_screening,
)

OUT = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"

t0 = time.time()
summary = run_buyback_screening(start=BUYBACK_FORMATION_START, end=date(2026, 8, 27))
elapsed = time.time() - t0
with open(f"{OUT}/buyback_summary.pkl", "wb") as f:
    pickle.dump(summary, f)

print(f"\n{'=' * 100}")
print(f"BUYBACK / NET-SHARE-ISSUANCE PRODUCTION RUN — completed in {elapsed:.0f}s")
print(f"{'=' * 100}")
print(summary.disclosure)
print()
print(f"universe_size                      : {summary.universe_size}")
print(f"missing_price_data                 : {len(summary.missing_price_data)}")
print(f"tickers_without_share_history      : {len(summary.tickers_without_share_history)}")
print(f"panel                              : {summary.panel_start} .. {summary.panel_end}")
print(f"formation_start                    : {summary.formation_start}")
print(f"n_tickers_with_splits              : {summary.n_tickers_with_splits}")
print(f"n_split_adjusted_observations      : {summary.n_split_adjusted_observations}")
print(f"median_signal_endpoint_age_days    : {summary.median_signal_endpoint_age_days:.1f}")
print(f"uninformative_window_rate          : "
      f"{ {k: round(v, 4) for k, v in summary.uninformative_window_rate.items()} }")
print(f"warnings                           : {summary.warnings}")
print()

print("=" * 140)
print(f"ALL {len(summary.results)} REPLAYED SPECS OF THE PRE-DECLARED {summary.n_trials} "
      f"(sorted by raw Sharpe, every one reported — nothing cherry-picked)")
print("=" * 140)
header = (
    f"{'pattern_id':<28} {'Sharpe':>8} {'DSR':>8} {'floor':>6} {'PSR>0':>8} {'sigma_sr':>9} "
    f"{'E[maxSR]':>9} {'days':>6} {'form':>5} {'skip':>5} {'leg':>6} {'costdrag':>9} {'turn/f':>8}"
)
print(header)
print("-" * len(header))
for r in summary.results:
    d = r.deflated_sharpe
    dsr = "n/a" if d.dsr is None else f"{d.dsr:.4f}"
    sig = "n/a" if d.sigma_sr_annualized is None else f"{d.sigma_sr_annualized:.4f}"
    emax = "n/a" if d.expected_max_sharpe_noise_annualized is None else (
        f"{d.expected_max_sharpe_noise_annualized:.4f}"
    )
    psr = "n/a" if d.psr_vs_zero is None else f"{d.psr_vs_zero:.4f}"
    print(
        f"{r.pattern_id:<28} {r.sharpe_annualized:>8.4f} {dsr:>8} {str(d.dsr_floor_met):>6} "
        f"{psr:>8} {sig:>9} {emax:>9} {r.n_trading_days:>6d} {r.n_formations:>5d} "
        f"{r.n_skipped_formations:>5d} {r.avg_names_per_leg:>6.1f} {r.total_cost_drag:>9.5f} "
        f"{summary.turnover_per_formation.get(r.pattern_id, float('nan')):>8.3f}"
    )

print()
print("interpretations:")
for r in summary.results:
    print(f"  {r.pattern_id:<28} {r.deflated_sharpe.interpretation}")

replayed = {r.pattern_id for r in summary.results}
dropped = [s.pattern_id for s in BUYBACK_FAMILY if s.pattern_id not in replayed]
print()
print(f"specs that did not survive the data floors (still counted in n_trials={summary.n_trials}): "
      f"{dropped or 'none'}")
if summary.results:
    pos = [r for r in summary.results if r.sharpe_annualized > 0]
    dsr_pass = [r for r in summary.results if (r.deflated_sharpe.dsr or 0.0) > 0.5]
    print(f"positive raw Sharpe : {len(pos)} / {len(summary.results)} replayed "
          f"(of the pre-declared {summary.n_trials})")
    print(f"DSR > 0.5           : {len(dsr_pass)} / {len(summary.results)}")
    print(f"best raw Sharpe     : {summary.results[0].pattern_id} "
          f"{summary.results[0].sharpe_annualized:.4f}")
    best_dsr = max(summary.results, key=lambda r: (r.deflated_sharpe.dsr or -1.0))
    print(f"best DSR            : {best_dsr.pattern_id} {best_dsr.deflated_sharpe.dsr}")

payload = {
    "elapsed_s": elapsed,
    "n_trials": summary.n_trials,
    "universe_size": summary.universe_size,
    "n_missing_price": len(summary.missing_price_data),
    "n_without_shares": len(summary.tickers_without_share_history),
    "panel_start": str(summary.panel_start),
    "panel_end": str(summary.panel_end),
    "formation_start": str(summary.formation_start),
    "n_tickers_with_splits": summary.n_tickers_with_splits,
    "n_split_adjusted_observations": summary.n_split_adjusted_observations,
    "median_signal_endpoint_age_days": summary.median_signal_endpoint_age_days,
    "uninformative_window_rate": summary.uninformative_window_rate,
    "warnings": summary.warnings,
    "disclosure": summary.disclosure,
    "turnover_per_formation": summary.turnover_per_formation,
    "results": [
        {
            "pattern_id": r.pattern_id,
            "sharpe": r.sharpe_annualized,
            "deflated_sharpe": asdict(r.deflated_sharpe),
            "n_trading_days": r.n_trading_days,
            "n_formations": r.n_formations,
            "n_skipped": r.n_skipped_formations,
            "avg_names_per_leg": r.avg_names_per_leg,
            "total_cost_drag": r.total_cost_drag,
            "total_financing_drag": r.total_financing_drag,
        }
        for r in summary.results
    ],
    "dropped_specs": dropped,
}
with open(f"{OUT}/buyback_production_result.json", "w") as f:
    json.dump(payload, f, indent=2, default=str)
print(f"\nwrote {OUT}/buyback_production_result.json")
