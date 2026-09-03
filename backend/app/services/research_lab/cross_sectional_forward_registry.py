"""HOW A FORWARD-VALIDATION REGISTRATION REFERENCES A CROSS-SECTIONAL SPEC.

THE DESIGN QUESTION THIS FILE ANSWERS. A pairs/momentum registration stores
its whole configuration in six scalar columns (ticker_a, ticker_b,
fit_window_days, entry_z, exit_z, cost_bps) because that IS the whole
strategy — the fit function and the return function are picked by
strategy_name out of strategy_registry, and nothing else varies. A
cross-sectional spec cannot work that way: its identity includes a SIGNAL
FUNCTION (a closure over a lookback, e.g. `lambda h: signal_crypto_btc_beta(
h, lookback_days=180)`), a universe rule that is itself computed from live
data (crypto's point-in-time liquidity gate), a leg-weighting scheme with
its own external basis frame, and a whole CrossSectionalConfig of market
assumptions. None of that is expressible as columns, and serializing it
would be worse than useless — a pickled closure or a re-typed copy of the
parameters is a SECOND declaration of the strategy that can drift from the
family's own, which is the one thing a 126-day forward clock must never
tolerate.

SO: A REGISTRATION STORES A REFERENCE, NOT A COPY. Two strings —
family_key and pattern_id — plus a FINGERPRINT of what those resolved to at
registration time. At every tick the spec is looked up live, by pattern_id,
in the family's OWN already-built spec registry (build_crypto_family() and
friends), so the forward run always executes the same objects the backtest
executed. There is exactly one declaration of the strategy and it lives
where it always did.

WHAT THE FINGERPRINT IS FOR, and why it is not redundant with the
reference. A reference alone has a failure mode the columns-based path does
not: someone edits the family later. Retuning a lookback, changing
CRYPTO_COST_BPS, adding a spec — all legitimate research actions — would
silently change what an in-flight registration is ticking, and its
accumulated track record would then be a blend of two different strategies
with nothing recording that it happened. So registration snapshots a hash
of the spec's identity fields and of the config's market assumptions, and
every tick re-derives and compares them. A mismatch does not "helpfully"
carry on: it parks the registration in status "spec_drift" and stops
ticking it, because a corrupted track record is worse than a stopped one.

The snapshot is also stored in full (spec_snapshot_json /
config_snapshot_json) so the row is human-auditable without importing
anything — but the snapshot is EVIDENCE, never the source of truth. Ticking
always reads the family.

WHAT AN ADAPTER MUST PROVIDE, and why build_live_panel is a callable rather
than data: the universe/eligibility rule of a cross-sectional family is not
a static list, it is a computation over live data (crypto's trailing
dollar-volume and stale-print gate, an equity family's point-in-time index
membership). It has to be recomputed from real data up to and including
today on every tick, which is exactly what the family's own production
entry point already does — so the adapter's job is to call the family's own
functions in the family's own order, never to reimplement the panel.

This mirrors strategy_registry.StrategyAdapter exactly, and for the same
stated reason: a runner that loads rows generically (by status, not by
family) must not hardcode which family a row belongs to.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app import dependencies
from app.services.market_data.edgar_filing_text_provider import EdgarFilingTextProvider
from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.finra_short_interest_provider import (
    FinraShortInterestFetchError,
    FinraShortInterestProvider,
)
from app.services.market_data.sec_shares_outstanding_provider import (
    SecSharesFetchError,
    SecSharesOutstandingProvider,
    build_point_in_time_share_count_frame,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    MembershipFn,
)
from app.services.research_lab.cross_sectional_buyback import SHARES_MAX_STALENESS_DAYS
from app.services.research_lab.cross_sectional_crypto import (
    CRYPTO_LIQUIDITY_WINDOW_DAYS,
    CRYPTO_MAX_STALE_FRACTION,
    CRYPTO_MIN_DOLLAR_VOLUME,
    CRYPTO_N_TRIALS,
    build_crypto_family,
    build_crypto_price_panel,
    build_eligibility,
    build_inverse_vol_basis,
    default_crypto_config,
    liquidity_membership,
)
from app.services.research_lab.cross_sectional_lazy_prices import (
    LAZY_PRICES_FILING_WARMUP_DAYS,
    LAZY_PRICES_FORMS,
    LAZY_PRICES_MAX_STALENESS_DAYS,
    LAZY_PRICES_N_TRIALS,
    build_similarity_observations,
    build_similarity_panel,
    default_lazy_prices_config,
)
from app.services.research_lab.cross_sectional_lazy_prices import (
    build_inverse_vol_basis as build_lazy_prices_inverse_vol_basis,
)
from app.services.research_lab.cross_sectional_lazy_prices import (
    specs_for_panel as lazy_prices_specs_for_panel,
)
from app.services.research_lab.cross_sectional_quality import (
    CBOP_FAMILY,
    CBOP_N_TRIALS,
    FUNDAMENTAL_MAX_STALENESS_DAYS,
    QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    QUALITY_SAMPLE_SEED,
    QUALITY_SAMPLE_SIZE,
    FactorObservation,
    build_point_in_time_factor_frame,
    build_quality_sample,
    compute_cbop_observations,
    compute_noa_observations,
    default_quality_config,
)
from app.services.research_lab.cross_sectional_quality_neutral import (
    MIN_BUCKET_SIZE,
    NOA_NEUTRAL_DSR_N_TRIALS,
    build_noa_neutral_family,
    build_point_in_time_bucket_frame,
)
from app.services.research_lab.cross_sectional_short_interest import (
    SHORT_INTEREST_CYCLE_FETCH_START,
    SHORT_INTEREST_FORMATION_START,
    SHORT_INTEREST_MAX_STALENESS_DAYS,
    SHORT_INTEREST_N_TRIALS,
    SHORT_INTEREST_PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    build_short_interest_panels,
    default_short_interest_config,
    specs_for_normalizer,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_AS_OF,
    MEMBERSHIP_DATA_START,
    get_universe_over,
    was_member,
)
from app.services.research_lab.spread_estimator import build_edge_half_spread_frame


class CrossSectionalUniverseDriftError(RuntimeError):
    """The candidate universe a live registration is ticking is no longer the
    one it was registered against.

    DELIBERATELY NOT a CrossSectionalPanelUnavailableError. That one means "no
    data today, try again in half an hour" and is retried forever in silence,
    which is right for an outage and wrong for this: a re-drawn universe is
    permanent, no retry can fix it, and the correct response is a human
    deciding whether to re-register. Raised rather than tolerated for the
    reason this module's docstring gives about spec drift — a track record
    that is a blend of two different strategies is worse than a stopped one —
    and raised rather than PARKED because unlike spec/config drift this is not
    something a registration row can see: the row stores no universe, so the
    park path (which compares against the row's own snapshot) has nothing to
    compare. The tick fails loudly in the log instead."""


class CrossSectionalPanelUnavailableError(RuntimeError):
    """The family's live price panel could not be built this tick (no data
    resolved, provider error). A transient condition: the tick logs it and
    returns, leaving the registration exactly as it was, so the next tick
    retries. Never a status change — a data outage is not a research
    finding about the strategy."""


class UnknownCrossSectionalFamilyError(ValueError):
    """No adapter registered under this family_key."""


class UnknownCrossSectionalSpecError(ValueError):
    """No spec with this pattern_id in the named family's own registry.
    Raised rather than falling back to anything: a pattern_id that does not
    resolve means the registration is referring to a strategy that does not
    exist, and inventing one would be the exact config-duplication this
    module is built to prevent."""


@dataclass(frozen=True)
class CrossSectionalLivePanel:
    """A family's real data up to and including today, plus the membership
    function that decides eligibility on it. Exactly the two things
    run_cross_sectional_backtest is given in a backtest — built by the
    family's own production code path, not by this module."""

    data: CrossSectionalData
    membership_fn: MembershipFn
    n_tickers: int
    last_row_date: date


