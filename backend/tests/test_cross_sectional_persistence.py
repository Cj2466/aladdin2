import logging
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.cross_sectional_trial_result import CrossSectionalTrialResult
from app.services.research_lab.cross_sectional_persistence import (
    describe_configured_database,
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
    warn_if_database_is_worktree_local,
)
from app.services.research_lab.deflated_sharpe import DeflatedSharpeResult


def _session(test_db_engine):
    return sessionmaker(bind=test_db_engine)()


def _deflated(dsr=0.62, psr=0.71, n_trials=15):
    """A minimal, real DeflatedSharpeResult -- not every field matters to
    this module, but every field must exist since persist_* reads the
    object by attribute, not by dict key."""
    return DeflatedSharpeResult(
        sharpe_net_annualized=0.8,
        sharpe_net_daily=0.05,
        n_observations=504,
        skewness=0.1,
        kurtosis=3.2,
        psr_vs_zero=psr,
        n_trials=n_trials,
        sigma_sr_annualized=0.3,
        expected_max_sharpe_noise_annualized=0.4,
        dsr=dsr,
        dsr_floor_met=True,
        interpretation="test fixture",
    )


@dataclass
class _PatternIdStyleResult:
    """Mirrors CrossSectionalScreeningResult's shape (the one ~8+ families
    share via import) without pulling in a full CrossSectionalConfig/replay
    -- exactly the shape persist_cross_sectional_trial_results is meant to
    accept, built directly rather than through a full backtest."""

    pattern_id: str
    family: str
    n_trading_days: int
    sharpe_annualized: float
    deflated_sharpe: DeflatedSharpeResult
    total_cost_drag: float = 0.01


@dataclass
class _SpecIdStyleResult:
    """Mirrors CrpScreeningResult/VolRegimeScreeningResult's shape."""

    spec_id: str
    n_trading_days: int
    sharpe_annualized: float
    deflated_sharpe: DeflatedSharpeResult


@dataclass
class _WrongShapeResult:
    """Neither spec_id nor pattern_id -- must be rejected loudly, not
    silently mapped to something wrong."""

    weird_id: str
    sharpe_annualized: float
    n_trading_days: int
    deflated_sharpe: DeflatedSharpeResult


def test_persists_pattern_id_style_result(test_db_engine):
    db = _session(test_db_engine)
    r = _PatternIdStyleResult(
        pattern_id="buyback_lookback60_h21",
        family="buyback",
        n_trading_days=2172,
        sharpe_annualized=0.17,
        deflated_sharpe=_deflated(dsr=0.34),
    )
    n = persist_cross_sectional_trial_results(db, "buyback", [r], run_tag="unit_test")
    assert n == 1

    row = db.query(CrossSectionalTrialResult).one()
    assert row.family_key == "buyback"
    assert row.trial_id == "buyback_lookback60_h21"
    assert row.run_tag == "unit_test"
    assert row.sharpe_annualized == pytest.approx(0.17)
    assert row.n_observations == 2172
    assert row.n_trials == 15
    assert row.dsr == pytest.approx(0.34)
    assert row.psr_vs_zero == pytest.approx(0.71)
    assert '"pattern_id": "buyback_lookback60_h21"' in row.full_result_json
    assert '"family": "buyback"' in row.full_result_json


def test_persists_spec_id_style_result(test_db_engine):
    db = _session(test_db_engine)
    r = _SpecIdStyleResult(
        spec_id="crp_crp_3m_h5",
        n_trading_days=4934,
        sharpe_annualized=0.28,
        deflated_sharpe=_deflated(dsr=0.28, n_trials=15),
    )
    n = persist_cross_sectional_trial_results(
        db, "correlation_risk_premium", [r], run_tag="unit_test"
    )
    assert n == 1
    row = db.query(CrossSectionalTrialResult).one()
    assert row.trial_id == "crp_crp_3m_h5"
    assert row.family_key == "correlation_risk_premium"


