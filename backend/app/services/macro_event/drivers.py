"""Stage-A trigger definitions for "Project 2", Layer 2 — Phase 2.2.

THE CENTRAL HONESTY POINT OF THIS ENTIRE MODULE
============================================================================
EVERY THRESHOLD REFERENCED HERE IS AN UNCALIBRATED GUESS. Not one is derived
from a measured distribution, a backtest, or a published result. They could
not be: the data needed to calibrate them does not exist yet, and collecting
it is precisely what Phase 2.2 is for.

The plan's exit criterion for this phase is a human reading a couple of weeks
of REAL trigger rates out of macro_event_detections and deciding whether each
constant is sane — the stated bar being "not zero, not dozens a day". Until
that has happened, a trigger here means "a number crossed a line somebody
guessed", NOT "something significant happened in the world".

Nothing downstream exists. Stage B (the LLM call) is Phase 2.3; the execution
pathway is Phase 2.4. In this phase a trigger writes a database row and does
nothing else. It cannot spend money and it cannot place a trade.

WHY THE DRIVER ROSTER IS IMPORTED RATHER THAN RESTATED
============================================================================
The 13 macro/commodity drivers come from research_lab.macro_beta.MACRO_DRIVERS
— the same frozen roster Layer 1 fit its betas on, which is itself fixed by
that family's pre-registration. They are imported, never re-declared. A second
copy could drift from the first, and the moment it did, a Phase-2.3 candidate
lookup would be keyed on a driver_id that Layer 1's beta table had never heard
of. THRESHOLDS_BY_DRIVER_ID is asserted complete against that roster at import
time (see the check at the bottom), so adding a 14th driver upstream breaks
loudly here instead of silently going unmonitored.
"""

from dataclasses import dataclass

from app.config import settings
from app.services.research_lab.macro_beta import (
    DRIVER_KIND_PRICE,
    DRIVER_KIND_RATE,
    MACRO_DRIVERS,
)

# --- the three independent Stage-A sources ---------------------------------
# One detection row is written per source per tick, so a tick is
# reconstructible as the rows sharing a detected_at, and each source's trigger
# rate is measurable on its own.
SOURCE_NUMERIC = "numeric"
SOURCE_GDELT = "gdelt"
SOURCE_EDGAR = "edgar"

ALL_SOURCES: tuple[str, ...] = (SOURCE_NUMERIC, SOURCE_GDELT, SOURCE_EDGAR)

# --- metric names, so the calibration query can GROUP BY without JSON parsing
METRIC_DAILY_PCT = "daily_pct_change"
METRIC_DAILY_BPS = "daily_bps_change"
METRIC_GDELT_VOLUME_Z = "article_volume_zscore"
METRIC_GDELT_TONE_SHIFT = "tone_shift"
METRIC_EDGAR_FILING_COUNT = "filing_count"


@dataclass(frozen=True)
class NumericTrigger:
    """One numeric threshold check.

    `kind` decides BOTH how the move is computed and what the threshold's
    units are, and conflating the two is the easiest possible error in this
    file:
      - DRIVER_KIND_PRICE: |simple daily % change|, threshold a FRACTION
        (0.04 == 4%).
      - DRIVER_KIND_RATE:  |daily first difference| in BASIS POINTS,
        threshold in bps (15.0 == 15bp).
    These match macro_beta.levels_to_moves exactly, so a Stage-A move and a
    Layer-1 beta are expressed in the same units and are composable in a later
    phase without a conversion nobody remembers to apply.
    """

    key: str
    kind: str
    threshold: float
    label: str


def _price(key: str, threshold: float, label: str) -> NumericTrigger:
    return NumericTrigger(key=key, kind=DRIVER_KIND_PRICE, threshold=threshold, label=label)


def _rate(key: str, threshold: float, label: str) -> NumericTrigger:
    return NumericTrigger(key=key, kind=DRIVER_KIND_RATE, threshold=threshold, label=label)


