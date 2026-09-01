"""Macro/commodity exposure betas — Layer 1 pure math.

Every fixture here is DETERMINISTIC and, where it matters, HAND-COMPUTABLE:
the headline beta assertions below are checked against closed-form values
worked out in the comments, not against whatever the implementation happened
to return when the test was written. A test that only pins current behaviour
would have passed just as happily with the units wrong.

No network call is made anywhere in this file — the real-data run is a
separate, manually-invoked script (run_macro_beta.py), matching this
codebase's convention that automated tests never touch a live provider.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.macro_commodity_beta import MacroCommodityBeta
from app.services.research_lab.macro_beta import (
    BETA_VARIANT_FULL_SAMPLE,
    BETA_VARIANT_SHOCK_DAYS,
    BONFERRONI_ALPHA,
    DRIVER_KIND_PRICE,
    DRIVER_KIND_RATE,
    DRIVER_SOURCE_ETF,
    DRIVER_SOURCE_FRED,
    MACRO_DRIVERS,
    MACRO_DRIVERS_BY_ID,
    MIN_OBS_FULL_SAMPLE,
    N_PRIMARY_TESTS,
    VERDICT_NO_SKILL,
    VERDICT_NO_VERDICT,
    VERDICT_SKILL,
    MacroBetaInputs,
    compute_beta_for_ticker,
    evaluate_out_of_sample_forecast_quality,
    latest_beta_as_of_date,
    levels_to_moves,
    run_macro_beta_family,
    shock_day_mask,
)


def _trading_days(n: int, start: date = date(2024, 1, 1)) -> pd.DatetimeIndex:
    """n consecutive weekdays. The calendar does not matter to any assertion
    here — only that the index is deterministic and shared across series."""
    return pd.bdate_range(start=start, periods=n)


# --- the frozen driver roster ------------------------------------------------


def test_exactly_thirteen_drivers_are_declared_and_all_ids_are_unique():
    assert len(MACRO_DRIVERS) == 13
    ids = [d.driver_id for d in MACRO_DRIVERS]
    assert len(set(ids)) == 13
    assert set(MACRO_DRIVERS_BY_ID) == set(ids)


def test_no_driver_uses_a_raw_futures_symbol():
    """The NG=F roll-splice bug, enforced mechanically rather than by
    intention. Yahoo's continuous-futures tickers all contain "=", and this
    project measured that splice fabricating +28.4%/yr of phantom return
    against the investable proxy (cross_sectional_commodities.py:41-50).
    Every price-side driver here must be a real ETF or a FRED series."""
    for driver in MACRO_DRIVERS:
        assert "=" not in driver.symbol, f"{driver.driver_id} uses a futures-style symbol"
        assert driver.source in (DRIVER_SOURCE_ETF, DRIVER_SOURCE_FRED)
        assert driver.kind in (DRIVER_KIND_PRICE, DRIVER_KIND_RATE)


def test_the_seven_etf_proxies_and_six_fred_series_are_the_declared_ones():
    etfs = {d.symbol for d in MACRO_DRIVERS if d.source == DRIVER_SOURCE_ETF}
    freds = {d.symbol for d in MACRO_DRIVERS if d.source == DRIVER_SOURCE_FRED}
    assert etfs == {"USO", "GLD", "CPER", "UNG", "DBA", "DBC", "FXI"}
    assert freds == {"BAMLH0A0HYM2", "DGS10", "T10Y2Y", "DFII10", "T10YIE", "DTWEXBGS"}


def test_the_bonferroni_denominator_matches_the_preregistered_trial_count():
    """13 drivers x 2 beta variants = 26 primary tests, alpha = 0.05/26.
    Pinned so that adding a driver without revisiting the correction — the
    classic way a pre-registered family quietly turns into a p-hacked one —
    fails a test instead of passing silently."""
    assert N_PRIMARY_TESTS == 26
    assert BONFERRONI_ALPHA == pytest.approx(0.05 / 26)


def test_dtwexbgs_is_a_price_kind_because_it_is_an_index_level_not_a_rate():
    assert MACRO_DRIVERS_BY_ID["dollar_broad"].kind == DRIVER_KIND_PRICE
    for rate_driver in ("credit_spread", "rate_dgs10", "curve_t10y2y",
                        "real_yield_dfii10", "breakeven_t10yie"):
        assert MACRO_DRIVERS_BY_ID[rate_driver].kind == DRIVER_KIND_RATE


# --- level -> move conversion, per kind --------------------------------------


def test_price_kind_moves_are_simple_returns():
    levels = pd.Series([100.0, 110.0, 99.0], index=_trading_days(3))
    moves = levels_to_moves(levels, DRIVER_KIND_PRICE)
    # 110/100 - 1 = +0.10 ; 99/110 - 1 = -0.10
    assert list(moves.round(10)) == [0.10, -0.10]


def test_rate_kind_moves_are_first_differences_in_basis_points():
    """FRED reports DGS10 and friends in PERCENT, so a 4.00 -> 4.10 print is
    a 10 basis-point move, not 0.10. Getting this wrong would rescale every
    rate beta by 100x with nothing in the output to reveal it."""
    levels = pd.Series([4.00, 4.10, 4.05], index=_trading_days(3))
    moves = levels_to_moves(levels, DRIVER_KIND_RATE)
    assert list(moves.round(10)) == [10.0, -5.0]


def test_an_unknown_driver_kind_raises_rather_than_guessing():
    levels = pd.Series([1.0, 2.0], index=_trading_days(2))
    with pytest.raises(ValueError):
        levels_to_moves(levels, "not_a_kind")


# --- the shock-day subset ----------------------------------------------------


def test_shock_mask_selects_the_drivers_own_top_decile_of_absolute_move():
    """180 quiet days at |m| = 0.01 and 20 shock days at |m| = 0.10.

    np.quantile(|m|, 0.90) on 200 points interpolates at position
    0.9 * 199 = 179.1, i.e. between the largest quiet value (0.01, sorted
    index 179) and the smallest shock value (0.10, index 180), giving a
    threshold of 0.01 + 0.1 * 0.09 = 0.019. So the mask selects exactly the
    20 shock days and no quiet day."""
    moves = _shock_moves()
    mask = shock_day_mask(moves)
    assert int(mask.sum()) == 20
    assert set(moves[mask].abs().round(10)) == {0.10}


def _shock_moves() -> pd.Series:
    """90 days at +0.01, 90 at -0.01, 10 at +0.10, 10 at -0.10 — 200 days,
    mean exactly 0, which makes the closed-form beta below trivial."""
    values = [0.01, -0.01] * 90 + [0.10, -0.10] * 10
    return pd.Series(values, index=_trading_days(len(values)))


# --- beta recovery -----------------------------------------------------------


def test_beta_is_recovered_exactly_on_a_noise_free_series():
    """r = 3*m + 0.001 exactly. OLS with an intercept must return beta = 3
    and correlation = 1; the intercept must not leak into the slope."""
    index = _trading_days(120)
    moves = pd.Series(np.linspace(-0.05, 0.05, 120), index=index)
    returns = 3.0 * moves + 0.001

    result = compute_beta_for_ticker("TEST", returns, moves)

    assert result is not None
    assert result.beta_full_sample == pytest.approx(3.0)
    assert result.correlation_full_sample == pytest.approx(1.0)
    assert result.n_observations_full_sample == 120


def test_shock_day_beta_isolates_shock_day_behaviour_from_the_full_sample_beta():
    """Hand-computed. On the 180 quiet days r = 1*m; on the 20 shock days
    r = 5*m. Both m and r have mean exactly 0, so the centred sums are the
    raw sums:

        Sxx = 180*(0.01)^2 + 20*(0.10)^2 = 0.018 + 0.200 = 0.218
        Sxy = 1*180*(0.01)^2 + 5*20*(0.10)^2 = 0.018 + 1.000 = 1.018
        beta_full  = 1.018 / 0.218 = 4.669724770642202
        beta_shock = 5.0 exactly (a perfect fit on those 20 days)

    The gap between 4.67 and 5.0 is the whole reason both betas are
    persisted: the full-sample beta is already dominated by the shock days
    (they carry 92% of the x-variance) yet still does not equal the shock-day
    beta. Resolving that by fiat is exactly what the design refuses to do."""
    moves = _shock_moves()
    mask = shock_day_mask(moves)
    returns = moves.copy()
    returns[mask] = 5.0 * moves[mask]

    result = compute_beta_for_ticker("TEST", returns, moves)

    assert result is not None
    assert result.beta_full_sample == pytest.approx(1.018 / 0.218)
    assert result.beta_full_sample == pytest.approx(4.669724770642202)
    assert result.beta_shock_days == pytest.approx(5.0)
    assert result.n_observations_shock_days == 20
    # Syy = 180*(0.01)^2 + 20*(0.5)^2 = 0.018 + 5.0 = 5.018
    # corr = 1.018 / sqrt(0.218 * 5.018)
    assert result.correlation_full_sample == pytest.approx(1.018 / np.sqrt(0.218 * 5.018))
    # On every shock day sign(r) == sign(beta*m) since beta > 0 and r = 5m.
    assert result.sign_agreement == pytest.approx(1.0)


def test_a_ticker_that_never_moves_with_the_driver_gets_a_beta_of_zero_not_none():
    """A measured zero is a real answer and must be reported as one. Only a
    NON-ESTIMABLE case may come back None — see the next two tests.

    The return series is flat, so beta is zero up to floating-point residue
    (measured ~2e-34, not literally 0.0 — subtracting the mean of a constant
    series does not cancel exactly in accumulated floating point, so an
    exact-equality assertion here would be wrong about real arithmetic).

    The correlation assertion is the load-bearing one. A flat series leaves
    Syy as pure float residue (~1e-64), which is strictly positive, so a
    naive `syy > 0` guard would compute tiny/sqrt(tiny) and hand back an
    arbitrary correlation anywhere in [-1, 1] beside a beta of zero. The
    scale-relative degeneracy guard in _ols_with_intercept must report 0.0."""
    index = _trading_days(120)
    moves = pd.Series(np.linspace(-0.05, 0.05, 120), index=index)
    returns = pd.Series([0.001] * 120, index=index)

    result = compute_beta_for_ticker("FLAT", returns, moves)

    assert result is not None
    assert result.beta_full_sample == pytest.approx(0.0, abs=1e-20)
    assert result.correlation_full_sample == 0.0


def test_too_few_overlapping_days_yields_none_rather_than_a_fabricated_beta():
    index = _trading_days(MIN_OBS_FULL_SAMPLE - 1)
    moves = pd.Series(np.linspace(-0.05, 0.05, len(index)), index=index)
    assert compute_beta_for_ticker("SHORT", 2.0 * moves, moves) is None


def test_a_constant_driver_yields_none_because_the_regression_is_degenerate():
    """Zero variance in x means beta is undefined, not zero. Dividing by
    Sxx = 0 would produce inf or nan and quietly poison the table."""
    index = _trading_days(120)
    moves = pd.Series([0.01] * 120, index=index)
    returns = pd.Series(np.linspace(-0.05, 0.05, 120), index=index)
    assert compute_beta_for_ticker("CONST", returns, moves) is None


def test_shock_beta_is_none_when_too_few_shock_days_are_estimable():
    """NULL means "not estimable" and must never be read as zero."""
    index = _trading_days(120)
    moves = pd.Series(np.linspace(-0.05, 0.05, 120), index=index)
    result = compute_beta_for_ticker(
        "TEST", 2.0 * moves, moves, min_obs_shock_days=999
    )
    assert result is not None
    assert result.beta_shock_days is None


def test_missing_days_are_dropped_not_forward_filled_or_imputed():
    """A missing observation is dropped on both sides. If the implementation
    ever forward-filled, the NaN day below would contribute a fabricated
    zero-move / zero-return pair and drag the beta toward zero."""
    index = _trading_days(120)
    moves = pd.Series(np.linspace(-0.05, 0.05, 120), index=index)
    returns = 4.0 * moves
    returns.iloc[10] = np.nan
    moves_with_gap = moves.copy()
    moves_with_gap.iloc[20] = np.nan

    result = compute_beta_for_ticker("GAPPY", returns, moves_with_gap)

    assert result is not None
    assert result.n_observations_full_sample == 118  # 120 - 2 dropped days
    assert result.beta_full_sample == pytest.approx(4.0)


# --- persistence -------------------------------------------------------------


def _synthetic_inputs(n_days: int = 300, n_tickers: int = 8) -> MacroBetaInputs:
    """A panel covering ALL 13 drivers, deterministic across runs."""
    index = _trading_days(n_days)
    rng = np.random.default_rng(20260901)
    moves = {
        driver.driver_id: pd.Series(rng.normal(0, 0.01, n_days), index=index)
        for driver in MACRO_DRIVERS
    }
    returns = pd.DataFrame(
        {f"T{i:03d}": rng.normal(0, 0.01, n_days) for i in range(n_tickers)}, index=index
    )
    return MacroBetaInputs(
        ticker_returns=returns, driver_moves=moves, missing_tickers=[], failed_drivers={}
    )


def test_run_macro_beta_family_writes_a_row_per_driver_and_ticker(test_db_engine):
    session_local = sessionmaker(bind=test_db_engine)
    inputs = _synthetic_inputs()

    with session_local() as db:
        summary = run_macro_beta_family(
            db, None, None, list(inputs.ticker_returns.columns),
            end=date(2025, 1, 1), window_days=252, inputs=inputs,
        )

    assert summary.n_drivers_computed == 13
    assert summary.n_rows == 13 * 8
    assert summary.window_days == 252

    with session_local() as db:
        rows = db.execute(select(MacroCommodityBeta)).scalars().all()
        assert len(rows) == 13 * 8
        assert {r.driver for r in rows} == set(MACRO_DRIVERS_BY_ID)
        assert all(r.window_days == 252 for r in rows)


def test_recomputing_appends_a_new_generation_and_never_overwrites(test_db_engine):
    """The append-only contract. A second run must ADD rows, not update them
    — a later phase records which beta value it acted on, and an overwrite
    would silently invalidate that record."""
    session_local = sessionmaker(bind=test_db_engine)
    inputs = _synthetic_inputs()
    tickers = list(inputs.ticker_returns.columns)

    with session_local() as db:
        run_macro_beta_family(db, None, None, tickers, end=date(2025, 1, 1), inputs=inputs)
        first_ids = set(db.execute(select(MacroCommodityBeta.id)).scalars().all())

    with session_local() as db:
        run_macro_beta_family(db, None, None, tickers, end=date(2025, 1, 1), inputs=inputs)
        all_ids = set(db.execute(select(MacroCommodityBeta.id)).scalars().all())

    assert len(all_ids) == 2 * len(first_ids)
    assert first_ids.issubset(all_ids), "the first generation's rows must still be present"


def test_latest_beta_as_of_date_is_none_on_an_empty_table(test_db_engine):
    """An empty table means "never computed", which the refresh runner must
    treat as stale. Returning None rather than raising is what lets it."""
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        assert latest_beta_as_of_date(db) is None


def test_the_window_is_sliced_on_aligned_trading_rows_not_calendar_dates(test_db_engine):
    """300 trading days in, window_days=252 out — so exactly 252 observations
    back the beta. Slicing on calendar dates instead would silently shorten
    the window by every weekend and holiday the range spanned."""
    session_local = sessionmaker(bind=test_db_engine)
    inputs = _synthetic_inputs(n_days=300)
    with session_local() as db:
        run_macro_beta_family(
            db, None, None, list(inputs.ticker_returns.columns),
            end=date(2025, 1, 1), window_days=252, inputs=inputs,
        )
        rows = db.execute(select(MacroCommodityBeta)).scalars().all()
    assert {r.n_observations_full_sample for r in rows} == {252}


def _regime_change_inputs(
    n_days: int = 300, window_days: int = 252, early_beta: float = 1.0, late_beta: float = 7.0
) -> MacroBetaInputs:
    """A panel whose oil_uso relationship CHANGES partway through.

    The LAST `window_days` rows have beta exactly `late_beta`; every earlier
    row has `early_beta`. So a correct trailing-window slice recovers
    `late_beta` exactly, while any slice reaching back into the early rows
    cannot. Only oil_uso is given a planted relationship — the other twelve
    drivers get independent noise, which is all these two tests assert on.
    """
    index = _trading_days(n_days)
    rng = np.random.default_rng(20260901)
    moves = {
        d.driver_id: pd.Series(rng.normal(0, 0.01, n_days), index=index) for d in MACRO_DRIVERS
    }
    reference = moves["oil_uso"].to_numpy()
    per_day_beta = np.where(np.arange(n_days) < n_days - window_days, early_beta, late_beta)
    planted = per_day_beta * reference
    returns = pd.DataFrame({f"T{i:03d}": planted for i in range(4)}, index=index)
    return MacroBetaInputs(
        ticker_returns=returns, driver_moves=moves, missing_tickers=[], failed_drivers={}
    )


def test_the_estimation_window_is_the_last_rows_not_the_first(test_db_engine):
    """The window must be the NEWEST `window_days` aligned rows.

    Pins slice DIRECTION, which "n_observations == 252" cannot: taking the
    oldest 252 rows also yields 252 observations and would pass that check
    while silently characterising a stale regime. Here the newest 252 days
    have beta exactly 7.0 and the 48 days before them have beta 1.0, so a
    reversed slice returns a blend and cannot equal 7.0.
    """
    session_local = sessionmaker(bind=test_db_engine)
    inputs = _regime_change_inputs()

    with session_local() as db:
        run_macro_beta_family(
            db, None, None, list(inputs.ticker_returns.columns),
            end=date(2025, 1, 1), window_days=252, inputs=inputs,
        )
        rows = (
            db.execute(select(MacroCommodityBeta).where(MacroCommodityBeta.driver == "oil_uso"))
            .scalars()
            .all()
        )

    assert rows, "expected oil_uso rows"
    for row in rows:
        assert row.beta_full_sample == pytest.approx(7.0)
        assert row.n_observations_full_sample == 252


def test_as_of_date_is_the_last_day_of_the_window_not_the_run_date(test_db_engine):
    """as_of_date must come from the DATA, not from the caller's `end`.

    This is load-bearing well beyond provenance: MacroBetaRefreshRunner's
    staleness gate reads as_of_date, so an as_of_date silently set to the run
    date would always look fresh and the runner would stop recomputing
    forever, with nothing raising. `end` is deliberately set years past the
    panel so the two cannot coincide by accident.
    """
    session_local = sessionmaker(bind=test_db_engine)
    inputs = _regime_change_inputs()
    last_window_day = inputs.ticker_returns.index[-1].date()
    run_date = date(2030, 1, 1)
    assert last_window_day != run_date

    with session_local() as db:
        summary = run_macro_beta_family(
            db, None, None, list(inputs.ticker_returns.columns),
            end=run_date, window_days=252, inputs=inputs,
        )
        rows = db.execute(select(MacroCommodityBeta)).scalars().all()

    assert rows
    assert {r.as_of_date for r in rows} == {last_window_day}
    assert summary.as_of_date == last_window_day
    assert all(r.as_of_date != run_date for r in rows)


# --- the out-of-sample forecast-quality test ---------------------------------


def _oos_inputs(*, planted_skill: bool, n_days: int = 520, n_tickers: int = 120) -> MacroBetaInputs:
    """A panel long enough for the 252/252 split, over all 13 drivers.

    planted_skill=True gives each ticker a FIXED, distinct beta to every
    driver, so the window-A fit genuinely does predict window-B shock days —
    the test must detect that. planted_skill=False makes returns wholly
    independent of every driver, so it must not.
    """
    index = _trading_days(n_days)
    rng = np.random.default_rng(7 if planted_skill else 11)
    betas = np.linspace(-2.0, 2.0, n_tickers)

    moves = {
        driver.driver_id: pd.Series(rng.normal(0, 0.01, n_days), index=index)
        for driver in MACRO_DRIVERS
    }
    reference = moves["oil_uso"].to_numpy()

    columns = {}
    for i in range(n_tickers):
        idiosyncratic = rng.normal(0, 0.002, n_days)
        if planted_skill:
            columns[f"T{i:03d}"] = betas[i] * reference + idiosyncratic
        else:
            columns[f"T{i:03d}"] = idiosyncratic
    returns = pd.DataFrame(columns, index=index)

    return MacroBetaInputs(
        ticker_returns=returns, driver_moves=moves, missing_tickers=[], failed_drivers={}
    )


def test_the_evaluation_returns_one_verdict_per_driver_and_beta_variant():
    results = evaluate_out_of_sample_forecast_quality(_oos_inputs(planted_skill=False))
    assert len(results) == N_PRIMARY_TESTS == 26
    assert {r.beta_variant for r in results} == {BETA_VARIANT_FULL_SAMPLE, BETA_VARIANT_SHOCK_DAYS}
    assert {r.driver for r in results} == set(MACRO_DRIVERS_BY_ID)


def test_planted_forecast_skill_is_detected_for_the_driver_that_has_it():
    """Returns are constructed as beta_i * oil_move + noise, so the window-A
    fit recovers the true betas and they rank-order window-B shock-day
    returns almost perfectly. If this comes back no_skill the test has no
    power and every negative it reports elsewhere is meaningless."""
    results = evaluate_out_of_sample_forecast_quality(_oos_inputs(planted_skill=True))
    oil = next(
        r for r in results
        if r.driver == "oil_uso" and r.beta_variant == BETA_VARIANT_FULL_SAMPLE
    )
    assert oil.verdict == VERDICT_SKILL, oil.reason
    assert oil.mean_rank_correlation > 0.9
    assert oil.p_rank_one_sided < BONFERRONI_ALPHA


def test_a_driver_the_returns_ignore_comes_back_no_skill():
    """The same planted-skill panel: returns depend on the OIL series only,
    so the other 12 drivers must NOT inherit its verdict."""
    results = evaluate_out_of_sample_forecast_quality(_oos_inputs(planted_skill=True))
    unrelated = [
        r for r in results
        if r.driver == "gold_gld" and r.beta_variant == BETA_VARIANT_FULL_SAMPLE
    ]
    assert unrelated[0].verdict == VERDICT_NO_SKILL, unrelated[0].reason


def test_pure_noise_returns_produce_no_demonstrated_skill_anywhere():
    results = evaluate_out_of_sample_forecast_quality(_oos_inputs(planted_skill=False))
    assert all(r.verdict != VERDICT_SKILL for r in results), [
        (r.driver, r.beta_variant, r.reason) for r in results if r.verdict == VERDICT_SKILL
    ]


def test_the_unit_of_observation_is_the_shock_day_not_the_ticker_day_pair():
    """~10% of 252 test days is ~25 shock days, and that — not 25 x 120 =
    3,000 pairs — is the sample size behind every p-value. Pooling pairs
    would understate the standard error by roughly sqrt(120) and manufacture
    significance out of cross-sectional correlation."""
    results = evaluate_out_of_sample_forecast_quality(_oos_inputs(planted_skill=True))
    oil = next(
        r for r in results
        if r.driver == "oil_uso" and r.beta_variant == BETA_VARIANT_FULL_SAMPLE
    )
    assert 15 <= oil.n_shock_days_tested <= 40
    assert oil.n_tickers_fit == 120
    assert oil.min_cross_section == 120


def test_the_fit_and_test_windows_do_not_overlap():
    results = evaluate_out_of_sample_forecast_quality(_oos_inputs(planted_skill=True))
    oil = next(
        r for r in results
        if r.driver == "oil_uso" and r.beta_variant == BETA_VARIANT_FULL_SAMPLE
    )
    assert oil.fit_end < oil.test_start


def test_the_test_window_shock_threshold_comes_from_the_test_window_itself():
    """Window B is made 10x more volatile than window A. If window A's
    threshold were reused, nearly every one of B's 252 days would qualify as
    a shock day. It must stay ~10% of B."""
    n_days, n_tickers = 520, 120
    index = _trading_days(n_days)
    rng = np.random.default_rng(3)
    scale = np.where(np.arange(n_days) < n_days - 252, 0.001, 0.01)
    moves = {
        d.driver_id: pd.Series(rng.normal(0, 1, n_days) * scale, index=index)
        for d in MACRO_DRIVERS
    }
    returns = pd.DataFrame(
        {f"T{i:03d}": rng.normal(0, 0.01, n_days) for i in range(n_tickers)}, index=index
    )
    inputs = MacroBetaInputs(
        ticker_returns=returns, driver_moves=moves, missing_tickers=[], failed_drivers={}
    )

    results = evaluate_out_of_sample_forecast_quality(inputs)
    tested = [r.n_shock_days_tested for r in results if r.verdict != VERDICT_NO_VERDICT]

    assert tested, "expected at least one driver to reach a verdict"
    assert all(n <= 40 for n in tested), tested


def test_insufficient_history_is_no_verdict_and_never_a_negative():
    """A NO VERDICT says the pre-registered test could not be run at the
    declared power. Reporting that as "no skill" would be a claim the data
    does not support."""
    inputs = _oos_inputs(planted_skill=True, n_days=300)  # < 504 aligned days
    results = evaluate_out_of_sample_forecast_quality(inputs)
    assert all(r.verdict == VERDICT_NO_VERDICT for r in results)
    assert all("insufficient history" in r.reason for r in results)


def test_a_driver_whose_series_failed_to_fetch_is_no_verdict_not_no_skill():
    inputs = _oos_inputs(planted_skill=True)
    del inputs.driver_moves["credit_spread"]
    inputs.failed_drivers["credit_spread"] = "FRED fetch failed: boom"

    results = evaluate_out_of_sample_forecast_quality(inputs)
    credit = [r for r in results if r.driver == "credit_spread"]

    assert len(credit) == 2
    assert all(r.verdict == VERDICT_NO_VERDICT for r in credit)
    assert all("boom" in r.reason for r in credit)


def test_too_small_a_cross_section_is_no_verdict():
    """Fewer than 100 tickers cannot support the pre-registered test."""
    inputs = _oos_inputs(planted_skill=True, n_tickers=20)
    results = evaluate_out_of_sample_forecast_quality(inputs)
    assert all(r.verdict == VERDICT_NO_VERDICT for r in results)
    assert all("estimable" in r.reason for r in results)


def test_shock_day_beta_variant_is_evaluated_separately_from_full_sample():
    """Both variants must reach a real verdict — the design deliberately
    refuses to pick between them a priori, so both have to be measurable."""
    results = evaluate_out_of_sample_forecast_quality(_oos_inputs(planted_skill=True))
    shock = next(
        r for r in results
        if r.driver == "oil_uso" and r.beta_variant == BETA_VARIANT_SHOCK_DAYS
    )
    assert shock.verdict in (VERDICT_SKILL, VERDICT_NO_SKILL)
    assert shock.n_tickers_fit > 0


def test_every_driver_including_all_thirteen_is_reachable_by_the_evaluation():
    """Coverage of the full roster, so a driver that silently stopped being
    evaluated (a typo'd id, a dropped tuple entry) fails a test."""
    results = evaluate_out_of_sample_forecast_quality(_oos_inputs(planted_skill=False))
    by_driver = {r.driver for r in results}
    for driver in MACRO_DRIVERS:
        assert driver.driver_id in by_driver
    assert len(by_driver) == 13


# --- the read-only API -------------------------------------------------------


def _seed_rows(test_db_engine, driver: str, betas: dict[str, float], as_of: date) -> None:
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        for ticker, beta in betas.items():
            db.add(
                MacroCommodityBeta(
                    driver=driver, ticker=ticker, as_of_date=as_of, window_days=252,
                    beta_full_sample=beta, beta_shock_days=None,
                    correlation_full_sample=0.3, n_observations_full_sample=252,
                    n_observations_shock_days=25, t_stat_full_sample=2.0,
                    sign_agreement=0.55,
                )
            )
        db.commit()


def test_the_api_requires_authentication(client):
    assert client.get("/api/macro-beta/oil_uso").status_code == 401
    assert client.get("/api/macro-beta/drivers").status_code == 401


def test_the_driver_catalog_lists_all_thirteen(client, register_and_verify):
    register_and_verify(client)
    response = client.get("/api/macro-beta/drivers")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["drivers"]) == 13
    assert body["disclaimer"]


