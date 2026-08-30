"""Tests for the jump-detection + post-jump drift/reversal family.

The load-bearing ones are the GROUND-TRUTH detector tests: a synthetic return
series with a KNOWN injected jump on a KNOWN day, buried in realistic
continuous noise, must be flagged on that day and only that day — while the
SAME construction with no injected discontinuity, and a separately elevated
but purely continuous volatility regime, must NOT be flagged. Without both
halves the detector could be a plain |return| threshold wearing a citation.
"""

import json
from dataclasses import asdict
from datetime import date
from math import pi, sqrt

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    fixed_universe_membership,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_jump_drift import (
    EVENT_STUDY_HORIZONS_DAYS,
    EVENT_STUDY_VERDICT_ALPHA,
    JUMP_DIRECTIONS,
    JUMP_DRIFT_SPECS,
    JUMP_HOLDING_HORIZONS_DAYS,
    JUMP_RANK_FRACTION,
    JUMP_SPEC_CEILING,
    JUMP_WINDOWS_DAYS,
    JUMP_Z_CRITICAL,
    MU1_INV_SQ,
    MU43_INV_CUBE,
    NU_BB_MINUS_NU_QQ,
    EventStudyCell,
    PostJumpEventStudy,
    _abs_normal_moment,
    _signal_rows_needed,
    compute_jump_diagnostics,
    detect_jump_days,
    forward_cumulative_log_return,
    jump_z_statistic,
    log_returns,
    run_jump_drift_screening,
    run_post_jump_event_study,
    signal_post_jump,
)

Z001 = JUMP_Z_CRITICAL["001"]
Z010 = JUMP_Z_CRITICAL["010"]


# --- synthetic fixtures ---------------------------------------------------


def _close_from_returns(returns: np.ndarray, start: str = "2015-01-05") -> pd.Series:
    """A price path whose LOG returns are exactly `returns` (the first close is
    the base, so len(close) == len(returns) + 1)."""
    levels = 100.0 * np.exp(np.concatenate([[0.0], np.cumsum(returns)]))
    return pd.Series(levels, index=pd.bdate_range(start, periods=len(levels)))


def _one_ticker_frame(returns: np.ndarray, ticker: str = "X") -> pd.DataFrame:
    series = _close_from_returns(returns)
    return pd.DataFrame({ticker: series.to_numpy()}, index=series.index)


def _path_with_optional_jump(
    *,
    seed: int,
    n: int = 120,
    sigma: float = 0.015,
    jump_day: int | None = None,
    jump_sigmas: float = 8.0,
) -> np.ndarray:
    """Continuous Gaussian noise of scale `sigma`, optionally with a single
    additive discontinuity of `jump_sigmas` * sigma on row `jump_day`.

    The jump is ADDED to that day's ordinary continuous return rather than
    replacing it, so the two worlds this returns (jump_day=None vs a row index)
    are identical in every other observation — which is what makes the pair a
    clean controlled comparison rather than two unrelated draws."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, sigma, n)
    if jump_day is not None:
        returns[jump_day] += jump_sigmas * sigma
    return returns


# --- the paper constants --------------------------------------------------


def test_moment_constants_match_the_values_the_sources_print():
    """[HT05] p.460 lists mu_1 = sqrt(2/pi), mu_2 = 1, mu_3 = 2 sqrt(2/pi),
    mu_4 = 3; [BNS06] Eq. (5) states mu_1 = sqrt(2)/sqrt(pi). Deriving them
    from E|Z|^a rather than typing decimals is only safe if the derivation
    reproduces the printed values, which is what this pins."""
    assert _abs_normal_moment(1.0) == pytest.approx(sqrt(2.0 / pi), rel=1e-12)
    assert _abs_normal_moment(2.0) == pytest.approx(1.0, rel=1e-12)
    assert _abs_normal_moment(3.0) == pytest.approx(2.0 * sqrt(2.0 / pi), rel=1e-12)
    assert _abs_normal_moment(4.0) == pytest.approx(3.0, rel=1e-12)


def test_bipower_and_quarticity_scaling_constants():
    """[HT05] p.459 writes the bipower scaling constant out both ways
    ("mu_1^{-2} ... = pi/2"), and p.461 Eq. (3) uses mu_{4/3}^{-3}."""
    assert MU1_INV_SQ == pytest.approx(pi / 2.0, rel=1e-12)
    assert MU43_INV_CUBE == pytest.approx(_abs_normal_moment(4.0 / 3.0) ** -3, rel=1e-12)


def test_theta_constant_agrees_across_both_sources():
    """[HT05] p.460: nu_qq = 2 and nu_bb = (pi/2)^2 + pi - 3, so the difference
    the test statistic scales by is (pi/2)^2 + pi - 5. [BNS06] Eq. (6) prints
    that same quantity directly as theta ~= 0.6090."""
    nu_qq = 2.0
    nu_bb = (pi / 2.0) ** 2 + pi - 3.0
    assert NU_BB_MINUS_NU_QQ == pytest.approx(nu_bb - nu_qq, rel=1e-12)
    assert NU_BB_MINUS_NU_QQ == pytest.approx(0.6090, abs=5e-5)


# --- the statistic's null distribution ------------------------------------


def test_z_statistic_is_approximately_standard_normal_under_a_continuous_null():
    """[HT05] Eq. (9): z_TP,rm -> N(0,1) as M -> infinity under no jumps. The
    whole daily adaptation rests on that limit being usable at M = 21 and
    M = 63, so it is verified here on a pure continuous path rather than
    assumed. Loose tolerances on purpose: this pins "the limit is in force at
    these window sizes", not a distributional identity."""
    rng = np.random.default_rng(20260830)
    returns = pd.DataFrame(
        rng.normal(0.0, 0.015, (3000, 30)), index=pd.bdate_range("2005-01-03", periods=3000)
    )
    for window in JUMP_WINDOWS_DAYS:
        z = jump_z_statistic(returns, window).to_numpy()
        z = z[np.isfinite(z)]
        assert z.size > 50_000
        assert abs(z.mean()) < 0.10
        assert z.std() == pytest.approx(1.0, abs=0.10)


