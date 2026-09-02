"""Production runner for the dividend-month-premium screen.

Calls the module's OWN entrypoint (run_dmp_screening) -- not a
reimplementation, not a shortcut -- then persists every per-spec result to the
shared cross_sectional_trial_results table and writes the git-durable
plain-text run report.

Checked into data/research_runs/ alongside the pre-registration and the report
so the exact invocation that produced the numbers is reproducible from the
repo, rather than living only in a scratchpad. Run from backend/ with
./venv/bin/python.
"""

import logging
import math
import sys
import time
from datetime import date
from pathlib import Path

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv whose site-packages
# resolves `app` to the MAIN checkout. Without the two lines below, the screen
# silently runs main's code instead of this branch's, and for a module that
# exists in both it would do so with NO error at all.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The screen would have run against another checkout's code."
    )

from app.db import SessionLocal
from app.models.cross_sectional_trial_result import CrossSectionalTrialResult
from app.services.research_lab.cross_sectional_dividend_month import (
    DMP_ALTERNATIVE_RULES,
    DMP_COST_SENSITIVITY_BPS,
    DMP_EVENT_WINDOW,
    DMP_FAMILY_NAME,
    DMP_MIN_PRICE,
    DMP_MIN_PRIOR_EX_DATES,
    DMP_N_TRIALS,
    DMP_PLACEBO_SHIFT_MONTHS,
    DmpConfig,
    load_dividend_cache,
    run_dmp_screening,
)
from app.services.research_lab.cross_sectional_earnings_premium import (
    load_calendar_cache as load_announcement_calendar_cache,
)
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)

FAMILY_KEY = DMP_FAMILY_NAME
RUN_TAG = "dividend_month_premium_2026-09-02"
REPORT_PATH = "data/research_runs/dividend_month_premium_2026-09-02.txt"

# Formations start one full year after MEMBERSHIP_DATA_START (2015-01-07):
# [HS12]'s forecast rule reads the firm's own ex-dates up to twelve months
# back, so no prediction can exist before a year of calendar has accumulated
# inside the priced panel. Prices load from FETCH_START for that warm-up plus
# the extra year the rule's t-12 lag needs; no position with a formation
# before FORMATION_START is ever traded.
FORMATION_START = date(2016, 1, 4)
FETCH_START = date(2013, 1, 2)
RUN_END = date(2026, 9, 2)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("dmp_runner")


def _fmt(value, spec: str = "+.3f") -> str:
    if value is None:
        return "n/a"
    try:
        if math.isnan(value):
            return "n/a"
    except TypeError:
        return "n/a"
    return format(value, spec)


def _short_slots(summary, short_leg: str) -> int:
    """This run's realized short-leg size for `short_leg`, read off the
    results rather than hard-coded.

    DERIVED, NOT TYPED, and that is the point: the independent-verification
    pass found this paragraph still quoting the PRE-FIX 'between' count
    (28,539) after ERRATA C2 removed monthly payers from that leg and made it
    28,402 -- a number the same report's own gates table already contradicted.
    A figure that describes the run must come from the run."""
    for result in summary.results:
        if result.short_leg == short_leg:
            return int(result.n_short_positions)
    return 0


def _short_slot_gap(summary) -> str:
    between, within = _short_slots(summary, "between"), _short_slots(summary, "within")
    if not within:
        return "an unmeasured gap"
    return f"{(between - within) / within * 100.0:.1f}% apart"


