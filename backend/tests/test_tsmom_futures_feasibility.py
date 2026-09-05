"""data/research_runs/run_tsmom_futures_feasibility.py -- TSMOM prep Step 4,
Option 2 (real futures) feasibility scoping -- needs test coverage for one
specific reason above all others: it implements a PUBLISHED FORMULA, and
CLAUDE.md's standing rule is that a published formula is never implemented from
memory and never trusted before it reproduces a synthetic case with a KNOWN
TRUE ANSWER.

Same convention as tests/test_combined_universe_effective_breadth.py (import
the runner by path, exercise its pure functions with no network fetch) and
tests/test_global_effective_n_runner.py.

WHAT IS PINNED HERE, and why each matters:

 1. THE KNOWN-ANSWER VALIDATION ITSELF. synthetic_two_contract_roll() is built
    so that every expected value is derivable by hand -- a true underlying path
    U = [100..105], one contract quoted at exactly U and another at exactly
    1.10*U, rolled at the close of day 2. The true cumulative return is exactly
    5%, the naive splice's is exactly 15.5%, and the injected roll artifact has
    the closed form 113.3 * 10.2 / (102 * 112.2). Those are asserted here
    against LITERAL constants typed from the arithmetic, not against whatever
    the module's own fixture dict happens to say -- otherwise a wrong fixture
    and a wrong implementation could agree with each other and the test would
    pass. This is the check the whole run's credibility rests on.

 2. THE EQUIVALENCE CLAIM. The run's central methodological recommendation is
    that MOP (2012) Section 2.1's chained within-contract returns and
    ratio/proportional back-adjustment are THE SAME OBJECT. That claim is
    load-bearing (it is why a price series and a return series can be used
    interchangeably downstream) and it is asserted in the report, so it is
    proven here on a randomised multi-roll panel, not only on the one
    hand-built fixture.

 3. THE REJECTION CLAIM. The run recommends AGAINST arithmetic/"Panama"
    back-adjustment, and names a real paid vendor (Norgate) that ships that
    form. A recommendation against something must be falsifiable: if Panama
    adjustment ever DID reproduce the true returns, the report would be wrong
    and must not print. Pinned as an explicit inequality.

 4. THE ROLL-DAY CONTRACT. chained_contract_daily_returns must never compute a
    return ACROSS two different contracts -- that is the single defect this
    whole run exists to characterise. Pinned two ways: the roll-day return must
    equal the incoming contract's own return, and a roll with no overlap day
    must RAISE rather than silently produce a number.

 5. THE SWITCH DETECTOR'S FALSE-POSITIVE GUARD. detect_switch_blocks discards
    exact-equality runs shorter than MIN_SWITCH_BLOCK_TRADING_DAYS because
    low-decimal markets genuinely produce coincidental price collisions (seen
    live for CL=F/CLV26.NYM during development). Without that guard the run
    would report rolls that never happened. Pinned against a synthetic panel
    containing a deliberate one-day collision.

 6. THE PERSISTED REPORT'S OWN INTERNAL CONSISTENCY. If this run's JSON is
    present in the checkout, its headline numbers are re-derived from ITS OWN
    stored primitives rather than re-trusted at face value.

 7. A REFUTED CLAIM, PINNED AS THE THING THAT REPLACED IT. An earlier draft of
    the run asserted that the naive splice's roll-day return would stand out as
    a statistical outlier. Measurement refuted it -- robust |z| 0.65 for the
    splice against 0.70 for the true return, i.e. the fabricated day is the
    LESS remarkable of the two -- and the report was rewritten around the
    refutation, because that is the stronger and more alarming finding: a
    ~0.9 percentage-point fabrication is invisible to any outlier filter. The
    test now pins THAT regime rather than the direction the draft assumed, so
    that if a future rerun ever made the splice a clear outlier, the report's
    "no outlier filter can find it" sentence would fail loudly instead of
    quietly becoming false.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
RUNNER = BACKEND / "data" / "research_runs" / "run_tsmom_futures_feasibility.py"
REPORT_JSON = BACKEND / "data" / "research_runs" / "tsmom_futures_feasibility_2026-09-05.json"


@pytest.fixture(scope="module")
def runner():
    """Import the runner by path -- it lives under data/research_runs/, not
    app/, so it is not importable by name. Importing it executes the WORKTREE
    BINDING GUARD and the module-level imports but not main(), so this is a
    fast, network-free import."""
    spec = importlib.util.spec_from_file_location("_run_tsmom_futures_feasibility", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1. THE KNOWN-ANSWER VALIDATION -- against literals, not against the fixture
# ---------------------------------------------------------------------------

# Typed fresh from the arithmetic in synthetic_two_contract_roll()'s docstring.
# Deliberately NOT read from the module: a test that compares the module's
# fixture against the module's implementation proves only that they agree with
# each other, which is exactly the failure mode CLAUDE.md's formula rule exists
# to catch.
TRUE_DAILY_RETURNS = [
    np.nan,
    101.0 / 100.0 - 1.0,
    102.0 / 101.0 - 1.0,
    103.0 / 102.0 - 1.0,
    104.0 / 103.0 - 1.0,
    105.0 / 104.0 - 1.0,
]
TRUE_CUMULATIVE_RETURN = 0.05
TRUE_RATIO_ADJUSTED_PRICES = [110.0, 111.1, 112.2, 113.3, 114.4, 115.5]
TRUE_NAIVE_SPLICE_TOTAL_RETURN = 0.155
TRUE_ROLL_ARTIFACT = 113.3 * (112.2 - 102.0) / (102.0 * 112.2)
TRUE_PANAMA_DAY1_RETURN = 111.2 / 110.2 - 1.0
TOL = 1e-12


def test_chained_returns_reproduce_the_hand_derived_answer(runner):
    fixture = runner.synthetic_two_contract_roll()
    got = runner.chained_contract_daily_returns(
        fixture["closes_by_contract"], fixture["holding"]
    )
    assert np.isnan(got.iloc[0]), "the first date has no previous close and must be NaN"
    np.testing.assert_allclose(got.to_numpy()[1:], np.array(TRUE_DAILY_RETURNS[1:]), atol=TOL)
    cumulative = float((1.0 + got.dropna()).prod() - 1.0)
    assert abs(cumulative - TRUE_CUMULATIVE_RETURN) < TOL, (
        f"the true cumulative return of a path running 100 -> 105 is exactly 5%; got {cumulative}"
    )


def test_ratio_back_adjusted_prices_reproduce_the_hand_derived_answer(runner):
    fixture = runner.synthetic_two_contract_roll()
    got = runner.ratio_back_adjusted_prices(fixture["closes_by_contract"], fixture["holding"])
    np.testing.assert_allclose(got.to_numpy(), np.array(TRUE_RATIO_ADJUSTED_PRICES), atol=1e-10)


def test_naive_splice_is_inflated_by_exactly_the_basis(runner):
    """The splice's total return is not merely 'too high' -- on this fixture it
    is the true return inflated by EXACTLY the 10% basis, 1.155/1.05 = 1.10.
    Pinning the exact relationship rather than an inequality is what makes this
    evidence about the mechanism rather than about the direction."""
    fixture = runner.synthetic_two_contract_roll()
    closes, holding = fixture["closes_by_contract"], fixture["holding"]
    naive = runner.naive_spliced_prices(closes, holding)
    total = float(naive.iloc[-1] / naive.iloc[0] - 1.0)
    assert abs(total - TRUE_NAIVE_SPLICE_TOTAL_RETURN) < TOL
    assert abs((1.0 + total) / (1.0 + TRUE_CUMULATIVE_RETURN) - 1.10) < TOL


def test_roll_artifact_matches_its_closed_form_and_is_zero_elsewhere(runner):
    fixture = runner.synthetic_two_contract_roll()
    artifact = runner.roll_artifact_per_date(
        fixture["closes_by_contract"], fixture["holding"]
    )
    assert abs(float(artifact.iloc[3]) - TRUE_ROLL_ARTIFACT) < TOL
    off_roll = artifact.drop(artifact.index[3]).to_numpy()
    assert np.nanmax(np.abs(off_roll)) < TOL, (
        "the artifact must be exactly zero on every non-roll day -- a construction that leaks "
        "adjustment into ordinary days would corrupt the whole series, not just the rolls"
    )


def test_validate_against_synthetic_passes_and_reports_no_failures(runner):
    """The gate main() itself calls before touching any real data."""
    result = runner.validate_against_synthetic()
    assert result["failures"] == [], f"synthetic validation failed on {result['failures']}"
    assert result["worst_delta"] <= result["tolerance"]
    assert abs(result["measured_cumulative_return"] - TRUE_CUMULATIVE_RETURN) < TOL
    assert abs(result["measured_roll_artifact"] - TRUE_ROLL_ARTIFACT) < TOL


# ---------------------------------------------------------------------------
# 2. THE EQUIVALENCE CLAIM -- on a randomised multi-roll panel
# ---------------------------------------------------------------------------


def _random_multi_roll_panel(seed: int = 20260905, n_days: int = 240, n_contracts: int = 5):
    """A panel with FOUR rolls and randomly-drawn, materially different bases
    per contract, so the equivalence is not being checked only on the one
    hand-built two-contract case whose numbers were chosen to be tidy."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    underlying = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n_days))), index=dates)
    closes, holding_values = {}, []
    boundaries = np.linspace(0, n_days, n_contracts + 1).astype(int)
    for c in range(n_contracts):
        # A distinct, sizeable basis per contract so a bug that ignored the
        # adjustment could not pass by the bases happening to be near 1.
        basis = 1.0 + float(rng.uniform(-0.08, 0.08))
        closes[f"C{c}"] = underlying * basis
    for c in range(n_contracts):
        holding_values.extend([f"C{c}"] * (boundaries[c + 1] - boundaries[c]))
    return closes, pd.Series(holding_values, index=dates)


