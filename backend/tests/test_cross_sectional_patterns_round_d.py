import pytest

from app.services.research_lab.cross_sectional_patterns import ROUND_C_FAMILY
from app.services.research_lab.cross_sectional_patterns_round_d import (
    LPS_INTRADAY_ONLY_PATTERN_IDS,
    ROUND_D_LPS_INTRADAY_FAMILY,
    select_intraday_only_from_round_c,
)

# The exact, hand-enumerated 6 pattern_ids this family must contain and no
# others — LPS_LOOKBACK_DAYS (21, 63, 252) x LPS_HOLDING_DAYS (21, 63) from
# cross_sectional_patterns.py, component="intraday" only. Spelled out
# literally here (not derived from the same LPS_LOOKBACK_DAYS/
# LPS_HOLDING_DAYS constants the family itself is built from) so this test
# would actually catch a mistake in the family-building loop, not just
# echo it back.
EXPECTED_PATTERN_IDS = {
    "lps_intraday_l21_h21",
    "lps_intraday_l21_h63",
    "lps_intraday_l63_h21",
    "lps_intraday_l63_h63",
    "lps_intraday_l252_h21",
    "lps_intraday_l252_h63",
}


# --- family shape: exactly these 6, no more, no fewer ---------------------


def test_family_is_exactly_6_definitions():
    assert len(ROUND_D_LPS_INTRADAY_FAMILY) == 6
    assert LPS_INTRADAY_ONLY_PATTERN_IDS == EXPECTED_PATTERN_IDS


def test_family_pattern_ids_are_exactly_the_expected_6_and_no_others():
    ids = {s.pattern_id for s in ROUND_D_LPS_INTRADAY_FAMILY}
    assert ids == EXPECTED_PATTERN_IDS
    # No duplicates collapsed the set comparison above.
    assert len([s.pattern_id for s in ROUND_D_LPS_INTRADAY_FAMILY]) == 6


def test_family_contains_no_overnight_component_siblings():
    for spec in ROUND_D_LPS_INTRADAY_FAMILY:
        assert "overnight" not in spec.pattern_id
        assert "intraday" in spec.pattern_id


def test_family_matches_round_c_intraday_subset_exactly():
    """Re-derives the expected set from ROUND_C_FAMILY itself (the family
    Round D's 6 are a strict subset of) rather than trusting only the
    hand-typed literal above — an independent cross-check that the subset
    relationship documented in the module docstring actually holds against
    the real Round C data."""
    round_c_intraday_ids = {
        s.pattern_id
        for s in ROUND_C_FAMILY
        if s.family == "overnight_intraday_tug_of_war" and s.pattern_id.startswith("lps_intraday_")
    }
    round_c_overnight_ids = {
        s.pattern_id
        for s in ROUND_C_FAMILY
        if s.family == "overnight_intraday_tug_of_war" and s.pattern_id.startswith("lps_overnight_")
    }
    assert len(round_c_intraday_ids) == 6
    assert len(round_c_overnight_ids) == 6

    round_d_ids = {s.pattern_id for s in ROUND_D_LPS_INTRADAY_FAMILY}
    assert round_d_ids == round_c_intraday_ids
    assert round_d_ids.isdisjoint(round_c_overnight_ids)


def test_family_definitions_are_unique_and_cited():
    ids = [s.pattern_id for s in ROUND_D_LPS_INTRADAY_FAMILY]
    assert len(set(ids)) == len(ids)
    for spec in ROUND_D_LPS_INTRADAY_FAMILY:
        assert spec.citation  # every definition traces to a real source
        assert "Lou" in spec.citation and "Polk" in spec.citation and "Skouras" in spec.citation
        assert spec.holding_days > 0
        assert spec.lookback_days > 0
        assert spec.rank_fraction == pytest.approx(0.1)


def test_family_declares_open_required_and_not_volume():
    for spec in ROUND_D_LPS_INTRADAY_FAMILY:
        assert spec.requires_open
        assert not spec.requires_volume


def test_family_is_all_long_short_decile_portfolios():
    for spec in ROUND_D_LPS_INTRADAY_FAMILY:
        assert spec.portfolio == "long_short"
        assert spec.family == "lps_intraday_only"


def test_family_covers_the_full_lookback_x_horizon_grid():
    pairs = {(s.pattern_id.split("_l")[1].split("_h")[0], s.holding_days) for s in ROUND_D_LPS_INTRADAY_FAMILY}
    lookbacks = {int(lb) for lb, _h in pairs}
    horizons = {h for _lb, h in pairs}
    assert lookbacks == {21, 63, 252}
    assert horizons == {21, 63}
    assert len(pairs) == 6  # the full 3x2 grid, no gaps and no duplicates


# --- select_intraday_only_from_round_c: a pure filter, never a re-screen --


class _FakeDeflatedSharpe:
    def __init__(self, n_trials, sigma_sr_annualized=0.4, dsr=0.5):
        self.n_trials = n_trials
        self.sigma_sr_annualized = sigma_sr_annualized
        self.dsr = dsr


class _FakeResult:
    """Stand-in for CrossSectionalScreeningResult carrying just the fields
    the filter and these tests touch."""

    def __init__(self, pattern_id, n_trials=30):
        self.pattern_id = pattern_id
        self.deflated_sharpe = _FakeDeflatedSharpe(n_trials=n_trials)


def test_select_intraday_only_from_round_c_filters_to_exactly_the_6_ids():
    round_c_results = [_FakeResult(pid) for pid in sorted(EXPECTED_PATTERN_IDS)] + [
        _FakeResult("lps_overnight_l21_h21"),
        _FakeResult("cs_52w_high_nearness"),
    ]
    selected = select_intraday_only_from_round_c(round_c_results)
    assert {r.pattern_id for r in selected} == EXPECTED_PATTERN_IDS


def test_select_intraday_only_from_round_c_does_not_alter_n_trials():
    """The load-bearing assertion this fix was made for: filtering down to
    the interesting 6 must NEVER change n_trials away from Round C's real,
    honest 30 — that is precisely the improper trial-count shrinkage this
    module used to perform and was rewritten to stop doing."""
    round_c_results = [_FakeResult(pid, n_trials=30) for pid in EXPECTED_PATTERN_IDS]
    selected = select_intraday_only_from_round_c(round_c_results)
    assert len(selected) == 6
    for r in selected:
        assert r.deflated_sharpe.n_trials == 30


def test_select_intraday_only_from_round_c_is_a_pure_filter_not_a_recompute():
    """Same object identity in and out — proves no new DeflatedSharpeResult
    is constructed anywhere in this path."""
    original = [_FakeResult(pid) for pid in EXPECTED_PATTERN_IDS]
    selected = select_intraday_only_from_round_c(original)
    by_id = {r.pattern_id: r for r in original}
    for r in selected:
        assert r is by_id[r.pattern_id]


def test_select_intraday_only_from_round_c_handles_empty_input():
    assert select_intraday_only_from_round_c([]) == []


def test_select_intraday_only_from_round_c_handles_no_matches():
    round_c_results = [_FakeResult("lps_overnight_l21_h21"), _FakeResult("cs_52w_high_nearness")]
    assert select_intraday_only_from_round_c(round_c_results) == []
