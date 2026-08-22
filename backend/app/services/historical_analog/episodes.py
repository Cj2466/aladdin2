from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from app.services.macro_data.base import MacroObservationResult


@dataclass
class ThresholdEpisode:
    start_date: date
    end_date: date
    trading_days: int


def find_crossing_episodes(
    history: list[MacroObservationResult], predicate: Callable[[float], bool]
) -> list[ThresholdEpisode]:
    """Edge-triggered crossing detection — history must be ascending by
    date (get_macro_history_cached already guarantees this). An episode
    starts on the first observation where predicate(value) becomes True
    (including already-True at the very first observation) and continues
    through every immediately following observation where it stays True —
    a multi-month inversion collapses to exactly one episode, not one per
    day it remained crossed."""
    episodes: list[ThresholdEpisode] = []
    in_episode = False
    start: date | None = None
    last: date | None = None
    count = 0

    for obs in history:
        matched = predicate(obs.value)
        if matched and not in_episode:
            in_episode, start, last, count = True, obs.observation_date, obs.observation_date, 1
        elif matched:
            last, count = obs.observation_date, count + 1
        elif in_episode:
            episodes.append(ThresholdEpisode(start, last, count))
            in_episode = False

    if in_episode:
        episodes.append(ThresholdEpisode(start, last, count))  # still ongoing as of the latest data

    return episodes
