from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.research_lab import momentum, ou_pairs
from app.services.research_lab.momentum import fit_momentum_window
from app.services.risk.correlation import correlation_matrix
from app.services.risk.returns import compute_daily_returns

# Empirically verified 2026-08-24 against 108 real large-cap tickers: taking
# 721 pairs that only passed a |corr| >= 0.3 prune and running the real
# fit_ou_pairs_window on them, 716 (99.3%) passed is_valid — matching the
# already-documented ~97-100% spurious-pass rate on pure noise. The AR(1)
# fit does not discriminate at screening time; correlation magnitude alone
# is the real filter. At |corr| >= 0.6, top hits were overwhelmingly
# same-sector economically-linked pairs (banks with banks, energy majors
# with energy majors) — a real, checked signal, not a guess.
MIN_SCREENING_CORRELATION = 0.6
MAX_PAIRS_CANDIDATES_STORED = 40

# Empirically verified 2026-08-24: fit_momentum_window's p<=0.05 gate,
# applied to 108 real tickers' trailing 90 days, passed 84.3% of them — not
# the ~5% a pure-noise null would suggest. Real large-caps share market-wide
# beta a single-asset OLS-on-time regression can't separate from genuine
# idiosyncratic trend, especially in a trending regime. The significance
# gate stays as a floor (never surface an insignificant fit) but the real
# narrowing is ranking by |t_stat| and a hard cap, not the gate alone.
MAX_MOMENTUM_CANDIDATES_STORED = 20

MOMENTUM_SCREENING_METHODOLOGY_NOTE = (
    "{universe_size} tickers were screened together — at p<=0.05, roughly 5% would be expected "
    "to clear this bar on pure chance alone even with zero real trend. On a broadly trending "
    "market the actual pass rate can run far higher (empirically ~84% against 108 real "
    "large-caps on 2026-08-24) because most stocks share the same market-wide move a "
    "single-asset regression cannot separate from genuine idiosyncratic trend. This is the "
    "top-ranked-by-|t-stat| shortlist, not a validated result — only a full walk-forward "
    "backtest on a specific candidate carries evidentiary weight."
)

PAIRS_SCREENING_METHODOLOGY_NOTE = (
    "High correlation means two tickers moved together — it does NOT mean their spread is "
    "mean-reverting (cointegrated), a materially weaker claim than ou_pairs_v1's own AR(1) "
    "walk-forward test. A structural AR(1) check was deliberately not used as an additional "
    "filter here (empirically verified it doesn't discriminate at pre-filter time). Only the "
    "full walk-forward backtest below carries evidentiary weight."
)


def build_screening_methodology_note(strategy_name: str, universe_size: int) -> str:
    if strategy_name == momentum.STRATEGY_NAME:
        return MOMENTUM_SCREENING_METHODOLOGY_NOTE.format(universe_size=universe_size)
    return PAIRS_SCREENING_METHODOLOGY_NOTE


@dataclass
class MomentumCandidate:
    ticker: str
    t_stat: float
    direction: str  # "long" | "short"
    fit_quality: str | None


@dataclass
class PairsCandidate:
    ticker_a: str
    ticker_b: str
    correlation: float


def screen_momentum_universe(prices: pd.DataFrame) -> list[MomentumCandidate]:
    """For each ticker independently: take the trailing fit-window rows of
    log price, run the exact same fit_momentum_window the live momentum_v1
    strategy uses (zero new statistics), keep it iff is_valid, rank by
    |t_stat|. A ticker with insufficient history is silently skipped, not
    an error."""
    candidates: list[MomentumCandidate] = []
    for ticker in prices.columns:
        series = prices[ticker].dropna()
        if len(series) < momentum.DEFAULT_FIT_WINDOW_DAYS:
            continue
        window = pd.DataFrame({"log_price": np.log(series.iloc[-momentum.DEFAULT_FIT_WINDOW_DAYS :])})
        fit = fit_momentum_window(window)
        if not fit.is_valid or fit.z_score is None:
            continue
        candidates.append(
            MomentumCandidate(
                ticker=ticker,
                t_stat=fit.z_score,
                direction="long" if fit.z_score > 0 else "short",
                fit_quality=fit.fit_quality,
            )
        )
    candidates.sort(key=lambda c: abs(c.t_stat), reverse=True)
    return candidates[:MAX_MOMENTUM_CANDIDATES_STORED]


def _pairs_from_correlation_matrix(
    corr: pd.DataFrame, min_corr: float, max_candidates: int
) -> list[PairsCandidate]:
    """Pure, RNG-free — extracted specifically so it's unit-testable
    against a hand-built matrix, mirroring why apply_zscore_threshold_rule
    was extracted out of step_one_day."""
    candidates: list[PairsCandidate] = []
    tickers = list(corr.columns)
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            value = corr.iloc[i, j]
            if pd.isna(value):
                continue
            if abs(value) >= min_corr:
                candidates.append(
                    PairsCandidate(ticker_a=tickers[i], ticker_b=tickers[j], correlation=float(value))
                )
    candidates.sort(key=lambda c: abs(c.correlation), reverse=True)
    return candidates[:max_candidates]


def screen_pairs_universe(prices: pd.DataFrame) -> list[PairsCandidate]:
    """Restrict to a clean common trailing window (drop any ticker with a
    gap in it, rather than silently down-weighting sparser tickers), reuse
    compute_daily_returns/correlation_matrix verbatim (simple returns,
    matching risk/engine.py's existing convention), then filter. No AR(1)
    check at this stage — see MIN_SCREENING_CORRELATION's docstring."""
    window = prices.tail(ou_pairs.DEFAULT_FIT_WINDOW_DAYS + 1).dropna(axis=1, how="any")
    if window.shape[1] < 2:
        return []
    returns = compute_daily_returns(window)
    corr = correlation_matrix(returns)
    return _pairs_from_correlation_matrix(corr, MIN_SCREENING_CORRELATION, MAX_PAIRS_CANDIDATES_STORED)
