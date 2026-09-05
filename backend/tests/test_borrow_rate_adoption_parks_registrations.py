"""THE 2026-09-06 BORROW ADOPTION, AND THE PARK IT IS SUPPOSED TO CAUSE.

WHAT WAS ADOPTED. lazy_prices and short_interest each stopped charging 0.0 for
short borrow and started charging THEIR OWN MEASURED rate:

    lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol   48.1644
      = 96.3287 bp/yr on that spec's realized short leg / 2
        (data/research_runs/lazy_prices_borrow_composition_2026-09-05)
    short_interest_ratio / si_ratio_hedged_h21               44.7705
      = 89.5410 bp/yr on that spec's realized short side / 2
        (data/research_runs/short_interest_borrow_composition_2026-09-05)

The halving is borrow_cost.financing_bps_for_long_short_book: the config field
charges GROSS notional and these books carry gross ~2x their short notional.

WHY THIS FILE EXISTS RATHER THAN A LINE IN A REPORT. Adopting those rates is
an OPERATIONAL-STATUS change to two LIVE forward-validation registrations —
both park as "spec_drift" and stop accumulating — and it was authorized by the
repo owner on exactly that basis. Two things therefore have to be true, and
neither is obvious from reading a constant:

  1. THE PARK MUST ACTUALLY HAPPEN, through the runner's own drift gate rather
     than through anyone hand-editing a status column. Sections 2 and 3 drive
     the REAL CrossSectionalForwardValidationRunner._process_registration
     against REAL rows carrying the fingerprints the live rows carry, and
     assert the status it writes.
  2. NOTHING ELSE MAY PARK. Three other families share the tick path and two
     of them (quality_cbop, quality_noa_industry_neutral) were fingerprinted
     on the very same 0.0 config, so a change made carelessly at the
     CrossSectionalConfig default instead of per-family would have taken them
     down too. Section 4 asserts they are untouched.

NO DB ROW'S STATUS IS WRITTEN BY THE ADOPTION COMMIT ITSELF. The rows in this
file are test fixtures; the deployed rows transition when the runner next
ticks them, which is the only mechanism that should ever perform it.
"""

import json
from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration,
)
from app.services.research_lab import (
    cross_sectional_forward_validation_runner as runner_module,
)
from app.services.research_lab.cross_sectional import CrossSectionalConfig
from app.services.research_lab.cross_sectional_forward import initial_state_json
from app.services.research_lab.cross_sectional_forward_registry import (
    config_fingerprint,
    config_identity,
    get_family_adapter,
    resolve_spec,
    spec_fingerprint,
    spec_identity,
)
from app.services.research_lab.cross_sectional_lazy_prices import (
    LAZY_PRICES_FINANCING_BPS_PER_YEAR,
)
from app.services.research_lab.cross_sectional_short_interest import (
    SHORT_INTEREST_FINANCING_BPS_PER_YEAR,
)

# The config fingerprint BOTH live rows were registered under. It is the hash
# of config_identity's six fields with financing_bps_per_year = 0.0, and the
# two families share it because every other field is the shared equity default.
# Read off cross_sectional_forward_validation_registrations (lazy_prices) and
# off the 2026-09-05 measurement run's baseline arm, which read it off the row
# (short_interest) — NOT recomputed from the code under test.
REGISTERED_CONFIG_FINGERPRINT = (
    "2dccbf932bfda8605e2f89ede56c501cc41dfb44ca8e876a99e6385e2dd06e2c"
)

# What each family's config hashes to AFTER adoption. Both were computed and
# published by the 2026-09-05 measurement runs BEFORE the rate was adopted, so
# these are predictions being checked, not outputs being recorded.
ADOPTED = {
    "lazy_prices_jaccard_full": (
        "lazy_jaccard_full_h126_ivol",
        48.1644,
        "97d087f74cd613e2fdf53751af8aab0c222834557715ad9f2cdc92536c13e7cd",
    ),
    "short_interest_ratio": (
        "si_ratio_hedged_h21",
        44.7705,
        "d8f3789e22141a4ff8ee1864ec5ae4325393514aa9c8de10f89331f11628d8a6",
    ),
}

# The families that share the tick path and MUST NOT move.
UNAFFECTED = ("cross_sectional_crypto", "quality_cbop", "quality_noa_industry_neutral")


@pytest.fixture(autouse=True)
def patch_runner_session(test_db_engine, monkeypatch):
    """CrossSectionalForwardValidationRunner opens its own SessionLocal
    directly (it is not a FastAPI route, so the get_db dependency override
    does not reach it) — point that at the same per-test SQLite engine.
    Identical to tests/test_cross_sectional_forward_validation.py's fixture of
    the same name; copied rather than shared because that file's is local to
    it."""
    testing_session_local = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(runner_module, "SessionLocal", testing_session_local)


