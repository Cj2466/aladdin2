from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.risk import returns as returns_svc
from app.services.risk.engine import NOISY_ESTIMATE_TRADING_DAYS
from app.services.risk.errors import InsufficientHistoryError, MissingTickerDataError
from app.services.risk.volatility import TRADING_DAYS_PER_YEAR

PricesFn = Callable[[list[str], date, date], tuple[pd.DataFrame, list[str]]]

# 6 factors + intercept = 7 free parameters. The rule-of-thumb minimum for
# stable OLS on noisy daily financial data is ~10-20 observations per
# parameter (vs. engine.py's MIN_OBS_FOR_ANY_ESTIMATE = 20, which estimates
# only a single mean/variance — effectively ~1-2 parameters). 126 trading
# days (~6 months) gives ~18 obs/parameter, avoiding a rank-deficient or
# wildly unstable fit while still working for recently-listed holdings.
MIN_OBS_FOR_FACTOR_REGRESSION = 126


@dataclass(frozen=True)
class FactorDefinition:
    key: str
    label: str
    long: str
    short: str | None  # None => raw return of `long`, not a spread


# ETF-proxy factor set — a well-established, licensing-free simplification
# of a proprietary multi-factor model (Barra/Axioma-style) for a retail
# app. Market is a raw ETF return; the rest are long-short spreads
# (Fama-French style) so each isolates one style tilt net of market
# exposure. This Market definition is fixed and independent of whatever
# benchmark a user separately picks for the single-factor `beta` field
# elsewhere in the app — a factor model needs one consistent Market leg.
FACTOR_DEFINITIONS: tuple[FactorDefinition, ...] = (
    FactorDefinition(key="market", label="Market", long="SPY", short=None),
    FactorDefinition(key="size", label="Size", long="IWM", short="SPY"),
    FactorDefinition(key="value", label="Value", long="VTV", short="VUG"),
    FactorDefinition(key="momentum", label="Momentum", long="MTUM", short="SPY"),
    FactorDefinition(key="quality", label="Quality", long="QUAL", short="SPY"),
    FactorDefinition(key="low_volatility", label="Low Volatility", long="USMV", short="SPY"),
)

FACTOR_PROXY_TICKERS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [d.long for d in FACTOR_DEFINITIONS] + [d.short for d in FACTOR_DEFINITIONS if d.short]
    )
)  # ("SPY", "IWM", "VTV", "VUG", "MTUM", "QUAL", "USMV")


@dataclass
class HoldingFactorFit:
    ticker: str
    betas: dict[str, float]  # factor key -> beta
    alpha_annualized: float  # intercept * 252 — raw (non-excess) returns only shift this,
    #                          not the betas, so it isn't surfaced in the API.
    r_squared: float
    idiosyncratic_volatility_annualized: float


@dataclass
class FactorRiskResult:
    as_of: str
    factor_exposures: dict[str, float]  # factor key -> portfolio-level weighted beta (can be < 0)
    factor_risk_contribution_pct: dict[str, float]  # factor key -> share of TOTAL portfolio
    #    variance (factor + idiosyncratic); can rarely be negative for a diversifying factor
    idiosyncratic_risk_pct: float
    factor_variance_annualized: float
    idiosyncratic_variance_annualized: float
    total_variance_annualized: float
    holdings: list[HoldingFactorFit]
    warnings: list[str] = field(default_factory=list)


def _build_factor_returns(raw_returns: pd.DataFrame) -> pd.DataFrame:
    data = {}
    for fd in FACTOR_DEFINITIONS:
        data[fd.key] = raw_returns[fd.long] if fd.short is None else raw_returns[fd.long] - raw_returns[fd.short]
    return pd.DataFrame(data)