def test_ratio_back_adjustment_equals_mop_chained_returns(runner):
    """The run's central methodological claim, proven rather than asserted."""
    closes, holding = _random_multi_roll_panel()
    chained = runner.chained_contract_daily_returns(closes, holding)
    adjusted = runner.ratio_back_adjusted_prices(closes, holding)
    np.testing.assert_allclose(
        adjusted.pct_change().to_numpy()[1:], chained.to_numpy()[1:], atol=1e-12
    )


def test_chained_returns_recover_the_true_underlying_path(runner):
    """Independent of any adjustment machinery: because every contract in the
    panel is a constant multiple of one true underlying, a correct construction
    must return the UNDERLYING's own daily returns, with every contract's basis
    cancelling. This is a known true answer for a 5-contract, 4-roll case."""
    closes, holding = _random_multi_roll_panel()
    chained = runner.chained_contract_daily_returns(closes, holding)
    # Recover the underlying from any contract by removing its constant basis.
    underlying = closes["C0"] / float(closes["C0"].iloc[0]) * 100.0
    np.testing.assert_allclose(
        chained.to_numpy()[1:], underlying.pct_change().to_numpy()[1:], atol=1e-12
    )


# ---------------------------------------------------------------------------
# 3. THE REJECTION CLAIM -- Panama must demonstrably NOT work
# ---------------------------------------------------------------------------