@dataclass(frozen=True)
class CrossSectionalFamilyAdapter:
    """Everything the cross-sectional forward-validation runner needs to
    tick a row of any family without knowing which family it is."""

    family_key: str
    # The module a reader should open to see this family declared, stored
    # on every registration so the row names its own source of truth.
    module_path: str
    # The family's eligibility rule, in words, snapshotted onto the
    # registration. A registration must record WHAT UNIVERSE it is trading,
    # and for a data-driven gate the rule is the only stable statement of
    # it (the eligible set itself changes every day, by design).
    universe_rule: str
    # The family's own pre-declared DSR denominator — recorded so the
    # multiple-comparisons context that a forward registration exists to
    # move past is never lost from the row.
    n_trials: int
    build_specs: Callable[[], list[CrossSectionalSpec]]
    build_config: Callable[[], CrossSectionalConfig]
    build_live_panel: Callable[[date], CrossSectionalLivePanel]


_registry: dict[str, CrossSectionalFamilyAdapter] = {}


def register_family(adapter: CrossSectionalFamilyAdapter) -> None:
    _registry[adapter.family_key] = adapter


def get_family_adapter(family_key: str) -> CrossSectionalFamilyAdapter:
    try:
        return _registry[family_key]
    except KeyError:
        raise UnknownCrossSectionalFamilyError(
            f"Unknown cross-sectional family_key: {family_key!r}. Known: {sorted(_registry)}"
        ) from None


def registered_family_keys() -> list[str]:
    return sorted(_registry)


def resolve_spec(family_key: str, pattern_id: str) -> tuple[CrossSectionalFamilyAdapter, CrossSectionalSpec]:
    """THE lookup: (family, pattern_id) -> the family's own spec object.

    This is the function that makes "reference, not copy" real. It builds
    the family's spec list with the family's own builder and picks the one
    whose pattern_id matches — so a registration's stored strings resolve to
    the identical CrossSectionalSpec (identical signal closure, identical
    lookback, hold, rank fraction and leg weighting) that
    screen_cross_sectional_universe screened."""
    adapter = get_family_adapter(family_key)
    for spec in adapter.build_specs():
        if spec.pattern_id == pattern_id:
            return adapter, spec
    known = sorted(s.pattern_id for s in adapter.build_specs())
    raise UnknownCrossSectionalSpecError(
        f"Family {family_key!r} has no spec with pattern_id {pattern_id!r}. Known pattern_ids: {known}"
    )


# --- fingerprints ------------------------------------------------------------


def spec_identity(spec: CrossSectionalSpec) -> dict:
    """The spec fields that define WHAT STRATEGY THIS IS. signal_fn is
    deliberately absent — a function object has no stable serialization, and
    pattern_id (which the whole family asserts is unique) is what names it.
    citation is absent too: it is documentation, and rewording a citation
    must not read as the strategy having changed."""
    return {
        "pattern_id": spec.pattern_id,
        "family": spec.family,
        "lookback_days": spec.lookback_days,
        "holding_days": spec.holding_days,
        "portfolio": spec.portfolio,
        "rank_fraction": spec.rank_fraction,
        "leg_weighting": spec.leg_weighting,
        "cohort_formation_days": spec.cohort_formation_days,
        "requires_open": spec.requires_open,
        "requires_volume": spec.requires_volume,
        "requires_market_cap": spec.requires_market_cap,
        "requires_price_only_close": spec.requires_price_only_close,
        "requires_shares_outstanding": spec.requires_shares_outstanding,
    }


def config_identity(config: CrossSectionalConfig) -> dict:
    """The config fields that define WHAT MARKET the strategy trades in.

    formation_start is deliberately excluded: it bounds the first formation
    of a BACKTEST and has no meaning forward (a forward registration's first
    formation is the day it was registered), so a family retuning it must
    not read as drift here."""
    return {
        "cost_bps": config.cost_bps,
        "min_names_per_leg": config.min_names_per_leg,
        "financing_bps_per_year": config.financing_bps_per_year,
        "periods_per_year": config.periods_per_year,
        "impute_delisting_returns": config.impute_delisting_returns,
        "imputed_delisting_return": config.imputed_delisting_return,
    }


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def spec_fingerprint(spec: CrossSectionalSpec) -> str:
    return _hash(spec_identity(spec))


def config_fingerprint(config: CrossSectionalConfig) -> str:
    return _hash(config_identity(config))


# --- the Crypto family adapter ----------------------------------------------

CRYPTO_FAMILY_KEY = "cross_sectional_crypto"

CRYPTO_UNIVERSE_RULE = (
    "Point-in-time LIQUIDITY gate, not a fixed basket (cross_sectional_crypto.build_eligibility): a "
    f"coin is eligible on a formation date iff its trailing {CRYPTO_LIQUIDITY_WINDOW_DAYS}-day median "
    f"daily dollar volume is >= ${CRYPTO_MIN_DOLLAR_VOLUME:,.0f} AND its trailing stale-print fraction "
    f"(share of days whose return is exactly zero) is <= {CRYPTO_MAX_STALE_FRACTION:.0%} AND it has a "
    "price on the date itself. Both rolling statistics are .shift(1)ed, so the gate reads only strictly "
    "prior rows and can no more see the future than a signal can. Candidate list: "
    "cross_sectional_crypto.CRYPTO_UNIVERSE minus CRYPTO_EXCLUDED (stablecoins and broken/mis-mapped "
    "feeds, excluded ex ante). The candidate list deliberately INCLUDES coins that died or migrated "
    "(LUNA1, MATIC, RNDR, FTM, GALA, FTT), so a coin leaves the cross-section on the real date its "
    "market did, not on the date a 2026 author noticed."
)


def build_crypto_live_panel(end: date) -> CrossSectionalLivePanel:
    """The Crypto family's live panel, built by calling that family's OWN
    functions in that family's OWN order — this is run_crypto_screening's
    data-preparation block, and nothing here computes anything the family
    does not already compute for its backtests.

    Price history always starts at CRYPTO_PRICE_HISTORY_START (the default
    of build_crypto_price_panel) rather than at some shorter window: the
    eligibility gate needs 90 trailing rows, the inverse-vol basis needs 90,
    and the spec's declared lookback is 730. Fetching less would change what
    a live formation sees relative to what a backtested one saw."""
    close, volume, _missing = build_crypto_price_panel(dependencies.provider, end)
    if close.empty:
        raise CrossSectionalPanelUnavailableError(
            "No crypto price data resolved — the live panel is empty, so nothing can be formed or "
            "realized this tick."
        )
    eligibility = build_eligibility(close, volume)
    membership_fn = liquidity_membership(eligibility)
    basis = build_inverse_vol_basis(close)
    data = CrossSectionalData(close=close, leg_weight_basis=basis)
    return CrossSectionalLivePanel(
        data=data,
        membership_fn=membership_fn,
        n_tickers=len(close.columns),
        last_row_date=close.index[-1].date(),
    )


