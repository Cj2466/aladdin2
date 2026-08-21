import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.services.risk import beta as beta_svc
from app.services.risk import returns as returns_svc

PricesFn = Callable[[list[str], date, date], tuple[pd.DataFrame, list[str]]]

# ~5 trading days, approximated as calendar days for simplicity.
ACTUAL_COVERAGE_TOLERANCE_DAYS = 7
BETA_LOOKBACK_YEARS = 3


@dataclass
class StressScenario:
    id: str
    label: str
    start: date
    end: date
    description: str


SCENARIOS: dict[str, StressScenario] = {
    "gfc_2008": StressScenario(
        id="gfc_2008",
        label="2008 Global Financial Crisis",
        start=date(2007, 10, 9),
        end=date(2009, 3, 9),
        description=(
            "Full peak-to-trough bear market (S&P 500 close ~1565 -> ~677, "
            "about -56.8%), not just the Sept-Nov Lehman window."
        ),
    ),
    "covid_2020": StressScenario(
        id="covid_2020",
        label="COVID-19 Crash",
        start=date(2020, 2, 19),
        end=date(2020, 3, 23),
        description="S&P 500 close ~3386 -> ~2237, about -33.9%, over roughly five weeks.",
    ),
    "rate_hikes_2022": StressScenario(
        id="rate_hikes_2022",
        label="2022 Rate-Hike Drawdown",
        start=date(2022, 1, 3),
        end=date(2022, 10, 12),
        description="S&P 500 close ~4797 -> ~3577, about -25.4%, as the Fed raised rates aggressively.",
    ),
}


@dataclass
class HoldingStressResult:
    ticker: str
    weight: float
    return_pct: float
    basis: str  # "actual" | "estimated"


@dataclass
class ScenarioResult:
    scenario_id: str
    label: str
    description: str
    start: str
    end: str
    portfolio_return: float
    benchmark_return: float
    has_estimated: bool
    holdings: list[HoldingStressResult]


def compute_stress_impact(
    weights: dict[str, float],
    benchmark: str,
    prices_fn: PricesFn,
) -> list[ScenarioResult]:
    """Apply each named historical scenario to the current holdings. A
    holding gets its "actual" realized return if price history covers the
    full scenario window; otherwise a beta-scaled "estimated" proxy off the
    benchmark, tagged as such — never blended untagged."""
    tickers = list(weights.keys())
    all_tickers = list(dict.fromkeys([*tickers, benchmark]))

    # Beta doesn't depend on which scenario we're in, so it's estimated once
    # per ticker (lazily, only for tickers that actually need it) rather
    # than refetched per scenario.
    beta_cache: dict[str, float] = {}

    results: list[ScenarioResult] = []
    for scenario in SCENARIOS.values():
        prices, _missing = prices_fn(all_tickers, scenario.start, scenario.end)

        benchmark_series = prices[benchmark] if benchmark in prices.columns else None
        benchmark_return = _window_return(benchmark_series) if benchmark_series is not None else 0.0

        holding_results: list[HoldingStressResult] = []
        has_estimated = False

        for ticker in tickers:
            series = prices[ticker] if ticker in prices.columns else None
            if series is not None and _covers_window(series, scenario.start, scenario.end):
                holding_results.append(
                    HoldingStressResult(
                        ticker=ticker,
                        weight=weights[ticker],
                        return_pct=_window_return(series),
                        basis="actual",
                    )
                )
                continue

            has_estimated = True
            if ticker not in beta_cache:
                beta_cache[ticker] = _estimate_beta(ticker, benchmark, prices_fn)
            holding_results.append(
                HoldingStressResult(
                    ticker=ticker,
                    weight=weights[ticker],
                    return_pct=beta_cache[ticker] * benchmark_return,
                    basis="estimated",
                )
            )

        portfolio_return = sum(h.weight * h.return_pct for h in holding_results)

        results.append(
            ScenarioResult(
                scenario_id=scenario.id,
                label=scenario.label,
                description=scenario.description,
                start=str(scenario.start),
                end=str(scenario.end),
                portfolio_return=portfolio_return,
                benchmark_return=benchmark_return,
                has_estimated=has_estimated,
                holdings=holding_results,
            )
        )

    return results


def _window_return(series: pd.Series) -> float:
    clean = series.dropna()
    if len(clean) < 2:
        return 0.0
    return float(clean.iloc[-1] / clean.iloc[0] - 1)


def _covers_window(series: pd.Series, start: date, end: date) -> bool:
    clean = series.dropna()
    if clean.empty:
        return False
    tolerance = timedelta(days=ACTUAL_COVERAGE_TOLERANCE_DAYS)
    first_date = clean.index.min().date()
    last_date = clean.index.max().date()
    return first_date <= start + tolerance and last_date >= end - tolerance


def _estimate_beta(ticker: str, benchmark: str, prices_fn: PricesFn) -> float:
    end = date.today()
    start = end - timedelta(days=int(BETA_LOOKBACK_YEARS * 365.25))
    prices, _missing = prices_fn([ticker, benchmark], start, end)
    if ticker not in prices.columns or benchmark not in prices.columns:
        return 0.0

    asset_returns = returns_svc.compute_daily_returns(prices[[ticker]])[ticker]
    benchmark_returns = returns_svc.compute_daily_returns(prices[[benchmark]])[benchmark]
    beta_value = beta_svc.compute_beta(asset_returns, benchmark_returns)
    return 0.0 if math.isnan(beta_value) else beta_value
