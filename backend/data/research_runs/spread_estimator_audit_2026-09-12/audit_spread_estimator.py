#!/usr/bin/env python
"""Independent audit of this project's spread estimator, BEFORE using it on the
whole-market panel (owner's instruction 2026-09-12: check the tool itself, both
its form and its internal mechanism, before trusting it).

Method: simulate daily OHLC from a random walk plus a KNOWN bid-ask bounce, then
ask `bidask.edge_rolling` — the estimator's own engine, called exactly as
`spread_estimator.estimate_effective_spread` calls it — what it recovers.
Nothing here reads market data; everything is reproducible from the seeds.

Run: audit_spread_estimator.py            (writes audit_output.json next to it)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from bidask import edge_rolling

HERE = Path(__file__).resolve().parent
WINDOW = 63  # spread_estimator.COST_MODEL_WINDOW_DAYS


def simulate(true_half_spread: float, *, n_days: int = 400, ticks: int = 390,
             daily_vol: float = 0.02, seed: int = 7, price0: float = 50.0) -> pd.DataFrame:
    """Daily OHLC built from `ticks` intraday trades a day. The efficient price is a
    random walk; every trade prints at the efficient price times (1 +/- s), i.e. at
    the bid or the ask, which is the bounce the estimator is designed to detect."""
    rng = np.random.default_rng(seed)
    rows = []
    price = price0
    for _ in range(n_days):
        efficient = price * np.exp(np.cumsum(rng.normal(0, daily_vol / np.sqrt(ticks), ticks)))
        observed = efficient * (1.0 + rng.choice([-1.0, 1.0], ticks) * true_half_spread)
        rows.append((observed[0], observed.max(), observed.min(), observed[-1]))
        price = efficient[-1]
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=pd.bdate_range("2016-01-04", periods=n_days))


def recovered_bps(frame: pd.DataFrame, *, sign: bool) -> float:
    series = edge_rolling(frame, window=WINDOW, sign=sign).dropna()
    if sign:
        series = series.clip(lower=0)
    return float(series.median() * 10_000)


def main() -> int:
    out: dict = {"window_days": WINDOW, "engine": "bidask.edge_rolling"}

    out["transfer_function"] = [
        {"true_full_bps": 2 * hs, "recovered_sign_false_bps": recovered_bps(simulate(hs / 10_000), sign=False),
         "recovered_sign_true_bps": recovered_bps(simulate(hs / 10_000), sign=True)}
        for hs in (0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500)
    ]
    out["noise_floor_vs_volatility"] = [
        {"daily_vol": vol, "ticks_per_day": ticks,
         "floor_bps_by_seed": [recovered_bps(simulate(0.0, daily_vol=vol, ticks=ticks, seed=s), sign=False)
                               for s in (1, 2, 3)]}
        for ticks in (78, 390, 1000) for vol in (0.02, 0.06)
    ]
    for row in out["noise_floor_vs_volatility"]:
        row["floor_over_vol_bps"] = float(np.mean(row["floor_bps_by_seed"]) / (row["daily_vol"] * 10_000))
    out["volatile_name_sign_comparison"] = [
        {"true_full_bps": 2 * hs, "daily_vol": 0.06,
         "sign_true_bps": recovered_bps(simulate(hs / 10_000, daily_vol=0.06), sign=True),
         "sign_false_bps": recovered_bps(simulate(hs / 10_000, daily_vol=0.06), sign=False)}
        for hs in (5, 25, 50, 100, 200)
    ]
    (HERE / "audit_output.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
