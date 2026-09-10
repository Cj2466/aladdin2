from datetime import date

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar
from app.services.market_data.base import MarketDataProvider

# These two window-coverage tolerances originated here and now live in
# price_store.py, which needs the identical rule for its own on-disk coverage
# check. Imported rather than duplicated so the DB cache and the price store
# cannot drift apart; the names are re-exported unchanged so every existing
# reference and test keeps working.
#
#   ROLLING_WINDOW_TOLERANCE_DAYS — weekend/holiday + "today's bar may not be
#     published yet" tolerance for a rolling window (end >= today). A fixed
#     historical window has no such tolerance: those dates never change once
#     fully fetched, so they become a permanent cache hit.
#   START_DATE_TRADING_CALENDAR_TOLERANCE_DAYS — a requested `start` can itself
#     land on a weekend/holiday, so the earliest real bar is unavoidably a few
#     calendar days later. Without it, `cached_min > start` trips for ~2/7 of
#     all date-derived starts and permanently defeats the cache.
from app.services.market_data.price_store import (
    ROLLING_WINDOW_TOLERANCE_DAYS,
    START_DATE_TRADING_CALENDAR_TOLERANCE_DAYS,
)

__all__ = [
    "ROLLING_WINDOW_TOLERANCE_DAYS",
    "START_DATE_TRADING_CALENDAR_TOLERANCE_DAYS",
    "get_price_history_cached",
]

# _upsert_price_bars sends one row of 4 bind variables (ticker, date,
# adj_close, source) per record. A single unchunked bulk insert across a
# large universe x a long lookback window can exceed a database's bound-
# parameter limit — confirmed directly this session: fetching the (Phase 3)
# 503-ticker universe over a 425-day window raised
# "sqlite3.OperationalError: too many SQL variables" on this environment's
# actual SQLITE_LIMIT_VARIABLE_NUMBER (250,000; verified via
# sqlite3.Connection.getlimit). 2,000 rows/chunk = 8,000 variables/statement
# — safely under both that limit and Postgres's typical ~65,535
# parameters-per-query ceiling, with wide headroom for either to change.
UPSERT_CHUNK_SIZE = 2000


def get_price_history_cached(
    db: Session,
    provider: MarketDataProvider,
    tickers: list[str],
    start: date,
    end: date,
) -> tuple[pd.DataFrame, list[str]]:
    """Every call is served by the provider; PriceBar is written on the way
    past for its direct readers. The name is kept so its 17 call sites need
    no change; the read-through cache that used to live here is retired.

    WHY, 2026-09-10 — the remedy this docstring itself named on 2026-09-04,
    now applied on purpose rather than as a rider. PriceBar stores a DERIVED
    value, an adjusted close, which only means anything relative to an
    adjustment base date and a return convention. Two rows written by two
    different calls could therefore sit on two bases (and, since the
    2026-09-04 CRSP switch, on two conventions), and a read spanning both
    spliced them with a fabricated return at the join. On top of that the
    freshness test used date.today() (the process-local date, one day ahead
    of the market's UTC date for part of every Bangkok morning) and one
    four-calendar-day tolerance for every asset, the five-day-calendar
    assumption that froze a real hole on seven-day crypto in the price store
    (price_store.CONTINUOUS_CALENDAR_TOLERANCE_DAYS). Since 2026-09-09 the
    provider's own get_price_history is served from the point-in-time price
    store — deterministic, on disk, with the UTC clock and the per-ticker
    tolerance built in — so there is nothing left for a second cache to add
    and three things it could get wrong. The pairs forward-validation runner,
    the screening and sweep runners, macro_beta, the alert checker and every
    portfolio/risk router therefore now read exactly what the cross-sectional
    families read.

    PriceBar is STILL WRITTEN, every call, because execution_runner reads the
    table directly (execution_runner.py, the newest adj_close per ticker) and
    a stale table there would be its own defect. The upsert overwrites, so
    the table converges to the provider's current series rather than
    preserving the old splice.

    Cost: a fixed historical window that used to be a permanent SQL hit is
    now a store read each time — local files, the same read every
    cross-sectional family does daily."""
    ordered = list(dict.fromkeys(tickers))
    if not ordered:
        return pd.DataFrame(), []
    prices, fetch_missing = provider.get_price_history(ordered, start, end)
    _upsert_price_bars(db, prices)
    if prices.empty:
        return pd.DataFrame(), ordered
    present_missing = [t for t in ordered if t not in prices.columns]
    return prices, list(dict.fromkeys([*fetch_missing, *present_missing]))


def _upsert_price_bars(db: Session, prices: pd.DataFrame) -> None:
    if prices.empty:
        return

    records = []
    for ticker in prices.columns:
        for dt, value in prices[ticker].dropna().items():
            bar_date = dt.date() if hasattr(dt, "date") else dt
            records.append(
                {"ticker": ticker, "date": bar_date, "adj_close": float(value), "source": "yfinance"}
            )
    if not records:
        return

    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    for i in range(0, len(records), UPSERT_CHUNK_SIZE):
        chunk = records[i : i + UPSERT_CHUNK_SIZE]
        stmt = insert(PriceBar).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={"adj_close": stmt.excluded.adj_close, "source": stmt.excluded.source},
        )
        db.execute(stmt)
    db.commit()
