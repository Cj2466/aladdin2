"""FORWARD-LOOKING DATA COLLECTION ONLY — NOT YET USABLE FOR BACKTESTING.

This module records, once per invocation, the front-month and next-month
futures contract prices (and volume / open interest where the source
exposes them) for a small set of liquid commodities, appending timestamped
JSON lines to a local file. Its entire purpose is to START ACCUMULATING the
contract-level term-structure data that a real commodity CARRY /
roll-yield backtest would need — data that free sources do not provide
historically, because (verified live 2026-08-27, see
cross_sectional_commodities.py's module docstring for the measurements)
Yahoo's continuous futures tickers are a naive front-month splice whose
chained returns fabricate the roll yield they would be needed to measure
(+28.4%/yr on NG=F vs the investable proxy), and expired individual
contracts are purged from the feed, so the curve's history cannot be
reconstructed after the fact. The only way to have this data in N years is
to start recording it now.

WHAT THIS IS NOT, stated as loudly as possible:
 * It is NOT a signal, a backtest input, or a research result. A useful
   carry test needs YEARS of accumulated observations; a file with weeks
   of them supports no conclusion of any kind.
 * It is NOT connected to the commodities screening family. cross_
   sectional_commodities.py neither imports this module nor reads its
   output file, and this module imports nothing from any cross_sectional
   module — the separation is structural (asserted by tests in both
   directions), so the collector can neither bias nor be biased by the
   family whose future round it serves.
 * Its output is NOT retroactively extendable. Each record exists only
   because this collector observed it at that timestamp; a gap (machine
   off, source down) is a permanent gap, which is exactly the property
   that makes the splice problem unfixable and this collector necessary.

WHAT ONE RECORD IS: for each commodity, the two nearest-delivery contracts
that still have a FRESH price (traded within STALE_AFTER_CALENDAR_DAYS) are
labeled "front" and "next", and one JSON line is written per contract:
observation timestamp (UTC), commodity root, contract ticker, delivery
month, close, volume, open interest (None where the source does not expose
it), and the source name. Front-vs-next is the minimal pair from which a
point-in-time annualized roll yield can later be computed; open interest,
when present, is what the standard roll-timing conventions key on.

Contract symbology (Yahoo): ROOT + MONTH_CODE + 2-DIGIT YEAR + "." +
EXCHANGE, e.g. CLV26.NYM = Crude Oil October 2026 on NYMEX. Delivery-month
cycles differ per commodity and are declared per root below — asking Yahoo
for a contract month that does not exist just wastes a request and returns
nothing.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# The banner constant tests and downstream readers can assert on. Included
# verbatim in every collection result so no consumer can claim they were
# not told.
NOT_USABLE_FOR_BACKTESTING = (
    "futures_curve_collector output is forward-looking raw data collection; it is NOT usable "
    "for backtesting until years of observations have accumulated, and it must never be mixed "
    "into a screening family's inputs or results."
)

# CME/standard futures month codes, month number -> letter.
MONTH_CODES: dict[int, str] = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}

# root -> (Yahoo exchange suffix, human name, active delivery-month cycle).
# The cycle matters: GC has no liquid September contract and ZW no August
# one, so generating "every month" would burn requests on tickers that do
# not exist. Cycles are the standard liquid CME/CBOT/NYMEX/COMEX listings.
COLLECTOR_COMMODITIES: dict[str, tuple[str, str, tuple[int, ...]]] = {
    "CL": ("NYM", "WTI crude oil", (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)),
    "NG": ("NYM", "Henry Hub natural gas", (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)),
    "GC": ("CMX", "gold", (2, 4, 6, 8, 10, 12)),
    "SI": ("CMX", "silver", (3, 5, 7, 9, 12)),
    "HG": ("CMX", "copper", (3, 5, 7, 9, 12)),
    "ZC": ("CBT", "corn", (3, 5, 7, 9, 12)),
    "ZW": ("CBT", "wheat", (3, 5, 7, 9, 12)),
    "ZS": ("CBT", "soybeans", (1, 3, 5, 7, 8, 9, 11)),
}

# How many upcoming cycle months to generate candidate contracts for. The
# front month is usually the first or second candidate (an expiring
# contract stops printing fresh closes days before its delivery month), so
# 5 leaves margin without spraying requests.
N_CANDIDATE_MONTHS = 5

# A contract whose last available close is older than this many calendar
# days is treated as stale (expired, delisted, or simply not trading) and
# skipped. 7 covers any exchange-holiday cluster while still rejecting a
# contract that stopped trading at expiry.
STALE_AFTER_CALENDAR_DAYS = 7

# Default output location: backend/data/futures_curve_observations.jsonl.
# JSON LINES, append-only: each invocation appends; nothing is ever
# rewritten, so the file is its own audit trail.
_DEFAULT_OUT_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "futures_curve_observations.jsonl"
)


def default_output_path() -> Path:
    return _DEFAULT_OUT_PATH


def candidate_delivery_months(root: str, today: date, n: int = N_CANDIDATE_MONTHS) -> list[date]:
    """The next `n` delivery months in `root`'s cycle, starting from the
    CURRENT month (the front contract's delivery month can be the current
    or next month depending on where we are relative to expiry — the
    freshness test below decides, not the calendar)."""
    _, _, cycle = COLLECTOR_COMMODITIES[root]
    months: list[date] = []
    year, month = today.year, today.month
    while len(months) < n:
        if month in cycle:
            months.append(date(year, month, 1))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return months


def contract_ticker(root: str, delivery: date) -> str:
    """CLV26.NYM-style Yahoo ticker for one contract."""
    exchange, _, _ = COLLECTOR_COMMODITIES[root]
    return f"{root}{MONTH_CODES[delivery.month]}{delivery.year % 100:02d}.{exchange}"


@dataclass(frozen=True)
class ContractObservation:
    """One contract's state as observed at one moment. open_interest is
    None whenever the source does not expose it — never fabricated."""

    commodity: str
    contract: str
    delivery_month: str  # "YYYY-MM"
    position: str  # "front" | "next"
    close: float
    close_date: str  # "YYYY-MM-DD" of the close actually observed
    volume: float | None
    open_interest: float | None


@dataclass
class CurveCollectionResult:
    """What one invocation observed and wrote. `failures` maps a commodity
    root to why it produced no pair (both contracts stale, fetch error,
    ...) — a partial collection is a normal outcome, never an exception,
    because one exchange's outage must not cost the others' daily record."""

    observed_at_utc: str
    out_path: Path
    records: list[ContractObservation] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)
    notice: str = NOT_USABLE_FOR_BACKTESTING


# A fetcher maps a contract ticker to (close, close_date, volume,
# open_interest) or None when the contract has no usable fresh data.
# Injectable so tests never touch the network.
FetchFn = Callable[[str], tuple[float, date, float | None, float | None] | None]


def _yfinance_fetch(ticker: str) -> tuple[float, date, float | None, float | None] | None:
    """The production fetcher. Last close and volume from a short history
    window; open interest from the quote info when Yahoo exposes it for
    the contract (it often does for futures; None otherwise)."""
    import yfinance as yf  # imported here so tests with injected fetchers never need it

    try:
        history = yf.Ticker(ticker).history(period="10d", auto_adjust=False)
    except Exception as exc:  # noqa: BLE001 — one bad contract must not kill the run
        logger.warning("futures_curve_collector: history fetch failed for %s: %s", ticker, exc)
        return None
    if history is None or history.empty or "Close" not in history.columns:
        return None
    closes = history["Close"].dropna()
    if closes.empty:
        return None
    close = float(closes.iloc[-1])
    close_date = closes.index[-1].date()
    volume: float | None = None
    if "Volume" in history.columns:
        vol_series = history["Volume"].dropna()
        if not vol_series.empty:
            volume = float(vol_series.iloc[-1])

    open_interest: float | None = None
    try:
        info = yf.Ticker(ticker).info
        raw_oi = info.get("openInterest") if isinstance(info, dict) else None
        if raw_oi is not None and float(raw_oi) > 0:
            open_interest = float(raw_oi)
    except Exception:  # noqa: BLE001 — OI is best-effort; None is the honest fallback
        open_interest = None
    return close, close_date, volume, open_interest


def _select_front_and_next(
    root: str, today: date, fetch: FetchFn
) -> tuple[list[ContractObservation], str | None]:
    """Walks `root`'s candidate contracts in delivery order and returns the
    first two with FRESH closes as (front, next). Freshness — a close within
    STALE_AFTER_CALENDAR_DAYS — is what decides the front month, not the
    calendar: near expiry the nominal first month stops printing and the
    freshness test correctly promotes the next one."""
    selected: list[ContractObservation] = []
    for delivery in candidate_delivery_months(root, today):
        ticker = contract_ticker(root, delivery)
        result = fetch(ticker)
        if result is None:
            continue
        close, close_date, volume, open_interest = result
        if (today - close_date).days > STALE_AFTER_CALENDAR_DAYS:
            continue
        if not (close > 0.0):
            continue
        selected.append(
            ContractObservation(
                commodity=root,
                contract=ticker,
                delivery_month=f"{delivery.year:04d}-{delivery.month:02d}",
                position="front" if not selected else "next",
                close=close,
                close_date=close_date.isoformat(),
                volume=volume,
                open_interest=open_interest,
            )
        )
        if len(selected) == 2:
            return selected, None
    if not selected:
        return [], "no candidate contract returned a fresh price"
    return [], "only one candidate contract returned a fresh price — a curve needs two"


def collect_futures_curve_once(
    out_path: Path | None = None,
    fetch: FetchFn | None = None,
    today: date | None = None,
) -> CurveCollectionResult:
    """One collection pass over every commodity in COLLECTOR_COMMODITIES:
    select front/next contracts, append one JSON line per observation to
    `out_path` (created with parents if absent), and return everything
    observed plus per-commodity failures. Run it daily (cron or by hand);
    each run adds at most 2 lines per commodity and skipping a day only
    costs that day's observation.

    Commodities whose pair could not be resolved are recorded in
    `failures` and simply absent from the file for this timestamp — a
    partial record is real data; a raised exception would cost every other
    commodity's line."""
    out_path = out_path if out_path is not None else default_output_path()
    fetch = fetch if fetch is not None else _yfinance_fetch
    today = today if today is not None else datetime.now(UTC).date()

    observed_at = datetime.now(UTC).isoformat(timespec="seconds")
    result = CurveCollectionResult(observed_at_utc=observed_at, out_path=out_path)

    for root in COLLECTOR_COMMODITIES:
        try:
            pair, failure = _select_front_and_next(root, today, fetch)
        except Exception as exc:  # noqa: BLE001 — one commodity's failure must not cost the rest
            logger.warning("futures_curve_collector: %s failed: %s", root, exc)
            result.failures[root] = f"unexpected error: {exc}"
            continue
        if failure is not None:
            result.failures[root] = failure
            continue
        result.records.extend(pair)

    if result.records:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as handle:
            for record in result.records:
                line = {
                    "observed_at_utc": observed_at,
                    "commodity": record.commodity,
                    "contract": record.contract,
                    "delivery_month": record.delivery_month,
                    "position": record.position,
                    "close": record.close,
                    "close_date": record.close_date,
                    "volume": record.volume,
                    "open_interest": record.open_interest,
                    "source": "yfinance",
                    "notice": "not_usable_for_backtesting",
                }
                handle.write(json.dumps(line, sort_keys=True) + "\n")

    logger.info(
        "futures_curve_collector: wrote %d observation(s) for %d/%d commodities to %s%s",
        len(result.records),
        len({r.commodity for r in result.records}),
        len(COLLECTOR_COMMODITIES),
        out_path,
        f" (failures: {result.failures})" if result.failures else "",
    )
    return result


__all__ = [
    "COLLECTOR_COMMODITIES",
    "MONTH_CODES",
    "NOT_USABLE_FOR_BACKTESTING",
    "N_CANDIDATE_MONTHS",
    "STALE_AFTER_CALENDAR_DAYS",
    "ContractObservation",
    "CurveCollectionResult",
    "candidate_delivery_months",
    "collect_futures_curve_once",
    "contract_ticker",
    "default_output_path",
]
