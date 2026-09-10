"""Structural enforcement of the registration scorecard (Layers 1-4 +
preservation_score).

THE HEADLINE TEST IN THIS FILE IS EXPECTED TO FAIL RIGHT NOW, and that is the
correct state, not a defect. test_every_family_has_a_scorecard lists every
family with persisted trial results or a live forward registration that has no
scorecard under data/research_runs/scorecards/. On the commit that introduced
this file that list is every family in the project.

DO NOT silence it by writing scorecards from the code. An honest Layer 2
source_locus needs the construction context the original author had — which
paper section they were reading when they picked a breakpoint — and inventing
one produces a citation that LOOKS verified and is not. This project has
already shipped one formula written from memory (the discarded Corwin-Schultz
implementation; see spread_estimator.py). A listed gap is worth more than a
fabricated scorecard. See REGISTRATION_SCORECARD_TEMPLATE.md, final section.

The rest of the file tests the validator itself against synthetic scorecards
in tmp_path, so the machinery is proven to work independently of whether any
real scorecard exists yet.

THE COST OF THAT, STATED RATHER THAN GLOSSED. This project's convention has
been "full suite green" (f385fc5: 3573 passed / 3 skipped). From this commit
the suite is green EXCEPT one named governance gap, and a permanently red test
is the classic way a signal stops being read. Two things are done about it
rather than nothing:

  * the failure is exactly ONE test with a self-describing name, so
    "nothing new is broken" is still answerable at a glance;
  * to see the rest of the suite on its own baseline:

        pytest --deselect tests/test_registration_scorecards.py::test_every_family_has_a_scorecard

    That is a reporting convenience for a verification pass, NOT a fix. The
    fix is writing the scorecards. Do not commit it into a config file.
"""

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.db import engine
from app.services.research_lab.registration_scorecard import (
    CLAIM_CONDITIONAL,
    CLAIM_UNCONDITIONAL,
    KNOWN_REGIME_KEYS,
    SCHEMA,
    VERDICT_DEFINITE_NEGATIVE,
    VERDICT_PASS,
    VERDICT_UNRESOLVED,
    ScorecardError,
    covered_family_keys,
    live_registration_family_keys,
    load_family_inventory,
    load_scorecard,
    load_scorecard_waivers,
    parse_scorecard,
    policy_d_verdict,
    regimes_covered_by,
    required_pooled_denominators,
    scorecard_path_for,
    unwaivable_family_keys,
    waived_family_keys,
)

# --- the requirement itself --------------------------------------------------


def required_family_keys() -> dict[str, str]:
    """{family_key: why it is required}. The union of the two tables the
    scorecard rule names — the committed snapshot of
    cross_sectional_trial_results, and every live/retired forward registration
    app/main.py opens at startup."""
    required: dict[str, str] = {}
    for key in load_family_inventory().family_keys:
        required[key] = "has persisted rows in cross_sectional_trial_results"
    for key, pattern_id in live_registration_family_keys().items():
        prior = required.get(key)
        reason = f"live forward registration ({pattern_id})"
        required[key] = f"{prior}; {reason}" if prior else reason
    return required


def test_every_family_has_a_scorecard():
    """EXPECTED TO FAIL until the families that cannot be waived have a card.
    Since 2026-09-10 (owner's option B) a required key is answered for either
    by a scorecard or by a WAIVER pointing at its existing verification
    record — and a waiver is barred for every live/retired registration and
    every Dormant-pool family, which is where a card actually matters. The
    list this prints is therefore exactly those families, and it is the
    deliverable, not an obstacle to it."""
    required = required_family_keys()
    covered = covered_family_keys()
    waived = waived_family_keys()
    missing = sorted(set(required) - covered - waived)
    if missing:
        barred = unwaivable_family_keys()
        lines = "\n".join(
            f"  - {key}: {required[key]}" + (f" [waiver barred: {barred[key]}]" if key in barred else "")
            for key in missing
        )
        pytest.fail(
            f"{len(missing)} of {len(required)} families have neither a registration scorecard nor a "
            f"waiver ({len(covered)} scored, {len(waived)} waived):\n"
            f"{lines}\n\n"
            "Fill in app/services/research_lab/templates/REGISTRATION_SCORECARD_TEMPLATE.md "
            "and commit it to data/research_runs/scorecards/<family_key>_SCORECARD.json.\n"
            "Do NOT reconstruct Layer 2 citations from the code to make this pass — see the "
            "template's final section. A waiver is NOT available for a family marked "
            "'waiver barred' above."
        )