def build_driver_triggers() -> dict[str, NumericTrigger]:
    """Threshold per Layer-1 driver_id, read from settings AT CALL TIME.

    Read at call time rather than bound at import so an operator can retune a
    constant via the environment without a code change — which is the entire
    expected outcome of this phase's observation window. Every value is
    snapshotted onto its detection row at check time, so a later retune never
    retroactively rewrites what an already-observed row meant.
    """
    return {
        "oil_uso": _price("oil_uso", settings.event_trigger_oil_uso_daily_pct, "Crude oil (USO)"),
        "gold_gld": _price("gold_gld", settings.event_trigger_gold_gld_daily_pct, "Gold (GLD)"),
        "copper_cper": _price(
            "copper_cper", settings.event_trigger_copper_cper_daily_pct, "Copper (CPER)"
        ),
        "natgas_ung": _price(
            "natgas_ung", settings.event_trigger_natgas_ung_daily_pct, "Natural gas (UNG)"
        ),
        "agri_dba": _price("agri_dba", settings.event_trigger_agri_dba_daily_pct, "Agriculture (DBA)"),
        "broad_commod_dbc": _price(
            "broad_commod_dbc",
            settings.event_trigger_broad_commod_dbc_daily_pct,
            "Broad commodities (DBC)",
        ),
        "china_fxi": _price(
            "china_fxi", settings.event_trigger_china_fxi_daily_pct, "China large-cap (FXI)"
        ),
        # DTWEXBGS is a FRED series but kind=price (an index LEVEL ~118, not a
        # rate), so its threshold is a percentage and NOT basis points. See
        # MacroDriver.kind — this is the one entry where source and kind
        # disagree, and getting it wrong is a 10,000x unit error.
        "dollar_broad": _price(
            "dollar_broad", settings.event_trigger_dollar_broad_daily_pct, "Broad trade-weighted USD"
        ),
        "credit_spread": _rate(
            "credit_spread", settings.event_trigger_credit_spread_daily_bps, "High-yield OAS"
        ),
        "rate_dgs10": _rate(
            "rate_dgs10", settings.event_trigger_rate_dgs10_daily_bps, "10Y Treasury yield"
        ),
        "curve_t10y2y": _rate(
            "curve_t10y2y", settings.event_trigger_curve_t10y2y_daily_bps, "10Y-2Y curve"
        ),
        "real_yield_dfii10": _rate(
            "real_yield_dfii10",
            settings.event_trigger_real_yield_dfii10_daily_bps,
            "10Y TIPS real yield",
        ),
        "breakeven_t10yie": _rate(
            "breakeven_t10yie",
            settings.event_trigger_breakeven_t10yie_daily_bps,
            "10Y breakeven inflation",
        ),
    }


# --- the vol-index complex --------------------------------------------------
#
# All six confirmed LIVE via yfinance 2026-09-01 (^VIX 16.07, ^MOVE 75.32,
# ^SKEW 148.53, ^VVIX 89.52, ^OVX 47.96, ^GVZ 25.13). Zero credentials.
#
# A MEASURED SURPRISE THAT THE SCANNER HAS TO HANDLE: these six do NOT all
# publish on the same schedule. On the live 2026-09-01 pull, ^VIX/^VVIX/^OVX/
# ^GVZ had a bar for 2026-09-01 while ^MOVE and ^SKEW did not (9 rows vs 8) —
# the newest row was NaN for those two. So each symbol's move must be computed
# on its OWN dropna'd series, never by differencing two shared frame rows; the
# latter silently compares mismatched dates or yields NaN. vol_move_pct below
# is written for exactly that.
#
# ^OVX (crude-oil implied vol) is the directly oil-shock-relevant member and is
# why this complex is watched alongside the price drivers rather than instead.
VOL_INDEX_SYMBOLS: dict[str, str] = {
    "vix": "^VIX",
    "move": "^MOVE",
    "skew": "^SKEW",
    "vvix": "^VVIX",
    "ovx": "^OVX",
    "gvz": "^GVZ",
}


def build_vol_index_triggers() -> dict[str, NumericTrigger]:
    """Threshold per vol-index metric key. All six are |daily % change| of the
    index LEVEL, as a fraction.

    ^MOVE quotes in basis points and ^SKEW is an index around 100-150, but a
    PERCENTAGE change is still the meaningful "did this move a lot today"
    measure for all six, so they share one convention rather than each needing
    a bespoke unit. This is a deliberate simplification, and like every other
    number in this module it is unvalidated until the observation window says
    otherwise.
    """
    return {
        "vix": _price("vix", settings.event_trigger_vix_daily_pct, "VIX (equity implied vol)"),
        "move": _price("move", settings.event_trigger_move_daily_pct, "MOVE (rates implied vol)"),
        "skew": _price("skew", settings.event_trigger_skew_daily_pct, "SKEW (tail-risk pricing)"),
        "vvix": _price("vvix", settings.event_trigger_vvix_daily_pct, "VVIX (vol of vol)"),
        "ovx": _price("ovx", settings.event_trigger_ovx_daily_pct, "OVX (crude-oil implied vol)"),
        "gvz": _price("gvz", settings.event_trigger_gvz_daily_pct, "GVZ (gold implied vol)"),
    }