def _stochastic_vol_panel(n: int, k: int, seed: int, vol_of_vol: float, rho: float = 0.98):
    """A CONTINUOUS-PATH null with persistent stochastic volatility and NO jumps
    anywhere — an AR(1) log-variance driving Gaussian innovations."""
    rng = np.random.default_rng(seed)
    log_var = np.zeros((n, k))
    for i in range(1, n):
        log_var[i] = rho * log_var[i - 1] + rng.normal(
            0.0, vol_of_vol * np.sqrt(1 - rho**2), k
        )
    return rng.normal(0.0, 1.0, (n, k)) * (0.015 * np.exp(log_var - 0.5 * log_var.var()))


def _rejection_rate(returns: np.ndarray, window: int, z_crit: float) -> float:
    z = jump_z_statistic(pd.DataFrame(returns), window).to_numpy()
    z = z[np.isfinite(z)]
    return float(np.mean(z > z_crit))


def test_size_distortion_under_a_stochastic_volatility_null_is_measured_not_asserted():
    """PINS THE "5-9x" NUMBER THE MODULE DOCSTRING CITES (verification pass,
    2026-08-30). That figure previously lived only in prose — no test, no
    persisted artifact, so it could not be checked. It is reproduced here: on a
    purely continuous stochastic-volatility null with NO jumps at all, the
    window-level test over-rejects a few-fold, and materially worse at w=63 than
    at w=21. Both are far below the 27.6x / 86.3x the real data produced, which
    is the honest direction: the synthetic check UNDERSTATED the real
    distortion, and the module says so."""
    returns = _stochastic_vol_panel(2000, 120, seed=7, vol_of_vol=0.60)
    rate21 = _rejection_rate(returns, 21, Z001) / 0.001
    rate63 = _rejection_rate(returns, 63, Z001) / 0.001
    assert 2.0 < rate21 < 6.0, f"w=21 stochastic-vol size was {rate21:.1f}x nominal"
    assert 5.0 < rate63 < 10.0, f"w=63 stochastic-vol size was {rate63:.1f}x nominal"
    assert rate63 > rate21, "the longer window must be the worse-behaved one"


def test_a_kurtosis_matched_null_over_rejects_more_than_the_real_data_does():
    """THE OTHER BRACKET ON THE MEASURED SIZE (verification pass, 2026-08-30).
    Paired with the stochastic-volatility test above, which shows a purely
    CONTINUOUS null over-rejecting far too little (3.7x / 7.1x) to account for
    the real data's 27.6x / 86.3x. This is the opposite bracket: an i.i.d.
    Student-t(4) panel, whose realized per-column excess kurtosis (median ~6.5)
    is MILDER than these 625 names' own (median ~12.2), over-rejects by MORE
    than the real data, preserving the same w=63 >> w=21 ordering.

    WHAT THIS DOES NOT PROVE, stated because the first draft of this test
    claimed it did: it does NOT show the real data is jump-free. An i.i.d.
    Student-t sequence is not the discretization of a continuous semimartingale
    — it is closer to a pure-jump process, so rejecting continuity for it may be
    correct rather than spurious. What the pair of tests DOES establish is that
    the observed rejection rate is a function of the return distribution's
    KURTOSIS and is not reachable by continuous stochastic volatility alone,
    which is why the z-thresholds are declared tuning parameters."""
    rng = np.random.default_rng(8)
    df = 4
    returns = rng.standard_t(df, (2000, 120)) * 0.015 / np.sqrt(df / (df - 2))
    rate21 = _rejection_rate(returns, 21, Z001) / 0.001
    rate63 = _rejection_rate(returns, 63, Z001) / 0.001
    # The real-data figures this brackets are 27.6x (w=21) and 86.3x (w=63).
    assert rate21 > 27.6, f"jump-free fat tails gave only {rate21:.1f}x at w=21"
    assert rate63 > 86.3, f"jump-free fat tails gave only {rate63:.1f}x at w=63"
    assert rate63 > rate21


def test_realized_size_exceeds_nominal_alpha_as_the_module_docstring_predicts():
    """The docstring's daily-adaptation item (b) claims the nominal alpha is not
    a calibrated false-positive rate and that the distortion is toward
    OVER-rejection. That is a falsifiable claim about this code, so it is
    tested: on a purely continuous path the realized rate must sit above
    nominal, and (since the limit does hold approximately) within an order of
    magnitude of it."""
    rng = np.random.default_rng(11)
    returns = pd.DataFrame(
        rng.normal(0.0, 0.015, (3000, 30)), index=pd.bdate_range("2005-01-03", periods=3000)
    )
    z = jump_z_statistic(returns, 21).to_numpy()
    z = z[np.isfinite(z)]
    for z_crit, nominal in ((Z010, 0.010), (Z001, 0.001)):
        realized = float(np.mean(z > z_crit))
        assert nominal < realized < 10.0 * nominal