# --- waivers: a pointer, never an exemption ----------------------------------


def test_no_waiver_covers_a_live_retired_or_parked_family():
    """The two groups where the card matters can never be waived."""
    barred = unwaivable_family_keys()
    offending = sorted(k for k in waived_family_keys() if k in barred)
    assert not offending, (
        "these families are waived but a waiver is barred for them: "
        + ", ".join(f"{k} ({barred[k]})" for k in offending)
    )


def test_no_family_is_both_scored_and_waived():
    both = sorted(covered_family_keys() & waived_family_keys())
    assert not both, f"scored AND waived — delete the waiver: {both}"


def test_every_waiver_names_a_required_family():
    """A waiver for a key nobody requires is a typo or a stale entry."""
    stray = sorted(waived_family_keys() - set(required_family_keys()))
    assert not stray, f"waivers for keys that are not required: {stray}"


def test_every_waiver_points_at_an_existing_record_and_a_named_reviewer():
    """load_scorecard_waivers already refuses a missing record_path; this pins
    that the loader is actually the thing being read, and that every waiver
    carries a reason, a locus and a dated signature."""
    waivers = load_scorecard_waivers()
    assert waivers, "no waivers on file — if that is intended, delete this test with the file"
    for w in waivers:
        assert (Path(__file__).resolve().parents[1] / w.record_path).exists(), w
        assert w.reason.strip() and w.record_locus.strip() and w.waived_by.strip(), w


def test_every_scorecard_on_disk_parses():
    """Separate from the completeness test on purpose: 'missing' and 'present
    but broken' are different failures and must not mask each other."""
    for key in sorted(covered_family_keys()):
        path = scorecard_path_for(key)
        if not path.exists():
            # An alias covered by another card's covers_family_keys.
            continue
        load_scorecard(key)


def test_no_scorecard_covers_a_family_that_is_not_required():
    """A card claiming coverage of a key nothing requires is either a typo in
    covers_family_keys or a family key that was renamed without the card
    following it. Both are silent-drift failures."""
    required = set(required_family_keys())
    stray = sorted(covered_family_keys() - required)
    assert not stray, (
        f"scorecard(s) claim coverage of unknown family key(s) {stray}. Either the key is "
        "misspelled, or the family was renamed and FAMILY_INVENTORY.json was not refreshed "
        "(data/research_runs/refresh_family_inventory.py)."
    )


def test_family_inventory_is_not_stale_against_the_live_database():
    """When the real research database IS in front of us, its family list must
    already be in the committed inventory. Skips when it is not — the inventory
    is what carries the requirement into worktrees and CI (see
    refresh_family_inventory.py), and this test is the guard that keeps the
    snapshot honest wherever the DB does exist."""
    # Checked BEFORE touching the engine: connecting to a sqlite:/// URL whose
    # file does not exist CREATES an empty one, so a naive has_table() probe
    # would litter every worktree and CI checkout with a stray 0-byte
    # aladdin2.db (observed, not theoretical — it happened on the first run of
    # this test).
    if engine.url.drivername.startswith("sqlite"):
        db_file = engine.url.database
        if db_file in (None, "", ":memory:") or not Path(db_file).exists():
            pytest.skip(f"no sqlite database file at {db_file!r}")
    if not inspect(engine).has_table("cross_sectional_trial_results"):
        pytest.skip("no cross_sectional_trial_results table in the configured database")
    with engine.connect() as conn:
        live = {
            row[0]
            for row in conn.execute(
                text("select distinct family_key from cross_sectional_trial_results")
            )
        }
    if not live:
        pytest.skip("cross_sectional_trial_results is empty in the configured database")
    missing = sorted(live - set(load_family_inventory().family_keys))
    assert not missing, (
        f"the database has family key(s) {missing} that FAMILY_INVENTORY.json does not list. "
        "Regenerate it: ./venv/bin/python data/research_runs/refresh_family_inventory.py"
    )


