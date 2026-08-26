from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from statsmodels.tsa.stattools import coint

from app.services.research_lab import momentum, ou_pairs, regime
from app.services.research_lab.momentum import fit_momentum_window
from app.services.research_lab.regime_hmm import classify_regime_hmm
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
# Re-verified after the Phase 3 108->503 universe expansion: at |corr|>=0.6
# over the 503-ticker S&P 500 universe, 934/123,753 pairs (0.75%) clear the
# bar — already well above MAX_PAIRS_CANDIDATES_STORED, i.e. the cap was
# already binding at 108 tickers and remains binding (proportionally more
# so) at 503. No threshold/cap change needed, only this comment refresh.
MIN_SCREENING_CORRELATION = 0.6
MAX_PAIRS_CANDIDATES_STORED = 40

# Engle-Granger cointegration (statsmodels.tsa.stattools.coint) — a formal
# ADF unit-root hypothesis test on the OLS residual, genuinely distinct
# from the AR(1)/OU structural coefficient-bounds check above (which
# ou_pairs.py's own docstring states is "NOT a cointegration/unit-root
# test"). Empirically verified twice independently on 2026-08-25: on the
# real 503-ticker universe, the |corr|>=0.6 prefilter passes ~935 pairs;
# a second-stage Engle-Granger test at p<=0.05 over a 500-trading-day
# window narrows that to ~10% (9.7%-10.8% across two independent runs).
# A spurious-pass control (400 synthetic correlated-but-not-cointegrated
# pairs sharing a random-walk factor) passed at 5.6%, matching the ~5%
# null rate — well-calibrated, not spurious, unlike the AR(1) fit above.
COINTEGRATION_WINDOW_TRADING_DAYS = 500
COINTEGRATION_P_VALUE_THRESHOLD = 0.05
# Headroom above the real observed correlation-pass count (934/123,753 at
# 503 tickers) — this must NOT bind before the cointegration filter runs.
# Verified: capping at MAX_PAIRS_CANDIDATES_STORED=40 first, then running
# cointegration on just those 40, leaves ~2 survivors instead of the ~100
# the full correlation-passing set yields — capping too early starves the
# second-stage test of candidates it would otherwise find.
MAX_CORRELATION_CANDIDATES_BEFORE_COINTEGRATION = 2000

# Empirically verified 2026-08-24: fit_momentum_window's p<=0.05 gate,
# applied to 108 real tickers' trailing 90 days, passed 84.3% of them — not
# the ~5% a pure-noise null would suggest. Real large-caps share market-wide
# beta a single-asset OLS-on-time regression can't separate from genuine
# idiosyncratic trend, especially in a trending regime. The significance
# gate stays as a floor (never surface an insignificant fit) but the real
# narrowing is ranking by |t_stat| and a hard cap, not the gate alone.
# Re-verified after the Phase 3 108->503 universe expansion: 429/501 (85.6%)
# of the S&P 500 universe passes (2 skipped for insufficient history) —
# consistent with the original 108-ticker finding, same conclusion holds at
# the larger scale. No cap change needed.
MAX_MOMENTUM_CANDIDATES_STORED = 20

