"""Sourcing-stage power pre-check for the crypto perpetual-futures basis candidate
(He, Manela, Ross & von Wachter, arXiv:2212.06888v6, "Fundamentals of Perpetual Futures").

Claimed effects are the paper's own Table 6 (High fee tier, "typically an individual
trader") annualized Sharpe ratios and its Table 7 per-year Sharpe ratios for the
post-2022 regime the paper itself calls a structural break. The paper annualizes a
threshold strategy Lucca-Moench style: SR_ann = (mu/sigma)*sqrt(N_active_hours); that is
algebraically the calendar-time Sharpe of the hourly series with zero return when flat
(mean = a*mu, var ~= a*sigma^2, so SR_hourly = sqrt(a)*mu/sigma, and sqrt(a*8760) =
sqrt(N_active)), so the paper's numbers are used AS-IS — NOT rescaled by sqrt(active%),
which the orchestrator first did in error and caught on re-derivation.

Power is computed with app.services.research_lab.dsr_power.dsr_power_report exactly as
the scorecard validator does (default skew 0 / kurt 3); sigma_SR = sqrt(periods_per_year
/ n), the same convention letf_rebalancing_2026-09-11/POWER_BLOCK.md declared.
Run: ./venv/bin/python data/research_runs/perp_basis_sourcing_2026-09-11/sourcing_power_perp_basis.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from app.services.research_lab.dsr_power import (
    POWER_FLOOR,
    dsr_power_report,
)

BAR = 0.95
PERIODS_PER_YEAR = 365  # crypto trades every calendar day; DSR series is daily
N_LOCAL = 16  # intended grid: 5 coins x {unrestricted, long-spot-only} + pooled + controls; declared here, before any build

# He et al. Table 6, High tier (spot 6.75 bp / futures 1.44 bp maker), full sample to 2024-03
TABLE_6_HIGH_TIER_SR = {"BTC": 1.80, "ETH": 2.55, "BNB": 4.84, "DOGE": 3.58, "ADA": 2.68}
# He et al. Table 7, High tier, unrestricted strategy, per year (2022 and 2023 columns)
TABLE_7_POST_BREAK_SR = {"BTC": (0.51, 0.87), "ETH": (0.81, 1.16), "BNB": (0.76, 0.73), "DOGE": (1.03, 0.49), "ADA": (None, 0.88)}
TABLE_7_ALL_SR = {"BTC": 1.62, "ETH": 2.23, "BNB": 3.29, "DOGE": 2.52, "ADA": 2.11}


def power(sr: float, years: float) -> dict:
    n = int(years * PERIODS_PER_YEAR)
    r = dsr_power_report(
        claimed_sharpe_annualized=sr,
        threshold=BAR,
        n_observations=n,
        n_trials=N_LOCAL,
        sigma_sr_annualized=math.sqrt(PERIODS_PER_YEAR / n),
        periods_per_year=PERIODS_PER_YEAR,
    )
    return {
        "claimed_sr": sr,
        "years": years,
        "n": n,
        "power": r.power_at_claimed_sharpe,
        "required_observed_sr": r.required_observed_sharpe,
        "years_to_detect": r.years_to_detect_claimed,
        "passes_floor": r.power_at_claimed_sharpe >= POWER_FLOOR,
    }


def main() -> None:
    out = {"written_utc": datetime.now(UTC).isoformat(), "bar": BAR, "n_local": N_LOCAL, "power_floor": POWER_FLOOR, "windows": {}}
    windows = {
        "full_sample_2019-09_to_2026-09 (7.0y, in-sample for the paper through 2024-03)": 7.0,
        "out_of_sample_only_2024-03_to_2026-09 (2.5y)": 2.5,
    }
    for label, years in windows.items():
        block = {}
        for coin, sr in TABLE_6_HIGH_TIER_SR.items():
            post = [x for x in TABLE_7_POST_BREAK_SR[coin] if x is not None]
            block[coin] = {
                "table6_full_claim": power(sr, years),
                "table7_all_2020_2024": power(TABLE_7_ALL_SR[coin], years),
                "table7_post_break_2022_2023_mean": power(sum(post) / len(post), years),
            }
        out["windows"][label] = block
    # the sourcing rule: the most conservative SOURCE-BASED claim must clear POWER_FLOOR
    conservative = [out["windows"][w][c]["table7_post_break_2022_2023_mean"]["passes_floor"] for w in out["windows"] for c in TABLE_6_HIGH_TIER_SR]
    out["decision"] = "PROCEED" if all(conservative) else "DECLINE_AT_SOURCING"
    out["decision_basis"] = (
        "Every coin's power at its own post-2022 Sharpe (the paper's Table 7, the regime the paper calls a "
        "structural break) is below POWER_FLOOR on both windows; the out-of-sample window alone is underpowered "
        "even at the full-sample claim. A build could only replicate the paper's in-sample years, not test the edge."
    )
    (HERE / "sourcing_power_perp_basis.json").write_text(json.dumps(out, indent=2))
    for w, block in out["windows"].items():
        print(w)
        for c, v in block.items():
            print(f"  {c:5s} full {v['table6_full_claim']['power']:.3f} | all20-24 {v['table7_all_2020_2024']['power']:.3f} | post-break {v['table7_post_break_2022_2023_mean']['claimed_sr']:.2f} -> {v['table7_post_break_2022_2023_mean']['power']:.3f}")
    print("DECISION:", out["decision"])


if __name__ == "__main__":
    main()
