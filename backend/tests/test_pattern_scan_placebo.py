"""Validation of the rule-free pattern scanner on a KNOWN answer, plus the
control non-degeneracy, determinism and encoding checks the pre-registration
requires before the real scan is believed.

Contract: `data/research_runs/pattern_scan_2026-09-11/PREREGISTRATION.md` §7
(synthetic validation), §5 (control non-degeneracy, seeded draws) and §3
(alphabet), as amended by ADDENDUM_01 item I, which declares the split and
floors §7 leaves open: 1,400 discovery bars / 600 holdout bars, the shift
measured in the same 20-bar sigma the scanner uses, and Panel E's 10-name /
250-bar floors.

The synthetic panel is built ONCE per module (session-scoped fixture) because
a 500 x 2,000 scan over three k values is the expensive part of this file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab import pattern_scan_placebo as ps

# --- §7's declared panel ----------------------------------------------------

SYNTH_NAMES = 500
SYNTH_BARS = 2000
SYNTH_DISCOVERY_BARS = 1400          # ADDENDUM 01 item I
PLANTED_SHIFT_SIGMA = 0.30           # §7 "+0.30 sigma"
PLANTED_PATTERN = (2, 2, 2)          # §7 "(U, U, U)"
SYNTH_SEED = 20260911

SYNTH_SPEC_DATES = pd.date_range("2000-01-03", periods=SYNTH_BARS, freq="B")

SYNTH_SPEC = ps.PanelSpec(
    key="S",
    label="synthetic validation panel (PREREGISTRATION §7)",
    min_names=10,
    min_bars=250,
    periods_per_year=252.0,
    cost_bp_one_way=5.0,
    discovery_start=str(SYNTH_SPEC_DATES[0].date()),
    discovery_end=str(SYNTH_SPEC_DATES[SYNTH_DISCOVERY_BARS - 1].date()),
    holdout_start=str(SYNTH_SPEC_DATES[SYNTH_DISCOVERY_BARS].date()),
    holdout_end=str(SYNTH_SPEC_DATES[-1].date()),
)


def _synthetic_returns() -> tuple[np.ndarray, np.ndarray]:
    """(base, planted). i.i.d. Student-t(4) returns scaled to ~1% a bar, then
    the planted rule: the return that FOLLOWS a (U,U,U) computed on the BASE
    series is shifted by +0.30 * sigma_{i,t+1}.

    The plant is deliberately measured on the base series while the scanner
    re-derives its bins from the planted series (ADDENDUM 01 item I) — the
    recovery test is therefore harder than a self-consistent plant, not
    easier."""
    rng = np.random.default_rng(SYNTH_SEED)
    base = rng.standard_t(df=4, size=(SYNTH_BARS, SYNTH_NAMES)) * (0.01 / np.sqrt(2.0))
    bins = ps.bin_matrix(base)
    sigma = ps.rolling_sigma(base)
    trigger = np.zeros(base.shape, dtype=bool)
    for j, want in enumerate(reversed(PLANTED_PATTERN)):      # j = 0 is bar t
        shifted = np.full(base.shape, -1, dtype=np.int8)
        if j == 0:
            shifted = bins
        else:
            shifted[j:] = bins[: SYNTH_BARS - j]
        trigger = (shifted == want) if j == 0 else (trigger & (shifted == want))
    planted = base.copy()
    fire = np.zeros(base.shape, dtype=bool)
    fire[1:] = trigger[:-1]                                    # outcome bar is t+1
    shift = np.where(np.isfinite(sigma), sigma, 0.0) * PLANTED_SHIFT_SIGMA
    planted[fire] = planted[fire] + shift[fire]
    return base, planted


@pytest.fixture(scope="module")
def synthetic():
    _base, planted = _synthetic_returns()
    panel = ps.build_panel(SYNTH_SPEC_DATES, [f"N{i:03d}" for i in range(SYNTH_NAMES)], planted)
    discovery = ps.run_discovery(panel, SYNTH_SPEC, horizons=(ps.HORIZON_PRIMARY,))
    return planted, panel, discovery[ps.HORIZON_PRIMARY]


# ---------------------------------------------------------------------------
# Base-3 encoding (§3)
# ---------------------------------------------------------------------------

def test_base3_encoding_round_trips_for_every_pattern():
    seen: set[int] = set()
    for k in ps.K_VALUES:
        for code in range(ps.N_BINS**k):
            bins = ps.decode_pattern(code, k)
            assert len(bins) == k
            assert ps.encode_pattern(bins) == code
            pid = ps.pattern_id(code, k)
            assert ps.split_pattern_id(pid) == (k, code)
            seen.add(pid)
    assert len(seen) == ps.TOTAL_PATTERNS == 6831           # §3's own arithmetic


def test_pattern_label_orders_oldest_bin_first():
    # (b_{t-2}, b_{t-1}, b_t) = (D, F, U): the most recent bar is the LAST letter
    code = ps.encode_pattern([0, 1, 2])
    assert ps.pattern_label(code, 3) == "DFU"
    assert code == 0 * 9 + 1 * 3 + 2 * 1


def test_code_matrix_agrees_with_encode_pattern_cell_by_cell():
    rng = np.random.default_rng(7)
    bins = rng.integers(0, 3, size=(40, 6)).astype(np.int8)
    bins[0, 0] = -1                                          # one undefined bin
    codes = ps.code_matrix(bins, 3)
    for t in range(2, 40):
        for i in range(6):
            window = bins[t - 2 : t + 1, i]
            if (window < 0).any():
                assert codes[t, i] == -1
            else:
                assert codes[t, i] == ps.encode_pattern(list(window))
    assert (codes[:2] == -1).all()                           # not enough history


# ---------------------------------------------------------------------------
# The HAC transcription, pinned against statsmodels rather than trusted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lag", [1, 5])
def test_newey_west_matches_statsmodels_hac(lag):
    import statsmodels.api as sm

    rng = np.random.default_rng(11)
    noise = rng.standard_normal(600)
    x = 0.02 + noise + 0.6 * np.concatenate([[0.0], noise[:-1]])   # autocorrelated on purpose
    t_mine, mean_mine, se_mine = ps.newey_west_t_of_mean(x, lag)
    fitted = sm.OLS(x, np.ones(x.size)).fit(
        cov_type="HAC", cov_kwds={"maxlags": lag, "use_correction": False}
    )
    assert mean_mine == pytest.approx(float(fitted.params[0]), rel=1e-12)
    assert se_mine == pytest.approx(float(fitted.bse[0]), rel=1e-10)
    assert t_mine == pytest.approx(float(fitted.tvalues[0]), rel=1e-10)


def test_newey_west_returns_nan_rather_than_garbage_on_a_too_short_sample():
    t, mean, se = ps.newey_west_t_of_mean(np.array([0.1, 0.2]), 5)
    assert np.isnan(t) and np.isnan(se)
    assert mean == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# §7 — the scanner must recover a planted rule
# ---------------------------------------------------------------------------

def test_scanner_recovers_the_planted_uuu_rule_in_the_top_three(synthetic):
    _planted, _panel, discovery = synthetic
    planted_code = ps.encode_pattern(list(PLANTED_PATTERN))
    planted_id = ps.pattern_id(planted_code, len(PLANTED_PATTERN))

    top3 = discovery.top(3)
    hit = [p for p in discovery.patterns if p.pattern_id == planted_id]
    assert hit, "the planted pattern was not even measurable — the plant, not the scanner, failed"
    stat = hit[0]
    print(
        f"\n[§7 recovery] planted UUU: t={stat.t_stat:.3f} mean={stat.mean:.3e} "
        f"n_bars={stat.n_bars} mean_names={stat.mean_names:.1f}; "
        f"measurable={discovery.n_measurable} of {ps.TOTAL_PATTERNS}"
    )
    assert stat.t_stat >= 3.0                                # §7 "with t >= 3"
    assert stat.mean > 0.0                                   # the plant was +0.30 sigma
    assert planted_id in [p.pattern_id for p in top3]        # §7 "in the top-3 by |t|"


def test_planted_pattern_survives_the_holdout(synthetic):
    _planted, panel, discovery = synthetic
    planted_id = ps.pattern_id(ps.encode_pattern(list(PLANTED_PATTERN)), len(PLANTED_PATTERN))
    holdout = ps.run_holdout(panel, SYNTH_SPEC, discovery, charge_cost=False)
    assert planted_id in holdout.top_pattern_ids
    idx = holdout.top_pattern_ids.index(planted_id)
    t_planted = holdout.top_holdout_t[idx]
    print(f"\n[§7 holdout] planted UUU holdout t={t_planted:.3f}; book t={holdout.t_stat:.3f}")
    assert t_planted > 2.0                                   # §7 "holdout t must exceed 2"


def test_sign_flip_placebo_of_the_synthetic_panel_produces_only_chance_false_positives(synthetic):
    """§7's false-positive leg. The band is taken against the number of
    MEASURABLE patterns in this panel, not 6,831 (ADDENDUM 01 item I): a
    500-name panel cannot make most k = 8 patterns measurable, so the
    analytic expectation here is far below §7's 6,831 x 0.0027 ~ 18."""
    planted, _panel, _discovery = synthetic
    flipped = ps.build_panel(
        SYNTH_SPEC_DATES,
        [f"N{i:03d}" for i in range(SYNTH_NAMES)],
        ps.sign_flip(planted, seed=1),
    )
    result = ps.run_discovery(flipped, SYNTH_SPEC, arm=ps.ARM_P1, seed=1, horizons=(ps.HORIZON_PRIMARY,))[
        ps.HORIZON_PRIMARY
    ]
    expected_measurable = result.n_measurable * 0.0027
    expected_all_6831 = ps.TOTAL_PATTERNS * 0.0027
    print(
        f"\n[§7 false positives] P1 draw seed=1: measurable={result.n_measurable}, "
        f"|t|>=3 count={result.n_t_ge_3} (expectation {expected_measurable:.2f} on the measurable "
        f"set; §7's 6,831-pattern figure would be {expected_all_6831:.1f}), "
        f"Tmax={result.t_max_abs:.3f}"
    )
    # Generous band: chance alone, with the pattern portfolios correlated to each
    # other, should not produce many multiples of the analytic expectation.
    assert result.n_t_ge_3 <= max(10.0, 6.0 * expected_measurable)


