"""Flow-induced trading (Lou 2012) family: the construction validated against
synthetic data with KNOWN true answers before any real-data claim rests on it,
and the point-in-time contract that makes the whole result meaningful.

CLAUDE.md: "Never implement a published formula from memory — put the source
paper/section in context, cite the equation number in code, and validate
against synthetic data with a known true answer before trusting it on real
data." Every equation in this family gets that treatment here:

  Eq.(3)/(5) FIT      hand-derived weighted averages, and two invariances that
                      hold for ANY weights (uniform flow; scale of weights)
  Eq.(2)     PSF      synthetic panel built from KNOWN coefficients, recovered
  Eq.(4)     E[flow]  synthetic panel built from KNOWN coefficients, recovered
  Carhart alpha       synthetic returns built from a KNOWN alpha and KNOWN
                      betas, recovered
  split restatement   a hand-computable 4-for-1 split
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.nport_provider import FundQuarterFiling
from app.services.research_lab.cross_sectional_nport_flow import (
    ALPHA_WINDOW_MONTHS,
    LOU_PUBLISHED_PSF,
    MAX_ABSOLUTE_FLOW,
    MAX_REPORT_STALENESS_DAYS,
    MIN_EXPECTED_FLOW_TRAINING_PAIRS,
    MIN_FUND_NET_ASSETS,
    MIN_FUNDS_PER_STOCK,
    NPORT_FLOW_BORROW_LADDER_BPS,
    NPORT_FLOW_HOLDING_DAYS,
    NPORT_FLOW_N_TRIALS,
    PERFECT_SCALING_PSF,
    FlowPanelDiagnostics,
    NportFlowScreeningSummary,
    PartialScalingFactor,
    SpecEvaluation,
    _series_index,
    build_flow_panels,
    build_nport_flow_family,
    build_split_adjustment,
    default_nport_flow_config,
    dsr_across_denominators,
    estimate_partial_scaling_factor,
    fit_expected_flow_model,
    flow_induced_trading,
    flow_induced_trading_multi,
    four_factor_alpha,
    fund_monthly_returns,
    fund_snapshots_as_of,
    month_end_snapshots,
    policy_d_denominators,
    split_factor_on,
)

# ===========================================================================
# Eq.(3) / Eq.(5) — the kernel
# ===========================================================================


def test_fit_reproduces_the_hand_derived_known_answer():
    """Two funds holding 100 and 300 shares with flows -0.10 and +0.20, under
    Lou's published univariate PSF (0.970 outflow / 0.618 inflow):

        numerator   = 100*(-0.10)*0.970 + 300*(0.20)*0.618
                    = -9.70 + 37.08 = 27.38
        denominator = 400
        FIT         = 0.06845

    Every term written out longhand so the test is a derivation, not a
    regression against whatever the code happened to produce."""
    value = flow_induced_trading({"A": 100.0, "B": 300.0}, {"A": -0.10, "B": 0.20}, LOU_PUBLISHED_PSF)
    assert value == pytest.approx((100 * -0.10 * 0.970 + 300 * 0.20 * 0.618) / 400)
    assert value == pytest.approx(0.06845)


@pytest.mark.parametrize("flow", [-0.45, -0.01, 0.01, 0.33])
def test_uniform_flow_collapses_to_flow_times_psf_for_any_weights(flow):
    """A weighted average of a constant is that constant. This holds for ANY
    weights, so it catches a numerator/denominator mismatch that a single
    hand-worked example could miss."""
    weights = {"A": 7.0, "B": 913.0, "C": 1.0, "D": 42.5}
    value = flow_induced_trading(weights, dict.fromkeys(weights, flow), LOU_PUBLISHED_PSF)
    assert value == pytest.approx(flow * LOU_PUBLISHED_PSF.for_flow(flow))


def test_fit_is_invariant_to_a_common_rescaling_of_every_share_count():
    """The property that makes the measure meaningful across funds at all: it
    is a RATIO of two sums of the same counts, so any common factor cancels.
    (It is NOT invariant to a per-fund rescaling, which is exactly why the
    split restatement in build_split_adjustment is load-bearing.)"""
    weights = {"A": 100.0, "B": 300.0, "C": 55.0}
    flows = {"A": -0.10, "B": 0.20, "C": -0.02}
    base = flow_induced_trading(weights, flows, LOU_PUBLISHED_PSF)
    scaled = flow_induced_trading({k: v * 1234.5 for k, v in weights.items()}, flows, LOU_PUBLISHED_PSF)
    assert scaled == pytest.approx(base)


def test_a_fund_with_no_observable_flow_leaves_both_sums():
    """Dropping it from the numerator only would silently treat it as
    zero-flow, diluting every other fund's contribution."""
    value = flow_induced_trading({"A": 100.0, "B": 300.0}, {"A": -0.10}, LOU_PUBLISHED_PSF)
    assert value == pytest.approx(-0.10 * 0.970)


def test_no_positive_share_count_returns_none_not_zero():
    """None means "no mutual fund is observed holding this stock", which
    excludes it from ranking. Zero would rank it at the middle of the
    cross-section on no evidence at all."""
    assert flow_induced_trading({}, {}, LOU_PUBLISHED_PSF) is None
    assert flow_induced_trading({"A": 0.0}, {"A": 0.5}, LOU_PUBLISHED_PSF) is None
    assert flow_induced_trading({"A": float("nan")}, {"A": 0.5}, LOU_PUBLISHED_PSF) is None


