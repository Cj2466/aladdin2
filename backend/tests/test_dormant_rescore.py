"""dormant_rescore.py: the pure scoring/persist logic and the invocation
table's coverage. The family runs themselves need network/data and are
exercised by the --demo record committed alongside, not here."""

import importlib.util
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.dormant_pool import BUCKET_LOW, C_K, K_MAX, DormantEntry

SCRIPT = Path(__file__).resolve().parents[1] / "data" / "research_runs" / "dormant_pool_2026-09-09" / "dormant_rescore.py"


@pytest.fixture(scope="module")
def rescore():
    spec = importlib.util.spec_from_file_location("dormant_rescore", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses under `from __future__ import annotations` resolve their
    # string annotations through sys.modules[cls.__module__]; a module loaded
    # from a path must be registered there first or the decorator sees None.
    sys.modules["dormant_rescore"] = mod
    spec.loader.exec_module(mod)
    return mod


def _entry(window_end="2026-06-30", ppy=252.0) -> DormantEntry:
    return DormantEntry(
        family_key="synthetic_family", pattern_id="syn_h63",
        spec_fingerprint="a" * 64, config_fingerprint="b" * 64,
        window_end_at_entry=date.fromisoformat(window_end), entered_at=date(2026, 9, 9),
        periods_per_year=ppy, phi_hat_entry=0.01, bucket=BUCKET_LOW, pit_ok=True, rescorable=True,
        mechanism_review="fixture", entry_rationale="fixture",
    )


def _series(n_pre=2900, n_ext=300, mean=0.0003, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-06-30", periods=n_pre).append(pd.bdate_range(start="2026-07-01", periods=n_ext))
    return pd.Series(rng.standard_normal(len(idx)) * 0.01 + mean, index=idx)


def test_the_invocation_table_covers_every_family_the_effective_n_run_could_reach(rescore):
    keys = set(rescore.rescore_registry(date(2026, 9, 9)))
    meta = json.loads((SCRIPT.parents[1] / "global_effective_n_return_matrix_2026-09-05.meta.json").read_text())
    reached = {f["family_key"] for f in meta["families"]}
    assert reached <= keys, sorted(reached - keys)
    assert "phase_a_intraday_expanded" in rescore.NOT_RESCORABLE


def test_score_splits_at_window_end_and_scores_only_the_extension(rescore):
    s = _series(n_ext=300)
    rec = rescore.score_series(s, _entry(), persisted_sharpe=None, data_end=date(2026, 9, 9), now=datetime(2026, 9, 9, tzinfo=UTC))
    assert rec.n_pre_entry == 2900 and rec.n_extension == 300
    assert rec.look_index == 1  # 300 >= 252
    assert rec.psr_ext is not None and rec.boundary == C_K[BUCKET_LOW]
    assert rec.k_max == K_MAX
    assert rec.pre_entry_drift is None and rec.pre_entry_drift_flagged is False


def test_no_look_before_a_year_of_extension(rescore):
    rec = rescore.score_series(_series(n_ext=100), _entry(), persisted_sharpe=None, data_end=date(2026, 9, 9))
    assert rec.look_index == 0 and rec.promoted is False and "no look due" in rec.note


def test_pre_entry_drift_is_measured_against_the_persisted_sharpe_and_flagged(rescore):
    s = _series()
    from app.services.research_lab import metrics

    pre_sharpe = metrics.sharpe_ratio(s[s.index <= pd.Timestamp("2026-06-30")])
    ok = rescore.score_series(s, _entry(), persisted_sharpe=pre_sharpe + 0.02, data_end=date(2026, 9, 9))
    assert ok.pre_entry_drift == pytest.approx(-0.02) and ok.pre_entry_drift_flagged is False
    bad = rescore.score_series(s, _entry(), persisted_sharpe=pre_sharpe + 0.5, data_end=date(2026, 9, 9))
    assert bad.pre_entry_drift_flagged is True and "PRE-ENTRY DRIFT" in bad.note


def test_persist_writes_a_json_record_and_appends_the_log(rescore, tmp_path):
    rec = rescore.score_series(_series(), _entry(), persisted_sharpe=None, data_end=date(2026, 9, 9), demo=True,
                               now=datetime(2026, 9, 9, tzinfo=UTC))
    path = rescore.persist(rec, looks_dir=tmp_path / "looks", log_path=tmp_path / "log.jsonl")
    assert path.name == "synthetic_family__syn_h63__2026-09-09__demo.json"
    payload = json.loads(path.read_text())
    assert payload["schema"] == "dormant_pool_look/v1" and payload["demo"] is True
    assert len((tmp_path / "log.jsonl").read_text().splitlines()) == 1
