"""Tests for the multi-signal combination experiment.

Two jobs, matching the two things that could silently go wrong:

  1. THE SELECTION RULE. The whole experiment's validity rests on Step 1
     excluding the specific specs this project's own verification passes
     already disqualified, and on the numeric threshold being applied
     uniformly and one-spec-per-family. Every hard exclusion is asserted by
     NAME here, so deleting one from HARD_EXCLUSIONS fails a test rather
     than quietly enlarging the candidate set.

  2. THE PIPELINE WIRING. RMT denoising, HRP and Kelly each have their own
     large test suites (test_rmt_denoising.py, test_hrp_optimizer.py,
     test_kelly_sizing.py). Nothing here re-tests them. These tests check
     only that this module composes them correctly on synthetic data whose
     right answer is known by construction.
"""

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import sessionmaker

from app.models.cross_sectional_trial_result import CrossSectionalTrialResult
from app.services.research_lab.multi_signal_combination import (
    HARD_EXCLUSIONS,
    MULTI_SIGNAL_FAMILY,
    PSR_SELECTION_THRESHOLD,
    CandidateSelection,
    ScannedSpec,
    build_persistable,
    build_returns_matrix,
    combined_series,
    compound_onto_calendar,
    equal_weights,
    inverse_volatility_weights,
    load_scanned_specs,
    persist_combination,
    run_combination,
    select_candidates,
)


def _spec(family, trial, psr, sharpe=0.3, dsr=0.4, n=2900, k=9, tag="t"):
    return ScannedSpec(
        family_key=family,
        run_tag=tag,
        trial_id=trial,
        sharpe_annualized=sharpe,
        dsr=dsr,
        psr_vs_zero=psr,
        n_observations=n,
        n_trials=k,
    )


def _decision(selection: CandidateSelection, trial_id: str):
    return next(d for d in selection.decisions if d.spec.trial_id == trial_id)


# ---------------------------------------------------------------------------
# 1. Step 1(a) — the known-artifact exclusions, by name.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("family", "trial"),
    [
        # Raw NOA: "DO NOT TREAT AS VALIDATED EDGE: likely sector-tilt artifact".
        ("quality_noa", "noa_low_ls_h126_quintile"),
        ("quality_noa", "noa_low_ls_h63_quintile"),
        # Industry-neutral NOA: "Do not trade NOA in any form on this universe."
        ("quality_noa_industry_neutral", "noa_neutral_ls_h126_median"),
        # Funding carry: confirmed untradeable (universe decay).
        ("funding_carry", "xf_carry_w30_h7_f10"),
        ("funding_carry", "xf_carry_w14_h7_f20"),
        # Cost-dominated under the EDGE re-audit.
        ("round_c", "lps_intraday_l252_h63"),
        ("phase_a_intraday_expanded", "volume_climax_4x_midday"),
    ],
)
def test_known_artifact_specs_are_hard_excluded_even_with_a_passing_psr(family, trial):
    """Each of these would sail through the numeric threshold — several of
    them have the best PSR in the whole table — so only the documented
    hard-exclude rule can stop them."""
    selection = select_candidates([_spec(family, trial, psr=0.99, sharpe=1.5)])
    decision = _decision(selection, trial)
    assert decision.selected is False
    assert decision.stage == "hard_exclude"
    assert selection.selected == ()


def test_seasonality_placebo_is_excluded_but_its_siblings_are_not():
    """The seasonality exclusion is spec-level, not family-level: the
    placebo arm is a confirmed artifact, the same-month arms are an ordinary
    honest negative and must stay eligible."""
    placebo = _spec(
        "same_calendar_month_seasonality",
        "seasonality_other_month_placebo_20y_ls",
        psr=0.7835,
    )
    sibling = _spec(
        "same_calendar_month_seasonality", "seasonality_same_month_20y_ls", psr=0.72
    )
    selection = select_candidates([placebo, sibling])
    assert _decision(selection, placebo.trial_id).stage == "hard_exclude"
    assert _decision(selection, sibling.trial_id).stage == "selected"
    assert [s.trial_id for s in selection.selected] == [sibling.trial_id]


