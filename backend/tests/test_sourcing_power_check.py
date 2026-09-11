"""sourcing_power_check: a pre-build power pre-check.

No new formula is validated here (dsr_power.py's own synthetic-data
validation, tests/test_dsr_power.py, already covers the underlying power
arithmetic). What this module adds is: (1) deriving n_observations and a
project-precedent sigma_SR from periods_per_year/years_of_data, (2) reading
the DSR policy ladder through the exact same two calls every family's own
policy_d_denominators() makes, and (3) a PROCEED/DECLINE_AT_SOURCING verdict
rule. These tests check those three things, plus a real-numbers regression
against the two families that actually ran (or would have run) this check.
"""

import pytest

from app.services.research_lab.dsr_policy_n import dsr_policy_denominators
from app.services.research_lab.dsr_power import POWER_FLOOR
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.sourcing_power_check import (
    DECLINE_AT_SOURCING,
    PROCEED,
    SourcingPowerCheckError,
    sourcing_power_check,
)


def test_high_sharpe_high_frequency_long_sample_proceeds():
    """A generous claim (Sharpe 2.0, daily data, 20 years, a small grid)
    should comfortably clear POWER_FLOOR at the smallest fraction and at
    n_local -- this is the "the pre-check does not just always say no" case."""
    report = sourcing_power_check(
        claimed_sharpe_annualized=2.0,
        periods_per_year=252.0,
        years_of_data=20.0,
        n_local=5,
        bar=0.95,
        offset_fractions=(1.0, 0.5),
    )
    assert report.verdict == PROCEED
    assert report.power_at_smallest_fraction_at_n_local >= POWER_FLOOR


def test_low_sharpe_short_sample_declines():
    """A modest claim (Sharpe 0.3) on a short sample (2 years) with a large
    grid should fail to clear POWER_FLOOR even at n_local -- the
    DECLINE_AT_SOURCING case."""
    report = sourcing_power_check(
        claimed_sharpe_annualized=0.3,
        periods_per_year=252.0,
        years_of_data=2.0,
        n_local=40,
        bar=0.95,
        offset_fractions=(1.0, 0.5),
    )
    assert report.verdict == DECLINE_AT_SOURCING
    assert report.power_at_smallest_fraction_at_n_local < POWER_FLOOR


def test_ladder_rungs_match_dsr_policy_n_directly():
    """The ladder this module reports must be byte-for-byte the same list
    dsr_policy_n.dsr_policy_denominators(dsr_n_trials(n_local)) returns --
    no rung is hardcoded in sourcing_power_check.py."""
    for n_local in (5, 8, 20, 48):
        expected = tuple(dsr_policy_denominators(dsr_n_trials(n_local)))
        report = sourcing_power_check(
            claimed_sharpe_annualized=1.0,
            periods_per_year=252.0,
            years_of_data=10.0,
            n_local=n_local,
            bar=0.95,
            offset_fractions=(1.0,),
        )
        assert report.ladder == expected
        assert report.n_local_tier == dsr_n_trials(n_local)


def test_verdict_uses_smallest_fraction_at_n_local_tier():
    """Verdict must key off the SMALLEST offset fraction (the most
    conservative claim checked) at the n_local tier specifically, not at
    some other ladder rung and not at the largest fraction."""
    report = sourcing_power_check(
        claimed_sharpe_annualized=1.5,
        periods_per_year=252.0,
        years_of_data=8.0,
        n_local=10,
        bar=0.95,
        offset_fractions=(1.0, 0.5, 0.25),
    )
    assert report.smallest_fraction == 0.25
    expected_power = report.fraction_results[0.25].power_at(report.n_local_tier)
    assert report.power_at_smallest_fraction_at_n_local == expected_power
    expected_verdict = PROCEED if expected_power >= POWER_FLOOR else DECLINE_AT_SOURCING
    assert report.verdict == expected_verdict


def test_invalid_inputs_raise_rather_than_default():
    with pytest.raises(SourcingPowerCheckError):
        sourcing_power_check(1.0, 252.0, 10.0, n_local=0)
    with pytest.raises(SourcingPowerCheckError):
        sourcing_power_check(1.0, 0.0, 10.0, n_local=5)
    with pytest.raises(SourcingPowerCheckError):
        sourcing_power_check(1.0, 252.0, -1.0, n_local=5)
    with pytest.raises(SourcingPowerCheckError):
        sourcing_power_check(1.0, 252.0, 10.0, n_local=5, offset_fractions=())
    with pytest.raises(SourcingPowerCheckError):
        sourcing_power_check(1.0, 252.0, 10.0, n_local=5, offset_fractions=(0.0,))
    with pytest.raises(SourcingPowerCheckError):
        sourcing_power_check(float("nan"), 252.0, 10.0, n_local=5)


# ---------------------------------------------------------------------------
# Regression: letf_rebalancing_eod
# ---------------------------------------------------------------------------
# Inputs read directly from
# data/research_runs/letf_rebalancing_2026-09-11/power_block.json:
#   n_local = 20
#   periods_per_year_measured = 248.75109762396693
#   panel.n_sessions = 2637  (years_of_data = n_sessions / periods_per_year)
#   arms.half_tuzun.claimed_net_sharpe_annualized = 0.41468259575966804
#   arms.half_tuzun.sigma_sr_declared__bar_0.95.power_at_claimed_sharpe
#       = 0.014014885044634329  (bar 0.95, sigma_SR = sqrt(pp/n) = 0.30713367617589954)
#   dsr_ladder = [20, 43, 397, 1131]
#   PRE_REGISTERED_DECISION.declared_underpowered_in_advance = true


