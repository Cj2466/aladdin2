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
# CORRECTION 2026-09-11 (found by the Fable adversarial review, confirmed by the orchestrator
# against the extracted text): in the pdftotext layout each table's BODY precedes its CAPTION, so
# the block under the "Table 7" caption is Table 8 (long-spot-only). The constants first committed
# here were Table 8's. The unrestricted Table 7 per-year High-tier Sharpe ratios (2022, 2023) are:
TABLE_7_POST_BREAK_SR = {"BTC": (0.70, 1.32), "ETH": (1.29, 1.64), "BNB": (2.83, 2.96), "DOGE": (1.49, 0.85), "ADA": (2.33, 1.12)}
TABLE_7_ALL_SR = {"BTC": 1.80, "ETH": 2.55, "BNB": 4.84, "DOGE": 3.58, "ADA": 2.68}  # Table 7 "All" == Table 6 High tier
# Retained for the record -- Table 8 (long-spot-only), the values the first run used by mistake:
TABLE_8_LONG_SPOT_ONLY_POST_BREAK_SR = {"BTC": (0.51, 0.87), "ETH": (0.81, 1.16), "BNB": (0.76, 0.73), "DOGE": (1.03, 0.49), "ADA": (None, 0.88)}
TABLE_8_LONG_SPOT_ONLY_ALL_SR = {"BTC": 1.62, "ETH": 2.23, "BNB": 3.29, "DOGE": 2.52, "ADA": 2.11}
# Table 5 (as quoted by the adversarial review): mean cross-coin correlation of the deviation 0.718
TABLE_5_MEAN_DEVIATION_CORRELATION = 0.718
# Table 7 active% and open-to-close hours give trades per year = active% * 8760 / OtC:
TABLE_7_TRADES_PER_YEAR = {"BTC": {"2022": 9.21 / 100 * 8760 / 402.50, "2023": 7.68 / 100 * 8760 / 223.33},
                           "ETH": {"2022": 8.23 / 100 * 8760 / 102.14, "2023": 10.35 / 100 * 8760 / 180.40},
                           "BNB": {"2023": 18.93 / 100 * 8760 / 41.62}, "ADA": {"2023": 25.24 / 100 * 8760 / 236.89}}


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
            post8 = [x for x in TABLE_8_LONG_SPOT_ONLY_POST_BREAK_SR[coin] if x is not None]
            block[coin] = {
                "table6_full_claim": power(sr, years),
                "table7_all_2020_2024": power(TABLE_7_ALL_SR[coin], years),
                "table7_post_break_2022_2023_mean": power(sum(post) / len(post), years),
                "table8_long_spot_only_post_break_mean (first run's mislabeled values)": power(sum(post8) / len(post8), years),
            }
        pooled_sr = sum(sum(v) / 2 for v in TABLE_7_POST_BREAK_SR.values()) / 5 * math.sqrt(5 / (1 + 4 * TABLE_5_MEAN_DEVIATION_CORRELATION))
        block["POOLED_5_equal_weight_post_break"] = power(pooled_sr, years)
        out["windows"][label] = block
    out["trades_per_year_table7"] = TABLE_7_TRADES_PER_YEAR
    # the sourcing rule: the most conservative SOURCE-BASED claim must clear POWER_FLOOR
    oos = next(k for k in out["windows"] if k.startswith("out_of_sample"))
    oos_pooled_ok = out["windows"][oos]["POOLED_5_equal_weight_post_break"]["passes_floor"]
    oos_each_ok = all(out["windows"][oos][c]["table7_post_break_2022_2023_mean"]["passes_floor"] for c in TABLE_6_HIGH_TIER_SR)
    out["decision"] = "PROCEED" if (oos_pooled_ok and oos_each_ok) else "DECLINE_AT_SOURCING"
    out["decision_basis"] = (
        "CORRECTED 2026-09-11. The deciding window is the out-of-sample one (2024-03 -> 2026-09): the paper's "
        "sample is in-sample and can only be replicated. There, at the paper's own unrestricted post-2022 Sharpe "
        "(Table 7), only BNB clears POWER_FLOOR; BTC/ETH/DOGE/ADA do not, and the equal-weight 5-coin pool at "
        "Table 5's 0.718 correlation does not either. Independently, Table 7 implies 2-10 trades per year per "
        "coin (BNB ~40), far too few bets for this project's daily-Sharpe machinery to certify anything."
    )
    (HERE / "sourcing_power_perp_basis.json").write_text(json.dumps(out, indent=2))
    for w, block in out["windows"].items():
        print(w)
        for c, v in block.items():
            if c.startswith("POOLED"):
                print(f"  POOLED-5 post-break SR={v['claimed_sr']:.2f} -> power {v['power']:.3f}")
                continue
            print(f"  {c:5s} full {v['table6_full_claim']['power']:.3f} | all20-24 {v['table7_all_2020_2024']['power']:.3f} | post-break {v['table7_post_break_2022_2023_mean']['claimed_sr']:.2f} -> {v['table7_post_break_2022_2023_mean']['power']:.3f}")
    print("DECISION:", out["decision"])


if __name__ == "__main__":
    main()
