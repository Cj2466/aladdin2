"""Hand-reconstructed 'D1-final, pre-D2' state of cross_sectional.py, for
independent regression verification ONLY (not part of the real codebase).

Built by taking the real committed pre-D1 baseline (git 52a453a) and
porting in D1's real, currently-uncommitted additions (CrossSectionalData.
market_cap, CrossSectionalSpec.leg_weighting, _resolve_leg_weights,
_apply_weight_cap, FormationRecord's *_value_weight_fallback fields,
CrossSectionalScreeningResult's n_value_weighted_legs/
n_value_weight_fallbacks) verbatim from the CURRENT (D1+D2) file, while
KEEPING the baseline's single-stream, non-overlapping, no-delisting-
imputation run_cross_sectional_backtest loop untouched (i.e. deliberately
NOT porting in D2's cohort_formation_days / impute_delisting_returns
machinery). This lets D1's real family (ROUND_D1_FAMILY, which needs
market_cap + leg_weighting="value" and therefore cannot run against the
true pre-D1 baseline at all) be replayed under a harness that has D1's
capability but genuinely lacks D2's new code paths, so its output can be
diffed byte-for-byte against the current (D1+D2, options left at default)
harness's output on the exact same data.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import was_member

DEFAULT_XS_COST_BPS = 5.0
DEFAULT_MIN_NAMES_PER_LEG = 5
MIN_REPLAY_TRADING_DAYS = 60
MAX_WEIGHT_MULTIPLE = 3.0

MembershipFn = Callable[[str, date], bool]


@dataclass(frozen=True)
class CrossSectionalData:
    close: pd.DataFrame
    open: pd.DataFrame | None = None
    volume: pd.DataFrame | None = None
    market_cap: pd.DataFrame | None = None


def validate_cross_sectional_data(data: CrossSectionalData) -> None:
    for name, frame in (("open", data.open), ("volume", data.volume), ("market_cap", data.market_cap)):
        if frame is None:
            continue
        if not frame.index.equals(data.close.index) or not frame.columns.equals(data.close.columns):
            raise ValueError(f"CrossSectionalData.{name} is not aligned with close.")


SignalFn = Callable[[CrossSectionalData], pd.Series]


@dataclass(frozen=True)
class CrossSectionalSpec:
    pattern_id: str
    family: str
    citation: str
    signal_fn: SignalFn
    lookback_days: int
    holding_days: int
    portfolio: Literal["long_short", "long_universe_hedged"]
    rank_fraction: float
    requires_open: bool = False
    requires_volume: bool = False
    requires_market_cap: bool = False
    leg_weighting: Literal["magnitude", "value"] = "magnitude"
    # D2's field intentionally OMITTED here (this is the "D1-final" state).


@dataclass
class CrossSectionalConfig:
    cost_bps: float = DEFAULT_XS_COST_BPS
    min_names_per_leg: int = DEFAULT_MIN_NAMES_PER_LEG
    formation_start: date | None = None
    # D2's impute_delisting_returns / imputed_delisting_return intentionally
    # OMITTED here.


@dataclass
class FormationRecord:
    date: pd.Timestamp
    n_eligible: int
    long_tickers: list[str] = field(default_factory=list)
    short_tickers: list[str] = field(default_factory=list)
    turnover: float = 0.0
    skipped_reason: str | None = None
    long_leg_value_weight_fallback: bool = False
    short_leg_value_weight_fallback: bool = False


@dataclass
class CrossSectionalBacktestResult:
    status: Literal["ok", "insufficient_history", "no_valid_formations"]
    daily_returns: pd.Series
    formations: list[FormationRecord] = field(default_factory=list)
    total_cost: float = 0.0


def select_leg_tickers(signal: pd.Series, rank_fraction: float) -> tuple[list[str], list[str]]:
    clean = signal.dropna()
    clean = clean[np.isfinite(clean)]
    n = len(clean)
    if n == 0:
        return [], []
    n_leg = max(1, int(n * rank_fraction))
    ordered = clean.sort_index().sort_values(ascending=False, kind="mergesort")
    top = list(ordered.index[:n_leg])
    bottom = list(ordered.index[-n_leg:])
    return top, bottom


MIN_RELATIVE_WEIGHT_FRACTION = 0.1


def _apply_weight_cap(raw: dict[str, float]) -> dict[str, float]:
    total = sum(raw.values())
    weights = {t: w / total for t, w in raw.items()}
    equal_share = 1.0 / len(weights)
    cap = MAX_WEIGHT_MULTIPLE * equal_share
    for _ in range(len(weights)):
        over = {t: w for t, w in weights.items() if w > cap}
        if not over:
            break
        excess_to_redistribute = sum(w - cap for w in over.values())
        under = {t: w for t, w in weights.items() if w <= cap}
        under_total = sum(under.values())
        for t in over:
            weights[t] = cap
        if under_total > 0.0:
            for t in under:
                weights[t] += excess_to_redistribute * (under[t] / under_total)
    return weights


def _leg_weights(tickers: list[str], signal: pd.Series, *, higher_is_stronger: bool) -> dict[str, float]:
    if not tickers:
        return {}
    if len(tickers) == 1:
        return {tickers[0]: 1.0}

    values = signal.reindex(tickers)
    boundary = values.min() if higher_is_stronger else values.max()
    excess = (values - boundary) if higher_is_stronger else (boundary - values)
    excess = excess.clip(lower=0.0)
    spread = float(excess.max())
    equal_share = 1.0 / len(tickers)
    if spread <= 0.0 or not np.isfinite(spread):
        return {t: equal_share for t in tickers}

    floor = spread * MIN_RELATIVE_WEIGHT_FRACTION
    raw = {t: max(float(excess[t]), floor) for t in tickers}
    return _apply_weight_cap(raw)


def _resolve_leg_weights(
    tickers: list[str],
    signal: pd.Series,
    *,
    higher_is_stronger: bool,
    leg_weighting: Literal["magnitude", "value"],
    market_cap: pd.Series | None,
) -> tuple[dict[str, float], bool]:
    if leg_weighting != "value" or len(tickers) <= 1:
        return _leg_weights(tickers, signal, higher_is_stronger=higher_is_stronger), False

    caps = None if market_cap is None else market_cap.reindex(tickers)
    usable = caps is not None and bool(caps.notna().all()) and bool((caps > 0.0).all())
    if not usable:
        return _leg_weights(tickers, signal, higher_is_stronger=higher_is_stronger), True

    raw = {t: float(caps[t]) for t in tickers}
    return _apply_weight_cap(raw), False


def _target_weights(
    long_weights: dict[str, float], short_weights: dict[str, float], portfolio: str, eligible: list[str]
) -> dict[str, float]:
    weights: dict[str, float] = {}
    for t, w in long_weights.items():
        weights[t] = weights.get(t, 0.0) + w
    if portfolio == "long_universe_hedged":
        if long_weights:
            w_short = 1.0 / len(eligible)
            for t in eligible:
                weights[t] = weights.get(t, 0.0) - w_short
    else:
        for t, w in short_weights.items():
            weights[t] = weights.get(t, 0.0) - w
    return weights


def _turnover(old: dict[str, float], new: dict[str, float]) -> float:
    tickers = set(old) | set(new)
    return float(sum(abs(new.get(t, 0.0) - old.get(t, 0.0)) for t in tickers))


def _leg_weighted_return(day_returns: pd.Series, leg_weights: dict[str, float]) -> float:
    if not leg_weights:
        return 0.0
    vals = day_returns.reindex(list(leg_weights.keys()))
    survivors = vals.dropna()
    if survivors.empty:
        return 0.0
    total_weight = sum(leg_weights[t] for t in survivors.index)
    if total_weight <= 0.0:
        return 0.0
    return float(sum(leg_weights[t] * survivors[t] for t in survivors.index) / total_weight)


def run_cross_sectional_backtest(
    data: CrossSectionalData,
    spec: CrossSectionalSpec,
    config: CrossSectionalConfig,
    membership_fn: MembershipFn | None = None,
) -> CrossSectionalBacktestResult:
    """D1-final single-stream replay (baseline's original loop, D2's
    overlapping-cohort / delisting-imputation machinery NOT present)."""
    validate_cross_sectional_data(data)
    if spec.requires_open and data.open is None:
        raise ValueError(f"{spec.pattern_id} requires daily Open data (CrossSectionalData.open is None).")
    if spec.requires_volume and data.volume is None:
        raise ValueError(f"{spec.pattern_id} requires daily Volume data (CrossSectionalData.volume is None).")
    if spec.requires_market_cap and data.market_cap is None:
        raise ValueError(f"{spec.pattern_id} requires point-in-time market cap.")
    if spec.leg_weighting == "value" and data.market_cap is None:
        raise ValueError(f"{spec.pattern_id} has leg_weighting='value' but CrossSectionalData.market_cap is None.")

    is_member = membership_fn if membership_fn is not None else was_member
    index = data.close.index
    n = len(index)

    daily_returns_all = data.close.pct_change(fill_method=None)

    first_formation = spec.lookback_days
    if config.formation_start is not None:
        eligible_positions = np.flatnonzero(index.date >= config.formation_start)  # type: ignore[attr-defined]
        if len(eligible_positions) == 0:
            return CrossSectionalBacktestResult(status="insufficient_history", daily_returns=pd.Series(dtype=float))
        first_formation = max(first_formation, int(eligible_positions[0]))

    if first_formation >= n - 1:
        return CrossSectionalBacktestResult(status="insufficient_history", daily_returns=pd.Series(dtype=float))

    formations: list[FormationRecord] = []
    return_dates: list[pd.Timestamp] = []
    net_returns: list[float] = []
    prev_weights: dict[str, float] = {}
    total_cost = 0.0
    any_formed = False

    for i in range(first_formation, n - 1, spec.holding_days):
        formation_ts = index[i]
        formation_day: date = formation_ts.date()

        formation_close = data.close.iloc[i]
        eligible = [
            t for t in data.close.columns if is_member(t, formation_day) and np.isfinite(formation_close[t])
        ]

        long_tickers: list[str] = []
        short_tickers: list[str] = []
        long_weights: dict[str, float] = {}
        short_weights: dict[str, float] = {}
        long_fallback = False
        short_fallback = False
        skipped_reason: str | None = None

        if eligible:
            row_start = max(0, i + 1 - spec.lookback_days)
            view = CrossSectionalData(
                close=data.close.iloc[row_start : i + 1].loc[:, eligible],
                open=data.open.iloc[row_start : i + 1].loc[:, eligible] if data.open is not None else None,
                volume=(data.volume.iloc[row_start : i + 1].loc[:, eligible] if data.volume is not None else None),
                market_cap=(
                    data.market_cap.iloc[row_start : i + 1].loc[:, eligible] if data.market_cap is not None else None
                ),
            )
            signal = spec.signal_fn(view)
            top, bottom = select_leg_tickers(signal, spec.rank_fraction)
            n_ranked = int(signal.dropna().shape[0])
            n_leg = len(top)
            if n_leg < config.min_names_per_leg:
                skipped_reason = (
                    f"only {n_ranked} ranked names -> leg of {n_leg} < min_names_per_leg="
                    f"{config.min_names_per_leg}"
                )
            elif 2 * n_leg > n_ranked:
                skipped_reason = f"legs would overlap ({n_ranked} ranked names for two legs of {n_leg})"
            else:
                market_cap_row = data.market_cap.iloc[i] if data.market_cap is not None else None
                long_tickers = top
                long_weights, long_fallback = _resolve_leg_weights(
                    top, signal, higher_is_stronger=True, leg_weighting=spec.leg_weighting, market_cap=market_cap_row
                )
                if spec.portfolio == "long_short":
                    short_tickers = bottom
                    short_weights, short_fallback = _resolve_leg_weights(
                        bottom,
                        signal,
                        higher_is_stronger=False,
                        leg_weighting=spec.leg_weighting,
                        market_cap=market_cap_row,
                    )
        else:
            skipped_reason = "no eligible tickers (point-in-time membership + price availability)"

        new_weights = _target_weights(long_weights, short_weights, spec.portfolio, eligible)
        turnover = _turnover(prev_weights, new_weights)
        cost = (config.cost_bps / 10_000.0) * turnover
        total_cost += cost
        prev_weights = new_weights
        if skipped_reason is None:
            any_formed = True

        formations.append(
            FormationRecord(
                date=formation_ts,
                n_eligible=len(eligible),
                long_tickers=long_tickers,
                short_tickers=(eligible if spec.portfolio == "long_universe_hedged" and long_tickers else short_tickers),
                turnover=turnover,
                skipped_reason=skipped_reason,
                long_leg_value_weight_fallback=long_fallback,
                short_leg_value_weight_fallback=short_fallback,
            )
        )

        realized_short_weights = (
            {t: 1.0 / len(eligible) for t in eligible}
            if spec.portfolio == "long_universe_hedged" and long_tickers
            else short_weights
        )

        hold_end = min(i + spec.holding_days, n - 1)
        for j in range(i + 1, hold_end + 1):
            day = daily_returns_all.iloc[j]
            long_ret = _leg_weighted_return(day, long_weights)
            short_ret = _leg_weighted_return(day, realized_short_weights)
            gross = long_ret - short_ret
            net = gross - (cost if j == i + 1 else 0.0)
            return_dates.append(index[j])
            net_returns.append(net)

    daily = pd.Series(net_returns, index=pd.DatetimeIndex(return_dates), dtype=float)
    status: Literal["ok", "insufficient_history", "no_valid_formations"] = (
        "ok" if any_formed else "no_valid_formations"
    )
    return CrossSectionalBacktestResult(status=status, daily_returns=daily, formations=formations, total_cost=total_cost)


@dataclass
class CrossSectionalScreeningResult:
    pattern_id: str
    family: str
    citation: str
    n_formations: int
    n_skipped_formations: int
    avg_names_per_leg: float
    n_trading_days: int
    sharpe_annualized: float
    total_cost_drag: float
    deflated_sharpe: DeflatedSharpeResult
    n_value_weighted_legs: int = 0
    n_value_weight_fallbacks: int = 0


def screen_cross_sectional_universe(
    data: CrossSectionalData,
    specs: list[CrossSectionalSpec],
    config: CrossSectionalConfig,
    membership_fn: MembershipFn | None = None,
) -> list[CrossSectionalScreeningResult]:
    n_trials = len(specs)

    replays: dict[str, CrossSectionalBacktestResult] = {}
    for spec in specs:
        result = run_cross_sectional_backtest(data, spec, config, membership_fn)
        if result.status != "ok":
            continue
        if len(result.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        replays[spec.pattern_id] = result

    sharpes = {pid: sharpe_ratio(res.daily_returns) for pid, res in replays.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {spec.pattern_id: spec for spec in specs}
    results: list[CrossSectionalScreeningResult] = []
    for pattern_id, replay in replays.items():
        spec = spec_by_id[pattern_id]
        formed = [f for f in replay.formations if f.skipped_reason is None]
        skipped = [f for f in replay.formations if f.skipped_reason is not None]
        avg_leg = float(np.mean([len(f.long_tickers) for f in formed])) if formed else 0.0
        dsr = compute_deflated_sharpe(sharpes[pattern_id], replay.daily_returns, n_trials, sigma_sr)

        n_value_weighted_legs = 0
        n_value_weight_fallbacks = 0
        if spec.leg_weighting == "value":
            for f in formed:
                n_value_weighted_legs += 1
                if f.long_leg_value_weight_fallback:
                    n_value_weight_fallbacks += 1
                if spec.portfolio == "long_short":
                    n_value_weighted_legs += 1
                    if f.short_leg_value_weight_fallback:
                        n_value_weight_fallbacks += 1

        results.append(
            CrossSectionalScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                n_formations=len(formed),
                n_skipped_formations=len(skipped),
                avg_names_per_leg=avg_leg,
                n_trading_days=len(replay.daily_returns),
                sharpe_annualized=sharpes[pattern_id],
                total_cost_drag=replay.total_cost,
                deflated_sharpe=dsr,
                n_value_weighted_legs=n_value_weighted_legs,
                n_value_weight_fallbacks=n_value_weight_fallbacks,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results