def test_every_hard_exclusion_names_a_category_and_a_source_file():
    """A hard exclusion without a documented reason is exactly the kind of
    unexplained filter that could hide a post-hoc choice."""
    for rule in HARD_EXCLUSIONS:
        assert rule.category in {"artifact", "untradeable", "imperative"}
        assert rule.source_file.endswith(".py")
        assert len(rule.reason) > 80


# ---------------------------------------------------------------------------
# 2. Step 1(b)/(c) — the threshold and one-spec-per-family.
# ---------------------------------------------------------------------------


def test_the_pre_declared_constants_are_pinned_to_their_declared_values():
    """Added by the independent verification pass (2026-08-29). The other
    selection tests deliberately reference PSR_SELECTION_THRESHOLD rather
    than 0.50, which means a mutation of the constant itself passed the
    whole suite (verified by mutating it to 0.40 — 32/32 passed). The
    module docstring pre-declares these exact values; changing any of them
    is a revision of the pre-registration and must fail loudly, not
    ripple silently through self-referential tests."""
    from app.services.research_lab.multi_signal_combination import (
        COMBINED_NULL_P_VALUE_BAR,
        COMBINED_SIGNIFICANCE_BAR,
        NULL_CONTROL_DRAWS,
        NULL_CONTROL_SEED,
    )

    assert PSR_SELECTION_THRESHOLD == 0.50
    assert COMBINED_SIGNIFICANCE_BAR == 0.90
    assert COMBINED_NULL_P_VALUE_BAR == 0.05
    assert NULL_CONTROL_DRAWS == 2000
    assert NULL_CONTROL_SEED == 20260829


def test_threshold_is_applied_uniformly_at_the_declared_value():
    just_over = _spec("fam_a", "a_over", psr=PSR_SELECTION_THRESHOLD)
    just_under = _spec("fam_b", "b_under", psr=PSR_SELECTION_THRESHOLD - 1e-9)
    selection = select_candidates([just_over, just_under])
    assert _decision(selection, "a_over").stage == "selected"
    assert _decision(selection, "b_under").stage == "threshold"


def test_a_none_psr_never_passes_the_threshold():
    """A spec whose PSR could not be computed is not evidence of a positive
    Sharpe, so it must fail rather than be treated as missing-and-fine."""
    selection = select_candidates([_spec("fam", "no_psr", psr=None)])
    assert _decision(selection, "no_psr").stage == "threshold"


def test_only_the_family_best_is_selected_and_the_criterion_is_psr():
    best = _spec("fam", "best", psr=0.90, sharpe=0.1)
    # Higher Sharpe but lower PSR — must lose, because the declared
    # criterion is PSR, not Sharpe.
    runner_up = _spec("fam", "runner_up", psr=0.80, sharpe=9.9)
    selection = select_candidates([runner_up, best])
    assert [s.trial_id for s in selection.selected] == ["best"]
    assert _decision(selection, "runner_up").stage == "not_family_best"


def test_one_spec_is_taken_per_family_not_per_table():
    specs = [
        _spec("fam_a", "a1", psr=0.9),
        _spec("fam_a", "a2", psr=0.8),
        _spec("fam_b", "b1", psr=0.7),
        _spec("fam_b", "b2", psr=0.6),
    ]
    selection = select_candidates(specs)
    assert sorted(s.trial_id for s in selection.selected) == ["a1", "b1"]


def test_ties_break_deterministically_on_sharpe_then_trial_id():
    a = _spec("fam", "aaa", psr=0.8, sharpe=0.5)
    b = _spec("fam", "bbb", psr=0.8, sharpe=0.5)
    forward = select_candidates([a, b]).selected
    backward = select_candidates([b, a]).selected
    assert [s.trial_id for s in forward] == [s.trial_id for s in backward] == ["aaa"]


