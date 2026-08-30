"""POST-HOC diagnostics for the jump-drift run. NOT pre-registered.

Two questions the pre-registered run leaves open, both of which can only
WEAKEN a claim, never create one:

 1. COST ATTRIBUTION. Every one of the 24 specs came out negative. Is that
    "no signal", or "a signal smaller than the EDGE cost model's charge"?
    Re-running the identical 24 specs at ZERO cost separates the two. This
    adds no spec, changes no threshold, and its output is reported as an
    attribution, never as a result.

 2. MARKET-TIMING CONFOUND in the event study. The pre-registered baseline is
    each ticker's OWN unconditional forward return, which removes that
    stock's drift but NOT the market's time variation — and jumps cluster in
    bad market periods. A cross-sectionally demeaned (market-neutral) version
    of the same event study says how much of the measured effect is the
    market rather than the stock.
"""

import json
import logging
import pickle
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_jump_drift import (
    EVENT_STUDY_BOOTSTRAP_DRAWS,
    EVENT_STUDY_HORIZONS_DAYS,
    EVENT_STUDY_MIN_BASELINE_DAYS,
    EVENT_STUDY_SEED,
    JUMP_DRIFT_SPECS,
    JUMP_PRICE_PADDING_CALENDAR_DAYS,
    JUMP_WINDOWS_DAYS,
    JUMP_Z_CRITICAL,
    detect_jump_days,
    forward_cumulative_log_return,
    log_returns,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("diag")

CLOSE_PICKLE = "/tmp/jump_drift_close.pkl"
OUT = "/tmp/jump_drift_diagnostics.json"


def market_adjusted_event_study(close: pd.DataFrame, window: int, z_crit: float) -> list[dict]:
    """The pre-registered event study with ONE change: each day's forward
    cumulative return has that day's CROSS-SECTIONAL MEAN forward return
    subtracted before anything else, so what is measured is a market-neutral
    abnormal return. Everything downstream — the per-ticker baseline, the
    per-ticker bootstrap, the seed — is identical."""
    returns = log_returns(close)
    jumps = detect_jump_days(close, window, z_crit)
    rng = np.random.default_rng(EVENT_STUDY_SEED)
    cells: list[dict] = []

    for horizon in EVENT_STUDY_HORIZONS_DAYS:
        forward = forward_cumulative_log_return(returns, horizon)
        forward = forward.sub(forward.mean(axis=1), axis=0)
        for direction, sign in (("up", 1.0), ("down", -1.0)):
            demeaned_events: list[np.ndarray] = []
            pools: list[np.ndarray] = []
            for ticker in close.columns:
                fwd = forward[ticker]
                jump = jumps[ticker]
                is_jump = jump.notna()
                is_event = is_jump & (np.sign(jump.fillna(0.0)) == sign) & fwd.notna()
                pool = fwd[(~is_jump) & fwd.notna()].to_numpy(dtype=float)
                if pool.size < EVENT_STUDY_MIN_BASELINE_DAYS:
                    continue
                events = fwd[is_event].to_numpy(dtype=float)
                if events.size == 0:
                    continue
                mean_baseline = float(pool.mean())
                demeaned_events.append(events - mean_baseline)
                pools.append(pool - mean_baseline)
            if not demeaned_events:
                continue
            demeaned = np.concatenate(demeaned_events)
            observed = float(demeaned.mean())
            null_sums = np.zeros(EVENT_STUDY_BOOTSTRAP_DRAWS)
            for ev, pool in zip(demeaned_events, pools, strict=True):
                draws = rng.integers(0, pool.size, size=(EVENT_STUDY_BOOTSTRAP_DRAWS, ev.size))
                null_sums += pool[draws].sum(axis=1)
            null = null_sums / demeaned.size
            exceed = int(np.sum(np.abs(null) >= abs(observed)))
            cells.append(
                {
                    "horizon_days": horizon,
                    "direction": direction,
                    "n_events": int(demeaned.size),
                    "mean_abnormal": observed,
                    "bootstrap_p_value": (1.0 + exceed) / (1.0 + EVENT_STUDY_BOOTSTRAP_DRAWS),
                    "bootstrap_null_std": float(null.std(ddof=1)),
                }
            )
    return cells


if __name__ == "__main__":
    start, end = MEMBERSHIP_DATA_START, date(2026, 8, 29)
    try:
        with open(CLOSE_PICKLE, "rb") as fh:
            close = pickle.load(fh)
        log.info("reused cached close frame %s", close.shape)
    except FileNotFoundError:
        universe = get_universe_over(start, end)
        # The padded start MUST be derived exactly as run_jump_drift_screening
        # derives it, not hardcoded. It was hardcoded to date(2013, 12, 1)
        # until the verification pass of 2026-08-30, one trading day earlier
        # than the production run's 2013-12-03 — so the GROSS column of the run
        # report was computed on a 3204-row frame while the NET column came
        # from a 3203-row one. Consequences were small but real and visible in
        # the report: jump_{cont,rev}_w63_a010_h5 show 139 formations (447
        # skipped) in the gross table against the 138 (448) actually persisted
        # to cross_sectional_trial_results, and four specs' turnover differs in
        # the fourth decimal. Two columns presented side by side must come from
        # one price frame.
        padded_start = start - timedelta(days=JUMP_PRICE_PADDING_CALENDAR_DAYS)
        frames, _missing = YFinanceProvider().get_daily_ohlcv(
            universe, padded_start, end
        )
        close = frames["close"]
        with open(CLOSE_PICKLE, "wb") as fh:
            pickle.dump(close, fh)
        log.info("downloaded close frame %s", close.shape)

    payload: dict = {}

    # (1) zero-cost attribution — identical 24 specs, no turnover charge.
    cfg = CrossSectionalConfig(cost_bps=0.0, cost_model="flat_bps", formation_start=start)
    zero_cost = screen_cross_sectional_universe(
        CrossSectionalData(close=close), JUMP_DRIFT_SPECS, cfg
    )
    payload["zero_cost_results"] = [
        {
            "pattern_id": r.pattern_id,
            "sharpe_annualized": r.sharpe_annualized,
            "n_formations": r.n_formations,
            "n_skipped_formations": r.n_skipped_formations,
            "avg_names_per_leg": r.avg_names_per_leg,
            "n_trading_days": r.n_trading_days,
            "total_turnover": r.total_turnover,
        }
        for r in zero_cost
    ]
    log.info("zero-cost screening done: %d specs", len(zero_cost))

    # (2) market-adjusted event study.
    payload["market_adjusted_event_studies"] = [
        {
            "window": window,
            "z_crit": JUMP_Z_CRITICAL[tag],
            "alpha_tag": tag,
            "cells": market_adjusted_event_study(close, window, JUMP_Z_CRITICAL[tag]),
        }
        for window in JUMP_WINDOWS_DAYS
        for tag in JUMP_Z_CRITICAL
    ]
    log.info("market-adjusted event studies done")

    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    log.info("wrote %s -- DIAGNOSTICS DONE", OUT)
