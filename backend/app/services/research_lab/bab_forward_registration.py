"""THE ONE DELIBERATE, DISCLOSED FORWARD-VALIDATION REGISTRATION OF
2026-08-27: the crypto betting-against-BTC-beta spec xc_btcbeta_l180_h180.

READ THIS BEFORE TREATING THAT REGISTRATION AS ANYTHING. It is NOT an
ordinary auto-registration. Nothing screened on 2026-08-27 cleared this
project's significance bar, and this registration does not claim otherwise.
It is a decision to spend real calendar time collecting real future data on
one hypothesis, made explicitly and recorded here so it can be audited,
argued with, or reversed.

--------------------------------------------------------------------------
WHAT THE BACKWARD EVIDENCE ACTUALLY SAID
--------------------------------------------------------------------------
The Crypto cross-sectional family (cross_sectional_crypto.py) is a
pre-declared, fixed enumeration of 28 definitions: 14 signal definitions x 2
holding periods, with the family size computed from its axes and asserted
before any run. Within that family, the betting-against-BTC-beta mechanism
(Frazzini & Pedersen 2014, with BTC as the market proxy per Liu, Tsyvinski &
Wu 2022) produced the family's most interesting result — and it SURVIVED the
adversarial confound check that killed this project's two most
promising-looking results of the day before:

  * BTC beta of roughly 0.06 — i.e. this stream is very nearly orthogonal to
    the crypto market itself, which is the whole question for a
    dollar-neutral but not market-neutral cross-sectional book.
  * an alpha t-statistic reaching 2.80 against BTC and the equal-weighted
    eligible-crypto basket JOINTLY (compute_crypto_factor_exposure regresses
    both together, so the BTC exposure is over and above the basket rather
    than a duplicate of it).
  * it held up under a regime split.

That is a real confound check passed, and it matters: on 2026-08-26 two
results with better headline DSRs (Commodities 0.767, Buyback 0.598) were
rejected precisely because a factor explained them. This one is not that.

--------------------------------------------------------------------------
AND WHY IT STILL LOST, ON THE MULTIPLE-COMPARISONS GROUND THAT MATTERS
--------------------------------------------------------------------------
It was one of 28 pre-declared trials. Its deflated Sharpe, computed against
that honest n_trials = 28 denominator with sigma_SR taken from its own 27
siblings, does not clear the bar. That is the correct verdict on the
backward data and this module does not dispute it. An alpha t of 2.80 is not
a t of 2.80 when it is the best of 28 searched definitions, and it is
computed with a plain iid standard error that the family's own docstring
already flags as GENEROUS for an autocorrelated, overlapping stream.

--------------------------------------------------------------------------
THE MISTAKE THIS REGISTRATION EXISTS TO AVOID
--------------------------------------------------------------------------
There is an obvious, tempting, and WRONG next move: re-run a narrower
"BTC-beta only" family — 3 lookbacks x 2 holds = 6 trials instead of 28 —
and report the DSR against 6. That would produce a corrected-LOOKING number
that is not corrected for the search that actually produced the hypothesis.
The 28 results were computed and seen; shrinking the denominator afterwards
launders the trial count.

This project has already caught and rejected exactly that move once, with a
different family — the reasoning is written up in
cross_sectional_patterns_round_d.py's module docstring, and it is enforced
in code: screen_cross_sectional_universe's n_trials_override parameter
RAISES if given a value smaller than len(specs), specifically so a smaller
denominator cannot be expressed. Doing the same thing by hand, with a
hand-narrowed spec list, would evade the assertion while committing the
identical error.

The backward data has been fully used. Every legitimate question it can
answer about this family, it has answered. No further backward re-test of a
re-drawn subset can add information — it can only re-describe the same
sample under a friendlier denominator.

--------------------------------------------------------------------------
SO: FORWARD VALIDATION, WHICH IS THE ONLY LEGITIMATE REMAINING TEST
--------------------------------------------------------------------------
Forward validation accumulates a track record out of data that DID NOT EXIST
at registration time. That is a structural property, not a statistical
technique: no amount of searching, tuning, or subset-redrawing done before
today can have seen tomorrow's returns. It is therefore immune to both the
look-ahead and the data-snooping objections that (correctly) sink the
backward result — and it is the only test that remains available.

WHAT WOULD AND WOULD NOT COUNT. Forward validation here is a HYPOTHESIS
TEST, not a promotion pipeline:

  * The registration graduating (status "forward_validated") means ONLY
    that enough real out-of-sample data has accumulated to be worth looking
    at. It is not a verdict. See
    cross_sectional_forward_validation_service.MIN_FORWARD_COMPLETE_HOLDS.
  * The graduation threshold for THIS registration is 360 realized days, not
    the pairs path's 126: max(MIN_FORWARD_VALIDATION_TRADING_DAYS,
    2 x holding_days) with holding_days = 180. At 126 days this spec would
    graduate in the MIDDLE OF ITS FIRST HOLD — a track record of one
    unfinished bet. And 360 crypto rows is ~360 calendar days, because this
    family's rows are calendar days (24/7/365), so this clock runs about a
    year.
  * TWO completed formations is still thin, and must be said out loud
    wherever this is surfaced. The honest evidence is the realized daily
    series and its Sharpe on the family's own 365-day calendar, with the
    formation count printed beside it — never the status word alone.
  * A negative forward result is a real result and must be reported as one.
    The registration's own auto-pruning (a trailing-window Sharpe at or
    below UNDERPERFORMANCE_SHARPE_THRESHOLD flags it "underperforming",
    permanently and non-reversibly) exists so that outcome cannot be quietly
    waited out.

WHY EXACTLY ONE REGISTRATION. Registering several of the family's specs
"to see which works" would re-import the multiple-comparisons problem into
the forward test — the forward record of the best of k registrations is
subject to the same selection effect as the backward best of 28. One
hypothesis, pre-committed, with its reasoning written down before any
forward data exists, is what makes the forward test clean. The spec is
pinned by pattern_id and fingerprinted, so it cannot be swapped later
(cross_sectional_forward_registry's drift check parks the registration
rather than letting it silently change strategies).

WHY l180_h180 SPECIFICALLY, and not another beta variant. It is the
mechanism's own best backward result and the one the confound check was run
on, so it is the hypothesis that was actually formed. Choosing a DIFFERENT
beta variant now, or forming a blend of them, would be a fresh selection
made on the same exhausted backward data. Pre-committing to the one that was
actually looked at is the honest version of this decision, even though "the
best of 28 by backward Sharpe" is exactly the kind of selection that biases
the point estimate — which is the whole reason a clean forward sample is
what is being collected.

--------------------------------------------------------------------------
DISCLOSURE APPENDED 2026-09-04 — THIS REGISTRATION WAS NEVER ACTUALLY
DEPLOYED UNTIL TODAY, EIGHT DAYS AFTER THE DECISION ABOVE WAS MADE
--------------------------------------------------------------------------
PURE APPEND, same convention as the corrections in
lazy_prices_forward_registration.py. Nothing above this section is
rewritten.

WHAT HAPPENED. The decision to register xc_btcbeta_l180_h180 for forward
validation was made and written up on 2026-08-27, above. It was never
finished: register_bab_forward_validation (this module) had no _on_startup
wrapper and app/main.py's lifespan() never called it. `grep -rn
register_bab_forward_validation app tests` before this fix returned the
definition, the __all__ entry, and TEST CALLS ONLY — no production call
path. The other three registrations made around the same period (quality's
two specs, short-interest, and later lazy_prices) were all correctly wired
into lifespan(); this one was not. This was found and disclosed, from code
rather than assumption, in commit 61bd307's price_store_pit_2026-09-04
report (section 5), during an unrelated price-data infrastructure audit —
not caught by any process built to catch it. That absence of a dedicated
check is itself worth naming rather than leaving implicit.

THE GAP, STATED PLAINLY. One task instruction that led to this fix described
the gap as "~seven months" between the 2026-08-27 decision and this
2026-09-04 deployment. That figure is wrong and is corrected here rather
than carried forward uncorrected: 2026-08-27 to 2026-09-04 is eight days,
not seven months. Eight days is still a real deployment gap for a decision
that was written up as final and actionable, and it is disclosed as exactly
that — not rounded up to sound more dramatic, and not rounded down to
sound less consequential.

WHAT THIS MEANS FOR THE FORWARD CLOCK. Because the row was never created,
no forward-validation clock has been running for this hypothesis at all
until this deploy — there is no accumulated track record that this fix
resets or disturbs. `started_at` on the row this deploy creates reflects
today, 2026-09-04, not 2026-08-27; backdating it to the decision date would
manufacture eight days of "forward" observations that were not, in fact,
held out prospectively at the time, which is exactly the kind of dishonesty
this registration's own reasoning (see "SO: FORWARD VALIDATION..." above)
exists to prevent.

WHETHER THE UNDERLYING DECISION STILL HOLDS, RE-CHECKED RATHER THAN
ASSUMED. Before deploying this eight-days-late, this spec's backward
numbers were re-derived twice, independently, from a live run of this
family's own unmodified run_crypto_screening (not from this docstring's
2026-08-27 prose): once as a side effect of the price-store rollout
(price_store_pit_2026-09-04.json/.txt) and once in a wholly separate
process invocation run specifically for this deployment
(data/research_runs/bab_independent_reverify_2026-09-04.json). Both agree
to 1e-15: Sharpe +0.9437630151, DSR 0.3552701584 against the family's own
n_trials=28, 12 formations, BTC beta +0.0572, alpha t-stat +2.681 (net of
BTC and basket exposure jointly), factor-neutralized Sharpe +1.1104 —
consistent with the 2026-08-27 write-up's "BTC beta ~0.06" and "alpha t up
to 2.80" to within the precision either was originally reported at, and
DSR still nowhere near any bar this project has used for a live promotion.
The crypto price path (build_crypto_price_panel -> get_daily_ohlcv) was
separately confirmed, in the same price-store audit, to be numerically
INERT to the retroactive-adjustment defect that caused lazy_prices'
reproduction drift: crypto carries zero dividends and zero splits, so
auto_adjust=True and auto_adjust=False returned BIT-IDENTICAL closes across
200,259 real cells (max relative difference 0.000e+00). Nothing in the
2026-08-27 decision is invalidated by the eight-day delay or by the
price-pipeline work done in the interim; the decision is deployed as
originally written, with this disclosure appended.
"""

