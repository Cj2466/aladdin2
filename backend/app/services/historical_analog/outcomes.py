from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.services.historical_analog.episodes import ThresholdEpisode

PricesFn = Callable[[list[str], date, date], tuple[pd.DataFrame, list[str]]]

HORIZONS_MONTHS: tuple[int, ...] = (6, 12, 18)
# Weekend/holiday tolerance for matching a calendar-day target to the
# nearest actually-traded price — mirrors ACTUAL_COVERAGE_TOLERANCE_DAYS
# in services/risk/stress.py for the same reason.
PRICE_MATCH_TOLERANCE_DAYS = 7


@dataclass
class EpisodeOutcome:
    episode_start: date
    episode_end: date
    trading_days_in_episode: int
    # months -> (return_pct, status); status is "ok" | "too_recent" | "benchmark_unavailable"
    returns: dict[int, tuple[float | None, str]]


def _months_to_days(months: int) -> int:
    # Calendar-day month approximation, matching this codebase's existing
    # convention (BETA_LOOKBACK_YEARS * 365.25 etc.) rather than adding a
    # new date-math dependency for this one use.
    return round(months * 30.44)


def _nearest_price(series: pd.Series | None, target: date) -> float | None:
    if series is None:
        return None
    clean = series.dropna()
    if clean.empty:
        return None
    target_ts = pd.Timestamp(target)
    deltas = abs(clean.index - target_ts)
    nearest_pos = deltas.argmin()
    nearest_date = clean.index[nearest_pos].date()
    if abs((nearest_date - target).days) > PRICE_MATCH_TOLERANCE_DAYS:
        return None
    return float(clean.iloc[nearest_pos])


def compute_episode_outcomes(
    episodes: list[ThresholdEpisode], benchmark: str, prices_fn: PricesFn
) -> list[EpisodeOutcome]:
    """What the benchmark actually did in the 6/12/18 months following each
    episode's start — real historical outcomes, not a prediction. Each
    horizon is tagged with why a value is missing when it is: "too_recent"
    (the horizon hasn't elapsed yet for a recent episode) vs.
    "benchmark_unavailable" (no price data that far back, e.g. a pre-1993
    inversion and SPY's 1993 inception)."""
    if not episodes:
        return []

    today = date.today()
    max_horizon_days = _months_to_days(max(HORIZONS_MONTHS))

    # One fetch spanning every episode, not one fetch per episode — with
    # 40+ episodes over 50 years of history, a per-episode fetch means 40+
    # separate (potentially cold-cache) round-trips to the price provider.
    # get_price_history_cached already handles an arbitrarily wide range
    # as a single upsert-and-cache operation, so this is both faster and
    # simpler than fetching narrow windows piecemeal.
    earliest_start = min(e.start_date for e in episodes)
    latest_window_end = min(
        max(e.start_date for e in episodes) + timedelta(days=max_horizon_days), today
    )
    prices, _missing = prices_fn(
        [benchmark],
        earliest_start - timedelta(days=PRICE_MATCH_TOLERANCE_DAYS),
        latest_window_end + timedelta(days=PRICE_MATCH_TOLERANCE_DAYS),
    )
    series = prices[benchmark] if benchmark in prices.columns else None

    outcomes: list[EpisodeOutcome] = []
    for episode in episodes:
        anchor = _nearest_price(series, episode.start_date)

        returns: dict[int, tuple[float | None, str]] = {}
        for months in HORIZONS_MONTHS:
            target = episode.start_date + timedelta(days=_months_to_days(months))
            if target > today:
                returns[months] = (None, "too_recent")
                continue
            forward = _nearest_price(series, target)
            if anchor is None or forward is None:
                returns[months] = (None, "benchmark_unavailable")
            else:
                returns[months] = (forward / anchor - 1, "ok")

        outcomes.append(
            EpisodeOutcome(
                episode_start=episode.start_date,
                episode_end=episode.end_date,
                trading_days_in_episode=episode.trading_days,
                returns=returns,
            )
        )

    return outcomes
