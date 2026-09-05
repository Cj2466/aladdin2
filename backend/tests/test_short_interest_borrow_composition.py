"""short_interest's MEASURED borrow exposure, pinned.

WHAT THIS FILE DEFENDS. borrow_cost.py names short_interest as the family
where the standing 0.0 borrow assumption "bites hardest", and it is right --
about the long_short specs. THE REGISTERED SPEC IS NOT ONE OF THEM.
si_ratio_hedged_h21 is a long_universe_hedged spec whose short side is the
equal-weighted whole eligible universe, so it is the cheap book in that
sentence, not the expensive one.

That distinction is the entire finding of
data/research_runs/run_short_interest_borrow_composition.py, and it rests on
two structural facts that a future refactor could quietly break: which
portfolio type the registered spec uses, and what the harness shorts for that
type. Both are asserted here rather than left in a report nobody re-runs.

NOTHING HERE ADOPTED ANYTHING UNTIL 2026-09-06, AND NOW THE MEASUREMENT IS
ADOPTED. The repo owner authorized wiring the measured rate into the family
config, having been told in the same breath that doing so parks the live
registration. So the two tests in sections 3 and 4 below are INVERTED rather
than deleted: they used to pin "the live config is still 0.0 and any rate
would park it", and they now pin "the live config IS the measured rate, and
it HAS drifted from the fingerprint the live row was registered under". The
underlying mechanism they defend -- financing_bps_per_year is in
config_identity, so moving it moves config_fingerprint and the runner's
drift gate parks the row -- is unchanged and is still what is asserted.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.cross_sectional_forward_validation_service import detect_config_drift
from app.services.research_lab.borrow_cost import (
    DEFAULT_SCHEDULE,
    GENERAL_COLLATERAL_BPS_PER_YEAR,
    HARD_TO_BORROW_BPS_PER_YEAR,
    financing_bps_for_long_short_book,
)
from app.services.research_lab.cross_sectional import CrossSectionalConfig
from app.services.research_lab.cross_sectional_forward_registry import (
    config_fingerprint,
    config_identity,
)
from app.services.research_lab.cross_sectional_short_interest import (
    SHORT_INTEREST_RANK_FRACTION,
    build_short_interest_family,
    default_short_interest_config,
)

REGISTERED_SPEC_ID = "si_ratio_hedged_h21"
# The fingerprint the LIVE row is registered under (financing 0.0), read off
# the 2026-09-05 measurement run's own baseline arm -- which read it off the
# registration row -- rather than recomputed from the code under test. A
# change here is not a test to update; it is the identity of the live row.
REGISTERED_ROW_CONFIG_FINGERPRINT = (
    "2dccbf932bfda8605e2f89ede56c501cc41dfb44ca8e876a99e6385e2dd06e2c"
)
# The rate adopted 2026-09-06, kept here as a literal so that a change to the
# family constant has to be restated in a second place on purpose.
ADOPTED_FINANCING_BPS_PER_YEAR = 44.7705
REPORT_JSON = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "research_runs"
    / "short_interest_borrow_composition_2026-09-05.json"
)


@pytest.fixture(scope="module")
def report():
    if not REPORT_JSON.is_file():
        pytest.skip(f"{REPORT_JSON.name} not present in this checkout")
    return json.loads(REPORT_JSON.read_text())


# --- 1: the structural fact the whole finding rests on -----------------------


def test_the_registered_spec_is_the_hedged_book_not_a_long_short_one():
    """THE HEADLINE, as an assertion. borrow_cost.py's "bites hardest"
    sentence is about the specs that short the most heavily shorted names;
    the registered one shorts the whole universe instead. If this ever flips,
    every borrow number measured for this registration is describing a
    different book and must be re-measured before it is used."""
    spec = next(s for s in build_short_interest_family() if s.pattern_id == REGISTERED_SPEC_ID)
    assert spec.portfolio == "long_universe_hedged"
    # And its LONG leg is the low-short-interest tail, which is what removes
    # part of borrow_cost's low tail from the shorted side.
    assert spec.signal_fn.__name__ == "signal_low_short_interest_ratio"
    assert spec.rank_fraction == SHORT_INTEREST_RANK_FRACTION == 0.05


def test_the_long_short_siblings_that_the_bites_hardest_sentence_describes_exist():
    """The expensive books are real, screened, and NOT registered. Stated as a
    test so "short_interest is expensive to borrow" can never be read as a
    statement about the live row."""
    ls = [s for s in build_short_interest_family() if s.portfolio == "long_short"]
    assert len(ls) == 6
    assert REGISTERED_SPEC_ID not in {s.pattern_id for s in ls}


def test_the_hedged_book_shorts_the_whole_eligible_universe():
    """cross_sectional._target_weights' contract, exercised rather than
    quoted: a long_universe_hedged formation's short side is 1/N on every
    eligible name, so its gross notional is NOT 2.0 and borrow_cost's B/2
    conversion does not apply to it."""
    from app.services.research_lab.cross_sectional import _target_weights

    eligible = [f"T{i}" for i in range(100)]
    long_weights = {t: 0.2 for t in eligible[:5]}
    weights = _target_weights(long_weights, {}, "long_universe_hedged", eligible)

    assert set(weights) == set(eligible), "every eligible name carries a weight"
    # The 95 non-long names are short 1/N each; the 5 long names are net long.
    assert all(weights[t] == pytest.approx(-0.01) for t in eligible[5:])
    assert all(weights[t] == pytest.approx(0.19) for t in eligible[:5])
    gross = sum(abs(w) for w in weights.values())
    assert gross == pytest.approx(1.9)
    assert gross != pytest.approx(2.0), (
        "if a hedged book's gross were 2.0, borrow_cost's B/2 would apply and the measurement "
        "runner's own net-weight arithmetic would be redundant"
    )


def test_the_net_weight_charge_reduces_to_borrow_costs_b_over_2_for_a_long_short_book():
    """The general formula the runner uses --
    sum(|net_w| * rate) / gross_notional -- must agree with borrow_cost's own
    conversion exactly on the book that conversion IS valid for. This is the
    cross-check the runner asserts at run time, kept here so it is exercised
    without a data build."""
    from app.services.research_lab.cross_sectional import _target_weights

    eligible = [f"T{i}" for i in range(20)]
    long_weights = {t: 0.5 for t in eligible[:2]}
    short_weights = {t: 0.5 for t in eligible[-2:]}
    weights = _target_weights(long_weights, short_weights, "long_short", eligible)
    gross = sum(abs(w) for w in weights.values())
    assert gross == pytest.approx(2.0)

    rate = 430.0
    charge = sum(-w * rate for w in weights.values() if w < 0)
    assert charge / gross == pytest.approx(financing_bps_for_long_short_book(rate))


# --- 2: the schedule's own arithmetic, on this family's construction ---------


def test_a_leg_selected_on_short_interest_lands_entirely_in_the_expensive_tail():
    """WHY the long_short specs are the expensive ones, from the two rules
    rather than from the data: the leg is the top SHORT_INTEREST_RANK_FRACTION
    (5%) of the cross-section by short interest, and borrow_cost's tail is the
    top HARD_TO_BORROW_TAIL_FRACTION (10%). 5% sits wholly inside 10%, so
    every name in that leg pays the specials rate."""
    assert SHORT_INTEREST_RANK_FRACTION < DEFAULT_SCHEDULE.tail_fraction

    values = pd.Series(np.arange(200, dtype=float), index=[f"T{i}" for i in range(200)])
    percentiles = values.rank(pct=True)
    top_leg = percentiles.nlargest(int(200 * SHORT_INTEREST_RANK_FRACTION)).index
    rates = DEFAULT_SCHEDULE.rate_for_percentiles(percentiles.reindex(top_leg))
    assert set(rates.unique()) == {HARD_TO_BORROW_BPS_PER_YEAR}
    assert financing_bps_for_long_short_book(float(rates.mean())) == pytest.approx(215.0)


def test_the_no_tilt_baseline_is_113_2_not_34():
    """The reference every measured tail share is read against, recomputed
    from the schedule rather than quoted: a short side drawn independently of
    short interest holds both tail deciles, i.e. 20% of it at the specials
    rate."""
    share = 2.0 * DEFAULT_SCHEDULE.tail_fraction
    no_tilt = share * HARD_TO_BORROW_BPS_PER_YEAR + (1.0 - share) * GENERAL_COLLATERAL_BPS_PER_YEAR
    assert no_tilt == pytest.approx(113.2)


# --- 3: the operational consequence, unchanged from lazy_prices' ------------


def test_any_non_zero_borrow_rate_parks_this_registration(report):
    """WHAT ADOPTING A RATE DOES, as an executable argument rather than a claim.

    UNTIL 2026-09-06 this test was named ..._would_park_... and was the reason
    NOTHING was adopted. The repo owner then authorized adoption, knowing that
    consequence, so the tense changes and the assertion does not: every
    candidate rate -- including the one this family's own measurement produced
    and now charges -- re-hashes config_fingerprint away from the value the
    live row was registered under, detect_config_drift returns a reason, and
    the runner parks the row as spec_drift.

    The candidate rates are read from the measurement artifact, not retyped,
    so this test cannot drift away from the numbers it is about."""

    class _Row:
        config_fingerprint = REGISTERED_ROW_CONFIG_FINGERPRINT
        family_key = "short_interest_ratio"
        started_at = "2026-09-03"
        config_snapshot_json = "{}"

    # The 0.0 config the row was actually registered on still hashes to the
    # row's own fingerprint — proof that this file's constant is the real one
    # and not a value invented to make the rest of the test pass.
    assert (
        config_fingerprint(CrossSectionalConfig(cost_bps=5.0, financing_bps_per_year=0.0))
        == REGISTERED_ROW_CONFIG_FINGERPRINT
    )

    measured = report["measured_financing_bps_per_year"]
    candidates = [
        measured["registered_hedged_book"],
        measured["long_short_books_si_ratio_h21"],
        financing_bps_for_long_short_book(GENERAL_COLLATERAL_BPS_PER_YEAR),
        financing_bps_for_long_short_book(HARD_TO_BORROW_BPS_PER_YEAR),
        # The live config itself, now that it carries the adopted rate — the
        # case that is no longer hypothetical.
        default_short_interest_config().financing_bps_per_year,
    ]
    for rate in candidates:
        assert rate > 0.0
        drifted = CrossSectionalConfig(cost_bps=5.0, financing_bps_per_year=rate)
        assert config_fingerprint(drifted) != REGISTERED_ROW_CONFIG_FINGERPRINT
        assert (
            detect_config_drift(_Row(), config_fingerprint(drifted), config_identity(drifted))
            is not None
        ), f"financing_bps_per_year={rate} must be detected as config drift"


# --- 4: the measurement artifact says what the report says it says -----------


def test_the_live_config_now_charges_exactly_the_rate_that_was_measured(report):
    """THE ADOPTION PIN, and the inverse of what this test asserted before
    2026-09-06.

    It used to be test_the_measurement_did_not_adopt_anything: the live config
    had to still be the 0.0 one, because a run that quietly changed the family
    default would be exactly the "cost fix as a side effect of research" this
    project refuses. Adoption is now explicit and authorized, so the guard
    changes direction rather than being removed — the live config must equal
    the rate the MEASUREMENT ARTIFACT reports for the REGISTERED spec, read
    from that artifact rather than retyped. A future edit that nudged the
    constant to a friendlier number, or that pointed it at one of the
    long_short specs' rates, still fails here."""
    live = default_short_interest_config().financing_bps_per_year
    assert live == ADOPTED_FINANCING_BPS_PER_YEAR
    assert live == report["measured_financing_bps_per_year"]["registered_hedged_book"]
    # ...and it is the REGISTERED (hedged) book's rate, not the long_short
    # one — the distinction this whole file exists to defend.
    assert live != report["measured_financing_bps_per_year"]["long_short_books_si_ratio_h21"]
    assert live == pytest.approx(
        report["composition"][REGISTERED_SPEC_ID]["implied_financing_bps_per_year"]["mean"],
        abs=5e-5,
    )
    # The baseline arm is history and stays 0.0; it is also the config the
    # LIVE ROW is registered under, which is why adopting drifts it.
    baseline = report["arms"][0]
    assert baseline["financing_bps_per_year"] == 0.0
    assert baseline["config_fingerprint"] == REGISTERED_ROW_CONFIG_FINGERPRINT
    assert config_fingerprint(default_short_interest_config()) != REGISTERED_ROW_CONFIG_FINGERPRINT


