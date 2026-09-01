"""ASSET GROWTH / INVESTMENT EFFECT: one pre-declared cross-sectional equity
family testing whether firms with LOW year-over-year total-asset growth
outperform firms with HIGH total-asset growth, computed from SEC EDGAR XBRL
annual fundamentals — with the RAW and INDUSTRY-NEUTRAL conditionings
pre-declared TOGETHER in a single 12-spec grid rather than sequentially.

This module is the direct structural descendant of
cross_sectional_quality.py (same EDGAR fetch path, same point-in-time step
panel, same seeded sample, same harness) and of
cross_sectional_quality_neutral.py (same point-in-time SIC bucket panel,
same within-bucket centering). See section 4 for why the two conditionings
live in ONE family here, which is the one place this family deliberately
departs from how the NOA pair was built.

=======================================================================
1. THE SIGNAL AND ITS SOURCES
=======================================================================

    AG_t = (Assets_t - Assets_{t-1}) / Assets_{t-1}

the year-over-year percentage growth in TOTAL assets, one value per usable
consecutive fiscal-year pair, deflated by the lagged (year t-1) total-asset
balance — the same deflator convention both sibling quality factors use.

DIRECTION: LOW asset growth predicts HIGH returns. The family's signal is
therefore the NEGATED growth rate (direction -1.0), so the harness's
top-is-long convention lands the long leg on the low-growth (conservative
investment) side and the short leg on the high-growth (aggressive
investment) side, matching the source literature's documented sign.

CITATION STATUS — READ THIS BEFORE QUOTING ANY NUMBER BELOW. Every
bibliographic claim in this section was verified against a live-fetched
source during this build (2026-09-01); the exact verification status of
each, including two claims that came into the build as premises and did
NOT survive verification unchanged, is recorded in the pre-registration
document data/research_runs/asset_growth_PREREGISTRATION.txt and the
results document. This module states no empirical magnitude from any paper
as fact. The pattern this rule exists to prevent — a plausible-sounding
quotation reconstructed from memory — has bitten this project before.

 (a) PRIMARY. Cooper, Michael J., Huseyin Gulen & Michael J. Schill,
     "Asset Growth and the Cross-Section of Stock Returns", Journal of
     Finance 63(4), 2008, pp. 1609-1651, DOI
     10.1111/j.1540-6261.2008.01370.x — the paper that documents the
     total-asset-growth sort. VERIFIED in full (authors, title, journal,
     volume, issue, year, page range, DOI) against two independent
     records, Crossref and RePEc, which returned identical fields.

     Its abstract, fetched identically from both, states that "Asset
     growth rates are strong predictors of future abnormal returns" and
     — the clause that makes this family testable at all on an S&P 500
     universe — that "Asset growth retains its forecasting ability even
     on large capitalization stocks". Both are exact quotes from the
     published abstract.

     WHAT THE ABSTRACT DOES NOT CONTAIN: any number at all. It states no
     spread return, no sample period, no horizon. Secondary write-ups
     circulate several different magnitudes for this paper and they
     CONFLICT with one another; the published full text is paywalled and
     could not be fetched during this build. NO empirical magnitude is
     therefore attributed to CGS anywhere in this module. The one figure
     stated below (in (d)) is quoted from Hou/Xue/Zhang QUOTING CGS, and
     is labeled as such.

 (b) MECHANISM, two competing stories the sort cannot distinguish
     between and this family does not claim to: q-theory / rational
     investment (firms invest more when their discount rate is low, so
     heavy investment mechanically co-occurs with low subsequent expected
     returns), and behavioral overinvestment/extrapolation (investors
     over-extrapolate the growth of fast-expanding firms and overvalue
     them, with a later correction). A negative result here is evidence
     against neither story in general — only against the sort being
     tradeable on this universe in this window.

 (c) THE "TOTAL ASSETS, NOT CAPEX" REFINEMENT — and a correction to this
     family's own build brief. Cooper, Michael, Huseyin Gulen & Mihai
     Ion, "The use of asset growth in empirical asset pricing models",
     Journal of Financial Economics 151, article 103746, 2024 (working
     paper 2018; SSRN 3026534), VERIFIED via Crossref and RePEc.

     Its TOTAL-ASSETS-BEAT-CAPEX finding is verified, from the published
     abstract: factor models' "ability to price the cross-section of
     returns decreases significantly when the investment factor is
     constructed using traditional investment measures, or measures that
     also account for investment in intangibles."

     TWO CLAIMS IN THIS FAMILY'S BUILD BRIEF DID NOT SURVIVE
     VERIFICATION, and are recorded here rather than quietly dropped:
      * The brief dated it ~2018-2019 as a working paper. It is a 2024
        JFE article; the 2018 date is the working paper only.
      * The brief said its finding is "evidence favoring the behavioral
        half" of (b). THE PAPER EXPLICITLY DISCLAIMS THAT INFERENCE. Its
        own conclusion states that "factor models in themselves cannot
        help distinguish between behavioral and rational determinants of
        expected return variation". The strongest claim it actually makes
        is against q-theory as a SOLE explanation, and the mechanism its
        abstract advances is a financing-cost channel — "the superior
        performance of the asset growth factor seems to be attributable
        to its ability to capture aggregate shocks to equity financing
        costs" — which is not a mispricing story. Section (b) above
        therefore leaves the two mechanisms undecided, which is what the
        literature actually supports.

     Nothing in this module's construction depends on (c) either way.
     The decision it would have supported — measure TOTAL asset growth
     rather than a capex proxy — is made on independent grounds that need
     no working paper: total assets is what the PRIMARY source (a) sorts
     on, and it is the one line item this pipeline resolves for
     essentially every filer (section 3).

 (d) LINEAGE / CROWDING, and the strongest single piece of prior evidence
     against expecting much here. The same quantity is the investment leg
     of two canonical asset-pricing models, both VERIFIED against primary
     sources during this build:

      * Hou, Kewei, Chen Xue & Lu Zhang, "Replicating Anomalies", Review
        of Financial Studies 33(5), 2020, pp. 2019-2133 (NBER Working
        Paper 23394, 2017). Their investment factor I/A is defined, from
        the fetched NBER PDF, as "the annual change in total assets
        (Compustat annual item AT) divided by one-year-lagged total
        assets" — the SAME construction as this module's AG_t.
      * The Fama-French 5-factor CMA leg. From Ken French's own data
        library definitions page: "The investment ratio used to form
        portfolios in June of year t is the change in total assets from
        the fiscal year ending in year t-2 to the fiscal year ending in
        t-1, divided by t-2 total assets."

     HXZ'S REPLICATION RESULT IS MORE FRAGILE THAN "IT SURVIVES", and the
     precise reading matters for this family's prior. Under their
     stricter method (NYSE breakpoints, value-weighted returns,
     1967-2014, financials excluded), their Table 4 reports the
     high-minus-low I/A decile at -0.46% per month with t = -2.92. So it
     IS significant at the conventional 5% level — one of their
     survivors, not one of the 286 anomalies they find insignificant —
     but it falls BELOW the t >= 3 hurdle they themselves advocate. They
     also state directly that this is "lower in magnitude than -1.05%
     (t = -5.04) with value-weighted returns and -1.73% (t = -8.45) with
     equal-weighted returns reported by Cooper, Gulen, and Schill (2008)"
     — that quoted pair is HXZ characterizing CGS, the only CGS
     magnitude this module states, and it is stated at second hand
     deliberately. And its alpha against their own q-factor model is 0.07
     (t = 0.61), i.e. fully absorbed — though that is close to mechanical,
     since I/A IS the q-model's investment factor.

     Read honestly: the best large-scale independent replication of this
     anomaly finds it attenuated by more than half versus the original,
     below its own authors' preferred significance hurdle, and fully
     explained by a factor model that was built to contain it. That is
     the prior this family goes in with.

=======================================================================
2. CROWDING — STATED UP FRONT, NOT DISCOVERED LATER
=======================================================================

This is the most heavily-institutionalized factor this project has ever
tested, and that is a reason for LOWER prior expectations, not higher.
Unlike most prior candidates here, this signal is not merely "published"
— it is EMBEDDED AS A FACTOR in two of the standard models the academic
literature itself risk-adjusts against, and is consequently a named,
deliberately-harvested leg in a large amount of commercial systematic
equity product. Anything a commercial risk model can compute from a
balance sheet in one line, on the most liquid 500 names in the world, is
about as crowded as a public anomaly gets.

The crowding argument is not merely a priori here — it is corroborated by
the replication evidence in section 1(d). Hou/Xue/Zhang, testing on
1967-2014 with NYSE breakpoints and value weighting, already found the
I/A sort attenuated to t = -2.92 (below their own t >= 3 bar) and fully
absorbed by their q-factor model. THIS family tests a window
(2015-2026) that begins after even that sample ends, on a universe
restricted to exactly the large-cap segment where any crowding would bite
hardest, with a cross-section two orders of magnitude smaller.

The honest prior going in, written before results: a genuine tradeable
edge on 2015-2026 large-cap US is UNLIKELY, and the interesting outcomes
are (i) an honest negative, or (ii) a positive that turns out to be a
sector bet — the exact failure mode the sibling NOA family was caught in.
This family is built so that (ii) cannot be reported as a success by
accident (section 4).

=======================================================================
3. WHY THIS FAMILY'S DATA IS THE CLEANEST OF THE THREE XBRL FAMILIES
=======================================================================

Asset growth needs exactly ONE line item: us-gaap `Assets`. That matters
concretely, because the two sibling families' honest coverage holes both
came from their OTHER inputs:

 * CbOP needs revenue AND cost-of-goods, which financials simply do not
   tag — the measured 2026-08-28 run refused 53 of 168 priced tickers
   outright, dominated by banks and insurers, and 801 firm-years for
   missing COGS.
 * NOA needs cash, common equity, and four zero-able debt/interest items,
   and refused 201 firm-years for missing cash alone.

`Assets` was the single UNIVERSAL tag in this provider's own design probe
(ASSETS_TAGS is a one-element tuple, `("Assets",)`, annotated "14/14
probe — the one universal tag"), and the sibling run measured 2,629
resolved annual `Assets` observations at 100% first-tier resolution — no
fallback tier ever needed. So this family ranks a strictly LARGER,
less-selected cross-section than either sibling, and in particular does
NOT structurally exclude financials the way CbOP does. That is a genuine
methodological advantage and it is the reason this family can be run at
all on the sample the siblings already paid to fetch.

THE COST OF THAT SIMPLICITY, stated plainly: total assets is also the
line item most violently corrupted by entity discontinuity, and asset
GROWTH is the worst possible functional form for that corruption —
a growth rate is a ratio of exactly the two numbers a shell-to-operating-
company transition makes incomparable. The sibling family's independent
verification pass found real instances in THIS VERY SAMPLE: TechnipFMC
filed 2015/2016 total assets of $74,100 against $28.3B in FY2017, and
Linde filed $9.2M against $93.4B. As NOA inputs those produced absurd
values; as ASSET GROWTH inputs they would produce growth rates of roughly
+38,000,000% and +1,000,000%, which under any ranking whatsoever would
pin them to the short leg's extreme for a full year.

This family therefore treats ASSETS_SCALE_BREAK_RATIO (imported, not
re-derived, from cross_sectional_quality) as load-bearing rather than
incidental, and tests it directly. It is the single most important data
guard in this module.

WHAT THE GUARD DELIBERATELY DOES NOT REMOVE: genuine large M&A. The
sibling run measured CBOE's real Bats-merger year at an 11x asset ratio
and KEPT it. A 1,000%-asset-growth acquisition year is a real firm doing
a real thing, and the source literature's sort includes exactly such
firms — asset growth financed by acquisition is part of the documented
effect, not noise to be trimmed. Keeping it is the faithful choice; it
does mean the short leg can be concentrated in acquirers. The harness's
MAX_WEIGHT_MULTIPLE = 3.0 concentration cap bounds how much any one such
name can matter within its leg (see _apply_weight_cap), which is what
makes magnitude leg-weighting survivable on a variable this right-skewed
(asset growth is bounded below at -100% and unbounded above).

POINT-IN-TIME CONSTRUCTION is inherited wholesale and unchanged from
cross_sectional_quality.build_point_in_time_factor_frame: each value
becomes visible at the LATEST `filed` date among the XBRL observations
used to compute it (in practice the current year's 10-K submission date,
never the fiscal period end), values are originally-filed so restatements
never rewrite history, the step frame forward-fills from filing dates
only and refuses a value carried past FUNDAMENTAL_MAX_STALENESS_DAYS, and
formation-time look-ahead is structurally impossible because the frame
rides CrossSectionalData.fundamental_signal, which the harness slices to
rows <= the formation date.

=======================================================================
4. THE PRE-DECLARED GRID — AND THE ONE DESIGN DEPARTURE FROM NOA
=======================================================================

THE DEPARTURE, AND WHY. The sibling NOA family was built RAW, came back
positive, was diagnosed post-hoc as a sector-composition artifact, and
only then spawned a separately pre-declared industry-neutral family that
had to carry the raw family's 9 trials into its own DSR denominator (18)
to stay honest about the sequential search. That sequence was handled
correctly, but it was still a sequence: the confound test was designed
AFTER seeing the confounded result.

Asset growth has the same confound risk for the same structural reason —
sector composition differences in balance-sheet growth rates are large
and obvious (REITs and utilities grow assets differently from asset-light
software firms; capital-intensity IS an industry attribute) — and this
project already knows that. Pre-declaring the neutral conditioning only
after a raw positive would be re-running a known trap on purpose.

So BOTH conditionings are pre-declared here, in ONE grid, with ONE DSR
denominator covering the entire search:

    conditioning {raw, industry_neutral}      2
  x holding period {63, 126, 252} days        3
  x rank fraction {decile core, quintile}     2
  = 12 definitions, long_short throughout.

n_trials = 12, this family's own honest denominator — no carried trials
from any other family, because this family is NOT a follow-up to a
positive found here. It is a fresh hypothesis from an independent
literature, and its two conditionings were fixed together before any
number was computed.

The load-bearing consequence: a raw-conditioning positive CANNOT be
reported as this family's finding without its industry-neutral sibling,
computed in the same run under the same denominator, agreeing. The
sector-artifact check is not a follow-up study, it is half the grid.

INDUSTRY-NEUTRAL CENTERING IS THE BUCKET MEDIAN, not the mean, fixed in
advance for a stated reason: asset growth is severely right-skewed
(bounded below at -100%, unbounded above), so a bucket MEAN is dragged
around by whichever peer happened to close an acquisition that year,
which is precisely the observation that should NOT redefine what
"normal growth for this industry" means. The median is the robust center
for a skewed variable. This also directly implements the natural reading
of the neutral hypothesis — growth relative to the industry's TYPICAL
growth — and it is consistent with what the sibling neutral family
measured (median demeaning outranked mean demeaning across its grid).
Mean centering is NOT in this grid: it is not searched over, so it cannot
be selected post-hoc.

HOLDING PERIODS {63, 126, 252} and the exclusion of a 21-day hold are
inherited verbatim from cross_sectional_quality.py section 4: the ranking
variable refreshes ANNUALLY per firm (one 10-K a year), so a monthly hold
re-pays turnover on an almost entirely unchanged ranking, while the
cross-section still refreshes continuously through the year as staggered
fiscal calendars file. 252 is the source literature's own annual
rebalance.

long_universe_hedged IS ABSENT, following the sibling neutral family's
reasoning: hedging against the whole (sector-imbalanced) eligible
universe would reintroduce through the hedge leg exactly the
between-sector exposure the neutral conditioning removes from the
ranking, making the two halves of this grid non-comparable. The
conditioning axis replaces it as this family's second dimension.

MIN_BUCKET_SIZE = 3 is inherited from the sibling neutral family: a name
whose point-in-time industry bucket has fewer than 3 ranked members at a
formation is REFUSED rather than centered (a 1-member bucket centers to
exactly 0; a 2-member bucket ranks on nothing but within-pair order).
Refusals are measured and reported, never silent.

UNIVERSE: the IDENTICAL seeded 200-ticker sample as both sibling quality
families (build_quality_sample, seed 20260828, drawn from the
point-in-time S&P 500 union universe), gated per formation by the
harness's default was_member. Deliberately identical, for the same reason
the neutral NOA family kept it: so this family's result is about the same
cross-section whose sector composition has ALREADY been measured in
detail by the sibling verification pass, rather than a universe change
wearing a new family's clothes. The honest cost is the sibling's cost —
a few hundred ranked names at most, decile legs in the low tens against
the source literature's hundreds, and correspondingly noisy leg returns.
This family should rank MORE names than either sibling (section 3), and
the realized count is measured per run rather than assumed.

COSTS: DEFAULT_XS_COST_BPS (5 bps one-way), identical to every S&P 500
equity family here so Sharpes stay comparable; financing_bps_per_year
stays 0.0 — this project's standing DISCLOSED optimism about short
borrow, not an estimate (see cross_sectional.py's short-borrow section).

PASS/FAIL, fixed before results: this family is reported as a validated
edge ONLY if (i) the best spec's deflated Sharpe (DSR, n_trials=12)
clears 0.95, AND (ii) that spec's INDUSTRY-NEUTRAL counterpart at the
same holding period and rank fraction also clears a materially positive
Sharpe rather than collapsing. Anything else is an honest negative or an
honest artifact, and gets written up as such. Condition (ii) is what
makes the NOA failure mode unreportable here.

=======================================================================
5. PRODUCTION RUN — NOT YET RUN AT THE TIME THIS SECTION WAS WRITTEN
=======================================================================

THIS SECTION IS INTENTIONALLY EMPTY OF RESULTS. The code above and the
pre-registration document (data/research_runs/
asset_growth_PREREGISTRATION.txt) are committed BEFORE the family is run,
which is this project's two-file discipline: the hypothesis, the spec
grid, n_trials, the centering statistic and the pass/fail rule are all
locked in writing while the outcome is still unknown, so no post-hoc
choice can be presented as a pre-registered one.

The measured coverage, the 12 realized Sharpes and DSRs, and the verdict
are written into this section, and into
data/research_runs/asset_growth_<date>.txt, only after the run — in a
separate commit, on top of a pre-registration commit that cannot be
retro-fitted to whatever came out.
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
    LineItemExtraction,
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
    _annual_pairs,
    _is_entity_scale_break,
    _median_age,
    build_point_in_time_factor_frame,
    build_quality_sample,
    default_quality_config,
)
from app.services.research_lab.cross_sectional_quality_neutral import (
    MIN_BUCKET_SIZE,
    build_point_in_time_bucket_frame,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    was_member,
)

logger = logging.getLogger(__name__)

ASSET_GROWTH_CITATION = (
    "Cooper, Gulen & Schill, 'Asset Growth and the Cross-Section of Stock Returns' (Journal "
    "of Finance 63(4), 2008, pp. 1609-1651, doi:10.1111/j.1540-6261.2008.01370.x) — the "
    "total-asset-growth sort, whose abstract claims it 'retains its forecasting ability even "
    "on large capitalization stocks'; the same quantity is the investment leg of the "
    "Hou-Xue-Zhang q-factor model (I/A) and the Fama-French 5-factor model (CMA), and "
    "Hou/Xue/Zhang's 'Replicating Anomalies' (RFS 33(5), 2020) reports it materially "
    "attenuated (t = -2.92, below their own t >= 3 hurdle) under NYSE breakpoints and "
    "value weighting"
)


# --- factor construction -----------------------------------------------------


def compute_asset_growth_observations(
    extraction: LineItemExtraction,
) -> tuple[list[FactorObservation], FactorBuildDiagnostics]:
    """Cooper/Gulen/Schill year-over-year TOTAL asset growth, one value per
    usable consecutive fiscal-year pair:

        AG_t = (Assets_t - Assets_{t-1}) / Assets_{t-1}

    Returned UNNEGATED — the raw growth rate, so the panel reads as the
    economic quantity it is. The direction flip that makes low growth the
    long leg happens in the signal functions, exactly as the sibling NOA
    family flips there rather than in its builder.

    Refusals, all counted, and deliberately few — this factor needs only
    the `Assets` tag, which is the one universal line item in this
    provider (see module docstring section 3):

     * `non_positive_lagged_assets` — a zero, negative or non-finite
       deflator. There is no meaningful growth rate off a non-positive
       asset base.
     * `assets_entity_scale_break` — the year-over-year pair cannot be the
       same economic entity (see ASSETS_SCALE_BREAK_RATIO in
       cross_sectional_quality). THE load-bearing guard for this family:
       a growth rate is a ratio of precisely the two numbers a
       shell-to-operating-company transition makes incomparable, so an
       unguarded pair would emit a growth rate in the millions of percent
       and pin that name to the short leg's extreme for a year.
     * `non_finite_value` — belt and braces; the two guards above already
       exclude every route to a non-finite result.

    Note there is no missing-`Assets` refusal reason: `_annual_pairs` is
    built from the keys of the assets series itself, so a fiscal year with
    no resolved total-assets value simply never forms a pair. A multi-year
    filing gap likewise cannot masquerade as a one-year change — that is
    _annual_pairs' 250..480-day window doing its job."""
    items = extraction.items
    diagnostics = FactorBuildDiagnostics()
    out: list[FactorObservation] = []
    assets = items["assets"]

    for e_prev, e in _annual_pairs(list(assets.keys())):
        lagged_assets = assets[e_prev]
        total_assets = assets[e]
        if not np.isfinite(lagged_assets.value) or lagged_assets.value <= 0.0:
            diagnostics.n_refused["non_positive_lagged_assets"] += 1
            continue
        if _is_entity_scale_break(lagged_assets.value, total_assets.value):
            diagnostics.n_refused["assets_entity_scale_break"] += 1
            continue

        value = (total_assets.value - lagged_assets.value) / lagged_assets.value
        if not np.isfinite(value):
            diagnostics.n_refused["non_finite_value"] += 1
            continue
        diagnostics.n_observations += 1
        out.append(
            FactorObservation(
                end=e,
                value=float(value),
                available=max(lagged_assets.filed, total_assets.filed),
            )
        )

    return out, diagnostics


