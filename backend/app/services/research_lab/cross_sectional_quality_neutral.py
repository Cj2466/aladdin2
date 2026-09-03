"""INDUSTRY-NEUTRAL NET OPERATING ASSETS: a new pre-declared cross-sectional
family testing whether NOA (Hirshleifer/Hou/Teoh/Zhang 2004) predicts
returns WITHIN industry — the follow-up hypothesis the original NOA
family's verification pass (cross_sectional_quality.py, section 6)
explicitly deferred to "a NEW family" rather than building post-hoc.

=======================================================================
1. WHY THIS FAMILY EXISTS — the hypothesis, stated precisely
=======================================================================

The original 9-spec NOA family (family_key "quality_noa", run tag
"quality_build_2026-08-28") was positive on its face (+0.46..+0.66 Sharpe,
DSR 0.88..0.97 on all 9 specs) and was explicitly flagged DO NOT TREAT AS
VALIDATED EDGE: its independent verification pass measured, with live SEC
SIC codes, that the long decile was 37% tech + 26% financials, the short
decile's largest bucket was REITs, and median NOA climbs monotonically
from financials (+0.25) to REITs (+0.83) — on this universe a low-NOA sort
IS close to a long-financials/tech short-REIT sort, and a static sector
portfolio of exactly that shape earns more Sharpe (+0.67) than any NOA
spec. A quick DIAGNOSTIC (not a pre-declared family) demeaning NOA within
sector collapsed the Sharpes to -0.01..+0.22.

This module turns that diagnostic into a real, separately pre-declared
hypothesis test:

    H: NOA predicts the cross-section of returns AMONG INDUSTRY PEERS —
    i.e. the anomaly is balance-sheet bloat, not sector membership.

Hirshleifer et al.'s own paper claims exactly this robustness for its
1964-2002 broad universe ("our main findings remain strong with
industry-demeaned NOA", p.315 of the published JAE version, verified
during the original family's build). This family asks whether that
survives on the 2015-2026 point-in-time S&P 500 sample where the RAW
ranking demonstrably did not.

An honest negative here is a complete, valued answer: it would make
"NOA has no genuine standalone predictive power on this universe" the
final verdict, with the raw family's positive fully attributed to the
sector bet. A positive would be the surprising outcome and gets treated
with THIS project's standing suspicion of surprising positives.

=======================================================================
2. THE PRE-DECLARED CONSTRUCTION — and why this one
=======================================================================

CHOSEN: within-bucket DEMEANING of the NOA signal, cross-sectionally at
each formation date, over that formation's own eligible ranked names,
using point-in-time SIC-derived industry buckets. Signal for ticker i in
bucket b(i) at formation date t:

    signal_i = -( NOA_i(t) - center_{b(i)}(t) )

where center is the bucket's cross-sectional mean (core specs) or median
(sibling specs — NOA is right-skewed, the median variant checks the
result is not an artifact of bucket-mean outlier sensitivity), computed
over the bucket's members among that formation's eligible, NOA-ranked
names only. The negation preserves the source paper's direction (low
residual NOA = long). Everything downstream — decile selection,
magnitude-weighted legs, costs, holding — is the harness unchanged.

The two alternatives considered and REJECTED up front, before any result:

 * Sector-neutral leg construction (equal sector exposure on both legs):
   with ~115-137 ranked names (the measured raw-NOA cross-section) and 8
   buckets, a decile leg of ~11-13 names would need ~1.5 names per sector
   per leg — the construction degenerates into forced off-decile picks
   and single-name sector sleeves. Not viable at this cross-section size.
 * Industry-matched long/short pairs: even more names-hungry, and a
   structurally different (pairwise) portfolio the harness does not
   express — a large new-code surface for a family whose entire premise
   is changing ONE thing (the conditioning of the ranking variable)
   relative to the raw family.

Demeaning wins because (a) it is the source paper's OWN industry
adjustment, so this family tests the exact claim the paper makes; (b) it
is the same construction the verification diagnostic ran informally, so
the pre-declared result is directly comparable to the number that
motivated it; and (c) it reuses the entire audited harness and NOA
pipeline unchanged — the only new moving parts are the bucket data and
one signal function.

MIN_BUCKET_SIZE = 3: a name whose bucket has fewer than 3 ranked members
at a formation is REFUSED (NaN) rather than demeaned. A 1-member bucket
demeans itself to exactly 0 (pure placement noise); a 2-member bucket's
demeaned values are +/-half the pair's spread, ranking on nothing but
within-pair order. 3 is the smallest bucket where distance-from-center
carries any cross-member information. Refusals are measured and reported
(NoaNeutralScreeningSummary.n_min_bucket_refusals), never silent.

Z-scoring within bucket (dividing by bucket dispersion) was considered
and EXCLUDED up front: it is an additional hypothesis about dispersion
normalization the source paper does not make, and this family stays
small and matched to the paper's own construction. Plain demeaning does
mean a high-dispersion bucket contributes more extreme demeaned values
than a tight one — disclosed, inherent to the paper's construction.

=======================================================================
3. POINT-IN-TIME SIC — the look-ahead problem, verified real, and closed
=======================================================================

The obvious free source of industry classification — the submissions API
(data.sec.gov/submissions) — carries only the CURRENT SIC code. Using it
historically would project today's classification onto the past. Checked
EMPIRICALLY before assuming it away, and the problem is REAL and
IN-SAMPLE: Iron Mountain (IRM, in this family's own 200-ticker sample)
reads SIC 6798 (REIT) today, but the archived SGML headers of its own
10-Ks — fetched live 2026-08-28 — read 4220 (public warehousing) on every
filing through 2015-02-27 and 6798 only from its 2016-02-26 filing
onward. A current-SIC bucketing would misclassify IRM as a REIT for every
2015 formation, a full year before EDGAR reclassified it.

CLOSED (not just disclosed), for free: every archived filing's
full-submission text begins with a static SGML header recording the SIC
EDGAR had on file AT DISSEMINATION TIME ("STANDARD INDUSTRIAL
CLASSIFICATION: ... [4220]") — verified point-in-time on the IRM sequence
above, and fetched with HTTP Range requests so only each filing's first
16KB ever moves (see edgar_xbrl_provider.py's SIC endpoints block, all
verified live 2026-08-28). The bucket panel is a forward-filled STEP
series keyed on each 10-K's real filing date — the same construction, on
the same filing events, as the NOA panel itself — so the classification
used at any formation date is the one publicly on file at that date.

RESIDUAL LIMITATIONS, disclosed not hidden:
 * EDGAR's classification can LAG economic reality (IRM elected REIT
   status effective fiscal 2014; EDGAR reflected it between its 2015 and
   2016 filings). The header series is the honest "what was publicly on
   file" record — point-in-time correct by construction — but it is not
   an instantaneous economic-sector truth, and no free source is.
 * Filings before a company's first cached annual accession contribute no
   event; a name is refused (NaN bucket -> never ranked) until its first
   header-dated classification. No backfill — a converter's pre-observation
   years must not inherit its later label. In practice companyfacts
   accession history starts ~2009-2011, years before the 2015 formation
   start, so coverage precedes every formation (measured per run:
   n_noa_without_bucket_slots).
 * A company whose headers ALL lack a parseable SIC falls back to its
   CURRENT SIC for its whole history — counted and named per run
   (current_sic_fallback_tickers).
 * SIC classifications are forward-filled without a staleness bound,
   unlike fundamentals: a classification persists until re-stated, and
   the NOA panel's own 455-day staleness rule already retires any name
   that stops filing before its bucket could matter.

The BUCKET MAP (sic_to_bucket below) is a fixed, coarse 8-bucket
partition frozen before any backtest ran. The three load-bearing
carve-outs follow the verification pass's tilt diagnosis exactly — REITs
(6500-6599, 6798) split from other financials (rest of 6000-6999), tech
(3570s computers, 3600s electronics/semis, 7370s software/IT services)
split from other services — because those are the buckets whose
between-sector composition carried the raw family's result. The
remaining five buckets are a coarse partition of everything else;
their exact boundaries are judgment calls (each documented inline) whose
realized composition is measured and reported per run
(bucket_slot_counts), never assumed. Validated pre-run against the
verification pass's own named tickers: VRSN (7371) and PFG (6321) — the
24/24-formation long-decile names — map to tech and financial; DOC, ARE,
VICI (6798) and INVH (6510) — the short-decile REITs — all map to reit
(current SICs fetched live 2026-08-28). Health INSURERS (6324: UNH, CI,
AET, WCG) deliberately stay in "financial": their balance sheets are
insurer balance sheets, which is the honest NOA peer group, whatever a
GICS-style market classification would say.

=======================================================================
4. THE PRE-DECLARED FAMILY AND ITS DSR DENOMINATOR
=======================================================================

The grid, fixed before any backtest ran: 3 holding periods {63, 126, 252}
x 2 demeaning statistics {mean, median} at deciles, long_short (6 core),
plus a quintile long_short mean-demeaned robustness variant per holding
period (3) = 9 definitions. Same size and shape register as the sibling
quality families; holding-period reasoning is inherited verbatim from
cross_sectional_quality.py section 4 (annual per-firm refresh, staggered
fiscal calendars). long_universe_hedged is deliberately absent: hedging
with the whole (sector-imbalanced) eligible universe would reintroduce
through the hedge leg exactly the between-sector exposure the demeaning
removes from the ranking — the {mean, median} axis replaces it as the
robustness dimension actually relevant to THIS hypothesis.

n_trials FOR THE DSR IS 18, NOT 9 — via screen_cross_sectional_universe's
enlarge-only n_trials_override — and the reasoning must be stated
exactly. This family is a genuinely NEW hypothesis (within-industry
predictive power), never pooled with the raw family: its own family_key,
its own spec list, its own sibling sigma_sr. But this family exists
BECAUSE the raw NOA family's 9 trials showed a (spurious) positive — a
sequential search the within-family count cannot see — and the original
module pre-declared, in writing, before this family was designed
("this run's 9 trials carried into its denominator",
cross_sectional_quality.py section 5). Honoring that standing
pre-declaration costs conservatism only: 9 own specs + 9 raw-NOA trials
= 18. The verification diagnostic's informal demeaned runs are NOT
additional trials beyond this: they are the same 9 raw specs' returns
re-examined, already counted in the 9 carried, and this family's specs
were fixed before ITS results existed.

Costs: DEFAULT_XS_COST_BPS (5 bps one-way) via default_quality_config —
identical to every S&P 500 equity family. financing_bps_per_year stays
0.0 (the standing disclosed short-borrow optimism, see
cross_sectional.py). Universe: the IDENTICAL seeded 200-ticker sample as
the raw family (build_quality_sample, seed 20260828) — deliberately, so
the neutral result is about the same cross-section the artifact was
found in, not a universe change wearing a neutralization's clothes.

=======================================================================
5. PRODUCTION RUN 2026-08-28 — MEASURED COVERAGE AND RESULTS
=======================================================================

Run tag "noa_neutral_build_2026-08-28", persisted to
cross_sectional_trial_results under family_key
"quality_noa_industry_neutral" (9 rows, n_trials=18). Formations
2015-01-07..2026-08-27, price panel 2014-12-08..2026-08-27, 2,926
realized trading days per spec — the identical window, seeded sample,
membership gate and NOA panel as the raw family's canonical post-fix run
(same 38 no-CIK tickers including EQR, same 32-name price gap, same
2,196 NOA observations with 201 missing-cash refusals, same 181-day
median panel-cell age).

SIC COVERAGE (all measured): 162 tickers with SIC history. 2,437 annual
filing headers fetched, 2,436 carrying a parseable SIC and 1 without;
exactly 1 accession's fetch failed (CRM 0001108524-21-000014 — the whole
archive directory 404s on EDGAR, verified directly; CRM's classification
is covered by its adjacent years). TWO current-SIC whole-history
fallbacks, both structurally harmless because neither name can ever
rank: SE is Sea Limited, a foreign private issuer filing 20-F/6-K (no
10-K -> no annual accessions AND no NOA), and XOM's ticker now resolves
to CIK 2115436 — a new Exxon holding-company entity whose companyfacts
holds only 10-Qs so far (same consequence). The 6 tickers with no bucket
at all (AET, CSRA, EMC, EQR, FB, TWX) are all no-CIK departed members
that never rank in ANY quality family. The load-bearing coverage number:
ZERO ranked ticker-formation slots had an NOA value but no point-in-time
bucket.

MEASURED SIC DRIFT: exactly 1 of 162 tickers' BUCKET changed inside the
window — IRM, industrial(4220)->reit(6798) between its 2015-02-27 and
2016-02-26 filings — and the same 1 ticker is the only current-vs-
history bucket mismatch. So the current-SIC shortcut would have
mis-bucketed one sampled name for one year of formations; the
point-in-time construction cost nothing and removed that error class
entirely. (Bucket-level drift; finer SIC-code-level changes that stay
inside one bucket are not counted because they cannot change the
demeaning.)

COMPOSITION (h126 cadence, 2,397 ranked slots): consumer 24.3%,
industrial 22.9%, tech 16.7%, energy_utility 11.7%, financial 10.3%,
healthcare 8.6%, reit 5.4%, telecom_media 0.1%. 36 slots (1.5%) refused
by MIN_BUCKET_SIZE=3 — almost entirely telecom_media, whose sampled
names are mostly in the departed-member price gap, leaving it below 3
ranked names on nearly every formation. Decile legs averaged 9.5-9.9
names, quintile legs 19.5-20.1; 0 skipped formations.

RESULTS — THE EDGE DOES NOT SURVIVE INDUSTRY NEUTRALIZATION. All 9
specs at 2,926 days, DSR at n_trials=18, sigma_sr 0.137, expected max
noise Sharpe 0.254:

    noa_neutral_ls_h126_median    +0.300  DSR 0.563
    noa_neutral_ls_h63_median     +0.260  DSR 0.508
    noa_neutral_ls_h126_quintile  +0.116  DSR 0.319
    noa_neutral_ls_h126_mean      +0.094  DSR 0.294
    noa_neutral_ls_h252_median    +0.022  DSR 0.215
    noa_neutral_ls_h252_mean      +0.008  DSR 0.201
    noa_neutral_ls_h63_mean       -0.054  DSR 0.148
    noa_neutral_ls_h63_quintile   -0.064  DSR 0.139
    noa_neutral_ls_h252_quintile  -0.067  DSR 0.137

Raw NOA's +0.46..+0.66 (DSR 0.88..0.97 on every spec) becomes
-0.07..+0.30 (DSR 0.14..0.56) once the ranking is conditioned on
industry. The family's best spec sits barely above the expected maximum
of 18 correlated noise trials (0.254) and its DSR says 56% — a coin
flip, and that is the MAXIMUM of the family. Five specs are at or below
+0.02; the paper's own annual rebalance (h252) is ~zero across all three
variants. Median demeaning consistently outranks mean demeaning
(right-skewed NOA within buckets moves the mean center around), but the
ordering is a within-noise reshuffle, not a signal. These numbers also
agree with the verification pass's informal diagnostic on the raw specs
(mean-demeaned -0.01..+0.22, median-demeaned +0.07..+0.34) — two
independent constructions of the same adjustment, same answer.

VERDICT — HONEST NEGATIVE, and the final answer to the NOA question on
this universe: NOA has no detectable predictive power for returns among
industry peers on the 2015-2026 point-in-time S&P 500 sample. Combined
with the raw family's verification (a static long-fin/tech-short-REIT
portfolio out-earning every raw NOA spec), the raw family's positive is
fully accounted for by between-industry composition, and nothing
measurable remains once it is removed. This differs from Hirshleifer et
al.'s reported industry-demeaning robustness in their 1964-2002 broad
universe; whether the anomaly decayed post-publication, never lived in
the large-cap segment, or needs the multi-thousand-name cross-section,
THIS dataset cannot distinguish — all three are consistent with these
numbers. Do not trade NOA in any form on this universe; do not re-test
it here without new data or a genuinely different hypothesis (and carry
these 18 trials into any such denominator).

CORRECTION ADDENDUM 2026-09-02 — XOM WAS MISSING FROM THE RUN ABOVE.
SEC's ticker map had already moved XOM onto CIK 2115436, the successor
of Exxon's 2026-07-01 holding-company reorganization (29 filings from
2026-07-01 to 2026-08-28, ZERO of them 10-Ks), so Exxon produced no NOA value and no point-in-time SIC bucket
and was silently absent from every formation. Fixed in
edgar_xbrl_provider.py (see its SUCCESSOR-SHELL RESOLUTION block).
RE-RUN 2026-09-02, one price fetch replayed to both arms, same cached
fundamentals, same 9 specs, same 18-trial denominator: the pre-fix arm
reproduced every Sharpe and DSR above exactly, and with XOM restored
(17 NOA observations, fiscal 2009..2025, +0.500..+0.769) the family
moves from -0.067..+0.300 to -0.067..+0.304, MAX |dSharpe| = 0.0335,
DSR 0.137..0.563 -> 0.138..0.571. Per-spec: h126_median +0.300 ->
+0.304, h63_median +0.260 -> +0.267, h126_quintile +0.116 -> +0.126,
h126_mean +0.094 -> +0.095, h252_median +0.022 -> +0.020, h252_mean
+0.008 -> +0.007, h63_mean -0.054 -> -0.053, h63_quintile -0.064 ->
-0.031, h252_quintile -0.067 -> -0.067.
THE VERDICT ABOVE IS UNCHANGED — still an honest negative, still no
validated edge, still a coin flip at the family maximum. One real
improvement is independent of the Sharpes: XOM now has a POINT-IN-TIME
bucket read from its own 10-K headers instead of falling back to the
current-day submissions SIC, which is exactly the projection-of-today-
onto-the-past this family's design exists to avoid — the "bucketed
from CURRENT SIC only" disclosure drops from ['SE', 'XOM'] to ['SE'].
Full detail in data/research_runs/xom_cik_fix_2026-09-02.txt.

=======================================================================
CORRECTION ADDENDUM 2026-09-04 — "THE PAPER'S OWN ANNUAL REBALANCE
(h252)" IS WRONG. HHTZ FORM PORTFOLIOS **MONTHLY**.
=======================================================================
PURE APPEND, same convention as the 2026-09-02 addendum above: nothing
in sections 1-5 is edited, so what was claimed stays visible next to
what is true. NO NUMBER IN THIS MODULE CHANGES; NO VERDICT CHANGES. What
changes is one factual characterisation of the source paper that this
module states twice (section 5 results discussion, and the closing
verdict paragraph's "the paper's own annual rebalance (h252) is ~zero
across all three variants") and that was carried verbatim into
quality_forward_registration.py's docstring AND into the registration
rationale persisted on the LIVE forward-validation row.

THE PRIMARY SOURCE, RE-READ RATHER THAN RE-QUOTED. The JAE-accepted
manuscript (title page "This Draft: March 29, 2004"; published as
Journal of Accounting and Economics 38(1), December 2004, pp. 297-331)
was fetched 2026-09-04 from the corresponding authors' own posting at
https://haas.berkeley.edu/wp-content/uploads/HHTZ-032904-jae.pdf and
text-extracted with pdftotext. Three passages, verbatim:

 * Section 4.1.1: "Every month, stocks are ranked by NOA, placed into
   deciles, and the equal-weighted and value-weighted monthly raw and
   characteristic adjusted returns are computed. We require at least a
   four-month gap between the portfolio formation month and the fiscal
   year end to ensure that investors have the financial statement data
   prior to forming portfolios."

 * Table 4 notes: "Every month between July, 1964 and December, 2002,
   portfolios are formed monthly by assigning firms to deciles based on
   the magnitude of NOA in year t. To allow for a minimum of a four-
   month lag between fiscal year end and the return month, all returns
   are measured from 5 months to 16 months after fiscal year end."

 * Section 3.2: "The NOA, Accruals, Size and Book-to-market variables,
   however, are only updated every 12 months."

WHERE THE ERROR CAME FROM, AND WHY IT IS STILL AN ERROR. The third quote
is true and is almost certainly what "annual rebalance" was reaching
for: the RANKING VARIABLE refreshes once a year per firm. But the
PORTFOLIO is re-formed every month — with staggered fiscal year-ends
across firms, composition changes monthly even though each firm's own
NOA does not. Those are different things, and this module's grid axis
(`holding`) is the second one, not the first. So h252 is not "the
paper's own rebalance"; of {63, 126, 252} it is the FURTHEST from
monthly and h63 is the closest.

WHAT THIS DOES TO THE READING OF THE GRID — it makes it WORSE, not
better. Under the corrected cadence the most literature-faithful cell
of the nine is h63 with MEAN demeaning (the paper's word is
"industry-demean", and this module's own section 2 designates mean the
CORE spec and median a robustness SIBLING): noa_neutral_ls_h63_mean,
Sharpe -0.0535, DSR 0.1476 — the second-worst cell in the family and
negative. Under the erroneous annual reading it was h252_mean at
+0.0080 / DSR 0.2013. Either way the mean-demeaned axis the paper's own
wording implies is flat to negative at every horizon
(-0.0535 / +0.0945 / +0.0080, arithmetic mean +0.0163).

WHAT IT DOES **NOT** CHANGE. Sections 1-3 are unaffected: the
industry-demeaning construction itself IS the paper's own robustness
check, re-verified verbatim from the same retrieved PDF, section 3.4 —
"Given the industry variation in NOA noted here, we have verified that
our main findings remain strong when we industry-demean our net
operating assets measure (results not reported; see Zhang (2004) for an
industry study on NOA)." (Noted for completeness, because it bears on
how much weight the sanction carries: the paper reports NO numbers for
it and defers to a separate study.) The section-5 verdict — HONEST
NEGATIVE, no detectable within-industry NOA predictability on this
universe — is unaffected and is if anything strengthened.

CONSEQUENCE OUTSIDE THIS FILE. The same erroneous phrase is load-bearing
in quality_forward_registration.py, which used "the paper's own annual
rebalance (h252) is ~zero" as a disclosed weakness of a registration it
made anyway. That file now carries a full re-review of the noa_neutral
registration appended 2026-09-04, including a recommendation awaiting
human sign-off. Read it before citing this family's registration as
precedent for anything.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from app.services.market_data.edgar_xbrl_provider import (
    EdgarXbrlProvider,
    SicHistory,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_quality import (
    NOA_N_TRIALS,
    QUALITY_COST_BPS,
    QUALITY_FINANCING_BPS_PER_YEAR,
    QUALITY_HOLDING_DAYS,
    QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    QUALITY_RANK_FRACTION,
    QUALITY_ROBUSTNESS_RANK_FRACTION,
    QUALITY_SAMPLE_SEED,
    QUALITY_SIGNAL_LOOKBACK_ROWS,
    FactorBuildDiagnostics,
    FactorObservation,
    _median_age,
    build_point_in_time_factor_frame,
    build_quality_sample,
    compute_noa_observations,
    default_quality_config,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    was_member,
)

logger = logging.getLogger(__name__)

NOA_NEUTRAL_CITATION = (
    "Hirshleifer, Hou, Teoh & Zhang, 'Do investors overvalue firms with bloated balance "
    "sheets?' (Journal of Accounting and Economics, 2004) — the paper's own industry-demeaned "
    "robustness construction (p.315), run as its own pre-declared family after the raw-NOA "
    "family's positive was diagnosed as a sector-composition artifact"
)

# --- the industry bucket map (frozen before any backtest — see section 3) ---

SECTOR_BUCKETS: tuple[str, ...] = (
    "reit",
    "financial",
    "tech",
    "healthcare",
    "energy_utility",
    "telecom_media",
    "consumer",
    "industrial",
)


def sic_to_bucket(sic: int) -> str:
    """The coarse industry bucket for one SIC code. Deterministic, total
    (every code maps somewhere — "industrial" is the residual), and FROZEN
    before any backtest ran. Order matters: the REIT test precedes the
    financial range it carves out of; the tech ranges precede the consumer
    services ranges they overlap numerically."""
    # REITs and real-estate operators/lessors — the short decile's dominant
    # bucket in the raw family's tilt diagnosis, split from financials
    # because their NOA (median +0.83) sits at the opposite extreme from
    # banks/insurers (+0.25): 6500-6599 real estate, 6798 REIT proper.
    if 6500 <= sic <= 6599 or sic == 6798:
        return "reit"
    # Everything else in the finance division: banks, brokers, insurers —
    # including health insurers (6324: UNH/CI/AET), whose balance sheets
    # are insurer balance sheets and belong with their NOA peers whatever
    # a market-sector scheme would label them.
    if 6000 <= sic <= 6999:
        return "financial"
    # Computers/storage (3570s), electronics incl. semiconductors (3600s),
    # software and IT services (7370s: VRSN 7371, MSFT/CRM 7372). Coarse on
    # purpose: 3600s also holds electrical-equipment makers — a broader
    # "electronics & electrical" peer group, disclosed, not a bug.
    if 3570 <= sic <= 3579 or 3600 <= sic <= 3699 or 7370 <= sic <= 7379:
        return "tech"
    # Drugs/biotech (2830s), medical devices/instruments (3840s), health
    # services (8000s: labs, hospitals, dialysis).
    if 2830 <= sic <= 2839 or 3840 <= sic <= 3859 or 8000 <= sic <= 8099:
        return "healthcare"
    # Coal (1200s), oil & gas extraction/services (1300s), refining
    # (2900s), utilities (4900s) — the capital-intensity peer group.
    if 1200 <= sic <= 1399 or 2900 <= sic <= 2999 or 4900 <= sic <= 4999:
        return "energy_utility"
    # Publishing (2700s), broadcasting/telecom (4800s), movies (7800-7849).
    if 2700 <= sic <= 2799 or 4800 <= sic <= 4899 or 7800 <= sic <= 7849:
        return "telecom_media"
    # Consumer goods, retail/wholesale distribution and consumer services:
    # agriculture (0100s), food/beverage/tobacco/apparel (2000-2399),
    # furniture (2500s), soap/cosmetics (2840s ONLY — 2851 paints is
    # industrial), rubber/leather/footwear (3000-3199), autos (3710s),
    # toys (3940s), trade (5000-5999 incl. restaurants), hotels/personal
    # services (7000-7299), auto rental (7500s), recreation/gaming
    # (7850-7999).
    if (
        100 <= sic <= 999
        or 2000 <= sic <= 2399
        or 2500 <= sic <= 2599
        or 2840 <= sic <= 2849
        or 3000 <= sic <= 3199
        or 3710 <= sic <= 3719
        or 3940 <= sic <= 3949
        or 5000 <= sic <= 5999
        or 7000 <= sic <= 7299
        or 7500 <= sic <= 7599
        or 7850 <= sic <= 7999
    ):
        return "consumer"
    # The residual: mining, construction, paper, industrial chemicals,
    # metals, machinery, aerospace/defense, transport, business services.
    return "industrial"


# The smallest bucket a demeaned value may come from — see section 2.
MIN_BUCKET_SIZE = 3

# --- point-in-time bucket panel ---------------------------------------------


def build_point_in_time_bucket_frame(
    close: pd.DataFrame,
    sic_histories: dict[str, SicHistory],
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """The point-in-time industry-bucket STEP panel: one column per ticker
    aligned to close's exact index/columns, each cell the bucket of the SIC
    code publicly on file (latest filing-header observation at or before
    that date), forward-filled only, never backfilled — a converter's
    pre-observation history must never inherit its later label (the IRM
    case, section 3). NaN before a ticker's first header-dated SIC and for
    tickers with no usable history at all.

    Tickers whose headers ALL lack a parseable SIC fall back to their
    CURRENT SIC for their whole history — a disclosed approximation, named
    per run, chosen over silently dropping the name entirely.

    Returns (bucket frame, tickers with no bucket ever,
    current-SIC-fallback tickers)."""
    empty = pd.Series(np.nan, index=close.index, dtype=object)
    columns: dict[str, pd.Series] = {}
    no_bucket: list[str] = []
    fallback: list[str] = []

    for ticker in close.columns:
        history = sic_histories.get(ticker)
        events = (
            sorted((f, s) for f, s in history.events if s is not None) if history else []
        )
        if not events and history is not None and history.current_sic is not None:
            # Whole-history fallback: no filing header ever carried a SIC
            # for this company, but the submissions API does today.
            events = [(date.min, history.current_sic)]
            fallback.append(ticker)
        if not events:
            no_bucket.append(ticker)
            columns[ticker] = empty.copy()
            continue

        stamps = pd.DatetimeIndex([pd.Timestamp(f) for f, _ in events])
        buckets = pd.Series([sic_to_bucket(s) for _, s in events], index=stamps, dtype=object)
        buckets = buckets[~buckets.index.duplicated(keep="last")].sort_index()
        union = buckets.index.union(close.index).sort_values()
        columns[ticker] = buckets.reindex(union).ffill().reindex(close.index)

    frame = pd.DataFrame(columns, index=close.index)[list(close.columns)]
    return frame, sorted(no_bucket), sorted(fallback)


# --- the signal --------------------------------------------------------------


def signal_industry_demeaned_noa(
    history: CrossSectionalData,
    *,
    bucket_frame: pd.DataFrame,
    statistic: str,
    min_bucket_size: int = MIN_BUCKET_SIZE,
) -> pd.Series:
    """The industry-demeaned NOA signal at one formation date: raw NOA
    minus its own bucket's cross-sectional center (mean or median),
    computed over THIS formation's eligible ranked names only, negated so
    the harness's top decile is the low-residual-NOA (lean-for-its-
    industry) side, matching the source paper's direction.

    Conditioning on the ELIGIBLE cross-section is deliberate and load-
    bearing: the harness hands this function a history view whose columns
    are already restricted to the formation date's point-in-time members,
    so bucket centers are computed among the names actually being ranked —
    "lean for its industry AMONG today's ranked peers", which is the
    hypothesis — never over departed members or unpriced names.

    The bucket row is read at the view's own last (formation) timestamp
    from a step frame built exclusively from filing dates <= each cell's
    date, so the classification used is the one publicly on file at
    formation — same point-in-time contract as the NOA value itself. A
    name with no bucket, or whose bucket has fewer than min_bucket_size
    ranked members here, is refused (NaN), which excludes it from ranking
    per the SignalFn contract."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_industry_demeaned_noa requires CrossSectionalData.fundamental_signal; "
            "the spec must set requires_fundamental_signal=True and the caller must supply "
            "the frame."
        )
    if statistic not in ("mean", "median"):
        raise ValueError(f"unknown demeaning statistic {statistic!r} (mean or median)")
    row = frame.iloc[-1].astype(float)
    formation_ts = frame.index[-1]
    buckets = bucket_frame.loc[formation_ts].reindex(row.index)

    valid = np.isfinite(row.to_numpy()) & buckets.notna().to_numpy()
    values = row[valid]
    if values.empty:
        return pd.Series(np.nan, index=row.index, dtype=float)
    labels = buckets[valid]
    grouped = values.groupby(labels)
    center = grouped.transform(statistic)
    sizes = grouped.transform("size")
    demeaned = (values - center).where(sizes >= min_bucket_size)
    return (-demeaned).reindex(row.index).astype(float)