# Newey-West (HAC) standard errors on the same OLS-on-time regression
# fit_momentum_window itself runs — informational, computed alongside (not
# replacing) that gate, and only on the final top-MAX_MOMENTUM_CANDIDATES_
# STORED shortlist (a deliberate cost bound, see the HMM regime tag's
# comment below for why this restructuring is shared). Does NOT touch
# fit_momentum_window itself — that function is also the live trading
# signal every forward-validation registration uses; changing its internal
# test would silently alter trading behavior for existing registrations,
# a much bigger, unvalidated change than this addition should make.
# Empirically verified 2026-08-25 on 167 real tickers: the existing plain-
# OLS gate passes 89.8%; this HAC-corrected version, on the identical
# data, passes 73.7% — a real, if partial, calibration improvement (vs a
# plain daily-return t-test's 1.2%, the wrong reference bound, and
# fractional differentiation's 99.4% — rejected, see the module's git
# history for that finding).
#
# That 167-real-ticker comparison is NOT the same question as "is this
# gate well-calibrated against its own p<=0.05 threshold on pure noise" —
# real tickers share market-wide beta a single-asset regression can't
# separate from genuine trend (same caveat as the plain gate above), so a
# high real-ticker pass rate doesn't imply good calibration. Checked
# directly and it is not: regressing log-price on time is a textbook
# spurious-regression setup (Phillips 1986) — log price under a pure
# random walk is I(1)/non-stationary, and HAC/Newey-West correction with a
# *fixed* lag count (HAC_LAGS=5) does not fix the resulting t-stat
# divergence the way it does for a genuinely stationary-but-autocorrelated
# series; the bandwidth would need to grow with the sample size, which
# statsmodels' fixed-maxlags HAC does not do. Empirically verified
# 2026-08-26 (see tests/test_screening.py's
# test_hac_significant_false_positive_rate_on_random_walk_is_far_above_nominal,
# 500 independent pure-random-walk trials, n=90, matching an earlier
# audit's ~69% finding): this flag fires "significant" on ~76% (379/500)
# of trials where the underlying series is pure noise with zero real
# trend — not the ~5% its own p<=0.05 threshold implies. This is a known,
# structural limitation of applying HAC significance to a price-level
# trend regression, not a bug in this implementation, and is NOT fixed
# here — see MOMENTUM_SCREENING_METHODOLOGY_NOTE for the user-facing
# disclosure of the same finding. Kept as an informational tag only (see
# screen_momentum_universe's docstring — it never filters or ranks) is
# exactly why this miscalibration, while real, doesn't corrupt anything
# downstream on its own; disclosure is still required because the field is
# surfaced to users via ScreeningCandidateOut.hac_significant and could
# otherwise be misread as a validated, well-calibrated significance test.
HAC_LAGS = 5

MOMENTUM_SCREENING_METHODOLOGY_NOTE = (
    "{universe_size} tickers were screened together — at p<=0.05, roughly 5% would be expected "
    "to clear this bar on pure chance alone even with zero real trend. On a broadly trending "
    "market the actual pass rate can run far higher (empirically ~86% against 503 S&P 500 "
    "constituents on 2026-08-24) because most stocks share the same market-wide move a "
    "single-asset regression cannot separate from genuine idiosyncratic trend. This is the "
    "top-ranked-by-|t-stat| shortlist, not a validated result — only a full walk-forward "
    "backtest on a specific candidate carries evidentiary weight. Each shortlisted candidate "
    "also carries: a Newey-West (HAC) autocorrelation-corrected significance flag on the same "
    "trend regression (a stricter bar on real tickers — passes ~74% vs ~90% for the "
    "uncorrected gate above — but NOT well-calibrated against its own p<=0.05 threshold: "
    "on pure random-walk noise with zero real trend, empirically measured at ~76% (500 "
    "independent synthetic trials), this flag still fires 'significant' far more often than "
    "the 5% its threshold implies. Regressing log-price on time is a classic spurious-"
    "regression setup for a non-stationary series, and fixed-lag HAC correction does not fix "
    "that divergence — a known, structural limitation of this test, not a data problem. "
    "Treat this flag as informational only, never as evidence of a real trend on its own); "
    "a variance-ratio regime tag (trending / "
    "mean-reverting / indeterminate) testing whether that ticker's own returns are serially "
    "correlated — a well-calibrated test (empirically ~3-6% of the real universe clears it, "
    "close to the ~5% chance rate) but too conservative at per-ticker granularity to filter or "
    "rank on; and an HMM volatility-regime tag (high-vol / low-vol) — a materially different "
    "axis than the trend/mean-reversion regime tag, and one that's empirically unstable under "
    "small refit-window changes (~19% of nearby-window refits flip the label), so treat it as a "
    "coarse, current-state signal, not a stable classification. All three are shown as "
    "information only — none filters or ranks candidates."
)