def test_rows_are_ranked_by_absolute_beta_within_the_driver(
    client, register_and_verify, test_db_engine
):
    """|-9.0| outranks +4.0 — the ranking is by MAGNITUDE, since a strongly
    negative sensitivity is just as relevant to a shock as a positive one."""
    register_and_verify(client)
    _seed_rows(
        test_db_engine, "oil_uso",
        {"AAA": 1.0, "BBB": 4.0, "CCC": -9.0, "DDD": 0.1},
        date(2026, 8, 31),
    )

    response = client.get("/api/macro-beta/oil_uso")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [r["ticker"] for r in body["rows"]] == ["CCC", "BBB", "AAA", "DDD"]
    assert body["as_of_date"] == "2026-08-31"
    assert body["driver"]["symbol"] == "USO"
    assert body["disclaimer"]


def test_only_the_newest_generation_is_returned(
    client, register_and_verify, test_db_engine
):
    """The table is append-only and keeps every past generation. Mixing them
    in one ranking would compare betas measured at different times."""
    register_and_verify(client)
    _seed_rows(test_db_engine, "gold_gld", {"OLD": 99.0}, date(2026, 1, 31))
    _seed_rows(test_db_engine, "gold_gld", {"NEW": 1.0}, date(2026, 8, 31))

    body = client.get("/api/macro-beta/gold_gld").json()

    assert [r["ticker"] for r in body["rows"]] == ["NEW"]
    assert body["as_of_date"] == "2026-08-31"