import asyncio
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.services.cross_sectional_forward_validation_service import (
    register_or_get_cross_sectional_forward_validation,
)
from app.services.research_lab.cross_sectional_forward_registry import CRYPTO_FAMILY_KEY
from app.services.research_lab.system_account import get_or_create_system_user

logger = logging.getLogger(__name__)

BAB_FAMILY_KEY = CRYPTO_FAMILY_KEY
BAB_PATTERN_ID = "xc_btcbeta_l180_h180"

# The rationale persisted onto the row itself (not just in this docstring),
# so a reader of the database — or of the API listing — sees WHY this
# registration exists without having to find this file. A condensed form of
# the module docstring above, which remains the full statement.
BAB_REGISTRATION_RATIONALE = (
    "DELIBERATE, DISCLOSED REGISTRATION — NOT AN AUTOMATIC ONE. "
    "xc_btcbeta_l180_h180 is the Frazzini-Pedersen betting-against-beta mechanism (BTC as market "
    "proxy) from the 28-definition pre-declared Crypto cross-sectional family. On the backward data "
    "it SURVIVED the adversarial confound check that rejected this project's two better-looking "
    "results of 2026-08-26 (Commodities DSR 0.767, Buyback DSR 0.598, both fully explained by a "
    "factor): BTC beta ~0.06 (near-orthogonal to the crypto market), alpha t up to 2.80 against BTC "
    "and the equal-weighted eligible-crypto basket jointly, and it held up under a regime split. "
    "It nevertheless LOST on multiple-comparisons grounds within its own family: as 1 of 28 "
    "pre-declared trials its deflated Sharpe does not clear the bar, and that verdict on the "
    "backward data stands and is not disputed here. "
    "The improper next move would be to re-run a narrower 'BTC-beta only' family (3 lookbacks x 2 "
    "holds = 6 trials) and report the DSR against 6. That is post-hoc trial-count shrinkage — the "
    "28 results were already computed and seen — and it is the exact mistake this project caught "
    "and rejected once already with a different family (see cross_sectional_patterns_round_d.py; "
    "screen_cross_sectional_universe's n_trials_override RAISES on a denominator smaller than the "
    "spec count precisely so it cannot be expressed in code). The backward data has been fully "
    "used and can answer nothing further about this hypothesis. "
    "Forward validation on data that did not exist at registration time is therefore the only "
    "statistically legitimate way to give this signal a further look — structurally immune to both "
    "look-ahead and data-snooping in a way no backtest re-slice can be. "
    "READING THE RESULT: graduation means ONLY that enough real out-of-sample data has accumulated "
    "to be worth looking at, never that the signal works. The threshold is 360 realized days "
    "(max(126, 2 x holding_days=180)) rather than the pairs path's 126, because at 126 this spec "
    "would graduate mid-first-hold on a record of one unfinished bet; crypto rows are calendar "
    "days, so that clock runs about a year and yields just TWO completed formations, which is thin "
    "and must be stated wherever this is surfaced. The evidence is the realized daily series on "
    "this family's own 365-day calendar with the formation count beside it, not the status word. "
    "A negative forward result is a real result: the trailing-window underperformance rule flags "
    "this registration permanently and non-reversibly if it earns that. "
    "Exactly ONE spec is registered, deliberately: registering several would re-import the "
    "multiple-comparisons problem into the forward test. "
    "DISCLOSURE APPENDED 2026-09-04: this decision was made 2026-08-27 but never actually deployed "
    "until today — this module had no _on_startup wrapper and app/main.py's lifespan() never called "
    "it, an oversight found during an unrelated price-data infrastructure audit (commit 61bd307), not "
    "by any dedicated check. That is an eight-day gap between decision and deployment, not the "
    "'seven months' one drafting instruction for this fix incorrectly stated — corrected here rather "
    "than propagated. No forward clock existed before this row was created, so nothing is backdated: "
    "started_at reflects 2026-09-04, and zero days of unearned track record are claimed. Before "
    "deploying, this spec's backward numbers were re-derived twice from a live run of the family's own "
    "unmodified screening path (not from this rationale's prose): Sharpe +0.9437630151, DSR "
    "0.3552701584 (n_trials=28, 12 formations), BTC beta +0.0572, alpha t-stat +2.681, "
    "factor-neutralized Sharpe +1.1104 — matching the original 2026-08-27 figures to within their own "
    "reported precision, and confirming the DSR still lands nowhere near any promotion bar this "
    "project uses. Crypto's price path was separately confirmed immune to the auto_adjust "
    "retroactive-restatement defect that caused lazy_prices' reproduction drift (crypto has zero "
    "dividends and zero splits; auto_adjust=True and auto_adjust=False returns are bit-identical). "
    "The 2026-08-27 decision is deployed unchanged; this paragraph is the only addition."
)


