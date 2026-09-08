"""Frazzini-Lamont (2008) dumb-money family: formula tests against the PAPER'S
OWN published worked examples.

The paper supplies TWO fully-worked numerical examples with printed answers,
and both are reproduced here rather than paraphrased:

  * The CISCO EXAMPLE, Section 2, pp.301-302 -- a two-fund sector worked all
    the way through to a printed FLOW of 5.6% of market cap. It exercises
    Eqs. (2)/(3) and Eqs. (6)/(7)/(8) end to end.
  * APPENDIX TABLE A1, p.321 -- a three-fund, five-period table with 21 printed
    counterfactual cells, exercising the pro-rata share, the recursion, the
    newborn rule, the death rule and both aggregate-membership rules.

Because both have KNOWN PUBLISHED ANSWERS that were not derived from this
code, agreement is evidence rather than tautology -- the standard
CLAUDE.md sets for implementing a published formula ("validate against
synthetic data with a known true answer before trusting it on real data").
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.research_lab.cross_sectional_dumb_money import (
    CounterfactualVariant,
    DumbMoneyDiagnostics,
    FundQuarterState,
    counterfactual_tna,
    equity_fund_series,
    stock_flow,
)

# Stand-in periods for the paper's illustrative annual columns. The recursion
# steps by position, not by calendar arithmetic, so any contiguous sequence
# serves; quarters are used because that is what the real panel passes.
P = [pd.Period(f"1980Q{i}", freq="Q") for i in (1, 2, 3, 4)] + [pd.Period("1981Q1", freq="Q")]


def _state(series: str, quarter: pd.Period, tna: float, flow: float, ret: float) -> FundQuarterState:
    return FundQuarterState(
        series_id=series,
        quarter=quarter,
        accession=f"{series}-{quarter}",
        filing_date=quarter.end_time.date(),
        report_date=quarter.end_time.date(),
        net_assets=tna,
        external_flow=flow,
        quarterly_return=ret,
    )


@pytest.fixture
def table_a1_states() -> dict[str, dict[pd.Period, FundQuarterState]]:
    """Appendix Table A1's ACTUAL data, exactly as printed on p.321.

    Columns are labelled 1980, 1981, 1982, 1983, 1985 in both the published
    JFE version and the 2005 NBER working paper. There is no 1984 column and
    the arithmetic is a single one-period step from 1983 to the last column, so
    the label appears to be a typo -- recorded in the pre-registration, and
    irrelevant to the arithmetic tested here.

    Returns are read off the "Returns" block: Fund 1 10/10/5/10/5 across all
    five columns; Fund 2 -5/10/-10 across 1980/1981/1982 (its 1980 return is
    unused, having no prior TNA); Fund 3 10/10/5 across 1982/1983/1985, with no
    1981 return printed -- its birth year -- so 0.0 is used there and cannot
    matter, because a newborn's counterfactual TNA is zero by rule.
    """
    f1 = {
        P[0]: _state("F1", P[0], 100.0, 0.0, 0.0),
        P[1]: _state("F1", P[1], 160.0, 50.0, 0.10),
        P[2]: _state("F1", P[2], 268.0, 100.0, 0.05),
        P[3]: _state("F1", P[3], 395.0, 100.0, 0.10),
        P[4]: _state("F1", P[4], 515.0, 100.0, 0.05),
    }
    f2 = {
        P[0]: _state("F2", P[0], 50.0, 0.0, 0.0),
        P[1]: _state("F2", P[1], 105.0, 50.0, 0.10),
        P[2]: _state("F2", P[2], 144.0, 50.0, -0.10),
        # Fund 2 dies: the table prints a 1983 NAV of 0 against a flow of -144.
        P[3]: _state("F2", P[3], 0.0, -144.0, 0.0),
        P[4]: _state("F2", P[4], 0.0, 0.0, 0.0),
    }
    f3 = {
        # Born in 1981: no 1980 column.
        P[1]: _state("F3", P[1], 50.0, 50.0, 0.0),
        P[2]: _state("F3", P[2], 45.0, -10.0, 0.10),
        P[3]: _state("F3", P[3], 100.0, 50.0, 0.10),
        P[4]: _state("F3", P[4], 154.0, 50.0, 0.05),
    }
    return {"F1": f1, "F2": f2, "F3": f3}


def _counterfactual_path(states, variant) -> dict[str, list[float]]:
    """dTNA for every fund at every column, by re-running the window one step
    longer each time. The public API returns only the window's endpoint, which
    is all the family needs, so the path is assembled here."""
    path: dict[str, list[float]] = {"F1": [], "F2": [], "F3": []}
    for length in range(2, len(P) + 1):
        result = counterfactual_tna(states, P[:length], variant=variant)
        for series in path:
            path[series].append(result.counterfactual_tna.get(series, 0.0))
    return path


class TestAppendixTableA1:
    """All 21 printed counterfactual cells of Table A1, p.321."""

    def test_counterfactual_tna_reproduces_every_published_cell(self, table_a1_states):
        path = _counterfactual_path(table_a1_states, CounterfactualVariant.CONTINUOUS)
        # Published "COUNTERFACTUAL / NAV" rows for 1981, 1982, 1983, 1985.
        assert [round(v) for v in path["F1"]] == [210, 292, 449, 591]
        assert [round(v) for v in path["F2"]] == [105, 141, 0, 0]
        assert [round(v) for v in path["F3"]] == [0, 22, 46, 79]

    def test_implied_counterfactual_flows_reproduce_the_published_flow_rows(
        self, table_a1_states
    ):
        """The table also prints counterfactual FLOWS. They are recovered from
        the TNA path by inverting Eq. (12), Fhat_s = dTNA_s - (1+R_s) dTNA_{s-1},
        so this checks the same recursion from the other side."""
        path = _counterfactual_path(table_a1_states, CounterfactualVariant.CONTINUOUS)
        start = {"F1": 100.0, "F2": 50.0, "F3": 0.0}
        flows: dict[str, list[float]] = {}
        for series, values in path.items():
            previous = [start[series]] + values[:-1]
            flows[series] = [
                value - (1.0 + table_a1_states[series][P[i + 1]].quarterly_return) * prior
                if P[i + 1] in table_a1_states[series]
                else value - prior
                for i, (value, prior) in enumerate(zip(values, previous))
            ]
        assert [round(v) for v in flows["F1"]] == [100, 71, 128, 120]
        # Fund 2's death outflow is its COUNTERFACTUAL 1982 TNA of 141, not its
        # ACTUAL 144 -- the distinction Appendix A.1 is explicit about.
        assert [round(v) for v in flows["F2"]] == [50, 47, -141, 0]
        assert [round(v) for v in flows["F3"]] == [0, 22, 22, 30]

    def test_newborn_receives_zero_counterfactual_assets_in_its_first_period(
        self, table_a1_states
    ):
        result = counterfactual_tna(
            table_a1_states, P[:2], variant=CounterfactualVariant.CONTINUOUS
        )
        assert result.counterfactual_tna["F3"] == 0.0
        assert "F3" in result.newborns
        assert result.newborns.isdisjoint(result.survivors)

    def test_dying_fund_is_zeroed_and_excluded_from_the_aggregate_flow(
        self, table_a1_states
    ):
        result = counterfactual_tna(
            table_a1_states, P[:4], variant=CounterfactualVariant.CONTINUOUS
        )
        assert result.counterfactual_tna.get("F2", 0.0) == 0.0
        # F2 is gone from the endpoint entirely, so it cannot contribute
        # ownership to Eq. (8) either.
        assert "F2" not in result.actual_tna

    def test_the_paper_prints_494_where_its_own_fund_rows_sum_to_495(
        self, table_a1_states
    ):
        """A recorded anomaly in the source, pinned rather than worked around.

        Table A1's 1983 "NAV, last year, of funds existing this year" is printed
        as 494; Fund 1's 395 plus Fund 3's 100 is 495. Using 494 would put the
        final Fund 1 cell at 591.6 (rounding to 592) against the published 591,
        while 495 gives 591.4 -> 591. So 495 is the value the authors' own code
        used and 494 is a typo. Identical in the 2005 NBER draft.
        """
        assert (
            table_a1_states["F1"][P[3]].net_assets + table_a1_states["F3"][P[3]].net_assets
            == 495.0
        )
        path = _counterfactual_path(table_a1_states, CounterfactualVariant.CONTINUOUS)
        assert round(path["F1"][-1]) == 591


class TestCiscoWorkedExample:
    """Section 2, pp.301-302, worked through to a printed FLOW of 5.6%."""

    @pytest.fixture
    def cisco_states(self):
        q0, q1 = P[0], P[1]
        # Quarter 0: tech $20bn, value $80bn. Quarter 1: tech takes an $11bn
        # inflow and $9bn of capital gains (-> $40bn); value has a $1bn outflow
        # and $1bn of gains (-> $80bn).
        return {
            "TECH": {
                q0: _state("TECH", q0, 20e9, 0.0, 0.0),
                q1: _state("TECH", q1, 40e9, 11e9, 9.0 / 20.0),
            },
            "VALUE": {
                q0: _state("VALUE", q0, 80e9, 0.0, 0.0),
                q1: _state("VALUE", q1, 80e9, -1e9, 1.0 / 80.0),
            },
        }

    def test_counterfactual_tnas_match_the_papers_31bn_and_89bn(self, cisco_states):
        result = counterfactual_tna(cisco_states, P[:2], variant=CounterfactualVariant.ROLLING)
        # "the technology fund would receive (.20)*(10) = $2 billion (giving it
        # total assets of $31 billion), while the value fund would receive
        # (.80)*(10) = $8 billion (giving it total assets of $89 billion)"
        assert result.counterfactual_tna["TECH"] == pytest.approx(31e9, rel=1e-12)
        assert result.counterfactual_tna["VALUE"] == pytest.approx(89e9, rel=1e-12)

    def test_flow_for_cisco_matches_the_papers_5_point_6_percent(self, cisco_states):
        result = counterfactual_tna(cisco_states, P[:2], variant=CounterfactualVariant.ROLLING)
        # "the technology fund has 10% of its assets in Cisco, while the value
        # fund has no shares of Cisco" -> $4bn of a $16bn market cap.
        flow = stock_flow(
            holdings_value={"TECH": {"CSCO": 4e9}, "VALUE": {}},
            counterfactual=result,
            market_cap={"CSCO": 16e9},
        )
        # "the entire mutual fund sector owns 25% of Cisco" and "In the
        # counterfactual world the total investment in Cisco is given by
        # (.1)*(31) = $3.1 billion, which is 19.4% of its market capitalization.
        # Hence the FLOW for Cisco ... is 25-19.4 = 5.6%."
        assert flow["CSCO"] == pytest.approx(25.0 - 3.1 / 16.0 * 100.0, rel=1e-12)
        assert flow["CSCO"] == pytest.approx(5.6, abs=0.03)

    def test_flow_is_zero_when_flows_were_already_proportional(self, cisco_states):
        """The construction's own null: if every fund's flow is exactly pro rata
        to its lagged TNA, the counterfactual world IS the actual world and FLOW
        must be identically zero. Nothing in the paper prints this, but it is
        forced by Eq. (8) and it is the sharpest available check that the
        normaliser is not introducing a spurious level."""
        q0, q1 = P[0], P[1]
        states = {
            "A": {
                q0: _state("A", q0, 20e9, 0.0, 0.0),
                q1: _state("A", q1, 20e9 * 1.45 + 2e9, 2e9, 0.45),
            },
            "B": {
                q0: _state("B", q0, 80e9, 0.0, 0.0),
                q1: _state("B", q1, 80e9 * 1.0125 + 8e9, 8e9, 0.0125),
            },
        }
        result = counterfactual_tna(states, P[:2], variant=CounterfactualVariant.ROLLING)
        flow = stock_flow(
            holdings_value={"A": {"X": 4e9}, "B": {"X": 1e9}},
            counterfactual=result,
            market_cap={"X": 16e9},
        )
        assert flow["X"] == pytest.approx(0.0, abs=1e-9)


class TestTheTwoCounterfactualReadings:
    """The main text and Table A1 do not describe the same recursion. The
    pre-registration fixes the main-text ROLLING reading as primary and keeps
    CONTINUOUS as a declared robustness arm; this test pins that they really do
    differ, so the arm is not silently a duplicate of the primary."""

    def test_readings_agree_on_a_single_step_window(self, table_a1_states):
        rolling = counterfactual_tna(
            table_a1_states, P[:2], variant=CounterfactualVariant.ROLLING
        )
        continuous = counterfactual_tna(
            table_a1_states, P[:2], variant=CounterfactualVariant.CONTINUOUS
        )
        assert rolling.counterfactual_tna == continuous.counterfactual_tna

    def test_readings_diverge_once_the_window_is_longer_than_one_step(
        self, table_a1_states
    ):
        rolling = counterfactual_tna(
            table_a1_states, P[:3], variant=CounterfactualVariant.ROLLING
        )
        continuous = counterfactual_tna(
            table_a1_states, P[:3], variant=CounterfactualVariant.CONTINUOUS
        )
        # CONTINUOUS is the published 292; ROLLING re-anchors the share at the
        # window start and lands elsewhere.
        assert round(continuous.counterfactual_tna["F1"]) == 292
        assert rolling.counterfactual_tna["F1"] != pytest.approx(
            continuous.counterfactual_tna["F1"]
        )


class TestNegativeTnaOverride:
    """Appendix A.1's override: a counterfactual TNA driven below zero by
    aggregate outflows is pinned at zero and its shortfall redistributed."""

    def test_pinned_at_zero_and_total_outflow_preserved(self):
        q0, q1 = P[0], P[1]
        # A tiny fund and a large one, with a sector outflow big enough to
        # drive the tiny fund's counterfactual negative.
        states = {
            "SMALL": {
                q0: _state("SMALL", q0, 1.0, 0.0, 0.0),
                q1: _state("SMALL", q1, 1.0, -50.0, 0.0),
            },
            "BIG": {
                q0: _state("BIG", q0, 99.0, 0.0, 0.0),
                q1: _state("BIG", q1, 60.0, -50.0, 0.0),
            },
        }
        diagnostics = DumbMoneyDiagnostics()
        result = counterfactual_tna(
            states, P[:2], variant=CounterfactualVariant.ROLLING, diagnostics=diagnostics
        )
        assert all(v >= 0.0 for v in result.counterfactual_tna.values())
        # Total counterfactual assets equal starting assets plus the sector's
        # actual total flow -- the override redistributes, it does not destroy.
        assert result.aggregate_counterfactual == pytest.approx(100.0 - 100.0, abs=1e-9)


class TestEquityFundSelection:
    """The paper's "domestic equity funds" restriction (p.302), inferred from
    ASSET_CAT because N-PORT publishes no fund-type field."""

    def test_keeps_equity_funds_and_drops_bond_funds(self):
        rows = [
            {"ACCESSION_NUMBER": "a1", "ASSET_CAT": "EC", "VALUE_SUM": "95.0"},
            {"ACCESSION_NUMBER": "a1", "ASSET_CAT": "DBT", "VALUE_SUM": "5.0"},
            {"ACCESSION_NUMBER": "a2", "ASSET_CAT": "EC", "VALUE_SUM": "10.0"},
            {"ACCESSION_NUMBER": "a2", "ASSET_CAT": "DBT", "VALUE_SUM": "90.0"},
        ]
        kept = equity_fund_series(rows, {"a1": "S1", "a2": "S2"})
        assert kept == {"S1"}

    def test_short_positions_do_not_inflate_the_equity_share(self):
        """A negative category total would otherwise shrink the denominator and
        push a balanced fund over the threshold; gross value is used instead."""
        rows = [
            {"ACCESSION_NUMBER": "a1", "ASSET_CAT": "EC", "VALUE_SUM": "60.0"},
            {"ACCESSION_NUMBER": "a1", "ASSET_CAT": "DE", "VALUE_SUM": "-40.0"},
        ]
        assert equity_fund_series(rows, {"a1": "S1"}) == set()

    def test_a_fund_qualifying_in_any_quarter_is_kept(self):
        rows = [
            {"ACCESSION_NUMBER": "a1", "ASSET_CAT": "EC", "VALUE_SUM": "50.0"},
            {"ACCESSION_NUMBER": "a1", "ASSET_CAT": "STIV", "VALUE_SUM": "50.0"},
            {"ACCESSION_NUMBER": "a2", "ASSET_CAT": "EC", "VALUE_SUM": "99.0"},
            {"ACCESSION_NUMBER": "a2", "ASSET_CAT": "STIV", "VALUE_SUM": "1.0"},
        ]
        # Same series, two quarters: one below the bar, one above.
        assert equity_fund_series(rows, {"a1": "S1", "a2": "S1"}) == {"S1"}