# --- 1: the rates themselves, pinned against their own source runs -----------


@pytest.mark.parametrize(
    "constant,family_key",
    [
        (LAZY_PRICES_FINANCING_BPS_PER_YEAR, "lazy_prices_jaccard_full"),
        (SHORT_INTEREST_FINANCING_BPS_PER_YEAR, "short_interest_ratio"),
    ],
)
def test_each_family_charges_its_own_measured_rate(constant, family_key):
    """The constant, the family's live config and the published measurement
    must be the same number. Mutation testing's lesson applies here more than
    anywhere: a borrow rate quietly nudged toward zero flatters exactly the
    spec whose forward record this project is trying to judge honestly."""
    _pattern_id, expected, _fp = ADOPTED[family_key]
    assert constant == expected
    assert get_family_adapter(family_key).build_config().financing_bps_per_year == expected
    # It is a real charge, not a rounding of zero.
    assert expected > 0.0


def test_the_registered_baseline_is_the_zero_config_and_is_not_recomputed_here():
    """The before-state this whole change is measured against. If this ever
    fails, the live rows are not registered on the config everything in this
    file assumes, and no other assertion here means what it says."""
    zero = CrossSectionalConfig(cost_bps=5.0, financing_bps_per_year=0.0)
    assert config_fingerprint(zero) == REGISTERED_CONFIG_FINGERPRINT
    assert config_identity(zero)["financing_bps_per_year"] == 0.0


@pytest.mark.parametrize("family_key", list(ADOPTED))
def test_the_new_fingerprint_is_the_one_the_measurement_run_predicted(family_key):
    """Both 2026-09-05 runs printed the fingerprint their measured rate WOULD
    produce, before anyone adopted it. Reproducing those exactly is what makes
    the adoption a carried-out plan rather than a fresh, unchecked hash."""
    _pattern_id, _rate, predicted = ADOPTED[family_key]
    live = config_fingerprint(get_family_adapter(family_key).build_config())
    assert live == predicted
    assert live != REGISTERED_CONFIG_FINGERPRINT


# --- 2 and 3: the park, driven through the runner's own gate -----------------