# --- the two SEC-fundamentals QUALITY family adapters ------------------------
#
# Both families rank the SAME point-in-time S&P 500 sample on an annual
# fundamental computed from SEC EDGAR XBRL filings, so they share this
# section's helpers exactly as run_quality_screening and
# run_noa_neutral_screening share cross_sectional_quality's pipeline. Three
# things about ticking them forward are NOT true of the Crypto family and
# each is handled explicitly below, because each is a way a live track
# record could silently stop being the strategy that was registered.
#
# 1. THE CANDIDATE SAMPLE MUST NOT BE RE-DRAWN MID-FLIGHT. Both families'
#    candidate pool is a SEEDED RANDOM SAMPLE of QUALITY_SAMPLE_SIZE names
#    drawn from the point-in-time membership UNION over a window
#    (build_quality_sample -> get_universe_over). random.Random(seed).sample
#    is a function of the WHOLE population, not a stable per-ticker hash: add
#    one name to the union and the drawn 200 are a substantially different
#    200. That matters here and nowhere else in this file, because
#    MembershipRefreshRunner is live in main.py's lifespan and extends
#    membership coverage forward in process, so a naive end=today would
#    re-draw the universe underneath an in-flight registration the first time
#    the index changed — an abrupt whole-book replacement, charged as 100%
#    turnover, blending two different strategies into one track record, and
#    INVISIBLE to the spec/config drift check (a universe is not part of
#    spec_identity or config_identity, and cannot be — it is data).
#    So the SAMPLE window's end is pinned to MEMBERSHIP_DATA_AS_OF, the
#    vendored data's own end-of-coverage constant. This is not a second
#    declaration of anything: get_universe_over already CLAMPS its end to
#    membership_coverage_end(), and MembershipExtension is documented and
#    validated as purely additive after MEMBERSHIP_DATA_AS_OF — so today the
#    pinned call returns the identical 768-name union and identical 200-name
#    sample the families' own production runs used (verified, and asserted in
#    tests/test_cross_sectional_forward_validation.py). The pin only bites in
#    the future, and only in the direction of keeping the registration on the
#    universe it was registered against. The PRICE window's end stays the
#    real tick date — that is the live half, and it must move.
#    AND THE PIN IS BACKED BY A FINGERPRINT, because pinning the window still
#    reads MEMBERSHIP_DATA_AS_OF as a variable: a re-vendoring of the literals
#    moves that constant forward by design and would re-draw the sample through
#    the pin. QUALITY_LIVE_SAMPLE_FINGERPRINT below is the literal the pin
#    cannot move, checked on every build; see it for why a stop is the right
#    outcome there. (earliest_overrides, considered and measured, is NOT a path
#    to this: get_universe_over is computed from _BASE_UNIVERSE and the event
#    list, and never reads the per-ticker intervals that overrides adjust — so
#    an override can change the was_member GATE but cannot add a name to the
#    union or move the drawn sample.)
#
# 2. THE FUNDAMENTALS CACHE MUST NOT FREEZE. EdgarXbrlProvider disk-caches
#    each company's companyfacts document forever by default, which is right
#    for a reproducible backtest and wrong for a live panel: the document
#    GROWS with each new 10-K, and a frozen copy would hold every firm's
#    factor value at its registration-day vintage until
#    FUNDAMENTAL_MAX_STALENESS_DAYS retired it and the name fell out of the
#    ranked cross-section entirely. The live provider is therefore
#    constructed with max_cache_age_days (see that parameter's own docstring
#    for why only the two MUTABLE caches are bounded).
#
# 3. ONE PANEL PER `end`, NOT ONE PER TICK. The runner's pre-check keeps a
#    family pending for the whole UTC day after its one real new row is
#    processed (last_processed_date is then YESTERDAY, which is still < today
#    — the panel's newest possible row is always the previous session's,
#    because yfinance's `end` is exclusive). At the 30-minute cadence that is
#    ~47 further calls to build_live_panel per day that can only return what
#    the first one returned, each a ~200-ticker multi-year download plus the
#    whole EDGAR pipeline. The memo below therefore holds ONE built panel per
#    family, keyed on the `end` it was built for, so a UTC-day rollover
#    always forces a rebuild. Its one cost, stated plainly: a bar published
#    upstream LATER in the same UTC day is not seen until the next day. That
#    delays a realization, it never loses one — rows_to_process steps onto
#    every unprocessed row whenever it does arrive.

QUALITY_CBOP_FAMILY_KEY = "quality_cbop"
QUALITY_NOA_NEUTRAL_FAMILY_KEY = "quality_noa_industry_neutral"

# How long the live path may serve a cached companyfacts document. One day:
# these are ANNUAL fundamentals whose panel is a step series, so a day of
# latency on a 10-K cannot change a formation that has not happened yet,
# while anything much longer starts eating into the staleness budget of
# point 2 above.
QUALITY_LIVE_EDGAR_MAX_CACHE_AGE_DAYS = 1

_QUALITY_SAMPLE_RULE = (
    "Candidate pool: a SEEDED RANDOM SAMPLE of "
    f"{QUALITY_SAMPLE_SIZE} tickers (seed {QUALITY_SAMPLE_SEED}, both fixed in code before any "
    "result was computed) drawn by cross_sectional_quality.build_quality_sample from the "
    "point-in-time S&P 500 membership UNION over "
    f"[{MEMBERSHIP_DATA_START.isoformat()}, the vendored coverage end] — 768 names, of which 200 "
    "are drawn. The cap is an SEC fair-access cost, not a research choice, and it costs a small "
    "cross-section (see cross_sectional_quality.py section 3). The sample window's END is PINNED to "
    "sp500_membership_history.MEMBERSHIP_DATA_AS_OF rather than following the tick date, because a "
    "seeded sample is a function of the whole population and a live membership refresh would "
    "otherwise re-draw the entire candidate universe underneath an in-flight registration. "
    "Eligibility on a formation date is the harness's own S&P 500 gate, exactly as when "
    "screen_cross_sectional_universe is called with membership_fn=None: "
    "sp500_membership_history.was_member(ticker, formation date) AND a finite close on that date. "
    "Two measured coverage holes stack on top of it, both disproportionately removing index "
    "LEAVERS (i.e. the short leg's natural candidates): departed members whose symbols died resolve "
    "no CIK in SEC's current-day ticker map, and the same names largely resolve no yfinance price "
    "history."
)

QUALITY_CBOP_UNIVERSE_RULE = (
    _QUALITY_SAMPLE_RULE + " A name is RANKED only if it also has a non-NaN cash-based operating "
    "profitability value in the point-in-time step panel "
    "(cross_sectional_quality.build_point_in_time_factor_frame): each value becomes visible on the "
    "LATEST XBRL 'filed' date among the observations used to compute it (in practice that fiscal "
    "year's 10-K submission date), is forward-filled from that date only — never interpolated, "
    f"never backfilled — and is refused once carried more than {FUNDAMENTAL_MAX_STALENESS_DAYS} "
    "calendar days. Financial firms have no COGS-shaped XBRL tags, so CbOP refuses them and they "
    "never rank in this family at all."
)

QUALITY_NOA_NEUTRAL_UNIVERSE_RULE = (
    _QUALITY_SAMPLE_RULE + " A name is RANKED only if it has BOTH a non-NaN net-operating-assets "
    "value in the point-in-time step panel (visible from the latest XBRL 'filed' date used, "
    f"forward-filled only, refused beyond {FUNDAMENTAL_MAX_STALENESS_DAYS} calendar days) AND a "
    "point-in-time industry bucket. The bucket comes from the SIC code recorded in each 10-K's own "
    "archived SGML header at dissemination time, forward-filled as a step series keyed on real "
    "filing dates — never today's submissions-API SIC projected backwards (measured in-sample: IRM "
    "read 4220 through its 2015-02-27 filing and 6798 only from 2016-02-26, so a current-SIC gate "
    "would have mis-bucketed it for a year of formations). Buckets are "
    "cross_sectional_quality_neutral.sic_to_bucket's frozen coarse 8-way partition, and a name "
    f"whose bucket holds fewer than {MIN_BUCKET_SIZE} ranked members at that formation is refused "
    "rather than demeaned against a center that would be pure placement noise."
)


@dataclass(frozen=True)
class _QualityLiveBuild:
    """One family's memoized live panel (see point 3 above), plus — for the
    industry-neutral NOA family only — the point-in-time bucket panel its
    specs must be bound to."""

    end: date
    panel: CrossSectionalLivePanel
    bucket_frame: pd.DataFrame | None = None


_QUALITY_PANEL_MEMO: dict[str, _QualityLiveBuild] = {}

# THE LIVE BUCKET PANEL, and why this one family needs a module-level
# holder. build_noa_neutral_family takes a bucket_frame and closes each
# spec's signal over it — it is runtime DATA, not a searched-over axis (that
# module's own words) — so the family's specs cannot be built at all without
# a concrete panel. The adapter contract, correctly, gives build_specs no
# arguments: resolve_spec is called by the /families endpoint and by every
# registration, neither of which may trigger a multi-hundred-request EDGAR
# fetch. So build_live_panel publishes the panel it just built here, and
# build_noa_neutral_live_specs binds the family's own builder to it.
# The runner's order makes this safe by construction: _process_family calls
# build_live_panel FIRST and returns early if it raises, and only then does
# _process_registration call resolve_spec.
_LIVE_NOA_NEUTRAL_BUCKET_FRAME: pd.DataFrame | None = None

