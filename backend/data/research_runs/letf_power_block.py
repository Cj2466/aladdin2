"""PREREGISTRATION section 4.3 -- the power block for letf_rebalancing_eod.

Run BEFORE run_letf_rebalancing_eod.py and committed before it. It builds the
panel and reads ONLY the sigma of y and the |r_open->15:30| distribution off it;
no position, no strategy return and no Sharpe of any spec is computed, and none
is reachable from anything this file imports.
"""

from __future__ import annotations

import json
import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import _main_checkout_backend_dir
from app.services.research_lab.dsr_power import POWER_FLOOR, dsr_power_report
from app.services.research_lab.letf_rebalancing_eod import (
    IVANOV_LENKEY_OFFSET_FRACTION,
    PRE_REGISTERED_N_LOCAL,
    PRIMARY_WINDOW,
    SCREENING_FLOOR,
    TUZUN_LARGE_CAP_BP_PER_1PCT,
    UNDERLYINGS,
    VALIDATED_EDGE_BAR,
    build_panel,
    claimed_sharpe,
    policy_d_denominators,
    power_inputs,
)
from data.research_runs.fetch_letf_aum import (
    AUM_COL,
    DATE_COL,
    TARGET_TICKERS,
    TICKER_COL,
    load_target_frame,
)

OUT_DIR = BACKEND / "data" / "research_runs" / "letf_rebalancing_2026-09-11"
MAIN_BACKEND = _main_checkout_backend_dir(BACKEND)
BARS_DIR = MAIN_BACKEND / "data" / "letf_1min_bars"
AUM_SNAPSHOT = MAIN_BACKEND / "data" / "letf_aum" / "historical_nav_2026-09-10.csv"


def load_bars() -> dict[str, pd.DataFrame]:
    out = {}
    for ticker in UNDERLYINGS:
        path = BARS_DIR / f"{ticker}_1Min.pkl"
        if not path.is_file():
            raise SystemExit(f"{path} missing -- run data/research_runs/fetch_letf_1min_bars.py")
        with path.open("rb") as fh:
            out[ticker] = pickle.load(fh)
    return out


def load_aum() -> pd.DataFrame:
    frame = load_target_frame(AUM_SNAPSHOT)
    return frame.rename(columns={AUM_COL: "aum"})[[DATE_COL, TICKER_COL, "aum"]]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel, audit = build_panel(load_bars(), load_aum(), TARGET_TICKERS)
    inputs = power_inputs(panel, PRIMARY_WINDOW)
    denominators = policy_d_denominators(PRE_REGISTERED_N_LOCAL)

    arms = {}
    for name, fraction in (("full_tuzun", 1.0), ("half_tuzun", IVANOV_LENKEY_OFFSET_FRACTION)):
        sharpe = claimed_sharpe(inputs, fraction=fraction)
        arms[name] = {"fraction_of_tuzun": fraction, "claimed_net_sharpe_annualized": sharpe}
        for label, sigma_sr in (
            ("declared", inputs.sigma_sr_annualized),
            ("zero", 0.0),
            ("double", inputs.sigma_sr_annualized * 2.0),
        ):
            for bar in (VALIDATED_EDGE_BAR, SCREENING_FLOOR):
                report = dsr_power_report(
                    claimed_sharpe_annualized=sharpe,
                    threshold=bar,
                    n_observations=inputs.n_observations,
                    n_trials=PRE_REGISTERED_N_LOCAL,
                    sigma_sr_annualized=sigma_sr,
                    periods_per_year=inputs.periods_per_year,
                )
                arms[name][f"sigma_sr_{label}__bar_{bar:.2f}"] = {
                    "sigma_sr_annualized": sigma_sr,
                    "required_observed_sharpe": report.required_observed_sharpe,
                    "power_at_claimed_sharpe": report.power_at_claimed_sharpe,
                    "min_detectable_sharpe": report.min_detectable_sharpe,
                    "years_to_detect_claimed": report.years_to_detect_claimed,
                    "underpowered": report.underpowered,
                }

    decisive = arms["half_tuzun"][f"sigma_sr_declared__bar_{VALIDATED_EDGE_BAR:.2f}"]
    declared_underpowered = decisive["power_at_claimed_sharpe"] < POWER_FLOOR

    payload = {
        "written_utc": datetime.now(UTC).isoformat(),
        "family_key": "letf_rebalancing_eod",
        "authority": "PREREGISTRATION.md section 4.3; sigma_SR per ADDENDUM_01 section 4",
        "computed_from": "the sigma of y and the |r_open->15:30| distribution ONLY -- no strategy return, position or Sharpe was computed to produce this file",
        "panel": {
            "n_sessions": inputs.n_observations,
            "first_session": str(panel["date"].min().date()),
            "last_session": str(panel["date"].max().date()),
            "periods_per_year_measured": inputs.periods_per_year,
            "n_rows": len(panel),
            "underlyings": list(UNDERLYINGS),
            "per_ticker_calendar_sessions": audit.per_ticker_sessions,
            "per_ticker_usable_sessions": audit.per_ticker_usable,
            "dropped_not_common_to_all": len(audit.dropped_not_common_to_all),
            "dropped_missing_window_bar": {
                t: len(v) for t, v in audit.dropped_missing_window_bar.items()
            },
        },
        "inputs": {
            "sigma_y_daily": inputs.sigma_y,
            "mean_abs_r": inputs.mean_abs_r,
            "median_abs_r": inputs.median_abs_r,
            "p90_abs_r": inputs.p90_abs_r,
            "tuzun_bp_per_1pct": TUZUN_LARGE_CAP_BP_PER_1PCT,
            "expected_gross_daily_return_full": inputs.expected_gross_daily_return_full,
            "expected_gross_daily_return_half": inputs.expected_gross_daily_return_half,
            "round_trip_cost": inputs.round_trip_cost,
            "sigma_sr_annualized_declared": inputs.sigma_sr_annualized,
        },
        "n_local": PRE_REGISTERED_N_LOCAL,
        "dsr_ladder": denominators,
        "power_floor": POWER_FLOOR,
        "arms": arms,
        "PRE_REGISTERED_DECISION": {
            "rule": "PREREGISTRATION section 4.3: the family is declared underpowered for the claim IN ADVANCE if the 50%-of-Tuzun arm's power to clear 0.95 at n_local is < 0.80.",
            "half_tuzun_power_at_0.95_n_local": decisive["power_at_claimed_sharpe"],
            "declared_underpowered_in_advance": declared_underpowered,
        },
    }
    (OUT_DIR / "power_block.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload["PRE_REGISTERED_DECISION"], indent=2))
    print(json.dumps(payload["inputs"], indent=2))
    print(json.dumps(payload["panel"], indent=2, default=str))
    for name, arm in arms.items():
        print(name, "claimed net Sharpe", arm["claimed_net_sharpe_annualized"])
        for key, value in arm.items():
            if key.startswith("sigma_sr_"):
                print(" ", key, value)
    print(f"wrote {OUT_DIR / 'power_block.json'}")


if __name__ == "__main__":
    main()
