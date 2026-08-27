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
from datetime import date

from app import dependencies
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    MembershipFn,
)
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


_bootstrap()


__all__ = [
    "CRYPTO_FAMILY_KEY",
    "CRYPTO_UNIVERSE_RULE",
    "CrossSectionalFamilyAdapter",
    "CrossSectionalLivePanel",
    "CrossSectionalPanelUnavailableError",
    "UnknownCrossSectionalFamilyError",
    "UnknownCrossSectionalSpecError",
    "build_crypto_live_panel",
    "config_fingerprint",
    "config_identity",
    "get_family_adapter",
    "register_family",
    "registered_family_keys",
    "resolve_spec",
    "spec_fingerprint",
    "spec_identity",
]
