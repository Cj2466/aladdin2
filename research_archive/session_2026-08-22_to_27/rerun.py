import json, sys
from datetime import date
import numpy as np, pandas as pd
from app.services.research_lab.cross_sectional_crypto import run_crypto_screening, CRYPTO_N_TRIALS

s = run_crypto_screening(end=date(2026, 8, 25))
print("n_trials         =", s.n_trials, "| CRYPTO_N_TRIALS =", CRYPTO_N_TRIALS)
print("periods_per_year =", s.periods_per_year)
print("panel", s.panel_start, "->", s.panel_end, "rows", s.n_panel_rows,
      "missing_cal_days", s.n_missing_calendar_days)
print("eligible min/med/max", s.min_eligible, s.median_eligible, s.max_eligible)
print("dead_coins_ranked", getattr(s, "dead_coins_ranked", None))
print("effective_breadth", s.effective_breadth)
print("N RESULTS =", len(s.results))
rows = []
for r in sorted(s.results, key=lambda r: -(r.sharpe_annualized or -9)):
    e = s.factor_exposures.get(r.pattern_id)
    d = r.deflated_sharpe
    rows.append(dict(pid=r.pattern_id, sharpe=r.sharpe_annualized, dsr=d.dsr,
        sr0=d.expected_max_sharpe_noise_annualized, sigma=d.sigma_sr_annualized,

        btc_b=(e.btc_beta if e else None), bask_b=(e.basket_beta if e else None),
        alpha_t=(e.alpha_t_stat if e else None), r2=(e.r_squared if e else None),
        hedged=(e.factor_neutralized_sharpe if e else None)))
for r in rows:
    print(f"{r['pid']:34s} SR={r['sharpe']:+.4f} DSR={str(r['dsr'])[:6]:>6s} "
          f"btcB={r['btc_b']:+.3f} bskB={r['bask_b']:+.3f} at={r['alpha_t']:+.2f} "
          f"R2={r['r2']:.3f} hedged={r['hedged']:+.4f} ")
print("MECH CORR:", {f"{a}|{b}": round(v,4) for (a,b),v in s.mechanism_correlations.items()})
pos = [r for r in rows if r['sharpe'] > 0]
print("N positive:", len(pos), "of", len(rows))
print("best SR", max(r['sharpe'] for r in rows), "SR0", rows[0]['sr0'], "sigma", rows[0]['sigma'])
print("max DSR", max((r['dsr'] or 0) for r in rows))
json.dump(rows, open(sys.argv[1],"w"), indent=1, default=str)