def test_the_registered_book_is_measured_below_the_no_tilt_baseline(report):
    """THE MEASURED RESULT, pinned in the direction it came out rather than
    to a digit: the registered hedged book's short side holds FEWER
    hard-to-borrow names than a short drawn at random, because its long leg
    removes part of the low-short-interest tail from the shorted side.

    Pinned as an inequality against the schedule's own no-tilt reference so
    it survives a re-measurement on new data while still failing loudly if
    the sign of the finding ever flips."""
    c = report["composition"][REGISTERED_SPEC_ID]
    assert c["portfolio"] == "long_universe_hedged"
    assert c["n_formations_sir_covered"] > 0
    no_tilt_share = 2.0 * DEFAULT_SCHEDULE.tail_fraction
    assert c["short_tail_share_notional"]["mean"] < no_tilt_share


def test_the_long_short_books_are_measured_far_above_it(report):
    """The other half of the same finding: the specs borrow_cost's sentence
    is actually about DO sit in the expensive tail, essentially entirely."""
    for spec_id, c in report["composition"].items():
        if c.get("portfolio") != "long_short" or not c.get("n_formations_sir_covered"):
            continue
        assert c["short_tail_share_notional"]["mean"] > 2.0 * DEFAULT_SCHEDULE.tail_fraction, (
            f"{spec_id} was expected to sit above the no-tilt baseline"
        )
    ls_ratio = report["composition"]["si_ratio_ls_h21"]
    assert ls_ratio["implied_financing_bps_per_year"]["mean"] > (
        report["composition"][REGISTERED_SPEC_ID]["implied_financing_bps_per_year"]["mean"]
    )