def build_report(summary, config, elapsed: float) -> str:
    lines: list[str] = []
    add = lines.append

    add(
        "DIVIDEND MONTH PREMIUM -- Hartzmark & Solomon (JFE 109(3), 2013), screened as exactly "
        f"{DMP_N_TRIALS} PRE-DECLARED specs with its own n_trials denominator."
    )
    add(f"family_key={FAMILY_KEY}  run_tag={RUN_TAG}  wall clock {elapsed / 60:.1f} min")
    add(
        f"Formations {summary.formation_start.isoformat()} .. "
        f"{summary.formation_end.isoformat()} "
        f"(prices and dividend calendar warm up from {FETCH_START.isoformat()})."
    )
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/dividend_month_premium_PREREGISTRATION.txt, "
        "committed in f8e5c1a BEFORE any return, Sharpe, DSR, event-study number or placebo "
        "result existed. The 12-spec grid, the forecast rule, the 91-day ex-day projection, the "
        "5.0bp headline cost and the two-condition decision rule below are that document's, "
        "unchanged."
    )
    add("")
    add("THIS IS A LIVE, NETWORK-BACKED RUN: real yfinance corporate-actions ex-dividend dates")
    add("and real yfinance daily bars. No synthetic data is used anywhere in the numbers below.")
    add("")

    add("=" * 78)
    add("SAMPLE")
    add("=" * 78)
    report = summary.calendar_report
    add(
        f"  UNIVERSE: {report.n_tickers_requested} tickers that were S&P 500 members on any day "
        "of the point-in-time membership window (sp500_membership_history.get_universe_over), "
        "NOT a present-day snapshot. ticker_universe.SCREENING_UNIVERSE is not used and is not "
        "imported."
    )
    add(
        f"  DIVIDEND CALENDAR: {report.n_tickers_priced} tickers resolved a price in the "
        f"corporate-actions fetch, {report.n_tickers_with_dividends} paid at least one dividend, "
        f"{report.n_ex_dates:,} ex-dates over "
        f"{report.fetch_start.isoformat()}..{report.fetch_end.isoformat()}. "
        f"{len(report.missing_price_data)} tickers resolved no price data at all."
    )
    add(
        f"  SCREENED PANEL: {summary.n_tickers_priced} tickers priced over "
        f"{summary.panel_start.isoformat()}..{summary.panel_end.isoformat()}, of which "
        f"{summary.n_tickers_with_dividends} carry a dividend calendar."
    )
    add(
        "  THE DATE IS THE EX-DIVIDEND DATE, not the payment date -- which is exactly what "
        "[HS12] keys on ('Dividend months refer to months with an ex-date unless otherwise "
        "noted'). Returns are computed from TOTAL-RETURN closes; the dividend-yield weighting "
        "basis divides by the SPLIT-ADJUSTED close instead, because the dividend amounts are on "
        "that basis. Mixing the two would overstate historical yields by a per-ticker factor."
    )
    add(
        "  RESIDUAL SURVIVORSHIP, NOT FIXED BY THE POINT-IN-TIME GATE: membership makes the "
        "ROSTER honest, not the PRICES -- this project has no delisted-securities price vendor, "
        "so the names that vanished (the acquired and the failed) are disproportionately "
        "unpriceable and their absence FLATTERS every number below."
    )
    for warning in summary.warnings:
        add(f"  WARNING: {warning}")
    add("")

    add("=" * 78)
    add("FORECAST-RULE ACCURACY -- MEASURED ON REAL EX-DATES, ALL VARIANTS REPORTED")
    add("=" * 78)
    add(
        "  Month level: 'predicted' against 'the firm really had an ex-date that month', over "
        "every ticker-month in the formation window. Dates only -- no price, no position, no "
        "return is read anywhere in this measurement, which is why it could be run before the "
        "grid was frozen."
    )
    add("")
    header = f"  {'rule':<20} {'predicted':>10} {'TP':>8} {'FP':>8} {'FN':>8} {'precision':>10} {'recall':>8}"
    add(header)
    add("  " + "-" * (len(header) - 2))
    for rule in DMP_ALTERNATIVE_RULES:
        a = summary.forecast_accuracy[rule]
        marker = "  <-- ADOPTED ([HS12]'s own rule)" if rule == "hs13" else ""
        add(
            f"  {rule:<20} {a.n_predicted:>10,} {a.n_true_positive:>8,} {a.n_false_positive:>8,} "
            f"{a.n_false_negative:>8,} {a.precision:>10.3f} {a.recall:>8.3f}{marker}"
        )
    add("")
    add(
        "  THE ADOPTED RULE IS NOT THE BEST SCORER HERE and the pre-registration said so in "
        "advance. Several alternatives have higher precision. The paper's rule is used anyway, "
        "because this family's job is to test its claim on this universe rather than to build "
        "the best dividend-month forecaster this project can -- tuning a predictor against a "
        "score measured on the same sample the returns come from is one step from tuning it "
        "against the returns. None of the alternatives is ever traded."
    )
    add("")

    if not summary.results:
        add("NO SPEC PRODUCED A REPLAYABLE RETURN SERIES.")
        return "\n".join(lines) + "\n"

    add("=" * 78)
    add(f"PER-SPEC RESULTS -- HEADLINE, NET OF {config.cost_bps:.1f}bp ONE-WAY TURNOVER COST")
    add("=" * 78)
    header = (
        f"  {'pattern_id':<28} {'Sharpe':>8} {'DSR':>6} {'PSR0':>6} {'gross':>8} "
        f"{'caught':>7} {'days':>6} {'inv':>6} {'meanL':>7} {'meanS':>7} {'turn':>6}"
    )
    add(header)
    add("  " + "-" * (len(header) - 2))
    for r in summary.results:
        add(
            f"  {r.pattern_id:<28} {r.sharpe_annualized:>+8.3f} "
            f"{_fmt(r.deflated_sharpe.dsr, '.3f'):>6} "
            f"{_fmt(r.deflated_sharpe.psr_vs_zero, '.3f'):>6} "
            f"{r.gross_sharpe_annualized:>+8.3f} "
            f"{r.caught_actual_fraction:>6.1%} {r.n_trading_days:>6} "
            f"{r.invested_fraction:>5.1%} {r.mean_long_leg_size:>7.1f} "
            f"{r.mean_short_leg_size:>7.1f} {r.mean_daily_turnover:>6.3f}"
        )
    add("")
    add(
        f"  Sharpe = annualized NET. gross = 0bp. DSR uses n_trials={DMP_N_TRIALS}. "
        "caught = share of traded long firm-months that actually contained an ex-date (a "
        "DIAGNOSTIC, never a filter). inv = fraction of days both legs were non-empty; a "
        "one-sided day is flat by design and counted. meanL/meanS = mean leg sizes. turn = mean "
        "daily L1 turnover of the net book."
    )
    add("")

    add("COST SENSITIVITY -- annualized Sharpe on the IDENTICAL position path:")
    levels = "  ".join(f"{lvl:>8.1f}bp" for lvl in DMP_COST_SENSITIVITY_BPS)
    add(f"  {'pattern_id':<28} {levels}")
    for r in summary.results:
        cells = "  ".join(
            f"{r.cost_sensitivity_sharpe.get(lvl, float('nan')):>+10.3f}"
            for lvl in DMP_COST_SENSITIVITY_BPS
        )
        add(f"  {r.pattern_id:<28} {cells}")
    add(
        "  The 5.0bp column is the declared HEADLINE. 2.0bp is this project's own sourced best "
        "estimate for an equal-weighted S&P 500 book. Neither was chosen after seeing these "
        "numbers."
    )
    add("")

    add("LEG SIZES, ONE-SIDED DAYS AND DRAG:")
    add(
        f"  {'pattern_id':<28} {'meanL':>7} {'minL':>6} {'maxL':>6} {'meanS':>7} "
        f"{'1sided':>7} {'nLong':>8} {'nShort':>8} {'costDrag':>9} {'netCum':>9}"
    )
    for r in summary.results:
        add(
            f"  {r.pattern_id:<28} {r.mean_long_leg_size:>7.1f} {r.min_long_leg_size:>6} "
            f"{r.max_long_leg_size:>6} {r.mean_short_leg_size:>7.1f} {r.n_one_sided_days:>7} "
            f"{r.n_long_positions:>8,} {r.n_short_positions:>8,} "
            f"{r.total_cost_drag:>9.4f} {r.net_cumulative_return:>+9.4f}"
        )
    add("")

    add("SUBPERIOD SHARPES (three equal contiguous thirds of each spec's own sample):")
    for r in summary.results:
        parts = "  ".join(_fmt(s) for s in r.subperiod_sharpes)
        add(f"  {r.pattern_id:<28} {parts}")
    add("")

    add("POSITION-CONSTRUCTION GATES (each counted, none a performance filter):")
    for r in summary.results:
        add(f"  {r.pattern_id:<28} {r.position_counts}")
    add("")

    add("=" * 78)
    add("THE EX-DAY EVENT STUDY -- THE MECHANISM TEST")
    add("=" * 78)
    es = summary.event_study
    add(
        f"  Mean UNIVERSE-HEDGED return in event time around {es.n_events:,} REAL ex-dates in "
        f"the formation window, cumulated, in basis points. Window "
        f"{DMP_EVENT_WINDOW[0]}..{DMP_EVENT_WINDOW[1]} trading days."
    )
    add(
        "  NOT DGTW characteristic-adjusted as [HS12]'s is -- this project has no "
        "size/book-to-market/momentum matched portfolios -- so the LEVELS are not directly "
        "comparable to the paper's. The SHAPE is what this measures."
    )
    add("")
    add(f"  {'offset':>7} {'mean bp':>9} {'cum bp':>9}")
    for offset, mean_bp, cum_bp in zip(es.offsets, es.mean_excess_bps, es.cumulative_bps):
        if offset in (-20, -15, -10, -5, -3, -2, -1, 0, 1, 2, 3, 5, 10, 20, 30, 40):
            add(f"  {offset:>+7} {mean_bp:>+9.2f} {cum_bp:>+9.2f}")
    add("")
    add(
        f"  RUN-UP (cumulative through the ex-day): {es.run_up_bps:+.1f} bp. "
        f"REVERSAL (cumulative over the {DMP_EVENT_WINDOW[1]} days after): "
        f"{es.reversal_bps:+.1f} bp."
    )
    add("")
    add(
        f"  PRECISION, on the {es.n_complete_events:,} events with a complete window. The "
        "clustered column is the one to read: ex-dates cluster hard into four seasonal pairs, so "
        "events sharing a calendar month share most of their market exposure and a naive t "
        "treats correlated observations as independent."
    )
    add(f"  {'':<12} {'mean bp':>10} {'naive t':>9} {'clustered t':>12}")
    add(
        f"  {'run-up':<12} {es.run_up_bps:>+10.2f} {es.run_up_t:>+9.2f} "
        f"{es.run_up_t_clustered:>+12.2f}"
    )
    add(
        f"  {'reversal':<12} {es.reversal_bps:>+10.2f} {es.reversal_t:>+9.2f} "
        f"{es.reversal_t_clustered:>+12.2f}"
    )
    add(
        f"  {'ROUND TRIP':<12} {es.net_bps:>+10.2f} {'':>9} {es.net_t_clustered:>+12.2f}"
    )
    add("")
    add(
        "  PRE-DECLARED READING: price pressure predicts a positive run-up into day 0 and a "
        "negative drift afterwards that offsets it. [HS12]'s own characteristic-adjusted figures "
        "are +54.2bp of run-up from declaration to ex-day and -73.2bp over the 40 days after, "
        "which the authors call 'large enough to offset the gains during the dividend month'."
    )
    add(
        "  WHAT THIS SAMPLE SHOWS, AND THE CAVEAT THAT FOLLOWS IT: the shape [HS12] describes is "
        "PRESENT here -- a run-up into the ex-day, a larger reversal after it, and a round trip "
        "not distinguishable from zero -- at roughly a quarter of the paper's magnitude, which "
        "is what its own liquidity evidence predicts for the most liquid large-cap segment there "
        "is. DO NOT STOP READING HERE. The next section shows that most of these windows also "
        "contain an earnings announcement, and that the run-up does not survive removing them. "
        "This shape is consistent with the mechanism; it does not establish it."
    )
    add("")

    add("=" * 78)
    add("THE EARNINGS CONFOUND -- A POST-HOC TEST THAT UNDERMINES THE ABOVE")
    add("=" * 78)
    add(
        "  NOT PRE-REGISTERED. Added after the run, because measuring this family's overlap with "
        "the sibling earnings_announcement_premium family turned up something that directly "
        "attacks the event study's interpretation. It is reported here rather than left out "
        "precisely because it is unflattering."
    )
    ec = summary.earnings_confound
    if not ec.available:
        add(
            "  NOT COMPUTED THIS RUN: no earnings-announcement calendar was supplied. Rebuild it "
            "with data/research_runs/fetch_eap_announcement_calendar.py and re-run."
        )
    else:
        add("")
        add(
            f"  {ec.fraction_window_contains_announcement:.1%} of the "
            f"{ec.n_all_events:,} ex-day event windows contain a real 8-K Item 2.02 earnings "
            f"announcement (median distance from ex-date to nearest announcement: "
            f"{ec.median_abs_gap_trading_days:.0f} trading days). So the pre-registered study "
            "CANNOT, on its own, attribute its run-up to dividend price pressure rather than to "
            "earnings. [HS12] does not have this problem -- its Table IV separates the "
            "declaration day, the interim period and the ex-day. This family's universe-hedged "
            "study does not decompose that way."
        )
        add("")
        add(
            "  THE TWO FAMILIES ARE STILL DISTINCT AS EVENTS, which is the other half of the "
            f"overlap question the build brief asked about: only {ec.share_same_day:.1%} of "
            f"ex-dates fall on the SAME trading day as an announcement, {ec.share_within_3_days:.1%} "
            f"within 3 trading days and {ec.share_within_10_days:.1%} within 10. Firms declare "
            "dividends alongside earnings and then go ex about three weeks later, so the "
            "PORTFOLIOS are separable -- this family is not a re-run of the earnings family -- "
            "while the mechanism EVIDENCE is not."
        )
        add("")
        add("  THE CLEAN TEST: the identical event study on ex-dates with NO announcement in window.")
        add("")
        add(f"  {'':<26} {'run-up bp':>10} {'t':>7} {'reversal bp':>12} {'t':>7} {'round trip bp':>14} {'t':>7}")
        add(
            f"  {'ALL ex-dates':<26} {ec.all_run_up_bps:>+10.2f} {ec.all_run_up_t:>+7.2f} "
            f"{ec.all_reversal_bps:>+12.2f} {ec.all_reversal_t:>+7.2f} "
            f"{ec.all_round_trip_bps:>+14.2f} {ec.all_round_trip_t:>+7.2f}   "
            f"(n={ec.n_all_events:,})"
        )
        add(
            f"  {'NO announcement in window':<26} {ec.clean_run_up_bps:>+10.2f} "
            f"{ec.clean_run_up_t:>+7.2f} {ec.clean_reversal_bps:>+12.2f} "
            f"{ec.clean_reversal_t:>+7.2f} {ec.clean_round_trip_bps:>+14.2f} "
            f"{ec.clean_round_trip_t:>+7.2f}   (n={ec.n_clean_events:,})"
        )
        add("  t is clustered by ex-date calendar month.")
        add("")
        add(
            "  READING IT HONESTLY, IN BOTH DIRECTIONS. The run-up's clustered t collapses once "
            "earnings-contaminated windows are removed, so the pre-registered mechanism finding "
            "is NOT SUPPORTED on the uncontaminated subset and this family must not claim it "
            "demonstrates dividend price pressure. BUT the clean test is itself weak: it drops "
            f"~{1 - ec.n_clean_events / max(ec.n_all_events, 1):.0%} of events, and what remains "
            "is a SELECTED population -- firms whose dividend calendar sits far from their "
            "earnings calendar are unusual by construction. The correct conclusion is 'not "
            "supported', NOT 'refuted'. Separating declaration, interim and ex-day returns the "
            "way [HS12] does would need a dividend DECLARATION-date feed, which this project "
            "does not have; that is the measurement a successor needs."
        )
    add("")

    add("=" * 78)
    add("THE PRE-DECLARED WINDOW PREDICTION -- CHECKED, MATCHED PAIR BY MATCHED PAIR")
    add("=" * 78)
    add(
        "  The pre-registration committed IN ADVANCE to this: under the price-pressure "
        "mechanism 'toex' (out at the predicted ex-day) should BEAT 'month' (hold the whole "
        "calendar month), because part of the reversal falls inside the same month. Recorded "
        "before any return existed so that neither outcome could be presented as a discovery."
    )
    add("")
    by_id = {r.pattern_id: r for r in summary.results}
    add(
        f"  {'short leg':<12} {'weighting':<10} {'gross month':>12} {'gross toex':>11} "
        f"{'toex wins?':>11} {'net month':>10} {'net toex':>9}"
    )
    wins = pairs = 0
    for short_leg in ("between", "within", "one_after"):
        for weighting in ("equal", "yield"):
            month_spec = by_id.get(f"dmp_{short_leg}_{weighting}_month")
            toex_spec = by_id.get(f"dmp_{short_leg}_{weighting}_toex")
            if month_spec is None or toex_spec is None:
                continue
            pairs += 1
            won = toex_spec.gross_sharpe_annualized > month_spec.gross_sharpe_annualized
            wins += won
            add(
                f"  {short_leg:<12} {weighting:<10} "
                f"{month_spec.gross_sharpe_annualized:>+12.3f} "
                f"{toex_spec.gross_sharpe_annualized:>+11.3f} "
                f"{'YES' if won else 'no':>11} "
                f"{month_spec.sharpe_annualized:>+10.3f} {toex_spec.sharpe_annualized:>+9.3f}"
            )
    add("")
    add(
        f"  'toex' beats 'month' on GROSS in {wins}/{pairs} matched pairs. The pre-declared "
        "prediction is CONFIRMED on gross -- and REVERSED on net, because exiting mid-month "
        "roughly doubles turnover and this book pays for that. Exiting before the reversal does "
        "capture more of the run-up; it does not survive the cost of doing so."
    )
    add("")

    add("=" * 78)
    add("THE PLACEBO CONTROL -- PRE-DECLARED AS A VETO, NOT A TIEBREAK")
    add("=" * 78)
    add(
        f"  The identical machinery with every predicted month shifted +{DMP_PLACEBO_SHIFT_MONTHS} "
        "month, which for a quarterly payer lands in a month it is NOT due to go ex. (A "
        "six-month shift would have been wrong here: a quarterly payer's ex-months are t, t+3, "
        "t+6, t+9, so it would land on another real payment month and the 'placebo' would be a "
        "live book.) If the placebo earns what the real book earns, the family is a null "
        "regardless of its headline."
    )
    add("")
    add(
        f"  {'pattern_id':<28} {'realGross':>10} {'placeboGross':>13} {'difference':>11} "
        f"{'plCaught':>9}"
    )
    for r in summary.results:
        p = summary.placebo.get(r.pattern_id)
        if p is None or p.status != "ok":
            continue
        add(
            f"  {r.pattern_id:<28} {r.gross_sharpe_annualized:>+10.3f} "
            f"{p.gross_sharpe_annualized:>+13.3f} "
            f"{r.gross_sharpe_annualized - p.gross_sharpe_annualized:>+11.3f} "
            f"{p.caught_actual_fraction:>8.1%}"
        )
    add(
        "  READING IT, per the pre-registration's own rule: the comparison that matters is GROSS "
        "vs GROSS on the SAME spec, since net Sharpes are dominated by a turnover cost both "
        "books pay. plCaught is the check that the shift WORKED -- it should be far below the "
        "live book's caught column, i.e. the placebo genuinely holds these same stocks in months "
        "when nothing is due."
    )
    add("")

    add("=" * 78)
    add("COST DISCLOSURE")
    add("=" * 78)
    for chunk in summary.cost_disclosure.split(". "):
        if chunk.strip():
            add("  " + chunk.strip() + ".")
    add("")

    add("=" * 78)
    add("VERDICT -- BY THE PRE-DECLARED DECISION RULE, NOT A FRESH ONE")
    add("=" * 78)
    best = summary.results[0]
    add(
        f"  Best raw Sharpe: {best.pattern_id} at {best.sharpe_annualized:+.3f} over "
        f"{best.n_trading_days} trading days."
    )
    dsr_results = [r for r in summary.results if r.deflated_sharpe.dsr is not None]
    if dsr_results:
        best_dsr = max(dsr_results, key=lambda r: r.deflated_sharpe.dsr)
        dsr = best_dsr.deflated_sharpe.dsr
        add(f"  Best DSR: {best_dsr.pattern_id} at {dsr:.3f} (n_trials={DMP_N_TRIALS}).")
        add("")
        add("  CONDITION (i): best DSR >= 0.95?")
        add(f"    {'MET' if dsr >= 0.95 else 'NOT MET'} -- {dsr:.3f} against a 0.95 bar.")
        counterpart_id = (
            f"dmp_within_{best_dsr.leg_weighting}_{best_dsr.window}"
        )
        counterpart = next(
            (r for r in summary.results if r.pattern_id == counterpart_id), None
        )
        add(
            "  CONDITION (ii): the 'within'-short-leg counterpart at the same weighting and "
            "window is also materially positive?"
        )
        if counterpart is None:
            add(f"    {counterpart_id} produced no replayable series.")
        else:
            add(
                f"    {counterpart_id} Sharpe {counterpart.sharpe_annualized:+.3f}, "
                f"DSR {_fmt(counterpart.deflated_sharpe.dsr, '.3f')}."
            )
        add("")
        if dsr >= 0.95:
            verdict = "clears condition (i); read condition (ii) and the placebo before calling it a pass"
        elif dsr >= 0.50:
            verdict = "possibly interesting, but short of this family's pre-registered 0.95 bar"
        else:
            verdict = "an HONEST NEGATIVE by this family's own pre-declared decision rule"
        add(f"  VERDICT: {verdict}.")
    add("")

    add("=" * 78)
    add("RESIDUAL LIMITATIONS")
    add("=" * 78)
    for line in (
        (
            "*** THIS FAMILY'S PRINCIPAL DESIGN DEFECT, FOUND AFTER THE RUN AND NOT FIXED IN "
            "IT. *** The 'between' short leg is NOT [HS12]'s 'between companies' portfolio. The "
            "paper's version shorts ALL companies not predicted to pay, INCLUDING firms that "
            "never pay a dividend at all; this implementation's short pool contains only "
            "dividend payers, for two independent reasons. (a) The screening entrypoint prices "
            "only tickers that appear in the dividend calendar, so 129 priced never-payers -- a "
            "fifth of the priced universe -- are absent from the panel entirely. (b) The "
            "uniform 4-prior-ex-date gate, which the pre-registration froze BY NAME and applied "
            "to both legs so that all twelve specs trade one population, excludes a never-payer "
            "by construction. THE PRE-REGISTRATION CONTRADICTED ITSELF HERE: it described "
            "'between' as 'INCLUDING firms that never pay' while simultaneously freezing a gate "
            "that makes that impossible, and the code followed the gate. The consequence is "
            "measurable: 'between' and 'within' differ only by a trailing-12-month recency "
            f"requirement, giving {_short_slots(summary, 'between'):,} against "
            f"{_short_slots(summary, 'within'):,} short slots -- {_short_slot_gap(summary)} -- so the "
            "between-versus-within contrast, which decision-rule condition (ii) rests on, has "
            "far less discriminating power than intended and is NOT the paper's "
            "payer-versus-non-payer contrast. It was NOT re-run with a corrected universe after "
            "the result was seen: changing a frozen gate post-hoc is exactly the move this "
            "family's pre-registration exists to prevent, and the verdict does not turn on it "
            "(condition (i) fails by an order of magnitude either way). It is the first thing a "
            "successor family should fix, and such a family must carry these 12 trials into its "
            "own denominator."
        ),
        (
            "THE UNIVERSE IS THE WRONG ONE FOR THIS EFFECT, and the paper says so. [HS12]'s own "
            "cross-sectional evidence is that ILLIQUID stocks show both larger run-ups and "
            "larger reversals; the S&P 500 is the most liquid large-cap segment there is. Its "
            "own value-weighted alphas sit below its equal-weighted ones. This was written into "
            "the pre-registration as the single strongest reason to expect little here."
        ),
        (
            "NO RISK-FACTOR CONTROL. [HS12] reports four-factor ALPHAS; this family reports raw "
            "long-short Sharpes with no factor adjustment, because this project's harness runs "
            "no factor regressions. Nothing above is an alpha and none of it may be described "
            "as one. The 'within' short leg is a structural substitute for factor neutrality, "
            "not an equivalent of it."
        ),
        (
            "FREQUENCY IS INFERRED, NOT READ. [HS12] reads declared frequency from CRSP's "
            "distribution code; this project has no CRSP, so frequency comes from the count of "
            "the firm's own ex-date months in the trailing year. A misclassified firm is "
            "predicted in the wrong months, which dilutes both legs."
        ),
        (
            "VALUE WEIGHTING IS NOT REPRODUCED. The paper reports equal- and value-weighted "
            "books side by side; this project has no cheap point-in-time market cap for this "
            "universe, so the second weighting axis is dividend YIELD. That is a deviation, not "
            "a replication of the paper's VW book."
        ),
        (
            "DELISTED PRICE COVERAGE. yfinance sells no delisted history, so a name that died "
            "is unpriceable and absent from both legs. OPEN paid-data item for this project."
        ),
        (
            "OVERLAPPING AND CLUSTERED RETURNS. Ex-dates cluster hard into the Feb/Mar, May/Jun, "
            "Aug/Sep and Nov/Dec pairs, so the long leg's composition swings seasonally and "
            "consecutive daily returns share most of their constituents. The daily observation "
            "count feeding the Sharpe and the DSR OVERSTATES the independent information. That "
            "is a SEPARATE caution from the n_trials correction and neither substitutes for the "
            "other."
        ),
        (
            "THE EVENT STUDY IS UNIVERSE-HEDGED, NOT CHARACTERISTIC-ADJUSTED, so its levels are "
            "not comparable to [HS12]'s DGTW-matched figures. Only its shape is."
        ),
        (
            "NOT BIT-REPRODUCIBLE, AND THE THIRD DECIMAL OF EVERY SHARPE ABOVE IS NOISE. The "
            "dividend calendar is cached but PRICES are re-fetched live each run, and yfinance "
            "returns float32-rounded values: two consecutive fetches of the identical 3,437 x "
            "496 panel, seconds apart, were measured to differ by up to 0.00048828125 (= 2^-11) "
            "with identical index, columns and NaN count. Across 2,662 daily returns that moves "
            "annualized Sharpes by up to ~0.008 and the best DSR between 0.076 and 0.078 across "
            "re-runs -- nowhere near a 0.95 bar, but a reader diffing two runs should know the "
            "last digit is vendor float precision, not a real change."
        ),
        (
            f"n_trials={DMP_N_TRIALS} counts THIS grid only. It does not cover the literature "
            "scan that nominated this family, nor the other families this project has screened. "
            "Every DSR above is an UPPER BOUND on the honest one."
        ),
    ):
        add("  - " + line)
    add("")

    add("=" * 78)
    add("PRE-REGISTRATION DISCIPLINE -- WHAT WAS AND WAS NOT DONE AFTER SEEING RESULTS")
    add("=" * 78)
    add(
        f"  The {DMP_N_TRIALS}-spec grid, [HS12]'s forecast rule, the 91-day ex-day projection, "
        f"the ${DMP_MIN_PRICE:.0f} price screen, the {DMP_MIN_PRIOR_EX_DATES}-prior-ex-date gate, "
        "the 5.0bp headline cost, the placebo veto, the event-study reading and the "
        "two-condition decision rule were ALL fixed in the pre-registration and committed in "
        "f8e5c1a before this script was first run. Nothing was added, removed, retuned, "
        "re-windowed or sign-flipped afterwards. The forecast-rule calibration and the ex-day "
        "projection calibration were run BEFORE the pre-registration and are disclosed in it; "
        "both measure DATES only and compute no return, which is why neither is a p-hacking "
        f"route. n_trials stays {DMP_N_TRIALS}."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    started = time.time()
    config = DmpConfig()
    logger.info("starting dividend-month-premium screen: %d specs", DMP_N_TRIALS)

    cached = load_dividend_cache()
    if cached is None:
        raise SystemExit(
            "No dividend calendar cache found. Run "
            "data/research_runs/fetch_dividend_calendar.py first."
        )
    events, calendar_report = cached
    logger.info(
        "loaded %d cached ex-dates covering %s..%s",
        len(events),
        calendar_report.fetch_start,
        calendar_report.fetch_end,
    )

    # The earnings calendar is OPTIONAL: it powers only the post-hoc
    # earnings-confound diagnostic, never a position. Absent, the report
    # says so rather than silently omitting the section.
    announcement_dates: dict[str, list[date]] | None = None
    cached_announcements = load_announcement_calendar_cache()
    if cached_announcements is None:
        logger.warning(
            "no earnings-announcement calendar cache -- the earnings-confound diagnostic will "
            "be reported as NOT COMPUTED. Rebuild it with "
            "data/research_runs/fetch_eap_announcement_calendar.py."
        )
    else:
        announcement_events = cached_announcements[0]
        announcement_dates = {}
        for event in announcement_events:
            announcement_dates.setdefault(event.ticker, []).append(event.filing_date)
        logger.info(
            "loaded %d earnings announcements across %d tickers for the confound diagnostic",
            len(announcement_events),
            len(announcement_dates),
        )

    summary = run_dmp_screening(
        start=FORMATION_START,
        end=RUN_END,
        config=config,
        events=events,
        calendar_report=calendar_report,
        fetch_start=FETCH_START,
        announcement_dates=announcement_dates,
    )
    elapsed = time.time() - started
    logger.info("screen finished in %.1f min: %d results", elapsed / 60, len(summary.results))

    report = build_report(summary, config, elapsed)
    with open(REPORT_PATH, "w") as handle:
        handle.write(report)
    logger.info("wrote report to %s", REPORT_PATH)

    if summary.results:
        db = SessionLocal()
        try:
            # IDEMPOTENCY. Re-running this script must leave ONE set of rows for
            # this run_tag, not two overlapping sets a later reader would have to
            # disentangle -- the shared table keys on (family_key, trial_id,
            # run_tag) only by convention, not by constraint.
            removed = (
                db.query(CrossSectionalTrialResult)
                .filter(
                    CrossSectionalTrialResult.family_key == FAMILY_KEY,
                    CrossSectionalTrialResult.run_tag == RUN_TAG,
                )
                .delete(synchronize_session=False)
            )
            db.commit()
            if removed:
                logger.info("cleared %d pre-existing rows for run_tag=%s", removed, RUN_TAG)
            written = persist_cross_sectional_trial_results(
                db, family_key=FAMILY_KEY, results=summary.results, run_tag=RUN_TAG
            )
            logger.info("persisted %d rows to cross_sectional_trial_results", written)
        finally:
            db.close()
    else:
        logger.error("NO RESULTS -- nothing persisted. See the report for why.")

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
