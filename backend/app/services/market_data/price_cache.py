from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar
from app.services.market_data.base import MarketDataProvider

# Weekend/holiday + "today's bar may not be published yet" tolerance for a
# rolling window (end == today). A fixed historical window (end < today,
# e.g. a stress scenario) has no tolerance — those dates never change once
# fully fetched, so they become a permanent cache hit.
ROLLING_WINDOW_TOLERANCE_DAYS = 4


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

    stale_or_missing: list[str] = []
    for ticker in tickers:
        cached_bounds = bounds_by_ticker.get(ticker)
        if cached_bounds is None:
            stale_or_missing.append(ticker)
            continue
        cached_min, cached_max = cached_bounds
        if cached_min > start or cached_max < required_max:
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

    stmt = sqlite_insert(PriceBar).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker", "date"],
        set_={"adj_close": stmt.excluded.adj_close, "source": stmt.excluded.source},
    )
    db.execute(stmt)
    db.commit()
