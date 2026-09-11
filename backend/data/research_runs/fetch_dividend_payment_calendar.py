"""DATA ACQUISITION for the aggregate-dividend-payment-pressure family.

Computes NO return, NO position and NO P&L of any kind, and is run BEFORE the
pre-registration is finalized, for the same reason
fetch_dividend_calendar.py and fetch_eap_announcement_calendar.py were: the
design has to be able to see what data actually exists before it freezes a
grid around it.

WHAT IT COLLECTS, and why each piece is needed:

 (1) EX-DATES AND PER-SHARE AMOUNTS for the point-in-time S&P 500 candidate
     pool, from YFinanceProvider.get_dividend_history off this project's own
     point-in-time price store. This is the SAME call
     cross_sectional_dividend_month.py's calendar is built from, and its
     amounts are split-adjusted onto the same basis as the Close returned
     with them.

 (2) THE PER-TICKER EX-DATE -> PAYMENT-DATE LAG, from yfinance's per-ticker
     `.calendar` endpoint, which carries BOTH 'Ex-Dividend Date' and
     'Dividend Date' (the PAYMENT date) for a ticker's most recent/upcoming
     distribution. Yahoo's HISTORICAL corporate-actions feed -- the one
     get_dividend_history reads -- carries the EX-DATE ONLY, which
     YFinanceProvider.get_dividend_history's own docstring states as a fact
     about the source. The paper this family tests is explicit that the
     PAYMENT date is the economically correct timing, so this endpoint is
     the only broad free route to one.

 (3) NASDAQ'S OWN DIVIDEND-HISTORY API as INDEPENDENT GROUND TRUTH for (2).
     api.nasdaq.com/api/quote/<T>/dividends returns real historical
     (ex-date, record date, DECLARATION date, PAYMENT date) tuples. It
     cannot be the primary source -- it answers
     "Dividend History for Non-Nasdaq symbols is not available" for
     NYSE-listed names, which is most of the dividend payers in this
     universe -- but on the subset it does cover it gives real historical
     pay dates against which the (2) imputation can be MEASURED rather than
     assumed.

 (4) SEC POINT-IN-TIME SHARE COUNTS, from this project's own
     SecSharesOutstandingProvider (dei:EntityCommonStockSharesOutstanding,
     90-day visibility lag), needed to turn per-share dividends into the
     DOLLAR aggregate the paper's payment yield is built from, and to build
     the aggregate market capitalization that is its denominator.

Run from backend/ with ./venv/bin/python
data/research_runs/fetch_dividend_payment_calendar.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv whose site-packages
# resolves `app` to the MAIN checkout. Without the two lines below, the fetch
# silently runs main's code instead of this branch's.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND})."
    )

import yfinance as yf

from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.sec_shares_outstanding_provider import (
    SecSharesOutstandingProvider,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.dividend_payment_pressure_timing import PAYMENT_CACHE_PATH
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
    membership_coverage_end,
)

# The family reads PAYMENT_CACHE_PATH (routed to the MAIN checkout since
# 2026-09-12); write to the same file so a worktree fetch is not orphaned.
CACHE_PATH = PAYMENT_CACHE_PATH

# Dividend history is loaded well before the first formation so the trailing
# 252-trading-day denominators of the paper's own abnormal-yield and top-N-day
# constructions can warm up on real data rather than on a truncated window.
FETCH_START = date(2012, 1, 3)
FETCH_END = date(2026, 9, 6)

# yfinance's own batching starts to time out well before 768 symbols in one
# call; 100 is the chunk size fetch_dividend_calendar.py measured live.
CHUNK_SIZE = 100

NASDAQ_URL = "https://api.nasdaq.com/api/quote/{ticker}/dividends?assetclass=stocks"
NASDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
NASDAQ_SLEEP_SECONDS = 0.25
YF_CALENDAR_SLEEP_SECONDS = 0.10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger("dividend_payment_fetch")


def _parse_us_date(raw: str | None) -> date | None:
    """Nasdaq's MM/DD/YYYY, or None for its several ways of saying 'absent'
    ('N/A', '--', '', missing key). Never raises: one unparseable cell must
    not lose a whole ticker's history."""
    if not raw:
        return None
    text = str(raw).strip()
    if not text or text in {"N/A", "--", "-"}:
        return None
    try:
        return datetime.strptime(text, "%m/%d/%Y").date()  # noqa: DTZ007
    except ValueError:
        return None