# --- GROUND TRUTH: the detector fires on a known injected jump ------------


def test_injected_jump_is_flagged_on_the_day_it_was_injected():
    """The core claim. A single 8-sigma discontinuity buried in 120 days of
    realistic continuous noise must be flagged, and flagged on ITS OWN day —
    not a neighbour, and not the whole window it sits in."""
    jump_row = 100
    returns = _path_with_optional_jump(seed=3, jump_day=jump_row, jump_sigmas=8.0)
    close = _one_ticker_frame(returns)
    # close has one extra leading row, so return row i is close row i + 1.
    jump_date = close.index[jump_row + 1]

    flags = detect_jump_days(close, window=21, z_crit=Z001)["X"]
    flagged_dates = list(flags.dropna().index)
    assert flagged_dates == [jump_date]
    assert flags.loc[jump_date] == pytest.approx(returns[jump_row], rel=1e-12)
    assert flags.loc[jump_date] > 0


def test_a_down_jump_is_flagged_with_a_negative_signed_size():
    jump_row = 90
    returns = _path_with_optional_jump(seed=5, jump_day=jump_row, jump_sigmas=-9.0)
    close = _one_ticker_frame(returns)
    flags = detect_jump_days(close, window=21, z_crit=Z001)["X"]
    flagged = flags.dropna()
    assert len(flagged) == 1
    assert flagged.iloc[0] < 0
    assert flagged.index[0] == close.index[jump_row + 1]


def test_detector_separates_jump_from_no_jump_across_many_seeds():
    """The seed-verification discipline applied to the thing that matters: over
    40 independent worlds, the SAME noise path with and without a single
    injected discontinuity. The jump world must fire on the injected day the
    large majority of the time; the identical no-jump world must almost never
    fire anywhere. One seed proving this would be an anecdote."""
    jump_row = 100
    hits = 0
    false_positives = 0
    n_seeds = 40
    for seed in range(n_seeds):
        with_jump = _path_with_optional_jump(seed=seed, jump_day=jump_row, jump_sigmas=8.0)
        without = _path_with_optional_jump(seed=seed, jump_day=None)
        # The two worlds differ in exactly one observation.
        assert np.count_nonzero(with_jump != without) == 1

        close_j = _one_ticker_frame(with_jump)
        close_n = _one_ticker_frame(without)
        jump_date = close_j.index[jump_row + 1]

        if np.isfinite(detect_jump_days(close_j, 21, Z001)["X"].get(jump_date, np.nan)):
            hits += 1
        false_positives += int(detect_jump_days(close_n, 21, Z001)["X"].notna().sum())

    assert hits >= 0.65 * n_seeds, f"only {hits}/{n_seeds} injected jumps detected"
    assert false_positives <= 0.10 * n_seeds, (
        f"{false_positives} false flags across {n_seeds} jump-free paths — the detector is "
        "firing on ordinary continuous moves"
    )


# --- GROUND TRUTH: the detector stays silent on ordinary volatility -------


def test_ordinary_large_move_in_a_continuous_path_is_not_flagged():
    """The negative control that makes the positive one mean something. The
    same path, same day, same "this is the biggest move in the window" —
    but the move is drawn from the path's own continuous distribution instead
    of being a discontinuity. A detector that flags this is a |return|
    threshold, not a jump test."""
    jump_row = 100
    returns = _path_with_optional_jump(seed=3, jump_day=None)
    # Force the target day to be the window's largest move WITHOUT making it a
    # discontinuity: 2.2 sigma is a perfectly ordinary draw for a Gaussian.
    returns[jump_row] = 2.2 * 0.015
    close = _one_ticker_frame(returns)
    jump_date = close.index[jump_row + 1]

    window_returns = returns[jump_row - 20 : jump_row + 1]
    assert abs(returns[jump_row]) == pytest.approx(np.abs(window_returns).max())

    flags = detect_jump_days(close, window=21, z_crit=Z001)["X"]
    assert np.isnan(flags.loc[jump_date])


def test_a_high_volatility_regime_without_discontinuities_is_not_flagged():
    """Volatility four times higher, entirely continuous. A jump test must be
    scale-free: multiplying every return by a constant cannot create a jump,
    and the statistic is built from ratios precisely so that it does not."""
    quiet = _path_with_optional_jump(seed=21, n=150, sigma=0.01, jump_day=None)
    loud = quiet * 4.0
    quiet_flags = detect_jump_days(_one_ticker_frame(quiet), 21, Z001)["X"]
    loud_flags = detect_jump_days(_one_ticker_frame(loud), 21, Z001)["X"]
    assert int(quiet_flags.notna().sum()) == 0
    assert int(loud_flags.notna().sum()) == 0

    # The statistic itself is exactly scale-invariant, which is the reason.
    z_quiet = jump_z_statistic(log_returns(_one_ticker_frame(quiet)), 21)
    z_loud = jump_z_statistic(log_returns(_one_ticker_frame(loud)), 21)
    np.testing.assert_allclose(
        z_quiet.to_numpy(), z_loud.to_numpy(), rtol=1e-9, equal_nan=True
    )


