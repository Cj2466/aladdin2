"""THE ONE DELIBERATE, DISCLOSED FORWARD-VALIDATION REGISTRATION OF
2026-09-02: short_interest_ratio / si_ratio_hedged_h21.

READ THIS BEFORE TREATING THIS REGISTRATION AS ANYTHING. It is not a
promotion and it does not claim a validated edge. The family it comes from
returned an HONEST NEGATIVE under its own pre-registered rule, that verdict
stands, and it is not disputed here. What this row is is a decision to spend
real calendar time collecting real future data on one pre-committed
hypothesis, recorded here so it can be audited, argued with, or reversed.

This mirrors quality_forward_registration.py — the same mechanism, the same
startup path, the same reasoning register, the same refusal to let a status
word stand in for evidence — with the differences stated below.

--------------------------------------------------------------------------
WHAT THE BACKWARD EVIDENCE SAID, AND WHAT IT DID NOT
--------------------------------------------------------------------------
cross_sectional_short_interest.py screened twelve pre-declared specs
(2 normalizers x 3 holding periods x 2 portfolio readings) against the
family's own 12-trial DSR denominator, on real FINRA bi-monthly short
interest, real SEC point-in-time share counts and real yfinance prices over
2018-01-12..2026-09-01 (2,169 realized days per spec, run tag
"short_interest_build_2026-09-02"). Its pre-registered bar required the best
spec's DSR to clear 0.95; the best reached 0.948, and the verdict is
therefore a fail. Independent verification reproduced all twelve rows
bit-for-bit and found the miss is BIGGER, not smaller, under the more
standard sigma_SR convention (0.903).

THE SPEC REGISTERED HERE IS NOT THAT BEST SPEC. From the persisted
cross_sectional_trial_results row (family_key "short_interest", trial_id
"si_ratio_hedged_h21"):

    Sharpe +0.4531, PSR(0) 0.9075, DSR 0.7962, n_trials 12, 2,169 days,
    100 formations (4 skipped), ~20.6 names per leg, cost drag 0.0308.

DSR >= 0.5 is a BACKTEST-LEVEL statistical signal, not proof of anything —
the same level that selected cbop (0.8174) and noa_neutral (0.5631) for the
two 2026-08-30 registrations, and this one sits between them. It says a spec
beat the expected maximum of its own family's correlated noise trials more
often than not. It cannot see a data bug, a universe artifact, a cost
misestimate, or a sequential search across families, and this project has
been burned by exactly that before (the raw-NOA family carried DSR up to
0.968 and was then shown to be a sector-composition artifact).

--------------------------------------------------------------------------
WHY THIS SPEC AND NOT THE HIGHER-SCORING ONES — the decision this file is
--------------------------------------------------------------------------
Five of the family's top five specs are DAYS-TO-COVER (short interest over
average daily volume), which is NOT the measure the source paper uses. The
family's post-hoc diagnostic — independently re-derived during verification,
and committed as measure_normalizer_divergence() so it can be re-checked —
found over 34 quarterly formations that the days-to-cover long leg:

  * overlaps the short-interest-ratio long leg by only 19.7% of a leg
    (stricter Jaccard: 11.2% — the two sorts disagree MORE than the headline
    figure suggests);
  * sits at the 72.7th percentile of trading VOLUME;
  * sits at only the 33.2nd percentile of the short-interest ratio itself.

Sorting on low days-to-cover is substantially sorting on high volume. A
year of forward data on si_dtc_ls_h63 would accumulate evidence about a
signal nobody has yet identified, which is what the family's own section 6
was unwilling to switch on unilaterally.

si_ratio_hedged_h21 is the opposite case. It is the paper's OWN measure
(short interest / shares outstanding, module docstring section 1a) x the
paper's OWN portfolio reading (long the low-short-interest tail, hedged
against the eligible universe — section 4's "the one that matters", because
the paper's distinctive claim is about the LONG side alone, not a spread)
x the paper's OWN rebalance cadence (monthly, ~21 trading days, section 4).
It is the single most pre-specified cell in the grid: every one of those
three axes was privileged IN WRITING, in a document committed before any of
these numbers existed. That is why it is registered, not because of where
it ranks.

AND IT IS STILL A SELECTION, WHICH MUST BE SAID PLAINLY. It is not the
family's best backward spec, and choosing a cell after seeing the grid is a
choice made on a sample that is now exhausted. What makes it defensible
rather than post-hoc is that its three axes were pre-committed and its
rejection of the higher-scoring alternative is on a stated mechanism (the
volume confound), not on its score. A reader who thinks that distinction is
too fine should read this row as what it also is: one selected cell of
twelve, whose point estimate is biased upward by the selection, which is
precisely why a clean forward sample is what is being collected.

THIS DEPARTS FROM THE FAMILY MODULE'S OWN WRITTEN RECOMMENDATION, which was
si_dtc_hedged_h63 (the best LONG-SIDE spec, DSR 0.925). That recommendation
came with its own stated reservations — "it is still days-to-cover, so it
inherits the same interpretive problem, and its January concentration (3.2x)
is among the worst in the grid" — and both reservations are what this
registration acts on. The departure is recorded rather than quietly made,
and the family module's section 6 addendum records it there too.

--------------------------------------------------------------------------
THE HONEST CASE AGAINST THIS SPEC, STATED BEFORE ANY FORWARD DATA EXISTS
--------------------------------------------------------------------------
 * ITS OWN FAMILY'S VERDICT IS A NEGATIVE. 0.796 is not a pass of anything;
   the bar this family set itself was 0.95 on its best spec, and this is not
   even that spec.
 * THE SAMPLE IS SHORT. ~8.7 years, where most families here get 10+. Every
   number above carries correspondingly less confidence than a same-numbered
   result from a longer-sample family.
 * RESIDUAL SURVIVORSHIP FLATTERS IT. The common-cross-section mask reimports
   SEC's current-day ticker map, dropping names that are overwhelmingly index
   LEAVERS — disproportionately the hedge leg's natural candidates.
 * A JANUARY TILT REMAINS. This spec earns +0.000304 mean daily return in
   January against +0.000149 outside it (2.05x). That is far milder than the
   days-to-cover hedged specs (3.2x and 4.4x) and milder than the artifact a
   2016 dissertation attributes to the paper's long side, but it is not
   nothing.
 * IT IS A POST-PUBLICATION TEST OF A FREE, PUBLIC SIGNAL on the most-watched
   500 stocks in the world. FINRA gives this data away twice a month. The
   prior should be low, and the family said so before it ran.
 * THE LEGS ARE THIN: ~20.6 names, a 5% tail of a ~400-name cross-section.

ONE STANDING OPTIMISM IS ACTUALLY MILDEST HERE, and it is worth naming
because it is usually the opposite. Costs assume financing_bps_per_year=0.0,
this project's disclosed short-borrow optimism rather than an estimate — and
the family's docstring flags that it bites HARDEST in a family whose whole
subject is short selling. But this spec is long_universe_hedged: its short
side is an equal-weighted basket of the whole eligible S&P 500
cross-section, which is genuinely cheap to borrow. The specs where the
assumption is least defensible are the long_short ones, which short the most
heavily shorted names in the index — and those are exactly the specs this
registration does NOT take.

--------------------------------------------------------------------------
WHY FORWARD VALIDATION IS THE ONLY LEGITIMATE REMAINING TEST
--------------------------------------------------------------------------
Every objection above is an objection about a SAMPLE that has been fully
used. The 2018-2026 backward window can answer nothing further about this
hypothesis, and any further slicing of it can only re-describe it under a
friendlier denominator — the move this project has caught and rejected
before (cross_sectional_patterns_round_d.py; screen_cross_sectional_universe
RAISES on a denominator smaller than the spec count precisely so it cannot be
expressed in code). The family's own closing line is "DO NOT re-test short
interest on this universe without genuinely new data or a genuinely different
hypothesis". A forward record IS genuinely new data: it accumulates out of
observations that did not exist at registration time, so no amount of
searching, tuning or subset-redrawing done before today can have seen it.
That is a structural property, not a statistical technique.

--------------------------------------------------------------------------
HOW TO READ THIS ROW, AND WHAT WOULD COUNT
--------------------------------------------------------------------------
 * Graduation (status "forward_validated") means ONLY that enough real
   out-of-sample data has accumulated to be worth looking at. It is never a
   verdict. See cross_sectional_forward_validation_service.
   MIN_FORWARD_COMPLETE_HOLDS.
 * The threshold is 126 realized trading days = max(the pairs floor of 126,
   2 x holding_days=21). NOTE WHICH TERM BINDS: the day floor does, not the
   two-hold rule, so this registration reaches graduation on SIX completed
   monthly formations over ~6 months rather than the two the quality rows
   graduate on. Six is still thin and must be stated wherever it is
   surfaced, but it is a better clock than either existing row's.
 * This is an equity family on a 252-day calendar (config.periods_per_year =
   252), unlike the crypto registration's 365.
 * The honest evidence is the realized daily series and its Sharpe with the
   formation count printed beside it — never the status word alone.
 * A negative forward result is a real result and must be reported as one.
   The trailing-window underperformance rule flags this registration
   permanently and non-reversibly if it earns that, so the outcome cannot be
   quietly waited out.
 * THERE ARE NOW THREE LIVE REGISTRATIONS (quality_cbop / cbop_ls_h63,
   quality_noa_industry_neutral / noa_neutral_ls_h126_median, and this one).
   "The best of the three" is a selection over three, and a reader who looks
   only at whichever survives is reading a biased point estimate. All three
   must always be reported, including the losers, and none may be quietly
   dropped.

--------------------------------------------------------------------------
WHAT THE FORWARD PATH CANNOT PROTECT AGAINST HERE
--------------------------------------------------------------------------
The drift machinery fingerprints the SPEC and the CONFIG. It cannot
fingerprint DATA. Three residuals specific to this family, all disclosed:

 1. THE NORMALIZER PANEL IS DATA, NOT SPEC. Both of this family's signal
    functions read CrossSectionalData.fundamental_signal, so which quantity
    that slot holds is invisible to the drift check. That is why the family
    is registered here under family_key "short_interest_ratio" exposing only
    the six ratio specs, rather than under one key exposing all twelve — see
    cross_sectional_forward_registry's short-interest section. A
    days-to-cover registration cannot be created against this key at all.
 2. THE UNIVERSE CAN GROW. The candidate pool is the point-in-time S&P 500
    UNION, and a live membership refresh extends it. Unlike the quality
    families' seeded sample (where one added name re-draws ~21 of 200, which
    is why that path pins its window), a union is ADDITIVE — a name is added
    only when it really joined the index, and was_member still gates it per
    formation — so the pool is deliberately NOT pinned here.
 3. VENDOR DATA CAN MOVE UNDERNEATH IT. FINRA files are immutable per
    settlement date, but SEC's frames are not: the live path bounds that
    cache's age (SHORT_INTEREST_LIVE_FRAME_MAX_CACHE_AGE_DAYS) precisely so
    the share-count denominator cannot freeze at its registration-day
    vintage. EDGAR restatement and entity-linking hazards are the same ones
    the backward run documents.

--------------------------------------------------------------------------
CORRECTION APPENDED 2026-09-04 — THE RETURN DEFINITION UNDER
si_ratio_hedged_h21 CHANGED, AND A SEPARATE REPRODUCIBILITY GAP SURFACED
WHILE MEASURING IT
--------------------------------------------------------------------------
PURE APPEND. Nothing above this line is edited.

AdjustmentConvention's default flipped from YAHOO to CRSP on 2026-09-04.
Yahoo's r(t) = P(t)/(P(t-1) - D(t)) - 1 is exactly the true total return
multiplied by 1/(1 - D/P(t-1)) — a leverage on ex-dates proportional to the
distribution — while CRSP's r(t) = (P(t) + D(t))/P(t-1) - 1 is what a holder
actually earned. Decision record, primary sources and the universe-wide
measurement: data/research_runs/dividend_convention_2026-09-04.txt.

MEASURED EFFECT ON THIS REGISTRATION, everything else held byte-identical
(same store, same FINRA cycle files, same SEC frames, same 2026-09-02 window,
one process per arm):

    si_ratio_hedged_h21   YAHOO  Sharpe +0.42711953  DSR 0.77972885
                          CRSP   Sharpe +0.42515503  DSR 0.77850886
                          delta         -0.00196449       -0.00121998

Two parts in a thousand of Sharpe, crossing no threshold. Identical with
`drop_same_day_split_distributions` on or off, i.e. this spec does not
materially hold any of the six same-day split+distribution names.

A SEPARATE OBSERVATION, DISCLOSED BECAUSE IT WAS FOUND WHILE MEASURING THIS
AND NOT BECAUSE THIS CHANGE CAUSED IT. The YAHOO arm above does NOT reproduce
this registration's own recorded Sharpe (+0.4531, run tag
short_interest_build_2026-09-02) or the +0.41870 that the price-store rollout
measured for the same spec earlier the same day. Three same-window rebuilds,
three levels: +0.4531, +0.41870, +0.42712. The convention delta measured here
is clean regardless — both arms share byte-identical inputs and differ only
in the return formula — but this family's absolute LEVEL is evidently not
reproducible across sessions. The price store fixed the PRICE input; the
remaining movement therefore has to come from a non-price input (the SEC
share-count frames and the point-in-time universe are the candidates) or from
the store having accumulated more tickers between runs. NOT DIAGNOSED HERE,
and deliberately not guessed at: it is recorded as an open item for whoever
next needs a byte-reproducible backward number from this family.

Section 1's headline figures (Sharpe +0.4531, PSR(0) 0.9075, DSR 0.7962) are
left exactly as written, because they are the numbers the registration
decision was made on.

Nothing about the spec, config_hash, spec_fingerprint, holding period,
portfolio construction or DSR denominator changed. Verified after the change
by running app/main.py's own lifespan sequence twice against a real database:
five rows, byte-identical across both startups, this one still in_progress.
ExecutionControl.trading_halted is untouched and stays True.

--------------------------------------------------------------------------
CORRECTION APPENDED 2026-09-04 (LATER THE SAME DAY) — THE OPEN
REPRODUCIBILITY ITEM ABOVE, INVESTIGATED
--------------------------------------------------------------------------
PURE APPEND. Nothing above this line is edited.

The previous correction left one item open: this family's absolute level was
not reproducible across sessions (+0.4531 / +0.41870 / +0.42712), and named
the SEC share-count frames, the point-in-time universe, or store ticker
accumulation as candidates, without diagnosing which. This entry is that
diagnosis. Full method and evidence: cross_sectional_short_interest.py's
module docstring section 8, and
data/research_runs/short_interest_reproducibility_2026-09-04.txt.

THREE OF THE FAMILY'S OWN NON-PRICE DATA SOURCES WERE TESTED DIRECTLY, THE
SAME "VARY ONE INPUT, HOLD EVERYTHING ELSE FIXED" METHOD THE PRICE AND
DIVIDEND-CONVENTION CORRECTIONS ABOVE USED:

  * FINRA cycle files — REFUTED as a cause. Three cached files re-fetched
    live and diffed byte-for-byte (md5) against the cache: identical.
    FINRA's claimed per-settlement-date immutability holds.
  * SEC's current-day ticker-to-CIK map (the asymmetry section 3 of the
    family module already names) — REAL churn confirmed (a live refetch one
    week after the cached copy differs by 45 dropped tickers, 69 added, 1
    changed CIK, including AVB, a genuine 2026 index leaver) but MEASURED
    IMMATERIAL: re-running the family's screening function under the old
    map vs the fresh map, everything else identical, changed the panel's
    cell counts but left si_ratio_hedged_h21's Sharpe and DSR identical to
    ten decimal places.
  * SEC's XBRL share-count frames — REAL growth confirmed (the still-open
    CY2026Q3 frame gained exactly 9 rows for this family's own point-in-time
    universe — PVH, CSCO, KSS, CIEN, NTAP, LULU, KEYS, MDT and HPE — between
    a 2026-09-02 and a 2026-09-04 fetch) but STRUCTURALLY UNABLE TO EXPLAIN
    THE DRIFT: every new row's cover-page `end` date falls within the final
    weeks before this
    window's 2026-09-01 cutoff, and this family's own +90-calendar-day
    availability lag (module docstring section 3) delays visibility to
    roughly November 2026 — three months past the window's own end. 35 of
    the 36 cached quarterly frames matched a live refetch exactly; the one
    exception could not have touched any ranked formation in this window
    regardless of fetch timing.

A FOURTH CANDIDATE — the price store's documented "first write wins" policy
(price_store.py section 4) meaning two INDEPENDENTLY first-populated stores
(e.g. two different git worktrees, this project's standing per-task
isolation practice) are each internally reproducible but not guaranteed to
agree with each other — CONFIRMED, WITH AN EXACT MECHANISM, once tested
against the FULL 597-ticker universe rather than an initial 111-ticker
sample (which found zero differences and was simply the wrong sample size).
Exactly 2 tickers, APH and MNST, differ between two independently-populated
stores, traced to source: both executed a real 2-for-1 stock split within
days of this investigation (MNST 2026-08-11, APH 2026-09-03 — one calendar
day before this investigation ran). The store's OWN
`cumulative_split_factor` function, run against each ticker's currently-
complete split history, computes the CORRECT un-adjustment factor; the
ALREADY-STORED rows for both tickers do not match it, because those rows
were written by an earlier fetch, before that specific split had
propagated through every yfinance code path this project's ingestion
touches, and `PriceStore.merge_ticker` never revisits an already-written
row. Because this window's end (2026-09-01) is in the past relative to
"today", the coverage ledger already marks both tickers covered through
2026-09-02 — so this exact query will keep serving the stale, pre-split-
basis price PERMANENTLY, and the store's own revision-detection safety net
(section 4's `PriceStoreReport.revisions`) can never fire, because it only
triggers on an actual re-fetch attempt, which the coverage ledger's whole
purpose is to prevent. THIS IS A REAL, PROJECT-WIDE ARCHITECTURAL GAP, NOT
A SHORT_INTEREST-SPECIFIC ONE: any family holding a ticker that splits
after that ticker's row was first stored will silently carry a stale price
for its entire pre-split history, for as long as the store persists, with
no automatic repair. Currently a local-dev-only risk (Render's free tier
has no persistent disk, so production rebuilds the store fresh on every
deploy), but would become a live-registration risk the day this project
gets persistent production storage. NOT FIXED HERE, deliberately —
recorded as a new open item, the same discipline this project already
applies to the (lower-priority) universe/membership live-fetch gap.

THE FIX MADE: run_short_interest_screening gained a `price_frames`
parameter, structurally identical to run_lazy_prices_screening's own (added
the same night, same reason) — passing a saved snapshot
(yfinance_provider.save_ohlcv_snapshot / load_ohlcv_snapshot) replays a
FROZEN price panel instead of triggering a live fetch, sidestepping
candidate (d) entirely for this family's own backward-research purposes
regardless of whether the deeper price_store fix is ever built. Proof: one
such snapshot, saved for this exact window (691-name universe, 94 tickers
unresolved — identical to the live-fetch run's own count), replayed through
two independent process invocations reproduces si_ratio_hedged_h21 and all
11 sibling specs at Sharpe/DSR delta EXACTLY 0.0 both times.

THE CURRENT BEST REPRODUCIBLE BACKWARD NUMBER, pinned via that snapshot, on
the now-default CRSP convention and now-default raw-price store:

    si_ratio_hedged_h21   Sharpe +0.42004211   DSR 0.77457982
    (100 formations, 4 skipped, avg leg 20.57 names, 2,168 trading days)

This is offered as the number to compare any FUTURE re-run of this exact
window against, not as a claim that it is more "true" than +0.4531,
+0.41870 or +0.42712 — only that it is the first of the four that a reader
of this repository can independently reproduce rather than take on faith,
and that it is itself a snapshot of a moment when a held name (APH) was
mid-split in the real world, so it may need re-pinning once that settles.
It sits comfortably inside the range every one of the prior measurements
occupied (+0.41870 to +0.4531) and changes no conclusion in section 5 or 6
of the family module: DSR 0.77 remains between the two 2026-08-30
registrations (cbop 0.8174, noa_neutral's now-retired 0.5631) and well short
of a validated-edge claim, exactly as every number in this range already
did.

Section 1's headline figures (Sharpe +0.4531, PSR(0) 0.9075, DSR 0.7962) and
the previous correction's YAHOO/CRSP delta are left exactly as written, for
the same reason as before: they are real numbers this project actually
computed and reported, and restating history would hide rather than
disclose what changed. Nothing about the spec, config_hash,
spec_fingerprint, holding period, portfolio construction or DSR denominator
changed. ExecutionControl.trading_halted is untouched and stays True; this
entry is a documentation and reproducibility-tooling change only, made in
an isolated worktree with the full backend test suite run before merge.
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
    SHORT_INTEREST_RATIO_FAMILY_KEY,
)
from app.services.research_lab.system_account import get_or_create_system_user

logger = logging.getLogger(__name__)

SHORT_INTEREST_PATTERN_ID = "si_ratio_hedged_h21"

# The rationale persisted onto the row itself (not just in this docstring),
# so a reader of the database — or of the API listing — sees WHY this
# registration exists without having to find this file. A condensed form of
# the module docstring above, which remains the full statement.
SHORT_INTEREST_REGISTRATION_RATIONALE = (
    "DELIBERATE, DISCLOSED REGISTRATION — NOT AN AUTOMATIC ONE, AND NOT A CLAIM OF VALIDATED EDGE. "
    "si_ratio_hedged_h21 comes from the 12-spec pre-declared short-interest family (Boehmer, Huszar "
    "& Jordan 2010, replicated on real FINRA bi-monthly short interest and real SEC point-in-time "
    "share counts), whose own pre-registered bar required its best spec to clear DSR 0.95, whose "
    "best spec reached 0.948, and whose VERDICT IS THEREFORE AN HONEST NEGATIVE — a verdict that "
    "stands and is not disputed by this row. This spec's own numbers, from the persisted "
    "cross_sectional_trial_results row (run tag short_interest_build_2026-09-02): Sharpe +0.4531, "
    "PSR(0) 0.9075, DSR 0.7962 against the family's own 12-trial denominator over 2,169 realized "
    "days, 100 formations, ~20.6 names per leg. DSR >= 0.5 is a BACKTEST-LEVEL statistical signal "
    "and never proof; 0.796 sits between the two rows registered on 2026-08-30 (cbop 0.8174, "
    "noa_neutral 0.5631). "
    "WHY THIS SPEC AND NOT THE HIGHER-SCORING ONES, which is the whole decision: all five of the "
    "family's top specs are DAYS-TO-COVER, which is not the measure the source paper uses, and the "
    "family's post-hoc diagnostic (independently re-derived in verification, and committed as "
    "measure_normalizer_divergence so it can be re-checked) found the days-to-cover long leg "
    "overlaps the ratio long leg by only 19.7% of a leg (Jaccard 11.2%), sits at the 72.7th "
    "percentile of trading VOLUME and at only the 33.2nd percentile of the short-interest ratio "
    "itself — i.e. sorting on low days-to-cover is substantially sorting on high volume, and a year "
    "of forward data on it would accumulate evidence about a signal nobody has yet identified. "
    "si_ratio_hedged_h21 is instead the paper's OWN measure (short interest / shares outstanding) x "
    "the paper's OWN long-side portfolio reading (long the low tail, hedged against the eligible "
    "universe — the paper's distinctive claim is about the long side alone, not a spread) x the "
    "paper's OWN monthly rebalance (~21 trading days). All three axes were privileged IN WRITING in "
    "a pre-registration committed before any of these numbers existed, which is why it is registered "
    "— not because of where it ranks. IT IS STILL A SELECTION: it is NOT the family's best backward "
    "spec, and picking a cell after seeing the grid biases the point estimate upward, which is "
    "exactly why a clean forward sample is what is being collected. It also DEPARTS from the family "
    "module's own written recommendation (si_dtc_hedged_h63, DSR 0.925), acting on the two "
    "reservations that recommendation itself stated: still days-to-cover, and a 3.2x January "
    "concentration. "
    "THE CASE AGAINST, STATED BEFORE ANY FORWARD DATA EXISTS: its own family's verdict is a "
    "negative; the sample is only ~8.7 years where most families here get 10+; the "
    "common-cross-section mask reimports SEC's current-day ticker map and so drops index LEAVERS, "
    "which FLATTERS the result; this spec still earns 2.05x more per day in January than outside it; "
    "the legs are ~20.6 names; and it is a post-publication test of a free, public, twice-monthly "
    "signal on the most-watched 500 stocks in the world, so the prior should be low. One standing "
    "optimism is at its MILDEST here and is named rather than hidden: costs assume "
    "financing_bps_per_year=0.0, but this spec's short side is an equal-weighted basket of the whole "
    "eligible cross-section (cheap to borrow), not the heavily-shorted names the long_short specs "
    "short — and those specs are precisely the ones this registration does not take. "
    "The backward 2018-2026 sample has been fully used and can answer nothing further; the family's "
    "own closing line forbids re-testing it without genuinely new data, and forward validation on "
    "observations that did not exist at registration time IS that new data — structurally immune to "
    "both look-ahead and data-snooping in a way no backtest re-slice can be. "
    "READING THE RESULT: graduation means ONLY that enough real out-of-sample data has accumulated "
    "to be worth looking at, never that the signal works. The threshold is 126 realized trading days "
    "= max(the pairs floor of 126, 2 x holding_days=21); note that the DAY FLOOR binds here, not the "
    "two-hold rule, so this row graduates on SIX completed monthly formations over ~6 months rather "
    "than the TWO completed formations the quality rows graduate on. Six is still thin and must be "
    "stated wherever this is surfaced; the evidence is the realized daily series on this family's "
    "252-day equity calendar with the formation count beside it, not the status word. A negative "
    "forward result is a real result: the trailing-window underperformance rule flags this "
    "registration permanently and non-reversibly if it earns that. "
    "ONE spec of this family is registered, deliberately — registering several would re-import the "
    "multiple-comparisons problem into the forward test — and it is registered under family_key "
    "short_interest_ratio, which exposes only the six short-interest-RATIO specs, because both "
    "normalizers' signals read the same fundamental_signal slot and a days-to-cover row would "
    "otherwise tick on the ratio panel undetected. THERE ARE NOW THREE LIVE REGISTRATIONS (this one, "
    "quality_cbop / cbop_ls_h63, quality_noa_industry_neutral / noa_neutral_ls_h126_median), so 'the "
    "best of the three' is a selection over three and ALL THREE must always be reported, including "
    "the losers."
)


def register_short_interest_forward_validation(
    db: Session, user_id: int, *, started_at: date | None = None
) -> tuple[CrossSectionalForwardValidationRegistration, bool]:
    """Create (or return, idempotently) the one short-interest
    forward-validation registration. Returns (registration, created).

    Idempotent by the same (user_id, config_hash) rule the pairs path uses,
    so re-running this never resets an accumulated track record — which
    matters more here than anywhere else in the codebase, since the whole
    value of the row is the clock it has been running.

    `started_at` exists only so tests can be deterministic; production
    callers pass nothing, and a forward clock therefore cannot be backdated
    into the backward data it was decided on."""
    return register_or_get_cross_sectional_forward_validation(
        db,
        user_id=user_id,
        family_key=SHORT_INTEREST_RATIO_FAMILY_KEY,
        pattern_id=SHORT_INTEREST_PATTERN_ID,
        rationale=SHORT_INTEREST_REGISTRATION_RATIONALE,
        started_at=started_at,
    )


# --- the production entry point: app startup ---------------------------------
#
# WHY STARTUP AND NOT A SCRIPT — identical to quality_forward_registration.py,
# whose comment block states it in full. In short: this row has to exist in
# the PRODUCTION database, this project's host (Render, free plan) has no
# Shell to run a one-off script from, and a deploy already happens
# automatically — so the deploy carries the registration.
#
# WHY THAT IS SAFE TO RUN ON EVERY PROCESS START (and there are many — every
# deploy, and every free-tier wake-from-sleep):
#  * register_short_interest_forward_validation is idempotent on (user_id,
#    config_hash), so a second start returns the SAME row and never resets the
#    accumulated forward clock, which is the entire value of the row.
#  * It touches no market data. The call resolves the family's own specs and
#    config in memory (build_specs/build_config), fingerprints them and writes
#    at most one indexed row. build_short_interest_live_panel — the
#    FINRA/SEC/yfinance path, which is by far the heaviest live panel in this
#    project — is only ever called by the runner's tick, never here, so
#    startup cannot block on a network fetch and cannot look like a hung
#    deploy to Render's health check. A test pins this by detonating every
#    registered family's live-panel builder.
#  * It cannot take the API down: every failure is caught and logged, and the
#    next process start simply retries.

STARTUP_FAILURE_LOG_MESSAGE = (
    "Short-interest forward-validation registration failed on startup. The API is starting anyway "
    "(this is a one-shot setup step, never a startup gate) and the next process start will "
    "retry it idempotently — an existing registration's accumulated clock is unaffected."
)


def _format_registration_outcome(
    registration: CrossSectionalForwardValidationRegistration, created: bool, user_id: int
) -> str:
    """One log line, formatted while the session that loaded the row is still
    open — every field below is a lazy/expirable ORM column, and reading one
    off a detached instance raises instead of returning a value."""
    return (
        f"short-interest forward-validation registration "
        f"{'CREATED' if created else 'ALREADY EXISTS'}: id={registration.id} "
        f"family_key={registration.family_key} pattern_id={registration.pattern_id} "
        f"status={registration.status} user_id={user_id} "
        f"started_at={registration.started_at} "
        f"n_forward_trading_days={registration.n_forward_trading_days} "
        f"threshold={registration.min_trading_days_threshold} "
        f"config_hash={registration.config_hash}"
    )


def register_short_interest_forward_validation_once() -> list[str]:
    """The SYNCHRONOUS unit of work behind the startup step. Returns one
    human-readable outcome line (a list of one, so the async wrapper's
    logging loop is identical to its quality sibling's); raises on any
    failure, which the async wrapper turns into a log line.

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
        registration, created = register_short_interest_forward_validation(db, system_user.id)
        return [_format_registration_outcome(registration, created, system_user.id)]
    finally:
        db.close()


async def register_short_interest_forward_validation_on_startup() -> None:
    """Create-or-confirm the short-interest forward-validation registration,
    once, during app startup. NEVER RAISES.

    Dispatched through asyncio.to_thread because the work below is synchronous
    SQLAlchemy and lifespan() is async — the same thread-boundary discipline
    every background runner already follows for its own DB work.

    `except Exception` deliberately, not BaseException: asyncio.CancelledError
    derives from BaseException, so a shutdown that interrupts this still
    cancels rather than being swallowed and logged as a failure."""
    try:
        outcomes = await asyncio.to_thread(register_short_interest_forward_validation_once)
    except Exception:
        logger.exception(STARTUP_FAILURE_LOG_MESSAGE)
        return
    for outcome in outcomes:
        # "%s", not an f-string into the message: an outcome line carries a
        # config_hash and could in principle contain a % that logging would
        # then try to interpret as a format spec.
        logger.info("%s", outcome)


__all__ = [
    "SHORT_INTEREST_PATTERN_ID",
    "SHORT_INTEREST_REGISTRATION_RATIONALE",
    "register_short_interest_forward_validation",
    "register_short_interest_forward_validation_on_startup",
    "register_short_interest_forward_validation_once",
]