# --- the two pre-declared signals --------------------------------------------


def signal_low_asset_growth(history: CrossSectionalData) -> pd.Series:
    """RAW conditioning: the negated asset-growth rate at the formation
    date, so the harness's top decile is the LOW-growth (conservative
    investment) side and the bottom decile the HIGH-growth (aggressive)
    side — the source literature's documented direction.

    All the real work — formula, filing-date visibility, staleness — is
    already done in the panel this reads. This function only takes the last
    row of a history view the harness has already truncated to rows <= the
    formation date, which is the structural look-ahead guarantee. NaN cells
    refuse the ticker from ranking, the correct answer for "this company's
    asset growth is unobservable or stale here"."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_low_asset_growth requires CrossSectionalData.fundamental_signal; the spec "
            "must set requires_fundamental_signal=True and the caller must supply the frame."
        )
    row = frame.iloc[-1].astype(float)
    signal = -row
    return signal.where(np.isfinite(signal))


def signal_low_asset_growth_industry_neutral(
    history: CrossSectionalData,
    *,
    bucket_frame: pd.DataFrame,
    min_bucket_size: int = MIN_BUCKET_SIZE,
) -> pd.Series:
    """INDUSTRY-NEUTRAL conditioning: the negated deviation of a firm's
    asset growth from its own industry bucket's MEDIAN growth, computed
    cross-sectionally over THIS formation's eligible ranked names only.

        signal_i = -( AG_i(t) - median_{b(i)}(t) )

    so the top of the ranking is the firm growing its balance sheet least
    relative to its industry peers. The median (not the mean) is the
    pre-declared center — see module docstring section 4: asset growth is
    bounded below at -100% and unbounded above, so a bucket mean is
    dragged by whichever peer closed an acquisition that year, which is
    exactly the observation that should not redefine "normal growth for
    this industry".

    Conditioning on the ELIGIBLE cross-section is deliberate and
    load-bearing, inherited from the sibling neutral family: the harness
    hands this function a history view whose columns are already
    restricted to the formation date's point-in-time members, so bucket
    medians are computed among the names actually being ranked — never
    over departed members or unpriced names.

    The bucket row is read at the view's own last (formation) timestamp
    from a step frame built exclusively from filing dates <= each cell's
    date, so the industry classification used is the one publicly on file
    at formation — the same point-in-time contract as the growth value
    itself. A name with no bucket, or whose bucket has fewer than
    min_bucket_size ranked members at this formation, is refused (NaN),
    which excludes it from ranking per the SignalFn contract."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_low_asset_growth_industry_neutral requires CrossSectionalData."
            "fundamental_signal; the spec must set requires_fundamental_signal=True and the "
            "caller must supply the frame."
        )
    row = frame.iloc[-1].astype(float)
    formation_ts = frame.index[-1]
    buckets = bucket_frame.loc[formation_ts].reindex(row.index)

    valid = np.isfinite(row.to_numpy()) & buckets.notna().to_numpy()
    values = row[valid]
    if values.empty:
        return pd.Series(np.nan, index=row.index, dtype=float)
    labels = buckets[valid]
    grouped = values.groupby(labels)
    center = grouped.transform("median")
    sizes = grouped.transform("size")
    demeaned = (values - center).where(sizes >= min_bucket_size)
    return (-demeaned).reindex(row.index).astype(float)