def test_live_registration_keys_resolve():
    """The five startup registrations resolve to real, distinct family keys.
    A rename that breaks this breaks the scorecard requirement for a LIVE
    registration, which is the one place a silent gap matters most."""
    keys = live_registration_family_keys()
    assert len(keys) == 5, keys
    assert all(k and isinstance(k, str) for k in keys)
    assert len(set(keys.values())) == 5, "two registrations share a pattern_id"


def test_pooled_denominators_come_from_the_committed_artifact():
    """Policy D's pooled rungs are READ, never retyped. If the ladder artifact
    is recomputed these move, and every scorecard's required N points move
    with them."""
    # Was `== (481, 857)` until 2026-09-06, when the pooled rungs moved from
    # global_effective_n.json's PROVENANCE fields to dsr_policy_n.json's
    # explicit ladder. Derived from the artifact rather than retyped, so this
    # test tracks the ladder instead of pinning a snapshot of it.
    from app.services.research_lab.dsr_policy_n import load_dsr_policy_ladder

    assert required_pooled_denominators() == load_dsr_policy_ladder().pooled_rungs
    assert required_pooled_denominators() == (43, 397, 1131)  # re-measured and adopted 2026-09-09 (was 37, 362, 1031)


# --- Policy D ----------------------------------------------------------------


def test_policy_d_definite_negative_when_local_fails():
    assert (
        policy_d_verdict(dsr_by_n={12: 0.30, 362: 0.05, 1031: 0.02}, threshold=0.95, n_local=12)
        == VERDICT_DEFINITE_NEGATIVE
    )


def test_policy_d_unresolved_when_local_passes_and_higher_fails():
    assert (
        policy_d_verdict(dsr_by_n={12: 0.97, 362: 0.61, 1031: 0.55}, threshold=0.95, n_local=12)
        == VERDICT_UNRESOLVED
    )


def test_policy_d_pass_only_at_the_highest_measured_n():
    assert (
        policy_d_verdict(dsr_by_n={12: 0.99, 362: 0.98, 1031: 0.96}, threshold=0.95, n_local=12)
        == VERDICT_PASS
    )


def test_policy_d_treats_an_unmeasurable_dsr_as_not_clearing():
    # None at the top N is not a pass: deflated_sharpe returns None below
    # MIN_TRIALS_FOR_DSR and on degenerate series, and neither is evidence.
    assert (
        policy_d_verdict(dsr_by_n={12: 0.99, 362: 0.98, 1031: None}, threshold=0.95, n_local=12)
        == VERDICT_UNRESOLVED
    )
    assert (
        policy_d_verdict(dsr_by_n={12: None, 362: 0.98, 1031: 0.99}, threshold=0.95, n_local=12)
        == VERDICT_DEFINITE_NEGATIVE
    )


def test_policy_d_single_tier_when_local_grid_exceeds_the_pooled_numbers():
    # phase_a_intraday_expanded has 212 specs; a hypothetical 900-spec family
    # is judged once, at its own N, because dsr_n_trials' max() makes the
    # pooled numbers irrelevant to it.
    assert policy_d_verdict(dsr_by_n={900: 0.96}, threshold=0.95, n_local=900) == VERDICT_PASS
    assert (
        policy_d_verdict(dsr_by_n={900: 0.94}, threshold=0.95, n_local=900)
        == VERDICT_DEFINITE_NEGATIVE
    )


def test_policy_d_requires_a_local_reading():
    with pytest.raises(ScorecardError, match="no DSR supplied at n_local"):
        policy_d_verdict(dsr_by_n={362: 0.9}, threshold=0.95, n_local=12)


# --- regime coverage is computed, not asserted -------------------------------


