"""The Dormant pool: pinned boundaries, no-peek look schedule, entry validation."""


import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.deflated_sharpe import (
    compute_return_stats,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.dormant_pool import (
    BUCKET_HIGH,
    BUCKET_LOW,
    C_K,
    K_MAX,
    PHI_BUCKET_CUT,
    DormantPoolError,
    assign_bucket,
    boundaries_from_gate_output,
    evaluate_look,
    lag1_autocorrelation,
    load_manifest,
    parse_entry,
)


def _entry(**over) -> dict:
    payload = {
        "family_key": "synthetic_family",
        "pattern_id": "synthetic_h63",
        "spec_fingerprint": "a" * 64,
        "config_fingerprint": "b" * 64,
        "window_end_at_entry": "2026-08-31",
        "entered_at": "2026-09-09",
        "periods_per_year": 252,
        "phi_hat_entry": 0.02,
        "bucket": BUCKET_LOW,
        "pit_ok": True,
        "rescorable": True,
        "mechanism_review": "scorecard layer 2: mechanism not shown absent (fixture)",
        "entry_rationale": "underpowered definite_negative; power 0.15 at the claimed 0.5 (fixture)",
    }
    payload.update(over)
    return payload


def test_pinned_boundaries_equal_the_committed_validated_run():
    assert boundaries_from_gate_output() == C_K


def test_bucket_is_computed_from_entry_phi_never_chosen():
    assert assign_bucket(PHI_BUCKET_CUT) == BUCKET_LOW
    assert assign_bucket(PHI_BUCKET_CUT + 1e-9) == BUCKET_HIGH
    with pytest.raises(DormantPoolError, match="never chosen"):
        parse_entry(_entry(phi_hat_entry=0.25, bucket=BUCKET_LOW))
    assert parse_entry(_entry(phi_hat_entry=0.25, bucket=BUCKET_HIGH)).boundary == C_K[BUCKET_HIGH]


def test_lag1_autocorrelation_matches_numpy_on_a_known_series():
    rng = np.random.default_rng(3)
    x = rng.standard_normal(500)
    y = x.copy()
    y[1:] += 0.5 * x[:-1]
    s = pd.Series(y)
    expected = float(np.corrcoef(y[:-1] - y.mean(), y[1:] - y.mean())[0, 1])
    assert lag1_autocorrelation(s) == pytest.approx(expected, abs=2e-3)


def test_no_look_is_due_before_a_full_year_of_extension():
    entry = parse_entry(_entry())
    r = evaluate_look(pd.Series(np.full(251, 0.01)), entry)  # wildly positive, but not yet a look
    assert r.look_index == 0 and r.promoted is False and "no look due" in r.note
    # PSR is still displayed once >= 2 observations exist
    rng = np.random.default_rng(1)
    r2 = evaluate_look(pd.Series(rng.standard_normal(100) * 0.01 + 0.002), entry)
    assert r2.psr_ext is not None and r2.promoted is False


def test_promotion_only_at_a_scheduled_look_and_only_above_the_boundary():
    entry = parse_entry(_entry())
    rng = np.random.default_rng(11)
    strong = pd.Series(rng.standard_normal(252) * 0.01 + 0.003)  # very high Sharpe
    r = evaluate_look(strong, entry)
    assert r.look_index == 1
    assert r.promoted is (r.psr_ext >= C_K[BUCKET_LOW])
    weak = pd.Series(rng.standard_normal(252) * 0.01 + 0.0002)
    r2 = evaluate_look(weak, entry)
    assert r2.look_index == 1 and r2.promoted is False
    assert r2.psr_ext < C_K[BUCKET_LOW]


def test_psr_ext_is_the_projects_own_function_on_per_period_scale():
    entry = parse_entry(_entry())
    rng = np.random.default_rng(5)
    x = pd.Series(rng.standard_normal(300) * 0.01 + 0.0005)
    r = evaluate_look(x, entry)
    stats = compute_return_stats(x)
    expected = probabilistic_sharpe_ratio(float(x.mean() / x.std(ddof=1)), 0.0, stats.n, stats.skewness, stats.kurtosis)
    assert r.psr_ext == expected
    assert r.sharpe_ext_annualized == pytest.approx(float(x.mean() / x.std(ddof=1)) * np.sqrt(252))


def test_look_index_caps_at_k_max_and_uses_the_familys_own_calendar():
    entry = parse_entry(_entry(periods_per_year=365))
    assert entry.look_periods == 365
    r = evaluate_look(pd.Series(np.random.default_rng(2).standard_normal(365 * (K_MAX + 3)) * 0.01), entry)
    assert r.look_index == K_MAX


def test_not_pit_or_not_rescorable_never_promotes_even_when_the_numbers_would():
    rng = np.random.default_rng(11)
    strong = pd.Series(rng.standard_normal(504) * 0.01 + 0.005)
    for over in ({"pit_ok": False}, {"rescorable": False}):
        entry = parse_entry(_entry(**over))
        r = evaluate_look(strong, entry)
        assert r.promoted is False
        assert r.psr_ext is not None  # still displayed
        assert ("pit_ok" in r.note) or ("not rescorable" in r.note)


def test_entry_validation_refuses_placeholders_bad_dates_and_missing_fields():
    with pytest.raises(DormantPoolError, match="placeholder"):
        parse_entry(_entry(mechanism_review="<fill in>"))
    with pytest.raises(DormantPoolError, match="precedes"):
        parse_entry(_entry(entered_at="2026-01-01"))
    payload = _entry()
    del payload["pit_ok"]
    with pytest.raises(DormantPoolError, match="pit_ok"):
        parse_entry(payload)


def test_the_committed_manifest_parses_and_ships_empty():
    entries = load_manifest()
    assert entries == []


def test_manifest_rejects_duplicates(tmp_path):
    import json

    p = tmp_path / "m.json"
    p.write_text(json.dumps({"schema": "dormant_pool/v1", "entries": [_entry(), _entry()]}))
    with pytest.raises(DormantPoolError, match="duplicate"):
        load_manifest(p)


def test_family_wise_false_promotion_under_null_is_at_most_alpha():
    # A short re-check of the gate inside the suite: null paths, K_MAX looks,
    # LOW boundary, i.i.d. normal. 1 500 paths -> se ~0.006; assert <= 0.05 + 3se.
    entry = parse_entry(_entry())
    rng = np.random.default_rng(99)
    reps = 1500
    promoted = 0
    for _ in range(reps):
        x = pd.Series(rng.standard_normal(K_MAX * 252) * 0.01)
        hit = False
        for k in range(1, K_MAX + 1):
            if evaluate_look(x.iloc[: k * 252], entry).promoted:
                hit = True
                break
        promoted += int(hit)
    rate = promoted / reps
    assert rate <= 0.05 + 3 * np.sqrt(0.05 * 0.95 / reps), rate