def register_bab_forward_validation(
    db: Session, user_id: int, *, started_at: date | None = None
) -> tuple[CrossSectionalForwardValidationRegistration, bool]:
    """Create (or return, idempotently) the one BAB forward-validation
    registration. Returns (registration, created).

    Idempotent by the same (user_id, config_hash) rule the pairs path uses,
    so re-running this never resets an accumulated track record — which
    matters more here than anywhere else in the codebase, since the whole
    value of the row is the clock it has been running."""
    return register_or_get_cross_sectional_forward_validation(
        db,
        user_id=user_id,
        family_key=BAB_FAMILY_KEY,
        pattern_id=BAB_PATTERN_ID,
        rationale=BAB_REGISTRATION_RATIONALE,
        started_at=started_at,
    )


# --- the production entry point: app startup ---------------------------------
#
# WHY STARTUP AND NOT A SCRIPT — identical to the other three registrations'
# own comment blocks (quality_forward_registration.py, short_interest_
# forward_registration.py, lazy_prices_forward_registration.py), which state
# it in full. In short: this row has to exist in the PRODUCTION database,
# this project's host (Render, free plan) has no Shell to run a one-off
# script from, and a deploy already happens automatically — so the deploy
# carries the registration.
#
# THIS WRAPPER IS THE FIX FOR THE 2026-09-04 DISCLOSURE ABOVE: the module
# docstring's 2026-08-27 decision was written as if this were already true,
# but no such wrapper existed and nothing called register_bab_forward_
# validation outside tests until this commit. See the module docstring's
# "DISCLOSURE APPENDED 2026-09-04" section for the full account.
#
# WHY THAT IS SAFE TO RUN ON EVERY PROCESS START (and there are many — every
# deploy, and every free-tier wake-from-sleep):
#  * register_bab_forward_validation is idempotent on (user_id, config_hash),
#    so a second start returns the SAME row and never resets the accumulated
#    forward clock, which is the entire value of the row.
#  * It touches no market data. The call resolves the family's own specs and
#    config in memory (build_crypto_family/default_crypto_config —
#    cross_sectional_crypto's family is built once at import, from no live
#    data), fingerprints them and writes at most one indexed row.
#    build_crypto_price_panel — the live yfinance path this family's forward
#    tick uses — is only ever called by the runner's tick, never here, so
#    startup cannot block on a network fetch and cannot look like a hung
#    deploy to Render's health check. A test pins this by detonating every
#    registered family's live-panel builder, this one included.
#  * It cannot take the API down: every failure is caught and logged, and the
#    next process start simply retries.