def test_the_newest_generation_is_scoped_per_driver_not_run_wide(
    client, register_and_verify, test_db_engine
):
    """MAX(as_of_date) must be taken WITHIN the requested driver.

    This is the real shape of the 2026-09-01 run, not a hypothetical: the
    four ETF drivers landed on as_of 2026-08-27 and the other nine on
    2026-08-28, because each driver's window ends on its OWN last aligned
    day. A run-wide MAX would resolve to the later date and return an EMPTY
    row list — a 200 with no rows — for every driver that legitimately lags,
    which is silent and would look like "no data yet" rather than a bug.

    Every other API test here seeds a single driver, so none of them can
    catch it.
    """
    register_and_verify(client)
    _seed_rows(test_db_engine, "copper_cper", {"AAA": 3.0}, date(2026, 8, 27))
    _seed_rows(test_db_engine, "credit_spread", {"BBB": 5.0}, date(2026, 8, 28))

    lagging = client.get("/api/macro-beta/copper_cper")
    assert lagging.status_code == 200, lagging.text
    lagging_body = lagging.json()
    assert [r["ticker"] for r in lagging_body["rows"]] == ["AAA"]
    assert lagging_body["as_of_date"] == "2026-08-27"

    leading_body = client.get("/api/macro-beta/credit_spread").json()
    assert [r["ticker"] for r in leading_body["rows"]] == ["BBB"]
    assert leading_body["as_of_date"] == "2026-08-28"


