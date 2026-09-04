"""The pooled-N runner's dated-artifact and merge contracts.

data/research_runs/run_global_effective_n.py had no test coverage at all, and
two of its properties are now load-bearing rather than incidental:

  1. RE-RUNNING IT MUST NOT OVERWRITE AN EARLIER RUN'S ARTIFACTS. The pooled
     matrix, cluster report and DSR before/after table are the persisted
     evidence behind figures already quoted in commit messages, registration
     corrections and the dependency manifest. Until 2026-09-05 every path was
     a hardcoded 2026-09-04 literal, so a second run silently rewrote the
     first one's files under the first one's names.

  2. THE MERGE MUST PRESERVE COLUMN ORDER. --only <family> re-screens one
     family and carries the rest forward, and plain dict insertion order
     appends the re-run family's columns at the END. stage_cluster's
     estimator is k-means, whose initialization draws from the rows of the
     feature matrix, so a permuted column order is a different starting point
     for the same seed -- and a re-cluster would then differ for two reasons
     at once, with no way to attribute the change.

Both are cheap to get wrong silently and neither shows up in any number the
run itself prints, which is why they are pinned here.
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
RUNNER = BACKEND / "data" / "research_runs" / "run_global_effective_n.py"


@pytest.fixture(scope="module")
def runner():
    """Import the runner by path. It lives under data/research_runs/ rather
    than in app/, so it is not importable by name."""
    spec = importlib.util.spec_from_file_location("_run_global_effective_n", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


# --- 1: dated artifacts ------------------------------------------------------


def test_the_default_run_date_reproduces_the_original_hardcoded_paths(runner):
    """The parameterization must be a no-op for an argument-free run. Those
    four filenames and that run_tag are referenced by name from committed
    reports and from global_effective_n.json's own `report` field."""
    runner.bind_run_date(runner.DEFAULT_RUN_DATE)
    assert runner.DEFAULT_RUN_DATE == "2026-09-04"
    assert runner.RUN_TAG == "global_effective_n_2026-09-04"
    assert runner.MATRIX_PATH.name == "global_effective_n_return_matrix_2026-09-04.csv.gz"
    assert runner.META_PATH.name == "global_effective_n_return_matrix_2026-09-04.meta.json"
    assert runner.CLUSTER_REPORT_PATH.name == "global_effective_n_2026-09-04.txt"
    assert runner.CLUSTER_JSON_PATH.name == "global_effective_n_2026-09-04.json"
    assert runner.DSR_REPORT_PATH.name == "global_effective_n_dsr_before_after_2026-09-04.txt"
    assert runner.DSR_JSON_PATH.name == "global_effective_n_dsr_before_after_2026-09-04.json"


def test_a_new_run_date_moves_every_dated_path_and_the_run_tag(runner):
    """The point of the parameterization: nothing a new run writes can land on
    an old run's filename. Checked as a set so a path added later without a
    date cannot slip through."""
    try:
        runner.bind_run_date("2099-12-31")
        dated = {
            runner.MATRIX_PATH,
            runner.META_PATH,
            runner.CLUSTER_REPORT_PATH,
            runner.CLUSTER_JSON_PATH,
            runner.DSR_REPORT_PATH,
            runner.DSR_JSON_PATH,
        }
        assert len(dated) == 6, "two dated artifacts resolve to the same path"
        assert all("2099-12-31" in p.name for p in dated)
        assert runner.RUN_TAG == "global_effective_n_2099-12-31"
    finally:
        runner.bind_run_date(runner.DEFAULT_RUN_DATE)


def test_the_config_artifact_is_deliberately_not_dated(runner):
    """global_effective_n.json is the ONE path a re-run must replace --
    production reads exactly that filename. Its own run_tag/computed_at/report
    fields carry the provenance, and it is pinned in the dependency manifest so
    replacing it turns the drift test red until it is acknowledged."""
    before = runner.CONFIG_PATH
    try:
        runner.bind_run_date("2099-12-31")
        assert runner.CONFIG_PATH == before
        assert runner.CONFIG_PATH.name == "global_effective_n.json"
    finally:
        runner.bind_run_date(runner.DEFAULT_RUN_DATE)


def test_seeding_refuses_to_overwrite_this_runs_own_matrix(runner, tmp_path, monkeypatch):
    """--seed-matrix-from copies an earlier run's matrix to THIS run's paths.
    If this run already has one, copying over it would destroy whatever the run
    had already computed, so it refuses instead."""
    monkeypatch.setattr(runner, "MATRIX_PATH", tmp_path / "m.csv.gz")
    monkeypatch.setattr(runner, "META_PATH", tmp_path / "m.meta.json")
    runner.MATRIX_PATH.write_text("not empty")
    with pytest.raises(SystemExit, match="refusing to seed"):
        runner.seed_matrix_from("2026-09-04")


def test_seeding_refuses_a_source_that_does_not_exist(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "MATRIX_PATH", tmp_path / "m.csv.gz")
    monkeypatch.setattr(runner, "META_PATH", tmp_path / "m.meta.json")
    monkeypatch.setattr(runner, "OUT_DIR", tmp_path)
    with pytest.raises(SystemExit, match="cannot seed from"):
        runner.seed_matrix_from("1999-01-01")


# --- 2: the merge preserves column order -------------------------------------


def test_the_merge_puts_carried_forward_columns_back_where_they_were(runner, tmp_path, monkeypatch):
    """A re-run family's columns must land in their ORIGINAL positions, not at
    the end. Without this the clustered matrix is a permutation of the previous
    one, and k-means' seeded initialization makes a permutation a different
    experiment."""
    monkeypatch.setattr(runner, "MATRIX_PATH", tmp_path / "m.csv.gz")
    monkeypatch.setattr(runner, "META_PATH", tmp_path / "m.meta.json")

    index = pd.date_range("2020-01-01", periods=5)
    original_order = ["a", "b", "c", "d"]
    # `b` and `c` are the "re-run family", so they are built last -- exactly
    # the insertion order stage_rebuild produces.
    series = {name: pd.Series(range(5), index=index, dtype=float) for name in ("a", "d", "b", "c")}

    runner._write_matrix(series, {}, [], {}, 0.0, original_order)
    written = pd.read_csv(runner.MATRIX_PATH, index_col=0, parse_dates=True, compression="gzip")
    assert list(written.columns) == original_order

    # ... and with no order given, insertion order stands (the from-scratch
    # run, which has no previous matrix to agree with).
    runner._write_matrix(series, {}, [], {}, 0.0, None)
    written = pd.read_csv(runner.MATRIX_PATH, index_col=0, parse_dates=True, compression="gzip")
    assert list(written.columns) == ["a", "d", "b", "c"]


def test_a_genuinely_new_column_is_appended_rather_than_dropped(runner, tmp_path, monkeypatch):
    """Order preservation must not become a filter: a spec that did not exist
    in the previous matrix has to survive the merge."""
    monkeypatch.setattr(runner, "MATRIX_PATH", tmp_path / "m.csv.gz")
    monkeypatch.setattr(runner, "META_PATH", tmp_path / "m.meta.json")

    index = pd.date_range("2020-01-01", periods=5)
    series = {n: pd.Series(range(5), index=index, dtype=float) for n in ("a", "b", "brand_new")}
    runner._write_matrix(series, {}, [], {}, 0.0, ["a", "b", "gone_since"])
    written = pd.read_csv(runner.MATRIX_PATH, index_col=0, parse_dates=True, compression="gzip")
    assert list(written.columns) == ["a", "b", "brand_new"]