def test_regime_coverage_for_a_2015_2026_window():
    present, absent = regimes_covered_by(date(2015, 1, 7), date(2026, 8, 31))
    assert present == ["covid_2020", "rate_hike_2022"]
    assert absent == ["dotcom_2000", "gfc_2008"]


def test_regime_coverage_for_a_full_history_window():
    present, absent = regimes_covered_by(date(1995, 1, 1), date(2026, 1, 1))
    assert sorted(present) == sorted(KNOWN_REGIME_KEYS)
    assert absent == []


def test_a_one_day_brush_with_a_regime_is_not_coverage():
    # Window ends the day after the GFC bracket opens.
    present, _ = regimes_covered_by(date(2005, 1, 1), date(2007, 10, 10))
    assert "gfc_2008" not in present


# --- the validator -----------------------------------------------------------


def _valid_payload(**overrides) -> dict:
    payload = {
        "schema": SCHEMA,
        "family_key": "synthetic_family",
        "covers_family_keys": ["synthetic_family"],
        "pattern_id": "synthetic_h63",
        "written_at": "2026-09-05",
        "author": "test fixture",
        "decision": "DECLINED",
        "decision_rationale": "Fixture card, not a real decision about a real family.",
        "preregistration_path": "none: this is a test fixture",
        "layer_1_statistical": {
            "best_spec_pattern_id": "synthetic_h63",
            "n_local": 12,
            "dsr_pass_threshold": 0.95,
            "dsr_by_n": {"12": 0.31, "37": 0.20, "362": 0.05, "1031": 0.02, "43": 0.19, "397": 0.05, "1131": 0.02},
            "verdict": VERDICT_DEFINITE_NEGATIVE,
            "sharpe_net_annualized": 0.42,
            "n_observations": 2180,
            "preservation_score": 0.0,
            "preservation_score_no_stab": 0.006,
            "preservation_inputs_note": "cred = dsr at n_local=12, run_tag synthetic; 252/yr",
        },
        "layer_2_mechanism_fidelity": {
            "source_citation": "A Fixture, 'Nothing Real', Journal of Tests 1(1), 2026, pp. 1-2",
            "source_text_obtained": True,
            "construction_choices": [
                {"choice": "monthly rebalance", "source_locus": "Journal of Tests 1(1), section 3"}
            ],
            "deviations": [],
            "independent_reviewer": "test fixture",
            "independent_reviewer_signed_off_at": "2026-09-05",
            "independent_reviewer_findings": "Nothing; this card is synthetic.",
        },
        "layer_3_regime_conditional": {
            "source_claim_type": CLAIM_UNCONDITIONAL,
            "claim_evidence": "The fixture source claims an unconditional effect.",
            "not_applicable_reason": "Unconditional claim, so no regime split is pre-declared.",
        },
        "layer_4_economics": {
            "cost_scenarios": [
                {
                    "name": "flat 2bp",
                    "one_way_bps": 2.0,
                    "source": "Hagstromer JFE 2021 Table 1",
                    "best_spec_net_sharpe": 0.42,
                },
                {
                    "name": "flat 5bp control",
                    "one_way_bps": 5.0,
                    "source": "DEFAULT_XS_COST_BPS",
                    "best_spec_net_sharpe": 0.21,
                },
            ],
            "capacity": {
                "avg_daily_dollar_volume_usd": 1.0e9,
                "participation_cap_fraction": 0.01,
                "n_names_per_leg": 25,
                "capacity_usd": 2.5e8,
                "method": "ADV x cap x names, fixture numbers",
            },
            "regime_coverage": {
                "window_start": "2015-01-07",
                "window_end": "2026-08-31",
                "regimes_present": ["covid_2020", "rate_hike_2022"],
                "regimes_absent": ["dotcom_2000", "gfc_2008"],
                "statement": "Fixture window sees COVID and 2022, not the dot-com bust or the GFC.",
            },
        },
    }
    payload.update(overrides)
    return payload


def test_a_complete_scorecard_parses():
    card = parse_scorecard(_valid_payload())
    assert card.layer_1.verdict == card.layer_1.computed_verdict
    assert card.layer_4.regime_coverage.regimes_present == ("covid_2020", "rate_hike_2022")
    assert "DEFINITE_NEGATIVE" in card.summary()