def test_persists_multiple_results_in_one_call(test_db_engine):
    db = _session(test_db_engine)
    results = [
        _SpecIdStyleResult(
            spec_id=f"spec_{i}",
            n_trading_days=1000 + i,
            sharpe_annualized=0.1 * i,
            deflated_sharpe=_deflated(dsr=0.1 * i),
        )
        for i in range(5)
    ]
    n = persist_cross_sectional_trial_results(db, "vol_regime", results, run_tag="unit_test")
    assert n == 5
    assert db.query(CrossSectionalTrialResult).count() == 5


def test_dsr_and_psr_survive_as_none_when_deflated_sharpe_has_none(test_db_engine):
    """Below MIN_TRIALS_FOR_DSR, DeflatedSharpeResult.dsr is legitimately
    None -- persisting must preserve that, not coerce it to 0.0 or crash."""
    db = _session(test_db_engine)
    deflated = _deflated()
    deflated.dsr = None
    deflated.psr_vs_zero = None
    r = _SpecIdStyleResult(
        spec_id="thin_family_spec",
        n_trading_days=500,
        sharpe_annualized=0.4,
        deflated_sharpe=deflated,
    )
    persist_cross_sectional_trial_results(db, "some_family", [r], run_tag="unit_test")
    row = db.query(CrossSectionalTrialResult).one()
    assert row.dsr is None
    assert row.psr_vs_zero is None


def test_missing_run_tag_raises(test_db_engine):
    db = _session(test_db_engine)
    r = _SpecIdStyleResult(
        spec_id="x", n_trading_days=100, sharpe_annualized=0.1, deflated_sharpe=_deflated()
    )
    with pytest.raises(ValueError, match="run_tag"):
        persist_cross_sectional_trial_results(db, "family", [r], run_tag="")


def test_empty_results_raises_rather_than_silently_no_opping(test_db_engine):
    db = _session(test_db_engine)
    with pytest.raises(ValueError, match="zero results"):
        persist_cross_sectional_trial_results(db, "family", [], run_tag="unit_test")


def test_unrecognized_result_shape_raises_rather_than_silently_mismapping(test_db_engine):
    db = _session(test_db_engine)
    r = _WrongShapeResult(
        weird_id="x", sharpe_annualized=0.1, n_trading_days=100, deflated_sharpe=_deflated()
    )
    with pytest.raises(ValueError, match="spec_id.*pattern_id"):
        persist_cross_sectional_trial_results(db, "family", [r], run_tag="unit_test")


def test_missing_deflated_sharpe_raises(test_db_engine):
    @dataclass
    class _NoDeflated:
        spec_id: str
        sharpe_annualized: float
        n_trading_days: int

    db = _session(test_db_engine)
    r = _NoDeflated(spec_id="x", sharpe_annualized=0.1, n_trading_days=100)
    with pytest.raises(ValueError, match="deflated_sharpe"):
        persist_cross_sectional_trial_results(db, "family", [r], run_tag="unit_test")


def test_full_result_json_round_trips_family_specific_fields(test_db_engine):
    """The JSON blob must carry fields that only exist on ONE family's
    dataclass (total_cost_drag here), proving this isn't just re-storing
    the four typed columns twice."""
    import json

    db = _session(test_db_engine)
    r = _PatternIdStyleResult(
        pattern_id="p1",
        family="round_c",
        n_trading_days=2923,
        sharpe_annualized=-0.09,
        deflated_sharpe=_deflated(),
        total_cost_drag=0.0234,
    )
    persist_cross_sectional_trial_results(db, "round_c", [r], run_tag="unit_test")
    row = db.query(CrossSectionalTrialResult).one()
    payload = json.loads(row.full_result_json)
    assert payload["total_cost_drag"] == pytest.approx(0.0234)
    assert payload["deflated_sharpe"]["n_trials"] == 15


# ---------------------------------------------------------------------------
# verify_persisted_trial_results -- the read-back check a research runner
# calls so "the reports are committed but the rows are not" fails loudly at
# the end of the run instead of being discovered a day later.
# ---------------------------------------------------------------------------


def _write(db, family_key, n, run_tag):
    results = [
        _SpecIdStyleResult(
            spec_id=f"{family_key}_{i}",
            n_trading_days=500,
            sharpe_annualized=0.1 * i,
            deflated_sharpe=_deflated(),
        )
        for i in range(n)
    ]
    return persist_cross_sectional_trial_results(db, family_key, results, run_tag=run_tag)