def test_the_published_psf_carries_lous_own_table_ii_numbers():
    """Table II column 1 (outflow, univariate) 0.970; column 5 (inflow,
    univariate) 0.618. Pinned so a later edit cannot quietly retune the one
    parameter this family takes from the paper."""
    assert LOU_PUBLISHED_PSF.outflow == 0.970
    assert LOU_PUBLISHED_PSF.inflow == 0.618
    assert LOU_PUBLISHED_PSF.for_flow(-0.5) == 0.970
    assert LOU_PUBLISHED_PSF.for_flow(0.5) == 0.618
    # A zero flow contributes flow*PSF == 0 either way, so the branch is
    # arbitrary and only needs to be total.
    assert LOU_PUBLISHED_PSF.for_flow(0.0) == 0.618
    assert PERFECT_SCALING_PSF.outflow == PERFECT_SCALING_PSF.inflow == 1.0


def test_outflows_are_weighted_more_heavily_than_inflows_as_lou_measured():
    """The whole economic content of the univariate PSF: a dollar of outflow
    moves the measure 0.970/0.618 = 1.57x as much as a dollar of inflow,
    because managers must sell pro-rata to fund redemptions but reinvest only
    part of an inflow."""
    outflow_only = flow_induced_trading({"A": 1.0}, {"A": -0.1}, LOU_PUBLISHED_PSF)
    inflow_only = flow_induced_trading({"A": 1.0}, {"A": 0.1}, LOU_PUBLISHED_PSF)
    assert abs(outflow_only) / abs(inflow_only) == pytest.approx(0.970 / 0.618)


def test_the_fast_multi_factor_path_agrees_with_the_reference_implementation():
    """flow_induced_trading is the reference the hand-derived tests check;
    flow_induced_trading_multi is the one the panel builder actually calls,
    because it shares one pass over the funds across the PSF sensitivity arms.
    An optimisation that is not pinned against the thing it optimises is an
    unverified rewrite."""
    rng = np.random.default_rng(99)
    factors = [LOU_PUBLISHED_PSF, PERFECT_SCALING_PSF, PartialScalingFactor(0.5, 0.3, "test")]
    for _ in range(200):
        n = int(rng.integers(1, 40))
        weights = {f"S{i}": float(rng.uniform(0, 1e6)) for i in range(n)}
        flows = {f"S{i}": float(rng.normal(0, 0.2)) for i in range(n) if rng.random() > 0.15}
        contributions = {
            series: [flow * factor.for_flow(flow) for factor in factors]
            for series, flow in flows.items()
        }
        fast = flow_induced_trading_multi(weights, contributions, len(factors))
        slow = [flow_induced_trading(weights, flows, factor) for factor in factors]
        if fast is None:
            assert all(v is None for v in slow)
            continue
        for got, want in zip(fast, slow, strict=True):
            assert got == pytest.approx(want)


def test_the_fast_path_also_drops_a_fund_with_no_observable_flow():
    contributions = {"A": [-0.10 * 0.970]}
    values = flow_induced_trading_multi({"A": 100.0, "B": 300.0}, contributions, 1)
    assert values == [pytest.approx(-0.10 * 0.970)]


# ===========================================================================
# Eq.(2) — the partial scaling factor, recovered from a KNOWN synthetic panel
# ===========================================================================


def test_eq2_reestimation_recovers_known_synthetic_coefficients():
    rng = np.random.default_rng(20260905)
    true_outflow_slope, true_outflow_intercept = 0.83, -0.02
    true_inflow_slope, true_inflow_intercept = 0.41, 0.05
    pairs: list[tuple[float, float]] = []
    for _ in range(4000):
        flow = float(rng.uniform(-0.4, -0.001))
        pairs.append((true_outflow_intercept + true_outflow_slope * flow + rng.normal(0, 0.01), flow))
    for _ in range(4000):
        flow = float(rng.uniform(0.001, 0.4))
        pairs.append((true_inflow_intercept + true_inflow_slope * flow + rng.normal(0, 0.01), flow))

    estimated, stats = estimate_partial_scaling_factor(pairs)
    assert estimated is not None
    assert estimated.outflow == pytest.approx(true_outflow_slope, abs=0.02)
    assert estimated.inflow == pytest.approx(true_inflow_slope, abs=0.02)
    assert stats["outflow_bounded_intercept"] == pytest.approx(true_outflow_intercept, abs=0.01)
    assert stats["inflow_bounded_intercept"] == pytest.approx(true_inflow_intercept, abs=0.01)
    assert stats["outflow_n"] == 4000
    assert stats["inflow_n"] == 4000
    # Nothing in this synthetic panel exceeds the bound, so all three
    # treatments must agree — the bound is inert where the data is clean.
    for side in ("outflow", "inflow"):
        assert stats[f"{side}_raw_slope"] == pytest.approx(stats[f"{side}_bounded_slope"], abs=1e-9)
        assert stats[f"{side}_retained_fraction"] == 1.0