def test_every_scanned_spec_gets_exactly_one_decision():
    specs = [
        _spec("quality_noa", "noa_low_ls_h63", psr=0.98),
        _spec("fam", "x", psr=0.9),
        _spec("fam", "y", psr=0.6),
        _spec("fam2", "z", psr=0.1),
    ]
    selection = select_candidates(specs)
    assert len(selection.decisions) == len(specs) == selection.n_scanned
    assert {d.spec.trial_id for d in selection.decisions} == {s.trial_id for s in specs}


def test_surviving_sharpes_exclude_only_the_hard_excluded():
    """Section 4A's diagnostic denominator: hard-excluded specs are out,
    threshold-failing ones are still part of the search."""
    specs = [
        _spec("quality_noa", "noa_low_ls_h63", psr=0.98, sharpe=5.0),
        _spec("fam", "kept", psr=0.9, sharpe=1.0),
        _spec("fam2", "below_threshold", psr=0.1, sharpe=-1.0),
    ]
    selection = select_candidates(specs)
    assert sorted(selection.surviving_sharpes) == [-1.0, 1.0]
    assert sorted(selection.scanned_sharpes) == [-1.0, 1.0, 5.0]


# ---------------------------------------------------------------------------
# 3. Reading the real table.
# ---------------------------------------------------------------------------


def _row(db, family, trial, tag, sharpe=0.2, psr=0.6):
    db.add(
        CrossSectionalTrialResult(
            family_key=family,
            trial_id=trial,
            run_tag=tag,
            sharpe_annualized=sharpe,
            n_observations=1000,
            n_trials=8,
            dsr=0.3,
            psr_vs_zero=psr,
            full_result_json="{}",
        )
    )


def test_load_refuses_to_guess_between_run_tags(test_db_engine):
    db = sessionmaker(bind=test_db_engine)()
    _row(db, "mystery_family", "m1", "build_a")
    _row(db, "mystery_family", "m1", "build_b")
    db.commit()
    with pytest.raises(ValueError, match="CANONICAL_RUN_TAGS"):
        load_scanned_specs(db)


def test_load_excludes_this_modules_own_persisted_rows(test_db_engine):
    """A combination cannot be one of its own inputs."""
    db = sessionmaker(bind=test_db_engine)()
    _row(db, "some_family", "s1", "only_tag")
    _row(db, MULTI_SIGNAL_FAMILY, "rmt_denoised_hrp", "multi_signal_build_2026-08-29")
    db.commit()
    loaded = load_scanned_specs(db)
    assert [s.family_key for s in loaded] == ["some_family"]


# ---------------------------------------------------------------------------
# 4. Calendar alignment.
# ---------------------------------------------------------------------------


def test_compounding_leaves_a_series_already_on_the_calendar_untouched():
    cal = pd.bdate_range("2024-01-01", periods=20)
    series = pd.Series(np.linspace(-0.01, 0.01, 20), index=cal)
    pd.testing.assert_series_equal(compound_onto_calendar(series, cal), series)


def test_compounding_conserves_the_cumulative_return_of_the_finer_series():
    """The whole point of compounding rather than dropping: a 24/7 sleeve's
    weekend P&L must survive the move onto a weekday calendar."""
    daily = pd.date_range("2024-01-01", periods=28, freq="D")
    rng = np.random.default_rng(7)
    fine = pd.Series(rng.normal(0.001, 0.01, len(daily)), index=daily)
    cal = pd.bdate_range("2024-01-01", "2024-01-28")
    coarse = compound_onto_calendar(fine, cal)
    # Everything up to the last common date is preserved exactly.
    kept = fine[fine.index <= cal[-1]]
    assert (1.0 + coarse).prod() == pytest.approx((1.0 + kept).prod(), rel=1e-12)


def test_a_calendar_date_with_no_native_observation_is_flat_not_nan():
    cal = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])
    fine = pd.Series([0.05], index=pd.DatetimeIndex(["2024-01-02"]))
    out = compound_onto_calendar(fine, cal)
    assert out.tolist() == pytest.approx([0.05, 0.0, 0.0])