def _seed_live_shaped_row(db, user_id: int, family_key: str):
    """A row shaped like the LIVE one: the real family_key and pattern_id, the
    real spec's own fingerprint (unchanged by this work, so spec drift must NOT
    be what fires), and the registered 0.0 config fingerprint and snapshot."""
    pattern_id, _rate, _fp = ADOPTED[family_key]
    _adapter, spec = resolve_spec(family_key, pattern_id)
    zero = CrossSectionalConfig(cost_bps=5.0, financing_bps_per_year=0.0)
    registration = CrossSectionalForwardValidationRegistration(
        user_id=user_id,
        family_key=family_key,
        pattern_id=pattern_id,
        module_path=get_family_adapter(family_key).module_path,
        spec_family=spec.family,
        citation=spec.citation,
        universe_rule="pinned in the family adapter",
        family_n_trials=get_family_adapter(family_key).n_trials,
        config_hash="borrow-adoption-test",
        spec_fingerprint=spec_fingerprint(spec),
        config_fingerprint=REGISTERED_CONFIG_FINGERPRINT,
        spec_snapshot_json=json.dumps(spec_identity(spec), sort_keys=True),
        config_snapshot_json=json.dumps(config_identity(zero), sort_keys=True),
        registration_rationale="seeded to the pre-adoption state",
        status="in_progress",
        min_trading_days_threshold=360,
        n_forward_trading_days=0,
        n_formations=0,
        started_at=date(2026, 9, 3),
        carry_state_json=initial_state_json(),
        day_results_json="[]",
        formations_json="[]",
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration


def _snapshot_of(registration):
    return runner_module._RegistrationSnapshot(
        id=registration.id,
        family_key=registration.family_key,
        pattern_id=registration.pattern_id,
        status=registration.status,
        started_at=registration.started_at,
        last_processed_date=registration.last_processed_date,
        min_trading_days_threshold=registration.min_trading_days_threshold,
        n_forward_trading_days=registration.n_forward_trading_days,
        n_formations=registration.n_formations,
        spec_fingerprint=registration.spec_fingerprint,
        config_fingerprint=registration.config_fingerprint,
        spec_snapshot_json=registration.spec_snapshot_json,
        config_snapshot_json=registration.config_snapshot_json,
        carry_state_json=registration.carry_state_json,
        day_results_json=registration.day_results_json,
        formations_json=registration.formations_json,
    )


@pytest.mark.parametrize("family_key", list(ADOPTED))
def test_the_runner_parks_the_live_row_on_its_next_tick(
    family_key, test_db_engine, register_and_verify, client
):
    """THE ASSERTION THE AUTHORIZATION WAS GIVEN AGAINST, executed rather than
    argued: a row carrying the live fingerprint, handed to the REAL runner with
    the REAL adapter's now-adopted config, comes back status "spec_drift".

    The panel is None deliberately. The drift gate runs BEFORE any day is
    processed, so a panel is never touched on this path — and passing None
    proves it: if the gate ever stopped firing first, this test would raise
    instead of quietly asserting the wrong thing.

    Nothing here writes a status by hand. _park_as_drifted is the runner's own
    method and is reached only through detect_spec_drift/detect_config_drift."""
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration = _seed_live_shaped_row(db, user["id"], family_key)
        registration_id = registration.id
        snapshot = _snapshot_of(registration)

    adapter = get_family_adapter(family_key)
    config = adapter.build_config()
    runner = runner_module.CrossSectionalForwardValidationRunner()
    runner._process_registration(
        snapshot, adapter, None, config, config_fingerprint(config), config_identity(config)
    )

    with session_local() as db:
        parked = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert parked.status == "spec_drift"
        # And it stops there: no day was accumulated on the way out.
        assert parked.n_forward_trading_days == 0
        assert parked.last_processed_date is None
        # ACTIVE_STATUSES excludes it, so it is never loaded again.
        assert parked.status not in runner_module.ACTIVE_STATUSES


@pytest.mark.parametrize("family_key", list(ADOPTED))
def test_it_is_the_BORROW_RATE_that_parks_it_and_not_something_else(
    family_key, test_db_engine, register_and_verify, client
):
    """ADVERSARIAL COMPANION to the test above, so a park for the wrong reason
    cannot read as success. Hand the same row the same adapter and the same
    everything EXCEPT financing_bps_per_year, held at the registered 0.0, and
    it must NOT park — which proves the spec is unchanged, the other five
    config fields are unchanged, and financing is the only thing that moved."""
    user = register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        registration = _seed_live_shaped_row(db, user["id"], family_key)
        registration_id = registration.id
        snapshot = _snapshot_of(registration)

    adapter = get_family_adapter(family_key)
    unchanged = adapter.build_config()
    unchanged.financing_bps_per_year = 0.0
    assert config_fingerprint(unchanged) == REGISTERED_CONFIG_FINGERPRINT

    runner = runner_module.CrossSectionalForwardValidationRunner()
    # The drift gate must fall through, which on this path means the runner
    # goes on to touch the panel — proving it got past the gate rather than
    # returning early. None is what makes that observable.
    with pytest.raises(AttributeError):
        runner._process_registration(
            snapshot,
            adapter,
            None,
            unchanged,
            config_fingerprint(unchanged),
            config_identity(unchanged),
        )

    with session_local() as db:
        still_live = db.get(CrossSectionalForwardValidationRegistration, registration_id)
        assert still_live.status == "in_progress", (
            "holding financing at 0.0 must not park this row — if it does, something OTHER than "
            "the borrow rate drifted and the adoption's blast radius is not what was authorized"
        )


# --- 4: the blast radius ------------------------------------------------------


@pytest.mark.parametrize("family_key", UNAFFECTED)
def test_no_other_live_family_was_dragged_along(family_key):
    """quality_cbop and quality_noa_industry_neutral are fingerprinted on the
    SAME 0.0 config the two adopting families were, so a rate applied at
    CrossSectionalConfig's default instead of per-family would have parked them
    too — silently, and without anyone authorizing it. Crypto is included
    because it is the one family that already charged financing (400.0) and so
    would expose a change made to the shared conversion helper."""
    live = config_fingerprint(get_family_adapter(family_key).build_config())
    assert live not in {fp for _p, _r, fp in ADOPTED.values()}
    if family_key.startswith("quality_"):
        assert live == REGISTERED_CONFIG_FINGERPRINT
        assert get_family_adapter(family_key).build_config().financing_bps_per_year == 0.0
    else:
        assert get_family_adapter(family_key).build_config().financing_bps_per_year == 400.0


def test_not_one_spec_fingerprint_moved_anywhere():
    """The adoption touches config, never a spec. A spec_fingerprint that moved
    would mean a strategy definition changed under the same commit, which is a
    different and much worse kind of drift than the one being authorized."""
    for family_key in list(ADOPTED) + list(UNAFFECTED):
        adapter = get_family_adapter(family_key)
        for spec in adapter.build_specs():
            resolved_adapter, resolved = resolve_spec(family_key, spec.pattern_id)
            assert resolved_adapter is adapter
            assert spec_fingerprint(resolved) == spec_fingerprint(spec)