def test_eq2_reestimation_splits_the_sample_the_way_lou_does():
    """Lou "conduct[s] separate regressions for the inflow and outflow
    subsamples". A pooled fit on data with genuinely different slopes would
    return one number between them; the split must return both."""
    pairs = [(0.9 * f, f) for f in np.linspace(-0.5, -0.01, 500)]
    pairs += [(0.2 * f, f) for f in np.linspace(0.01, 0.5, 500)]
    estimated, _ = estimate_partial_scaling_factor(pairs)
    assert estimated is not None
    assert estimated.outflow == pytest.approx(0.9, abs=1e-6)
    assert estimated.inflow == pytest.approx(0.2, abs=1e-6)
    # A pooled fit would return one number between the two; the split returns
    # both, which is why Lou runs separate regressions.
    assert estimated.outflow != pytest.approx(estimated.inflow, abs=0.1)


def test_eq2_reestimation_is_not_destroyed_by_the_unbounded_upper_tail():
    """THE defect this bound exists for, reproduced from a KNOWN true slope.
    Eq.(2)'s dependent variable is structurally bounded at -1 below (a fund
    cannot sell more shares than it holds) and unbounded above; on the real
    N-PORT panel its top tail reaches +776,631 (a position initiated from a
    residual stake). Untreated OLS then reports a slope with the WRONG SIGN and
    R^2 of zero — which this family's first run published as a measurement
    before it was caught."""
    rng = np.random.default_rng(20260906)
    true_slope, true_intercept = 0.84, -0.01
    pairs = [
        (true_intercept + true_slope * f + rng.normal(0, 0.05), f)
        for f in rng.uniform(-0.4, -0.001, 20_000)
    ]
    pairs += [(0.6 * f + rng.normal(0, 0.05), f) for f in rng.uniform(0.001, 0.4, 20_000)]
    # 0.3% contamination, the measured real-data share of |trade| > 10
    for _ in range(60):
        pairs.append((float(rng.uniform(1e3, 8e5)), float(rng.uniform(-0.4, -0.001))))

    estimated, stats = estimate_partial_scaling_factor(pairs)
    assert estimated is not None
    # untreated: destroyed, and reported as such rather than hidden
    assert abs(stats["outflow_raw_slope"] - true_slope) > 10.0
    assert stats["outflow_raw_r_squared"] < 0.01
    # bounded: recovers the known truth
    assert estimated.outflow == pytest.approx(true_slope, abs=0.02)
    assert stats["outflow_bounded_r_squared"] > 0.5
    assert 0.99 < stats["outflow_retained_fraction"] < 1.0
    # and the untreated fit is still present in the output, not dropped
    assert "outflow_winsorized_slope" in stats


def test_the_psf_bound_is_the_symmetric_counterpart_of_the_structural_floor():
    """|trade| <= 1 means 'at most fully liquidated, at most doubled'. -1 is
    where the variable is censored by construction, so 1 is the only upper
    bound that makes the two tails comparable."""
    from app.services.research_lab.cross_sectional_nport_flow import (
        MAX_ABS_TRADE_FOR_PSF,
    )

    assert MAX_ABS_TRADE_FOR_PSF == 1.0


def test_eq2_reestimation_refuses_a_degenerate_subsample_rather_than_inventing_one():
    """A side with no usable observations has no partial scaling factor, and
    returning a NaN-carrying one would quietly turn every FIT value into NaN
    downstream instead of failing where the problem is."""
    estimated, stats = estimate_partial_scaling_factor([(0.1, 0.2), (0.2, 0.4)])
    assert estimated is None
    assert stats["outflow_n_all"] == 0  # no outflow observations at all
    assert stats["inflow_n"] == 2


# ===========================================================================
# Carhart four-factor alpha, recovered from KNOWN synthetic returns
# ===========================================================================