def fetch_yf_payment_lag(tickers: list[str]) -> dict[str, dict]:
    """{ticker: {ex, pay, lag_days}} from yfinance's per-ticker `.calendar`.

    ONE observation per ticker -- the most recent or upcoming distribution --
    which is all this endpoint carries. A ticker whose calendar has an
    ex-date but no 'Dividend Date' is recorded with pay=None so the coverage
    hole is counted rather than silently becoming a missing key."""
    out: dict[str, dict] = {}
    for i, ticker in enumerate(tickers):
        if i % 100 == 0:
            logger.info("yfinance calendar %d/%d", i, len(tickers))
        try:
            calendar = yf.Ticker(ticker).calendar or {}
        except Exception:  # noqa: BLE001 -- one bad name must not lose the pass
            continue
        ex = calendar.get("Ex-Dividend Date")
        pay = calendar.get("Dividend Date")
        if ex is None and pay is None:
            continue
        row: dict = {
            "ex": ex.isoformat() if ex else None,
            "pay": pay.isoformat() if pay else None,
        }
        if ex is not None and pay is not None:
            row["lag_days"] = (pay - ex).days
        out[ticker] = row
        time.sleep(YF_CALENDAR_SLEEP_SECONDS)
    return out


def fetch_nasdaq_history(tickers: list[str]) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """{ticker: [{ex, pay, declaration, record, amount}]} plus a coverage
    tally, from Nasdaq's own dividend-history API.

    A ticker Nasdaq refuses ("Dividend History for Non-Nasdaq symbols is not
    available") comes back HTTP 200 with zero rows, so the refusal is counted
    from the message rather than from an exception -- silently reading an
    empty list as "this company paid no dividends" is exactly the failure
    this project's free-futures scoping was burned by."""
    out: dict[str, list[dict]] = {}
    tally = {"covered": 0, "refused_non_nasdaq": 0, "empty_other": 0, "http_error": 0}
    for i, ticker in enumerate(tickers):
        if i % 100 == 0:
            logger.info("nasdaq %d/%d (covered so far %d)", i, len(tickers), tally["covered"])
        url = NASDAQ_URL.format(ticker=ticker.replace(".", "/"))
        try:
            request = urllib.request.Request(url, headers=NASDAQ_HEADERS)
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            tally["http_error"] += 1
            time.sleep(NASDAQ_SLEEP_SECONDS)
            continue
        data = payload.get("data") or {}
        rows = ((data.get("dividends") or {}).get("rows")) or []
        if not rows:
            message = str(payload.get("message") or "")
            if "Non-Nasdaq" in message:
                tally["refused_non_nasdaq"] += 1
            else:
                tally["empty_other"] += 1
            time.sleep(NASDAQ_SLEEP_SECONDS)
            continue
        kept: list[dict] = []
        for row in rows:
            ex = _parse_us_date(row.get("exOrEffDate"))
            pay = _parse_us_date(row.get("paymentDate"))
            declaration = _parse_us_date(row.get("declarationDate"))
            record = _parse_us_date(row.get("recordDate"))
            if ex is None:
                continue
            kept.append(
                {
                    "ex": ex.isoformat(),
                    "pay": pay.isoformat() if pay else None,
                    "declaration": declaration.isoformat() if declaration else None,
                    "record": record.isoformat() if record else None,
                    "type": row.get("type"),
                    "amount": row.get("amount"),
                }
            )
        if kept:
            out[ticker] = kept
            tally["covered"] += 1
        else:
            tally["empty_other"] += 1
        time.sleep(NASDAQ_SLEEP_SECONDS)
    return out, tally