def test_letf_rebalancing_eod_regression_reproduces_the_recorded_decline():
    n_local = 20
    periods_per_year = 248.75109762396693
    n_sessions = 2637
    years_of_data = n_sessions / periods_per_year
    claimed_sharpe_half_tuzun = 0.41468259575966804

    report = sourcing_power_check(
        claimed_sharpe_annualized=claimed_sharpe_half_tuzun,
        periods_per_year=periods_per_year,
        years_of_data=years_of_data,
        n_local=n_local,
        bar=0.95,
        offset_fractions=(1.0,),
    )

    assert report.n_observations == n_sessions
    assert report.ladder == (20, 43, 397, 1131)

    recorded_sigma_sr = 0.30713367617589954
    assert report.sigma_sr_annualized == pytest.approx(recorded_sigma_sr, abs=1e-9)

    recorded_power = 0.014014885044634329
    power = report.fraction_results[1.0].power_at(n_local)
    # Exact reproduction is expected here: this module's n_observations
    # (years_of_data * periods_per_year, rounded, which recovers n_sessions
    # exactly) and its sigma_SR formula (sqrt(periods_per_year/n_observations))
    # are IDENTICAL to what POWER_BLOCK.md's own script used for this arm, so
    # tolerance is 0 rather than approximate -- any difference would mean a
    # real bug in this module's formula reuse, not an expected proxy gap.
    assert power == pytest.approx(recorded_power, abs=1e-12)

    assert report.verdict == DECLINE_AT_SOURCING
    assert report.power_at_smallest_fraction_at_n_local < POWER_FLOOR


# ---------------------------------------------------------------------------
# intraday_momentum_spy, run at its own PREREGISTRATION/RUN_REPORT inputs
# ---------------------------------------------------------------------------
# Inputs read from data/research_runs/intraday_momentum_spy_2026-09-09/run_output.json:
#   n_local = 8, denominators = [8, 37, 362, 1031] AS RECORDED ON 2026-09-09.
#   The ladder read live today (via dsr_policy_n.json) is [8, 43, 397, 1131]
#   -- the pooled rungs moved between 2026-09-09 and now (independently
#   confirmed: letf_rebalancing_eod's own power_block.json, written
#   2026-09-11, records [20, 43, 397, 1131] for the same pooled rungs
#   43/397/1131). This module always reads the CURRENT ladder (that is the
#   point of not hardcoding it), so the regression checks against today's
#   ladder, not the 2026-09-09 snapshot.
#   sample.n_trading_days = 2660 (periods_per_year = 252, the family's own
#       preservation block's periods_per_year)
#   power["0.95"].claimed_sharpe_annualized = 1.08 (the paper's own claim)
#   power["0.95"].power_at_claimed_sharpe = 0.19510505057029315  -- computed
#       there at the family's REALIZED sigma_SR = 0.5740485047348345
#       (RUN_REPORT.txt line 212), not at this module's pre-build proxy.


def test_intraday_momentum_spy_does_not_reproduce_the_realized_run_because_no_realized_sigma_sr_exists_at_sourcing_time():
    """This is the honest-divergence case the task asked to record: run the
    sourcing check at intraday_momentum_spy's own declared inputs and show
    its power differs from the family's later REALIZED-sigma_SR run, because
    sigma_SR cannot be realized before the grid is built. Confirms the
    ladder still matches exactly."""
    n_local = 8
    periods_per_year = 252.0
    n_trading_days = 2660
    years_of_data = n_trading_days / periods_per_year
    claimed_sharpe = 1.08

    report = sourcing_power_check(
        claimed_sharpe_annualized=claimed_sharpe,
        periods_per_year=periods_per_year,
        years_of_data=years_of_data,
        n_local=n_local,
        bar=0.95,
        offset_fractions=(1.0, 0.5),
    )

    from app.services.research_lab.dsr_policy_n import dsr_policy_denominators
    from app.services.research_lab.global_effective_n import dsr_n_trials

    assert report.ladder == tuple(dsr_policy_denominators(dsr_n_trials(n_local)))
    assert report.n_observations == n_trading_days

    # This module's sourcing-time sigma_SR proxy is NOT the family's later
    # realized sigma_SR -- that is the documented, expected divergence.
    realized_sigma_sr = 0.5740485047348345
    assert report.sigma_sr_annualized != pytest.approx(realized_sigma_sr, abs=1e-6)

    realized_power_at_0_95 = 0.19510505057029315
    proxy_power_at_0_95 = report.fraction_results[1.0].power_at(n_local)
    assert proxy_power_at_0_95 != pytest.approx(realized_power_at_0_95, abs=1e-6)

    # But the sourcing check's own verdict is still DECLINE_AT_SOURCING here
    # (checked, not assumed): the deciding tier is the smallest fraction
    # (0.5) at n_local, which is well under POWER_FLOOR at either sigma_SR.
    assert report.verdict == DECLINE_AT_SOURCING
