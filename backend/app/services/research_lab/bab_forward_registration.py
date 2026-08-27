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
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.services.cross_sectional_forward_validation_service import (
    register_or_get_cross_sectional_forward_validation,
)
from app.services.research_lab.cross_sectional_forward_registry import CRYPTO_FAMILY_KEY

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
    "multiple-comparisons problem into the forward test."
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


__all__ = [
    "BAB_FAMILY_KEY",
    "BAB_PATTERN_ID",
    "BAB_REGISTRATION_RATIONALE",
    "register_bab_forward_validation",
]
