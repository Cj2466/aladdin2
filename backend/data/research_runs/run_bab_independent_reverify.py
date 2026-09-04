"""One-off independent re-verification for the xc_btcbeta_l180_h180 forward
registration, run 2026-09-04 as part of wiring the registration's missing
_on_startup call into main.py's lifespan().

WHY THIS SCRIPT EXISTS. bab_forward_registration.py's registration decision
(2026-08-27) was never actually deployed -- confirmed independently in
commit 61bd307's price_store_pit_2026-09-04.json/.txt, which also measured
this spec's Sharpe/DSR as a side effect of proving the new price-store is
numerics-neutral. This script re-derives the same numbers from a SEPARATE,
freshly-run invocation of the family's own unmodified production entry
point (run_crypto_screening), independently of that committed report, so
the "re-derive rather than trust old notes" step in this task has a second,
independently-run source rather than one report re-read twice.

Window matches price_store_pit_2026-09-04's own choice (end=2026-08-31) so
the two are directly comparable.
"""

import json
from datetime import date

from app.services.research_lab.cross_sectional_crypto import run_crypto_screening

PATTERN_ID = "xc_btcbeta_l180_h180"
END = date(2026, 8, 31)


def main() -> None:
    summary = run_crypto_screening(end=END)
    match = [r for r in summary.results if r.pattern_id == PATTERN_ID]
    if not match:
        raise SystemExit(
            f"{PATTERN_ID} not found among {len(summary.results)} screened results -- "
            "family shape may have drifted since registration."
        )
    result = match[0]
    ds = result.deflated_sharpe
    exposure = summary.factor_exposures.get(PATTERN_ID)
    payload = {
        "pattern_id": PATTERN_ID,
        "n_trials": summary.n_trials,
        "sharpe_annualized": result.sharpe_annualized,
        "sharpe_net_annualized": ds.sharpe_net_annualized,
        "dsr": ds.dsr,
        "dsr_floor_met": ds.dsr_floor_met,
        "psr_vs_zero": ds.psr_vs_zero,
        "n_observations": ds.n_observations,
        "n_formations": result.n_formations,
        "n_skipped_formations": result.n_skipped_formations,
        "n_trading_days": result.n_trading_days,
        "avg_names_per_leg": result.avg_names_per_leg,
        "panel_start": str(summary.panel_start),
        "panel_end": str(summary.panel_end),
        "n_missing_calendar_days": summary.n_missing_calendar_days,
        "warnings": summary.warnings,
        "interpretation": ds.interpretation,
        "btc_beta": exposure.btc_beta if exposure else None,
        "basket_beta": exposure.basket_beta if exposure else None,
        "alpha_annualized": exposure.alpha_annualized if exposure else None,
        "alpha_t_stat": exposure.alpha_t_stat if exposure else None,
        "r_squared": exposure.r_squared if exposure else None,
        "factor_neutralized_sharpe": exposure.factor_neutralized_sharpe if exposure else None,
    }
    print(json.dumps(payload, indent=2))
    out_path = "data/research_runs/bab_independent_reverify_2026-09-04.json"
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nwritten to {out_path}")


if __name__ == "__main__":
    main()
