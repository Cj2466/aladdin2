import numpy as np
import pandas as pd
import pytest

from app.services.risk.errors import InsufficientHistoryError
from app.services.risk.factor_model import (
    FACTOR_DEFINITIONS,
    FACTOR_PROXY_TICKERS,
    MIN_OBS_FOR_FACTOR_REGRESSION,
    _build_factor_returns,
    compute_factor_risk,
)

FACTOR_KEYS = [d.key for d in FACTOR_DEFINITIONS]


def _make_returns(n_days: int, seed: int, loc: float = 0.0003, scale: float = 0.01) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(loc=loc, scale=scale, size=n_days)


def _prices_from_returns(returns: np.ndarray, start_price: float = 100.0) -> np.ndarray:
    return start_price * np.cumprod(1 + returns)


def _factor_frame(n_days: int, seed_offset: int = 0) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    returns_by_ticker = {
        ticker: _make_returns(n_days, seed=seed_offset + i)
        for i, ticker in enumerate(FACTOR_PROXY_TICKERS)
    }
    prices = {t: _prices_from_returns(r) for t, r in returns_by_ticker.items()}
    return pd.DataFrame(prices, index=dates), returns_by_ticker


def _with_holdings(base_prices: pd.DataFrame, holdings: dict[str, np.ndarray]) -> pd.DataFrame:
    frame = base_prices.copy()
    for ticker, returns in holdings.items():
        frame[ticker] = _prices_from_returns(returns)
    return frame


def _prices_fn_from_frame(frame: pd.DataFrame):
    def prices_fn(tickers, start, end):
        present = [t for t in tickers if t in frame.columns]
        missing = [t for t in tickers if t not in frame.columns]
        return frame[present], missing

    return prices_fn


def test_pure_market_holding_has_beta_one_and_high_r_squared():
    n_days = 300
    base_prices, factor_returns = _factor_frame(n_days)
    frame = _with_holdings(base_prices, {"PUREMKT": factor_returns["SPY"]})

    result = compute_factor_risk({"PUREMKT": 1.0}, 3, _prices_fn_from_frame(frame))

    fit = result.holdings[0]
    assert fit.betas["market"] == pytest.approx(1.0, abs=1e-6)
    for key in FACTOR_KEYS:
        if key != "market":
            assert fit.betas[key] == pytest.approx(0.0, abs=1e-6)
    assert fit.r_squared == pytest.approx(1.0, abs=1e-6)
    assert fit.idiosyncratic_volatility_annualized == pytest.approx(0.0, abs=1e-6)


def test_pure_idiosyncratic_holding_has_low_r_squared_and_small_betas():
    n_days = 300
    base_prices, _ = _factor_frame(n_days)
    noise_returns = _make_returns(n_days, seed=999, loc=0.0, scale=0.02)
    frame = _with_holdings(base_prices, {"PURENOISE": noise_returns})

    result = compute_factor_risk({"PURENOISE": 1.0}, 3, _prices_fn_from_frame(frame))

    fit = result.holdings[0]
    assert fit.r_squared < 0.3
    assert all(abs(b) < 0.3 for b in fit.betas.values())
    assert result.idiosyncratic_risk_pct > 0.7


def test_portfolio_exposure_is_weighted_sum_of_holding_betas():
    n_days = 300
    base_prices, factor_returns = _factor_frame(n_days)
    lev2x = factor_returns["SPY"] * 2.0
    flat = _make_returns(n_days, seed=555, loc=0.0, scale=0.001)
    frame = _with_holdings(base_prices, {"LEV2X": lev2x, "FLAT": flat})

    weights = {"LEV2X": 0.6, "FLAT": 0.4}
    result = compute_factor_risk(weights, 3, _prices_fn_from_frame(frame))

    betas_by_ticker = {h.ticker: h.betas for h in result.holdings}
    expected_market = sum(weights[t] * betas_by_ticker[t]["market"] for t in weights)
    assert result.factor_exposures["market"] == pytest.approx(expected_market, abs=1e-9)


def test_portfolio_exposure_matches_direct_regression_of_portfolio_returns():
    """Bottom-up weighted aggregation of per-holding betas must equal what
    you'd get by regressing the portfolio's own return series directly
    against the same factors — a linearity check on the OLS aggregation."""
    n_days = 300
    base_prices, factor_returns = _factor_frame(n_days)
    a_returns = factor_returns["SPY"] * 1.3 + _make_returns(n_days, seed=1, scale=0.005)
    b_returns = factor_returns["IWM"] * 0.7 + _make_returns(n_days, seed=2, scale=0.005)
    frame = _with_holdings(base_prices, {"A": a_returns, "B": b_returns})
    weights = {"A": 0.5, "B": 0.5}

    result = compute_factor_risk(weights, 3, _prices_fn_from_frame(frame))

    from app.services.risk import returns as returns_svc

    all_tickers = [*weights, *FACTOR_PROXY_TICKERS]
    raw_returns = returns_svc.compute_daily_returns(frame[all_tickers])
    factor_frame = _build_factor_returns(raw_returns)
    portfolio_returns = returns_svc.compute_portfolio_returns(raw_returns[list(weights)], weights)
    aligned = pd.concat([portfolio_returns.rename("portfolio"), factor_frame], axis=1).dropna()

    X = np.column_stack([np.ones(len(aligned)), aligned[FACTOR_KEYS].to_numpy()])
    direct_coeffs, *_ = np.linalg.lstsq(X, aligned["portfolio"].to_numpy(), rcond=None)
    direct_market_beta = direct_coeffs[1 + FACTOR_KEYS.index("market")]

    assert result.factor_exposures["market"] == pytest.approx(direct_market_beta, abs=1e-6)


def test_risk_contributions_sum_to_total():
    n_days = 300
    base_prices, factor_returns = _factor_frame(n_days)
    a_returns = factor_returns["SPY"] * 1.1 + _make_returns(n_days, seed=1, scale=0.008)
    b_returns = factor_returns["VTV"] * 0.4 + _make_returns(n_days, seed=2, scale=0.01)
    frame = _with_holdings(base_prices, {"A": a_returns, "B": b_returns})
    weights = {"A": 0.5, "B": 0.5}

    result = compute_factor_risk(weights, 3, _prices_fn_from_frame(frame))

    total_pct = sum(result.factor_risk_contribution_pct.values()) + result.idiosyncratic_risk_pct
    assert total_pct == pytest.approx(1.0, abs=1e-9)


def test_insufficient_history_raises():
    n_days = MIN_OBS_FOR_FACTOR_REGRESSION - 10
    base_prices, factor_returns = _factor_frame(n_days)
    frame = _with_holdings(base_prices, {"A": factor_returns["SPY"]})

    with pytest.raises(InsufficientHistoryError):
        compute_factor_risk({"A": 1.0}, 3, _prices_fn_from_frame(frame))
