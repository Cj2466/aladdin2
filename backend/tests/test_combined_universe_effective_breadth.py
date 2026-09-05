"""data/research_runs/run_combined_universe_effective_breadth.py -- TSMOM
universe-validation prep Step 1 -- had no test coverage. Same convention as
tests/test_global_effective_n_runner.py (import the runner by path, exercise
its pure functions without a network fetch) and tests/test_short_interest_
borrow_composition.py (skip a persisted-artifact assertion if that artifact
is not present in this checkout, rather than re-running a multi-second data
build inside the test suite).

WHAT IS PINNED HERE, and why each matters:
  1. The gate decision (branch_for/branch_statement) is a pure function of
     one float. If BREADTH_GATE_FLOOR or the >= vs > comparison ever drifts,
     nothing else in this run would show it -- the log line and the report
     both just print whatever the function returns.
  2. find_ticker_overlaps must actually catch a real overlap, not just
     return {} on the happy path forever. A silent dedup bug here would
     double-count a ticker's variance in the pooled correlation matrix.
  3. independent_effective_breadth (numpy.linalg.eigh + hand-typed
     sum(lambda)^2/sum(lambda^2)) must agree with cross_sectional_
     commodities.effective_breadth (numpy.linalg.eigvalsh) on synthetic data
     with a KNOWN true answer -- n uncorrelated series -> n, n copies of one
     series -> 1 -- not just on whatever the live run happened to produce.
  4. The four universes' own module-level ticker lists must not overlap,
     checked directly against the real constants (no network needed) so a
     future addition to one family's basket cannot silently double-count an
     instrument already claimed by another.
  5. If this run's own persisted JSON is present, its headline numbers are
     re-derived from ITS OWN stored primitives (not re-trusted at face
     value): the pooled effective breadth must be less than the pooled
     nominal count (pooling can never manufacture independence), the
     branch_statement it persisted must match what branch_for(...) returns
     on its own persisted pooled effective breadth today, and the
     independent-verification deltas it recorded must be inside the
     tolerance it declared.
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
RUNNER = BACKEND / "data" / "research_runs" / "run_combined_universe_effective_breadth.py"
REPORT_JSON = BACKEND / "data" / "research_runs" / "combined_universe_effective_breadth_2026-09-05.json"


@pytest.fixture(scope="module")
def runner():
    """Import the runner by path -- it lives under data/research_runs/, not
    app/, so it is not importable by name. Importing it executes the
    WORKTREE BINDING GUARD and the module-level imports (commodities/fx/
    bonds/country_valmom family modules) but not main(), so this is a fast,
    network-free import."""
    spec = importlib.util.spec_from_file_location("_run_combined_universe_breadth", RUNNER)
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


# --- 1: the gate decision, as a pure function --------------------------------


def test_branch_for_is_a_pure_threshold_at_the_declared_floor(runner):
    floor = runner.BREADTH_GATE_FLOOR
    assert floor == 15.0, "the task's own gate: >= ~15 proceeds, below it expands the basket first"
    assert runner.branch_for(floor) == "proceed", "the floor itself counts as clearing it"
    assert runner.branch_for(floor - 0.01) == "expand_first"
    assert runner.branch_for(floor + 10.0) == "proceed"
    assert runner.branch_for(0.0) == "expand_first"


def test_branch_statement_names_the_correct_branch_in_its_own_text(runner):
    proceed_text = runner.branch_statement(20.0)
    assert proceed_text.startswith("PROCEED")
    assert "TSMOM" in proceed_text

    expand_text = runner.branch_statement(5.0)
    assert expand_text.startswith("EXPAND FIRST")
    assert "separate, later task" in expand_text
    assert "NOT performed by this run" in expand_text


# --- 2: ticker-overlap detection, exercised on a real collision -------------


def test_find_ticker_overlaps_is_empty_on_disjoint_universes(runner):
    assert runner.find_ticker_overlaps({"a": ["X", "Y"], "b": ["Z"]}) == {}


def test_find_ticker_overlaps_catches_a_real_collision(runner):
    overlaps = runner.find_ticker_overlaps({"bonds": ["SHY", "TLT"], "commodities": ["TLT", "GLD"]})
    assert overlaps == {"TLT": ["bonds", "commodities"]}


def test_the_four_real_universes_do_not_overlap_today(runner):
    """The actual module-level constants, not a synthetic example -- this is
    the real dedup check the task asked for, run against live imports rather
    than a fixture, so it catches a future basket edit that accidentally
    re-admits a ticker another family already claims."""
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
        "fx": list(FX_PAIRS),  # currency codes -- the columns this run pools, not raw tickers
        "country_valmom": list(COUNTRY_ETF_TICKERS),
    }
    assert runner.find_ticker_overlaps(universes) == {}
    n_nominal = sum(len(v) for v in universes.values())
    assert n_nominal == 43, "8 bonds + 11 commodities + 9 fx + 15 country_valmom"


# --- 3: independent_effective_breadth on synthetic data with a KNOWN answer -


def test_independent_effective_breadth_matches_the_shared_function_on_synthetic_data(runner):
    """cross_sectional_commodities.effective_breadth (numpy.linalg.eigvalsh)
    and this run's independent_effective_breadth (numpy.linalg.eigh, formula
    hand-typed fresh) must agree on data whose TRUE answer is known by
    construction, not just on whatever the live fetch happened to produce."""
    from app.services.research_lab.cross_sectional_commodities import (
        effective_breadth,
    )

    rng = np.random.default_rng(20260905)
    dates = pd.date_range("2020-01-01", periods=500, freq="B")

    # n=6 mutually INDEPENDENT series -> effective breadth should be ~n (6).
    independent = pd.DataFrame(rng.normal(size=(500, 6)), index=dates, columns=list("ABCDEF"))
    eb_shared = effective_breadth(independent)
    eb_indep, n_cols = runner.independent_effective_breadth(independent)
    assert n_cols == 6
    assert eb_shared == pytest.approx(eb_indep, abs=1e-9)
    assert eb_shared == pytest.approx(6.0, abs=0.5), (
        f"6 independent series should measure close to 6 effective bets, got {eb_shared}"
    )

    # n=5 EXACT COPIES of one series -> effective breadth should be exactly 1.
    base = rng.normal(size=500)
    copies = pd.DataFrame({c: base for c in "PQRST"}, index=dates)
    eb_shared_copies = effective_breadth(copies)
    eb_indep_copies, n_cols_copies = runner.independent_effective_breadth(copies)
    assert n_cols_copies == 5
    assert eb_shared_copies == pytest.approx(1.0, abs=1e-6)
    assert eb_shared_copies == pytest.approx(eb_indep_copies, abs=1e-9)


def test_independent_effective_breadth_uses_a_genuinely_different_numpy_entry_point(runner):
    """Not a re-typing of effective_breadth's own body under a new name --
    confirms the two functions call different numpy.linalg routines, which
    is what makes the cross-check independent evidence rather than the same
    computation invoked twice."""
    import inspect

    from app.services.research_lab import cross_sectional_commodities as cc

    # Compare CALLS, not raw source text -- independent_effective_breadth's
    # own docstring names "eigvalsh" for contrast, so a plain substring check
    # against the whole source (docstring included) would false-fail on its
    # own explanatory comment.
    shared_src = inspect.getsource(cc.effective_breadth)
    indep_src = inspect.getsource(runner.independent_effective_breadth)
    assert "np.linalg.eigvalsh(" in shared_src
    assert "np.linalg.eigh(" in indep_src
    assert "np.linalg.eigvalsh(" not in indep_src


# --- 4: the persisted run's own numbers, re-checked rather than re-trusted --


def test_pooled_effective_breadth_is_below_the_pooled_nominal_count(report):
    """Pooling instruments can only ever reveal how few independent bets
    they already contained -- it cannot manufacture new independence. If
    this ever failed it would mean the pooled matrix's columns were not
    actually the returns of 43 real, distinct instruments."""
    pooled = report["pooled"]
    assert pooled["effective_breadth"] < pooled["n_nominal_tickers"]
    assert pooled["n_nominal_tickers"] == 43


def test_the_persisted_branch_matches_branch_for_on_the_persisted_number(runner, report):
    """The report's own stated branch must be exactly what the pure gate
    function returns on the report's own pooled number -- not a separately
    hand-typed conclusion that could silently disagree with the code."""
    pooled_eb = report["pooled"]["effective_breadth"]
    assert report["branch"] == runner.branch_for(pooled_eb)
    assert report["branch_statement"] == runner.branch_statement(pooled_eb)


def test_independent_verification_deltas_are_inside_the_declared_tolerance(report):
    v = report["verification"]
    assert v["worst_delta_any_universe"] < v["tolerance"]
    assert v["pooled_delta"] < v["tolerance"]
    for name, u in report["per_universe"].items():
        assert u["independent_verification_delta"] < v["tolerance"], (
            f"{name}: independent re-derivation delta exceeds the declared tolerance"
        )


def test_no_ticker_overlap_was_found_in_the_persisted_run(report):
    assert report["ticker_overlaps"] == {}


def test_commodities_reproduction_gap_is_explained_and_cited(report):
    """The commodities-alone reproduction check does not silently pass or
    silently fail -- if it landed outside tolerance, the persisted report
    must carry a named explanation and at least one commit citation rather
    than an unexplained gap."""
    c = report["commodities_reproduction_check"]
    if not c["reproduced_within_tolerance"]:
        assert c["explanation_if_outside_tolerance"], (
            "reproduction missed tolerance with no recorded explanation"
        )
        assert c["explanation_citations"], "reproduction missed tolerance with no citations"
