import numpy as np
import pandas as pd

from app.services.research_lab.sharpe_robustness import (
    MIN_TRADES_FOR_BLOCK_BOOTSTRAP,
    compute_sharpe_robustness,
)


def _synthetic_returns(n: int, seed: int, mean: float = 0.0005, std: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mean, std, n))


def test_compute_sharpe_robustness_returns_none_below_min_trades():
    returns = _synthetic_returns(300, seed=1)
    # Only 2 closed trades — below MIN_TRADES_FOR_BLOCK_BOOTSTRAP=3.
    result = compute_sharpe_robustness(returns, [10, 15], sharpe_annualized=1.0)
    assert result is None


def test_compute_sharpe_robustness_returns_none_for_too_short_series():
    returns = _synthetic_returns(3, seed=1)
    result = compute_sharpe_robustness(returns, [1, 1, 1, 1], sharpe_annualized=1.0)
    assert result is None


def test_compute_sharpe_robustness_ignores_zero_holding_day_open_trades():
    # trade_holding_days can include 0 for a still-open trade at the end of
    # the backtest window — must be excluded from the median block-length
    # calculation and from the min-trades-for-bootstrap count.
    returns = _synthetic_returns(300, seed=2)
    result = compute_sharpe_robustness(returns, [10, 15, 20, 0], sharpe_annualized=1.0)
    assert result is not None
    assert result.block_length_days == 15  # median of [10, 15, 20], not influenced by the 0


def test_compute_sharpe_robustness_on_iid_returns_ratio_near_one():
    # i.i.d. synthetic returns should show no meaningful SE inflation —
    # the bootstrap and naive SEs should land in the same ballpark.
    returns = _synthetic_returns(500, seed=42)
    result = compute_sharpe_robustness(returns, [10, 12, 8, 15, 9], sharpe_annualized=0.8)
    assert result is not None
    assert 0.5 < result.se_inflation_ratio < 2.0
    assert result.naive_se_annualized > 0
    assert result.block_bootstrap_se_annualized > 0


def test_compute_sharpe_robustness_flags_strongly_autocorrelated_returns():
    # Construct returns with strong positive block-level autocorrelation
    # (repeated runs of the same sign in big blocks) — the block bootstrap
    # should show meaningfully more spread than the naive i.i.d. formula.
    rng = np.random.default_rng(7)
    n_blocks = 40
    block_len = 10
    block_means = rng.normal(0, 0.03, n_blocks)
    values = np.concatenate([np.full(block_len, m) + rng.normal(0, 0.002, block_len) for m in block_means])
    returns = pd.Series(values)
    result = compute_sharpe_robustness(returns, [block_len] * 5, sharpe_annualized=0.5)
    assert result is not None
    assert result.se_inflation_ratio > 1.0


def test_min_trades_for_block_bootstrap_is_three():
    assert MIN_TRADES_FOR_BLOCK_BOOTSTRAP == 3
