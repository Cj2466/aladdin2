"""THE REAL production screening run: 28 pre-declared crypto specs against
live yfinance data."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_897780eb-d4b-1/backend")

import pandas as pd

from app.services.research_lab.cross_sectional_crypto import run_crypto_screening

pd.set_option("display.width", 250)

summary = run_crypto_screening(end=date(2026, 8, 27))

print("=" * 100)
print(summary.text)
print("=" * 100)
print()
print(f"warnings: {summary.warnings}")
print(f"panel: {summary.n_panel_rows} rows {summary.panel_start}..{summary.panel_end}, "
      f"missing calendar days={summary.n_missing_calendar_days}")
print(f"candidates={summary.candidate_universe_size}  missing_price_data={summary.missing_price_data}")
print(f"eligible over window: min={summary.min_eligible} median={summary.median_eligible} max={summary.max_eligible}")
print(f"effective breadth: {summary.effective_breadth:.3f}")
print(f"dead coins actually ranked: {summary.dead_coins_ranked}")
print()
print("MECHANISM CORRELATIONS (blended streams):")
for (a, b), v in sorted(summary.mechanism_correlations.items()):
    print(f"   {a:24s} vs {b:24s}  {v:+.3f}")
print()
print(f"ALL {len(summary.results)} SPEC RESULTS (of {summary.n_trials} declared), sorted by Sharpe:")
rows = []
for r in summary.results:
    d = r.deflated_sharpe
    e = summary.factor_exposures.get(r.pattern_id)
    rows.append({
        "pattern_id": r.pattern_id,
        "n_form": r.n_formations,
        "n_skip": r.n_skipped_formations,
        "avg_leg": round(r.avg_names_per_leg, 1),
        "n_days": r.n_trading_days,
        "sharpe": round(r.sharpe_annualized, 3),
        "psr": None if d.psr_vs_zero is None else round(d.psr_vs_zero, 3),
        "dsr": None if d.dsr is None else round(d.dsr, 3),
        "sr0": None if d.expected_max_sharpe_noise_annualized is None else round(d.expected_max_sharpe_noise_annualized, 3),
        "cost": round(r.total_cost_drag, 4),
        "fin": round(r.total_financing_drag, 4),
        "btc_b": None if e is None else round(e.btc_beta, 3),
        "bskt_b": None if e is None else round(e.basket_beta, 3),
        "alpha/y": None if e is None else round(e.alpha_annualized, 4),
        "alpha_t": None if e is None else round(e.alpha_t_stat, 2),
        "hedged_sh": None if e is None else round(e.factor_neutralized_sharpe, 3),
    })
df = pd.DataFrame(rows)
print(df.to_string(index=False))
print()
print("n_trials used for DSR:", summary.n_trials)
if summary.results:
    d0 = summary.results[0].deflated_sharpe
    print("sigma_sr (annualized, from the 28 siblings):", d0.sigma_sr_annualized)
    print("best DSR in family:", max((r.deflated_sharpe.dsr or float('-inf')) for r in summary.results))
    print("count DSR > 0.5:", sum(1 for r in summary.results if (r.deflated_sharpe.dsr or 0) > 0.5))
    print("count Sharpe > 0:", sum(1 for r in summary.results if r.sharpe_annualized > 0))
