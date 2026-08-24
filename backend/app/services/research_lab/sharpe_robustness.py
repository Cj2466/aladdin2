from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

# Companion diagnostic to deflated_sharpe.py, addressing the same concern
# CPCV (Combinatorial Purged Cross-Validation) targets — that overlapping
# fit windows can inflate a Sharpe's apparent precision — without building
# literal CPCV. Confirmed by direct code read: run_walk_forward fits
# strictly on [t-fit_window_days, t) and tests only at t, forward-only,
# zero gap needed — by construction this already lacks CPCV's two target
# leakage modes (forward-looking multi-day labels causing train/test
# overlap; non-chronological fold reordering). Building it would be
# applying a fix to a leak that doesn't exist in this architecture.
#
# Empirically measured 2026-08-25 against 4 real 5-year backtests: lag-1
# autocorrelation of realized daily P&L ranged -0.013 to +0.191 (small,
# inconsistent sign). A moving-block bootstrap (block length = each
# backtest's own median trade holding-days) gave a Sharpe SE within
# 0.88x-1.02x of the naive analytic SE across all 3 real cases with enough
# trades to test — the theoretical concern is real in principle but small
# in this architecture's actual measured output. This diagnostic is
# additive/informational, never a rewrite of the existing Sharpe or DSR
# numbers — overstating the correction relative to the evidence would
# itself be a form of the dishonesty this project exists to avoid.

BLOCK_BOOTSTRAP_N = 2000
MIN_TRADES_FOR_BLOCK_BOOTSTRAP = 3
MIN_BLOCK_LEN_DAYS = 5

# Not crossed in any real case tested this session (max observed 1.02x) —
# a threshold for flagging, not a number derived from a target false-positive
# rate.
SE_INFLATION_FLAG_THRESHOLD = 1.3


@dataclass
class SharpeRobustnessResult:
    naive_se_annualized: float
    block_bootstrap_se_annualized: float
    se_inflation_ratio: float
    block_length_days: int
    n_bootstrap_samples: int
    flagged: bool
    note: str


def _naive_sharpe_se_annualized(returns: pd.Series) -> float | None:
    """Analytic SE of the Sharpe estimator under the i.i.d. assumption
    (Lo, 2002 first-order approximation), annualized the same way
    metrics.sharpe_ratio itself scales its point estimate."""
    n = len(returns)
    if n < 2:
        return None
    sharpe_daily = returns.mean() / returns.std(ddof=1) if returns.std(ddof=1) != 0 else 0.0
    se_daily = np.sqrt((1 + 0.5 * sharpe_daily**2) / n)
    if not np.isfinite(se_daily):
        return None
    return float(se_daily * np.sqrt(TRADING_DAYS_PER_YEAR))


def _block_bootstrap_sharpe_se_annualized(
    returns: pd.Series, block_length_days: int, n_samples: int
) -> float | None:
    """Moving-block bootstrap: resample overlapping blocks of consecutive
    daily returns (preserving whatever short-range autocorrelation is
    actually present, unlike an i.i.d. resample) until the original length
    is reached, recompute annualized Sharpe each time, take the std of the
    resulting distribution as the SE estimate."""
    values = returns.to_numpy()
    n = len(values)
    if n < block_length_days:
        return None

    n_blocks_needed = int(np.ceil(n / block_length_days))
    max_start = n - block_length_days
    sharpes = np.empty(n_samples)
    for i in range(n_samples):
        starts = np.random.randint(0, max_start + 1, size=n_blocks_needed)
        sample = np.concatenate([values[s : s + block_length_days] for s in starts])[:n]
        std = sample.std(ddof=1)
        sharpe_daily = sample.mean() / std if std != 0 else 0.0
        sharpes[i] = sharpe_daily * np.sqrt(TRADING_DAYS_PER_YEAR)

    se = float(np.std(sharpes, ddof=1))
    return se if np.isfinite(se) else None


def compute_sharpe_robustness(
    net_returns: pd.Series, trade_holding_days: list[int], sharpe_annualized: float
) -> SharpeRobustnessResult | None:
    """None when there isn't enough data to make either SE estimate
    meaningful — a diagnostic that can't be computed reliably must not
    silently render a misleadingly precise number."""
    naive_se = _naive_sharpe_se_annualized(net_returns)
    if naive_se is None:
        return None

    closed_holding_days = [d for d in trade_holding_days if d > 0]
    if len(closed_holding_days) < MIN_TRADES_FOR_BLOCK_BOOTSTRAP:
        return None

    block_length = max(MIN_BLOCK_LEN_DAYS, int(np.median(closed_holding_days)))
    bootstrap_se = _block_bootstrap_sharpe_se_annualized(net_returns, block_length, BLOCK_BOOTSTRAP_N)
    if bootstrap_se is None:
        return None

    ratio = bootstrap_se / naive_se if naive_se != 0 else 1.0
    flagged = ratio >= SE_INFLATION_FLAG_THRESHOLD

    if flagged:
        note = (
            f"The block-bootstrap Sharpe SE ({bootstrap_se:.2f}) runs {ratio:.2f}x higher than the naive "
            f"analytic SE ({naive_se:.2f}) — this backtest's trades may be more autocorrelated than the "
            "naive Sharpe formula assumes, meaning the true uncertainty around this Sharpe is wider than "
            "it looks."
        )
    else:
        note = (
            f"The block-bootstrap Sharpe SE ({bootstrap_se:.2f}) is close to the naive analytic SE "
            f"({naive_se:.2f}, {ratio:.2f}x) — no meaningful autocorrelation inflation detected in this "
            "backtest's realized daily returns."
        )

    return SharpeRobustnessResult(
        naive_se_annualized=naive_se,
        block_bootstrap_se_annualized=bootstrap_se,
        se_inflation_ratio=ratio,
        block_length_days=block_length,
        n_bootstrap_samples=BLOCK_BOOTSTRAP_N,
        flagged=flagged,
        note=note,
    )