# --- GDELT watched themes ---------------------------------------------------


@dataclass(frozen=True)
class GdeltTheme:
    """One pre-declared, bounded news theme.

    `query` is a literal GDELT DOC 2.0 query string. It is declared here, in
    one place, rather than assembled at call time so that the watch list is
    auditable as a fixed roster — the same "bounded, pre-declared" discipline
    the plan asks for and that every other roster in this project follows.
    """

    key: str
    query: str
    rationale: str


# THE FIVE CATEGORIES ARE THE PLAN'S OWN: energy, military conflict,
# central-bank/monetary policy, trade/sanctions, sovereign debt.
#
# A DELIBERATE, DOCUMENTED DEVIATION FROM THE PLAN'S WORDING
# ---------------------------------------------------------------------------
# The plan specifies "themes chosen from GDELT's own GKG taxonomy, not
# free-text". These ship as free-text keyword queries instead. The reason is
# evidence and scope, not a claim that the taxonomy is unusable:
#
#  * The five keyword queries below were exercised LIVE against the real API
#    during the build (2026-09-01/02). Six of the ten (theme x mode)
#    combinations returned well-formed 56-bucket series; the other four failed
#    ONLY at the transport layer (ECONNRESET / connect timeout / 429), never
#    with a syntax error or a malformed payload — and both modes and three of
#    the five themes were confirmed working. The query SYNTAX is verified.
#  * The GKG `theme:` operator DOES work: `theme:ARMEDCONFLICT` was confirmed
#    live to return a real non-empty series (56 buckets). So GKG themes are a
#    genuinely available option, and an earlier draft of this comment which
#    said the operator was unverified was WRONG and is corrected here.
#
#  * The bogus-theme CONTROL was also run live, and its result is worth
#    recording precisely: `theme:ZZZ_NOT_A_REAL_THEME` returned an EMPTY JSON
#    OBJECT — `{}`, no `timeline` key, no error status, no message. GDELT does
#    NOT announce an unknown theme; it just answers with nothing. That is
#    exactly the silent-death failure mode feared above, and gdelt_provider's
#    parse_timeline shape guard caught it live and raised, rather than
#    reporting it as a quiet theme. The guard is therefore not defensive
#    boilerplate — it is load-bearing against a real, observed behaviour.
#
# So the remaining gap is narrow and purely one of coverage: only ONE GKG theme
# name (ARMEDCONFLICT) has been confirmed live to return data, and mapping the
# five categories below onto specific GKG names would need each of those names
# checked the same way. GDELT's connectivity from this network had degraded to
# near-constant ECONNRESET by the end of the build window, so that sweep was
# not finishable here.
#
# Migrating to GKG themes is therefore a clean, isolated follow-up — only the
# `query` strings below change — and it is now a SAFE one, because a wrong
# theme name fails loudly through the shape guard instead of silently matching
# nothing. It just needs each intended name confirmed live first. Until then
# these keyword queries are the verified option.
#
# Every query is scoped `sourcelang:eng` to keep the volume series comparable
# tick over tick; GDELT monitors 100+ languages and an unscoped query's volume
# would move with which regions' news cycles happened to be awake.
GDELT_THEMES: tuple[GdeltTheme, ...] = (
    GdeltTheme(
        "energy",
        '(oil OR "crude oil" OR opec OR "natural gas" OR refinery OR pipeline) sourcelang:eng',
        "Energy supply shocks — the user's own worked example, and the driver "
        "with the most direct Layer-1 proxies (USO, UNG, ^OVX).",
    ),
    GdeltTheme(
        "military_conflict",
        '(airstrike OR invasion OR ceasefire OR "armed conflict" OR "military strike") '
        "sourcelang:eng",
        "Geopolitical risk — routes into oil, gold and broad risk appetite.",
    ),
    GdeltTheme(
        "monetary_policy",
        '("central bank" OR "interest rate" OR "federal reserve" OR "monetary policy" '
        "OR inflation) sourcelang:eng",
        "Rate-decision channel — the plan's second worked example.",
    ),
    GdeltTheme(
        "trade_sanctions",
        '(sanctions OR tariff OR embargo OR "trade war" OR "export controls") sourcelang:eng',
        "Trade/sanctions shocks — dollar, China and commodity-demand channels.",
    ),
    GdeltTheme(
        "sovereign_debt",
        '("sovereign debt" OR "debt crisis" OR "credit rating" OR bailout OR default) '
        "sourcelang:eng",
        "Sovereign-credit stress — the credit-spread and risk-appetite channel.",
    ),
)