PAIRS_SCREENING_METHODOLOGY_NOTE = (
    "Two-stage filter: first, |correlation| >= 0.6 over the trailing ~1 year (a weak prefilter — "
    "high correlation alone does NOT mean a pair's spread is mean-reverting). Second, an "
    "Engle-Granger cointegration test (a formal statistical test for whether the spread is "
    "stationary) over the trailing 500 trading days, kept only at p<=0.05 — empirically this "
    "narrows the correlation-passing set to roughly 10%, close to a synthetic spurious-pair "
    "control's ~5.6% null rate, i.e. well-calibrated. A structural AR(1) coefficient-bounds check "
    "was deliberately NOT used as a filter here (empirically verified it doesn't discriminate at "
    "pre-filter time — ~99% of merely-correlated pairs pass it). Pairs candidates also "
    "deliberately carry no per-ticker regime tag: a variance-ratio test on one leg's own returns "
    "answers a different question than whether the pair's spread mean-reverts — a cointegrated "
    "pair typically has each leg looking like its own random walk individually while the spread "
    "mean-reverts, so tagging legs this way would mislead rather than inform. Only the full "
    "walk-forward backtest below carries evidentiary weight."
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
    regime: str | None  # "trending" | "mean_reverting" | "indeterminate" | None (insufficient history)
    hac_significant: bool
    regime_hmm: str | None  # "high_vol" | "low_vol" | None (insufficient history or fit failure)


@dataclass
class PairsCandidate:
    ticker_a: str
    ticker_b: str
    correlation: float


def _hac_significant(log_price_window: np.ndarray) -> bool:
    """Newey-West (HAC) standard errors on the same OLS-on-time regression
    fit_momentum_window runs — see HAC_LAGS's module-level docstring for
    the empirical calibration comparison. NOT well-calibrated against its
    own p<=0.05 threshold on pure noise (empirically ~76% false-positive
    rate on random-walk data, see tests/test_screening.py's
    test_hac_significant_false_positive_rate_on_random_walk_is_far_above_nominal
    and MOMENTUM_SCREENING_METHODOLOGY_NOTE) — informational only, never
    treat True as evidence of a real trend on its own. Returns False (not
    an error) on a degenerate window or a fit failure — same "can't
    compute -> don't surface a misleading tag" convention as the other two
    informational tags below."""
    n = len(log_price_window)
    if n < 3 or np.std(log_price_window) == 0:
        return False
    t = np.arange(n, dtype=float)
    design = add_constant(t)
    try:
        result = OLS(log_price_window, design).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    except (ValueError, np.linalg.LinAlgError):
        return False
    p_value = result.pvalues[1]  # index 1 = slope; index 0 = constant
    return bool(np.isfinite(p_value) and p_value <= 0.05)


def screen_momentum_universe(prices: pd.DataFrame) -> list[MomentumCandidate]:
    """For each ticker independently: take the trailing fit-window rows of
    log price, run the exact same fit_momentum_window the live momentum_v1
    strategy uses (zero new statistics), keep it iff is_valid, rank by
    |t_stat|, cap at MAX_MOMENTUM_CANDIDATES_STORED. A ticker with
    insufficient history is silently skipped, not an error. The three
    informational tags (variance-ratio regime, HAC significance, HMM
    volatility regime) are deliberately computed only on the capped,
    ranked shortlist, not the whole passing universe — HMM fitting alone
    costs ~0.07s/ticker, which would add tens of seconds across an
    ~85%-passing 503-ticker universe if run before the cap; computing
    these after ranking doesn't change any candidate's own tag value,
    since each is a pure function of that one ticker's own series."""
    raw_hits: list[tuple[str, object, pd.Series]] = []
    for ticker in prices.columns:
        series = prices[ticker].dropna()
        if len(series) < momentum.DEFAULT_FIT_WINDOW_DAYS:
            continue
        window = pd.DataFrame({"log_price": np.log(series.iloc[-momentum.DEFAULT_FIT_WINDOW_DAYS :])})
        fit = fit_momentum_window(window)
        if not fit.is_valid or fit.z_score is None:
            continue
        raw_hits.append((ticker, fit, series))

    raw_hits.sort(key=lambda item: abs(item[1].z_score), reverse=True)
    top_hits = raw_hits[:MAX_MOMENTUM_CANDIDATES_STORED]

    candidates: list[MomentumCandidate] = []
    for ticker, fit, series in top_hits:
        classification = regime.classify_regime(series)
        hmm_classification = classify_regime_hmm(series)
        log_window = np.log(series.iloc[-momentum.DEFAULT_FIT_WINDOW_DAYS :].to_numpy())
        candidates.append(
            MomentumCandidate(
                ticker=ticker,
                t_stat=fit.z_score,
                direction="long" if fit.z_score > 0 else "short",
                fit_quality=fit.fit_quality,
                regime=classification.regime if classification else None,
                hac_significant=_hac_significant(log_window),
                regime_hmm=hmm_classification.label if hmm_classification else None,
            )
        )
    return candidates


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


def _cointegration_filter(prices: pd.DataFrame, candidates: list[PairsCandidate]) -> list[PairsCandidate]:
    """Second-stage filter, applied after the correlation prefilter: an
    Engle-Granger test on COINTEGRATION_WINDOW_TRADING_DAYS of log price
    for each candidate pair, keeping only p<=COINTEGRATION_P_VALUE_THRESHOLD.
    A pair without enough overlapping history for the full window is
    silently dropped (same "insufficient data -> skip, not an error"
    convention as screen_momentum_universe's history-floor skip), not
    treated as a failure. Preserves the input's sort order (already
    correlation-ranked by _pairs_from_correlation_matrix) — this function
    only removes candidates, never reorders them."""
    filtered: list[PairsCandidate] = []
    for candidate in candidates:
        if candidate.ticker_a not in prices.columns or candidate.ticker_b not in prices.columns:
            continue
        pair_window = (
            prices[[candidate.ticker_a, candidate.ticker_b]].dropna().tail(COINTEGRATION_WINDOW_TRADING_DAYS)
        )
        if len(pair_window) < COINTEGRATION_WINDOW_TRADING_DAYS:
            continue
        log_a = np.log(pair_window[candidate.ticker_a])
        log_b = np.log(pair_window[candidate.ticker_b])
        try:
            _stat, p_value, _crit = coint(log_a, log_b)
        except (ValueError, np.linalg.LinAlgError):
            continue
        if p_value <= COINTEGRATION_P_VALUE_THRESHOLD:
            filtered.append(candidate)
    return filtered


def screen_pairs_universe(prices: pd.DataFrame) -> list[PairsCandidate]:
    """Restrict to a clean common trailing window (drop any ticker with a
    gap in it, rather than silently down-weighting sparser tickers), reuse
    compute_daily_returns/correlation_matrix verbatim (simple returns,
    matching risk/engine.py's existing convention) for the correlation
    prefilter, then narrow with a real cointegration test. No AR(1) check
    at any stage — see MIN_SCREENING_CORRELATION's docstring. The
    correlation stage is deliberately uncapped at MAX_PAIRS_CANDIDATES_STORED
    (capped instead at the much larger MAX_CORRELATION_CANDIDATES_BEFORE_
    COINTEGRATION) — capping early would starve the cointegration filter,
    see that constant's docstring."""
    window = prices.tail(ou_pairs.DEFAULT_FIT_WINDOW_DAYS + 1).dropna(axis=1, how="any")
    if window.shape[1] < 2:
        return []
    returns = compute_daily_returns(window)
    corr = correlation_matrix(returns)
    correlation_candidates = _pairs_from_correlation_matrix(
        corr, MIN_SCREENING_CORRELATION, MAX_CORRELATION_CANDIDATES_BEFORE_COINTEGRATION
    )
    cointegrated_candidates = _cointegration_filter(prices, correlation_candidates)
    return cointegrated_candidates[:MAX_PAIRS_CANDIDATES_STORED]