STARTUP_FAILURE_LOG_MESSAGE = (
    "BAB (crypto betting-against-beta) forward-validation registration failed on startup. The API is "
    "starting anyway (this is a one-shot setup step, never a startup gate) and the next process start "
    "will retry it idempotently — an existing registration's accumulated clock is unaffected."
)


def _format_registration_outcome(
    registration: CrossSectionalForwardValidationRegistration, created: bool, user_id: int
) -> str:
    """One log line, formatted while the session that loaded the row is still
    open — every field below is a lazy/expirable ORM column, and reading one
    off a detached instance raises instead of returning a value."""
    return (
        f"bab forward-validation registration "
        f"{'CREATED' if created else 'ALREADY EXISTS'}: id={registration.id} "
        f"family_key={registration.family_key} pattern_id={registration.pattern_id} "
        f"status={registration.status} user_id={user_id} "
        f"started_at={registration.started_at} "
        f"n_forward_trading_days={registration.n_forward_trading_days} "
        f"threshold={registration.min_trading_days_threshold} "
        f"config_hash={registration.config_hash}"
    )


def register_bab_forward_validation_once() -> list[str]:
    """The SYNCHRONOUS unit of work behind the startup step. Returns one
    human-readable outcome line (a list of one, so the async wrapper's
    logging loop is identical to its siblings'); raises on any failure, which
    the async wrapper turns into a log line.

    Owns its own session and closes it in a finally, sharing nothing with the
    request-scoped get_db sessions or with any runner. Ownership is the system
    account, the same convention every other autonomously created row in this
    project uses — a row owned by whichever human happened to run a script
    would be the wrong answer for a registration the project as a whole is
    making.

    SessionLocal is looked up on the module at call time, not bound at import,
    so tests can monkeypatch it exactly the way the runner tests already do."""
    db = SessionLocal()
    try:
        system_user = get_or_create_system_user(db)
        registration, created = register_bab_forward_validation(db, system_user.id)
        return [_format_registration_outcome(registration, created, system_user.id)]
    finally:
        db.close()


async def register_bab_forward_validation_on_startup() -> None:
    """Create-or-confirm the BAB forward-validation registration, once,
    during app startup. NEVER RAISES.

    Dispatched through asyncio.to_thread because the work below is synchronous
    SQLAlchemy and lifespan() is async — the same thread-boundary discipline
    every background runner already follows for its own DB work.

    `except Exception` deliberately, not BaseException: asyncio.CancelledError
    derives from BaseException, so a shutdown that interrupts this still
    cancels rather than being swallowed and logged as a failure."""
    try:
        outcomes = await asyncio.to_thread(register_bab_forward_validation_once)
    except Exception:
        logger.exception(STARTUP_FAILURE_LOG_MESSAGE)
        return
    for outcome in outcomes:
        # "%s", not an f-string into the message: an outcome line carries a
        # config_hash and could in principle contain a % that logging would
        # then try to interpret as a format spec.
        logger.info("%s", outcome)


__all__ = [
    "BAB_FAMILY_KEY",
    "BAB_PATTERN_ID",
    "BAB_REGISTRATION_RATIONALE",
    "register_bab_forward_validation",
    "register_bab_forward_validation_on_startup",
    "register_bab_forward_validation_once",
]