# --- the pre-declared family -------------------------------------------------

NOA_NEUTRAL_HOLDING_DAYS: tuple[int, ...] = QUALITY_HOLDING_DAYS  # (63, 126, 252)
NOA_NEUTRAL_DEMEAN_STATISTICS: tuple[str, ...] = ("mean", "median")

# 3 holds x 2 demeaning statistics at deciles (6 core) + 3 quintile
# mean-demeaned robustness variants = 9 definitions, fixed before any
# backtest ran. See section 4 for why long_universe_hedged is absent.
NOA_NEUTRAL_N_CORE_TRIALS = len(NOA_NEUTRAL_HOLDING_DAYS) * len(NOA_NEUTRAL_DEMEAN_STATISTICS)
NOA_NEUTRAL_N_ROBUSTNESS_TRIALS = len(NOA_NEUTRAL_HOLDING_DAYS)
NOA_NEUTRAL_N_TRIALS = NOA_NEUTRAL_N_CORE_TRIALS + NOA_NEUTRAL_N_ROBUSTNESS_TRIALS

# The DSR denominator: this family's own 9 specs PLUS the raw NOA family's
# 9 trials, per that module's standing written pre-declaration ("this
# run's 9 trials carried into its denominator") — the sequential search
# that produced this hypothesis, counted rather than forgotten. Applied
# via screen_cross_sectional_universe's enlarge-only n_trials_override.
# See section 4 for the full reasoning.
NOA_NEUTRAL_DSR_N_TRIALS = NOA_NEUTRAL_N_TRIALS + NOA_N_TRIALS