# ---------------------------------------------------------------------------
# §5 — control non-degeneracy and seeding
# ---------------------------------------------------------------------------

def test_p1_draw_membership_is_not_degenerate_against_the_real_panel(synthetic):
    planted, panel, _discovery = synthetic
    flipped = ps.build_panel(
        SYNTH_SPEC_DATES,
        [f"N{i:03d}" for i in range(SYNTH_NAMES)],
        ps.sign_flip(planted, seed=1),
    )
    fraction, identical, union = ps.identical_membership_fraction(panel, flipped, SYNTH_SPEC)
    print(f"\n[§5 non-degeneracy] identical (pattern,date) membership cells: {identical}/{union} = {fraction:.5f}")
    assert fraction < ps.NON_DEGENERACY_MAX_IDENTICAL_FRACTION      # §5's own 5% bar
    assert union > 0


def test_placebos_are_deterministic_in_their_seed_and_differ_across_seeds():
    rng = np.random.default_rng(3)
    r = rng.standard_normal((50, 8))
    r[0, 0] = np.nan
    for transform in (ps.sign_flip, ps.time_shuffle):
        a = transform(r, 5)
        b = transform(r, 5)
        c = transform(r, 6)
        assert np.array_equal(np.isnan(a), np.isnan(r))              # history length preserved
        np.testing.assert_array_equal(np.nan_to_num(a), np.nan_to_num(b))
        assert not np.array_equal(np.nan_to_num(a), np.nan_to_num(c))