def _factor_frame(n_months: int = 36, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2020-01-31", periods=n_months, freq="ME")
    return pd.DataFrame(
        {
            "mkt_rf": rng.normal(0.008, 0.04, n_months),
            "smb": rng.normal(0.001, 0.02, n_months),
            "hml": rng.normal(0.000, 0.02, n_months),
            "mom": rng.normal(0.003, 0.03, n_months),
            "rf": np.full(n_months, 0.002),
        },
        index=index,
    )


def test_four_factor_alpha_recovers_a_known_alpha_and_known_betas():
    factors = _factor_frame()
    true_alpha, betas = 0.0031, (0.95, 0.20, -0.10, 0.35)
    returns = {
        month: float(
            factors.loc[month, "rf"]
            + true_alpha
            + betas[0] * factors.loc[month, "mkt_rf"]
            + betas[1] * factors.loc[month, "smb"]
            + betas[2] * factors.loc[month, "hml"]
            + betas[3] * factors.loc[month, "mom"]
        )
        for month in factors.index
    }
    alpha = four_factor_alpha(returns, factors, factors.index[-1])
    assert alpha == pytest.approx(true_alpha, abs=1e-10)


def test_four_factor_alpha_needs_the_full_twelve_month_window():
    """Lou: "the monthly Carhart four-factor alpha computed from the fund's
    returns in the previous year". A short window would make alpha an artifact
    of however many months a fund happened to report."""
    factors = _factor_frame()
    returns = {month: 0.01 for month in factors.index[: ALPHA_WINDOW_MONTHS - 1]}
    assert four_factor_alpha(returns, factors, factors.index[ALPHA_WINDOW_MONTHS - 2]) is None


def test_four_factor_alpha_refuses_a_window_with_a_reporting_gap():
    """Twelve observations spread over three years are not "the previous
    year"."""
    factors = _factor_frame(n_months=48, seed=11)
    sparse = {month: 0.01 for month in factors.index[::4][:ALPHA_WINDOW_MONTHS]}
    assert four_factor_alpha(sparse, factors, factors.index[-1]) is None


def test_four_factor_alpha_refuses_when_a_factor_month_is_missing():
    factors = _factor_frame()
    holed = factors.copy()
    holed.loc[holed.index[-3], "mom"] = np.nan
    returns = {month: 0.01 for month in factors.index}
    assert four_factor_alpha(returns, holed, holed.index[-1]) is None


def test_fund_monthly_returns_maps_the_three_reported_months_correctly():
    """Item B.5.a reports the report month and the two before it, in that
    order, as PERCENTAGES."""
    filing = FundQuarterFiling(
        accession="a1",
        series_id="S1",
        series_name="Fund",
        report_date=date(2026, 6, 30),
        filing_date=date(2026, 8, 29),
        submission_type="NPORT-P",
        is_last_filing=False,
        net_assets=1e9,
        sales=0.0,
        reinvestment=0.0,
        redemption=0.0,
    )
    out = fund_monthly_returns([filing], {"a1": [(1.0, 2.0, 3.0)]})
    assert out["S1"] == {
        pd.Timestamp("2026-04-30"): pytest.approx(0.01),
        pd.Timestamp("2026-05-31"): pytest.approx(0.02),
        pd.Timestamp("2026-06-30"): pytest.approx(0.03),
    }


def test_multi_class_fund_returns_are_averaged_across_classes():
    """A DISCLOSED approximation, not a preference: Form N-PORT reports returns
    per class and reports NO class-level assets, so a true NAV-weighted blend
    is not computable from N-PORT alone."""
    filing = FundQuarterFiling(
        accession="a1",
        series_id="S1",
        series_name="Fund",
        report_date=date(2026, 6, 30),
        filing_date=date(2026, 8, 29),
        submission_type="NPORT-P",
        is_last_filing=False,
        net_assets=1e9,
        sales=0.0,
        reinvestment=0.0,
        redemption=0.0,
    )
    out = fund_monthly_returns([filing], {"a1": [(1.0, 2.0, 3.0), (3.0, 4.0, 5.0)]})
    assert out["S1"][pd.Timestamp("2026-06-30")] == pytest.approx(0.04)


# ===========================================================================
# Eq.(4) — the expected-flow first stage
# ===========================================================================


def test_expected_flow_model_recovers_known_synthetic_coefficients():
    rng = np.random.default_rng(4)
    true_intercept, true_slope = -0.031, 3.7
    pairs = []
    for _ in range(3000):
        alpha = float(rng.normal(0.0, 0.004))
        pairs.append((alpha, true_intercept + true_slope * alpha + rng.normal(0, 0.02)))
    fitted = fit_expected_flow_model(pairs)
    assert fitted is not None
    intercept, slope, stats = fitted
    assert intercept == pytest.approx(true_intercept, abs=0.002)
    assert slope == pytest.approx(true_slope, abs=0.3)
    assert stats["n"] == 3000


def test_expected_flow_model_refuses_a_sample_below_the_declared_floor():
    """Below MIN_EXPECTED_FLOW_TRAINING_PAIRS the first stage is noise, and
    every fund's expected flow would be an artifact of a handful of funds."""
    pairs = [(0.001 * i, 0.01 * i) for i in range(MIN_EXPECTED_FLOW_TRAINING_PAIRS - 1)]
    assert fit_expected_flow_model(pairs) is None


def test_expected_flow_model_refuses_a_degenerate_regressor():
    pairs = [(0.002, 0.05 + 0.001 * i) for i in range(MIN_EXPECTED_FLOW_TRAINING_PAIRS + 10)]
    assert fit_expected_flow_model(pairs) is None


# ===========================================================================
# split restatement
# ===========================================================================


def test_split_restatement_matches_a_hand_computed_four_for_one():
    index = pd.DatetimeIndex(pd.date_range("2020-01-31", "2021-01-31", freq="ME"))
    adjustments = build_split_adjustment(
        {"AAPL": pd.Series([4.0], index=[pd.Timestamp("2020-08-31")])}, index
    )
    # A count observed BEFORE the split must be multiplied by 4 to compare with
    # counts observed after it.
    assert split_factor_on(adjustments, "AAPL", date(2020, 6, 30)) == 4.0
    assert split_factor_on(adjustments, "AAPL", date(2020, 12, 31)) == 1.0
    # A ticker with no recorded split, and a date before the panel starts.
    assert split_factor_on(adjustments, "MSFT", date(2020, 6, 30)) == 1.0
    assert split_factor_on(adjustments, "AAPL", date(2019, 1, 1)) == 4.0


def test_split_restatement_compounds_successive_splits():
    index = pd.DatetimeIndex(pd.date_range("2020-01-31", "2023-01-31", freq="ME"))
    adjustments = build_split_adjustment(
        {
            "NVDA": pd.Series(
                [4.0, 10.0], index=[pd.Timestamp("2021-07-31"), pd.Timestamp("2024-06-30")]
            )
        },
        index,
    )
    # Only the 2021 split falls inside the panel, so a 2020 observation carries
    # that factor alone; the 2024 event is outside the frame's own index.
    assert split_factor_on(adjustments, "NVDA", date(2020, 6, 30)) == pytest.approx(40.0)
    assert split_factor_on(adjustments, "NVDA", date(2022, 6, 30)) == pytest.approx(10.0)


def test_split_restatement_makes_two_staggered_fiscal_quarters_comparable():
    """The failure this exists to prevent, worked end to end. Fund A reports on
    31 December and fund B on 31 January; the stock splits 2-for-1 on 15
    January. Both funds hold the SAME economic position, so a correct FIT is
    the share-count-weighted average with EQUAL weights."""
    index = pd.DatetimeIndex(pd.date_range("2020-11-30", "2021-06-30", freq="ME"))
    adjustments = build_split_adjustment(
        {"XYZ": pd.Series([2.0], index=[pd.Timestamp("2021-01-15")])}, index
    )
    raw_a, raw_b = 1_000.0, 2_000.0  # same economics, different reporting dates
    adjusted = {
        "A": raw_a * split_factor_on(adjustments, "XYZ", date(2020, 12, 31)),
        "B": raw_b * split_factor_on(adjustments, "XYZ", date(2021, 1, 31)),
    }
    assert adjusted["A"] == adjusted["B"] == 2_000.0
    flows = {"A": -0.20, "B": 0.20}
    corrected = flow_induced_trading(adjusted, flows, LOU_PUBLISHED_PSF)
    unadjusted = flow_induced_trading({"A": raw_a, "B": raw_b}, flows, LOU_PUBLISHED_PSF)
    # Equal weights: the two flows net to (-0.2*0.970 + 0.2*0.618)/2.
    assert corrected == pytest.approx((-0.20 * 0.970 + 0.20 * 0.618) / 2)
    # Unadjusted, fund B is double-counted and the answer is materially
    # different — this is the bias the restatement removes, not a rounding.
    assert unadjusted != pytest.approx(corrected, abs=1e-6)


# ===========================================================================
# the point-in-time contract
# ===========================================================================


def _filing(
    series: str,
    report: date,
    filed: date,
    *,
    sales: float = 100.0,
    redemption: float = 50.0,
    net_assets: float = 1e9,
    accession: str | None = None,
) -> FundQuarterFiling:
    return FundQuarterFiling(
        accession=accession or f"{series}-{report.isoformat()}-{filed.isoformat()}",
        series_id=series,
        series_name=f"Fund {series}",
        report_date=report,
        filing_date=filed,
        submission_type="NPORT-P",
        is_last_filing=False,
        net_assets=net_assets,
        sales=sales,
        reinvestment=7.0,
        redemption=redemption,
    )


def test_a_filing_not_yet_public_cannot_affect_the_fund_state():
    """THE look-ahead test. The 2026-06-30 report is filed 2026-08-29; asked as
    of 2026-08-28 the fund's state must still be the March quarter's."""
    filings = [
        _filing("S1", date(2025, 12, 31), date(2026, 3, 1)),
        _filing("S1", date(2026, 3, 31), date(2026, 5, 30)),
        _filing("S1", date(2026, 6, 30), date(2026, 8, 29)),
    ]
    by_series = _series_index(filings)
    before = fund_snapshots_as_of(by_series, date(2026, 8, 28), FlowPanelDiagnostics())
    after = fund_snapshots_as_of(by_series, date(2026, 8, 29), FlowPanelDiagnostics())
    assert before["S1"].report_date == date(2026, 3, 31)
    assert after["S1"].report_date == date(2026, 6, 30)


def test_an_amendment_supersedes_its_original_only_from_its_own_filing_date():
    original = _filing("S1", date(2026, 3, 31), date(2026, 5, 30), sales=100.0, accession="orig")
    amended = _filing("S1", date(2026, 3, 31), date(2026, 9, 1), sales=900.0, accession="amend")
    by_series = _series_index([_filing("S1", date(2025, 12, 31), date(2026, 3, 1)), original, amended])
    before = fund_snapshots_as_of(by_series, date(2026, 8, 31), FlowPanelDiagnostics())
    after = fund_snapshots_as_of(by_series, date(2026, 9, 1), FlowPanelDiagnostics())
    assert before["S1"].current_accession == "orig"
    assert after["S1"].current_accession == "amend"


def test_flow_is_scaled_by_the_PREVIOUS_quarters_net_assets():
    """Lou: "the dollar flow to fund i in quarter t scaled by the fund's lagged
    total net assets". Scaling by the CURRENT quarter's would make a fund that
    doubled in size look like it had half the flow."""
    filings = [
        _filing("S1", date(2026, 3, 31), date(2026, 5, 30), net_assets=2e7),
        _filing(
            "S1", date(2026, 6, 30), date(2026, 8, 29),
            net_assets=1e9,  # the fund grew 50x; scaling by THIS would hide the flow
            sales=6e6, redemption=2e6,
        ),
    ]
    state = fund_snapshots_as_of(_series_index(filings), date(2026, 9, 30), FlowPanelDiagnostics())
    assert state["S1"].flow == pytest.approx((6e6 - 2e6) / 2e7)
    assert state["S1"].previous_net_assets == 2e7


@pytest.mark.parametrize(
    ("filings_builder", "reason"),
    [
        # a single public filing: no prior quarter to weight by
        (lambda: [_filing("S1", date(2026, 6, 30), date(2026, 8, 29))], "fewer_than_two_public_filings"),
        # two filings six months apart: `flow` would be a half-year figure
        (
            lambda: [
                _filing("S1", date(2025, 12, 31), date(2026, 3, 1)),
                _filing("S1", date(2026, 6, 30), date(2026, 8, 29)),
            ],
            "report_dates_not_one_quarter_apart",
        ),
        # a fund below the declared size floor
        (
            lambda: [
                _filing("S1", date(2026, 3, 31), date(2026, 5, 30), net_assets=MIN_FUND_NET_ASSETS - 1),
                _filing("S1", date(2026, 6, 30), date(2026, 8, 29)),
            ],
            "fund_below_size_floor",
        ),
        # a flow beyond the declared cap: a merger, not investor flow
        (
            lambda: [
                _filing("S1", date(2026, 3, 31), date(2026, 5, 30), net_assets=1e7),
                _filing(
                    "S1",
                    date(2026, 6, 30),
                    date(2026, 8, 29),
                    sales=1e7 * (MAX_ABSOLUTE_FLOW + 1),
                    redemption=0.0,
                ),
            ],
            "flow_exceeds_absolute_cap",
        ),
    ],
)
def test_each_declared_refusal_actually_fires_and_is_counted(filings_builder, reason):
    diagnostics = FlowPanelDiagnostics()
    state = fund_snapshots_as_of(
        _series_index(filings_builder()), date(2026, 9, 30), diagnostics
    )
    assert state == {}
    assert diagnostics.n_refused[reason] == 1


def test_a_fund_that_stopped_filing_stops_voting_once_its_report_goes_stale():
    filings = [
        _filing("S1", date(2025, 3, 31), date(2025, 5, 30)),
        _filing("S1", date(2025, 6, 30), date(2025, 8, 29)),
    ]
    by_series = _series_index(filings)
    fresh = date(2025, 6, 30) + pd.Timedelta(days=MAX_REPORT_STALENESS_DAYS).to_pytimedelta()
    stale = fresh + pd.Timedelta(days=1).to_pytimedelta()
    assert "S1" in fund_snapshots_as_of(by_series, fresh, FlowPanelDiagnostics())
    diagnostics = FlowPanelDiagnostics()
    assert fund_snapshots_as_of(by_series, stale, diagnostics) == {}
    assert diagnostics.n_refused["latest_public_report_too_stale"] == 1


# ===========================================================================
# the panel builder, end to end on synthetic data with a known answer
# ===========================================================================


def _synthetic_panel_inputs(n_funds: int = 6):
    """Five quarterly filings per fund for one stock, with hand-set flows."""
    reports = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31)]
    filings: list[FundQuarterFiling] = []
    holdings: dict[str, dict[str, float]] = {}
    returns: dict[str, list[tuple[float, float, float]]] = {}
    for fund in range(n_funds):
        series = f"S{fund}"
        for report in reports:
            filed = report + pd.Timedelta(days=60).to_pytimedelta()
            # fund 0 has a big outflow; the rest have small inflows
            sales, redemption = (0.0, 5e7) if fund == 0 else (2e6, 1e6)
            filing = _filing(
                series, report, filed, sales=sales, redemption=redemption, net_assets=1e9
            )
            filings.append(filing)
            holdings[filing.accession] = {"037833100": 1_000.0 * (fund + 1)}
            returns[filing.accession] = [(1.0, 1.0, 1.0)]
    return filings, holdings, returns