# --- the pre-declared family -------------------------------------------------

ASSET_GROWTH_HOLDING_DAYS: tuple[int, ...] = QUALITY_HOLDING_DAYS  # (63, 126, 252)
ASSET_GROWTH_CONDITIONINGS: tuple[str, ...] = ("raw", "industry_neutral")
ASSET_GROWTH_RANK_FRACTIONS: tuple[tuple[str, float], ...] = (
    ("", QUALITY_RANK_FRACTION),  # deciles — the core sort
    ("_quintile", QUALITY_ROBUSTNESS_RANK_FRACTION),  # quintile robustness variant
)

# 2 conditionings x 3 holds x 2 rank fractions = 12, long_short throughout,
# ALL fixed before any backtest ran. See module docstring section 4 for why
# the conditioning axis is inside this family rather than a follow-up
# family, and why long_universe_hedged is absent.
ASSET_GROWTH_N_TRIALS = (
    len(ASSET_GROWTH_CONDITIONINGS)
    * len(ASSET_GROWTH_HOLDING_DAYS)
    * len(ASSET_GROWTH_RANK_FRACTIONS)
)

# The family_key every persisted row carries (see cross_sectional_persistence).
ASSET_GROWTH_FAMILY_KEY = "asset_growth"
ASSET_GROWTH_FAMILY = "asset_growth"