def test_panama_back_adjustment_demonstrably_distorts_returns(runner):
    """The report recommends AGAINST arithmetic back-adjustment and names a
    real paid vendor that ships it. If this ever passed silently -- i.e. if
    Panama DID reproduce the truth -- that recommendation would be unfounded
    and must not be published."""
    fixture = runner.synthetic_two_contract_roll()
    panama = runner.panama_back_adjusted_prices(
        fixture["closes_by_contract"], fixture["holding"]
    )
    day1 = float(panama.pct_change().iloc[1])
    assert abs(day1 - TRUE_PANAMA_DAY1_RETURN) < TOL, "hand-derived Panama value not reproduced"
    assert abs(day1 - (101.0 / 100.0 - 1.0)) > 1e-6, (
        "arithmetic back-adjustment must NOT reproduce the true 1% day-1 return; if it does, "
        "the run's recommendation against it is wrong"
    )


def test_panama_and_ratio_disagree_on_a_multi_roll_panel(runner):
    """Not only on the tidy fixture."""
    closes, holding = _random_multi_roll_panel()
    ratio = runner.ratio_back_adjusted_prices(closes, holding).pct_change()
    panama = runner.panama_back_adjusted_prices(closes, holding).pct_change()
    assert float(np.nanmax(np.abs(ratio.to_numpy() - panama.to_numpy()))) > 1e-6


