"""data/research_runs/run_expand_tsmom_universe.py -- TSMOM universe-
validation prep Step 3 ("Option 1b") -- had no test coverage. Same
convention as tests/test_combined_universe_effective_breadth.py: import the
runner by path, exercise its pure functions without a network fetch, and
re-check the persisted report's own numbers rather than trust them at face
value.

WHAT IS PINNED HERE, and why each matters:
  1. The gate decision (branch_for/branch_statement) is a pure function of
     one float, same floor (15.0) as Step 1, not re-litigated here.
  2. find_ticker_overlaps must actually catch a real overlap, not just
     return {} on the happy path forever.
  3. independent_effective_breadth must agree with cross_sectional_
     commodities.effective_breadth on synthetic data with a KNOWN true
     answer (n independent series -> n, n copies of one series -> 1).
  4. screen_redundant_candidates -- the actual redundancy discipline this
     run adds on top of Step 1 -- is exercised on synthetic data with a
     real, engineered collision (a candidate built to be 0.99-correlated
     with an existing base ticker must be excluded; an independent
     candidate must be accepted), including the two-window (full +
     recent-1260) refinement this run's own PCY/EMB finding motivated: a
     candidate whose FULL-window correlation is low but whose RECENT-
     window correlation is high must still be excluded.
  5. The four NEW_*_CANDIDATES lists must not overlap the four ORIGINAL
     family constants (BONDS_UNIVERSE, COMMODITIES_UNIVERSE, FX_PAIRS,
     COUNTRY_ETF_TICKERS) or each other -- this run is additive-only, and a
     future edit that accidentally re-admits an already-claimed ticker
     should fail loudly here.
  6. If this run's own persisted JSON is present, its headline numbers are
     re-derived from ITS OWN stored primitives, not re-trusted at face
     value: pooled AFTER breadth must be less than pooled AFTER nominal
     count, must be >= pooled BEFORE breadth is NOT asserted (adding
     correlated names does not have to raise effective breadth -- what IS
     asserted is arithmetic consistency of n and the gate/branch
     agreement), and every redundancy-excluded candidate must carry a
     measured correlation and the ticker it duplicates.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
RUNNER = BACKEND / "data" / "research_runs" / "run_expand_tsmom_universe.py"
REPORT_JSON = BACKEND / "data" / "research_runs" / "expand_tsmom_universe_2026-09-05.json"


@pytest.fixture(scope="module")
def runner():
    """Import the runner by path -- it lives under data/research_runs/, not
    app/, so it is not importable by name. Importing it executes the
    WORKTREE BINDING GUARD and the module-level imports (commodities/fx/
    bonds/country_valmom family modules) but not main(), so this is a fast,
    network-free import."""
    spec = importlib.util.spec_from_file_location("_run_expand_tsmom_universe", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


@pytest.fixture(scope="module")
def report():
    if not REPORT_JSON.is_file():
        pytest.skip(f"{REPORT_JSON.name} not present in this checkout")
    return json.loads(REPORT_JSON.read_text())


# --- 1: the gate decision, as a pure function, same floor as Step 1 --------


def test_branch_for_uses_the_same_15_floor_step1_declared(runner):
    assert runner.BREADTH_GATE_FLOOR == 15.0
    assert runner.branch_for(15.0) == "proceed"
    assert runner.branch_for(14.99) == "expand_further_or_build_futures_pipeline"
    assert runner.branch_for(0.0) == "expand_further_or_build_futures_pipeline"
    assert runner.branch_for(100.0) == "proceed"


def test_branch_statement_names_the_correct_branch_in_its_own_text(runner):
    proceed_text = runner.branch_statement(20.0)
    assert proceed_text.startswith("PROCEED")

    below_text = runner.branch_statement(8.0)
    assert below_text.startswith("STILL BELOW FLOOR")
    assert "Option 2" in below_text
    assert "not executed here" in below_text


# --- 2: ticker-overlap detection --------------------------------------------


def test_find_ticker_overlaps_is_empty_on_disjoint_universes(runner):
    assert runner.find_ticker_overlaps({"a": ["X", "Y"], "b": ["Z"]}) == {}


def test_find_ticker_overlaps_catches_a_real_collision(runner):
    overlaps = runner.find_ticker_overlaps({"bonds": ["SHY", "EMB"], "new_bonds": ["EMB", "BWX"]})
    assert overlaps == {"EMB": ["bonds", "new_bonds"]}


def test_new_candidates_do_not_overlap_the_four_original_family_constants(runner):
    """This run is additive-only: none of its NEW_*_CANDIDATES may already
    be claimed by BONDS_UNIVERSE, COMMODITIES_UNIVERSE, FX_PAIRS, or
    COUNTRY_ETF_TICKERS (the four original constants this file imports
    read-only and must never modify), or by each other."""
    from app.services.research_lab.cross_sectional_bonds import BONDS_UNIVERSE
    from app.services.research_lab.cross_sectional_commodities import (
        COMMODITIES_UNIVERSE,
    )
    from app.services.research_lab.cross_sectional_country_valmom import (
        COUNTRY_ETF_TICKERS,
    )
    from app.services.research_lab.cross_sectional_fx import FX_PAIRS

    universes = {
        "bonds": list(BONDS_UNIVERSE),
        "commodities": list(COMMODITIES_UNIVERSE),
        "fx": list(FX_PAIRS),
        "country_valmom": list(COUNTRY_ETF_TICKERS),
        "new_fx": list(runner.NEW_FX_CANDIDATES),
        "new_country": list(runner.NEW_COUNTRY_CANDIDATES),
        "new_bonds": list(runner.NEW_BONDS_CANDIDATES),
        "new_commodities": list(runner.NEW_COMMODITIES_CANDIDATES),
    }
    overlaps = runner.find_ticker_overlaps(universes)
    assert overlaps == {}


def test_original_family_constants_are_unmodified_by_this_module(runner):
    """Byte-for-byte the same objects Step 1 measured -- this run must never
    have edited BONDS_UNIVERSE/COMMODITIES_UNIVERSE/FX_PAIRS/
    COUNTRY_ETF_TICKERS, only read them."""
    from app.services.research_lab.cross_sectional_bonds import BONDS_UNIVERSE
    from app.services.research_lab.cross_sectional_commodities import (
        COMMODITIES_UNIVERSE,
    )
    from app.services.research_lab.cross_sectional_country_valmom import (
        COUNTRY_ETF_TICKERS,
    )
    from app.services.research_lab.cross_sectional_fx import FX_PAIRS

    assert tuple(BONDS_UNIVERSE) == ("SHY", "IEI", "IEF", "TLH", "TLT", "TIP", "LQD", "HYG")
    assert len(COMMODITIES_UNIVERSE) == 11
    assert len(FX_PAIRS) == 9
    assert len(COUNTRY_ETF_TICKERS) == 15


# --- 3: independent_effective_breadth on synthetic data with a KNOWN answer -


def test_independent_effective_breadth_matches_the_shared_function_on_synthetic_data(runner):
    from app.services.research_lab.cross_sectional_commodities import (
        effective_breadth,
    )

    rng = np.random.default_rng(20260905)
    dates = pd.date_range("2020-01-01", periods=500, freq="B")

    independent = pd.DataFrame(rng.normal(size=(500, 6)), index=dates, columns=list("ABCDEF"))
    eb_shared = effective_breadth(independent)
    eb_indep, n_cols = runner.independent_effective_breadth(independent)
    assert n_cols == 6
    assert eb_shared == pytest.approx(eb_indep, abs=1e-9)
    assert eb_shared == pytest.approx(6.0, abs=0.5)

    base = rng.normal(size=500)
    copies = pd.DataFrame({c: base for c in "PQRST"}, index=dates)
    eb_shared_copies = effective_breadth(copies)
    eb_indep_copies, n_cols_copies = runner.independent_effective_breadth(copies)
    assert n_cols_copies == 5
    assert eb_shared_copies == pytest.approx(1.0, abs=1e-6)
    assert eb_shared_copies == pytest.approx(eb_indep_copies, abs=1e-9)


def test_independent_effective_breadth_uses_a_genuinely_different_numpy_entry_point(runner):
    import inspect

    from app.services.research_lab import cross_sectional_commodities as cc

    shared_src = inspect.getsource(cc.effective_breadth)
    indep_src = inspect.getsource(runner.independent_effective_breadth)
    assert "np.linalg.eigvalsh(" in shared_src
    assert "np.linalg.eigh(" in indep_src
    assert "np.linalg.eigvalsh(" not in indep_src


# --- 4: the redundancy screen, on synthetic data with an engineered collision


def _synthetic_returns(rng, n_days, columns):
    dates = pd.date_range("2015-01-01", periods=n_days, freq="B")
    return {c: pd.Series(rng.normal(scale=0.01, size=n_days), index=dates) for c in columns}


def test_screen_redundant_candidates_accepts_an_independent_candidate(runner):
    rng = np.random.default_rng(1)
    base = _synthetic_returns(rng, 2000, ["X", "Y"])
    candidate = _synthetic_returns(rng, 2000, ["NEW"])  # independent draw, no engineered correlation
    accepted, decisions = runner.screen_redundant_candidates(candidate, base, ["NEW"])
    assert "NEW" in accepted
    assert decisions["NEW"]["status"] == "accepted"
    assert decisions["NEW"]["max_correlation"] < runner.EXPANSION_REDUNDANCY_CORR_LIMIT


def test_screen_redundant_candidates_excludes_an_engineered_duplicate(runner):
    rng = np.random.default_rng(2)
    dates = pd.date_range("2015-01-01", periods=2000, freq="B")
    x = pd.Series(rng.normal(scale=0.01, size=2000), index=dates)
    # DUPLICATE is 99% x plus a sliver of independent noise -- an obvious
    # "same bet wearing a second ticker", the BNO/USO shape.
    noise = pd.Series(rng.normal(scale=0.01, size=2000), index=dates)
    duplicate = 0.99 * x + 0.01 * noise
    base = {"X": x}
    candidate = {"DUPLICATE": duplicate}
    accepted, decisions = runner.screen_redundant_candidates(candidate, base, ["DUPLICATE"])
    assert "DUPLICATE" not in accepted
    assert decisions["DUPLICATE"]["status"] == "excluded_redundant"
    assert decisions["DUPLICATE"]["compared_against"] == "X"
    assert decisions["DUPLICATE"]["max_correlation"] > runner.EXPANSION_REDUNDANCY_CORR_LIMIT


def test_screen_redundant_candidates_catches_a_recent_regime_duplicate_the_full_window_misses(runner):
    """The exact shape of this run's own PCY/EMB finding: a candidate whose
    FULL-window correlation with an existing ticker is comfortably under
    the limit (because its early history is noisy/uncorrelated) but whose
    RECENT window is a near-exact duplicate must still be excluded -- this
    is what motivated using max(full, recent) rather than the full-window
    number alone."""
    rng = np.random.default_rng(3)
    n_old, n_recent = 2000, runner.RECENT_REGIME_WINDOW_TRADING_DAYS
    dates = pd.date_range("2010-01-01", periods=n_old + n_recent, freq="B")
    x = pd.Series(rng.normal(scale=0.01, size=n_old + n_recent), index=dates)

    old_part = pd.Series(rng.normal(scale=0.01, size=n_old), index=dates[:n_old])  # independent
    recent_noise = pd.Series(rng.normal(scale=0.001, size=n_recent), index=dates[n_old:])
    recent_part = 0.995 * x.iloc[n_old:] + 0.005 * recent_noise  # near-duplicate in the recent regime
    candidate_series = pd.concat([old_part, recent_part])

    base = {"X": x}
    candidate = {"LATE_DUPLICATE": candidate_series}
    accepted, decisions = runner.screen_redundant_candidates(candidate, base, ["LATE_DUPLICATE"])

    d = decisions["LATE_DUPLICATE"]
    assert d["full_window_correlation"] < runner.EXPANSION_REDUNDANCY_CORR_LIMIT, (
        "the full-window correlation should be too diluted by the independent early era to "
        "exceed the limit on its own -- otherwise this test is not exercising the refinement"
    )
    assert d["recent_window_correlation"] > runner.EXPANSION_REDUNDANCY_CORR_LIMIT
    assert d["status"] == "excluded_redundant"
    assert "LATE_DUPLICATE" not in accepted


def test_screen_redundant_candidates_flags_insufficient_overlap_rather_than_silently_accepting(runner):
    rng = np.random.default_rng(4)
    base_dates = pd.date_range("2000-01-01", periods=2000, freq="B")
    candidate_dates = pd.date_range("2023-01-01", periods=50, freq="B")  # barely overlaps `base`
    base = {"OLD": pd.Series(rng.normal(size=2000), index=base_dates)}
    candidate = {"TOO_SHORT": pd.Series(rng.normal(size=50), index=candidate_dates)}
    accepted, decisions = runner.screen_redundant_candidates(
        candidate, base, ["TOO_SHORT"], min_overlap_days=250
    )
    assert decisions["TOO_SHORT"]["status"] == "accepted_untested_insufficient_overlap"
    assert "TOO_SHORT" in accepted  # accepted, but explicitly flagged as untested, not silently passed


# --- 5: the persisted run's own numbers, re-checked rather than re-trusted -


def test_pooled_after_breadth_is_below_pooled_after_nominal_count(report):
    pooled = report["pooled"]
    assert pooled["effective_breadth_after"] < pooled["n_nominal_after"]


def test_pooled_nominal_counts_are_arithmetically_consistent_with_accepted_candidates(report):
    """43 (Step 1's pooled nominal count) plus the number of ACCEPTED (not
    excluded) candidates across all four categories must equal the
    persisted pooled AFTER nominal count -- catches a silent mismatch
    between what the redundancy screen decided and what the report says
    was actually pooled."""
    pooled = report["pooled"]
    assert pooled["n_nominal_before"] == 43
    n_accepted = 0
    for category_decisions in report["candidate_decisions"].values():
        for decision in category_decisions.values():
            if decision["status"] != "excluded_redundant":
                n_accepted += 1
    assert pooled["n_nominal_after"] == pooled["n_nominal_before"] + n_accepted
    assert pooled["n_new_accepted"] == n_accepted


def test_the_persisted_branch_matches_branch_for_on_the_persisted_number(runner, report):
    pooled_eb_after = report["pooled"]["effective_breadth_after"]
    assert report["branch"] == runner.branch_for(pooled_eb_after)
    assert report["branch_statement"] == runner.branch_statement(pooled_eb_after)


def test_independent_verification_deltas_are_inside_the_declared_tolerance(report):
    v = report["verification"]
    assert v["worst_delta_any_call"] < v["tolerance"]
    for category, cat_report in report["per_category"].items():
        assert cat_report["independent_verification_delta_before"] < v["tolerance"], category
        assert cat_report["independent_verification_delta_after"] < v["tolerance"], category


def test_no_ticker_overlap_was_found_in_the_persisted_run(report):
    assert report["ticker_overlaps"] == {}


def test_every_excluded_redundant_candidate_carries_its_measured_correlation_and_duplicate(report):
    for category_decisions in report["candidate_decisions"].values():
        for ticker, d in category_decisions.items():
            if d["status"] == "excluded_redundant":
                assert d["compared_against"], f"{ticker}: excluded with no recorded duplicate"
                assert d["max_correlation"] is not None, f"{ticker}: excluded with no recorded correlation"
                assert d["max_correlation"] > report["redundancy_discipline"]["corr_limit"], ticker


def test_step1_reproduction_check_passed_in_the_persisted_run(report):
    """This run's own recomputation of the four ORIGINAL (pre-expansion)
    per-category and pooled numbers must match Step 1's persisted numbers
    within the declared tolerance -- otherwise something about the loaders
    or underlying data drifted between the two runs and the AFTER numbers
    would not be measured on the same baseline Step 1 reported."""
    s1 = report["step1_reproduction_check"]
    assert s1["reproduced_within_tolerance"] is True
    for label, delta in s1["deltas"].items():
        assert delta <= s1["tolerance"], f"{label}: {delta} exceeds {s1['tolerance']}"


def test_the_pcy_finding_is_reflected_in_the_persisted_decision(report):
    """The specific, real finding that motivated the two-window redundancy
    refinement (PCY's thin pre-2013 trading depresses its full-window
    correlation with EMB well below its true, current-regime correlation)
    must actually show up in the persisted decision record, not just in
    the module docstring's prose."""
    bonds_decisions = report["candidate_decisions"]["bonds"]
    assert "PCY" in bonds_decisions
    pcy = bonds_decisions["PCY"]
    assert pcy["status"] == "excluded_redundant"
    assert pcy["full_window_correlation"] < report["redundancy_discipline"]["corr_limit"], (
        "the full-window correlation for PCY should itself be UNDER the limit -- the whole point "
        "of the finding is that the full-window number alone would have wrongly accepted it"
    )
    assert pcy["recent_window_correlation"] > report["redundancy_discipline"]["corr_limit"]