def build_asset_growth_family(bucket_frame: pd.DataFrame) -> list[CrossSectionalSpec]:
    """The 12 pre-declared specs, bound to a concrete point-in-time industry
    bucket panel.

    The GRID (conditionings x holds x rank fractions, and the count of 12)
    is fixed in the module constants above; the bucket frame is runtime
    DATA injected into the neutral specs' signal closures — the same
    relationship the sibling neutral family's specs have to their bucket
    panel — never a searched-over axis."""
    specs: list[CrossSectionalSpec] = []
    for conditioning in ASSET_GROWTH_CONDITIONINGS:
        if conditioning == "raw":
            signal_fn = signal_low_asset_growth
            id_prefix = "ag_low"
        else:
            signal_fn = partial(
                signal_low_asset_growth_industry_neutral, bucket_frame=bucket_frame
            )
            id_prefix = "ag_neutral"
        for holding in ASSET_GROWTH_HOLDING_DAYS:
            for suffix, rank_fraction in ASSET_GROWTH_RANK_FRACTIONS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"{id_prefix}_ls_h{holding}{suffix}",
                        family=ASSET_GROWTH_FAMILY,
                        citation=ASSET_GROWTH_CITATION,
                        signal_fn=signal_fn,
                        lookback_days=QUALITY_SIGNAL_LOOKBACK_ROWS,
                        holding_days=holding,
                        portfolio="long_short",
                        rank_fraction=rank_fraction,
                        requires_fundamental_signal=True,
                    )
                )

    assert len(specs) == ASSET_GROWTH_N_TRIALS == 12, (
        f"asset growth built {len(specs)} definitions; the declared grid implies "
        f"{ASSET_GROWTH_N_TRIALS} and the build pre-declared exactly 12. All three must "
        "agree — a drift silently changes this family's DSR denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.requires_fundamental_signal for s in specs)
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.leg_weighting == "magnitude" for s in specs)
    assert all(s.cohort_formation_days is None for s in specs)
    assert all(s.holding_days in ASSET_GROWTH_HOLDING_DAYS for s in specs)
    assert 21 not in ASSET_GROWTH_HOLDING_DAYS, (
        "monthly holds are excluded up front: the per-firm ranking variable refreshes once a "
        "year, so a 21-day hold re-pays turnover on an almost entirely unchanged ranking."
    )
    return specs