# ---------------------------------------------------------------------------
# 4. THE ROLL-DAY CONTRACT -- never a return across two contracts
# ---------------------------------------------------------------------------


def test_roll_day_return_is_the_incoming_contracts_own_return(runner):
    fixture = runner.synthetic_two_contract_roll()
    closes, holding = fixture["closes_by_contract"], fixture["holding"]
    chained = runner.chained_contract_daily_returns(closes, holding)
    roll_date = holding.index[3]
    prev_date = holding.index[2]
    incoming = closes["B"]
    expected = float(incoming.loc[roll_date] / incoming.loc[prev_date] - 1.0)
    assert abs(float(chained.loc[roll_date]) - expected) < TOL, (
        "the roll-day return must come entirely from the INCOMING contract; computing it "
        "across the two contracts is precisely the defect this run characterises"
    )


def test_roll_without_an_overlap_day_raises(runner):
    """A roll needs a day on which the incoming contract is already quoted. If
    it is absent the construction must REFUSE, not emit a NaN that a downstream
    dropna() would quietly swallow."""
    dates = pd.date_range("2020-01-01", periods=4, freq="D")
    closes = {
        "A": pd.Series([100.0, 101.0], index=dates[:2]),
        # B starts only on the roll date itself -- no previous close exists.
        "B": pd.Series([110.0, 111.0], index=dates[2:]),
    }
    holding = pd.Series(["A", "A", "B", "B"], index=dates)
    with pytest.raises(ValueError, match="overlap day"):
        runner.chained_contract_daily_returns(closes, holding)


def test_unknown_contract_in_holding_raises(runner):
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    closes = {"A": pd.Series([100.0, 101.0, 102.0], index=dates)}
    holding = pd.Series(["A", "A", "MISSING"], index=dates)
    with pytest.raises(KeyError):
        runner.chained_contract_daily_returns(closes, holding)


# ---------------------------------------------------------------------------
# 5. THE SWITCH DETECTOR'S FALSE-POSITIVE GUARD
# ---------------------------------------------------------------------------


def test_detect_switch_blocks_finds_a_real_block_and_rejects_a_collision(runner):
    """A one-day coincidental exact price match must NOT be reported as a roll.
    This was observed live (CL=F matching CLV26.NYM on isolated days in a month
    when CLV26 could not have been the front contract), and without the guard
    the run would publish rolls that never happened."""
    dates = pd.date_range("2020-01-01", periods=40, freq="D")
    splice = pd.Series(np.arange(100.0, 140.0), index=dates)
    contract = splice.copy() + 5.0
    # a genuine 15-day identity block at the end ...
    contract.iloc[25:] = splice.iloc[25:]
    # ... plus a single coincidental collision far away from it
    contract.iloc[3] = splice.iloc[3]

    blocks = runner.detect_switch_blocks(splice, contract, min_block=10)
    assert len(blocks) == 1, f"expected exactly one real block, got {blocks}"
    assert blocks[0]["first_date"] == str(dates[25].date())
    assert blocks[0]["n_trading_days"] == 15

    # With the guard removed the collision IS picked up -- proving the guard is
    # what suppresses it, not some other accident of the fixture.
    unguarded = runner.detect_switch_blocks(splice, contract, min_block=1)
    assert len(unguarded) == 2


def test_detect_switch_blocks_requires_exact_equality(runner):
    """A splice republishes its constituent; it does not approximate it. A
    near-match must not count, or the detector would 'find' a switch wherever
    two contracts merely traded close together."""
    dates = pd.date_range("2020-01-01", periods=30, freq="D")
    splice = pd.Series(np.arange(100.0, 130.0), index=dates)
    contract = splice + 1e-9
    assert runner.detect_switch_blocks(splice, contract, min_block=5) == []