def test_preservation_score_is_not_optional():
    payload = _valid_payload()
    del payload["layer_1_statistical"]["preservation_score"]
    with pytest.raises(ScorecardError, match="preservation_score"):
        parse_scorecard(payload)


def test_a_placeholder_string_is_rejected():
    for placeholder in ("<who wrote it>", "TODO", "  ", "TBD later"):
        payload = _valid_payload(author=placeholder)
        with pytest.raises(ScorecardError, match="placeholder|missing"):
            parse_scorecard(payload)


def test_a_verdict_that_disagrees_with_its_own_numbers_is_rejected():
    payload = _valid_payload()
    payload["layer_1_statistical"]["verdict"] = VERDICT_PASS
    with pytest.raises(ScorecardError, match="disagree"):
        parse_scorecard(payload)


def test_missing_a_pooled_denominator_is_rejected():
    payload = _valid_payload()
    del payload["layer_1_statistical"]["dsr_by_n"]["1131"]
    with pytest.raises(ScorecardError, match="1131"):
        parse_scorecard(payload)


def test_asserted_regime_coverage_that_contradicts_the_window_is_rejected():
    payload = _valid_payload()
    payload["layer_4_economics"]["regime_coverage"]["regimes_present"] = list(KNOWN_REGIME_KEYS)
    payload["layer_4_economics"]["regime_coverage"]["regimes_absent"] = []
    with pytest.raises(ScorecardError, match="COMPUTED from the window"):
        parse_scorecard(payload)


def test_a_single_cost_scenario_is_rejected():
    payload = _valid_payload()
    payload["layer_4_economics"]["cost_scenarios"] = payload["layer_4_economics"]["cost_scenarios"][:1]
    with pytest.raises(ScorecardError, match="at least 2"):
        parse_scorecard(payload)


def test_an_unconditional_claim_may_not_carry_a_regime_split():
    payload = _valid_payload()
    payload["layer_3_regime_conditional"]["dsr_in_regime"] = 0.9
    with pytest.raises(ScorecardError, match="post-hoc conditioning"):
        parse_scorecard(payload)


def test_a_conditional_claim_must_pre_declare_its_rule_and_split_the_dsr():
    payload = _valid_payload()
    payload["layer_3_regime_conditional"] = {
        "source_claim_type": CLAIM_CONDITIONAL,
        "claim_evidence": "The fixture source claims the effect only in high-volatility months.",
    }
    with pytest.raises(ScorecardError, match="regime_definition_rule"):
        parse_scorecard(payload)

    payload["layer_3_regime_conditional"].update(
        {
            "regime_definition_rule": "VIX above its trailing 12-month median at formation.",
            "regime_rule_pre_declared_at": "2026-09-01",
            "dsr_in_regime": 0.80,
            "dsr_out_of_regime": 0.10,
        }
    )
    card = parse_scorecard(payload)
    assert card.layer_3.is_conditional
    assert card.layer_3.dsr_in_regime == 0.80


def test_covers_family_keys_must_include_the_cards_own_key():
    payload = _valid_payload(covers_family_keys=["something_else"])
    with pytest.raises(ScorecardError, match="must include the scorecard's own family_key"):
        parse_scorecard(payload)


def test_an_unknown_schema_is_refused_rather_than_guessed_at():
    with pytest.raises(ScorecardError, match="Refusing to guess"):
        parse_scorecard(_valid_payload(schema="registration_scorecard/v99"))


def test_loading_a_scorecard_filed_under_the_wrong_name_is_refused(tmp_path: Path):
    (tmp_path / "wrong_name_SCORECARD.json").write_text(json.dumps(_valid_payload()))
    with pytest.raises(ScorecardError, match="filed under"):
        load_scorecard("wrong_name", directory=tmp_path)


def test_a_missing_scorecard_names_the_template(tmp_path: Path):
    with pytest.raises(ScorecardError, match="REGISTRATION_SCORECARD_TEMPLATE.md"):
        load_scorecard("nothing_here", directory=tmp_path)