# What build_noa_neutral_live_specs binds to when no live panel has been
# built yet — registration time, the /families listing, drift checks. Every
# field spec_identity fingerprints (pattern_id, holding_days, rank_fraction,
# portfolio, leg_weighting, cohort_formation_days, the requires_* flags) is
# fixed by the family's declared grid and is IDENTICAL whichever bucket frame
# is passed, so these specs are exactly as good as live ones for identity —
# and they are deliberately useless for anything else: forming a portfolio
# with one raises out of the empty frame rather than quietly ranking nothing.
_IDENTITY_ONLY_BUCKET_FRAME: pd.DataFrame = pd.DataFrame()


# THE CANDIDATE POOL THE TWO 2026-08-30 REGISTRATIONS WERE CREATED AGAINST,
# hashed: sha256 over {"sample": the 200 drawn tickers, "universe_size": the
# 768-name point-in-time union}. Recomputed and compared on every live panel
# build.
#
# WHY THE PIN ABOVE IS NOT ENOUGH ON ITS OWN. Pinning the sample window's end
# to MEMBERSHIP_DATA_AS_OF closes the path a live MembershipRefreshRunner
# opens, because a refresh may only ever add coverage AFTER that constant. It
# closes nothing against a change to the constant itself, or to the vendored
# _EVENTS/_BASE_UNIVERSE literals inside the existing window — a re-vendoring
# is an ordinary, legitimate maintenance action, it moves MEMBERSHIP_DATA_AS_OF
# forward by design, and because build_quality_sample reads the constant rather
# than a literal, the pinned call would then draw from a LARGER union and
# random.Random(seed).sample would re-draw the whole 200 (measured: one added
# name swaps ~21 of them). That is the exact abrupt whole-book replacement the
# pin exists to prevent, and it is invisible to every other guard here — a
# universe is data, so it is in neither spec_identity nor config_identity, and
# the registration row stores no copy of it to compare against.
#
# So the sample is fingerprinted against a LITERAL that a re-vendoring cannot
# move. Regenerating this constant is therefore a deliberate act that ENDS the
# in-flight registrations' comparability and must be accompanied by
# re-registering them, not a routine update to keep the tests green.
QUALITY_LIVE_SAMPLE_FINGERPRINT = "93e106422a115390d6b9c12b67a449a631c13e664e0e8571e80623bb66ed52ce"


def quality_sample_fingerprint(sample: list[str], universe_size: int) -> str:
    return _hash({"sample": list(sample), "universe_size": universe_size})


def _assert_sample_is_the_registered_one(sample: list[str], universe_size: int) -> None:
    live = quality_sample_fingerprint(sample, universe_size)
    if live != QUALITY_LIVE_SAMPLE_FINGERPRINT:
        raise CrossSectionalUniverseDriftError(
            "The seeded candidate sample the quality forward registrations tick is no longer the "
            f"one they were registered against: {len(sample)} of a {universe_size}-name union "
            f"fingerprints as {live}, registered {QUALITY_LIVE_SAMPLE_FINGERPRINT}. A seeded sample "
            "is a function of the WHOLE membership union, so this is a wholesale re-draw, not a "
            "name or two — almost certainly a re-vendoring of sp500_membership_history's literals "
            "(which moves MEMBERSHIP_DATA_AS_OF, and so the pinned sample window, forward). "
            "Ticking on would blend two different candidate universes into one track record and "
            "charge the switch as 100% turnover, so this stops instead. Resolve it deliberately: "
            "either restore the literals, or re-register both rows against the new universe and "
            "regenerate QUALITY_LIVE_SAMPLE_FINGERPRINT — never regenerate the constant alone."
        )


def _live_edgar_provider() -> EdgarXbrlProvider:
    """The EDGAR provider the LIVE path uses — the one difference from the
    default a backtest gets is the cache-age bound of point 2 above."""
    return EdgarXbrlProvider(max_cache_age_days=QUALITY_LIVE_EDGAR_MAX_CACHE_AGE_DAYS)