# ---------------------------------------------------------------------------
# 6. THE PERSISTED REPORT'S OWN INTERNAL CONSISTENCY
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REPORT_JSON.exists(), reason="this run's report is not in this checkout")
def test_persisted_report_is_internally_consistent():
    """Re-derive the persisted report's headline claims from ITS OWN stored
    primitives instead of re-trusting them at face value."""
    payload = json.loads(REPORT_JSON.read_text())

    sv = payload["synthetic_validation"]
    assert sv["failures"] == []
    assert sv["worst_delta"] <= sv["tolerance"]
    # The three headline synthetic numbers must still equal the hand arithmetic.
    assert abs(sv["measured_cumulative_return"] - TRUE_CUMULATIVE_RETURN) < TOL
    assert abs(sv["measured_naive_splice_total_return"] - TRUE_NAIVE_SPLICE_TOTAL_RETURN) < TOL
    assert abs(sv["measured_roll_artifact"] - TRUE_ROLL_ARTIFACT) < TOL
    assert sv["panama_demonstrably_differs"] is True

    # PROOF_3: every reported artifact must equal splice-return minus true
    # return, recomputed from the stored per-switch primitives.
    n_switches = 0
    for pair in payload["switch_dates_and_artifacts"]["pairs"]:
        for s in pair.get("switches", []):
            n_switches += 1
            assert abs(
                s["artifact_pct_points"]
                - (s["splice_return_pct"] - s["contract_own_return_pct"])
            ) < 1e-9, f"{pair['splice']}/{pair['contract']} artifact is not its own difference"
            assert s["block_trading_days"] >= payload["switch_dates_and_artifacts"]["pairs"][0][
                "min_block_trading_days"
            ]
    assert n_switches > 0, "the report claims measured roll artifacts but persisted none"

    # The verdict must be the one the module defines, not free text that drifted.
    assert payload["verdict_code"] == "FEASIBLE_ONLY_WITH_A_PAID_DATA_DECISION"

    # The expired-contract finding is the load-bearing reason self-building
    # fails; if retention ever improved, the verdict would need revisiting, so
    # pin that it is still a small minority.
    for root, r in payload["expired_contract_retention"].items():
        assert r["n_resolved"] < r["n_probed"] / 2, (
            f"{root}: Yahoo now retains {r['n_resolved']}/{r['n_probed']} contract months -- "
            "the 'cannot rebuild a historical chain' conclusion must be re-examined"
        )

    poc = payload["proof_of_concept"]
    if poc.get("resolved"):
        # The equivalence must hold on the REAL prices too, not only synthetic.
        assert poc["ratio_adjusted_equals_chained_max_delta"] < 1e-10

        # The artifact must BE the difference between the two roll-date
        # returns, re-derived from the stored primitives rather than trusted.
        assert abs(
            poc["artifact_on_roll_date_pct_points"]
            - (
                poc["naive_splice_return_on_roll_date_pct"]
                - poc["constructed_return_on_roll_date_pct"]
            )
        ) < 1e-9

        # THE CORRECTED CLAIM. An earlier draft asserted the naive splice's
        # roll-day return would be a BIGGER outlier than the constructed one.
        # Measurement refuted that (|z| 0.65 vs 0.70), the report was rewritten
        # around the refutation, and this test now pins the finding that
        # replaced it: the artifact is NOT visible as a day-level outlier, which
        # is why no filter can remove it. If a future rerun ever made the splice
        # a clear outlier, the report's "no outlier filter can find it" sentence
        # would be wrong and must be revisited -- so this asserts the regime,
        # not merely a direction.
        assert abs(poc["naive_splice_robust_z_on_roll_date"]) < 3.0, (
            "the report states the splice's roll-day artifact is invisible to an outlier "
            "filter; a robust |z| this large would contradict it"
        )

        # And the artifact must be SYSTEMATICALLY SIGNED, which is the property
        # that makes it a bias rather than noise that averages away.
        dist = poc["artifact_distribution_over_all_candidate_roll_dates"]
        assert dist["share_positive"] > 0.95, (
            "the report's central claim is that the roll artifact does not average away; if "
            "its sign were mixed that claim would be unfounded"
        )
        assert dist["n_candidate_dates"] > 100

        # CHECK 2: the constructed series must look like the market it claims
        # to be, not like a smoothed or broken series.
        cs = poc.get("cash_index_sanity_check") or {}
        if cs:
            assert cs["return_correlation"] > 0.95, (
                "a correctly constructed E-mini S&P series must track the cash index closely; "
                "MOP p.231 says exactly this"
            )
            assert abs(cs["constructed_annualized_vol"] - cs["cash_annualized_vol"]) < 0.03
