import numpy as np
import pandas as pd

from app.services.research_lab.screening import (
    COINTEGRATION_WINDOW_TRADING_DAYS,
    MAX_MOMENTUM_CANDIDATES_STORED,
    MIN_SCREENING_CORRELATION,
    PairsCandidate,
    _cointegration_filter,
    _pairs_from_correlation_matrix,
    screen_momentum_universe,
    screen_pairs_universe,
)


def _trend_price_series(n: int, drift: float, noise_std: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    log_price = np.cumsum(rng.normal(drift, noise_std, n))
    return 100 * np.exp(log_price)


def _flat_price_series(n: int, seed: int) -> np.ndarray:
    # Same construction as test_momentum.py's own verified-flat fixtures —
    # i.i.d. noise around a constant mean, no cumulative drift.
    rng = np.random.default_rng(seed)
    log_price = 4.6 + rng.normal(0, 0.01, n)
    return np.exp(log_price)


def _ar1_return_price_series(n: int, phi: float, eps_std: float, seed: int) -> np.ndarray:
    # AR(1)-on-returns — see test_regime.py for why this, not _trend_price_series,
    # is the fixture that actually trips the variance-ratio regime classifier.
    rng = np.random.default_rng(seed)
    eps = rng.normal(0, eps_std, n)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = phi * r[t - 1] + eps[t]
    log_price = np.cumsum(r)
    return 100 * np.exp(log_price)


def _cointegrated_pair_price_series(
    n: int, seed: int, phi: float = 0.5, common_std: float = 0.01, spread_std: float = 0.005
) -> tuple[np.ndarray, np.ndarray]:
    # Genuinely cointegrated: both legs share the exact same random-walk
    # component (log_a); the spread between them is a stationary AR(1)
    # process (|phi|<1), not a second independent random walk. Empirically
    # verified 2026-08-25 at n=550 across seeds 0-19: correlation ~0.84-0.88,
    # Engle-Granger p~0.0 every time — reliably passes both stages.
    rng = np.random.default_rng(seed)
    common = np.cumsum(rng.normal(0, common_std, n))
    spread = np.zeros(n)
    eps = rng.normal(0, spread_std, n)
    for t in range(1, n):
        spread[t] = phi * spread[t - 1] + eps[t]
    log_a = common
    log_b = common + spread
    return 100 * np.exp(log_a), 100 * np.exp(log_b)


def _spurious_correlated_pair_price_series(
    n: int, seed: int, common_std: float = 0.01, idio_std: float = 0.003
) -> tuple[np.ndarray, np.ndarray]:
    # Merely correlated, NOT cointegrated: both legs share a common
    # random-walk component, but each also carries its OWN independent
    # random-walk idiosyncratic component — so their spread (idio_a -
    # idio_b) is itself a non-stationary random walk, not mean-reverting.
    # This is exactly the shape of pair the existing AR(1) fit spuriously
    # passes 99.3% of the time (see MIN_SCREENING_CORRELATION's docstring)
    # and that the cointegration filter must correctly reject. Empirically
    # verified 2026-08-25 at n=550 across seeds 0-19: correlation ~0.90-0.93
    # (clears the 0.6 prefilter) but Engle-Granger p ranges ~0.06-0.99
    # (never clears p<=0.05) every time.
    rng = np.random.default_rng(seed)
    common = np.cumsum(rng.normal(0, common_std, n))
    idio_a = np.cumsum(rng.normal(0, idio_std, n))
    idio_b = np.cumsum(rng.normal(0, idio_std, n))
    log_a = common + idio_a
    log_b = common + idio_b
    return 100 * np.exp(log_a), 100 * np.exp(log_b)


# --- screen_momentum_universe ----------------------------------------------


def test_screen_momentum_universe_ranks_strongest_trend_first():
    n = 90
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    prices = pd.DataFrame(
        {
            "TRND": _trend_price_series(n, drift=0.003, noise_std=0.0005, seed=42),
            # seeds 2/1/3 verified (test_momentum.py + this session) to reliably land p > 0.05.
            "FLATA": _flat_price_series(n, seed=2),
            "FLATB": _flat_price_series(n, seed=1),
            "FLATC": _flat_price_series(n, seed=3),
        },
        index=dates,
    )

    candidates = screen_momentum_universe(prices)
    tickers = [c.ticker for c in candidates]

    assert tickers[0] == "TRND"
    assert candidates[0].direction == "long"
    assert "FLATA" not in tickers
    assert "FLATB" not in tickers
    assert "FLATC" not in tickers


def test_screen_momentum_universe_downtrend_ranked_with_short_direction():
    n = 90
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    prices = pd.DataFrame(
        {
            "DOWN": _trend_price_series(n, drift=-0.003, noise_std=0.0005, seed=43),
            "FLATA": _flat_price_series(n, seed=2),
        },
        index=dates,
    )

    candidates = screen_momentum_universe(prices)
    assert candidates[0].ticker == "DOWN"
    assert candidates[0].direction == "short"
    assert candidates[0].t_stat < 0


def test_screen_momentum_universe_caps_at_max_stored():
    n = 90
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    columns = {
        f"T{i}": _trend_price_series(n, drift=0.001 * (i + 1), noise_std=0.0005, seed=1000 + i)
        for i in range(MAX_MOMENTUM_CANDIDATES_STORED + 5)
    }
    prices = pd.DataFrame(columns, index=dates)

    candidates = screen_momentum_universe(prices)
    assert len(candidates) == MAX_MOMENTUM_CANDIDATES_STORED
    # Strongest drift (largest i) should be ranked first.
    t_stats = [abs(c.t_stat) for c in candidates]
    assert t_stats == sorted(t_stats, reverse=True)


def test_screen_momentum_universe_skips_insufficient_history_ticker():
    n = 90
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    short = np.full(n, np.nan)
    short[-50:] = _trend_price_series(50, drift=0.003, noise_std=0.0005, seed=42)
    prices = pd.DataFrame(
        {
            "TRND": _trend_price_series(n, drift=0.003, noise_std=0.0005, seed=42),
            "SHORT": short,  # only 50 real rows — below momentum.DEFAULT_FIT_WINDOW_DAYS (90)
        },
        index=dates,
    )

    candidates = screen_momentum_universe(prices)
    tickers = [c.ticker for c in candidates]
    assert "TRND" in tickers
    assert "SHORT" not in tickers


def test_screen_momentum_universe_attaches_regime_tag():
    # n=91, not 90 — the classifier needs one more row than momentum's own
    # OLS fit window (see regime.py's VR_WINDOW_DAYS+1 floor).
    n = 91
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    prices = pd.DataFrame(
        {"TRND": _ar1_return_price_series(n, phi=0.4, eps_std=0.01, seed=0)},
        index=dates,
    )

    candidates = screen_momentum_universe(prices)
    assert len(candidates) == 1
    assert candidates[0].ticker == "TRND"
    assert candidates[0].regime == "trending"


# --- _pairs_from_correlation_matrix (pure, RNG-free) ------------------------


def test_pairs_from_correlation_matrix_respects_threshold():
    corr = pd.DataFrame(
        [
            [1.0, 0.6, 0.59, -0.7],
            [0.6, 1.0, 0.1, 0.0],
            [0.59, 0.1, 1.0, 0.2],
            [-0.7, 0.0, 0.2, 1.0],
        ],
        columns=["A", "B", "C", "D"],
        index=["A", "B", "C", "D"],
    )
    candidates = _pairs_from_correlation_matrix(corr, min_corr=MIN_SCREENING_CORRELATION, max_candidates=40)
    pairs = {(c.ticker_a, c.ticker_b) for c in candidates}

    assert ("A", "B") in pairs  # exactly at threshold (0.6 >= 0.6)
    assert ("A", "C") not in pairs  # just below (0.59 < 0.6)
    assert ("A", "D") in pairs  # negative correlation, |−0.7| >= 0.6 — legitimate candidate
    assert len(pairs) == 2


def test_pairs_from_correlation_matrix_caps_and_sorts():
    tickers = [f"T{i}" for i in range(6)]
    corr = pd.DataFrame(np.eye(6), columns=tickers, index=tickers)
    # Fill every off-diagonal pair with a distinct, above-threshold value.
    value = 0.61
    for i in range(6):
        for j in range(i + 1, 6):
            corr.iloc[i, j] = value
            corr.iloc[j, i] = value
            value += 0.01  # 15 pairs total, all above MIN_SCREENING_CORRELATION

    candidates = _pairs_from_correlation_matrix(corr, min_corr=0.6, max_candidates=5)
    assert len(candidates) == 5
    scores = [abs(c.correlation) for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_pairs_from_correlation_matrix_ignores_nan():
    corr = pd.DataFrame(
        [[1.0, np.nan], [np.nan, 1.0]], columns=["A", "B"], index=["A", "B"]
    )
    assert _pairs_from_correlation_matrix(corr, min_corr=0.6, max_candidates=40) == []


# --- _cointegration_filter (integration with statsmodels) -------------------


def test_cointegration_filter_keeps_genuinely_cointegrated_pair():
    n = COINTEGRATION_WINDOW_TRADING_DAYS
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    price_a, price_b = _cointegrated_pair_price_series(n, seed=0)
    prices = pd.DataFrame({"COA": price_a, "COB": price_b}, index=dates)
    candidates = [PairsCandidate(ticker_a="COA", ticker_b="COB", correlation=0.85)]

    filtered = _cointegration_filter(prices, candidates)
    assert len(filtered) == 1
    assert filtered[0].ticker_a == "COA"


def test_cointegration_filter_drops_spurious_correlated_pair():
    n = COINTEGRATION_WINDOW_TRADING_DAYS
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    price_a, price_b = _spurious_correlated_pair_price_series(n, seed=0)
    prices = pd.DataFrame({"SPA": price_a, "SPB": price_b}, index=dates)
    candidates = [PairsCandidate(ticker_a="SPA", ticker_b="SPB", correlation=0.92)]

    assert _cointegration_filter(prices, candidates) == []


def test_cointegration_filter_drops_pair_with_insufficient_history():
    n = COINTEGRATION_WINDOW_TRADING_DAYS - 1  # one short of the required window
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    price_a, price_b = _cointegrated_pair_price_series(n, seed=0)
    prices = pd.DataFrame({"COA": price_a, "COB": price_b}, index=dates)
    candidates = [PairsCandidate(ticker_a="COA", ticker_b="COB", correlation=0.85)]

    assert _cointegration_filter(prices, candidates) == []


def test_cointegration_filter_preserves_input_order():
    n = COINTEGRATION_WINDOW_TRADING_DAYS
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    a1, b1 = _cointegrated_pair_price_series(n, seed=1)
    a2, b2 = _cointegrated_pair_price_series(n, seed=5)
    prices = pd.DataFrame({"C1A": a1, "C1B": b1, "C2A": a2, "C2B": b2}, index=dates)
    # Deliberately listed lower-scored-first — the filter must not resort.
    candidates = [
        PairsCandidate(ticker_a="C1A", ticker_b="C1B", correlation=0.80),
        PairsCandidate(ticker_a="C2A", ticker_b="C2B", correlation=0.90),
    ]

    filtered = _cointegration_filter(prices, candidates)
    assert [c.ticker_a for c in filtered] == ["C1A", "C2A"]


# --- screen_pairs_universe (integration) ------------------------------------


def test_screen_pairs_universe_finds_genuinely_cointegrated_pair():
    n = COINTEGRATION_WINDOW_TRADING_DAYS + 50
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    price_a, price_b = _cointegrated_pair_price_series(n, seed=0)

    independents = {}
    for i, seed in enumerate([200, 201, 202]):
        r = np.random.default_rng(seed)
        independents[f"IND{i}"] = 100 * np.exp(np.cumsum(r.normal(0, 0.01, n)))

    prices = pd.DataFrame({"CORRA": price_a, "CORRB": price_b, **independents}, index=dates)

    candidates = screen_pairs_universe(prices)
    pairs = {frozenset((c.ticker_a, c.ticker_b)) for c in candidates}

    assert frozenset(("CORRA", "CORRB")) in pairs
    for i in range(3):
        for j in range(3):
            if i < j:
                assert frozenset((f"IND{i}", f"IND{j}")) not in pairs


def test_screen_pairs_universe_rejects_merely_correlated_non_cointegrated_pair():
    # The load-bearing regression: a pair that clears the correlation
    # prefilter but is NOT cointegrated (shared trend, independent
    # random-walk idiosyncratic legs) must be filtered out by the second
    # stage — this is exactly the failure mode the AR(1) fit spuriously
    # passed and cointegration screening exists to fix.
    n = COINTEGRATION_WINDOW_TRADING_DAYS + 50
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    price_a, price_b = _spurious_correlated_pair_price_series(n, seed=0)
    prices = pd.DataFrame({"SPA": price_a, "SPB": price_b}, index=dates)

    candidates = screen_pairs_universe(prices)
    pairs = {frozenset((c.ticker_a, c.ticker_b)) for c in candidates}
    assert frozenset(("SPA", "SPB")) not in pairs


def test_screen_pairs_universe_returns_empty_below_two_tickers():
    n = 253
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    prices = pd.DataFrame({"ONLY": 100 * np.exp(np.cumsum(np.zeros(n)))}, index=dates)
    assert screen_pairs_universe(prices) == []


def test_screen_pairs_universe_never_sets_regime():
    # PairsCandidate deliberately has no regime attribute at all — a
    # per-ticker variance-ratio tag would test the wrong statistical
    # object for a pairs candidate (one leg's own serial correlation, not
    # whether the pair's spread mean-reverts). Structural check, not a
    # behavioral one: this simply must not raise.
    candidates = screen_pairs_universe(pd.DataFrame())
    assert candidates == []
    assert not hasattr(PairsCandidate(ticker_a="A", ticker_b="B", correlation=0.9), "regime")