# --- production entry point --------------------------------------------------


@dataclass
class AssetGrowthScreeningSummary:
    """run_asset_growth_screening's full result: the screening output plus
    every measured coverage number a reader needs to interpret it. Typed
    fields, not docstring paragraphs — the discipline the sibling quality
    summaries state. A result read without these is not interpretable."""

    results: list[CrossSectionalScreeningResult]
    n_trials: int
    # Universe accounting — same fields, same meaning as the siblings.
    universe_size: int
    sample_size: int
    sample_seed: int
    missing_cik: list[str]
    failed_edgar_fetch: list[str]
    missing_price_data: list[str]
    tickers_without_asset_growth: list[str]
    panel_start: date | None
    panel_end: date | None
    formation_start: date
    # Realized `Assets` tag coverage across the sample: "t{tier}:{tag}" ->
    # count of resolved fiscal-year observations. Expected to be 100%
    # first-tier (see module docstring section 3) — reported so that
    # expectation is MEASURED rather than assumed.
    assets_tier_usage: dict[str, int] = field(default_factory=dict)
    diagnostics: FactorBuildDiagnostics = field(default_factory=FactorBuildDiagnostics)
    # The realized range of the factor itself. The single most useful
    # sanity number for THIS family: an unguarded entity discontinuity
    # shows up here as a growth rate in the thousands (see section 3),
    # so a reader can confirm the scale-break guard did its job without
    # re-running anything.
    min_asset_growth: float = float("nan")
    max_asset_growth: float = float("nan")
    median_value_age_days: float = float("nan")
    # Industry-bucket accounting for the neutral half of the grid.
    tickers_without_bucket: list[str] = field(default_factory=list)
    current_sic_fallback_tickers: list[str] = field(default_factory=list)
    bucket_slot_counts: dict[str, int] = field(default_factory=dict)
    n_min_bucket_refusals: int = 0
    n_growth_without_bucket_slots: int = 0
    cost_bps: float = QUALITY_COST_BPS
    financing_bps_per_year: float = QUALITY_FINANCING_BPS_PER_YEAR
    warnings: list[str] = field(default_factory=list)