def test_a_lower_threshold_flags_at_least_as_much_as_a_higher_one():
    """Monotonicity in z_crit — a cheap structural guard that the threshold is
    wired into the comparison the way the docstring says."""
    returns = _path_with_optional_jump(seed=8, n=400, jump_day=None)
    close = _one_ticker_frame(returns)
    loose = int(detect_jump_days(close, 21, Z010).notna().to_numpy().sum())
    strict = int(detect_jump_days(close, 21, Z001).notna().to_numpy().sum())
    assert loose >= strict


def test_window_max_condition_is_what_localizes_the_day():
    """Attribution rule (ii). A jump on row J makes the WINDOW statistic
    significant for up to `window` subsequent rows, but only row J is the
    window max at the moment its own window ends — so only row J is flagged."""
    jump_row = 60
    returns = _path_with_optional_jump(seed=4, n=120, jump_day=jump_row, jump_sigmas=10.0)
    close = _one_ticker_frame(returns)
    z = jump_z_statistic(log_returns(close), 21)["X"]
    jump_date = close.index[jump_row + 1]

    # The window verdict stays significant well past the jump day...
    trailing = z.loc[jump_date : close.index[jump_row + 10]]
    assert (trailing > Z001).sum() > 1
    # ...but the day-level attribution picks out exactly one day.
    assert list(detect_jump_days(close, 21, Z001)["X"].dropna().index) == [jump_date]


# --- statistic guards -----------------------------------------------------


def test_jump_z_statistic_rejects_a_window_too_short_for_quarticity():
    returns = pd.DataFrame({"X": np.zeros(50)}, index=pd.bdate_range("2015-01-05", periods=50))
    with pytest.raises(ValueError, match="window >= 4"):
        jump_z_statistic(returns, 3)


def test_a_flat_price_path_yields_no_statistic_rather_than_a_spurious_one():
    """RV = BV = 0 is 0/0, not evidence of anything. NaN, never a 0 that would
    read as "tested and found continuous"."""
    close = pd.DataFrame(
        {"X": np.full(60, 100.0)}, index=pd.bdate_range("2015-01-05", periods=60)
    )
    z = jump_z_statistic(log_returns(close), 21)
    assert z["X"].notna().sum() == 0
    assert detect_jump_days(close, 21, Z001)["X"].notna().sum() == 0


def test_non_positive_prices_become_nan_instead_of_infinities():
    values = np.full(60, 100.0)
    values[30] = 0.0
    close = pd.DataFrame({"X": values}, index=pd.bdate_range("2015-01-05", periods=60))
    returns = log_returns(close)["X"]
    assert not np.isinf(returns.to_numpy()).any()
    assert np.isnan(returns.iloc[30])


# --- the signal function --------------------------------------------------


def _signal_view(returns: np.ndarray, tickers: dict[str, np.ndarray]) -> CrossSectionalData:
    del returns
    frames = {t: _close_from_returns(r).to_numpy() for t, r in tickers.items()}
    index = _close_from_returns(next(iter(tickers.values()))).index
    return CrossSectionalData(close=pd.DataFrame(frames, index=index))


def test_signal_ranks_up_jumpers_above_down_jumpers_under_continuation():
    """H_CONT (+1): the long leg must be the up-jumpers. Non-jumpers must be
    NaN — the SignalFn contract's "no valid signal today" — so they are dropped
    from the ranking rather than crowding its middle."""
    n = 120
    jump_row = n - 1  # jumps on the formation date itself
    data = _signal_view(
        np.empty(0),
        {
            "UP": _path_with_optional_jump(seed=1, n=n, jump_day=jump_row, jump_sigmas=9.0),
            "DOWN": _path_with_optional_jump(seed=2, n=n, jump_day=jump_row, jump_sigmas=-9.0),
            "QUIET": _path_with_optional_jump(seed=3, n=n, jump_day=None),
        },
    )
    signal = signal_post_jump(
        data, window=21, z_crit=Z001, event_window_days=5, direction=JUMP_DIRECTIONS["cont"]
    )
    assert signal["UP"] > 0
    assert signal["DOWN"] < 0
    assert signal["UP"] > signal["DOWN"]
    assert np.isnan(signal["QUIET"])


def test_reversal_direction_is_the_exact_negation_of_continuation():
    """H_REV (-1) is the same events with the sign flipped, which is why the
    module docstring calls the two near-mirrors and counts both in n_trials
    anyway."""
    n = 120
    data = _signal_view(
        np.empty(0),
        {
            "UP": _path_with_optional_jump(seed=1, n=n, jump_day=n - 1, jump_sigmas=9.0),
            "DOWN": _path_with_optional_jump(seed=2, n=n, jump_day=n - 1, jump_sigmas=-9.0),
        },
    )
    cont = signal_post_jump(data, window=21, z_crit=Z001, event_window_days=5, direction=1)
    rev = signal_post_jump(data, window=21, z_crit=Z001, event_window_days=5, direction=-1)
    pd.testing.assert_series_equal(rev, -cont)


def test_signal_reads_only_the_trailing_event_window():
    """A jump older than event_window_days must not be traded. This is what
    makes "every detected jump is traded exactly once" true rather than
    aspirational."""
    n = 140
    old_jump_row = n - 30
    # 15 sigma, not the 8-9 used elsewhere: this test is about the event WINDOW,
    # not about detector power, so the jump is made large enough that detection
    # is certain (verified across seeds 0-11) and a failure here can only mean
    # the staleness rule is wrong.
    data = _signal_view(
        np.empty(0),
        {"OLD": _path_with_optional_jump(seed=6, n=n, jump_day=old_jump_row, jump_sigmas=15.0)},
    )
    # Detected somewhere in the panel...
    assert detect_jump_days(data.close, 21, Z001)["OLD"].notna().sum() == 1
    # ...but 30 days stale, so a 5-day event window must not see it.
    fresh = signal_post_jump(data, window=21, z_crit=Z001, event_window_days=5, direction=1)
    assert np.isnan(fresh["OLD"])
    # A 40-day window reaches back far enough and does.
    stale = signal_post_jump(data, window=21, z_crit=Z001, event_window_days=40, direction=1)
    assert np.isfinite(stale["OLD"])