def test_build_returns_matrix_uses_the_intersection_and_never_fabricates():
    cal_long = pd.bdate_range("2024-01-01", periods=40)
    cal_short = cal_long[10:30]
    frame = build_returns_matrix(
        {
            "a": pd.Series(0.001, index=cal_long),
            "b": pd.Series(0.002, index=cal_short),
        }
    )
    assert list(frame.index) == list(cal_short)
    assert np.isfinite(frame.to_numpy()).all()


def test_a_finer_calendar_sleeve_cannot_extend_the_window_backwards():
    equity = pd.bdate_range("2024-01-01", periods=60)
    crypto_days = pd.date_range("2024-02-01", periods=40, freq="D")
    frame = build_returns_matrix(
        {"eq": pd.Series(0.001, index=equity), "cx": pd.Series(0.002, index=crypto_days)},
        daily_calendar_specs=("cx",),
    )
    assert frame.index.min() >= crypto_days.min()
    assert frame.index.max() <= crypto_days.max()


# ---------------------------------------------------------------------------
# 5. Pipeline wiring on synthetic data with a known answer.
# ---------------------------------------------------------------------------


def _synthetic_selection(labels):
    specs = [_spec(f"fam_{i}", label, psr=0.8) for i, label in enumerate(labels)]
    return select_candidates(specs)


