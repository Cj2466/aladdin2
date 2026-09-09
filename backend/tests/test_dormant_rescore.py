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


def test_every_persisted_family_is_either_rescorable_or_explicitly_not(rescore):
    # The family list the criteria audit read from the live DB on 2026-09-09.
    csv = SCRIPT.parents[1] / "criteria_audit_2026-09-09" / "family_power.csv"
    persisted = {line.split(",")[0] for line in csv.read_text().splitlines()[1:] if line.strip()}
    keys = set(rescore.rescore_registry(date(2026, 9, 9)))
    unaccounted = sorted(persisted - keys - set(rescore.NOT_RESCORABLE))
    assert unaccounted == [], unaccounted
    for new in ("quarter_end_marking", "tax_loss_selling_turn_of_year", "rebalancing_pressure",
                "dividend_payment_pressure", "margin_credit", "ipo_lockup_expiration"):
        assert new in keys


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


def test_hub_arm_gate_records_only_the_main_replay(rescore):
    """The shared-harness arm trap (2026-09-09): a family whose sensitivity
    function replays the whole grid again must NOT have those replays recorded
    over the main replay. Exercised on a synthetic module so no data is needed:
    inside the gated function the module's harness binding is the UNHOOKED
    original; outside it is the hub wrapper again, even if the arm raises."""
    import types

    calls: list[str] = []

    def unhooked(spec):
        calls.append(f"unhooked:{spec}")
        return spec

    def hooked(spec):
        calls.append(f"hooked:{spec}")
        return spec

    fake = types.ModuleType("fake_family")
    fake.run_cross_sectional_backtest = hooked

    def _sensitivity_arm(multiplier, boom=False):
        out = fake.run_cross_sectional_backtest(f"arm{multiplier}")
        if boom:
            raise ValueError("arm failed")
        return out

    fake._sensitivity_arm = _sensitivity_arm
    n_patched_before = len(rescore.gen._PATCHED)
    rescore._wrap_hub_arm_gate(fake, "_sensitivity_arm", unhooked)
    assert len(rescore.gen._PATCHED) == n_patched_before + 1

    fake.run_cross_sectional_backtest("main")  # the main replay: hub wrapper
    assert fake._sensitivity_arm(2.0) == "arm2.0"
    fake.run_cross_sectional_backtest("main2")
    with pytest.raises(ValueError):
        fake._sensitivity_arm(0.0, boom=True)
    fake.run_cross_sectional_backtest("main3")

    assert calls == ["hooked:main", "unhooked:arm2.0", "hooked:main2", "unhooked:arm0.0", "hooked:main3"]
    assert fake.run_cross_sectional_backtest is hooked
    rescore.gen._PATCHED.pop()


def test_the_two_shared_harness_arm_families_are_gated(rescore):
    """Pins the gate table to the two functions that actually re-replay the grid
    (qem._cost_arm, tls._sensitivity_arm) and checks both still exist by name."""
    import importlib

    assert dict(rescore._HUB_ARM_GATES) == {
        "cross_sectional_quarter_end_marking": "_cost_arm",
        "cross_sectional_tax_loss_selling": "_sensitivity_arm",
    }
    for mod_name, fn_name in rescore._HUB_ARM_GATES:
        module = importlib.import_module(f"app.services.research_lab.{mod_name}")
        assert callable(getattr(module, fn_name))


def test_known_reproducibility_gaps_is_empty_after_the_root_cause_fix(rescore):
    assert rescore.KNOWN_REPRODUCIBILITY_GAPS == {}