def test_signal_returns_all_nan_when_history_is_too_short_rather_than_raising():
    """A data floor is a research outcome ("no ticker qualified today"), not an
    error — every other family in this project treats it the same way."""
    short = _signal_view(
        np.empty(0), {"A": _path_with_optional_jump(seed=1, n=10, jump_day=None)}
    )
    signal = signal_post_jump(short, window=63, z_crit=Z001, event_window_days=20, direction=1)
    assert signal.index.tolist() == ["A"]
    assert signal.isna().all()


def test_future_rows_cannot_change_the_signal():
    """Look-ahead is structural (the harness slices the view), but the day-level
    flags are computed over a rolling window, so this pins that the window
    really does END at the row it labels: poisoning every future row must leave
    the formation-date signal bit-identical."""
    n = 200
    cutoff = 150
    paths = {
        "A": _path_with_optional_jump(seed=1, n=n, jump_day=145, jump_sigmas=9.0),
        "B": _path_with_optional_jump(seed=2, n=n, jump_day=148, jump_sigmas=-9.0),
        "C": _path_with_optional_jump(seed=3, n=n, jump_day=None),
    }
    full = _signal_view(np.empty(0), paths)
    before = signal_post_jump(
        CrossSectionalData(close=full.close.iloc[:cutoff]),
        window=21,
        z_crit=Z001,
        event_window_days=10,
        direction=1,
    )

    poisoned = full.close.copy()
    poisoned.iloc[cutoff:] = poisoned.iloc[cutoff:] * 3.0
    after = signal_post_jump(
        CrossSectionalData(close=poisoned.iloc[:cutoff]),
        window=21,
        z_crit=Z001,
        event_window_days=10,
        direction=1,
    )
    pd.testing.assert_series_equal(before, after)


def test_detect_jump_days_flags_are_never_revised_by_later_data():
    """The same property one level down, on the panel the event study reads."""
    n = 300
    cutoff = 200
    close = _one_ticker_frame(_path_with_optional_jump(seed=9, n=n, jump_day=150, jump_sigmas=9.0))
    truncated = detect_jump_days(close.iloc[:cutoff], 21, Z001)
    full = detect_jump_days(close, 21, Z001).iloc[:cutoff]
    np.testing.assert_allclose(
        truncated.to_numpy(), full.to_numpy(), rtol=1e-12, equal_nan=True
    )


# --- family shape guards --------------------------------------------------


def test_family_is_24_specs_at_the_hard_ceiling():
    assert len(JUMP_DRIFT_SPECS) == JUMP_SPEC_CEILING == 24
    assert JUMP_SPEC_CEILING == (
        len(JUMP_DIRECTIONS)
        * len(JUMP_WINDOWS_DAYS)
        * len(JUMP_Z_CRITICAL)
        * len(JUMP_HOLDING_HORIZONS_DAYS)
    )


def test_family_pattern_ids_are_unique_and_the_grid_is_fully_crossed():
    ids = [s.pattern_id for s in JUMP_DRIFT_SPECS]
    assert len(set(ids)) == len(ids)
    expected = {
        f"jump_{d}_w{w}_a{a}_h{h}"
        for d in JUMP_DIRECTIONS
        for w in JUMP_WINDOWS_DAYS
        for a in JUMP_Z_CRITICAL
        for h in JUMP_HOLDING_HORIZONS_DAYS
    }
    assert set(ids) == expected


def test_every_spec_is_cited_to_the_sources_actually_read():
    for spec in JUMP_DRIFT_SPECS:
        for token in (
            "Barndorff-Nielsen",
            "Shephard",
            "Huang",
            "Tauchen",
            "Savor",
            "Jiang",
            "Journal of Financial Econometrics",
            "Journal of Financial Economics",
        ):
            assert token in spec.citation
        assert spec.family == "jump_drift"


def test_every_spec_declares_the_shape_the_harness_needs():
    for spec in JUMP_DRIFT_SPECS:
        assert spec.portfolio == "long_short"
        assert spec.rank_fraction == JUMP_RANK_FRACTION == 0.40
        assert spec.leg_weighting == "magnitude"
        assert spec.holding_days in JUMP_HOLDING_HORIZONS_DAYS
        # This family reads closes only; it must not claim frames it never uses.
        assert not spec.requires_open
        assert not spec.requires_volume
        assert not spec.requires_market_cap
        assert not spec.requires_fundamental_signal


def test_lookback_covers_the_window_plus_the_whole_event_window():
    """A spec whose declared lookback were shorter than its signal needs would
    silently return all-NaN forever; the harness caps the view at
    lookback_days, so this is the one place the two must agree."""
    for spec in JUMP_DRIFT_SPECS:
        window = int(spec.pattern_id.split("_w")[1].split("_")[0])
        assert spec.lookback_days == _signal_rows_needed(window, spec.holding_days)
        assert spec.lookback_days > window + spec.holding_days