def test_sign_flip_preserves_magnitudes_and_time_shuffle_preserves_the_multiset():
    rng = np.random.default_rng(4)
    r = rng.standard_normal((60, 5))
    r[:3, 1] = np.nan
    flipped = ps.sign_flip(r, 2)
    np.testing.assert_allclose(np.abs(np.nan_to_num(flipped)), np.abs(np.nan_to_num(r)))
    shuffled = ps.time_shuffle(r, 2)
    for col in range(r.shape[1]):
        a = np.sort(r[np.isfinite(r[:, col]), col])
        b = np.sort(shuffled[np.isfinite(shuffled[:, col]), col])
        np.testing.assert_allclose(a, b)


def test_run_discovery_is_reproducible_bit_for_bit(synthetic):
    planted, _panel, discovery = synthetic
    rebuilt = ps.build_panel(SYNTH_SPEC_DATES, [f"N{i:03d}" for i in range(SYNTH_NAMES)], planted)
    again = ps.run_discovery(rebuilt, SYNTH_SPEC, horizons=(ps.HORIZON_PRIMARY,))[ps.HORIZON_PRIMARY]
    assert again.n_measurable == discovery.n_measurable
    assert again.n_t_ge_3 == discovery.n_t_ge_3
    assert again.t_max_abs == discovery.t_max_abs
    assert [p.pattern_id for p in again.top(20)] == [p.pattern_id for p in discovery.top(20)]