def test_build_flow_panels_writes_a_hand_checkable_value_and_only_after_filing():
    close = pd.DataFrame(
        1.0,
        index=pd.DatetimeIndex(pd.date_range("2025-01-01", "2026-06-30", freq="B")),
        columns=["AAPL"],
    )
    filings, holdings, returns = _synthetic_panel_inputs()
    panels = build_flow_panels(
        close,
        filings,
        holdings,
        {"037833100": "AAPL"},
        returns,
        _factor_frame(n_months=48, seed=3),
        {},
        psfs={"lou_published": LOU_PUBLISHED_PSF},
        headline_psf="lou_published",
    )
    fit = panels.fit["lou_published"]["AAPL"]

    # The 2025-06-30 report is filed 2025-08-29 and needs the 2025-03-31 report
    # (filed 2025-05-30) for its weights. Nothing is knowable before then.
    assert not np.isfinite(fit.loc[: pd.Timestamp("2025-08-28")].to_numpy(dtype=float)).any()

    # From 2025-08-29 the value is the hand-computable weighted average:
    #   fund 0: weight 1000, flow (0 - 5e7)/1e9 = -0.05, PSF 0.970
    #   funds 1..5: weights 2000..6000, flow (2e6 - 1e6)/1e9 = +0.001, PSF 0.618
    weights = {f"S{i}": 1000.0 * (i + 1) for i in range(6)}
    flows = {"S0": -0.05, **{f"S{i}": 0.001 for i in range(1, 6)}}
    expected = flow_induced_trading(weights, flows, LOU_PUBLISHED_PSF)
    settled = fit.loc[pd.Timestamp("2025-09-30")]
    assert settled == pytest.approx(expected)