def test_rank_fraction_leaves_room_for_two_disjoint_legs():
    """The harness skips a formation when 2 * leg_size > n_ranked. At
    rank_fraction 0.40 that can never bind, which is why 0.40 was chosen over
    0.50 (see the module docstring)."""
    for n_ranked in range(13, 200):
        n_leg = max(1, int(n_ranked * JUMP_RANK_FRACTION))
        assert 2 * n_leg <= n_ranked


# --- detector diagnostics -------------------------------------------------


def test_diagnostics_report_the_realized_rate_against_the_nominal_alpha():
    rng = np.random.default_rng(77)
    n, k = 1200, 20
    returns = rng.normal(0.0, 0.015, (n, k))
    # Plant a known number of large discontinuities.
    planted = [(200, 0), (400, 1), (600, 2), (800, 3)]
    for row, col in planted:
        returns[row, col] += 10.0 * 0.015
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(np.vstack([np.zeros(k), returns]), axis=0)),
        index=pd.bdate_range("2010-01-04", periods=n + 1),
        columns=[f"T{i}" for i in range(k)],
    )
    diag = compute_jump_diagnostics(close, window=21, z_crit=Z001, nominal_alpha=0.001)

    assert diag.window == 21
    assert diag.n_ticker_days > 0
    assert diag.n_jump_days == diag.n_up_jumps + diag.n_down_jumps
    assert diag.n_jump_days >= len(planted)
    assert diag.realized_rate == pytest.approx(diag.n_jump_days / diag.n_ticker_days)
    assert diag.rate_vs_nominal == pytest.approx(diag.realized_rate / 0.001)
    # The WINDOW test rejects strictly more often than the day-level rule
    # accepts: attribution condition (ii) can only discard rejections, never
    # add them. Reporting only the day-level rate against a window-level
    # nominal alpha would therefore flatter the test, which is why both exist.
    assert diag.n_window_rejections >= diag.n_jump_days
    assert diag.window_rejection_rate == pytest.approx(
        diag.n_window_rejections / diag.n_ticker_days
    )
    assert diag.window_rate_vs_nominal == pytest.approx(diag.window_rejection_rate / 0.001)
    # A flagged day is a big day — that is the point, and also exactly why the
    # docstring insists this be reported rather than assumed harmless.
    assert diag.mean_abs_jump_return > 3.0 * diag.mean_abs_return_all_days
    assert diag.n_tickers == k


# --- the post-jump event study -------------------------------------------


def test_forward_return_starts_the_day_after_the_event():
    """Off-by-one here would silently include the jump's own return in the
    "response", which would manufacture continuation out of nothing."""
    returns = pd.DataFrame(
        {"X": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]},
        index=pd.bdate_range("2015-01-05", periods=6),
    )
    fwd2 = forward_cumulative_log_return(returns, 2)["X"]
    assert fwd2.iloc[0] == pytest.approx(0.2 + 0.3)
    assert fwd2.iloc[1] == pytest.approx(0.3 + 0.4)
    assert np.isnan(fwd2.iloc[-1])
    assert np.isnan(fwd2.iloc[-2])


