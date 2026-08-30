"""THE TWO DELIBERATE, DISCLOSED FORWARD-VALIDATION REGISTRATIONS OF
2026-08-30: quality_cbop / cbop_ls_h63 and quality_noa_industry_neutral /
noa_neutral_ls_h126_median.

READ THIS BEFORE TREATING EITHER REGISTRATION AS ANYTHING. Neither is a
promotion, and neither claims a validated edge. Both families' own module
docstrings say, in their own words, that they did not clear this project's
bar — cross_sectional_quality.py section 5 calls CbOP "no validated edge"
and "a null result", and cross_sectional_quality_neutral.py section 5 calls
the industry-neutral NOA family an "HONEST NEGATIVE". Those verdicts stand
and are not disputed here. What these rows are is a decision to spend real
calendar time collecting real future data on two pre-committed hypotheses,
recorded here so it can be audited, argued with, or reversed.

This mirrors bab_forward_registration.py — the same mechanism, the same
reasoning register, and the same refusal to let a status word stand in for
evidence — with the differences stated below.

--------------------------------------------------------------------------
WHY THESE TWO, AND WHAT "STRONGEST" ACTUALLY MEANS HERE
--------------------------------------------------------------------------
Both are the best spec of their own pre-declared family by deflated Sharpe,
and both clear DSR >= 0.5 — the level this codebase treats everywhere else
as the line below which a result is an honest negative. From the persisted
cross_sectional_trial_results rows (run tags "quality_build_2026-08-28" and
"noa_neutral_build_2026-08-28", 2,926 realized days each):

  * cbop_ls_h63            Sharpe +0.4565, PSR(0) 0.9397, DSR 0.8174 (n=9)
  * noa_neutral_ls_h126_median  +0.3003, PSR(0) 0.8470, DSR 0.5631 (n=18)

DSR >= 0.5 is a BACKTEST-LEVEL statistical signal, not proof of anything.
It says the spec beat the expected maximum of its own family's correlated
noise trials more often than not. It cannot see a data bug, a sector tilt,
a cost misestimate, or a sequential search across families — and this
project has been burned by exactly that: the RAW NOA family carried DSR up
to 0.968, higher than either number above, and its own verification pass
then showed a static long-financials/tech short-REIT portfolio out-earned
every NOA spec on the same dates. A high DSR was not enough there and is
not enough here.

--------------------------------------------------------------------------
THE HONEST CASE AGAINST EACH, STATED BEFORE ANY FORWARD DATA EXISTS
--------------------------------------------------------------------------
cbop_ls_h63. Sharpe +0.46 on a financials-free cross-section averaging ~68
ranked names (decile legs of ~7), which is a small, noisy cross-section by
the standards of the Ball et al. (2016) result it replicates, and that paper
itself reports post-publication attenuation. Its own family's docstring
concluded no spec "clears an 82% probability of beating its own family's
9-trial noise benchmark, well short of this project's bar". Costs assume
financing_bps_per_year = 0.0 — the standing, disclosed short-borrow
optimism, not an estimate.

noa_neutral_ls_h126_median. Its own family's verdict is that the edge does
NOT survive industry neutralization: the family's best spec (this one) sits
barely above the expected maximum of 18 correlated noise trials (0.254 vs
+0.300), four of nine specs are at or below +0.02, and the paper's own
annual rebalance (h252) is ~zero across all three variants. DSR 0.563 is a
coin flip, and it is the MAXIMUM of the family. That module's closing line
is "do not re-test it here without new data or a genuinely different
hypothesis".

FORWARD VALIDATION IS NEW DATA, WHICH IS PRECISELY WHY IT IS THE ONE
LEGITIMATE NEXT TEST AND NOT THE RE-TEST THAT LINE FORBIDS. Every objection
above is an objection about a SAMPLE that has been fully used: the 2015-2026
backward window can answer nothing further about either hypothesis, and any
further slicing of it can only re-describe it under a friendlier
denominator. A forward record accumulates out of data that did not exist at
registration time, so no amount of searching, tuning or subset-redrawing
done before today can have seen it. That is a structural property, not a
statistical technique, and it is what makes this the only remaining test.

--------------------------------------------------------------------------
TWO REGISTRATIONS, NOT ONE — a deliberate departure, disclosed
--------------------------------------------------------------------------
bab_forward_registration.py registers exactly ONE spec and explains why:
registering several of A FAMILY's specs "to see which works" re-imports the
multiple-comparisons problem into the forward test. That reasoning is
honored, not evaded, here — these are ONE spec from each of TWO SEPARATE
pre-declared families testing two unrelated mechanisms (cash-based operating
profitability; within-industry balance-sheet bloat), each pinned by
pattern_id before any forward data exists.

It is still a departure and it still costs something, which must be said
plainly: with two live registrations, "the better of the two" is a selection
over two, and a reader who looks only at whichever one survives is reading a
biased point estimate. Both must be reported, always, including the loser,
and neither may be quietly dropped.

WHY THE BEST BACKWARD SPEC OF EACH FAMILY, and not another variant or a
blend: it is the hypothesis that was actually formed and looked at. Choosing
a different sibling now, or averaging them, would be a fresh selection made
on the same exhausted backward data. Pre-committing to the one that was
actually seen is the honest version of this decision, even though "best of 9
by backward Sharpe" is exactly the kind of selection that biases the point
estimate — which is the whole reason a clean forward sample is what is being
collected.

--------------------------------------------------------------------------
HOW TO READ THESE ROWS, AND WHAT WOULD COUNT
--------------------------------------------------------------------------
 * Graduation (status "forward_validated") means ONLY that enough real
   out-of-sample data has accumulated to be worth looking at. It is never a
   verdict. See cross_sectional_forward_validation_service.
   MIN_FORWARD_COMPLETE_HOLDS.
 * The thresholds differ because the holds do: cbop_ls_h63 graduates at 126
   realized trading days (max(126, 2 x 63) — the pairs floor, reached
   exactly at two complete holds, ~6 months), noa_neutral_ls_h126_median at
   252 (max(126, 2 x 126), ~1 year). Both are TWO completed formations,
   which is thin, and must be stated wherever either is surfaced: two
   independent formations cannot resolve a signal.
 * These are equity families on a 252-day calendar (config.periods_per_year
   = 252), unlike the crypto registration's 365.
 * The honest evidence is the realized daily series and its Sharpe with the
   formation count printed beside it — never the status word alone.
 * A negative forward result is a real result and must be reported as one.
   The trailing-window underperformance rule flags either registration
   permanently and non-reversibly if it earns that, so the outcome cannot
   be quietly waited out.

--------------------------------------------------------------------------
WHAT THE FORWARD PATH CANNOT PROTECT AGAINST HERE — read before trusting it
--------------------------------------------------------------------------
The drift machinery fingerprints the SPEC and the CONFIG. It cannot
fingerprint DATA, and both of these families are data-heavy in ways the
Crypto family is not. See cross_sectional_forward_registry's quality section
for what is closed (the seeded candidate sample is pinned against a live
membership refresh re-drawing it; the companyfacts cache is bounded so
fundamentals cannot freeze; a panel that can rank nothing raises rather than
recording an empty book's exact 0.0 as flat performance) and for the
residuals that are NOT closed (a membership refresh's earliest_overrides, or
a re-vendoring of the membership literals, can still move the candidate
pool; EDGAR restatement and entity-linking hazards are the same ones the
backward run documents).
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
from app.services.research_lab.cross_sectional_forward_registry import (
    QUALITY_CBOP_FAMILY_KEY,
    QUALITY_NOA_NEUTRAL_FAMILY_KEY,
)
from app.services.research_lab.system_account import get_or_create_system_user

logger = logging.getLogger(__name__)

CBOP_PATTERN_ID = "cbop_ls_h63"
NOA_NEUTRAL_PATTERN_ID = "noa_neutral_ls_h126_median"

# The rationales persisted onto the rows themselves (not just in this
# docstring), so a reader of the database — or of the API listing — sees WHY
# each registration exists without having to find this file. Condensed forms
# of the module docstring above, which remains the full statement.

CBOP_REGISTRATION_RATIONALE = (
    "DELIBERATE, DISCLOSED REGISTRATION — NOT AN AUTOMATIC ONE, AND NOT A CLAIM OF VALIDATED EDGE. "
    "cbop_ls_h63 is the best of the 9 pre-declared specs of the cash-based operating profitability "
    "family (Ball, Gerakos, Linnainmaa & Nikolaev 2016, replicated from SEC EDGAR XBRL annual "
    "fundamentals): Sharpe +0.4565, PSR(0) 0.9397, DSR 0.8174 against its own family's 9-trial "
    "denominator over 2,926 realized days (run tag quality_build_2026-08-28). DSR >= 0.5 is a "
    "BACKTEST-LEVEL statistical signal, never proof: this family's own module docstring calls the "
    "result 'no validated edge' and 'a null result', because 0.82 falls well short of this "
    "project's bar. It is also a small cross-section — ~68 ranked names, decile legs of ~7, "
    "financials structurally excluded for lack of COGS-shaped XBRL tags — and Ball et al. "
    "themselves report post-publication attenuation. Costs assume financing_bps_per_year=0.0, the "
    "standing disclosed short-borrow optimism rather than an estimate. "
    "THE WARNING FROM THIS PROJECT'S OWN HISTORY: the sibling raw-NOA family carried a HIGHER DSR "
    "(up to 0.968) and was then shown to be a sector-composition artifact — a static "
    "long-financials/tech short-REIT portfolio out-earned every one of its specs on the same "
    "dates. A high DSR did not survive scrutiny there and is not being treated as sufficient here. "
    "The backward 2015-2026 sample has been fully used and can answer nothing further; forward "
    "validation on data that did not exist at registration time is the only statistically "
    "legitimate remaining test, structurally immune to both look-ahead and data-snooping in a way "
    "no backtest re-slice can be. "
    "READING THE RESULT: graduation means ONLY that enough real out-of-sample data has accumulated "
    "to be worth looking at, never that the signal works. The threshold is 126 realized trading "
    "days = max(the pairs floor of 126, 2 x holding_days=63), i.e. exactly TWO completed "
    "formations, which is thin and must be stated wherever this is surfaced; the evidence is the "
    "realized daily series on this family's 252-day equity calendar with the formation count beside "
    "it, not the status word. A negative forward result is a real result: the trailing-window "
    "underperformance rule flags this registration permanently and non-reversibly if it earns that. "
    "ONE spec of this family is registered, deliberately — registering several would re-import the "
    "multiple-comparisons problem into the forward test — but a SECOND registration from a "
    "different family (quality_noa_industry_neutral / noa_neutral_ls_h126_median) was made the same "
    "day, so 'the better of the two' is a selection over two and BOTH must always be reported, "
    "including the loser."
)

NOA_NEUTRAL_REGISTRATION_RATIONALE = (
    "DELIBERATE, DISCLOSED REGISTRATION — NOT AN AUTOMATIC ONE, AND MADE AGAINST ITS OWN FAMILY'S "
    "STATED NEGATIVE VERDICT, which is not disputed here. noa_neutral_ls_h126_median is the best of "
    "the 9 pre-declared specs of the industry-neutral net-operating-assets family (Hirshleifer, "
    "Hou, Teoh & Zhang 2004, run as the paper's own industry-demeaned robustness construction on "
    "point-in-time SIC buckets read from archived 10-K SGML headers): Sharpe +0.3003, PSR(0) "
    "0.8470, DSR 0.5631 against an 18-trial denominator — this family's own 9 plus the raw NOA "
    "family's 9, carried per that module's standing written pre-declaration so the sequential "
    "search that produced this hypothesis is counted rather than forgotten (run tag "
    "noa_neutral_build_2026-08-28, 2,926 realized days). "
    "THE CASE AGAINST IT, IN ITS OWN FAMILY'S WORDS: the edge does NOT survive industry "
    "neutralization. This spec sits barely above the expected maximum of 18 correlated noise trials "
    "(0.254), four of the nine specs are at or below +0.02, the paper's own annual rebalance (h252) "
    "is ~zero in all three variants, and DSR 0.563 is a coin flip that is also the MAXIMUM of the "
    "family. That module's verdict is an HONEST NEGATIVE and its closing line is 'do not re-test it "
    "here without new data or a genuinely different hypothesis'. "
    "THIS REGISTRATION IS NOT THAT FORBIDDEN RE-TEST: every objection above is an objection about a "
    "SAMPLE that has been fully used, and forward validation accumulates a record out of data that "
    "DID NOT EXIST at registration time — the new data that line asks for, not another slice of the "
    "old. Registering it is a decision to let the one spec that cleared DSR 0.5 be resolved by real "
    "future returns instead of by argument. "
    "READING THE RESULT: graduation means ONLY that enough real out-of-sample data has accumulated "
    "to be worth looking at, never that the signal works. The threshold is 252 realized trading "
    "days = max(126, 2 x holding_days=126), i.e. TWO completed formations (~1 year), which is thin "
    "and must be stated wherever this is surfaced; the evidence is the realized daily series on "
    "this family's 252-day equity calendar with the formation count beside it, not the status word. "
    "Given the backward evidence, a negative forward result is the EXPECTED outcome here and would "
    "be a complete, valued answer — it is a real result and the trailing-window underperformance "
    "rule flags this registration permanently and non-reversibly if it earns one. "
    "ONE spec of this family is registered, deliberately; a SECOND registration from a different "
    "family (quality_cbop / cbop_ls_h63) was made the same day, so 'the better of the two' is a "
    "selection over two and BOTH must always be reported, including the loser."
)


def register_quality_forward_validations(
    db: Session, user_id: int, *, started_at: date | None = None
) -> list[tuple[CrossSectionalForwardValidationRegistration, bool]]:
    """Create (or return, idempotently) both quality forward-validation
    registrations, in a fixed order. Returns [(registration, created), ...].

    Idempotent by the same (user_id, config_hash) rule the pairs path uses,
    so re-running this never resets an accumulated track record — which
    matters more here than anywhere else in the codebase, since the whole
    value of a row is the clock it has been running.

    `started_at` exists only so tests can be deterministic; production
    callers pass nothing, and a forward clock therefore cannot be
    backdated into the backward data it was decided on."""
    return [
        register_or_get_cross_sectional_forward_validation(
            db,
            user_id=user_id,
            family_key=family_key,
            pattern_id=pattern_id,
            rationale=rationale,
            started_at=started_at,
        )
        for family_key, pattern_id, rationale in (
            (QUALITY_CBOP_FAMILY_KEY, CBOP_PATTERN_ID, CBOP_REGISTRATION_RATIONALE),
            (
                QUALITY_NOA_NEUTRAL_FAMILY_KEY,
                NOA_NEUTRAL_PATTERN_ID,
                NOA_NEUTRAL_REGISTRATION_RATIONALE,
            ),
        )
    ]


# --- the production entry point: app startup ---------------------------------
#
# WHY STARTUP AND NOT A SCRIPT. These two rows have to exist in the PRODUCTION
# database, and this project's production host (Render, free plan) has no Shell
# — running a one-off script there is a paid feature. A deploy, on the other
# hand, already happens automatically. So the deploy itself carries the
# registration: main.py's lifespan awaits register_quality_forward_validations_
# on_startup() once per process start, before the background runners launch.
#
# WHY THAT IS SAFE TO RUN ON EVERY PROCESS START (and there are many — every
# deploy, and every Render free-tier wake-from-sleep):
#  * register_quality_forward_validations is idempotent on (user_id,
#    config_hash), so a second start returns the SAME row and never resets the
#    accumulated forward clock, which is the entire value of these rows.
#  * It touches no market data. The call resolves the family's own specs and
#    config in memory (build_specs/build_config), fingerprints them and writes
#    at most one indexed row per family. build_live_panel — the EDGAR/yfinance
#    path — is only ever called by the runner's tick, never here, so startup
#    cannot block on a network fetch and cannot look like a hung deploy to
#    Render's health check.
#  * It cannot take the API down: every failure is caught and logged, and the
#    next process start simply retries.

STARTUP_FAILURE_LOG_MESSAGE = (
    "Quality forward-validation registration failed on startup. The API is starting anyway "
    "(this is a one-shot setup step, never a startup gate) and the next process start will "
    "retry it idempotently — an existing registration's accumulated clock is unaffected."
)


def _format_registration_outcome(
    registration: CrossSectionalForwardValidationRegistration, created: bool, user_id: int
) -> str:
    """One log line per registration, formatted while the session that loaded
    it is still open — every field below is a lazy/expirable ORM column, and
    reading one off a detached instance raises instead of returning a value."""
    return (
        f"quality forward-validation registration "
        f"{'CREATED' if created else 'ALREADY EXISTS'}: id={registration.id} "
        f"family_key={registration.family_key} pattern_id={registration.pattern_id} "
        f"status={registration.status} user_id={user_id} "
        f"started_at={registration.started_at} "
        f"n_forward_trading_days={registration.n_forward_trading_days} "
        f"threshold={registration.min_trading_days_threshold} "
        f"config_hash={registration.config_hash}"
    )


def register_quality_forward_validations_once() -> list[str]:
    """The SYNCHRONOUS unit of work behind the startup step. Returns one
    human-readable outcome line per registration; raises on any failure (the
    async wrapper is what turns a failure into a log line).

    Owns its own session and closes it in a finally, sharing nothing with the
    request-scoped get_db sessions or with any runner. Ownership is the system
    account, the same convention run_register_quality_forward_validation.py
    and every other autonomously created row in this project uses — a row
    owned by whichever human happened to run a script would be the wrong
    answer for a registration the project as a whole is making.

    SessionLocal is looked up on the module at call time, not bound at import,
    so tests can monkeypatch it exactly the way the runner tests already do."""
    db = SessionLocal()
    try:
        system_user = get_or_create_system_user(db)
        return [
            _format_registration_outcome(registration, created, system_user.id)
            for registration, created in register_quality_forward_validations(db, system_user.id)
        ]
    finally:
        db.close()


async def register_quality_forward_validations_on_startup() -> None:
    """Create-or-confirm both quality forward-validation registrations, once,
    during app startup. NEVER RAISES.

    Dispatched through asyncio.to_thread because the work below is synchronous
    SQLAlchemy and lifespan() is async — the same thread-boundary discipline
    every background runner already follows for its own DB work (see
    AutonomousResearchRunner._tick).

    `except Exception` deliberately, not BaseException: asyncio.CancelledError
    derives from BaseException, so a shutdown that interrupts this still
    cancels rather than being swallowed and logged as a failure."""
    try:
        outcomes = await asyncio.to_thread(register_quality_forward_validations_once)
    except Exception:
        logger.exception(STARTUP_FAILURE_LOG_MESSAGE)
        return
    for outcome in outcomes:
        # "%s", not an f-string into the message: an outcome line carries a
        # config_hash and could in principle contain a % that logging would
        # then try to interpret as a format spec.
        logger.info("%s", outcome)


__all__ = [
    "CBOP_PATTERN_ID",
    "CBOP_REGISTRATION_RATIONALE",
    "NOA_NEUTRAL_PATTERN_ID",
    "NOA_NEUTRAL_REGISTRATION_RATIONALE",
    "register_quality_forward_validations",
    "register_quality_forward_validations_on_startup",
    "register_quality_forward_validations_once",
]