def _measure_bucket_composition(
    close: pd.DataFrame,
    factor_frame: pd.DataFrame,
    bucket_frame: pd.DataFrame,
    formation_start: date,
    holding_days: int,
) -> tuple[dict[str, int], int, int]:
    """(bucket -> ranked ticker-formation slots, slots refused by
    MIN_BUCKET_SIZE, slots with a growth value but no bucket), measured on
    the given cadence's formation dates re-derived exactly as the harness
    derives them (first row at/after formation_start, then every
    holding_days rows) under the same eligibility gate (point-in-time
    member + finite price). Measurement only — the backtests never read
    this."""
    positions = np.flatnonzero(close.index.date >= formation_start)  # type: ignore[attr-defined]
    if len(positions) == 0:
        return {}, 0, 0
    slot_counts: Counter = Counter()
    n_refused = 0
    n_no_bucket = 0
    for i in range(int(positions[0]), len(close.index) - 1, holding_days):
        formation_day = close.index[i].date()
        prices = close.iloc[i]
        factor_row = factor_frame.iloc[i]
        bucket_row = bucket_frame.iloc[i]
        eligible = [
            t for t in close.columns if was_member(t, formation_day) and np.isfinite(prices[t])
        ]
        values = factor_row[eligible]
        has_value = values[np.isfinite(values.to_numpy())]
        buckets = bucket_row[has_value.index]
        n_no_bucket += int(buckets.isna().sum())
        labeled = buckets.dropna()
        sizes = labeled.groupby(labeled).transform("size")
        for bucket, size in zip(labeled, sizes):
            if size >= MIN_BUCKET_SIZE:
                slot_counts[str(bucket)] += 1
            else:
                n_refused += 1
    return dict(slot_counts), n_refused, n_no_bucket