def test_every_reported_book_rate_is_reproducible_from_its_own_tail_share(report):
    """The schedule is a two-rate step function, so the notional-weighted book
    rate must be recoverable from the notional-weighted tail share and the two
    rates. Any gap is the NaN->GC names plus mean-of-products vs
    product-of-means across formations, both small; a large one would mean the
    per-name rate assignment is not the schedule's."""
    for spec_id, c in report["composition"].items():
        if not c.get("n_formations_sir_covered"):
            continue
        share = c["short_tail_share_notional"]["mean"]
        hand = (
            share * HARD_TO_BORROW_BPS_PER_YEAR
            + (1.0 - share) * GENERAL_COLLATERAL_BPS_PER_YEAR
        )
        got = c["book_bps_on_short_side"]["mean"]
        assert abs(got - hand) < 0.05 * HARD_TO_BORROW_BPS_PER_YEAR, (
            f"{spec_id}: book rate {got:.2f} is not reproducible from tail share {share:.4f} "
            f"(hand-derived {hand:.2f})"
        )


def test_the_before_after_arms_share_one_data_build(report):
    """Every arm must have faced the SAME prices and the SAME formations --
    fa614ac showed this family's Sharpe moves between runs of identical code
    when the prices underneath move, so a before/after built from two fetches
    would be measuring that instead of the borrow charge."""
    assert report["data_build"]["one_shared_fetch"] is True
    baseline = report["arms"][0]["specs"]
    for arm in report["arms"][1:]:
        for spec_id, v in arm["specs"].items():
            assert v["n_formations"] == baseline[spec_id]["n_formations"]
            assert v["n_trading_days"] == baseline[spec_id]["n_trading_days"]
            assert v["total_cost_drag"] == pytest.approx(baseline[spec_id]["total_cost_drag"])


def test_only_the_baseline_arm_charges_no_financing(report):
    """A cost arm that accrued nothing would make the whole table vacuous."""
    assert report["arms"][0]["specs"][REGISTERED_SPEC_ID]["total_financing_drag"] == 0.0
    for arm in report["arms"][1:]:
        drag = arm["specs"][REGISTERED_SPEC_ID]["total_financing_drag"]
        assert drag > 0.0, f"arm {arm['label']!r} charged no financing at all"