def build_noa_neutral_family(bucket_frame: pd.DataFrame) -> list[CrossSectionalSpec]:
    """The 9 pre-declared specs, bound to a concrete point-in-time bucket
    panel. The GRID (holds x statistics x rank fractions, and the count of
    9) is fixed in the module constants above; the bucket frame is runtime
    DATA injected into each spec's signal closure — the same relationship
    the sibling family's specs have to the fundamental frame the harness
    hands them — never a searched-over axis."""
    specs: list[CrossSectionalSpec] = []
    for statistic in NOA_NEUTRAL_DEMEAN_STATISTICS:
        for holding in NOA_NEUTRAL_HOLDING_DAYS:
            specs.append(
                CrossSectionalSpec(
                    pattern_id=f"noa_neutral_ls_h{holding}_{statistic}",
                    family="net_operating_assets_industry_neutral",
                    citation=NOA_NEUTRAL_CITATION,
                    signal_fn=partial(
                        signal_industry_demeaned_noa,
                        bucket_frame=bucket_frame,
                        statistic=statistic,
                    ),
                    lookback_days=QUALITY_SIGNAL_LOOKBACK_ROWS,
                    holding_days=holding,
                    portfolio="long_short",
                    rank_fraction=QUALITY_RANK_FRACTION,
                    requires_fundamental_signal=True,
                )
            )
    for holding in NOA_NEUTRAL_HOLDING_DAYS:
        specs.append(
            CrossSectionalSpec(
                pattern_id=f"noa_neutral_ls_h{holding}_quintile",
                family="net_operating_assets_industry_neutral",
                citation=NOA_NEUTRAL_CITATION,
                signal_fn=partial(
                    signal_industry_demeaned_noa,
                    bucket_frame=bucket_frame,
                    statistic="mean",
                ),
                lookback_days=QUALITY_SIGNAL_LOOKBACK_ROWS,
                holding_days=holding,
                portfolio="long_short",
                rank_fraction=QUALITY_ROBUSTNESS_RANK_FRACTION,
                requires_fundamental_signal=True,
            )
        )

    assert len(specs) == NOA_NEUTRAL_N_TRIALS == 9, (
        f"industry-neutral NOA built {len(specs)} definitions; the declared grid implies "
        f"{NOA_NEUTRAL_N_TRIALS} and the build pre-declared exactly 9. All three must agree — "
        "a drift silently changes this family's DSR denominator."
    )
    assert NOA_NEUTRAL_DSR_N_TRIALS == 18 and NOA_NEUTRAL_DSR_N_TRIALS > NOA_NEUTRAL_N_TRIALS
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.requires_fundamental_signal for s in specs)
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.leg_weighting == "magnitude" for s in specs)
    assert all(s.cohort_formation_days is None for s in specs)
    assert all(s.holding_days in NOA_NEUTRAL_HOLDING_DAYS for s in specs)
    return specs