def _panel_with_planted_post_jump_effect(
    *, seed: int, effect: float, n_tickers: int = 25, n_days: int = 1400
) -> pd.DataFrame:
    """A panel with jumps injected on a fixed schedule and a planted post-jump
    response of `effect` times the jump size, spread evenly over the following
    5 days. effect < 0 is a REVERSAL world, > 0 a CONTINUATION world, 0.0 the
    null world.

    Jump signs alternate so up- and down-jumps are both well populated, and the
    schedule is offset per ticker so events are not calendar-clustered."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0003, 0.015, (n_days, n_tickers))
    for col in range(n_tickers):
        for i, row in enumerate(range(120 + col * 7, n_days - 40, 90)):
            size = (10.0 if i % 2 == 0 else -10.0) * 0.015
            returns[row, col] += size
            returns[row + 1 : row + 6, col] += effect * size / 5.0
    return pd.DataFrame(
        100.0 * np.exp(np.cumsum(np.vstack([np.zeros(n_tickers), returns]), axis=0)),
        index=pd.bdate_range("2010-01-04", periods=n_days + 1),
        columns=[f"T{i}" for i in range(n_tickers)],
    )


def test_event_study_recovers_a_planted_reversal():
    """Ground truth for the analysis half: a world built with a -40% reversal
    of the jump must read as REVERSAL — up-jumps followed by NEGATIVE abnormal
    returns, down-jumps by POSITIVE ones — and the bootstrap must call it
    significant."""
    close = _panel_with_planted_post_jump_effect(seed=42, effect=-0.4)
    study = run_post_jump_event_study(close, window=21, z_crit=Z001, horizons=(5,), n_bootstrap=500)

    cells = {c.direction: c for c in study.cells}
    assert cells["up"].n_events > 100
    assert cells["down"].n_events > 100
    assert cells["up"].mean_abnormal < 0
    assert cells["down"].mean_abnormal > 0
    assert cells["up"].bootstrap_p_value < 0.05
    assert cells["down"].bootstrap_p_value < 0.05
    assert "REVERSAL" in study.verdict()


def test_event_study_recovers_a_planted_continuation():
    close = _panel_with_planted_post_jump_effect(seed=43, effect=+0.4)
    study = run_post_jump_event_study(close, window=21, z_crit=Z001, horizons=(5,), n_bootstrap=500)
    cells = {c.direction: c for c in study.cells}
    assert cells["up"].mean_abnormal > 0
    assert cells["down"].mean_abnormal < 0
    assert "CONTINUATION" in study.verdict()


def test_event_study_reads_a_world_with_no_planted_effect_as_null():
    """The negative control. Jumps exist, but nothing follows them; the study
    must not manufacture a direction out of ordinary drift — which is precisely
    what the per-ticker baseline subtraction is there to prevent (the panel has
    a real +0.03%/day drift built in)."""
    close = _panel_with_planted_post_jump_effect(seed=44, effect=0.0)
    study = run_post_jump_event_study(close, window=21, z_crit=Z001, horizons=(5,), n_bootstrap=500)
    assert "NULL" in study.verdict()
    for cell in study.cells:
        assert abs(cell.mean_abnormal) < 0.01


def test_event_study_baseline_removes_the_tickers_own_drift():
    """A panel of pure drift plus noise, with jumps that lead nowhere: the RAW
    forward return after a jump is positive (the drift), but the ABNORMAL one
    is not. That difference is the whole reason the baseline exists."""
    close = _panel_with_planted_post_jump_effect(seed=45, effect=0.0)
    study = run_post_jump_event_study(
        close, window=21, z_crit=Z001, horizons=(20,), n_bootstrap=300
    )
    for cell in study.cells:
        assert cell.mean_baseline > 0.0, "the synthetic panel really does drift up"
        assert abs(cell.mean_abnormal) < abs(cell.mean_raw)
        assert cell.mean_raw == pytest.approx(cell.mean_abnormal + cell.mean_baseline, abs=1e-12)


def test_event_study_is_reproducible_under_its_fixed_seed():
    close = _panel_with_planted_post_jump_effect(seed=46, effect=-0.3, n_tickers=10, n_days=900)
    kwargs = {"window": 21, "z_crit": Z001, "horizons": (5,), "n_bootstrap": 200}
    first = run_post_jump_event_study(close, **kwargs)
    second = run_post_jump_event_study(close, **kwargs)
    assert [c.bootstrap_p_value for c in first.cells] == [c.bootstrap_p_value for c in second.cells]
    assert [c.mean_abnormal for c in first.cells] == [c.mean_abnormal for c in second.cells]


def test_bootstrap_p_value_can_never_be_exactly_zero():
    """An empirical p-value cannot resolve past 1/draws; reporting 0.0 would
    overstate what the resampling shows."""
    close = _panel_with_planted_post_jump_effect(seed=47, effect=-0.8, n_tickers=12, n_days=900)
    study = run_post_jump_event_study(
        close, window=21, z_crit=Z001, horizons=(5,), n_bootstrap=100
    )
    assert study.cells
    for cell in study.cells:
        assert cell.bootstrap_p_value >= 1.0 / 101.0


def test_event_study_default_horizons_cover_the_briefs_grid():
    assert EVENT_STUDY_HORIZONS_DAYS == (1, 5, 10, 20)


def _cell(direction: str, abnormal: float, p_value: float, horizon: int = 5) -> EventStudyCell:
    return EventStudyCell(
        horizon_days=horizon,
        direction=direction,
        n_events=1000,
        mean_raw=abnormal,
        mean_baseline=0.0,
        mean_abnormal=abnormal,
        bootstrap_p_value=p_value,
        bootstrap_null_mean=0.0,
        bootstrap_null_std=1.0,
    )


def _verdict(up: EventStudyCell, down: EventStudyCell) -> str:
    return PostJumpEventStudy(
        window=21, z_crit=Z001, n_tickers_used=10, n_bootstrap_draws=2000, seed=1,
        cells=[up, down],
    ).verdict()


def test_an_insignificant_side_cannot_cast_the_deciding_vote():
    """REGRESSION (verification pass, 2026-08-30). The rule's docstring has always
    said only cells clearing 0.05 may vote, but the first implementation checked
    significance only to catch "NEITHER side significant" and then read the
    pattern straight off both point estimates. On the production run that turned
    w=21 / alpha=0.001 / h=1 into CONTINUATION on an up-jump abnormal return of
    +0.0001% with p=0.998 — a coin flip deciding the verdict. Reproduced here at
    the exact production numbers."""
    up = _cell("up", +0.000001, 0.998, horizon=1)
    down = _cell("down", -0.002578, 0.0005, horizon=1)
    assert _verdict(up, down) == "h=1: NULL (the up side is not significant)"


def test_a_pattern_still_reads_when_both_sides_are_significant():
    """The fix must not gag a genuine two-sided result."""
    assert _verdict(_cell("up", +0.01, 0.001), _cell("down", -0.01, 0.001)) == "h=5: CONTINUATION"
    assert _verdict(_cell("up", -0.01, 0.001), _cell("down", +0.01, 0.001)) == "h=5: REVERSAL"


def test_both_sides_insignificant_still_reads_as_the_neither_side_null():
    assert _verdict(_cell("up", +0.01, 0.9), _cell("down", -0.01, 0.8)) == (
        "h=5: NULL (neither side significant)"
    )


def test_two_significant_same_signed_sides_are_null_not_a_pattern():
    """Which is exactly the shape this family's real data has — both sides
    negative — and it must not be read as either hypothesis."""
    assert _verdict(_cell("up", -0.002, 0.004), _cell("down", -0.006, 0.001)) == (
        "h=5: NULL (signs do not form either pattern)"
    )


def test_verdict_significance_threshold_is_the_declared_constant():
    assert EVENT_STUDY_VERDICT_ALPHA == 0.05
    just_inside = _verdict(_cell("up", +0.01, 0.049), _cell("down", -0.01, 0.049))
    just_outside = _verdict(_cell("up", +0.01, 0.051), _cell("down", -0.01, 0.049))
    assert just_inside == "h=5: CONTINUATION"
    assert just_outside == "h=5: NULL (the up side is not significant)"


# --- end-to-end through the real harness, and the persistence contract ----


def _clustered_jump_panel(
    *, seed: int, effect: float, n_tickers: int = 40, n_days: int = 1500, every: int = 25
) -> pd.DataFrame:
    """A panel whose jumps are CALENDAR-CLUSTERED: on each event date roughly
    every ticker jumps, half up and half down, with a planted post-jump
    response of `effect` times the jump size spread over the following 5 days.

    Clustering is required for a harness test, and the reason is itself worth
    stating: rank_fraction 0.40 with min_names_per_leg 5 needs >= 13 FLAGGED
    names in one cross-section, and jumps scattered independently across
    tickers never supply that in a 5-day window. Real jumps do cluster
    (earnings season, macro prints), so this is a legitimate world rather than
    a convenient one — but it is a DIFFERENT world from
    _panel_with_planted_post_jump_effect, which is deliberately unclustered so
    the event study is tested on independent events."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0002, 0.015, (n_days, n_tickers))
    for row in range(150, n_days - 40, every):
        for col in range(n_tickers):
            size = (10.0 if (col + row // every) % 2 == 0 else -10.0) * 0.015
            returns[row, col] += size
            returns[row + 1 : row + 6, col] += effect * size / 5.0
    return pd.DataFrame(
        100.0 * np.exp(np.cumsum(np.vstack([np.zeros(n_tickers), returns]), axis=0)),
        index=pd.bdate_range("2010-01-04", periods=n_days + 1),
        columns=[f"T{i}" for i in range(n_tickers)],
    )


def test_family_replays_through_the_harness_and_carries_the_persistence_contract():
    """persist_cross_sectional_trial_results reads .pattern_id (or .spec_id),
    .sharpe_annualized, .n_trading_days and .deflated_sharpe, calls asdict() on
    the result, and raises on the first one missing — pin them here rather than
    at the call site.

    fixed_universe_membership is used ONLY because this is synthetic data with
    no index-membership concept; its own docstring is explicit that passing an
    equity list to it in production reintroduces survivorship bias, which is
    why run_jump_drift_screening leaves membership_fn at the harness default
    (was_member) instead."""
    close = _clustered_jump_panel(seed=101, effect=-0.5)
    config = CrossSectionalConfig(
        cost_bps=5.0, formation_start=close.index[200].date(), min_names_per_leg=5
    )
    results = screen_cross_sectional_universe(
        CrossSectionalData(close=close),
        JUMP_DRIFT_SPECS,
        config,
        membership_fn=fixed_universe_membership(list(close.columns)),
    )

    assert results, "a 40-ticker synthetic panel with planted jumps should replay"
    for r in results:
        assert isinstance(r.pattern_id, str) and r.pattern_id
        assert isinstance(r.sharpe_annualized, float) and np.isfinite(r.sharpe_annualized)
        assert isinstance(r.n_trading_days, int) and r.n_trading_days > 0
        assert r.deflated_sharpe is not None
        assert r.deflated_sharpe.n_trials == JUMP_SPEC_CEILING == 24
        assert r.deflated_sharpe.dsr_floor_met  # 24 >= MIN_TRIALS_FOR_DSR
        # The writer serializes the whole result; a non-dataclass would raise.
        assert isinstance(json.dumps(asdict(r), default=str), str)


def test_planted_reversal_world_favours_the_reversal_specs_end_to_end():
    """The family's own directional wiring, checked through the full harness:
    in a world built with a planted post-jump REVERSAL, the rev specs must
    out-Sharpe their mirror-image cont specs. This is what proves the
    +1/-1 direction tag reaches the traded book and not just the signal."""
    close = _clustered_jump_panel(seed=102, effect=-0.6)
    config = CrossSectionalConfig(
        cost_bps=0.0, formation_start=close.index[200].date(), min_names_per_leg=5
    )
    results = screen_cross_sectional_universe(
        CrossSectionalData(close=close),
        JUMP_DRIFT_SPECS,
        config,
        membership_fn=fixed_universe_membership(list(close.columns)),
    )
    by_id = {r.pattern_id: r.sharpe_annualized for r in results}
    compared = 0
    for pattern_id, sharpe in by_id.items():
        if not pattern_id.startswith("jump_rev_"):
            continue
        mirror = pattern_id.replace("jump_rev_", "jump_cont_", 1)
        if mirror in by_id:
            assert sharpe > by_id[mirror], f"{pattern_id} did not beat {mirror}"
            compared += 1
    assert compared >= 3, f"only {compared} mirror pairs replayed"


# --- production entry point guard ----------------------------------------


def test_screening_rejects_start_before_membership_coverage():
    """Fails before any network call — a formation before MEMBERSHIP_DATA_START
    would see was_member answer False for the whole universe."""
    with pytest.raises(ValueError, match="predates point-in-time membership coverage"):
        run_jump_drift_screening(date(2010, 1, 4), date(2020, 1, 1))
