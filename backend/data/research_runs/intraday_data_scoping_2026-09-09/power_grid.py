"""Power grid for the intraday-data scoping memo (2026-09-09).

Uses app.services.research_lab.dsr_power as-is. No formula is retyped here.

UNIT CONTRACT (dsr_power module docstring): every Sharpe argument is
ANNUALIZED; `periods_per_year` is the number of PER-PERIOD returns the DSR
gate is computed on per year, and `n_observations` = years * periods_per_year.

INDEPENDENCE ASSUMPTION, STATED EXPLICITLY. The task asks for bets-per-year
to be used as `periods_per_year`. That is only correct if every bet is an
independently-observed return draw. It is NOT correct for a cross-sectional
book of K stocks traded on the same day: those K bets share a common daily
factor, so the strategy's P&L series still has 252 observations per year and
the extra breadth raises the achievable Sharpe (Grinold's IR = IC*sqrt(breadth))
rather than the observation count. Both readings are therefore computed:
  * `ppy` = the strategy P&L series frequency (252 = one daily return;
    504 = two non-overlapping intraday legs per day; etc.), and
  * an "effective independent bets" reading where ppy = bets/year, which is
    the OPTIMISTIC bound and is labelled as such in the memo.
Neither is a claim about any real mechanism; both are arithmetic.
"""

from __future__ import annotations

import itertools
import json

from app.services.research_lab.dsr_power import (
    min_detectable_sharpe,
    years_to_detect,
)

THRESHOLD = 0.95
POWER = 0.80

# Annualized true Sharpe values. 0.50 is the project's own reference micro-edge
# (criteria_fix_2026-09-09). 2.09 and 3.62 are conversions of published effect
# sizes, derived in the memo with the arithmetic shown there.
SHARPES = [0.30, 0.50, 1.00, 2.09, 3.62]

# periods_per_year values used in the memo, with what each stands for.
PPY = {
    252: "one daily P&L observation (daily close-to-close, status quo)",
    504: "two non-overlapping intraday legs per day",
    2_520: "10 non-overlapping intraday observations per day",
    25_200: "100 effective independent bets per day",
    504_000: "2000 stocks x 252 days, ALL treated as independent (upper bound)",
}

N_TRIALS = [12, 36]
SIGMA = [0.2, 0.5]

rows = []
for ppy, s, n, sig in itertools.product(PPY, SHARPES, N_TRIALS, SIGMA):
    yrs = years_to_detect(
        true_sharpe_annualized=s,
        threshold=THRESHOLD,
        n_trials=n,
        sigma_sr_annualized=sig,
        periods_per_year=float(ppy),
        power_target=POWER,
    )
    rows.append(
        {
            "periods_per_year": ppy,
            "meaning": PPY[ppy],
            "true_sharpe_annualized": s,
            "n_trials": n,
            "sigma_sr_annualized": sig,
            "years_to_detect_at_80pct_power": None if yrs is None else round(yrs, 2),
        }
    )

# Minimum detectable Sharpe at a fixed budget of calendar years.
mds_rows = []
for ppy, years, n, sig in itertools.product(PPY, [3.0, 5.0, 11.6], N_TRIALS, SIGMA):
    n_obs = max(3, round(years * ppy))
    mds = min_detectable_sharpe(
        threshold=THRESHOLD,
        n_observations=n_obs,
        n_trials=n,
        sigma_sr_annualized=sig,
        periods_per_year=float(ppy),
        power_target=POWER,
    )
    mds_rows.append(
        {
            "periods_per_year": ppy,
            "calendar_years": years,
            "n_observations": n_obs,
            "n_trials": n,
            "sigma_sr_annualized": sig,
            "min_detectable_sharpe_annualized": None if mds is None else round(mds, 4),
        }
    )

out = {
    "threshold": THRESHOLD,
    "power_target": POWER,
    "years_to_detect": rows,
    "min_detectable_sharpe": mds_rows,
}
print(json.dumps(out, indent=1))

# ---------------------------------------------------------------------------
# Companion tables printed as text (memo Section 3). Includes a reproduction
# check against the already-committed validate_dsr_power_output.txt.
# ---------------------------------------------------------------------------
print("\n== REPRODUCTION CHECK vs criteria_fix_2026-09-09/validate_dsr_power_output.txt ==")
print(
    "years_to_detect(S=0.50, N=12, sigma=0.19, ppy=252) =",
    round(
        years_to_detect(
            true_sharpe_annualized=0.5, threshold=0.95, n_trials=12,
            sigma_sr_annualized=0.19, periods_per_year=252.0,
        ),
        1,
    ),
    "(committed value: 183.3)",
)
print(
    "min_detectable_sharpe(n=2926, N=12, sigma=0.19, ppy=252) =",
    round(
        min_detectable_sharpe(
            threshold=0.95, n_observations=2926, n_trials=12,
            sigma_sr_annualized=0.19, periods_per_year=252.0,
        ),
        3,
    ),
    "(committed value: 1.047)",
)

print("\n== years to detect at 80% power, threshold 0.95, ppy=252 ==")
print(f"{'S_ann':>6} {'N12 s0.2':>9} {'N36 s0.2':>9} {'N12 s0.5':>9} {'N36 s0.5':>9}")
for s in [0.30, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.09, 2.50, 3.00, 3.62]:
    vals = [
        years_to_detect(
            true_sharpe_annualized=s, threshold=0.95, n_trials=n,
            sigma_sr_annualized=sg, periods_per_year=252.0,
        )
        for n, sg in [(12, 0.2), (36, 0.2), (12, 0.5), (36, 0.5)]
    ]
    print(f"{s:>6} " + " ".join(f"{('never' if v is None else f'{v:.2f}'):>9}" for v in vals))

print("\n== min detectable annualized Sharpe at 80% power, threshold 0.95, ppy=252 ==")
print(f"{'years':>6} {'N12 s0.2':>9} {'N36 s0.2':>9} {'N12 s0.5':>9} {'N36 s0.5':>9}")
for yrs in [1.0, 2.0, 3.0, 5.0, 11.6]:
    vals = [
        min_detectable_sharpe(
            threshold=0.95, n_observations=round(yrs * 252), n_trials=n,
            sigma_sr_annualized=sg, periods_per_year=252.0,
        )
        for n, sg in [(12, 0.2), (36, 0.2), (12, 0.5), (36, 0.5)]
    ]
    print(f"{yrs:>6} " + " ".join(f"{v:>9.3f}" for v in vals))