# --- production entry point --------------------------------------------------


@dataclass
class NoaNeutralScreeningSummary:
    """run_noa_neutral_screening's full result: screening output plus every
    measured coverage number a reader needs — universe accounting inherited
    from the sibling family's discipline, plus this family's own SIC
    point-in-time accounting and realized bucket composition."""

    results: list[CrossSectionalScreeningResult]
    n_family_trials: int  # 9 — the family's own pre-declared size
    n_dsr_trials: int  # 18 — the denominator actually applied (section 4)
    # Universe accounting (same fields, same meaning as the sibling).
    universe_size: int
    sample_size: int
    sample_seed: int
    missing_cik: list[str]
    failed_edgar_fetch: list[str]
    missing_price_data: list[str]
    tickers_without_noa: list[str]
    panel_start: date | None
    panel_end: date | None
    formation_start: date
    # SIC point-in-time accounting (section 3) — all measured.
    n_annual_headers_with_sic: int = 0
    n_annual_headers_without_sic: int = 0
    n_header_fetch_failures: int = 0
    tickers_without_bucket: list[str] = field(default_factory=list)
    current_sic_fallback_tickers: list[str] = field(default_factory=list)
    # Tickers whose header-derived bucket CHANGED inside the formation
    # window (the IRM case) — the direct measure of how much a
    # current-SIC-only shortcut would have mis-bucketed.
    bucket_drift_tickers: list[str] = field(default_factory=list)
    # Tickers with at least one in-window header bucket differing from
    # today's submissions-API bucket.
    current_vs_history_mismatch_tickers: list[str] = field(default_factory=list)
    # Realized composition, measured on the h126 core cadence's formation
    # dates over ranked (eligible, NOA-and-bucket-bearing) names.
    bucket_slot_counts: dict[str, int] = field(default_factory=dict)
    n_min_bucket_refusals: int = 0
    n_noa_without_bucket_slots: int = 0
    noa_diagnostics: FactorBuildDiagnostics = field(default_factory=FactorBuildDiagnostics)
    median_noa_value_age_days: float = float("nan")
    cost_bps: float = QUALITY_COST_BPS
    financing_bps_per_year: float = QUALITY_FINANCING_BPS_PER_YEAR
    warnings: list[str] = field(default_factory=list)