# ---------------------------------------------------------------------------
# §4 — the holdout is a separate call that cannot be run by accident
# ---------------------------------------------------------------------------

def test_run_holdout_refuses_without_a_discovery_result(synthetic):
    _planted, panel, discovery = synthetic
    with pytest.raises(ValueError, match="requires the discovery ScanResult"):
        ps.run_holdout(panel, SYNTH_SPEC, None)
    with pytest.raises(ValueError, match="arm"):
        ps.run_holdout(panel, SYNTH_SPEC, discovery, arm=ps.ARM_P1, seed=1)
    holdout_scan = ps.scan_window(
        panel,
        SYNTH_SPEC,
        horizon=ps.HORIZON_PRIMARY,
        window=(SYNTH_SPEC.holdout_start, SYNTH_SPEC.holdout_end),
        window_label="holdout",
        min_bars=1,
    )
    with pytest.raises(ValueError, match="not 'discovery'"):
        ps.run_holdout(panel, SYNTH_SPEC, holdout_scan)


def test_formation_mask_keeps_the_outcome_window_inside_the_window():
    mask = np.array([False, True, True, True, True, False, False])
    np.testing.assert_array_equal(
        ps._formation_mask(mask, 1), np.array([False, True, True, True, False, False, False])
    )
    np.testing.assert_array_equal(
        ps._formation_mask(mask, 3), np.array([False, True, False, False, False, False, False])
    )


def test_discovery_never_reads_a_holdout_bar(synthetic):
    """Blanking every holdout return must leave the discovery scan identical
    — the structural check behind §4's 'touched exactly once'."""
    planted, _panel, discovery = synthetic
    blanked = planted.copy()
    blanked[SYNTH_DISCOVERY_BARS:] = np.nan
    panel_b = ps.build_panel(SYNTH_SPEC_DATES, [f"N{i:03d}" for i in range(SYNTH_NAMES)], blanked)
    again = ps.run_discovery(panel_b, SYNTH_SPEC, horizons=(ps.HORIZON_PRIMARY,))[ps.HORIZON_PRIMARY]
    assert again.n_measurable == discovery.n_measurable
    assert again.t_max_abs == discovery.t_max_abs


# ---------------------------------------------------------------------------
# Gates read off mechanically (§6)
# ---------------------------------------------------------------------------

def _scan_stub(n3, tmax, arm=ps.ARM_REAL, seed=0):
    return ps.ScanResult(
        panel_key="S", arm=arm, seed=seed, horizon=1, window="discovery",
        n_formation_bars=100, n_measurable=10, n_unmeasurable=0,
        n_t_ge_3=n3, n_t_ge_4=0, t_max_abs=tmax, sigma_sr_annualized=0.1, patterns=[],
    )


def test_gate1_needs_both_legs_strictly_above_the_placebo_maximum():
    placebo = [_scan_stub(4, 3.5, ps.ARM_P1, s) for s in (1, 2)]
    assert ps.evaluate_gate1(_scan_stub(5, 3.6), placebo).passed
    assert not ps.evaluate_gate1(_scan_stub(4, 3.6), placebo).passed      # ties do not pass
    assert not ps.evaluate_gate1(_scan_stub(5, 3.5), placebo).passed
    with pytest.raises(ValueError):
        ps.evaluate_gate1(_scan_stub(5, 3.6), [])


def _holdout_stub(t, arm=ps.ARM_REAL, seed=0):
    return ps.HoldoutResult(
        panel_key="S", arm=arm, seed=seed, horizon=1, n_bars=100, n_patterns=20,
        t_stat=t, mean=0.0, sharpe_annualized=0.0, t_stat_after_cost=float("nan"),
        mean_after_cost=float("nan"), mean_turnover=float("nan"),
        top_pattern_ids=[], top_labels=[], top_signs=[], top_discovery_t=[], top_holdout_t=[],
    )


def test_gate2_needs_the_floor_and_the_envelope():
    placebo = [_holdout_stub(1.4, ps.ARM_P1, s) for s in (1, 2)]
    assert ps.evaluate_gate2(_holdout_stub(2.5), placebo).passed
    assert not ps.evaluate_gate2(_holdout_stub(1.9), placebo).passed          # below the 2.0 floor
    assert not ps.evaluate_gate2(_holdout_stub(2.5), [_holdout_stub(3.0, ps.ARM_P1, 1)]).passed
    assert not ps.evaluate_gate2(_holdout_stub(-4.0), placebo).passed         # a reversal is not a pass