def test_verify_returns_the_row_count_when_the_write_landed(test_db_engine):
    db = _session(test_db_engine)
    written = _write(db, "fam_a", 3, "run_ok")
    assert verify_persisted_trial_results(db, "run_ok", written) == 3


def test_verify_raises_when_rows_are_missing(test_db_engine):
    """The failure this exists for: the runner believes it wrote N rows and
    the database has fewer (or none)."""
    db = _session(test_db_engine)
    _write(db, "fam_a", 2, "run_short")
    with pytest.raises(RuntimeError, match="PERSISTENCE CHECK FAILED"):
        verify_persisted_trial_results(db, "run_short", 5)


def test_verify_raises_when_the_run_tag_never_reached_the_database(test_db_engine):
    db = _session(test_db_engine)
    _write(db, "fam_a", 2, "some_other_run")
    with pytest.raises(RuntimeError, match="read back 0"):
        verify_persisted_trial_results(db, "the_run_that_did_not_land", 2)


def test_verify_counts_only_this_run_tag(test_db_engine):
    """An earlier run's rows must not paper over a current run that wrote
    nothing -- the count is scoped to the run_tag, never the whole table."""
    db = _session(test_db_engine)
    _write(db, "fam_a", 4, "old_run")
    written = _write(db, "fam_a", 2, "new_run")
    assert verify_persisted_trial_results(db, "new_run", written) == 2


def test_verify_can_be_scoped_to_one_family_key(test_db_engine):
    """Some runners write several family keys under one run_tag; passing
    family_key checks just that family's share."""
    db = _session(test_db_engine)
    _write(db, "fam_a", 3, "multi")
    _write(db, "fam_b", 2, "multi")
    assert verify_persisted_trial_results(db, "multi", 3, family_key="fam_a") == 3
    assert verify_persisted_trial_results(db, "multi", 2, family_key="fam_b") == 2
    assert verify_persisted_trial_results(db, "multi", 5) == 5


def test_verify_refuses_a_zero_expectation(test_db_engine):
    """Verifying "I expected 0 and got 0" against an empty database would
    report success for a run that persisted nothing."""
    db = _session(test_db_engine)
    with pytest.raises(ValueError, match="expected_rows=0"):
        verify_persisted_trial_results(db, "run", 0)


def test_describe_configured_database_shows_a_sqlite_path_but_redacts_postgres(monkeypatch):
    """Which aladdin2.db received the rows is the whole point, so a sqlite
    URL is shown in full. A Postgres URL carries credentials, so only its
    scheme is."""
    from app.config import settings as live_settings

    monkeypatch.setattr(live_settings, "database_url", "sqlite:////tmp/x/aladdin2.db")
    assert describe_configured_database() == "sqlite:////tmp/x/aladdin2.db"

    monkeypatch.setattr(live_settings, "database_url", "postgresql+psycopg://u:secret@h/db")
    described = describe_configured_database()
    assert described == "postgresql+psycopg://<redacted>"
    assert "secret" not in described


def test_worktree_local_database_is_flagged(monkeypatch, caplog):
    """The failure a row-count check CANNOT see: the rows are really there,
    in a database that disappears with the worktree."""
    from app.config import settings as live_settings

    monkeypatch.setattr(
        live_settings,
        "database_url",
        "sqlite:////repo/.claude/worktrees/some-branch/backend/aladdin2.db",
    )
    with caplog.at_level(logging.WARNING):
        assert warn_if_database_is_worktree_local() is True
    assert "WORKTREE-LOCAL DATABASE" in caplog.text


def test_main_checkout_database_is_not_flagged(monkeypatch):
    from app.config import settings as live_settings

    monkeypatch.setattr(live_settings, "database_url", "sqlite:////repo/backend/aladdin2.db")
    assert warn_if_database_is_worktree_local() is False


def test_postgres_is_never_flagged_as_worktree_local(monkeypatch):
    from app.config import settings as live_settings

    monkeypatch.setattr(live_settings, "database_url", "postgresql+psycopg://u:p@h/db")
    assert warn_if_database_is_worktree_local() is False