def _measure_bucket_composition(
    close: pd.DataFrame,
    noa_frame: pd.DataFrame,
    bucket_frame: pd.DataFrame,
    formation_start: date,
    holding_days: int,
) -> tuple[dict[str, int], int, int]:
    """(bucket -> ranked ticker-formation slots, slots refused by
    MIN_BUCKET_SIZE, slots with NOA but no bucket), measured on the given
    cadence's formation dates re-derived exactly as the harness derives
    them (first row at/after formation_start, then every holding_days
    rows) with the same eligibility gate (point-in-time member + finite
    price). Measurement only — the backtests never read this."""
    positions = np.flatnonzero(close.index.date >= formation_start)  # type: ignore[attr-defined]
    if len(positions) == 0:
        return {}, 0, 0
    slot_counts: Counter = Counter()
    n_refused = 0
    n_no_bucket = 0
    for i in range(int(positions[0]), len(close.index) - 1, holding_days):
        formation_day = close.index[i].date()
        prices = close.iloc[i]
        noa_row = noa_frame.iloc[i]
        bucket_row = bucket_frame.iloc[i]
        eligible = [
            t
            for t in close.columns
            if was_member(t, formation_day) and np.isfinite(prices[t])
        ]
        values = noa_row[eligible]
        has_noa = values[np.isfinite(values.to_numpy())]
        buckets = bucket_row[has_noa.index]
        n_no_bucket += int(buckets.isna().sum())
        labeled = buckets.dropna()
        sizes = labeled.groupby(labeled).transform("size")
        for bucket, size in zip(labeled, sizes):
            if size >= MIN_BUCKET_SIZE:
                slot_counts[str(bucket)] += 1
            else:
                n_refused += 1
    return dict(slot_counts), n_refused, n_no_bucket


