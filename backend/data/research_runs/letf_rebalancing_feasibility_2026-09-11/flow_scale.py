"""FEASIBILITY-ONLY flow-scale calculation (Q5 of FEASIBILITY_MEMO_2026-09-11.md).

For each underlying (S&P 500 / SPY, Nasdaq-100 / QQQ, Russell 2000 / IWM,
Semiconductors / SOXX, Biotech / XBI, Gold Miners / GDX), computes the implied
LETF rebalancing dollar demand for a |r| = 1% and |r| = 2% day using
Sum_i AUM_i * (L_i^2 - L_i), per Cheng & Madhavan (2009)'s formula as quoted
and derived in Shum, Hejazi, Haryanto & Rodier (2016) Eq.(1)-(2)
(RA_t = NAV_{t-1} * (x^2 - x) * r_t), and compares that dollar figure to the
underlying ETF's own mean last-30-minute dollar volume (2025-06-02..2025-06-27
window, from alpaca_minute_sample.json's companion bar pickles). This is a
FLOW-SCALE / LIQUIDITY comparison only -- NO return statistics of any kind are
computed here, per the orchestrator's explicit instruction.

Reads: letf_universe.csv (AUM+leverage), and the *_2025_jun_1Min.pkl bar
files this run's fetch_alpaca_sample.py wrote to the session scratchpad.

Run from backend/ with the venv python (no Alpaca credentials needed --
reads only the already-fetched pickles):
  python data/research_runs/letf_rebalancing_feasibility_2026-09-11/flow_scale.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SCRATCHPAD_BARS = Path(
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "578690ea-ca6c-4d87-9e97-95cd1d64495e/scratchpad/letf_bars"
)

UNDERLYING_ETF = {
    "S&P 500": "SPY",
    "Nasdaq-100": "QQQ",
    "Russell 2000": "IWM",
    "Semiconductors": "SOXX",
    "Biotech": "XBI",
    "Gold Miners": "GDX",
}


def load_universe() -> dict[str, float]:
    """Sum AUM_i * (L_i^2 - L_i) per underlying group, from letf_universe.csv.
    Skips the single-stock out-of-scope row."""
    totals: dict[str, float] = {k: 0.0 for k in UNDERLYING_ETF}
    with open(HERE / "letf_universe.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            underlying = row["underlying"]
            if underlying not in totals:
                continue  # single-stock out-of-scope row
            aum = float(row["aum_usd"])
            l2_minus_l = float(row["leverage_sq_minus_l"])
            totals[underlying] += aum * l2_minus_l
    return totals


def mean_last30min_dollar_volume(ticker: str) -> float | None:
    pkl_path = SCRATCHPAD_BARS / f"{ticker}_2025_jun_1Min.pkl"
    if not pkl_path.exists():
        return None
    df = pd.read_pickle(pkl_path).sort_index()
    dv = df["close"] * df["volume"]
    df = df.assign(dollar_vol=dv)
    daily_last30 = []
    for d in sorted(set(df.index.date)):
        day_df = df[df.index.date == d]
        last30 = day_df.between_time("15:30", "15:59")["dollar_vol"].sum()
        daily_last30.append(float(last30))
    return sum(daily_last30) / len(daily_last30) if daily_last30 else None


def main() -> None:
    coef_totals = load_universe()
    results = {}
    for underlying, etf in UNDERLYING_ETF.items():
        coef = coef_totals[underlying]
        demand_1pct = coef * 0.01
        demand_2pct = coef * 0.02
        mean_last30 = mean_last30min_dollar_volume(etf)
        results[underlying] = {
            "underlying_etf_used_for_volume_comparison": etf,
            "sum_aum_times_l2_minus_l_usd": coef,
            "implied_rebalance_demand_at_1pct_move_usd": demand_1pct,
            "implied_rebalance_demand_at_2pct_move_usd": demand_2pct,
            "underlying_etf_mean_last30min_dollar_volume_usd_2025jun": mean_last30,
            "ratio_demand_1pct_to_etf_last30min_volume": (
                demand_1pct / mean_last30 if mean_last30 else None
            ),
            "ratio_demand_2pct_to_etf_last30min_volume": (
                demand_2pct / mean_last30 if mean_last30 else None
            ),
            "note": (
                "This compares implied LETF rebalancing demand to the "
                "UNDERLYING ETF's own last-30-min dollar volume only, a "
                "LOWER BOUND on available liquidity (real rebalancing trades "
                "the underlying index constituents directly and/or via swaps "
                "with bank counterparties, not the underlying ETF itself -- "
                "Shum et al. 2016 section 5.2.2 find SPY alone cannot "
                "absorb the trades: relative-volume ratios of 1,781%-8,646% "
                "using SPY as the rebalancing vehicle). No constituent-level "
                "closing-auction volume was sourced for this feasibility "
                "pass (see memo 'Things I could not verify')."
            ),
        }
    out_path = HERE / "flow_scale.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