def _factor_range(observations: dict[str, list[FactorObservation]]) -> tuple[float, float]:
    values = [o.value for obs in observations.values() for o in obs]
    if not values:
        return float("nan"), float("nan")
    return float(min(values)), float(max(values))


def run_asset_growth_screening(
    start: date = MEMBERSHIP_DATA_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    edgar: EdgarXbrlProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> AssetGrowthScreeningSummary:
    """THE production entry point: one EDGAR fetch, one SIC-history fetch,
    one price fetch, one 12-spec pre-declared family screened under its own
    12-trial DSR denominator.

    Deliberately the sibling quality families' exact pipeline (same seeded
    sample, same extraction, same point-in-time step panel and bucket
    panel, same price panel and membership gate) with one factor swapped
    in, so any difference in result is a difference in the FACTOR, not in
    the machinery around it."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Asset-growth screening start {start.isoformat()} predates point-in-time "
            f"membership coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before "
            "that date would silently see an empty universe."
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

    sic_histories: dict[str, SicHistory]
    sic_histories, _, sic_failed = edgar.fetch_sic_history_for_tickers(
        [t for t in sample if t not in missing_cik]
    )
    if sic_failed:
        warnings.append(f"{len(sic_failed)} tickers produced no SIC history (fetch failures).")

    padded_start = start - timedelta(days=QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    close, missing_price = provider.get_price_history(sample, padded_start, end)
    if close.empty:
        return AssetGrowthScreeningSummary(
            results=[],
            n_trials=ASSET_GROWTH_N_TRIALS,
            universe_size=universe_size,
            sample_size=len(sample),
            sample_seed=QUALITY_SAMPLE_SEED,
            missing_cik=missing_cik,
            failed_edgar_fetch=failed_fetch,
            missing_price_data=missing_price,
            tickers_without_asset_growth=[],
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

    observations: dict[str, list[FactorObservation]] = {}
    diagnostics = FactorBuildDiagnostics()
    assets_tiers: Counter = Counter()
    for ticker, extraction in extractions.items():
        obs, diag = compute_asset_growth_observations(extraction)
        observations[ticker] = obs
        diagnostics.merge(diag)
        assets_tiers.update(extraction.tier_usage.get("assets", Counter()))

    factor_frame, ages, unusable = build_point_in_time_factor_frame(close, observations)
    if unusable:
        warnings.append(
            f"{len(unusable)} of {len(close.columns)} priced tickers produced no usable "
            "asset-growth observation (no CIK, failed fetch, or refused by the formula's own "
            "requirements — see diagnostics) and are never ranked."
        )

    bucket_frame, no_bucket, sic_fallback = build_point_in_time_bucket_frame(close, sic_histories)
    if sic_fallback:
        warnings.append(
            f"{len(sic_fallback)} tickers bucketed from CURRENT SIC only (no filing header ever "
            f"carried one): {sic_fallback} — a disclosed point-in-time approximation."
        )

    slot_counts, n_refused, n_no_bucket_slots = _measure_bucket_composition(
        close, factor_frame, bucket_frame, start, holding_days=126
    )
    if n_no_bucket_slots:
        warnings.append(
            f"{n_no_bucket_slots} ranked ticker-formation slots (h126 cadence) had an "
            "asset-growth value but no point-in-time industry bucket, and are refused from "
            "ranking in the neutral half of the grid."
        )

    results = screen_cross_sectional_universe(
        CrossSectionalData(close=close, fundamental_signal=factor_frame),
        build_asset_growth_family(bucket_frame),
        config,
    )

    min_growth, max_growth = _factor_range(observations)
    return AssetGrowthScreeningSummary(
        results=results,
        n_trials=ASSET_GROWTH_N_TRIALS,
        universe_size=universe_size,
        sample_size=len(sample),
        sample_seed=QUALITY_SAMPLE_SEED,
        missing_cik=missing_cik,
        failed_edgar_fetch=failed_fetch,
        missing_price_data=missing_price,
        tickers_without_asset_growth=unusable,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        formation_start=start,
        assets_tier_usage=dict(assets_tiers),
        diagnostics=diagnostics,
        min_asset_growth=min_growth,
        max_asset_growth=max_growth,
        median_value_age_days=_median_age(ages, start),
        tickers_without_bucket=no_bucket,
        current_sic_fallback_tickers=sic_fallback,
        bucket_slot_counts=slot_counts,
        n_min_bucket_refusals=n_refused,
        n_growth_without_bucket_slots=n_no_bucket_slots,
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        warnings=warnings,
    )
