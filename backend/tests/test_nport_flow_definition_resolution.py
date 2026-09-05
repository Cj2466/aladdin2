"""data/research_runs/run_nport_flow_definition_resolution.py -- resolution of the
Lou (2012) Eq.(1) vs Form N-PORT Item B.6 flow-definition question left open by
nport_flow_feasibility_2026-09-05.txt PROOF_4.

Same convention as tests/test_nport_flow_feasibility.py: import the runner by
path, exercise its pure functions, and pin the real numbers against the real
data committed alongside it, so a regression is caught with NO network call.

WHAT IS PINNED HERE:

 1. HAND-DERIVABLE ARITHMETIC for all three flow definitions, each checked
    against a case whose answer is computed by hand in the assertion itself.

 2. THE STRUCTURAL IDENTITY, AGAINST SYNTHETIC FUNDS WITH A KNOWN TRUE ANSWER.
    This run's whole conclusion rests on the claim

        EQ1_dollars == (a - c) - (D - b)                                  (I)

    and its corollary, that under Lou's OWN stated full-reinvestment assumption
    (D == b) Eq.(1) collapses EXACTLY onto B.6 EXTERNAL (a - c). CLAUDE.md
    forbids trusting a published formula before it reproduces a hand-derivable
    known-answer case, so these are checked on simulated funds built from
    primitives where the true external flow is known by construction -- NOT on
    the real data the conclusion is drawn from.

 3. THE DEPENDENCY-FREE STATISTICS HELPERS (rank/Spearman/OLS/decile) against
    known answers. The OLS in particular carries a real finding (a unit loading
    on reinvestment), so a silent solver bug would corrupt the conclusion.

 4. THE REAL-PANEL FINDINGS, against the committed 49,705-row derived panel:
    Eq.(1) tracks B.6 EXTERNAL better than B.6 NET on every metric; the sign
    disagreement concentrates in the economic noise floor; the share-class
    explanation is refuted; the December/bond-fund distribution fingerprints
    are present.

 5. THE PROOF_4 RESOLUTION ITSELF, against the two real sample filings the
    PRIOR run committed. test_nport_flow_feasibility.py deliberately pins the
    sign DISAGREEMENT (vs B.6 NET) so it cannot be silently "fixed"; this file
    pins the complementary fact -- that the same fund-quarter AGREES under
    B.6 EXTERNAL -- so the resolution cannot be silently lost either. Both
    tests must keep passing: they are two halves of one finding, not a
    contradiction.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
RUNNER = BACKEND / "data" / "research_runs" / "run_nport_flow_definition_resolution.py"
REPORT_JSON = BACKEND / "data" / "research_runs" / "nport_flow_definition_resolution_2026-09-05.json"

TOL = 1e-9


@pytest.fixture(scope="module")
def runner():
    spec = importlib.util.spec_from_file_location("_run_nport_flow_definition_resolution", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def panel(runner):
    return runner.load_panel()


# ---------------------------------------------------------------------------
# 1. HAND-DERIVABLE ARITHMETIC
# ---------------------------------------------------------------------------


def test_compound_quarterly_return_hand_derived(runner):
    assert abs(runner.compound_quarterly_return_pct(0.0, 0.0, 0.0)) < TOL
    assert abs(runner.compound_quarterly_return_pct(100.0, 0.0, 0.0) - 100.0) < TOL
    # 1.1^3 - 1 = 33.1%, not 30%
    assert abs(runner.compound_quarterly_return_pct(10.0, 10.0, 10.0) - 33.1) < 1e-9


def test_lou_eq1_flow_dollars_hand_derived(runner):
    # TNA grew exactly by the fund's own return -> zero flow.
    assert abs(runner.lou_eq1_flow_dollars(100.0, 105.0, 5.0)) < TOL
    # TNA_prev=100, return 0%, TNA_curr=110 -> +10 dollars of flow.
    assert abs(runner.lou_eq1_flow_dollars(100.0, 110.0, 0.0) - 10.0) < TOL
    # MGN is subtracted: 4 of that 10 came from a merger -> 6 of real flow.
    assert abs(runner.lou_eq1_flow_dollars(100.0, 110.0, 0.0, mgn=4.0) - 6.0) < TOL


def test_b6_definitions_hand_derived(runner):
    # a=100, b=5, c=40
    assert abs(runner.b6_net_flow_dollars(100.0, 5.0, 40.0) - 65.0) < TOL
    assert abs(runner.b6_external_flow_dollars(100.0, 40.0) - 60.0) < TOL
    # The ONLY difference between the two is Item B.6.b, by construction.
    assert (
        abs((runner.b6_net_flow_dollars(100.0, 5.0, 40.0) - runner.b6_external_flow_dollars(100.0, 40.0)) - 5.0)
        < TOL
    )


# ---------------------------------------------------------------------------
# 2. THE STRUCTURAL IDENTITY, ON SYNTHETIC FUNDS WITH A KNOWN TRUE ANSWER
# ---------------------------------------------------------------------------


def test_identity_holds_exactly_on_synthetic_funds(runner):
    """Identity (I): EQ1 == (a - c) - (D - b), exactly, by construction."""
    for kwargs in (
        {"tna_prev": 1_000.0, "gross_return_pct": 5.0, "subscriptions": 100.0,
         "redemptions": 40.0, "distributions": 20.0, "reinvestment_rate": 0.0},
        {"tna_prev": 1_000.0, "gross_return_pct": -8.0, "subscriptions": 10.0,
         "redemptions": 300.0, "distributions": 50.0, "reinvestment_rate": 0.5},
        # parameterised to the real PROOF_4 fund-quarter's own magnitudes
        {"tna_prev": 29_248_363_673.15, "gross_return_pct": 19.23, "subscriptions": 2_792_484_013.09,
         "redemptions": 2_804_583_336.55, "distributions": 58_438_684.29, "reinvestment_rate": 0.2834},
        {"tna_prev": 5.0, "gross_return_pct": 0.0, "subscriptions": 0.0,
         "redemptions": 0.0, "distributions": 0.0, "reinvestment_rate": 1.0},
    ):
        fq = runner.simulate_fund_quarter(**kwargs)
        # RELATIVE tolerance: these fund-quarters span $5 to $29 BILLION of net
        # assets, so an absolute dollar tolerance is meaningless at one end and
        # unsatisfiable at the other. 1e-12 of TNA is still ~4,000x tighter than
        # the float64 rounding floor (the observed residual on the $29bn case is
        # 2.2e-16 of TNA), so this catches any real error, not just a gross one.
        tol = 1e-12 * max(fq.tna_prev, 1.0)
        assert abs(runner.identity_residual(fq)) < tol, f"identity (I) failed for {kwargs}"


def test_full_reinvestment_makes_eq1_equal_b6_external(runner):
    """Corollary (III) -- THE CENTRAL CLAIM OF THIS RUN. Under Lou's own stated
    assumption that investors reinvest all distributions, Eq.(1) IS B.6
    EXTERNAL (a - c). It is not an approximation of it; it is equal to it."""
    fq = runner.simulate_fund_quarter(
        tna_prev=10_000.0, gross_return_pct=7.5, subscriptions=900.0,
        redemptions=1_400.0, distributions=250.0, reinvestment_rate=1.0,
    )
    eq1 = runner.lou_eq1_flow_dollars(fq.tna_prev, fq.tna_curr, fq.quarterly_return_pct)
    ext = runner.b6_external_flow_dollars(fq.sales, fq.redemption)
    assert abs(eq1 - ext) < 1e-6
    assert abs(eq1 - fq.true_external_flow) < 1e-6
    assert abs(eq1 - (-500.0)) < 1e-6  # 900 - 1400, computed by hand


def test_partial_reinvestment_biases_eq1_down_by_cash_distributions(runner):
    """The bias is EXACTLY the distributions paid out in cash, and it makes
    Eq.(1) understate flow -- which is why the prior run's fund-quarter looked
    like an outflow under Eq.(1) and an inflow under B.6 NET."""
    fq = runner.simulate_fund_quarter(
        tna_prev=10_000.0, gross_return_pct=7.5, subscriptions=1_000.0,
        redemptions=1_000.0, distributions=200.0, reinvestment_rate=0.25,
    )
    eq1 = runner.lou_eq1_flow_dollars(fq.tna_prev, fq.tna_curr, fq.quarterly_return_pct)
    ext = runner.b6_external_flow_dollars(fq.sales, fq.redemption)
    net = runner.b6_net_flow_dollars(fq.sales, fq.reinvestment, fq.redemption)
    cash_distributions = fq.distributions - fq.reinvestment  # 200 - 50 = 150
    assert abs(cash_distributions - 150.0) < TOL
    assert abs(ext - 0.0) < 1e-6           # true external flow is exactly zero
    assert abs(eq1 - (-150.0)) < 1e-6      # Eq.(1) reads it as a 150 OUTFLOW
    assert abs(net - 50.0) < 1e-6          # B.6 NET reads it as a 50 INFLOW
    # This is the prior run's sign disagreement, reproduced from primitives:
    assert eq1 < 0 < net
    # ...and it vanishes against B.6 EXTERNAL, which is the run's conclusion.
    assert not (eq1 < 0 < ext)


def test_inequality_chain_holds_on_synthetic_funds(runner):
    """Inequality (II): EQ1 <= (a - c) <= (a + b - c) whenever distributions are
    non-negative. Any real-data violation is therefore measurement error, not a
    different economic story -- which is how this run reads the 33.7% of real
    fund-quarters that violate it."""
    for rate in (0.0, 0.3, 0.7, 1.0):
        for dist in (0.0, 10.0, 250.0):
            fq = runner.simulate_fund_quarter(
                tna_prev=10_000.0, gross_return_pct=3.0, subscriptions=500.0,
                redemptions=200.0, distributions=dist, reinvestment_rate=rate,
            )
            eq1 = runner.lou_eq1_flow_dollars(fq.tna_prev, fq.tna_curr, fq.quarterly_return_pct)
            ext = runner.b6_external_flow_dollars(fq.sales, fq.redemption)
            net = runner.b6_net_flow_dollars(fq.sales, fq.reinvestment, fq.redemption)
            assert eq1 <= ext + 1e-6 <= net + 1e-6


def test_simulate_fund_quarter_rejects_impossible_inputs(runner):
    with pytest.raises(ValueError):
        runner.simulate_fund_quarter(tna_prev=100.0, gross_return_pct=0.0, subscriptions=0.0,
                                     redemptions=0.0, distributions=10.0, reinvestment_rate=1.5)
    with pytest.raises(ValueError):
        runner.simulate_fund_quarter(tna_prev=100.0, gross_return_pct=0.0, subscriptions=0.0,
                                     redemptions=0.0, distributions=-1.0, reinvestment_rate=0.5)


# ---------------------------------------------------------------------------
# 3. THE DEPENDENCY-FREE STATISTICS HELPERS, AGAINST KNOWN ANSWERS
# ---------------------------------------------------------------------------


def test_pearson_and_spearman_known_answers(runner):
    assert abs(runner.pearson([1, 2, 3, 4], [2, 4, 6, 8]) - 1.0) < 1e-12
    assert abs(runner.pearson([1, 2, 3, 4], [8, 6, 4, 2]) + 1.0) < 1e-12
    # Monotone but non-linear: Spearman is exactly 1, Pearson is not.
    xs, ys = [1, 2, 3, 4, 5], [1, 4, 9, 16, 25]
    assert abs(runner.spearman(xs, ys) - 1.0) < 1e-12
    assert runner.pearson(xs, ys) < 0.99


def test_rank_handles_ties_with_average_ranks(runner):
    assert runner._rank([10.0, 20.0, 20.0, 30.0]) == [1.0, 2.5, 2.5, 4.0]


def test_same_sign_and_sign_agreement(runner):
    assert runner.same_sign(1.0, 2.0) and runner.same_sign(-1.0, -2.0) and runner.same_sign(0.0, 0.0)
    assert not runner.same_sign(1.0, -1.0)
    assert not runner.same_sign(0.0, 1.0), "exact zero must not silently agree with a positive flow"
    assert abs(runner.sign_agreement([1, -1, 1, 1], [1, -1, -1, 1]) - 0.75) < TOL


def test_ols3_recovers_known_coefficients(runner):
    """y = 2 + 3*x1 - 4*x2 exactly -> the solver must return (2, 3, -4)."""
    x1 = [0.0, 1.0, 2.0, 3.0, 1.0, 5.0, 2.5]
    x2 = [1.0, 0.0, 3.0, 1.0, 4.0, 2.0, 0.5]
    y = [2.0 + 3.0 * a - 4.0 * b for a, b in zip(x1, x2)]
    a, b, c = runner._ols3(y, x1, x2)
    assert abs(a - 2.0) < 1e-9 and abs(b - 3.0) < 1e-9 and abs(c + 4.0) < 1e-9


def test_ols3_rejects_singular_design(runner):
    x1 = [1.0, 2.0, 3.0, 4.0]
    with pytest.raises(ValueError):
        runner._ols3([1.0, 2.0, 3.0, 4.0], x1, x1)  # x2 collinear with x1


def test_decile_helpers_known_answer(runner):
    values = [float(i) for i in range(100)]
    cutoffs = runner._quantiles(values, 10)
    assert len(cutoffs) == 9
    assert runner.decile_of(values[0], cutoffs) == 0
    assert runner.decile_of(values[-1], cutoffs) == 9
    # An identical candidate must reproduce the reference deciles exactly.
    d = runner.decile_agreement(values, values)
    assert abs(d["exact_decile_match"] - 1.0) < TOL
    assert d["top_decile_flipped_to_bottom"] == 0


# ---------------------------------------------------------------------------
# 4. THE REAL PANEL
# ---------------------------------------------------------------------------


def test_panel_loads_with_expected_shape(panel):
    assert len(panel) == 49705, "the committed derived panel changed size"
    assert len({r.series_id for r in panel}) == 13156
    assert all(r.tna_prev > 0 for r in panel)


def test_panel_row_derived_fields_are_self_consistent(panel, runner):
    """B.6 NET minus B.6 EXTERNAL must be exactly Item B.6.b, on every row.

    Relative tolerance for the same reason as the synthetic identity test: the
    panel spans sub-$1mm funds to the $600bn Fidelity 500 Index Fund, and
    1e-12 of scale sits ~2,000x above the float64 rounding floor."""
    for r in panel[:2000]:
        scale = max(abs(r.b6_net_dollars), r.tna_prev, 1.0)
        assert abs((r.b6_net_dollars - r.b6_external_dollars) - r.reinvestment) < 1e-12 * scale
        assert abs(r.gap_vs_net - r.gap_vs_external - r.reinvestment_frac) < 1e-12


def test_eq1_tracks_b6_external_better_than_b6_net(panel, runner):
    """THE HEADLINE RESULT. Eq.(1) is a better proxy for (a-c) than for
    (a+b-c) on every metric measured, on 49,705 real fund-quarters."""
    cmp = runner.compare_definitions(panel)
    ext, net = cmp["vs_b6_external"], cmp["vs_b6_net"]

    assert ext["spearman"] > net["spearman"]
    assert ext["sign_agreement"] > net["sign_agreement"]
    assert ext["decile"]["exact_decile_match"] > net["decile"]["exact_decile_match"]

    # Pinned point values (real measurements, 2026-09-05).
    assert abs(ext["spearman"] - 0.9726) < 0.001
    assert abs(net["spearman"] - 0.9069) < 0.001
    assert abs(ext["sign_agreement"] - 0.9401) < 0.001
    assert abs(net["sign_agreement"] - 0.8708) < 0.001
    assert abs(ext["decile"]["exact_decile_match"] - 0.8376) < 0.001
    assert abs(net["decile"]["exact_decile_match"] - 0.5972) < 0.001

    # The magnitude ratio is tighter against EXTERNAL: Eq.(1) is not merely
    # rank-correlated with (a-c), it is close to it one-for-one.
    ext_iqr = ext["magnitude_ratio_eq1_over_ref"]["p75"] - ext["magnitude_ratio_eq1_over_ref"]["p25"]
    net_iqr = net["magnitude_ratio_eq1_over_ref"]["p75"] - net["magnitude_ratio_eq1_over_ref"]["p25"]
    assert ext_iqr < net_iqr
    assert abs(ext["magnitude_ratio_eq1_over_ref"]["median"] - 1.0152) < 0.001


def test_extreme_flow_deciles_are_where_a_fit_signal_lives_and_they_agree(panel, runner):
    """A cross-sectional FIT signal trades the tails of the flow sort, not the
    middle. In the tails the two definitions agree almost perfectly, which is
    what makes the choice defensible either way -- and makes the prior run's
    single mid-noise fund-quarter a bad basis for a decision."""
    d = runner.compare_definitions(panel)["vs_b6_external"]["decile"]
    assert d["top_decile_retained"] > 0.95
    assert d["bottom_decile_retained"] > 0.92
    assert d["top_decile_sign_agreement"] > 0.99
    assert d["bottom_decile_sign_agreement"] > 0.99
    # The failure that would actually hurt a long/short FIT portfolio -- a fund
    # in the true top decile landing in the Eq.(1) bottom decile -- is rare.
    assert d["top_decile_flipped_to_bottom"] <= 10


def test_sign_disagreement_concentrates_in_the_economic_noise_floor(panel, runner):
    """The prior run's PROOF_4 fund-quarter had |a-c| = 4.1bp of TNA. This is
    the bucket where sign agreement is WORST and where almost no flow dollars
    live -- so a methodological conclusion drawn there was drawing on noise."""
    buckets = runner.by_flow_magnitude(panel)
    smallest, largest = buckets[0], buckets[-1]
    assert smallest["abs_external_flow_hi"] == 0.001
    assert smallest["sign_agreement_vs_external"] < 0.35
    assert smallest["share_of_total_flow_dollars"] < 0.001
    assert largest["sign_agreement_vs_external"] > 0.99
    # Agreement must rise monotonically with flow magnitude.
    agr = [b["sign_agreement_vs_external"] for b in buckets]
    assert agr == sorted(agr), f"expected monotone improvement with flow size, got {agr}"


def test_share_class_explanation_is_refuted(panel, runner):
    """The prior run's reason (a). Bracketing Eq.(1) across the fund's OWN
    lowest and highest reported share-class returns fixes almost nothing, and
    over half the disagreements are single-share-class funds where the
    explanation cannot apply at all."""
    sc = runner.share_class_explanation_test(panel)
    assert sc["vs_b6_net"]["n_disagreements"] == 6420
    assert sc["vs_b6_net"]["fraction_fixable"] < 0.05
    assert sc["vs_b6_net"]["n_disagreements_single_share_class"] > 3000
    # Single-class funds are not meaningfully better behaved than multi-class
    # ones against B.6 NET -- so class blending is not the driver.
    assert abs(sc["single_share_class"]["sign_agreement_vs_net"]
               - sc["multi_share_class"]["sign_agreement_vs_net"]) < 0.02


def test_distribution_explanation_is_confirmed_by_three_fingerprints(panel, runner):
    de = runner.distribution_explanation_test(panel)

    # (i) December capital-gains season. The gap against B.6 NET explodes, and
    # sign agreement against B.6 NET collapses -- while agreement against B.6
    # EXTERNAL is FLAT. That contrast is the discriminating test.
    dec, non = de["december_quarters"], de["non_december_quarters"]
    assert dec["median_gap_vs_net"] > 4 * non["median_gap_vs_net"]
    assert dec["sign_agreement_vs_net"] < non["sign_agreement_vs_net"] - 0.10
    assert abs(dec["sign_agreement_vs_external"] - non["sign_agreement_vs_external"]) < 0.02

    # (ii) Distribution intensity: bond/income funds distribute far more.
    assert de["bond_income_named"]["median_gap_vs_net"] > 5 * de["equity_named"]["median_gap_vs_net"]

    # (iii) The regression loads on reinvestment ~1:1, as identity (I) requires.
    ols = de["ols_gap_vs_net"]["primary_tna_at_least_10mm"]
    assert abs(ols["coef_reinvestment"] - 1.0) < 0.10
    assert ols["coef_flow_times_return"] < 0.0


def test_flow_timing_control_moves_the_residual_monotonically(panel, runner):
    """Lou assumes flows land at quarter-end. Where that assumption is least
    wrong, inequality (II) holds more often -- monotonically. This is what
    licenses naming flow timing as part of the residual instead of guessing."""
    timing = runner.distribution_explanation_test(panel)["flow_timing_control"]
    fracs = [t["fraction_satisfying_eq1_le_external"] for t in timing]
    assert fracs == sorted(fracs), f"expected monotone improvement in quiet quarters, got {fracs}"
    assert fracs[-1] > fracs[0] + 0.05


def test_identity_is_directional_not_exact_on_real_data(panel, runner):
    """HONESTY GUARD. Identity (I) is confirmed in direction and structure but
    NOT satisfied row-by-row. If a future edit ever makes this look exact, the
    edit is wrong -- the real residual is flow timing, mergers folded into
    Item B.6.a, and as-filed data noise."""
    ineq = runner.distribution_explanation_test(panel)["inequality_eq1_le_external"]
    assert 0.60 < ineq["fraction_satisfied"] < 0.75, (
        "inequality (II) holds for about two thirds of real fund-quarters; a value "
        "near 1.0 would mean the residual was silently engineered away"
    )
    assert ineq["fraction_within_10bp"] > ineq["fraction_satisfied"]
    assert ineq["median_violation_bp"] < 25.0


# ---------------------------------------------------------------------------
# 5. THE PROOF_4 RESOLUTION, ON THE PRIOR RUN'S OWN SAMPLE FILINGS
# ---------------------------------------------------------------------------


def test_proof4_disagreement_is_real_under_b6_net_and_resolved_under_b6_external(runner):
    """The two halves of the finding, pinned together.

    tests/test_nport_flow_feasibility.py pins that Eq.(1) and B.6 NET disagree
    in sign on this fund-quarter. That remains true and must stay true. What
    this run adds is that the same fund-quarter AGREES under B.6 EXTERNAL,
    because the entire disagreement is Item B.6.b."""
    r = runner.reexamine_proof4_fund_quarter()

    assert r["series_id"] == "S000012756"
    assert len(r["eq1_by_share_class"]) == 3
    # Every share class gives a NEGATIVE Eq.(1) -- so no choice of class return
    # could have produced agreement with B.6 NET.
    assert r["eq1_all_share_classes_negative"] is True
    assert r["prior_run_disagreement_vs_b6_net"] is True
    assert r["disagreement_resolved_vs_b6_external"] is True

    assert r["b6_net_dollars"] > 0, "B.6 NET reads this quarter as an inflow"
    assert r["b6_external_dollars"] < 0, "B.6 EXTERNAL reads it as an outflow, like Eq.(1)"

    # The whole difference is one number: Item B.6.b.
    assert abs(r["b6_b_reinvestment"] - 16_562_681.94) < 0.01
    assert abs((r["b6_net_dollars"] - r["b6_external_dollars"]) - r["b6_b_reinvestment"]) < 0.01
    # ...and it lands almost entirely in month 3, consistent with a quarterly
    # distribution rather than a steady flow.
    assert r["b6_b_reinvestment_by_month"][2] > 0.999 * r["b6_b_reinvestment"]

    # Implied total distributions of ~$58.4mm on ~$29.2bn is ~20bp for the
    # quarter (~0.8%/yr) -- a plausible equity index fund distribution. This is
    # IMPLIED BY IDENTITY (I), not independently verified against the fund's
    # published distribution history.
    assert 50e6 < r["implied_total_distributions_dollars"] < 70e6
    assert 0.2 < r["implied_reinvestment_rate"] < 0.4


def test_main_runs_and_is_json_serializable(runner):
    result = runner.main()
    assert result["verdict_code"] == "RESOLVED_USE_B6_EXTERNAL_A_MINUS_C"
    assert result["panel"]["n_fund_quarters"] == 49705
    json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# 6. THE PERSISTED REPORT'S OWN INTERNAL CONSISTENCY
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REPORT_JSON.exists(), reason="this run's report is not in this checkout")
def test_persisted_report_is_internally_consistent():
    payload = json.loads(REPORT_JSON.read_text())
    assert payload["verdict_code"] == "RESOLVED_USE_B6_EXTERNAL_A_MINUS_C"
    assert payload["panel"]["n_fund_quarters"] == 49705
    ext = payload["definition_comparison"]["vs_b6_external"]
    net = payload["definition_comparison"]["vs_b6_net"]
    assert ext["spearman"] > net["spearman"]
    assert ext["sign_agreement"] > net["sign_agreement"]
    assert payload["proof4_reexamined"]["disagreement_resolved_vs_b6_external"] is True
    assert not math.isnan(payload["proof4_reexamined"]["implied_reinvestment_rate"])