def _synthetic_series(n_obs=1000, seed=11):
    """Four uncorrelated sleeves with deliberately unequal volatility, so
    the risk-based and return-blind weighting schemes must disagree."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n_obs)
    vols = {"s_lo": 0.002, "s_mid": 0.004, "s_hi": 0.010, "s_hi2": 0.012}
    return {k: pd.Series(rng.normal(0.0002, v, n_obs), index=idx) for k, v in vols.items()}


def test_pipeline_composes_rmt_hrp_and_kelly_end_to_end():
    series = _synthetic_series()
    selection = _synthetic_selection(list(series))
    summary = run_combination(
        selection,
        series,
        family_spec_counts=dict.fromkeys(series, 3),
        run_null=False,
    )
    methods = [r.method for r in summary.results]
    assert methods == [
        "rmt_denoised_hrp",
        "hrp_no_denoise",
        "equal_weight",
        "inverse_volatility",
    ]
    for result in summary.results:
        assert set(result.weights) == set(series)
        assert sum(result.weights.values()) == pytest.approx(1.0)
        assert len(result.daily_returns) == summary.n_trading_days
    # The RMT diagnostics must actually come from the denoised call, not be
    # left None — that is the wiring this test exists to check.
    rmt = summary.results[0]
    assert rmt.rmt_n_signal is not None
    assert rmt.rmt_n_signal + rmt.rmt_n_noise == len(series)
    assert rmt.rmt_lambda_plus > 1.0
    assert set(rmt.hrp_quasi_diag_order) == set(series)
    # Kelly ran on the HRP direction and reported a scale, not a direction.
    assert summary.kelly["kelly_fraction"] == 0.5
    assert summary.kelly["leverage_at_kelly_fraction"] == pytest.approx(
        0.5 * summary.kelly["full_kelly_leverage"]
    )
    assert summary.kelly["zero_growth_leverage"] == pytest.approx(
        2.0 * summary.kelly["full_kelly_leverage"]
    )
    assert summary.kelly["risk_free_rate"] == 0.0


def test_hrp_weights_are_risk_based_so_the_high_vol_sleeve_gets_least():
    """Pins the mechanism behind the real result: HRP allocates by variance
    and is blind to expected return, so it must underweight the volatile
    sleeves regardless of how well they did."""
    series = _synthetic_series()
    summary = run_combination(
        _synthetic_selection(list(series)),
        series,
        family_spec_counts=dict.fromkeys(series, 3),
        run_null=False,
    )
    hrp = summary.results[0].weights
    equal = summary.results[2].weights
    assert hrp["s_lo"] > hrp["s_hi"]
    assert hrp["s_lo"] > hrp["s_hi2"]
    assert len(set(equal.values())) == 1


def test_the_combined_series_is_exactly_the_weighted_sum():
    series = _synthetic_series(n_obs=300, seed=3)
    frame = build_returns_matrix(series)
    weights = {"s_lo": 0.4, "s_mid": 0.3, "s_hi": 0.2, "s_hi2": 0.1}
    got = combined_series(frame, weights)
    expected = sum(frame[k] * w for k, w in weights.items())
    pd.testing.assert_series_equal(got, expected, check_names=False)


def test_combined_series_refuses_incomplete_weights():
    frame = build_returns_matrix(_synthetic_series(n_obs=100))
    with pytest.raises(ValueError, match="do not cover"):
        combined_series(frame, {"s_lo": 1.0})


def test_baseline_weight_helpers_are_what_they_claim():
    frame = build_returns_matrix(_synthetic_series(n_obs=500, seed=5))
    eq = equal_weights(frame)
    iv = inverse_volatility_weights(frame)
    assert set(eq.values()) == {0.25}
    assert sum(iv.values()) == pytest.approx(1.0)
    # Inverse-vol must rank strictly opposite to realized volatility.
    order_by_weight = sorted(iv, key=lambda k: iv[k])
    order_by_vol = sorted(frame.columns, key=lambda c: -frame[c].std(ddof=1))
    assert order_by_weight == order_by_vol


def test_null_control_on_zero_edge_data_does_not_reject():
    """A real end-to-end run of the pre-declared null on synthetic noise:
    a zero-edge combination must NOT come out significant."""
    series = _synthetic_series(n_obs=800, seed=21)
    summary = run_combination(
        _synthetic_selection(list(series)),
        series,
        family_spec_counts=dict.fromkeys(series, 4),
        run_null=True,
    )
    assert summary.null_control is not None
    assert summary.null_control.n_draws > 0
    assert 0.0 <= summary.null_control.p_value_rmt_hrp <= 1.0
    assert "HONEST NEGATIVE" in summary.verdict


def test_null_control_is_reproducible_from_its_declared_seed():
    series = _synthetic_series(n_obs=400, seed=9)
    selection = _synthetic_selection(list(series))
    counts = dict.fromkeys(series, 3)
    a = run_combination(selection, series, family_spec_counts=counts, run_null=True)
    b = run_combination(selection, series, family_spec_counts=counts, run_null=True)
    assert a.null_control.p_value_rmt_hrp == b.null_control.p_value_rmt_hrp
    assert a.null_control.null_median_sharpe_rmt_hrp == pytest.approx(
        b.null_control.null_median_sharpe_rmt_hrp
    )


def test_null_control_requires_counts_keyed_by_the_returns_columns():
    series = _synthetic_series(n_obs=200)
    with pytest.raises(ValueError, match="family_spec_counts"):
        run_combination(
            _synthetic_selection(list(series)),
            series,
            family_spec_counts={"wrong": 3},
            run_null=True,
        )


# ---------------------------------------------------------------------------
# 6. Persistence.
# ---------------------------------------------------------------------------


def test_persisted_rows_carry_the_dsr_caveat_and_the_return_series(test_db_engine):
    series = _synthetic_series(n_obs=400, seed=13)
    summary = run_combination(
        _synthetic_selection(list(series)),
        series,
        family_spec_counts=dict.fromkeys(series, 3),
        run_null=False,
    )
    rows = build_persistable(summary)
    assert len(rows) == 4
    for row in rows:
        assert row.dsr_is_not_a_bailey_lopez_de_prado_dsr is True
        assert "not a Bailey" not in row.spec_id  # the caveat lives in its own field
        assert "deflation-style SENSITIVITY" in row.dsr_caveat
        assert len(row.daily_returns) == summary.n_trading_days
        assert row.selection_reasoning

    db = sessionmaker(bind=test_db_engine)()
    written = persist_combination(db, summary, run_tag="unit_test_run")
    assert written == 4
    stored = (
        db.query(CrossSectionalTrialResult)
        .filter_by(family_key=MULTI_SIGNAL_FAMILY)
        .all()
    )
    assert {r.trial_id for r in stored} == {
        "rmt_denoised_hrp",
        "hrp_no_denoise",
        "equal_weight",
        "inverse_volatility",
    }
    assert all(r.n_trials == summary.selection.n_scanned for r in stored)
