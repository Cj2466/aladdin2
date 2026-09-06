"""Layer 4 cost scenarios for the recovered low-frequency pattern family.

A registration scorecard's layer_4_economics requires at least two cost
scenarios, each reporting the BEST SPEC's net Sharpe at that cost
(registration_scorecard.py's _parse_layer_4). This measures them.

Only the best spec is re-run, not the whole family: the field asks for
`best_spec_net_sharpe`, so this is 1 pattern x 284 tickers rather than 28 x
284, and it reuses the module's own run_patterns_for_ticker and
aggregate_ticker_outcomes so the pooling rule is not re-derived here.

THE SCENARIOS, and why each number rather than a round guess:

  2.00 bp/side   The CORRECTED EDGE frame's own measured median one-way
                 half-spread on this project's real S&P 500 panel
                 (data/research_runs/edge_cost_correction_2026-09-05.txt:
                 "corrected frame  2.00 bp median / 2.83 bp mean", 1,830,000
                 cells). Independently corroborated there against Hagstromer
                 (JFE 2021) Table 1, which measures the actual S&P 500 median
                 full effective spread at 2.53bp -- i.e. ~1.27bp per side.
                 This is the OPTIMISTIC-BUT-SOURCED end for a 284-name
                 large-cap universe like PHASE_B_UNIVERSE_15MIN.

  5.00 bp/side   INTRADAY_COST_BPS, the constant the family actually screened
                 at on 2026-08-26 and again today. Included so the scorecard's
                 headline number is one of the scenarios rather than a
                 separate unexplained figure.

 10.00 bp/side   A 2x stress on the as-run constant, i.e. ~4-8x the corrected
                 large-cap reality. Not a prediction -- a floor-test of
                 whether the verdict is robust to the cost model being badly
                 wrong in the direction that would matter.

WHY THE AS-RUN 5bp IS ALREADY CONSERVATIVE, stated because it is the opposite
of the usual failure mode and should not be mistaken for one: at 5bp/side the
family charges a 10bp round trip against a corrected large-cap reality of
roughly 2.5-4bp. The 2026-09-05 EDGE correction (997b5fe) did NOT touch this
constant, and did not need to -- it fixed the cross-sectional EDGE estimator,
a different cost path. The one thing the flat constant genuinely omits is
BORROW on short legs, which borrow_cost.py prices at
GENERAL_COLLATERAL_BPS_PER_YEAR = 34.0 bp/year for names like these. Its
magnitude is computed and printed below rather than asserted.

Run from backend/ AFTER the main screen, with
    python3 data/research_runs/run_low_frequency_cost_scenarios.py
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
import time
from multiprocessing import Pool
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND})."
    )

from app.config import _main_checkout_backend_dir
from app.services.research_lab.borrow_cost import GENERAL_COLLATERAL_BPS_PER_YEAR
from app.services.research_lab.intraday_patterns import INTRADAY_COST_BPS
from app.services.research_lab.low_frequency_patterns import (
    EVENT_HOLD_DAYS,
    EXTREME_MOVE_HOLD_DAYS,
    HIGH252_HOLD_DAYS,
    LOW_FREQUENCY_PATTERN_FAMILY,
    TOM_EXIT_ORDINALS,
    aggregate_ticker_outcomes,
)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

CACHE = _main_checkout_backend_dir(_BACKEND) / "data" / "intraday_bars_15min"
MAIN_JSON = _BACKEND / "data" / "research_runs" / "low_frequency_patterns_recovered_2026-09-06.json"
OUT_JSON = _BACKEND / "data" / "research_runs" / "low_frequency_cost_scenarios_2026-09-06.json"

SCENARIOS = [
    ("corrected EDGE large-cap (2bp/side)", 2.00, "edge_cost_correction_2026-09-05.txt, corrected frame median one-way half-spread; Hagstromer JFE 2021 Table 1"),
    ("as run (5bp/side, INTRADAY_COST_BPS)", INTRADAY_COST_BPS, "intraday_patterns.INTRADAY_COST_BPS, the constant this family screened at"),
    ("2x stress (10bp/side)", 10.00, "stress test, not a prediction: 2x the as-run constant"),
]

N_WORKERS = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
logger = logging.getLogger("lowfreq_cost_scenarios")

_PATTERN_ID: str = ""
_COST: float = 0.0


def _init(pattern_id: str, cost: float) -> None:
    global _PATTERN_ID, _COST
    _PATTERN_ID, _COST = pattern_id, cost


def _run_ticker(ticker: str):
    import app.services.research_lab.low_frequency_patterns as lf

    spec = next(p for p in lf.LOW_FREQUENCY_PATTERN_FAMILY if p.pattern_id == _PATTERN_ID)
    with open(CACHE / f"{ticker}_15Min.pkl", "rb") as handle:
        bars = pickle.load(handle)
    return ticker, lf.run_patterns_for_ticker(bars, [spec], cost_bps=_COST)


def main() -> None:
    if not MAIN_JSON.is_file():
        raise SystemExit(f"REFUSING TO RUN: {MAIN_JSON} not found. Run the main screen first.")
    main_result = json.loads(MAIN_JSON.read_text())
    results = main_result["results"]
    if not results:
        raise SystemExit("REFUSING TO RUN: the main screen recorded no reportable results.")
    best = max(results, key=lambda r: r["sharpe_annualized"])
    pattern_id = best["pattern_id"]
    logger.info("best spec from the main screen: %s (sharpe %.4f)", pattern_id, best["sharpe_annualized"])

    spec = next(p for p in LOW_FREQUENCY_PATTERN_FAMILY if p.pattern_id == pattern_id)
    tickers = sorted(p.name.replace("_15Min.pkl", "") for p in CACHE.glob("*_15Min.pkl"))

    scenarios_out = []
    for name, cost, source in SCENARIOS:
        started = time.time()
        outcomes_by_ticker = {}
        with Pool(N_WORKERS, initializer=_init, initargs=(pattern_id, cost)) as pool:
            for ticker, outcomes in pool.imap_unordered(_run_ticker, tickers):
                outcomes_by_ticker[ticker] = outcomes
        summary = aggregate_ticker_outcomes(outcomes_by_ticker, [spec])
        if not summary.results:
            raise SystemExit(f"scenario {name!r} produced no reportable result")
        row = summary.results[0]
        logger.info(
            "%-40s one_way_bps=%5.2f  net_sharpe=%8.4f  trades=%d  (%.0fs)",
            name, cost, row.sharpe_annualized, row.n_trades, time.time() - started,
        )
        scenarios_out.append(
            {
                "name": name,
                "one_way_bps": cost,
                "source": source,
                "best_spec_net_sharpe": row.sharpe_annualized,
                "n_trades": row.n_trades,
                "trades_per_ticker_year": row.trades_per_ticker_year,
            }
        )

    # ----- the borrow charge the flat constant omits, MEASURED -------------
    # A short leg pays borrow only while held. Time-in-market comes from this
    # family's own measured trade frequency and hold lengths, not an
    # assumption: round trips/ticker-year x mean hold days / trading days.
    as_run = next(s for s in scenarios_out if s["one_way_bps"] == INTRADAY_COST_BPS)
    trades_per_year = as_run["trades_per_ticker_year"]
    # Hold length comes from the family's OWN declared constants, not a
    # hand-typed table, so it cannot drift away from the design it describes.
    hold_days_by_family = {
        "extreme_move": sum(EXTREME_MOVE_HOLD_DAYS) / len(EXTREME_MOVE_HOLD_DAYS),
        "gap": 1.0,  # entered at the first bar's close, exited the same day's close
        "turn_of_month": 1.0 + sum(TOM_EXIT_ORDINALS.values()) / len(TOM_EXIT_ORDINALS),
        "preholiday": 1.0,  # the single pre-holiday session
        "high252_breakout": float(HIGH252_HOLD_DAYS),
        "opex_week": 5.0,  # entered the prior close, exited expiration Friday
        "bollinger3s_daily": float(EVENT_HOLD_DAYS),
        "rsi_daily_extreme": float(EVENT_HOLD_DAYS),
        "volume_shock_5x": float(EVENT_HOLD_DAYS),
    }
    if spec.family not in hold_days_by_family:
        raise SystemExit(f"no declared hold length for family {spec.family!r}; refusing to guess one")
    mean_hold_days = hold_days_by_family[spec.family]
    fraction_of_year_held = trades_per_year * mean_hold_days / TRADING_DAYS_PER_YEAR
    borrow_drag_bps_per_year = GENERAL_COLLATERAL_BPS_PER_YEAR * fraction_of_year_held
    logger.info(
        "omitted borrow charge, if this spec were held SHORT 100%% of its time in market: "
        "%.2f trades/ticker-yr x %.1f hold days / %d = %.4f of the year held; "
        "%.1f bp/yr general collateral -> %.3f bp/year drag",
        trades_per_year, mean_hold_days, TRADING_DAYS_PER_YEAR, fraction_of_year_held,
        GENERAL_COLLATERAL_BPS_PER_YEAR, borrow_drag_bps_per_year,
    )

    OUT_JSON.write_text(
        json.dumps(
            {
                "best_spec_pattern_id": pattern_id,
                "best_spec_family": spec.family,
                "scenarios": scenarios_out,
                "omitted_borrow_charge": {
                    "general_collateral_bps_per_year": GENERAL_COLLATERAL_BPS_PER_YEAR,
                    "trades_per_ticker_year": trades_per_year,
                    "mean_hold_days": mean_hold_days,
                    "fraction_of_year_held": fraction_of_year_held,
                    "drag_bps_per_year_if_always_short": borrow_drag_bps_per_year,
                    "note": (
                        "Upper bound: assumes the leg is short 100% of its time in market. "
                        "Charged nowhere in this family, and its magnitude is why that is "
                        "disclosed rather than fixed -- adding it would only lower the Sharpe, "
                        "hardening an already-negative verdict."
                    ),
                },
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    logger.info("wrote %s", OUT_JSON)


if __name__ == "__main__":
    main()