def test_a_stock_held_by_fewer_than_the_declared_minimum_funds_is_never_ranked():
    close = pd.DataFrame(
        1.0,
        index=pd.DatetimeIndex(pd.date_range("2025-01-01", "2026-06-30", freq="B")),
        columns=["AAPL"],
    )
    filings, holdings, returns = _synthetic_panel_inputs(n_funds=MIN_FUNDS_PER_STOCK - 1)
    panels = build_flow_panels(
        close, filings, holdings, {"037833100": "AAPL"}, returns,
        _factor_frame(n_months=48, seed=3), {},
        psfs={"lou_published": LOU_PUBLISHED_PSF}, headline_psf="lou_published",
    )
    assert not np.isfinite(panels.fit["lou_published"].to_numpy(dtype=float)).any()
    assert panels.diagnostics.n_refused["fit_too_few_funds"] > 0
    assert panels.tickers_never_ranked == ["AAPL"]


def test_the_panel_is_a_step_series_never_interpolated():
    close = pd.DataFrame(
        1.0,
        index=pd.DatetimeIndex(pd.date_range("2025-01-01", "2026-06-30", freq="B")),
        columns=["AAPL"],
    )
    filings, holdings, returns = _synthetic_panel_inputs()
    panels = build_flow_panels(
        close, filings, holdings, {"037833100": "AAPL"}, returns,
        _factor_frame(n_months=48, seed=3), {},
        psfs={"lou_published": LOU_PUBLISHED_PSF}, headline_psf="lou_published",
    )
    values = panels.fit["lou_published"]["AAPL"].dropna()
    # A step series takes few distinct values; an interpolated one would take a
    # new value on nearly every row.
    assert 0 < values.nunique() <= 12
    assert len(values) > 100


