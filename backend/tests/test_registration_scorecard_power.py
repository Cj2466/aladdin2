"""The UNDERPOWERED verdict tier and the scorecard `power` block (2026-09-09).

Kept in its own file from test_registration_scorecards.py so the pre-existing
Policy D tests there are byte-for-byte unchanged — the tier is an addition
to the failing branch, and those tests are the proof it changed nothing else."""

import pytest

from app.services.research_lab.dsr_power import POWER_FLOOR, dsr_power_report
from app.services.research_lab.registration_scorecard import (
    VERDICT_DEFINITE_NEGATIVE,
    VERDICT_PASS,
    VERDICT_UNDERPOWERED,
    VERDICT_UNRESOLVED,
    VERDICTS,
    ScorecardError,
    parse_scorecard,
    policy_d_verdict,
)
from tests.test_registration_scorecards import _valid_payload

FAILING = {12: 0.31, 37: 0.20, 362: 0.05, 1031: 0.02}


def test_the_new_tier_is_in_the_vocabulary():
    assert VERDICT_UNDERPOWERED in VERDICTS


def test_a_local_failure_with_low_power_is_underpowered_not_definite_negative():
    assert (
        policy_d_verdict(dsr_by_n=FAILING, threshold=0.95, n_local=12, power_at_claimed_sharpe=POWER_FLOOR - 0.01)
        == VERDICT_UNDERPOWERED
    )


def test_a_local_failure_with_adequate_power_stays_definite_negative():
    assert (
        policy_d_verdict(dsr_by_n=FAILING, threshold=0.95, n_local=12, power_at_claimed_sharpe=POWER_FLOOR)
        == VERDICT_DEFINITE_NEGATIVE
    )


def test_without_a_power_number_the_failing_tier_is_unchanged():
    assert policy_d_verdict(dsr_by_n=FAILING, threshold=0.95, n_local=12) == VERDICT_DEFINITE_NEGATIVE


def test_power_never_upgrades_a_failure_and_never_touches_the_upper_tiers():
    # Low power on a local pass changes nothing: the higher rungs decide.
    assert (
        policy_d_verdict(dsr_by_n={12: 0.97, 362: 0.61, 1031: 0.55}, threshold=0.95, n_local=12, power_at_claimed_sharpe=0.05)
        == VERDICT_UNRESOLVED
    )
    assert (
        policy_d_verdict(dsr_by_n={12: 0.99, 362: 0.98, 1031: 0.96}, threshold=0.95, n_local=12, power_at_claimed_sharpe=0.05)
        == VERDICT_PASS
    )
    # And an unmeasurable local DSR with low power is underpowered, not a pass.
    assert (
        policy_d_verdict(dsr_by_n={12: None, 362: 0.98, 1031: 0.99}, threshold=0.95, n_local=12, power_at_claimed_sharpe=0.05)
        == VERDICT_UNDERPOWERED
    )


def _power_block(claimed: float, *, threshold=0.95, n_local=12, n_observations=2180, sigma=0.19, ppy=252.0) -> dict:
    report = dsr_power_report(
        claimed_sharpe_annualized=claimed,
        threshold=threshold,
        n_observations=n_observations,
        n_trials=n_local,
        sigma_sr_annualized=sigma,
        periods_per_year=ppy,
    )
    return {
        "claimed_sharpe_annualized": claimed,
        "claimed_sharpe_source": "Fixture source, Table 1, gross 0.6 less 5bp cost model",
        "sigma_sr_annualized": sigma,
        "periods_per_year": ppy,
        "required_observed_sharpe": round(report.required_observed_sharpe, 4),
        "power_at_claimed_sharpe": round(report.power_at_claimed_sharpe, 4),
        "min_detectable_sharpe": None if report.min_detectable_sharpe is None else round(report.min_detectable_sharpe, 4),
        "years_to_detect_claimed": None if report.years_to_detect_claimed is None else round(report.years_to_detect_claimed, 2),
    }


def _payload_with_power(claimed: float, verdict: str) -> dict:
    payload = _valid_payload()
    layer = payload["layer_1_statistical"]
    layer["power"] = _power_block(claimed)
    layer["verdict"] = verdict
    return payload


def test_a_card_whose_test_could_not_see_the_claim_parses_as_underpowered():
    card = parse_scorecard(_payload_with_power(0.5, VERDICT_UNDERPOWERED))
    assert card.layer_1.verdict == VERDICT_UNDERPOWERED == card.layer_1.computed_verdict
    assert card.layer_1.power is not None and card.layer_1.power.power_at_claimed_sharpe < POWER_FLOOR
    assert "UNDERPOWERED" in card.summary()


def test_a_card_whose_test_could_see_the_claim_stays_definite_negative():
    card = parse_scorecard(_payload_with_power(1.6, VERDICT_DEFINITE_NEGATIVE))
    assert card.layer_1.verdict == VERDICT_DEFINITE_NEGATIVE
    assert card.layer_1.power.power_at_claimed_sharpe >= POWER_FLOOR


def test_a_verdict_that_ignores_its_own_power_block_is_refused():
    with pytest.raises(ScorecardError, match="never allowed to disagree"):
        parse_scorecard(_payload_with_power(0.5, VERDICT_DEFINITE_NEGATIVE))
    with pytest.raises(ScorecardError, match="never allowed to disagree"):
        parse_scorecard(_payload_with_power(1.6, VERDICT_UNDERPOWERED))


def test_stated_power_numbers_that_disagree_with_their_inputs_are_refused():
    payload = _payload_with_power(0.5, VERDICT_UNDERPOWERED)
    payload["layer_1_statistical"]["power"]["power_at_claimed_sharpe"] = 0.79  # flattering, and false
    with pytest.raises(ScorecardError, match="power_at_claimed_sharpe says"):
        parse_scorecard(payload)
    payload = _payload_with_power(0.5, VERDICT_UNDERPOWERED)
    payload["layer_1_statistical"]["power"]["min_detectable_sharpe"] = 0.5
    with pytest.raises(ScorecardError, match="min_detectable_sharpe says"):
        parse_scorecard(payload)


def test_a_power_block_needs_its_source_and_all_four_outputs():
    payload = _payload_with_power(0.5, VERDICT_UNDERPOWERED)
    del payload["layer_1_statistical"]["power"]["claimed_sharpe_source"]
    with pytest.raises(ScorecardError, match="claimed_sharpe_source"):
        parse_scorecard(payload)
    payload = _payload_with_power(0.5, VERDICT_UNDERPOWERED)
    del payload["layer_1_statistical"]["power"]["years_to_detect_claimed"]
    with pytest.raises(ScorecardError, match="years_to_detect_claimed"):
        parse_scorecard(payload)


def test_a_pre_2026_09_09_card_without_a_power_block_still_parses_unchanged():
    card = parse_scorecard(_valid_payload())
    assert card.layer_1.power is None
    assert card.layer_1.verdict == VERDICT_DEFINITE_NEGATIVE