# --- SEC EDGAR watched form types -------------------------------------------
#
# From the plan: "market-moving form types (8-K, SC 13D/G)".
#
# AMENDMENTS ARE INCLUDED DELIBERATELY, and this is a judgement call worth
# stating rather than burying. An amended SC 13D is frequently the market-
# moving event in its own right — it is how a change in an activist holder's
# stake or stated intent becomes public — so watching 13D but not 13D/A would
# miss the follow-up that often matters more than the initial filing. 8-K/A is
# included for symmetry; it is expected to be rare (one of 100 entries on the
# live 2026-09-01 pull).
#
# EACH IS QUERIED SEPARATELY AND EXACT-MATCHED. `type=` is a PREFIX match
# upstream — verified live: `type=SC 13` returned only SC 13E3 filings, a
# different form type entirely — so sec_edgar_rss_provider re-filters every
# entry against the exact `<category term>`. Nothing here may be shortened to
# a prefix in the hope of saving a request.
EDGAR_WATCHED_FORM_TYPES: tuple[str, ...] = (
    "8-K",
    "8-K/A",
    "SC 13D",
    "SC 13D/A",
    "SC 13G",
    "SC 13G/A",
)

# A filing only counts when it names a company in the point-in-time universe.
# The feed carries CIK but NO TICKER (verified live), so the scanner maps via
# edgar_xbrl_provider's existing ticker->CIK map, inverted. This constant is
# the trigger rule: any single in-universe watched filing is a trigger, since
# unlike the numeric sources there is no natural continuous magnitude to
# threshold — "a material-events form was filed by a company we track" is
# already the event.
#
# ALREADY SUSPECTED TOO SENSITIVE, FROM THE VERY FIRST REAL TICK. On the live
# run of 2026-09-01 18:57 UTC this tripped immediately: 6 in-universe 8-Ks
# (Caterpillar, Public Storage, Keurig Dr Pepper, Humana, Medtronic) among the
# 100 most recent 8-K filings, plus one in-universe 8-K/A (Yum Brands). A
# 500-name universe files 8-Ks more or less continuously during business hours,
# so at 1 filing this will very likely fire on most ticks of most weekdays —
# nearer the plan's "dozens a day" failure mode than its "looks sane" bar.
#
# It is deliberately NOT pre-emptively retuned here. The whole design of this
# phase is to observe the honest rate produced by the declared starting guess
# and let a human calibrate against real counts; quietly tightening it now on a
# single observation would substitute one guess for another and destroy the
# comparison. The raw per-filing detail is in every row's raw_metrics_json, so
# the calibration can replay any alternative rule (a higher count, specific
# Item numbers such as 1.01/2.02/5.02 rather than routine 7.01/8.01, or
# ownership forms only) against real observed history.
EDGAR_MIN_IN_UNIVERSE_FILINGS_TO_TRIGGER = 1


# --- import-time completeness check -----------------------------------------
#
# The promise made at the top of this module, actually enforced. If a 14th
# driver is ever added to macro_beta.MACRO_DRIVERS, this raises AT IMPORT
# rather than letting the new driver go silently unmonitored — which is the
# failure mode that matters, because an unmonitored driver looks exactly like
# a driver that never triggers.
_declared = set(build_driver_triggers())
_roster = {d.driver_id for d in MACRO_DRIVERS}
if _declared != _roster:
    raise RuntimeError(
        "macro_event.drivers thresholds are out of sync with macro_beta.MACRO_DRIVERS: "
        f"missing a threshold for {sorted(_roster - _declared)}, "
        f"threshold declared for unknown driver {sorted(_declared - _roster)}"
    )
del _declared, _roster
