from dataclasses import dataclass

import httpx

from app.config import settings

FINNHUB_PROFILE_URL = "https://finnhub.io/api/v1/stock/profile2"
FINNHUB_METRIC_URL = "https://finnhub.io/api/v1/stock/metric"
FINNHUB_RECOMMENDATION_URL = "https://finnhub.io/api/v1/stock/recommendation"
FINNHUB_PEERS_URL = "https://finnhub.io/api/v1/stock/peers"


class FinnhubFundamentalsError(Exception):
    pass


@dataclass
class CompanyProfile:
    company_name: str | None
    exchange: str | None
    country: str | None
    currency: str | None
    ipo_date: str | None
    # Both confirmed via a live call (AAPL) to be in millions — market_capitalization
    # in millions of USD, share_outstanding in millions of shares.
    market_capitalization: float | None
    share_outstanding: float | None
    finnhub_industry: str | None
    weburl: str | None
    logo: str | None


@dataclass
class FundamentalMetrics:
    week52_high: float | None
    week52_low: float | None
    beta: float | None
    pe_ttm: float | None
    eps_ttm: float | None
    # Confirmed via a live call: roe/roa/margins are already whole percentages
    # (e.g. 137.18 means 137.18%), not fractions — do not multiply by 100 again.
    roe_ttm: float | None
    roa_ttm: float | None
    gross_margin_ttm: float | None
    net_margin_ttm: float | None
    current_ratio: float | None
    quick_ratio: float | None
    debt_to_equity: float | None
    dividend_yield_ttm: float | None
    avg_10day_volume: float | None


@dataclass
class RecommendationTrendPoint:
    period: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


class FinnhubFundamentalsClient:
    """Hand-rolled sync httpx client for Finnhub's free-tier fundamentals
    endpoints — mirrors FredProvider's style (a handful of simple GET/JSON
    calls isn't worth a third-party dependency), but sync rather than async
    since every router in this app is `def`, not `async def` (unlike
    finnhub_rest.py, which is async only because it's called from the
    websocket/alert-checker loop)."""

    def get_profile(self, ticker: str) -> CompanyProfile | None:
        data = self._get(FINNHUB_PROFILE_URL, ticker)
        # Finnhub signals "unknown symbol" on /profile2 with HTTP 200 + {}
        # (no "name" key) rather than an error status — same sentinel-value
        # trick finnhub_rest.py already uses for /quote's all-zero fields.
        if not data or not data.get("name"):
            return None
        return CompanyProfile(
            company_name=data.get("name"),
            exchange=data.get("exchange"),
            country=data.get("country"),
            currency=data.get("currency"),
            ipo_date=data.get("ipo"),
            market_capitalization=data.get("marketCapitalization"),
            share_outstanding=data.get("shareOutstanding"),
            finnhub_industry=data.get("finnhubIndustry"),
            weburl=data.get("weburl") or None,
            logo=data.get("logo") or None,
        )

    def get_metrics(self, ticker: str) -> FundamentalMetrics | None:
        data = self._get(FINNHUB_METRIC_URL, ticker, extra_params={"metric": "all"})
        metric = (data or {}).get("metric") or {}
        if not metric:
            return None
        return FundamentalMetrics(
            week52_high=metric.get("52WeekHigh"),
            week52_low=metric.get("52WeekLow"),
            beta=metric.get("beta"),
            pe_ttm=metric.get("peTTM"),
            eps_ttm=metric.get("epsTTM"),
            roe_ttm=metric.get("roeTTM"),
            roa_ttm=metric.get("roaTTM"),
            gross_margin_ttm=metric.get("grossMarginTTM"),
            net_margin_ttm=metric.get("netProfitMarginTTM"),
            current_ratio=metric.get("currentRatioQuarterly") or metric.get("currentRatioAnnual"),
            quick_ratio=metric.get("quickRatioQuarterly") or metric.get("quickRatioAnnual"),
            debt_to_equity=(
                metric.get("totalDebt/totalEquityQuarterly") or metric.get("totalDebt/totalEquityAnnual")
            ),
            dividend_yield_ttm=metric.get("currentDividendYieldTTM"),
            avg_10day_volume=metric.get("10DayAverageTradingVolume"),
        )

    def get_recommendation_trends(self, ticker: str) -> list[RecommendationTrendPoint]:
        data = self._get(FINNHUB_RECOMMENDATION_URL, ticker)
        # An empty list is a legitimate response (no analyst coverage for
        # this ticker), not an error — can't distinguish that from "unknown
        # ticker" here, so this endpoint doesn't try; get_profile is the
        # sole ticker-existence check.
        if not data:
            return []
        return [
            RecommendationTrendPoint(
                period=row["period"],
                strong_buy=row.get("strongBuy", 0),
                buy=row.get("buy", 0),
                hold=row.get("hold", 0),
                sell=row.get("sell", 0),
                strong_sell=row.get("strongSell", 0),
            )
            for row in data
        ]

    def get_peers(self, ticker: str) -> list[str]:
        data = self._get(FINNHUB_PEERS_URL, ticker)
        if not data:
            return []
        # Finnhub's /peers response includes the queried ticker itself.
        return [t for t in data if t != ticker]

    def _get(self, url: str, ticker: str, extra_params: dict | None = None) -> dict | list | None:
        if not settings.finnhub_api_key:
            raise FinnhubFundamentalsError("FINNHUB_API_KEY is not configured.")

        params = {"symbol": ticker, "token": settings.finnhub_api_key, **(extra_params or {})}
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise FinnhubFundamentalsError(f"Finnhub request failed for {ticker}: {exc}") from exc
