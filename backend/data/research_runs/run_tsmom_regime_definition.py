"""Records which quarters/dates the PRE-REGISTERED TSMOM regime rule would
have flagged over 2013-2025, as a committed artifact.

INFORMATIONAL ONLY. This script touches the broad-market index series and
NOTHING ELSE. It does not read futures data, does not compute a TSMOM
signal, and does not look at any TSMOM return. Its entire purpose is to make
the pre-registered rule's historical footprint a matter of committed record
BEFORE any TSMOM return exists, so nobody can later claim the split was
chosen to flatter a result.

Run:  python data/research_runs/run_tsmom_regime_definition.py
Writes: data/research_runs/tsmom_regime_definition_2026-09-07.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.config import MAIN_CHECKOUT_BACKEND_DIR
from app.services.research_lab.tsmom_regime_definition import (
    MIN_PRIOR_QUARTERS,
    MOP_EXTREME_TAIL_FRACTION,
    PRIMARY_RULE,
    PRIMARY_RULE_INDEX,
    SECONDARY_DRAWDOWN_THRESHOLD,
    classify_drawdown_regime,
    classify_extreme_market_quarters,
)

BACKEND = Path(__file__).resolve().parents[2]

# The price store is untracked data that lives only in the MAIN checkout, so
# a worktree run must reach across to it rather than find an empty directory
# of its own. app.config.MAIN_CHECKOUT_BACKEND_DIR already resolves exactly
# this (via `git rev-parse --git-common-dir`, with a fallback to the local
# backend/ whenever the answer cannot be established) and is the same
# mechanism that fixed the 2026-09-06 worktree DB-routing bug -- reused here
# rather than reimplemented, so both paths cannot drift apart.
PRICE_FILE = (
    MAIN_CHECKOUT_BACKEND_DIR / "data" / "price_store" / "v1" / "SPY.csv.gz"
)
OUT_FILE = BACKEND / "data" / "research_runs" / "tsmom_regime_definition_2026-09-07.json"

REPORT_START = "2013-01-01"
REPORT_END = "2025-12-31"


def load_broad_market_prices() -> pd.Series:
    """SPY raw close -- the price-return series, dividends deliberately
    excluded, because MOP 2012 Fig. 4 plots TSMOM against the S&P 500 PRICE
    index. See tsmom_regime_definition's module docstring for the full
    citation and the logged deviation (SPY proxying the index itself)."""
    frame = pd.read_csv(PRICE_FILE)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["close"].astype(float).sort_index()


def main() -> None:
    prices = load_broad_market_prices()

    primary = classify_extreme_market_quarters(prices)
    secondary = classify_drawdown_regime(prices)

    in_window = (primary.labels.index >= REPORT_START) & (
        primary.labels.index <= REPORT_END
    )
    primary_rows = [
        {
            "quarter_end": ts.strftime("%Y-%m-%d"),
            "market_quarter_return": round(float(primary.period_returns.loc[ts]), 6),
            "abs_return": round(abs(float(primary.period_returns.loc[ts])), 6),
            "expanding_threshold": (
                None
                if pd.isna(primary.thresholds.loc[ts])
                else round(float(primary.thresholds.loc[ts]), 6)
            ),
            "n_prior_quarters": int(primary.n_prior.loc[ts]),
            "label": str(primary.labels.loc[ts]),
        }
        for ts in primary.labels.index[in_window]
    ]

    # Secondary rule: report contiguous in-regime episodes, not 3000 daily
    # rows -- the episodes are what a reader can actually check by eye.
    secondary_window = secondary.labels.loc[REPORT_START:REPORT_END]
    episodes = []
    current_start = None
    for ts, label in secondary_window.items():
        if label == "extreme" and current_start is None:
            current_start = ts
        elif label != "extreme" and current_start is not None:
            episodes.append((current_start, prev_ts))
            current_start = None
        prev_ts = ts
    if current_start is not None:
        episodes.append((current_start, secondary_window.index[-1]))

    secondary_rows = [
        {
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "trading_days": int(
                ((secondary_window.index >= start) & (secondary_window.index <= end)).sum()
            ),
            "max_drawdown": round(
                float(secondary.period_returns.loc[start:end].max()), 6
            ),
        }
        for start, end in episodes
    ]

    payload = {
        "generated": "2026-09-07",
        "purpose": (
            "Pre-registered TSMOM regime definition -- historical footprint, "
            "INFORMATIONAL ONLY. No TSMOM return series was read, computed, or "
            "in existence when this was generated."
        ),
        "source": (
            "Moskowitz, Ooi & Pedersen, 'Time series momentum', Journal of "
            "Financial Economics 104(2), 2012, pp.228-250. Abstract p.228; "
            "Introduction p.229; Section 4.3 p.238 (Fig. 4, Table 3 Panel C); "
            "Section 4.4 p.240 (the VIX/TED/sentiment extremes, all null); "
            "the 20% tail convention is MOP's own, p.240."
        ),
        "honest_caveat": (
            "MOP 2012 does NOT define a binary crisis regime. Their actual "
            "extreme-markets test is a continuous regression of quarterly TSMOM "
            "returns on the market return and the SQUARED market return (Table 3 "
            "Panel C row 1: squared-term coefficient 1.99, t=3.88). The binary "
            "rule recorded here is DERIVED to match the shape of that finding, "
            "using MOP's own 20% tail convention; it is not a quotation. MOP's "
            "own VIX-percentile test was insignificant, which is why a "
            "volatility-percentile rule was deliberately NOT chosen as primary."
        ),
        "primary_rule": {
            "name": PRIMARY_RULE,
            "index": PRIMARY_RULE_INDEX,
            "price_file": str(PRICE_FILE),
            "tail_fraction": MOP_EXTREME_TAIL_FRACTION,
            "min_prior_quarters_burn_in": MIN_PRIOR_QUARTERS,
            "two_sided": True,
            "contemporaneous_not_tradeable": True,
            "threshold_window": "expanding, strictly-prior quarters only",
            "price_history_start": prices.index[0].strftime("%Y-%m-%d"),
            "price_history_end": prices.index[-1].strftime("%Y-%m-%d"),
            "n_extreme_in_window": sum(
                1 for r in primary_rows if r["label"] == "extreme"
            ),
            "n_normal_in_window": sum(1 for r in primary_rows if r["label"] == "normal"),
            "n_unclassified_in_window": sum(
                1 for r in primary_rows if r["label"] == "unclassified"
            ),
            "quarters": primary_rows,
        },
        "secondary_rule_non_mop": {
            "name": secondary.rule_name,
            "drawdown_threshold": SECONDARY_DRAWDOWN_THRESHOLD,
            "note": (
                "One-sided 'crisis alpha' framing. NOT MOP's claim. Recorded for "
                "completeness and because it is pointwise-causal, unlike the "
                "primary rule."
            ),
            "episodes": secondary_rows,
        },
    }

    OUT_FILE.write_text(json.dumps(payload, indent=2))
    print(f"wrote {OUT_FILE}")
    print(
        f"primary: {payload['primary_rule']['n_extreme_in_window']} extreme / "
        f"{payload['primary_rule']['n_normal_in_window']} normal / "
        f"{payload['primary_rule']['n_unclassified_in_window']} unclassified quarters "
        f"in {REPORT_START}..{REPORT_END}"
    )
    for row in primary_rows:
        if row["label"] == "extreme":
            print(
                f"  EXTREME {row['quarter_end']}  return {row['market_quarter_return']:+.4f}"
                f"  threshold {row['expanding_threshold']}"
            )
    print(f"secondary drawdown episodes: {len(secondary_rows)}")
    for ep in secondary_rows:
        print(
            f"  DD {ep['start']} .. {ep['end']}  ({ep['trading_days']} days, "
            f"max {ep['max_drawdown']:.4f})"
        )


if __name__ == "__main__":
    main()