def compute_factor_risk(
    weights: dict[str, float],
    lookback_years: int,
    prices_fn: PricesFn,
) -> FactorRiskResult:
    """Framework-agnostic core of the factor-risk decomposition — mirrors
    compute_portfolio_risk's shape so it's reusable by both the stateless
    and authenticated endpoints. Regresses each holding's daily return
    against 6 ETF-proxy style factors (with intercept), then aggregates to
    portfolio level via weighted-sum exposures and an Euler variance
    decomposition. Assumes idiosyncratic (residual) returns are
    uncorrelated across holdings, the standard factor-model simplification
    — understated here more than in a full Barra model, since only 6 broad
    style factors are used (no industry factors), so residual correlation
    within the same narrow industry isn't captured."""
    warnings: list[str] = []
    tickers = list(weights.keys())

    end = date.today()
    start = end - timedelta(days=int(lookback_years * 365.25))

    all_tickers = list(dict.fromkeys([*tickers, *FACTOR_PROXY_TICKERS]))
    prices, missing = prices_fn(all_tickers, start, end)

    missing_holdings = [t for t in tickers if t not in prices.columns]
    if missing_holdings:
        raise MissingTickerDataError(missing_holdings)
    missing_factor_tickers = [t for t in FACTOR_PROXY_TICKERS if t not in prices.columns]
    if missing_factor_tickers:
        raise MissingTickerDataError(missing_factor_tickers, label="factor proxy ETFs")
    if missing:
        warnings.append(f"No data returned for: {', '.join(missing)}")

    raw_returns = returns_svc.compute_daily_returns(prices[all_tickers])
    factor_returns = _build_factor_returns(raw_returns)
    factor_keys = [d.key for d in FACTOR_DEFINITIONS]

    aligned = pd.concat([raw_returns[tickers], factor_returns], axis=1).dropna()
    n_obs = len(aligned)
    if n_obs < MIN_OBS_FOR_FACTOR_REGRESSION:
        raise InsufficientHistoryError(n_obs)
    if n_obs < NOISY_ESTIMATE_TRADING_DAYS:
        approx_years = n_obs / TRADING_DAYS_PER_YEAR
        warnings.append(
            f"Only ~{approx_years:.1f} years of overlapping history available; "
            "factor betas are noisy below ~2 years."
        )

    X = np.column_stack([np.ones(n_obs), aligned[factor_keys].to_numpy()])

    holding_fits: list[HoldingFactorFit] = []
    beta_matrix = np.zeros((len(tickers), len(factor_keys)))
    idio_var_by_ticker: dict[str, float] = {}

    for i, ticker in enumerate(tickers):
        y = aligned[ticker].to_numpy()
        coeffs, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
        if rank < X.shape[1]:
            warnings.append(
                f"{ticker}: factor returns were collinear over this window "
                "(rank-deficient fit); betas may be unstable."
            )

        fitted = X @ coeffs
        resid = y - fitted
        ss_res = float(np.sum(resid**2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r_squared = float("nan") if ss_tot == 0 else 1.0 - ss_res / ss_tot
        idio_vol_annualized = float(np.std(resid, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))

        beta_matrix[i, :] = coeffs[1:]
        idio_var_by_ticker[ticker] = idio_vol_annualized**2
        holding_fits.append(
            HoldingFactorFit(
                ticker=ticker,
                betas=dict(zip(factor_keys, coeffs[1:].tolist())),
                alpha_annualized=float(coeffs[0] * TRADING_DAYS_PER_YEAR),
                r_squared=r_squared,
                idiosyncratic_volatility_annualized=idio_vol_annualized,
            )
        )

    weight_vector = np.array([weights[t] for t in tickers])
    exposure = weight_vector @ beta_matrix  # exact, not an approximation — OLS is linear in y,
    #   and portfolio return is a weighted sum of holding returns over the same design matrix.

    factor_cov = aligned[factor_keys].cov().to_numpy() * TRADING_DAYS_PER_YEAR
    factor_variance = float(exposure @ factor_cov @ exposure)
    idiosyncratic_variance = float(sum((weights[t] ** 2) * idio_var_by_ticker[t] for t in tickers))
    total_variance = factor_variance + idiosyncratic_variance

    marginal = factor_cov @ exposure  # sums exactly to factor_variance via exposure . marginal
    contributions = exposure * marginal

    if total_variance > 0:
        factor_risk_contribution_pct = {k: float(c / total_variance) for k, c in zip(factor_keys, contributions)}
        idiosyncratic_risk_pct = float(idiosyncratic_variance / total_variance)
    else:
        factor_risk_contribution_pct = dict.fromkeys(factor_keys, 0.0)
        idiosyncratic_risk_pct = 0.0

    return FactorRiskResult(
        as_of=str(prices.index.max().date()),
        factor_exposures=dict(zip(factor_keys, exposure.tolist())),
        factor_risk_contribution_pct=factor_risk_contribution_pct,
        idiosyncratic_risk_pct=idiosyncratic_risk_pct,
        factor_variance_annualized=factor_variance,
        idiosyncratic_variance_annualized=idiosyncratic_variance,
        total_variance_annualized=total_variance,
        holdings=holding_fits,
        warnings=warnings,
    )
