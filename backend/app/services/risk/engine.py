from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd

from app.schemas.risk import PortfolioAnalyzeResponse
from app.services.risk import beta as beta_svc
from app.services.risk import correlation as corr_svc
from app.services.risk import diversification as div_svc
from app.services.risk import returns as returns_svc
from app.services.risk import var as var_svc
from app.services.risk import volatility as vol_svc
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError

MIN_OBS_FOR_ANY_ESTIMATE = 20
NOISY_ESTIMATE_TRADING_DAYS = 500  # ~2 years

PricesFn = Callable[[list[str], date, date], tuple[pd.DataFrame, list[str]]]


def compute_portfolio_risk(
    weights: dict[str, float],
    benchmark: str,
    lookback_years: int,
    prices_fn: PricesFn,
) -> PortfolioAnalyzeResponse:
    """Framework-agnostic core of portfolio risk analysis — no FastAPI
    imports, so it's reusable by both the stateless /analyze endpoint and
    the authenticated saved-portfolio endpoint. `prices_fn` abstracts away
    whether the caller wants a raw provider fetch or a cached one; this
    function doesn't know or care which."""
    warnings: list[str] = []
    tickers = list(weights.keys())

    end = date.today()
    start = end - timedelta(days=int(lookback_years * 365.25))

    all_tickers = list(dict.fromkeys([*tickers, benchmark]))
    prices, missing = prices_fn(all_tickers, start, end)

    missing_required = [t for t in tickers if t not in prices.columns]
    if missing_required:
        raise MissingTickerDataError(missing_required)
    if benchmark not in prices.columns:
        raise MissingTickerDataError([benchmark], is_benchmark=True)
    if missing:
        warnings.append(f"No data returned for: {', '.join(missing)}")

    asset_returns = returns_svc.compute_daily_returns(prices[tickers])
    benchmark_returns = returns_svc.compute_daily_returns(prices[[benchmark]])[benchmark]
    portfolio_returns = returns_svc.compute_portfolio_returns(asset_returns, weights)

    n_obs = len(portfolio_returns)
    if n_obs < MIN_OBS_FOR_ANY_ESTIMATE:
        raise InsufficientHistoryError(n_obs)
    if n_obs < NOISY_ESTIMATE_TRADING_DAYS:
        approx_years = n_obs / 252
        warnings.append(
            f"Only ~{approx_years:.1f} years of overlapping history available; "
            "VaR tail estimates are noisy below ~5 years."
        )

    corr = corr_svc.correlation_matrix(asset_returns)

    return PortfolioAnalyzeResponse(
        as_of=str(prices.index.max().date()),
        volatility_annualized=vol_svc.annualized_volatility(portfolio_returns),
        var_historical_95=var_svc.historical_var(portfolio_returns),
        var_parametric_95=var_svc.parametric_var(portfolio_returns),
        cvar_95=var_svc.conditional_var(portfolio_returns),
        beta=beta_svc.compute_beta(portfolio_returns, benchmark_returns),
        hhi=div_svc.herfindahl_index(weights),
        avg_pairwise_correlation=div_svc.average_pairwise_correlation(corr),
        correlation_matrix=corr.round(4).to_dict(),
        warnings=warnings,
    )