def test_an_unknown_driver_is_404_with_the_allowed_list(client, register_and_verify):
    register_and_verify(client)
    response = client.get("/api/macro-beta/not_a_driver")
    assert response.status_code == 404, response.text
    assert "oil_uso" in response.json()["detail"]


def test_a_known_driver_with_no_computed_rows_is_404(client, register_and_verify):
    register_and_verify(client)
    response = client.get("/api/macro-beta/natgas_ung")
    assert response.status_code == 404, response.text
    assert "No betas have been computed yet" in response.json()["detail"]


def test_the_limit_is_honoured_and_bounded(client, register_and_verify, test_db_engine):
    register_and_verify(client)
    _seed_rows(
        test_db_engine, "copper_cper",
        {f"T{i:02d}": float(i) for i in range(40)},
        date(2026, 8, 31),
    )

    assert len(client.get("/api/macro-beta/copper_cper?limit=5").json()["rows"]) == 5
    assert client.get("/api/macro-beta/copper_cper?limit=0").status_code == 422
    assert client.get("/api/macro-beta/copper_cper?limit=999").status_code == 422


def test_a_non_estimable_shock_beta_serializes_as_null_not_zero(
    client, register_and_verify, test_db_engine
):
    """NULL means "not estimable". A consumer coercing it to 0.0 would be
    asserting "no sensitivity on shock days", a claim the row does not make."""
    register_and_verify(client)
    _seed_rows(test_db_engine, "agri_dba", {"AAA": 2.0}, date(2026, 8, 31))
    row = client.get("/api/macro-beta/agri_dba").json()["rows"][0]
    assert row["beta_shock_days"] is None


def test_evaluation_dates_are_reported_so_a_run_is_reproducible():
    results = evaluate_out_of_sample_forecast_quality(_oos_inputs(planted_skill=True))
    graded = [r for r in results if r.verdict != VERDICT_NO_VERDICT]
    assert graded
    for r in graded:
        assert r.fit_start is not None and r.fit_end is not None
        assert r.test_start is not None and r.test_end is not None
        assert r.fit_start < r.fit_end < r.test_start < r.test_end
        assert isinstance(r.test_end, date)
        assert r.test_end - r.fit_start > timedelta(days=365)