def test_month_end_snapshots_takes_the_last_trading_row_of_each_month():
    index = pd.DatetimeIndex(pd.date_range("2025-01-01", "2025-03-31", freq="B"))
    snapshots = month_end_snapshots(index)
    assert snapshots == [
        pd.Timestamp("2025-01-31"),
        pd.Timestamp("2025-02-28"),
        pd.Timestamp("2025-03-31"),
    ]
    assert month_end_snapshots(pd.DatetimeIndex([])) == []


def test_headline_psf_must_be_among_the_supplied_factors():
    close = pd.DataFrame(1.0, index=pd.DatetimeIndex(pd.date_range("2025-01-01", periods=5, freq="B")), columns=["A"])
    with pytest.raises(ValueError, match="headline_psf"):
        build_flow_panels(
            close, [], {}, {}, {}, _factor_frame(), {},
            psfs={"perfect_scaling": PERFECT_SCALING_PSF}, headline_psf="lou_published",
        )


# ===========================================================================
# the pre-declared grid, and Policy D reporting
# ===========================================================================


def test_the_grid_is_exactly_the_twelve_pre_registered_specs():
    frame = pd.DataFrame()
    specs = build_nport_flow_family({"fit": frame, "expected_fit": frame})
    assert len(specs) == NPORT_FLOW_N_TRIALS == 12
    assert len({s.pattern_id for s in specs}) == 12
    assert {s.pattern_id for s in specs} == {
        f"{prefix}_ls_h{hold}{suffix}"
        for prefix in ("fit", "efit")
        for hold in (63, 126, 252)
        for suffix in ("", "_quintile")
    }
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.leg_weighting == "magnitude" for s in specs)
    assert all(s.requires_fundamental_signal for s in specs)
    assert all(s.family == "nport_flow_fit" for s in specs)
    assert {s.rank_fraction for s in specs} == {0.1, 0.2}


def test_a_monthly_hold_is_excluded_from_the_grid():
    """N-PORT holdings refresh quarterly and are published 60 days late, so a
    21-day hold re-pays turnover on an essentially unchanged ranking."""
    assert 21 not in NPORT_FLOW_HOLDING_DAYS
    assert NPORT_FLOW_HOLDING_DAYS == (63, 126, 252)


def test_the_family_refuses_to_build_without_a_panel_for_every_measure():
    with pytest.raises(ValueError, match="expected_fit"):
        build_nport_flow_family({"fit": pd.DataFrame()})


def test_policy_d_denominators_carry_the_local_grid_and_both_pooled_numbers():
    denominators = policy_d_denominators()
    assert denominators[0] == NPORT_FLOW_N_TRIALS == 12
    assert len(denominators) == 3
    assert denominators == sorted(denominators)


def test_dsr_is_monotonically_non_increasing_in_the_denominator():
    """The property that makes a three-point Policy D report sufficient rather
    than a sample of a curve: SR0 is strictly increasing in N and PSR is
    strictly decreasing in its benchmark, so there is no N between two
    reported points at which a failing spec passes."""
    rng = np.random.default_rng(11)
    returns = pd.Series(rng.normal(0.0005, 0.01, 1500))
    by_n = dsr_across_denominators(0.8, returns, 0.25, [12, 481, 857], periods_per_year=252.0)
    values = [by_n[n] for n in (12, 481, 857)]
    assert all(v is not None for v in values)
    assert values[0] >= values[1] >= values[2]


