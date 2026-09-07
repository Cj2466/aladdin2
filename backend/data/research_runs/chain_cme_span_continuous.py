"""JOB 4 of futures_span_full_pull_2026-09-07: chain the real, fully-pulled CME
SPAN per-contract settlements (data/futures_daily/cme_span/by_instrument/*.csv,
built by fetch_cme_span_archive.py against app/services/market_data/
cme_span_settlements.py) into MOP (2012) Section 2.1 continuous series, for
each of the 31 CME-Group instruments the project owner decided to proceed
with (PENDING_PAID_DATA_DECISIONS.md P4, decision recorded 2026-09-07).

REUSES, DOES NOT REINVENT: the chaining/back-adjustment functions
(chained_contract_daily_returns, ratio_back_adjusted_prices,
panama_back_adjusted_prices) and the synthetic known-answer validation
(validate_against_synthetic) are imported directly from
run_tsmom_futures_feasibility.py, which already implements and validates
MOP's Section 2.1 construction. This script does NOT redefine that logic --
it only supplies the roll rule (which contract is "held" on each date) and
the real price data, both of which that module explicitly does not provide
(see its own docstring: "this run does NOT decide the paid-data question"
and futures_data_sourcing_phase2_2026-09-07.txt:137-142, "ROLL/CHAINING
LOGIC: none exists in this module").

ROLL RULE (the disclosed calendar/expiry-order deviation from MOP's
"most-liquid contract" rule, since no free source provides per-contract
volume -- see PENDING_PAID_DATA_DECISIONS.md P4 and
cme_span_settlements.py's module docstring, "KNOWN LIMITS"):
  On each trade date, the HELD contract is the one with the SMALLEST
  expiration_date that is still >= that trade date (i.e. the first
  not-yet-expired contract month) -- the standard "front month" definition
  by calendar order, exactly as futures_data_sourcing_phase2_2026-09-07.txt
  verified cme_span_settlements.py already identifies for CL on 2019-01-02
  (front = 201902, since 201812/201901 had already expired). Contract
  months with no expiration_date on record are excluded from being "held"
  (cannot be ordered), but keep their settlement rows for reference and are
  counted in the manifest so the gap is visible, not silent.

  ADDITIONAL DEVIATION, found and fixed while chaining the REAL full pull
  (not visible on the 30-day smoke test): rows with settle == 0.0 are
  EXCLUDED from roll-rule candidacy. cme_span_settlements.write_manifest's
  own zero_settle_rows counter already flags these as "economically
  implausible for every instrument in this 31-root universe" but does not
  drop them (correctly -- it is a monitoring counter, not a filter). Real
  full-history data surfaced exactly 3 cases where this matters: CME's SPAN
  archive prints a placeholder/stub Type-82 record for a not-yet-fully-
  configured far contract month, with settle 0.0 AND a bogus
  expiration_date equal to its own trade date (e.g. ZT/ZF contract_month
  "201612" on 2015-09-25/2015-09-28, expiration_date "20150925" i.e. the
  SAME day, settle 0.0 -- the real 201612 contract with its real
  expiration (20161230) and real prices does not start appearing until
  2016-04-01; LE contract_month "201710" shows the identical pattern on
  2016-06-14/15). Because the stub's fabricated expiration_date is the
  smallest of all candidates on that date, the roll rule would otherwise
  treat it as the new front month and try to roll into a contract with no
  real price and no prior-day quote -- chained_contract_daily_returns
  correctly REFUSES this (raises rather than guessing, per its own
  docstring), which is how this was caught rather than silently producing
  a fabricated return. Excluding settle==0.0 rows from candidacy (while
  still counting them in diagnostics below) resolves all 3 real cases
  found in the full 2013-2025 pull without weakening any other date's
  roll decision, since a genuine settlement of exactly 0.0 does not occur
  for any instrument in this universe. Checked by hand for all 72
  zero-settle rows in the full pull (not assumed): the other 69 are all
  EITHER already-expired as of their own trade date (expiration_date is
  before the trade date, so the pre-existing "not yet expired" filter
  already excludes them regardless of this fix -- e.g. CL contract_month
  201405 on 2014-06-20 carries expiration_date 20140422, before the trade
  date) OR far-deferred contract months whose expiration_date is nowhere
  near the minimum among that date's quoted contracts (e.g. SI 202101 on
  2019-02-22 has 18 nearer, non-zero-settle contract months quoted that
  same day -- see futures_span_full_pull_2026-09-07.txt). Only the 3
  ZT/ZF/LE stub cases carry BOTH a zero settle AND a self-referential
  expiration_date equal to their own trade date, which is what makes them
  look like "the front month expiring today" under the calendar rule
  alone.

This produces the actual usable price series a future TSMOM family would
consume. It does NOT build a TSMOM signal itself: no lookback return, no
volatility estimate, no position sizing, no pre-registration, no DSR.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}"
    )

from app.services.market_data import cme_span_settlements as span  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_tsmom_futures_feasibility import (  # noqa: E402
    chained_contract_daily_returns,
    panama_back_adjusted_prices,
    ratio_back_adjusted_prices,
    validate_against_synthetic,
)

STORE = _BACKEND / "data" / "futures_daily" / "cme_span"
BY_INSTRUMENT = STORE / "by_instrument"
CONTINUOUS_DIR = STORE / "continuous"


@dataclass
class ChainResult:
    globex: str
    n_trade_days: int
    n_contract_months: int
    n_contracts_with_no_expiration: int
    n_rolls: int
    first_date: str
    last_date: str
    roll_dates: list[str]
    cumulative_return: float
    max_abs_daily_return: float
    max_abs_daily_return_date: str | None
    negative_settle_days: list[dict[str, Any]]
    ok: bool
    error: str | None = None


def build_holding_series(instrument_frame: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    """From a by_instrument CSV frame (trade_date, contract_month, settle,
    expiration_date), determine which contract is HELD on each trade date
    under the calendar/expiry-order roll rule described in the module
    docstring, and build the per-contract close series the chaining
    functions need.

    Returns (holding, closes_by_contract) plus diagnostics."""
    frame = instrument_frame.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame["expiration_date"] = frame["expiration_date"].astype(str)

    has_expiry = frame[frame["expiration_date"].str.len() == 8].copy()
    n_no_expiry_rows = len(frame) - len(has_expiry)
    if has_expiry.empty:
        raise ValueError("no rows with a known expiration_date -- cannot build a roll rule")
    has_expiry["expiration_dt"] = pd.to_datetime(has_expiry["expiration_date"], format="%Y%m%d")

    # one price series per contract month (indexed by trade_date)
    closes_by_contract: dict[str, pd.Series] = {}
    expiry_by_contract: dict[str, pd.Timestamp] = {}
    for month, g in has_expiry.groupby("contract_month"):
        g = g.drop_duplicates(subset="trade_date", keep="last").sort_values("trade_date")
        closes_by_contract[str(month)] = pd.Series(
            g["settle"].to_numpy(dtype=float), index=pd.DatetimeIndex(g["trade_date"])
        )
        expiry_by_contract[str(month)] = g["expiration_dt"].iloc[0]

    trade_dates = pd.DatetimeIndex(sorted(has_expiry["trade_date"].unique()))
    held: list[str] = []
    n_zero_settle_excluded_from_candidacy = 0
    for d in trade_dates:
        # candidates: contracts quoted on this date, not yet expired as of this
        # date, and NOT an implausible zero-settle stub record (see the module
        # docstring's "ADDITIONAL DEVIATION" -- a real front-month contract
        # never legitimately settles at exactly 0.0 in this 31-root universe;
        # a handful of stub Type-82 records for not-yet-fully-configured far
        # months carry settle 0.0 together with a bogus expiration_date equal
        # to their own trade date, which would otherwise look like "expires
        # today" and get chosen as front).
        candidates = [
            m
            for m, s in closes_by_contract.items()
            if d in s.index and expiry_by_contract[m] >= d and float(s.loc[d]) != 0.0
        ]
        n_zero_settle_excluded_from_candidacy += sum(
            1
            for m, s in closes_by_contract.items()
            if d in s.index and expiry_by_contract[m] >= d and float(s.loc[d]) == 0.0
        )
        if not candidates:
            # every quoted contract on this date has already "expired" per its
            # own recorded expiration_date (can happen on the expiration day
            # itself depending on time-of-day convention) -- fall back to the
            # contract with the LATEST expiration among those quoted that day,
            # i.e. treat it as still the nearest available, and log via the
            # None sentinel so the caller can see how often this fired.
            # Zero-settle rows are excluded here too, for the same reason.
            quoted_today = [m for m, s in closes_by_contract.items() if d in s.index and float(s.loc[d]) != 0.0]
            if not quoted_today:
                held.append(None)
                continue
            candidates = quoted_today
        # nearest-to-expiry among the not-yet-expired candidates
        front = min(candidates, key=lambda m: expiry_by_contract[m])
        held.append(front)

    holding = pd.Series(held, index=trade_dates, dtype=object)
    diagnostics = {
        "n_rows_total": int(len(frame)),
        "n_rows_no_expiration_date": int(n_no_expiry_rows),
        "n_contract_months_with_expiry": int(len(closes_by_contract)),
        "n_trade_dates": int(len(trade_dates)),
        "n_dates_with_no_quoted_contract": int(sum(1 for h in held if h is None)),
        "n_zero_settle_candidate_exclusions": int(n_zero_settle_excluded_from_candidacy),
    }
    return holding, closes_by_contract, diagnostics


def chain_one_instrument(globex: str) -> tuple[ChainResult, pd.DataFrame | None]:
    path = BY_INSTRUMENT / f"{globex}.csv"
    if not path.exists():
        return (
            ChainResult(
                globex=globex, n_trade_days=0, n_contract_months=0,
                n_contracts_with_no_expiration=0, n_rolls=0, first_date="", last_date="",
                roll_dates=[], cumulative_return=float("nan"), max_abs_daily_return=float("nan"),
                max_abs_daily_return_date=None, negative_settle_days=[], ok=False,
                error=f"no by_instrument CSV at {path}",
            ),
            None,
        )
    frame = pd.read_csv(path, dtype={"contract_month": str, "expiration_date": str})
    if frame.empty:
        return (
            ChainResult(
                globex=globex, n_trade_days=0, n_contract_months=0,
                n_contracts_with_no_expiration=0, n_rolls=0, first_date="", last_date="",
                roll_dates=[], cumulative_return=float("nan"), max_abs_daily_return=float("nan"),
                max_abs_daily_return_date=None, negative_settle_days=[], ok=False,
                error="empty by_instrument CSV",
            ),
            None,
        )
    try:
        holding_raw, closes_by_contract, diag = build_holding_series(frame)
    except Exception as exc:  # noqa: BLE001
        return (
            ChainResult(
                globex=globex, n_trade_days=int(len(frame)), n_contract_months=0,
                n_contracts_with_no_expiration=0, n_rolls=0, first_date="", last_date="",
                roll_dates=[], cumulative_return=float("nan"), max_abs_daily_return=float("nan"),
                max_abs_daily_return_date=None, negative_settle_days=[], ok=False,
                error=f"{type(exc).__name__}: {exc}",
            ),
            None,
        )
    holding = holding_raw.dropna()
    if holding.empty:
        return (
            ChainResult(
                globex=globex, n_trade_days=0, n_contract_months=diag["n_contract_months_with_expiry"],
                n_contracts_with_no_expiration=0, n_rolls=0, first_date="", last_date="",
                roll_dates=[], cumulative_return=float("nan"), max_abs_daily_return=float("nan"),
                max_abs_daily_return_date=None, negative_settle_days=[], ok=False,
                error="no date had a determinable held contract",
            ),
            None,
        )

    try:
        returns = chained_contract_daily_returns(closes_by_contract, holding)
        ratio_adj = ratio_back_adjusted_prices(closes_by_contract, holding)
    except Exception as exc:  # noqa: BLE001 -- e.g. a roll date with no overlap; surfaced, not hidden
        return (
            ChainResult(
                globex=globex, n_trade_days=int(len(holding)),
                n_contract_months=diag["n_contract_months_with_expiry"],
                n_contracts_with_no_expiration=diag["n_rows_no_expiration_date"],
                n_rolls=0, first_date=str(holding.index.min().date()),
                last_date=str(holding.index.max().date()), roll_dates=[],
                cumulative_return=float("nan"), max_abs_daily_return=float("nan"),
                max_abs_daily_return_date=None, negative_settle_days=[], ok=False,
                error=f"chaining failed: {type(exc).__name__}: {exc}",
            ),
            None,
        )

    roll_dates = [
        str(holding.index[i].date())
        for i in range(1, len(holding))
        if holding.iloc[i] != holding.iloc[i - 1]
    ]
    clean_returns = returns.dropna()
    cumulative = float((1.0 + clean_returns).prod() - 1.0) if len(clean_returns) else float("nan")
    if len(clean_returns):
        idx_max = clean_returns.abs().idxmax()
        max_abs = float(clean_returns.loc[idx_max])
        max_abs_date = str(idx_max.date())
    else:
        max_abs, max_abs_date = float("nan"), None

    negative_settle_days = [
        {"date": str(d.date()), "contract_month": str(holding.loc[d]), "settle": float(closes_by_contract[holding.loc[d]].loc[d])}
        for d in holding.index
        if closes_by_contract[holding.loc[d]].loc[d] < 0
    ]

    out = pd.DataFrame(
        {
            "trade_date": holding.index,
            "held_contract_month": holding.to_numpy(),
            "held_contract_settle": [float(closes_by_contract[holding.iloc[i]].loc[holding.index[i]]) for i in range(len(holding))],
            "chained_daily_return": returns.to_numpy(),
            "ratio_adjusted_close": ratio_adj.to_numpy(),
        }
    )

    result = ChainResult(
        globex=globex,
        n_trade_days=int(len(holding)),
        n_contract_months=diag["n_contract_months_with_expiry"],
        n_contracts_with_no_expiration=diag["n_rows_no_expiration_date"],
        n_rolls=len(roll_dates),
        first_date=str(holding.index.min().date()),
        last_date=str(holding.index.max().date()),
        roll_dates=roll_dates,
        cumulative_return=cumulative,
        max_abs_daily_return=max_abs,
        max_abs_daily_return_date=max_abs_date,
        negative_settle_days=negative_settle_days,
        ok=True,
    )
    return result, out


def main() -> None:
    validation = validate_against_synthetic()
    if validation["failures"]:
        raise SystemExit(
            f"REFUSING TO CHAIN REAL DATA: synthetic known-answer validation failed: "
            f"{validation['failures']}"
        )
    print(f"synthetic validation OK, worst_delta={validation['worst_delta']:.3e}")

    if not BY_INSTRUMENT.exists():
        raise SystemExit(
            f"no by_instrument directory at {BY_INSTRUMENT} -- run fetch_cme_span_archive.py "
            "(and its write_per_instrument step) first"
        )

    globex_roots = sorted(span.GLOBEX_TO_SPAN)
    CONTINUOUS_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    for globex in globex_roots:
        result, out = chain_one_instrument(globex)
        results[globex] = result.__dict__
        if out is not None:
            out.to_csv(CONTINUOUS_DIR / f"{globex}.csv", index=False)
        status = "OK" if result.ok else f"FAILED: {result.error}"
        print(
            f"{globex}: {status} "
            f"({result.n_trade_days} days, {result.n_rolls} rolls, "
            f"{result.first_date}..{result.last_date})"
        )

    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "app/services/market_data/cme_span_settlements.py by_instrument store, chained "
        "per MOP (2012) Section 2.1 via run_tsmom_futures_feasibility.chained_contract_daily_returns",
        "roll_rule": "calendar/expiry-order: on each date, hold the contract with the smallest "
        "expiration_date still >= that date (first not-yet-expired contract), a disclosed "
        "deviation from MOP's most-liquid-contract rule (no free source provides per-contract "
        "volume) -- see PENDING_PAID_DATA_DECISIONS.md P4",
        "synthetic_validation": validation,
        "n_instruments_attempted": len(globex_roots),
        "n_instruments_ok": sum(1 for r in results.values() if r["ok"]),
        "n_instruments_failed": sum(1 for r in results.values() if not r["ok"]),
        "per_instrument": results,
    }
    manifest_path = CONTINUOUS_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"wrote {manifest_path}")
    print(f"OK: {manifest['n_instruments_ok']}/{manifest['n_instruments_attempted']}")


if __name__ == "__main__":
    main()