def main() -> int:
    started = time.time()
    universe = get_universe_over(MEMBERSHIP_DATA_START, membership_coverage_end())
    logger.info("point-in-time candidate pool: %d tickers", len(universe))

    provider = YFinanceProvider()

    # ---- (1) ex-dates and amounts, batched off the point-in-time store ----
    dividends: dict[str, list[tuple[str, float]]] = {}
    missing_price: list[str] = []
    priced: list[str] = []
    for i in range(0, len(universe), CHUNK_SIZE):
        chunk = universe[i : i + CHUNK_SIZE]
        logger.info("dividend chunk %d..%d of %d", i, i + len(chunk), len(universe))
        by_ticker, close, chunk_missing = provider.get_dividend_history(
            chunk, FETCH_START, FETCH_END
        )
        missing_price.extend(chunk_missing)
        priced.extend([t for t in chunk if t not in chunk_missing])
        for ticker, series in by_ticker.items():
            dividends[ticker] = [
                (ts.date().isoformat(), float(amount)) for ts, amount in series.items()
            ]
    logger.info(
        "ex-date calendar: %d tickers with dividends, %d ex-dates, %d priced, %d unpriced",
        len(dividends),
        sum(len(v) for v in dividends.values()),
        len(priced),
        len(missing_price),
    )

    # ---- (2) the per-ticker ex -> pay lag ----
    logger.info("fetching yfinance per-ticker payment-date calendars")
    yf_lags = fetch_yf_payment_lag(sorted(dividends))
    with_lag = sum(1 for v in yf_lags.values() if v.get("lag_days") is not None)
    logger.info("yfinance calendar: %d tickers answered, %d with a usable lag", len(yf_lags), with_lag)

    # ---- (3) Nasdaq ground truth ----
    logger.info("fetching Nasdaq dividend history (ground truth for the lag imputation)")
    nasdaq, nasdaq_tally = fetch_nasdaq_history(sorted(dividends))
    logger.info("nasdaq: %s", nasdaq_tally)

    # ---- (4) SEC point-in-time share counts ----
    # Routed through SEC's own current-day ticker->CIK map exactly as
    # cross_sectional_short_interest.py does it, including its
    # `missing_from_map` accounting, so a ticker SEC cannot resolve is COUNTED
    # rather than silently contributing no dividends to the dollar aggregate.
    logger.info("fetching SEC point-in-time share counts")
    edgar = EdgarXbrlProvider()
    cik_map = edgar.get_ticker_cik_map()
    resolvable = {ticker: cik_map[ticker] for ticker in priced if ticker in cik_map}
    unresolvable = [ticker for ticker in priced if ticker not in cik_map]
    sec = SecSharesOutstandingProvider()
    observations, diagnostics = sec.fetch_share_counts(
        resolvable, FETCH_START, FETCH_END, missing_from_map=unresolvable
    )
    logger.info(
        "sec share counts: %d tickers with observations, %d priced tickers resolve no CIK",
        len(observations),
        len(unresolvable),
    )
    share_counts = {
        ticker: [
            {"as_of": o.as_of.isoformat(), "available": o.available.isoformat(), "shares": o.shares}
            for o in rows
        ]
        for ticker, rows in observations.items()
    }

    payload = {
        "schema": "dividend_payment_calendar/v1",
        "fetched_at": datetime.now(UTC).isoformat(),
        "fetch_start": FETCH_START.isoformat(),
        "fetch_end": FETCH_END.isoformat(),
        "n_tickers_requested": len(universe),
        "n_tickers_priced": len(priced),
        "n_tickers_with_dividends": len(dividends),
        "missing_price_data": sorted(missing_price),
        "dividends": dividends,
        "yf_payment_lag": yf_lags,
        "nasdaq_history": nasdaq,
        "nasdaq_tally": nasdaq_tally,
        "share_counts": share_counts,
        "share_count_diagnostics": {
            "n_tickers": len(share_counts),
            "n_priced_without_cik": len(unresolvable),
            "detail": str(diagnostics)[:2000],
        },
    }
    CACHE_PATH.write_text(json.dumps(payload) + "\n")
    logger.info(
        "wrote %s (%.1f MB) in %.1f min",
        CACHE_PATH,
        CACHE_PATH.stat().st_size / 1e6,
        (time.time() - started) / 60,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