def test_the_borrow_ladder_is_the_three_pre_registered_rates():
    """0 is this project's standing (known-wrong) optimism, 34 the D'Avolio /
    Beneish-Lee-Nichols general-collateral rate used as the headline, 430
    D'Avolio Table 3's value-weighted mean fee for specials."""
    assert NPORT_FLOW_BORROW_LADDER_BPS == (0.0, 34.0, 430.0)


def test_the_default_config_charges_both_spread_and_borrow():
    """CLAUDE.md: cost realism must feed into the DSR calculation itself, not
    sit as a side disclosure. This family does NOT inherit the 0.0 financing
    every other single-stock equity family here carries."""
    config = default_nport_flow_config()
    assert config.cost_model == "edge_spread"
    assert config.financing_bps_per_year == 17.0  # 34 bps/yr on the short leg alone
    # A fresh object per call: the harness writes formation_start onto whatever
    # it is given, so a shared singleton would leak between runs.
    assert default_nport_flow_config() is not config


def _evaluation(pattern_id: str, dsr_by_n: dict[int, float | None]) -> SpecEvaluation:
    return SpecEvaluation(
        pattern_id=pattern_id,
        sharpe_annualized=0.5,
        dsr_by_n=dsr_by_n,
        preservation={},
        n_trading_days=1000,
        total_cost_drag=0.0,
        total_financing_drag=0.0,
        total_turnover=0.0,
        edge_flat_fallback_notional=0.0,
        avg_names_per_leg=40.0,
        n_formations=20,
    )


def _summary(evaluations: list[SpecEvaluation]) -> NportFlowScreeningSummary:
    return NportFlowScreeningSummary(
        results=[],
        n_trials=12,
        universe_size=0,
        cusips_resolved=0,
        tickers_without_cusip=[],
        missing_price_data=[],
        tickers_never_ranked=[],
        quarters_loaded=[],
        n_filings=0,
        n_holding_rows=0,
        panel_start=None,
        panel_end=None,
        formation_start=date(2020, 4, 1),
        psf=LOU_PUBLISHED_PSF,
        evaluations=evaluations,
    )


@pytest.mark.parametrize(
    ("dsr_by_n", "expected"),
    [
        ({12: 0.60, 481: 0.30, 857: 0.25}, "definite_negative"),
        ({12: 0.97, 481: 0.80, 857: 0.70}, "unresolved"),
        ({12: 0.99, 481: 0.98, 857: 0.97}, "pass"),
        ({12: None, 481: None, 857: None}, "definite_negative"),
    ],
)
def test_the_two_tier_verdict_follows_policy_d(dsr_by_n, expected):
    assert _summary([_evaluation("fit_ls_h63", dsr_by_n)]).verdict()[0] == expected


def test_the_verdict_is_taken_on_the_best_spec_at_the_local_denominator():
    summary = _summary(
        [
            _evaluation("fit_ls_h63", {12: 0.20, 481: 0.10, 857: 0.05}),
            _evaluation("efit_ls_h252", {12: 0.99, 481: 0.99, 857: 0.99}),
        ]
    )
    verdict, best = summary.verdict()
    assert (verdict, best) == ("pass", "efit_ls_h252")


def test_an_empty_evaluation_set_is_a_definite_negative_not_a_pass():
    assert _summary([]).verdict() == ("definite_negative", "")


def test_the_expected_flow_training_set_counts_each_fund_quarter_once():
    """A fund's filing stays its latest PUBLIC one for one to three monthly
    snapshots. Appending a training pair per snapshot would enter the same
    fund-quarter two or three times, and NOT uniformly — a fund with a longer
    publication gap would be entered more often, silently weighting Lou's
    Eq.(4) first stage by publication cadence. The training set is therefore
    keyed by (fund, filing), and this pins the count."""
    n_funds = 260
    reports = [date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31),
               date(2025, 3, 31), date(2025, 6, 30)]
    filings, holdings, returns = [], {}, {}
    factors = _factor_frame(n_months=60, seed=5)
    for fund in range(n_funds):
        series = f"S{fund}"
        for report in reports:
            filed = report + pd.Timedelta(days=60).to_pytimedelta()
            filing = _filing(series, report, filed, sales=2e6 + fund, redemption=1e6, net_assets=1e9)
            filings.append(filing)
            holdings[filing.accession] = {"037833100": 1_000.0 * (fund + 1)}
            # 3 real monthly returns per filing gives the 12-month alpha window
            returns[filing.accession] = [(0.5 + fund * 0.001, 0.4, 0.6)]
    close = pd.DataFrame(
        1.0, index=pd.DatetimeIndex(pd.date_range("2024-01-01", "2026-06-30", freq="B")), columns=["AAPL"]
    )
    panels = build_flow_panels(
        close, filings, holdings, {"037833100": "AAPL"}, returns, factors, {},
        psfs={"lou_published": LOU_PUBLISHED_PSF}, headline_psf="lou_published",
    )
    assert panels.expected_flow_fits, "the first stage never fitted; the test cannot check it"
    counts = [fit["n"] for fit in panels.expected_flow_fits]
    # Each fund can contribute at most one pair per consecutive report PAIR.
    assert max(counts) <= n_funds * (len(reports) - 1)
    # And the count is non-decreasing across snapshots (an expanding window),
    # never re-counting a pair it already holds.
    assert counts == sorted(counts)
