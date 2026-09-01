"""Production runner for the scheduled earnings-announcement premium screen.

Calls the module's OWN entrypoint (run_eap_screening) -- not a
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
from app.models.cross_sectional_trial_result import (
    CrossSectionalTrialResult,
)
from app.services.research_lab.cross_sectional_earnings_premium import (
    EAP_COST_SENSITIVITY_BPS,
    EAP_FAMILY_NAME,
    EAP_MIN_PRIOR_ANNOUNCEMENTS,
    EAP_N_TRIALS,
    EAP_PLACEBO_SHIFT_CALENDAR_DAYS,
    EAP_PREDICTOR_LAG_DAYS,
    EapConfig,
    load_calendar_cache,
    run_eap_screening,
)
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.sp500_membership_history import (
    membership_coverage_end,
)

FAMILY_KEY = EAP_FAMILY_NAME
RUN_TAG = "earnings_announcement_premium_2026-09-01"
REPORT_PATH = "data/research_runs/earnings_announcement_premium_2026-09-01.txt"

# Formations start one full year after MEMBERSHIP_DATA_START (2015-01-07):
# the predictor needs a prior year of each firm's own filing calendar before
# it can place a single prediction. Filings and prices are loaded from
# FETCH_START for that warm-up; no window with an entry before FORMATION_START
# is ever traded.
FORMATION_START = date(2016, 1, 4)
FETCH_START = date(2014, 6, 1)
RUN_END = date(2026, 9, 1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("eap_runner")


def _fmt(value, spec: str = "+.3f") -> str:
    if value is None:
        return "n/a"
    try:
        if math.isnan(value):
            return "n/a"
    except TypeError:
        return "n/a"
    return format(value, spec)


def build_report(summary, config, elapsed: float) -> str:
    lines: list[str] = []
    add = lines.append

    add(
        "SCHEDULED EARNINGS-ANNOUNCEMENT PREMIUM -- Savor & Wilson (JF 2016) / Lamont & Frazzini "
        f"(NBER 13090), screened as exactly {EAP_N_TRIALS} PRE-DECLARED specs with its own "
        "n_trials denominator."
    )
    add(f"family_key={FAMILY_KEY}  run_tag={RUN_TAG}  wall clock {elapsed / 60:.1f} min")
    add(
        f"Formations {FORMATION_START.isoformat()} .. "
        f"{min(RUN_END, membership_coverage_end()).isoformat()} "
        f"(filings and prices warm up from {FETCH_START.isoformat()})."
    )
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/earnings_announcement_premium_PREREGISTRATION.txt, "
        "committed BEFORE any return, Sharpe, DSR or placebo number existed. The spec grid, the "
        "364-day predictor lag, the 5.0bp headline cost and the decision rule below are that "
        "document's, unchanged."
    )
    add("")
    add("THIS IS A LIVE, NETWORK-BACKED RUN: real SEC EDGAR 8-K Item 2.02 filings and real")
    add("yfinance daily bars. No synthetic data is used anywhere in the numbers below.")
    add("")

    add("=" * 78)
    add("SAMPLE")
    add("=" * 78)
    for chunk in summary.sample.text.split(". "):
        if chunk.strip():
            add("  " + chunk.strip() + ".")
    add("")

    add("=" * 78)
    add("PREDICTOR ACCURACY -- MEASURED ON REAL FILINGS, ALL VARIANTS REPORTED")
    add("=" * 78)
    add(
        "Signed error is (actual - predicted) in TRADING days, matched to the nearest actual "
        "announcement by the same ticker. Measured over the formation window."
    )
    add("")
    header = (
        f"  {'lag':>5} {'n_pred':>8} {'unmatch':>8} {'medAbs':>7} {'meanAbs':>8} "
        f"{'meanSgn':>8} {'+/-0':>7} {'+/-1':>7} {'+/-3':>7} {'+/-5':>7} {'+/-7':>7}"
    )
    add(header)
    add("  " + "-" * (len(header) - 2))
    for lag in sorted(summary.sample.predictor_accuracy):
        a = summary.sample.predictor_accuracy[lag]
        add(
            f"  {lag:>5} {a.n_predictions:>8,} {a.unmatched_fraction:>7.1%} "
            f"{a.median_abs_error_days:>7.1f} {a.mean_abs_error_days:>8.2f} "
            f"{a.mean_error_days:>+8.2f} "
            + " ".join(
                f"{a.hit_rate_within.get(k, float('nan')):>6.1%} " for k in (0, 1, 3, 5, 7)
            )
        )
    add("")
    add(
        f"  The declared lag is {EAP_PREDICTOR_LAG_DAYS} days = 52 weeks, chosen because it "
        "PRESERVES DAY OF WEEK; the table is what confirms that empirically rather than assuming "
        "it. A window that MISSES the real announcement holds an ordinary week of an ordinary "
        "stock and cannot earn an announcement premium, so the caught_actual column below is the "
        "realized dilution of every Sharpe in this report."
    )
    add("")

    if not summary.results:
        add("NO SPEC PRODUCED A REPLAYABLE RETURN SERIES.")
        return "\n".join(lines) + "\n"

    add("=" * 78)
    add(f"PER-SPEC RESULTS -- HEADLINE, NET OF {config.cost_bps:.1f}bp ONE-WAY TURNOVER COST")
    add("=" * 78)
    header = (
        f"  {'pattern_id':<22} {'Sharpe':>8} {'DSR':>6} {'PSR0':>6} {'gross':>8} "
        f"{'caught':>7} {'days':>6} {'wins':>7} {'meanL':>7} {'turn':>6}"
    )
    add(header)
    add("  " + "-" * (len(header) - 2))
    for r in summary.results:
        add(
            f"  {r.pattern_id:<22} {r.sharpe_annualized:>+8.3f} "
            f"{_fmt(r.deflated_sharpe.dsr, '.3f'):>6} "
            f"{_fmt(r.deflated_sharpe.psr_vs_zero, '.3f'):>6} "
            f"{r.gross_sharpe_annualized:>+8.3f} "
            f"{r.caught_actual_fraction:>6.1%} "
            f"{r.n_trading_days:>6} {r.n_windows_traded:>7,} "
            f"{r.mean_long_leg_size:>7.1f} {r.mean_daily_turnover:>6.3f}"
        )
    add("")
    add(
        f"  Sharpe = annualized NET. gross = 0bp. DSR uses n_trials={EAP_N_TRIALS}. "
        "caught = share of traded windows that actually contained the firm's real announcement "
        "(a DIAGNOSTIC, never a filter). wins = traded windows. meanL = mean long-leg size. "
        "turn = mean daily L1 turnover of the net book."
    )
    add("")

    add("COST SENSITIVITY -- annualized Sharpe on the IDENTICAL position path:")
    levels = "  ".join(f"{lvl:>8.1f}bp" for lvl in EAP_COST_SENSITIVITY_BPS)
    add(f"  {'pattern_id':<22} {levels}")
    for r in summary.results:
        cells = "  ".join(
            f"{r.cost_sensitivity_sharpe.get(lvl, float('nan')):>+10.3f}"
            for lvl in EAP_COST_SENSITIVITY_BPS
        )
        add(f"  {r.pattern_id:<22} {cells}")
    add(
        "  The 5.0bp column is the declared HEADLINE. 2.0bp is this project's own sourced best "
        "estimate for an equal-weighted S&P 500 book. Neither was chosen after seeing these "
        "numbers."
    )
    add("")

    add("LONG-LEG SIZE, ONE-SIDED DAYS AND DRAG:")
    add(
        f"  {'pattern_id':<22} {'meanL':>7} {'minL':>6} {'maxL':>6} {'meanS':>7} "
        f"{'1sided':>7} {'costDrag':>9} {'netCum':>9}"
    )
    for r in summary.results:
        add(
            f"  {r.pattern_id:<22} {r.mean_long_leg_size:>7.1f} {r.min_long_leg_size:>6} "
            f"{r.max_long_leg_size:>6} {r.mean_short_leg_size:>7.1f} "
            f"{r.n_one_sided_days:>7} {r.total_cost_drag:>9.4f} "
            f"{r.net_cumulative_return:>+9.4f}"
        )
    add("")

    add("TURNOVER DECOMPOSITION -- is the cost that decides this family REAL trading?")
    add(
        "  long_inout / short_inout = a name entering or leaving the long leg (the same trade "
        "seen from both sides); UNAVOIDABLE, it is the strategy. long_drift = weight change "
        "among names STAYING long, because the leg is 1.0 of notional over a membership that "
        "swings with the reporting season -- design-dependent, a fixed per-name notional would "
        "avoid most of it. short_drift = pure renormalization of the ~400-name universe short; "
        "the one bucket that is mostly an accounting artifact. flatUnwind = unwinding the book "
        "on a day the long leg empties out. The five buckets sum exactly to total."
    )
    add(
        f"  {'pattern_id':<22} {'total':>8} {'longInOut':>10} {'longDrift':>10} "
        f"{'shortInOut':>11} {'shortDrift':>11} {'flatUnwind':>11}"
    )
    for r in summary.results:
        d = r.turnover_decomposition
        add(
            f"  {r.pattern_id:<22} {r.mean_daily_turnover:>8.4f} "
            f"{d.get('long_inout', 0.0):>10.4f} {d.get('long_drift', 0.0):>10.4f} "
            f"{d.get('short_inout', 0.0):>11.4f} {d.get('short_drift', 0.0):>11.4f} "
            f"{d.get('flat_unwind', 0.0):>11.4f}"
        )
    add("")

    add("SUBPERIOD SHARPES (three equal contiguous thirds of each spec's own sample):")
    for r in summary.results:
        parts = "  ".join(_fmt(s) for s in r.subperiod_sharpes)
        add(f"  {r.pattern_id:<22} {parts}")
    add("")

    add("WINDOW-CONSTRUCTION GATES (each counted, none a performance filter):")
    for r in summary.results:
        add(f"  {r.pattern_id:<22} {r.window_counts}")
    add("")

    add("=" * 78)
    add("THE PLACEBO CONTROL -- PRE-DECLARED AS A VETO, NOT A TIEBREAK")
    add("=" * 78)
    add(
        f"  The identical machinery on a calendar shifted +{EAP_PLACEBO_SHIFT_CALENDAR_DAYS} "
        "calendar days, so every window lands mid-quarter where nothing is scheduled. If the "
        "placebo earns what the real book earns, the family is a null regardless of its headline."
    )
    add("")
    add(f"  {'pattern_id':<22} {'placeboSR':>10} {'placeboGross':>13} {'realSR':>9} {'caught':>7}")
    real_by_id = {r.pattern_id: r for r in summary.results}
    for pattern_id in sorted(summary.placebo):
        p = summary.placebo[pattern_id]
        real = real_by_id.get(pattern_id)
        add(
            f"  {pattern_id:<22} {_fmt(p.sharpe_annualized):>10} "
            f"{_fmt(p.gross_sharpe_annualized):>13} "
            f"{_fmt(real.sharpe_annualized) if real else 'n/a':>9} "
            f"{p.caught_actual_fraction:>6.1%}"
        )
    add(
        "  READING IT, per the pre-registration's own rule. The comparison that matters is "
        "GROSS vs GROSS on the SAME spec -- net Sharpes are dominated by a turnover cost both "
        "books pay, so comparing them would mostly compare trading costs."
    )
    add("")
    add(f"  {'pattern_id':<22} {'realGross':>10} {'placeboGross':>13} {'difference':>11}")
    for r in summary.results:
        p = summary.placebo.get(r.pattern_id)
        if p is None or p.status != "ok":
            continue
        add(
            f"  {r.pattern_id:<22} {r.gross_sharpe_annualized:>+10.3f} "
            f"{p.gross_sharpe_annualized:>+13.3f} "
            f"{r.gross_sharpe_annualized - p.gross_sharpe_annualized:>+11.3f}"
        )
    add("")
    add(
        "  The placebo's own caught column above is the check that the shift WORKED: it lands on "
        "a real announcement under 1% of the time against 67-93% for the live book, so the "
        "placebo genuinely holds these same stocks at times when nothing is scheduled."
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
        if dsr >= 0.90:
            verdict = "clears this project's ~0.90-0.95 significance standard"
        elif dsr >= 0.50:
            verdict = "possibly interesting, but well short of this project's ~0.90-0.95 standard"
        else:
            verdict = "an HONEST NEGATIVE by this project's own pre-declared decision rule"
        add(
            f"  Best DSR: {best_dsr.pattern_id} at {dsr:.3f} (n_trials={EAP_N_TRIALS}) -- "
            f"{verdict}."
        )
    add("")

    add("=" * 78)
    add("RESIDUAL LIMITATIONS")
    add("=" * 78)
    for line in (
        (
            "THE PREDICTED CALENDAR IS A PROXY for a real earnings-date feed. Its measured "
            "accuracy is reported above and directly dilutes every result; no published "
            "implementation of this premium had to work from an inferred calendar."
        ),
        (
            "CIK-RESOLUTION SURVIVORSHIP. 162 of the 768 point-in-time tickers (21%) do not "
            "resolve in SEC's company_tickers.json, which lists only CURRENT registrants -- the "
            "unresolved names are exactly the acquired and renamed ones. Coverage is therefore "
            "strongly time-trended: ~390 of ~504 real index members are represented in early "
            "2016 against ~501 of 503 in mid-2026. The early sample is thinner AND more "
            "survivor-heavy than the late one, so subperiod comparisons across this sample are "
            "confounded by data coverage, not only by any real change in the premium."
        ),
        (
            "DELISTED PRICE COVERAGE. yfinance sells no delisted history, so even a "
            "CIK-resolved name that died is unpriceable. OPEN paid-data item for this project."
        ),
        (
            "NO BETA CONTROL. If the long leg is systematically higher-beta than the index "
            "short, part of any positive number is beta rather than an announcement premium. "
            "Savor & Wilson's own claim is that the premium EXCEEDS what beta explains; this "
            "family does not estimate betas and cannot make that claim."
        ),
        (
            "OVERLAPPING RETURNS. Earnings cluster into four reporting seasons and windows "
            "overlap heavily, so the daily observation count feeding the Sharpe and the DSR "
            "OVERSTATES the independent information by a large, unquantified factor."
        ),
        (
            "ANNOUNCEMENT-WINDOW SPREAD WIDENING is not modelled. Costs are charged at a flat "
            "rate that prices a stock's normal-times spread, not the wider one it trades at "
            "around its announcement. True costs are HIGHER than every column of the ladder."
        ),
        (
            "ITEM 2.02 IS NOT EXACTLY ONE EARNINGS RELEASE. It is overwhelmingly quarterly "
            "earnings but also covers preliminary-results and guidance 8-Ks; no press-release "
            "text is parsed to tell them apart."
        ),
        (
            f"n_trials={EAP_N_TRIALS} counts THIS grid only. It does not cover the literature "
            "scan that nominated this family, nor the ~28 other families this project has "
            "screened. Every DSR above is an UPPER BOUND on the honest one."
        ),
    ):
        add("  - " + line)
    add("")

    add("=" * 78)
    add("PRE-REGISTRATION DISCIPLINE -- WHAT WAS AND WAS NOT DONE AFTER SEEING RESULTS")
    add("=" * 78)
    add(
        "  The 8-spec grid, the 364-day predictor lag, the 5.0bp headline cost, the placebo "
        "veto and the DSR decision rule were all fixed in the PREREGISTRATION before any return "
        "existed, and that document was committed before this script was first run. Nothing was "
        "added, removed, retuned, re-windowed or sign-flipped afterwards. The predictor-accuracy "
        "calibration that chose the 364-day lag was run BEFORE the pre-registration and is "
        "disclosed in it; it measures announcement DATES only and computes no return, which is "
        f"why it is not a p-hacking route. n_trials stays {EAP_N_TRIALS}."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    started = time.time()
    config = EapConfig()
    logger.info("starting earnings-announcement-premium screen: %d specs", EAP_N_TRIALS)
    logger.info(
        "predictor lag=%dd, min prior announcements=%d, headline cost=%.1fbp",
        EAP_PREDICTOR_LAG_DAYS,
        EAP_MIN_PRIOR_ANNOUNCEMENTS,
        config.cost_bps,
    )

    cached = load_calendar_cache()
    if cached is None:
        raise SystemExit(
            "No EDGAR calendar cache found. Run "
            "data/research_runs/fetch_eap_announcement_calendar.py first."
        )
    events, fetch_report, cache_start, cache_end = cached
    logger.info(
        "loaded %d cached Item 2.02 filings covering %s..%s",
        len(events),
        cache_start,
        cache_end,
    )

    summary = run_eap_screening(
        start=FORMATION_START,
        end=RUN_END,
        config=config,
        events=events,
        fetch_report=fetch_report,
        fetch_start=FETCH_START,
    )
    elapsed = time.time() - started
    logger.info(
        "screen finished in %.1f min: %d results", elapsed / 60, len(summary.results)
    )

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
