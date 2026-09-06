"""INDEPENDENT VERIFICATION of the period-end marking-the-close run.

Re-derives ONE spec's per-event number end to end from raw primitives, in code
that shares nothing with cross_sectional_quarter_end_marking.py except the
price frames themselves: the eligible set, the ranking variable, the quintile
cut, the equal leg weights, the gross day return, the EDGE turnover charge and
the borrow accrual are all recomputed here from the formulas in the source
paper and in cross_sectional.py's own documented conventions, then compared
against the committed run JSON.

Run from backend/ with
    ./venv/bin/python data/research_runs/verify_quarter_end_marking.py

This exists because CLAUDE.md requires a key number to be re-derived by hand
from primitives before any deliverable is called done, and because a family
whose whole point is "the effect might be the bid-ask spread" cannot be trusted
on a cost number it computed itself once.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}."
    )

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_quarter_end_marking import (
    QEM_H126_SESSIONS,
    QEM_PRICE_PADDING_CALENDAR_DAYS,
    QEM_RANK_FRACTION,
)
from app.services.research_lab.sp500_membership_history import (
    get_universe_over,
    was_member,
)
from app.services.research_lab.spread_estimator import (
    build_calibrated_half_spread_frame,
)

JSON_PATH = _BACKEND / "data" / "research_runs" / "quarter_end_marking_2026-09-06.json"

# The spec and the event this script re-derives. Chosen before looking at any
# result: the S&P 500 day0 arm on the paper's own six-month ranking window, at
# the year-end the paper's own test is about, in a year comfortably inside the
# membership window.
UNIVERSE = "sp500"
PATTERN_ID = "qem_year_end_day0_perf_h126"
EVENT_YEAR = 2019

START = date(2015, 1, 7)  # sp500_membership_history.MEMBERSHIP_DATA_START
END = date(2026, 9, 5)

# cross_sectional.py's own constants, restated so this script does not import
# the module whose arithmetic it is checking.
FINANCING_DAYS_PER_YEAR = 365.0
FINANCING_BPS_PER_YEAR = 17.0  # borrow_cost.financing_bps_for_long_short_book(34.0)
FLAT_FALLBACK_BPS = 5.0  # DEFAULT_XS_COST_BPS


def main() -> int:
    payload = json.loads(JSON_PATH.read_text())
    universe = next(u for u in payload["universes"] if u["universe"] == UNIVERSE)
    evaluation = next(e for e in universe["evaluations"] if e["pattern_id"] == PATTERN_ID)

    tickers = get_universe_over(START, END)
    frames, _missing = provider_frames(tickers)
    close = frames["close"]
    half_spread, _report = build_calibrated_half_spread_frame(
        frames["open"], frames["high"], frames["low"], close, calibration_start=pd.Timestamp(START)
    )

    index = close.index
    december = index[(index.year == EVENT_YEAR) & (index.month == 12)]
    d0 = december[-1]
    position = int(index.searchsorted(d0))
    d_minus_1 = index[position - 1]
    print(f"event: d(-1)={d_minus_1.date()}  d(0)={d0.date()}")

    # ---- 1. the eligible cross-section on d(-1), from the real gate --------
    formation_day = d_minus_1.date()
    row = close.loc[d_minus_1]
    eligible = [t for t in close.columns if was_member(t, formation_day) and np.isfinite(row[t])]
    print(f"eligible on d(-1): {len(eligible)}")

    # ---- 2. PERF, recomputed from the two raw closes ----------------------
    base = close.iloc[position - 1 - QEM_H126_SESSIONS]
    perf = (row[eligible] / base[eligible]) - 1.0
    perf = perf[np.isfinite(perf) & np.isfinite(base[eligible]) & (base[eligible] > 0.0)]
    print(f"finite PERF: {len(perf)}   min {perf.min():+.4f}  max {perf.max():+.4f}")

    # ---- 3. the quintile cut, with the harness's own tie-break ------------
    n_leg = max(1, int(len(perf) * QEM_RANK_FRACTION))
    ordered = perf.sort_index().sort_values(ascending=False, kind="mergesort")
    longs = list(ordered.index[:n_leg])
    shorts = list(ordered.index[-n_leg:])
    assert not set(longs) & set(shorts), "legs must be disjoint"
    print(f"leg size {n_leg}; top name {longs[0]} ({perf[longs[0]]:+.4f}), "
          f"bottom name {shorts[-1]} ({perf[shorts[-1]]:+.4f})")

    # ---- 4. equal weights, and the gross day-0 return ---------------------
    weight = 1.0 / n_leg
    day_returns = (close.loc[d0] / close.loc[d_minus_1]) - 1.0

    def leg_return(names: list[str]) -> float:
        """cross_sectional._leg_weighted_return at equal weights: mean over the
        members that actually printed, weights renormalised to the survivors."""
        vals = day_returns.reindex(names).dropna()
        if vals.empty:
            return 0.0
        return float((vals * weight).sum() / (weight * len(vals)))

    gross = leg_return(longs) - leg_return(shorts)
    print(f"gross day-0 winner-minus-loser return: {gross:+.8f}")

    # ---- 5. the EDGE turnover charge, on ENTRY and again on EXIT ----------
    # ENTRY, at the d(-1) formation: the previous session's formation had an
    # all-NaN signal and was skipped, so the book was FLAT going in and the
    # traded notional is |w| for every member, priced off d(-1)'s half-spread
    # row. EXIT, at the d(0) formation: the signal is NaN again, so the book
    # goes back to flat and the same |w| is traded, this time priced off
    # d(0)'s row. cross_sectional.py charges a formation's turnover on that
    # formation's FIRST REALIZATION DAY, so the entry charge lands on d(0) and
    # the exit charge lands on d(1) — which is why an event's profit and loss
    # spans [d(0), d(1)] and not d(0) alone.
    flat_rate = FLAT_FALLBACK_BPS / 10_000.0

    def turnover_charge(row: pd.Series) -> tuple[float, float]:
        charged = 0.0
        fallback = 0.0
        for name in longs + shorts:
            hs = row.get(name, np.nan)
            if np.isfinite(hs) and hs > 0.0:
                charged += weight * float(hs)
            else:
                charged += weight * flat_rate
                fallback += weight
        return charged, fallback

    entry_cost, entry_fallback = turnover_charge(half_spread.loc[d_minus_1])
    exit_cost, exit_fallback = turnover_charge(half_spread.loc[d0])
    print(f"entry charge (at d(-1), lands on d(0)): {entry_cost:.8f}  (fallback {entry_fallback:.4f})")
    print(f"exit  charge (at d(0),  lands on d(1)): {exit_cost:.8f}  (fallback {exit_fallback:.4f})")

    # ---- 6. the borrow accrual over the calendar days actually elapsed ----
    # Only on d(0): the book is flat from the close of d(0), and
    # cross_sectional.py accrues financing on the formation's GROSS NOTIONAL
    # HELD, which is exactly 0.0 for the skipped formation at d(0).
    gross_notional = 2.0  # 1.0 long + 1.0 short, a fully formed long_short book
    per_day = (FINANCING_BPS_PER_YEAR / 10_000.0) / FINANCING_DAYS_PER_YEAR
    calendar_days = float((d0 - d_minus_1).days)
    financing = per_day * gross_notional * calendar_days
    print(f"financing over {calendar_days:.0f} calendar days: {financing:.10f}")

    day0_net = gross - entry_cost - financing
    day1_net = -exit_cost
    net = (1.0 + day0_net) * (1.0 + day1_net) - 1.0
    print(f"d(0) net {day0_net:+.8f}   d(1) net {day1_net:+.8f}")
    print(f"NET entry-to-exit event return, hand-derived: {net:+.8f}")

    # ---- 7. against the committed run ------------------------------------
    dates = evaluation["events"]["event_dates"]
    returns = evaluation["events"]["event_returns"]
    key = d0.date().isoformat()
    if key not in dates:
        print(f"FAIL: the committed run has no event dated {key} for {PATTERN_ID}")
        return 1
    reported = float(returns[dates.index(key)])
    print(f"NET entry-to-exit event return, committed run: {reported:+.8f}")
    difference = abs(net - reported)
    print(f"absolute difference: {difference:.3e}")

    ok = difference < 1e-9
    print("VERDICT:", "MATCH" if ok else "MISMATCH")

    # ---- 8. the database row must agree with the committed JSON -----------
    # A committed report describing rows no database backs is exactly the
    # failure this project has already had twice (N-PORT, the first tax-loss
    # run). Checking the two against each other here, from a separate process,
    # is what makes "persisted" mean something.
    ok = check_persistence(payload) and ok
    return 0 if ok else 1


def check_persistence(payload: dict) -> bool:
    from sqlalchemy import select

    from app.config import settings
    from app.db import SessionLocal
    from app.models.cross_sectional_trial_result import CrossSectionalTrialResult

    print()
    print(f"database: {settings.database_url}")
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(CrossSectionalTrialResult).where(
                    CrossSectionalTrialResult.run_tag == payload["run_tag"]
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()

    expected = sum(len(u["evaluations"]) for u in payload["universes"])
    print(f"rows for run_tag={payload['run_tag']!r}: {len(rows)} (expected {expected})")
    if len(rows) != expected:
        print("FAIL: row count does not match the committed JSON")
        return False

    n_local = int(payload["n_trials"])
    by_key = {(r.family_key, r.trial_id): r for r in rows}
    mismatches = 0
    for universe in payload["universes"]:
        for evaluation in universe["evaluations"]:
            row = by_key.get((universe["family_key"], evaluation["pattern_id"]))
            if row is None:
                print(f"FAIL: no row for {universe['family_key']}/{evaluation['pattern_id']}")
                mismatches += 1
                continue
            if abs(row.sharpe_annualized - evaluation["sharpe_annualized"]) > 1e-12:
                print(
                    f"FAIL: {row.trial_id} Sharpe {row.sharpe_annualized} != JSON "
                    f"{evaluation['sharpe_annualized']}"
                )
                mismatches += 1
            if row.n_trials != n_local:
                print(f"FAIL: {row.trial_id} n_trials {row.n_trials} != {n_local}")
                mismatches += 1
            # The harness's OWN deflated Sharpe (computed inside
            # screen_cross_sectional_universe) must equal the ladder's entry at
            # n_local, which this family recomputes separately. Two independent
            # paths to the same number.
            ladder = evaluation["dsr_by_n"].get(str(n_local))
            if row.dsr is None or ladder is None:
                if row.dsr is not ladder:
                    print(f"FAIL: {row.trial_id} DSR None-ness differs ({row.dsr} vs {ladder})")
                    mismatches += 1
            elif abs(float(row.dsr) - float(ladder)) > 1e-9:
                print(f"FAIL: {row.trial_id} harness DSR {row.dsr} != ladder@{n_local} {ladder}")
                mismatches += 1
    print("PERSISTENCE VERDICT:", "MATCH" if mismatches == 0 else f"{mismatches} MISMATCHES")
    return mismatches == 0


def provider_frames(tickers: list[str]):
    provider = YFinanceProvider()
    padded = START - timedelta(days=QEM_PRICE_PADDING_CALENDAR_DAYS)
    return provider.get_daily_ohlcv(tickers, padded, END)


if __name__ == "__main__":
    raise SystemExit(main())
