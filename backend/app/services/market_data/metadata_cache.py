from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.ticker_metadata import TickerMetadata
from app.services.market_data.base import MarketDataProvider, TickerMetadataResult
from app.time_utils import utcnow_naive

DEFAULT_TTL_DAYS = 30


def get_ticker_metadata_cached(
    db: Session,
    provider: MarketDataProvider,
    ticker: str,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> TickerMetadataResult | None:
    """Read-through cache over TickerMetadata. On a fetch failure, falls
    back to a *stale* cached row rather than caching the failure — so the
    next request retries instead of getting permanently stuck as
    'Unknown'."""
    cached = db.get(TickerMetadata, ticker)
    if cached is not None and cached.fetched_at >= utcnow_naive() - timedelta(days=ttl_days):
        return _to_result(cached)

    fetched = provider.get_ticker_metadata(ticker)
    if fetched is None:
        return _to_result(cached) if cached is not None else None

    if cached is None:
        db.add(
            TickerMetadata(
                ticker=ticker,
                sector=fetched.sector,
                industry=fetched.industry,
                asset_class=fetched.asset_class,
                currency=fetched.currency,
            )
        )
    else:
        cached.sector = fetched.sector
        cached.industry = fetched.industry
        cached.asset_class = fetched.asset_class
        cached.currency = fetched.currency
        cached.fetched_at = utcnow_naive()
    db.commit()

    return fetched


def _to_result(row: TickerMetadata) -> TickerMetadataResult:
    return TickerMetadataResult(
        sector=row.sector, industry=row.industry, asset_class=row.asset_class, currency=row.currency
    )
