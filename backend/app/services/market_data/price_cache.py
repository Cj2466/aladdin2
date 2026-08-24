from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar
from app.services.market_data.base import MarketDataProvider

# Weekend/holiday + "today's bar may not be published yet" tolerance for a
# rolling window (end == today). A fixed historical window (end < today,
# e.g. a stress scenario) has no tolerance — those dates never change once
# fully fetched, so they become a permanent cache hit.
ROLLING_WINDOW_TOLERANCE_DAYS = 4

# A requested `start` date can itself land on a weekend/holiday — no trading
# bar will ever exist exactly on that date, so the earliest real bar is
# unavoidably a few calendar days later. Without this tolerance, `cached_min
# > start` trips on every call whenever `start` isn't a trading day (~2/7 of
# the time for any date-derived start, e.g. `today - 365 days`), permanently
# defeating the cache for that ticker/window and silently refetching on every
# request. Applies regardless of rolling vs. fixed window — unlike
# ROLLING_WINDOW_TOLERANCE_DAYS, this is about the trading calendar around
# `start`, not about "today's bar not posted yet".
START_DATE_TRADING_CALENDAR_TOLERANCE_DAYS = 4

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
    """Read-through cache over PriceBar. Deliberately simple — no partial
    range-diffing: a ticker with insufficient cached coverage gets the full
    requested range refetched and upserted, not just the missing delta."""
    is_rolling_window = end >= date.today()

    # Bounds are scoped to the requested [start, end] window itself, not the
    # ticker's all-time cached range — a ticker can have two disjoint cached
    # spans (e.g. a fixed 2008 scenario fetch and a separate rolling 3-year
    # fetch) with a gap between them that an all-time min/max would miss,
    # silently treating a completely uncached window as "already covered."
    bounds_rows = db.execute(
        select(PriceBar.ticker, func.min(PriceBar.date), func.max(PriceBar.date))
        .where(PriceBar.ticker.in_(tickers))
        .where(PriceBar.date >= start)
        .where(PriceBar.date <= end)
        .group_by(PriceBar.ticker)
    ).all()
    bounds_by_ticker = {ticker: (min_d, max_d) for ticker, min_d, max_d in bounds_rows}

    required_max = (end - timedelta(days=ROLLING_WINDOW_TOLERANCE_DAYS)) if is_rolling_window else end
    required_min = start + timedelta(days=START_DATE_TRADING_CALENDAR_TOLERANCE_DAYS)

    stale_or_missing: list[str] = []
    for ticker in tickers:
        cached_bounds = bounds_by_ticker.get(ticker)
        if cached_bounds is None:
            stale_or_missing.append(ticker)
            continue
        cached_min, cached_max = cached_bounds
        if cached_min > required_min or cached_max < required_max:
            stale_or_missing.append(ticker)

    fetch_missing: list[str] = []
    if stale_or_missing:
        fetched, fetch_missing = provider.get_price_history(stale_or_missing, start, end)
        _upsert_price_bars(db, fetched)

    rows = db.execute(
        select(PriceBar.ticker, PriceBar.date, PriceBar.adj_close)
        .where(PriceBar.ticker.in_(tickers))
        .where(PriceBar.date >= start)
        .where(PriceBar.date <= end)
    ).all()

    if not rows:
        return pd.DataFrame(), list(dict.fromkeys(tickers))

    frame = pd.DataFrame(rows, columns=["ticker", "date", "adj_close"])
    prices = frame.pivot(index="date", columns="ticker", values="adj_close")
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index()
    prices.columns.name = None

    present_missing = [t for t in tickers if t not in prices.columns]
    missing = list(dict.fromkeys([*fetch_missing, *present_missing]))
    return prices, missing


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