def _build_quality_sample_and_prices(
    end: date, provider: YFinanceProvider
) -> tuple[list[str], pd.DataFrame]:
    """run_quality_screening's own sample-and-price block, with the one
    documented pin of point 1: the SAMPLE window ends at the vendored
    membership coverage constant, the PRICE window ends at the live tick
    date. Padding before the start is the family's own constant."""
    sample, universe_size = build_quality_sample(MEMBERSHIP_DATA_START, MEMBERSHIP_DATA_AS_OF)
    _assert_sample_is_the_registered_one(sample, universe_size)
    padded_start = MEMBERSHIP_DATA_START - timedelta(days=QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    close, _missing_price = provider.get_price_history(sample, padded_start, end)
    return sample, close


def _require_rankable_today(frame: pd.DataFrame, what: str) -> None:
    """Refuse a panel whose newest row can rank NOTHING.

    WHY THIS IS A PANEL-UNAVAILABLE ERROR AND NOT A RESEARCH FINDING. If the
    EDGAR pipeline resolves nothing (outage, throttling, an emptied cache),
    the factor frame is all-NaN, form_portfolio ranks zero names, and the
    tick holds an empty book that realizes EXACTLY 0.0 every day. Those zeros
    are indistinguishable in day_results_json from a real flat day, so an
    outage would be written into the track record as performance. Raising
    instead leaves the registration untouched for the next tick, and
    rows_to_process realizes every missed row once data returns — the
    behavior CrossSectionalPanelUnavailableError is documented for."""
    if frame.empty or not bool(np.isfinite(frame.iloc[-1].to_numpy(dtype=float)).any()):
        raise CrossSectionalPanelUnavailableError(
            f"No {what} resolved on the live panel's newest row, so nothing could be ranked this "
            "tick. Treated as a data outage rather than a formation with no eligible names: an "
            "empty book realizes exactly 0.0 every day, which would be recorded as flat "
            "performance rather than as missing data."
        )


def build_cbop_specs() -> list[CrossSectionalSpec]:
    """The CbOP family's own 9 pre-declared spec objects. A list copy, not a
    rebuild: cross_sectional_quality declares CBOP_FAMILY at module level
    (its _build_quality_family runs the pre-declared-grid assertions there),
    so these ARE the objects run_quality_screening screened."""
    return list(CBOP_FAMILY)


def build_cbop_live_panel(
    end: date,
    *,
    provider: YFinanceProvider | None = None,
    edgar: EdgarXbrlProvider | None = None,
) -> CrossSectionalLivePanel:
    """The CbOP family's live panel, built by calling that family's OWN
    functions in that family's OWN order — this is run_quality_screening's
    data-preparation block for the CbOP half, with nothing recomputed that
    the family does not already compute for its backtests: the seeded sample,
    the EDGAR line-item extraction, compute_cbop_observations per company,
    and build_point_in_time_factor_frame's filing-dated step panel.

    The membership function is sp500_membership_history.was_member itself —
    the exact gate run_cross_sectional_backtest falls back to when
    screen_cross_sectional_universe is called with membership_fn=None, which
    is what run_quality_screening does.

    `provider` and `edgar` are injectable for the same reason
    run_quality_screening's own are: so tests can drive this without a
    network call. Production passes neither."""
    memo = _QUALITY_PANEL_MEMO.get(QUALITY_CBOP_FAMILY_KEY)
    if memo is not None and memo.end == end:
        return memo.panel

    provider = provider if provider is not None else dependencies.provider
    edgar = edgar if edgar is not None else _live_edgar_provider()

    sample, close = _build_quality_sample_and_prices(end, provider)
    if close.empty:
        raise CrossSectionalPanelUnavailableError(
            "No price data resolved for any sampled ticker — the CbOP live panel is empty, so "
            "nothing can be formed or realized this tick."
        )

    extractions, _missing_cik, _failed_fetch = edgar.fetch_line_items_for_tickers(sample)
    observations: dict[str, list[FactorObservation]] = {}
    for ticker, extraction in extractions.items():
        observations[ticker], _diagnostics = compute_cbop_observations(extraction)

    frame, _ages, _unusable = build_point_in_time_factor_frame(close, observations)
    _require_rankable_today(frame, "cash-based operating profitability value")

    panel = CrossSectionalLivePanel(
        data=CrossSectionalData(close=close, fundamental_signal=frame),
        membership_fn=was_member,
        n_tickers=len(close.columns),
        last_row_date=close.index[-1].date(),
    )
    _QUALITY_PANEL_MEMO[QUALITY_CBOP_FAMILY_KEY] = _QualityLiveBuild(end=end, panel=panel)
    return panel


def build_noa_neutral_live_specs() -> list[CrossSectionalSpec]:
    """The industry-neutral NOA family's own 9 pre-declared specs, bound to
    the bucket panel the most recent build_live_panel published — or, when
    none has been, to the identity-only frame documented above.

    Built by calling the family's OWN build_noa_neutral_family (which runs
    its pre-declared-grid and 18-trial-denominator assertions on every call),
    never by re-declaring specs here."""
    frame = _LIVE_NOA_NEUTRAL_BUCKET_FRAME
    return build_noa_neutral_family(frame if frame is not None else _IDENTITY_ONLY_BUCKET_FRAME)


def build_noa_neutral_live_panel(
    end: date,
    *,
    provider: YFinanceProvider | None = None,
    edgar: EdgarXbrlProvider | None = None,
) -> CrossSectionalLivePanel:
    """The industry-neutral NOA family's live panel — run_noa_neutral_
    screening's data-preparation block, calling that family's own functions
    in its own order: the same seeded sample and the same NOA pipeline as the
    sibling family (compute_noa_observations ->
    build_point_in_time_factor_frame), plus this family's own point-in-time
    SIC panel (fetch_sic_history_for_tickers ->
    build_point_in_time_bucket_frame).

    The SIC history is fetched for the sample MINUS the tickers EDGAR
    resolves no CIK for, exactly as run_noa_neutral_screening does — those
    names have no accession list to read headers from and can never rank in
    any quality family anyway.

    Publishes the bucket panel to the module holder before returning, which
    is what makes build_noa_neutral_live_specs able to bind the family's own
    specs to the same panel this one was built with."""
    global _LIVE_NOA_NEUTRAL_BUCKET_FRAME

    memo = _QUALITY_PANEL_MEMO.get(QUALITY_NOA_NEUTRAL_FAMILY_KEY)
    if memo is not None and memo.end == end:
        _LIVE_NOA_NEUTRAL_BUCKET_FRAME = memo.bucket_frame
        return memo.panel

    provider = provider if provider is not None else dependencies.provider
    edgar = edgar if edgar is not None else _live_edgar_provider()

    sample, close = _build_quality_sample_and_prices(end, provider)
    if close.empty:
        raise CrossSectionalPanelUnavailableError(
            "No price data resolved for any sampled ticker — the industry-neutral NOA live panel "
            "is empty, so nothing can be formed or realized this tick."
        )

    extractions, missing_cik, _failed_fetch = edgar.fetch_line_items_for_tickers(sample)
    observations: dict[str, list[FactorObservation]] = {}
    for ticker, extraction in extractions.items():
        observations[ticker], _diagnostics = compute_noa_observations(extraction)

    frame, _ages, _unusable = build_point_in_time_factor_frame(close, observations)
    _require_rankable_today(frame, "net-operating-assets value")

    sic_histories, _sic_missing_cik, _sic_failed = edgar.fetch_sic_history_for_tickers(
        [t for t in sample if t not in missing_cik]
    )
    bucket_frame, _no_bucket, _sic_fallback = build_point_in_time_bucket_frame(close, sic_histories)
    # A bucket panel whose newest row classifies nobody cannot demean
    # anything, so every name would be refused and the book would be empty —
    # the same fake-flat-day hazard _require_rankable_today exists for, one
    # step further down the pipeline. notna() rather than isfinite(): this
    # frame holds bucket LABELS (strings), not numbers.
    if bucket_frame.empty or not bool(bucket_frame.iloc[-1].notna().any()):
        raise CrossSectionalPanelUnavailableError(
            "No point-in-time industry bucket resolved on the live panel's newest row, so every "
            "name would be refused from the industry-demeaned ranking this tick. Treated as a data "
            "outage, not as a formation with no eligible names."
        )

    panel = CrossSectionalLivePanel(
        data=CrossSectionalData(close=close, fundamental_signal=frame),
        membership_fn=was_member,
        n_tickers=len(close.columns),
        last_row_date=close.index[-1].date(),
    )
    _LIVE_NOA_NEUTRAL_BUCKET_FRAME = bucket_frame
    _QUALITY_PANEL_MEMO[QUALITY_NOA_NEUTRAL_FAMILY_KEY] = _QualityLiveBuild(
        end=end, panel=panel, bucket_frame=bucket_frame
    )
    return panel


# --- the SHORT-INTEREST RATIO family adapter ---------------------------------
#
# ONE NORMALIZER PER FAMILY KEY, AND THAT IS A SAFETY PROPERTY RATHER THAN A
# NAMING CHOICE — read this before adding the sibling half.
#
# cross_sectional_short_interest declares TWELVE specs across TWO normalizers
# (short-interest ratio, days-to-cover), and both normalizers' signal
# functions read the SAME slot: CrossSectionalData.fundamental_signal. Which
# quantity that slot holds is the caller's decision — run_short_interest_
# screening screens the family as two passes over two different panels — and
# it is DATA, so it appears in neither spec_identity nor config_identity and
# no drift check can see it.
#
# An adapter contract gives a family exactly one build_live_panel. So a
# single "short_interest" adapter serving the ratio panel while exposing all
# twelve pattern_ids would let a days-to-cover registration resolve happily
# and then tick on the RATIO panel forever — ranking a different variable
# than its own pattern_id names, with a spec fingerprint that matches
# perfectly on every tick. That is precisely the silent mis-tick this whole
# module exists to make impossible.
#
# This adapter therefore exposes only the six specs its panel actually feeds.
# Registering a days-to-cover spec raises UnknownCrossSectionalSpecError
# naming the six that exist, which is the correct answer: the days-to-cover
# half needs its OWN family key bound to its OWN panel, and building it was
# deliberately not done here (that half is the one the family's post-hoc
# diagnostic found is substantially sorting on trading VOLUME — see
# cross_sectional_short_interest.py section 5).
#
# n_trials stays the family's full 12, NOT the 6 this key exposes, exactly as
# the industry-neutral NOA adapter records 18 rather than its own 9: 12 is
# what screen_cross_sectional_universe deflated these Sharpes against and what
# the persisted cross_sectional_trial_results rows record. Recording 6 would
# launder half the family's search out of the registration row.

SHORT_INTEREST_RATIO_FAMILY_KEY = "short_interest_ratio"
SHORT_INTEREST_RATIO_NORMALIZER = "short_interest_ratio"

# How long the live path may serve a cached SEC frames document. Seven days,
# and the reasoning is the visibility lag rather than freshness for its own
# sake: this project may not READ a share count until 90 calendar days after
# its cover date (sec_shares_outstanding_provider.VISIBILITY_LAG_DAYS), so any
# bound comfortably shorter than that picks every record up long before it is
# usable. What it prevents is the real failure — the frame of the quarter
# currently IN PROGRESS, which a live panel first requests on the day that
# quarter begins when it is nearly empty, being cached in that state forever.
# See SecSharesOutstandingProvider's class docstring.
SHORT_INTEREST_LIVE_FRAME_MAX_CACHE_AGE_DAYS = 7

SHORT_INTEREST_UNIVERSE_RULE = (
    "Candidate pool: the FULL point-in-time S&P 500 UNION over "
    f"[{SHORT_INTEREST_FORMATION_START.isoformat()}, the vendored coverage end] "
    "(sp500_membership_history.get_universe_over) — 691 names in the 2026-09-02 production run, and "
    "NOT a seeded sample: this family's data cost is per FINRA settlement CYCLE rather than per "
    "ticker, so it can afford the whole universe where the EDGAR-based quality families had to draw "
    "200 names. Unlike those families the window's end is NOT pinned to the vendored membership "
    "constant: a union is additive (a live membership refresh can only ADD a name that really "
    "joined the index, never re-draw the pool the way a seeded sample re-draws), and every name is "
    "gated per formation anyway by the harness's own S&P 500 rule, exactly as when "
    "screen_cross_sectional_universe is called with membership_fn=None: "
    "sp500_membership_history.was_member(ticker, formation date) AND a finite close on that date. "
    "A name is RANKED only where the family's COMMON-CROSS-SECTION MASK admits it "
    "(cross_sectional_short_interest.build_short_interest_panels): the cell must carry BOTH a "
    "short-interest RATIO — real FINRA bi-monthly short shares over a real SEC point-in-time share "
    "count, the numerator readable at settlement + 14 calendar days and the denominator at its own "
    "cover date + 90, both forward-filled as step series (never interpolated, never back-filled) and "
    f"refused once carried past {SHORT_INTEREST_MAX_STALENESS_DAYS} / {SHARES_MAX_STALENESS_DAYS} "
    "days respectively, with every FINRA-flagged stock-split cycle and every ratio above 1.0 refused "
    "outright — AND a days-to-cover, so the two normalizer halves rank the identical cross-section. "
    "The backward run ranked ~394-404 names per formation, giving 5%-tail legs of ~20.6 names. "
    "RESIDUAL SURVIVORSHIP, stated not hidden: the mask reimports SEC's current-day ticker map into "
    "the family (108 of the 691 names resolve no CIK, and 69 priced tickers are never ranked at "
    "all), and the names it drops are overwhelmingly index LEAVERS — disproportionately the hedge "
    "leg's natural candidates — so the surviving cross-section is better than the real one was. "
    "THIS FLATTERS THE RESULTS."
)


@dataclass(frozen=True)
class _ShortInterestLiveBuild:
    """This family's memoized live panel, for the same reason point 3 of the
    quality section gives: the runner keeps a family pending for the rest of
    the UTC day after its one real new row is processed, and every further
    call to build_live_panel that day can only return what the first one
    returned."""

    end: date
    panel: CrossSectionalLivePanel


_SHORT_INTEREST_PANEL_MEMO: dict[str, _ShortInterestLiveBuild] = {}


def build_short_interest_ratio_specs() -> list[CrossSectionalSpec]:
    """The six pre-declared SHORT-INTEREST-RATIO specs — the family's own
    objects, from the family's own builder (which re-runs its 12-spec grid
    assertions on every call), filtered to the half this adapter's panel
    feeds. See this section's header for why the filter is a safety property.

    Takes no arguments and touches no data, so /families and every drift
    check stay cheap."""
    return specs_for_normalizer(SHORT_INTEREST_RATIO_NORMALIZER)


def build_short_interest_live_panel(
    end: date,
    *,
    provider: YFinanceProvider | None = None,
    finra: FinraShortInterestProvider | None = None,
    sec_shares: SecSharesOutstandingProvider | None = None,
    edgar: EdgarXbrlProvider | None = None,
) -> CrossSectionalLivePanel:
    """The short-interest family's live panel, built by calling that family's
    OWN functions in that family's OWN order — this is
    run_short_interest_screening's data-preparation block, with nothing
    recomputed that the family does not already compute for its backtests:
    the point-in-time union universe, the FINRA cycle fetch, the SEC
    point-in-time share-count step panel, and build_short_interest_panels
    (which is also what applies the family's common-cross-section mask, so
    the live ratio panel ranks exactly the cross-section the backtested one
    did).

    THE WHOLE HISTORY IS REBUILT, not a trailing window, and that is
    deliberate: a shortened window would be a SECOND declaration of this
    family's panel — new constants, derived by hand from its staleness bounds
    — and the one thing a forward clock must never tolerate is a panel that
    can drift from the one its backtest used. The disclosed cost is real and
    is paid once per UTC day (the memo below): ~209 FINRA cycle files, ~37 SEC
    frames and a ~690-ticker multi-year price history, all of which are disk
    caches on a machine that has them and cold fetches on a host whose disk is
    ephemeral. It runs in the runner's worker thread, never on the event loop,
    and never at app startup — registration resolves specs in memory only.

    A vendor outage is translated into CrossSectionalPanelUnavailableError
    rather than escaping as a provider error: it means "no data this tick,
    retry in half an hour", which is exactly that class's contract, and the
    registration is left untouched.

    The four providers are injectable for the same reason
    run_short_interest_screening's own are: so tests can drive this without a
    network call. Production passes none of them."""
    memo = _SHORT_INTEREST_PANEL_MEMO.get(SHORT_INTEREST_RATIO_FAMILY_KEY)
    if memo is not None and memo.end == end:
        return memo.panel

    provider = provider if provider is not None else dependencies.provider
    finra = finra if finra is not None else FinraShortInterestProvider()
    sec_shares = (
        sec_shares
        if sec_shares is not None
        else SecSharesOutstandingProvider(
            max_cache_age_days=SHORT_INTEREST_LIVE_FRAME_MAX_CACHE_AGE_DAYS
        )
    )
    # The bounded provider, for its ticker->CIK map: that map is one of the
    # two MUTABLE caches EdgarXbrlProvider's own bound covers, and a frozen
    # copy would keep a newly-added index member out of the share-count
    # denominator (and so out of the ranked cross-section) indefinitely.
    edgar = edgar if edgar is not None else _live_edgar_provider()

    universe = get_universe_over(SHORT_INTEREST_FORMATION_START, end)
    padded_start = SHORT_INTEREST_FORMATION_START - timedelta(
        days=SHORT_INTEREST_PRICE_HISTORY_PADDING_CALENDAR_DAYS
    )
    close, _missing_price = provider.get_price_history(universe, padded_start, end)
    if close.empty:
        raise CrossSectionalPanelUnavailableError(
            "No price data resolved for any universe ticker — the short-interest live panel is "
            "empty, so nothing can be formed or realized this tick."
        )

    priced = list(close.columns)
    try:
        observations, _finra_diagnostics = finra.fetch_observations_for_tickers(
            priced, SHORT_INTEREST_CYCLE_FETCH_START, end
        )
        cik_map = edgar.get_ticker_cik_map()
        resolvable = {ticker: cik_map[ticker] for ticker in priced if ticker in cik_map}
        share_observations, _share_diagnostics = sec_shares.fetch_share_counts(
            resolvable,
            padded_start,
            end,
            missing_from_map=[ticker for ticker in priced if ticker not in cik_map],
        )
    except (FinraShortInterestFetchError, SecSharesFetchError) as exc:
        raise CrossSectionalPanelUnavailableError(
            f"A short-interest input could not be fetched this tick, so the panel was not built: {exc}"
        ) from exc

    share_frame, _no_shares = build_point_in_time_share_count_frame(
        close, share_observations, max_staleness_days=SHARES_MAX_STALENESS_DAYS
    )
    ratio_frame, _dtc_frame, _panel_diagnostics = build_short_interest_panels(
        close, observations, share_frame
    )
    _require_rankable_today(ratio_frame, "short-interest ratio")

    panel = CrossSectionalLivePanel(
        data=CrossSectionalData(close=close, fundamental_signal=ratio_frame),
        membership_fn=was_member,
        n_tickers=len(close.columns),
        last_row_date=close.index[-1].date(),
    )
    _SHORT_INTEREST_PANEL_MEMO[SHORT_INTEREST_RATIO_FAMILY_KEY] = _ShortInterestLiveBuild(
        end=end, panel=panel
    )
    return panel


# --- the LAZY PRICES (filing-language) family adapter ------------------------
#
# ONE (metric, scope) PANEL PER FAMILY KEY, for the identical reason the
# short-interest section above states: cross_sectional_lazy_prices declares
# THIRTY-SIX specs across SIX different signal panels (2 similarity metrics x
# 3 document scopes), and every one of those 36 specs reads the SAME slot,
# CrossSectionalData.fundamental_signal. Which of the six similarity panels
# that slot holds at a given moment is the CALLER's decision, is DATA, and is
# therefore invisible to spec_identity/config_identity — no drift check can
# see it. An adapter that built the jaccard/full panel while resolving all 36
# pattern_ids would let a risk_factors or cosine registration tick on the
# WRONG variable forever, with a spec fingerprint that matches perfectly on
# every tick — precisely the silent mis-tick this whole module exists to make
# impossible.
#
# This adapter therefore exposes only the SIX specs that share the (jaccard,
# full) panel: cross_sectional_lazy_prices.specs_for_panel is the family's OWN
# filter, mirroring specs_for_normalizer exactly. Registering any other
# pattern_id (a risk_factors or mda spec, or a cosine spec) raises
# UnknownCrossSectionalSpecError naming the six that exist — the other five
# panels have no adapter at all today, deliberately not built until a
# registration decision is actually made for one of them.
#
# n_trials stays the family's full 36, NOT the 6 this key exposes — the same
# convention short_interest_ratio (12, not 6) and quality_noa_industry_neutral
# (18, not 9) already keep: 36 is what screen_lazy_prices_family actually
# deflated these Sharpes against and what the persisted cross_sectional_
# trial_results rows record. Recording 6 would launder 30 trials of search out
# of the registration row.
#
# THIS IS THE MOST EXPENSIVE LIVE PANEL IN THE PROJECT, BY A WIDE MARGIN, and
# that must be said plainly here rather than discovered later. The
# 2026-09-01 production run fetched 7,798 real 10-K documents from
# www.sec.gov/Archives to build all six panels; rebuilding even the ONE panel
# this key needs still requires listing and fetching (or, once a process has
# cached them, re-reading from disk) every same-type filing pair of every
# point-in-time S&P 500 union member back to MEMBERSHIP_DATA_START, because a
# language-change signal needs each filing AND its own predecessor — there is
# no shorter live-only window that does not change what the panel measures
# (see "THE WHOLE HISTORY IS REBUILT" in build_lazy_prices_live_panel's own
# docstring, and short_interest's identical choice above for the general
# reasoning). EdgarFilingTextProvider's filing-TEXT cache is a PERMANENT disk
# cache (that module's docstring: an already-published filing's text never
# changes), so a long-running process pays this cost roughly once; a host
# whose disk resets on every deploy or free-tier wake — this project's own
# Render host is exactly that host, per SHORT_INTEREST_UNIVERSE_RULE's own
# disclosure of the identical hazard at a smaller scale — pays it again on
# every cold start, at a scale an order of magnitude larger than any sibling
# family's. It runs in the runner's worker thread (asyncio.to_thread, never
# the event loop) and never at app startup, so a slow or failing build cannot
# look like a hung deploy and cannot block any other family's tick (families
# build their live panels concurrently, one thread each — see
# CrossSectionalForwardValidationRunner._tick). A build still running when the
# next tick fires is simply awaited again; nothing is corrupted by an
# in-flight fetch, because the memo below only ever publishes a COMPLETE
# panel.

LAZY_PRICES_JACCARD_FULL_FAMILY_KEY = "lazy_prices_jaccard_full"

LAZY_PRICES_UNIVERSE_RULE = (
    "Candidate pool: the FULL point-in-time S&P 500 UNION over "
    f"[{MEMBERSHIP_DATA_START.isoformat()}, the vendored coverage end] "
    "(sp500_membership_history.get_universe_over) — 768 names in the 2026-09-01 production run, and "
    "NOT a seeded sample, exactly like the short-interest family and unlike the two EDGAR-XBRL "
    "quality families: this family's cost is per FILING, not per API call, so a union costs the same "
    "whichever names are in it. Every name is additionally gated per formation by the harness's own "
    "S&P 500 rule: sp500_membership_history.was_member(ticker, formation date) AND a finite close on "
    "that date. "
    "A name is RANKED only where the point-in-time JACCARD SIMILARITY OF ITS FULL 10-K TEXT TO ITS "
    "OWN IMMEDIATELY-PRIOR 10-K carries a value (cross_sectional_lazy_prices.build_similarity_panel): "
    "visible from the CURRENT filing's real EDGAR acceptance date (acceptanceDateTime, never the "
    "fiscal period end — see availability_date), forward-filled as a step series (never interpolated, "
    f"never back-filled) and refused once carried past {LAZY_PRICES_MAX_STALENESS_DAYS} calendar "
    "days. A firm's FIRST filing of a form type has no predecessor and scores nothing; comparing "
    "across form types (10-K vs 10-Q) is structurally impossible (pair_same_type_filings pairs "
    "strictly within each form's own chronological sequence). "
    "'full' — the whole 10-K text, not an extracted section — is the paper's own BASE-CASE scope "
    "(Cohen/Malloy/Nguyen's 34-58bp headline is whole-document, not a section) and had ZERO "
    "section-extraction loss in the 2026-09-01 production run (100.0% of same-type pairs scored, "
    "unlike risk_factors' 90.0% and mda's 87.4%), so unlike those two section-scope panels this one's "
    "cross-section is not differentially composed by which filers' section headings happen to parse. "
    "RESIDUAL, DISCLOSED AND NOT YET FIXED: SEC's ticker->CIK map currently resolves XOM to a "
    "newly-registered successor shell (CIK 2115436, zero 10-K filings) rather than its real historic "
    "CIK — the same root cause fixed in edgar_xbrl_provider.py on 2026-09-02 for the quality "
    "families, deliberately NOT ported to edgar_filing_text_provider.py (this family's own, separate "
    "provider) because it was out of scope for that change. XOM is therefore likely silently excluded "
    "from this live panel today (build_filing_index(['XOM'], forms=('10-K',)) returns 0 filings, "
    "recorded as a successfully-indexed ticker with nothing in it rather than as a missing one). One "
    "name's absence from a roughly 700-name union is not expected to change this registration's "
    "outcome, but it is unmeasured and unfixed, exactly as data/research_runs/lazy_prices_2026-09-01."
    "txt section 9 discloses for the backward panel this registration was decided from."
)


@dataclass(frozen=True)
class _LazyPricesLiveBuild:
    """This family's memoized live panel, for the identical reason the
    quality section's point 3 and the short-interest memo give: the runner
    keeps a family pending for the rest of the UTC day after its one real new
    row is processed, and every further call to build_live_panel that day can
    only return what the first one returned — which matters far more here,
    since a rebuild is this project's single most expensive live fetch by a
    wide margin (see this section's header)."""

    end: date
    panel: CrossSectionalLivePanel


_LAZY_PRICES_PANEL_MEMO: dict[str, _LazyPricesLiveBuild] = {}


def build_lazy_prices_jaccard_full_specs() -> list[CrossSectionalSpec]:
    """The six pre-declared JACCARD/FULL specs — the family's own objects,
    from the family's own filter (cross_sectional_lazy_prices.specs_for_panel,
    which reads the module-level LAZY_PRICES_FAMILY built once at import,
    itself asserted against the frozen 36-spec grid). Takes no arguments and
    touches no data, so /families and every drift check stay cheap."""
    return lazy_prices_specs_for_panel("jaccard", "full")


def build_lazy_prices_live_panel(
    end: date,
    *,
    provider: YFinanceProvider | None = None,
    text_provider: EdgarFilingTextProvider | None = None,
) -> CrossSectionalLivePanel:
    """The lazy_prices family's live panel, built by calling that family's OWN
    functions in that family's OWN order — this is run_lazy_prices_
    screening's data-preparation block, restricted to the ONE (jaccard, full)
    panel this adapter's family_key exposes, with nothing recomputed that the
    family does not already compute for its backtests: the point-in-time
    union universe, the real EDGAR filing index, build_similarity_
    observations and build_similarity_panel.

    THE WHOLE HISTORY IS REBUILT, not a trailing window — the same deliberate
    choice build_short_interest_live_panel makes and documents: a shortened
    window would be a SECOND declaration of this family's panel (new
    constants, hand-derived from its staleness bounds), and the one thing a
    forward clock must never tolerate is a panel that can drift from the one
    its backtest used. See this section's header for the real, disclosed cost
    of that choice for this family specifically — by far the largest in the
    project.

    `provider` and `text_provider` are injectable for the same reason every
    sibling adapter's are: so tests can drive this without a network call.
    Production passes neither."""
    memo = _LAZY_PRICES_PANEL_MEMO.get(LAZY_PRICES_JACCARD_FULL_FAMILY_KEY)
    if memo is not None and memo.end == end:
        return memo.panel

    provider = provider if provider is not None else dependencies.provider
    text_provider = text_provider if text_provider is not None else EdgarFilingTextProvider()

    start = MEMBERSHIP_DATA_START
    universe = get_universe_over(start, end)
    frames, _missing = provider.get_daily_ohlcv(sorted(universe), start, end)
    close = frames.get("close") if frames else None
    if close is None or close.empty:
        raise CrossSectionalPanelUnavailableError(
            "No price data resolved for any point-in-time universe ticker — the lazy_prices live "
            "panel is empty, so nothing can be formed or realized this tick."
        )
    priced = list(close.columns)

    filing_index, _filing_report = text_provider.build_filing_index(priced, forms=LAZY_PRICES_FORMS)
    # Only filings that could matter to a same-type consecutive pair — the
    # identical warm-up trim run_lazy_prices_screening applies.
    warmup_floor = start.toordinal() - LAZY_PRICES_FILING_WARMUP_DAYS
    trimmed = {
        ticker: [f for f in filings if f.filing_date.toordinal() >= warmup_floor]
        for ticker, filings in filing_index.items()
        if ticker in close.columns
    }

    observations, _similarity_report = build_similarity_observations(
        text_provider, trimmed, metrics=("jaccard",), scopes=("full",)
    )
    by_ticker = observations.get(("jaccard", "full"), {})
    panel, _ages, _unusable = build_similarity_panel(close, by_ticker)
    _require_rankable_today(panel, "jaccard/full filing-language similarity")

    half_spread = build_edge_half_spread_frame(frames["open"], frames["high"], frames["low"], close)
    leg_weight_basis = build_lazy_prices_inverse_vol_basis(close)

    live_panel = CrossSectionalLivePanel(
        data=CrossSectionalData(
            close=close,
            fundamental_signal=panel,
            half_spread=half_spread,
            leg_weight_basis=leg_weight_basis,
        ),
        membership_fn=was_member,
        n_tickers=len(close.columns),
        last_row_date=close.index[-1].date(),
    )
    _LAZY_PRICES_PANEL_MEMO[LAZY_PRICES_JACCARD_FULL_FAMILY_KEY] = _LazyPricesLiveBuild(
        end=end, panel=live_panel
    )
    return live_panel


def _bootstrap() -> None:
    register_family(
        CrossSectionalFamilyAdapter(
            family_key=CRYPTO_FAMILY_KEY,
            module_path="app/services/research_lab/cross_sectional_crypto.py",
            universe_rule=CRYPTO_UNIVERSE_RULE,
            n_trials=CRYPTO_N_TRIALS,
            build_specs=build_crypto_family,
            build_config=default_crypto_config,
            build_live_panel=build_crypto_live_panel,
        )
    )
    register_family(
        CrossSectionalFamilyAdapter(
            family_key=QUALITY_CBOP_FAMILY_KEY,
            module_path="app/services/research_lab/cross_sectional_quality.py",
            universe_rule=QUALITY_CBOP_UNIVERSE_RULE,
            # This family's OWN pre-declared denominator: 9 definitions
            # (3 holds x 2 portfolio modes at deciles, plus 3 quintile
            # robustness variants), never pooled with its NOA sibling built
            # in the same session. Matches the n_trials the persisted
            # cross_sectional_trial_results rows were deflated against.
            n_trials=CBOP_N_TRIALS,
            build_specs=build_cbop_specs,
            build_config=default_quality_config,
            build_live_panel=build_cbop_live_panel,
        )
    )
    register_family(
        CrossSectionalFamilyAdapter(
            family_key=QUALITY_NOA_NEUTRAL_FAMILY_KEY,
            module_path="app/services/research_lab/cross_sectional_quality_neutral.py",
            universe_rule=QUALITY_NOA_NEUTRAL_UNIVERSE_RULE,
            # 18, NOT this family's own 9: its DSR denominator carries the
            # raw NOA family's 9 trials, because this hypothesis exists ONLY
            # because those 9 produced a (later-diagnosed spurious) positive
            # — a sequential search the within-family count cannot see, which
            # the raw family pre-declared in writing would be carried. 18 is
            # what screen_cross_sectional_universe actually deflated against
            # and what the persisted trial rows record; recording 9 here
            # would quietly launder that search out of the row.
            n_trials=NOA_NEUTRAL_DSR_N_TRIALS,
            build_specs=build_noa_neutral_live_specs,
            build_config=default_quality_config,
            build_live_panel=build_noa_neutral_live_panel,
        )
    )
    register_family(
        CrossSectionalFamilyAdapter(
            family_key=SHORT_INTEREST_RATIO_FAMILY_KEY,
            module_path="app/services/research_lab/cross_sectional_short_interest.py",
            universe_rule=SHORT_INTEREST_UNIVERSE_RULE,
            # 12, NOT the 6 this key exposes: the family screened both
            # normalizers under one pre-declared denominator and passed
            # n_trials_override=12 to both passes, which is what the
            # persisted trial rows record. See this section's header.
            n_trials=SHORT_INTEREST_N_TRIALS,
            build_specs=build_short_interest_ratio_specs,
            build_config=default_short_interest_config,
            build_live_panel=build_short_interest_live_panel,
        )
    )
    register_family(
        CrossSectionalFamilyAdapter(
            family_key=LAZY_PRICES_JACCARD_FULL_FAMILY_KEY,
            module_path="app/services/research_lab/cross_sectional_lazy_prices.py",
            universe_rule=LAZY_PRICES_UNIVERSE_RULE,
            # 36, NOT the 6 this key exposes: the family's own screening loop
            # pools all 36 Sharpes (2 metrics x 3 scopes x 3 holds x 2
            # weightings) into one sigma_sr before deflating any of them (see
            # cross_sectional_lazy_prices's own "WHY THIS MODULE RUNS ITS OWN
            # SCREENING LOOP"), so 36 is what the persisted trial rows record.
            n_trials=LAZY_PRICES_N_TRIALS,
            build_specs=build_lazy_prices_jaccard_full_specs,
            build_config=default_lazy_prices_config,
            build_live_panel=build_lazy_prices_live_panel,
        )
    )


_bootstrap()


__all__ = [
    "CRYPTO_FAMILY_KEY",
    "CRYPTO_UNIVERSE_RULE",
    "LAZY_PRICES_JACCARD_FULL_FAMILY_KEY",
    "LAZY_PRICES_UNIVERSE_RULE",
    "QUALITY_CBOP_FAMILY_KEY",
    "QUALITY_CBOP_UNIVERSE_RULE",
    "QUALITY_LIVE_EDGAR_MAX_CACHE_AGE_DAYS",
    "QUALITY_LIVE_SAMPLE_FINGERPRINT",
    "QUALITY_NOA_NEUTRAL_FAMILY_KEY",
    "QUALITY_NOA_NEUTRAL_UNIVERSE_RULE",
    "SHORT_INTEREST_LIVE_FRAME_MAX_CACHE_AGE_DAYS",
    "SHORT_INTEREST_RATIO_FAMILY_KEY",
    "SHORT_INTEREST_UNIVERSE_RULE",
    "CrossSectionalFamilyAdapter",
    "CrossSectionalLivePanel",
    "CrossSectionalPanelUnavailableError",
    "CrossSectionalUniverseDriftError",
    "UnknownCrossSectionalFamilyError",
    "UnknownCrossSectionalSpecError",
    "build_cbop_live_panel",
    "build_cbop_specs",
    "build_crypto_live_panel",
    "build_lazy_prices_jaccard_full_specs",
    "build_lazy_prices_live_panel",
    "build_noa_neutral_live_panel",
    "build_noa_neutral_live_specs",
    "build_short_interest_live_panel",
    "build_short_interest_ratio_specs",
    "config_fingerprint",
    "config_identity",
    "get_family_adapter",
    "quality_sample_fingerprint",
    "register_family",
    "registered_family_keys",
    "resolve_spec",
    "spec_fingerprint",
    "spec_identity",
]