def _measure_bucket_drift(
    sic_histories: dict[str, SicHistory], start: date, end: date
) -> tuple[list[str], list[str]]:
    """(tickers whose header bucket changed inside [start, end], tickers
    with an in-window header bucket differing from the current-day
    submissions bucket). The in-window bucket set is the bucket in force
    AT start (last event at or before it) plus every event inside the
    window — exactly what the step panel exposes to formations."""
    drift: list[str] = []
    mismatch: list[str] = []
    for ticker, history in sic_histories.items():
        events = sorted((f, s) for f, s in history.events if s is not None)
        if not events:
            continue
        window_buckets: list[str] = []
        at_start = [s for f, s in events if f <= start]
        if at_start:
            window_buckets.append(sic_to_bucket(at_start[-1]))
        window_buckets.extend(sic_to_bucket(s) for f, s in events if start < f <= end)
        if len(set(window_buckets)) > 1:
            drift.append(ticker)
        if (
            window_buckets
            and history.current_sic is not None
            and any(b != sic_to_bucket(history.current_sic) for b in window_buckets)
        ):
            mismatch.append(ticker)
    return sorted(drift), sorted(mismatch)


def run_noa_neutral_screening(
    start: date = MEMBERSHIP_DATA_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    edgar: EdgarXbrlProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> NoaNeutralScreeningSummary:
    """THE production entry point: the sibling family's exact NOA pipeline
    (same seeded sample, same EDGAR extraction, same factor formula, same
    step panel, same price panel and membership gate) plus the
    point-in-time SIC panel, screened as the 9-spec industry-neutral
    family with the 18-trial DSR denominator of section 4."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Screening start {start.isoformat()} predates point-in-time membership coverage "
            f"({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that date would "
            "silently see an empty universe."
        )
    end = end if end is not None else date.today()  # noqa: DTZ011 — price-fetch end bound only
    provider = provider if provider is not None else YFinanceProvider()
    edgar = edgar if edgar is not None else EdgarXbrlProvider()
    config = config if config is not None else default_quality_config()
    config.formation_start = start

    warnings: list[str] = []
    sample, universe_size = build_quality_sample(start, end)

    extractions, missing_cik, failed_fetch = edgar.fetch_line_items_for_tickers(sample)
    if missing_cik:
        warnings.append(
            f"{len(missing_cik)} of {len(sample)} sampled tickers resolve no CIK in SEC's "
            "current-day ticker map (departed members whose symbols died — see "
            "cross_sectional_quality.py section 3) and can never be ranked."
        )
    if failed_fetch:
        warnings.append(
            f"{len(failed_fetch)} EDGAR companyfacts fetches failed outright after retries."
        )
    if edgar.cik_resolution.describe():
        warnings.append(
            "SEC ticker-map CIK resolution: " + edgar.cik_resolution.describe() + "."
        )

    sic_histories, _, sic_failed = edgar.fetch_sic_history_for_tickers(
        [t for t in sample if t not in missing_cik]
    )
    if sic_failed:
        warnings.append(f"{len(sic_failed)} tickers produced no SIC history (fetch failures).")

    padded_start = start - timedelta(days=QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    close, missing_price = provider.get_price_history(sample, padded_start, end)
    if close.empty:
        return NoaNeutralScreeningSummary(
            results=[],
            n_family_trials=NOA_NEUTRAL_N_TRIALS,
            n_dsr_trials=NOA_NEUTRAL_DSR_N_TRIALS,
            universe_size=universe_size,
            sample_size=len(sample),
            sample_seed=QUALITY_SAMPLE_SEED,
            missing_cik=missing_cik,
            failed_edgar_fetch=failed_fetch,
            missing_price_data=missing_price,
            tickers_without_noa=[],
            panel_start=None,
            panel_end=None,
            formation_start=start,
            warnings=[*warnings, "No price data resolved for any sampled ticker."],
        )
    if missing_price:
        warnings.append(
            f"{len(missing_price)} of {len(sample)} sampled tickers resolved no price data "
            "(the standing departed-member yfinance gap — see cross_sectional.py)."
        )

    noa_obs: dict[str, list[FactorObservation]] = {}
    noa_diag = FactorBuildDiagnostics()
    for ticker, extraction in extractions.items():
        obs, diag = compute_noa_observations(extraction)
        noa_obs[ticker] = obs
        noa_diag.merge(diag)

    noa_frame, noa_ages, no_noa = build_point_in_time_factor_frame(close, noa_obs)
    if no_noa:
        warnings.append(
            f"{len(no_noa)} of {len(close.columns)} priced tickers produced no usable NOA "
            "observation and are never ranked."
        )

    bucket_frame, no_bucket, sic_fallback = build_point_in_time_bucket_frame(
        close, sic_histories
    )
    if sic_fallback:
        warnings.append(
            f"{len(sic_fallback)} tickers bucketed from CURRENT SIC only (no filing header "
            f"ever carried one): {sic_fallback} — a disclosed point-in-time approximation."
        )

    drift, mismatch = _measure_bucket_drift(sic_histories, start, end)
    slot_counts, n_refused, n_no_bucket_slots = _measure_bucket_composition(
        close, noa_frame, bucket_frame, start, holding_days=126
    )
    if n_no_bucket_slots:
        warnings.append(
            f"{n_no_bucket_slots} ranked ticker-formation slots (h126 cadence) had an NOA "
            "value but no point-in-time bucket and were refused from ranking."
        )

    results = screen_cross_sectional_universe(
        CrossSectionalData(close=close, fundamental_signal=noa_frame),
        build_noa_neutral_family(bucket_frame),
        config,
        n_trials_override=NOA_NEUTRAL_DSR_N_TRIALS,
    )

    return NoaNeutralScreeningSummary(
        results=results,
        n_family_trials=NOA_NEUTRAL_N_TRIALS,
        n_dsr_trials=NOA_NEUTRAL_DSR_N_TRIALS,
        universe_size=universe_size,
        sample_size=len(sample),
        sample_seed=QUALITY_SAMPLE_SEED,
        missing_cik=missing_cik,
        failed_edgar_fetch=failed_fetch,
        missing_price_data=missing_price,
        tickers_without_noa=no_noa,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        formation_start=start,
        n_annual_headers_with_sic=sum(
            1 for h in sic_histories.values() for _, s in h.events if s is not None
        ),
        n_annual_headers_without_sic=sum(
            1 for h in sic_histories.values() for _, s in h.events if s is None
        ),
        n_header_fetch_failures=sum(
            h.n_header_fetch_failures for h in sic_histories.values()
        ),
        tickers_without_bucket=no_bucket,
        current_sic_fallback_tickers=sic_fallback,
        bucket_drift_tickers=drift,
        current_vs_history_mismatch_tickers=mismatch,
        bucket_slot_counts=slot_counts,
        n_min_bucket_refusals=n_refused,
        n_noa_without_bucket_slots=n_no_bucket_slots,
        noa_diagnostics=noa_diag,
        median_noa_value_age_days=_median_age(noa_ages, start),
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        warnings=warnings,
    )
