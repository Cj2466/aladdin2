"""Tests for the quality/profitability families (cross_sectional_quality.py)
and their SEC EDGAR XBRL pipeline (edgar_xbrl_provider.py).

Mirrors test_cross_sectional_buyback.py's structure: family-shape
assertions, synthetic vendor-shaped fixtures for the data pipeline (here,
companyfacts-shaped dicts exercising the tag-normalization fallbacks),
hand-computed formula checks against the papers' own definitions, the
point-in-time step panel's visibility/staleness rules, signal direction,
and the harness integration (loud failures, structural look-ahead
impossibility, existing families unaffected)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.edgar_xbrl_provider import (
    AP_COMBINED_TAG,
    LINE_ITEMS,
    extract_annual_tag_series,
    extract_line_items,
)
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
    validate_cross_sectional_data,
)
from app.services.research_lab.cross_sectional_quality import (
    CBOP_FAMILY,
    CBOP_N_TRIALS,
    FUNDAMENTAL_MAX_STALENESS_DAYS,
    NOA_FAMILY,
    NOA_N_TRIALS,
    QUALITY_COST_BPS,
    QUALITY_HOLDING_DAYS,
    QUALITY_N_TRIALS_PER_FAMILY,
    QUALITY_PORTFOLIOS,
    QUALITY_RANK_FRACTION,
    QUALITY_ROBUSTNESS_RANK_FRACTION,
    QUALITY_SAMPLE_SIZE,
    FactorObservation,
    build_point_in_time_factor_frame,
    build_quality_sample,
    compute_cbop_observations,
    compute_noa_observations,
    default_quality_config,
    signal_fundamental_factor,
)

# --- companyfacts-shaped fixture helpers -----------------------------------


def flow(start: str, end: str, val: float, filed: str, form: str = "10-K") -> dict:
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def instant(end: str, val: float, filed: str, form: str = "10-K") -> dict:
    return {"end": end, "val": val, "filed": filed, "form": form}


def node(entries: list[dict]) -> dict:
    """One tag's node, as companyfacts nests it (label/units/USD)."""
    return {"label": "synthetic", "units": {"USD": entries}}


def facts(tags: dict[str, list[dict]]) -> dict:
    """A minimal companyfacts-shaped document (the real nesting observed
    live on CIK0000320193: facts -> us-gaap -> tag -> units -> USD ->
    entry list)."""
    return {
        "cik": 999,
        "entityName": "Synthetic Corp",
        "facts": {
            "us-gaap": {
                tag: {"label": tag, "units": {"USD": entries}} for tag, entries in tags.items()
            }
        },
    }


# A two-fiscal-year synthetic company whose CbOP and NOA are hand-computed
# in the formula tests below. FY2022 filed 2023-02-10, FY2023 filed
# 2024-02-15.
def two_year_company() -> dict:
    return facts(
        {
            "Revenues": [
                flow("2022-01-01", "2022-12-31", 900.0, "2023-02-10"),
                flow("2023-01-01", "2023-12-31", 1000.0, "2024-02-15"),
            ],
            "CostOfGoodsAndServicesSold": [
                flow("2022-01-01", "2022-12-31", 500.0, "2023-02-10"),
                flow("2023-01-01", "2023-12-31", 600.0, "2024-02-15"),
            ],
            "SellingGeneralAndAdministrativeExpense": [
                flow("2022-01-01", "2022-12-31", 90.0, "2023-02-10"),
                flow("2023-01-01", "2023-12-31", 100.0, "2024-02-15"),
            ],
            "AccountsReceivableNetCurrent": [
                instant("2022-12-31", 50.0, "2023-02-10"),
                instant("2023-12-31", 80.0, "2024-02-15"),
            ],
            "InventoryNet": [
                instant("2022-12-31", 40.0, "2023-02-10"),
                instant("2023-12-31", 30.0, "2024-02-15"),
            ],
            # prepaid: absent in BOTH years -> zero change, counted.
            "ContractWithCustomerLiabilityCurrent": [
                instant("2022-12-31", 20.0, "2023-02-10"),
                instant("2023-12-31", 25.0, "2024-02-15"),
            ],
            "AccountsPayableCurrent": [
                instant("2022-12-31", 60.0, "2023-02-10"),
                instant("2023-12-31", 50.0, "2024-02-15"),
            ],
            "AccruedLiabilitiesCurrent": [
                instant("2022-12-31", 10.0, "2023-02-10"),
                instant("2023-12-31", 15.0, "2024-02-15"),
            ],
            "Assets": [
                instant("2022-12-31", 2000.0, "2023-02-10"),
                instant("2023-12-31", 2500.0, "2024-02-15"),
            ],
            "CashAndCashEquivalentsAtCarryingValue": [
                instant("2022-12-31", 400.0, "2023-02-10"),
                instant("2023-12-31", 500.0, "2024-02-15"),
            ],
            "DebtCurrent": [
                instant("2022-12-31", 90.0, "2023-02-10"),
                instant("2023-12-31", 100.0, "2024-02-15"),
            ],
            "LongTermDebtNoncurrent": [
                instant("2022-12-31", 350.0, "2023-02-10"),
                instant("2023-12-31", 400.0, "2024-02-15"),
            ],
            "MinorityInterest": [
                instant("2022-12-31", 45.0, "2023-02-10"),
                instant("2023-12-31", 50.0, "2024-02-15"),
            ],
            "PreferredStockValue": [
                instant("2022-12-31", 25.0, "2023-02-10"),
                instant("2023-12-31", 25.0, "2024-02-15"),
            ],
            "StockholdersEquity": [
                instant("2022-12-31", 800.0, "2023-02-10"),
                instant("2023-12-31", 900.0, "2024-02-15"),
            ],
        }
    )


# --- family shape -----------------------------------------------------------


def test_each_family_is_exactly_nine_definitions_matching_the_declared_grid():
    assert len(CBOP_FAMILY) == CBOP_N_TRIALS == QUALITY_N_TRIALS_PER_FAMILY == 9
    assert len(NOA_FAMILY) == NOA_N_TRIALS == 9
    expected = len(QUALITY_HOLDING_DAYS) * len(QUALITY_PORTFOLIOS) + len(QUALITY_HOLDING_DAYS)
    assert expected == 9


def test_family_covers_every_core_axis_combination_exactly_once():
    for family in (CBOP_FAMILY, NOA_FAMILY):
        core = [s for s in family if s.rank_fraction == QUALITY_RANK_FRACTION]
        combos = {(s.portfolio, s.holding_days) for s in core}
        assert len(core) == 6
        assert combos == {
            (p, h) for p in QUALITY_PORTFOLIOS for h in QUALITY_HOLDING_DAYS
        }
        quintiles = [s for s in family if s.rank_fraction == QUALITY_ROBUSTNESS_RANK_FRACTION]
        assert len(quintiles) == 3
        assert all(s.portfolio == "long_short" for s in quintiles)


def test_pattern_ids_are_unique_within_and_across_the_two_families():
    ids = [s.pattern_id for s in CBOP_FAMILY + NOA_FAMILY]
    assert len(ids) == len(set(ids))


def test_every_spec_requires_the_fundamental_frame_and_carries_a_real_citation():
    for spec in CBOP_FAMILY:
        assert spec.requires_fundamental_signal
        assert "Ball, Gerakos, Linnainmaa & Nikolaev" in spec.citation
        assert "Novy-Marx" in spec.citation
    for spec in NOA_FAMILY:
        assert spec.requires_fundamental_signal
        assert "Hirshleifer, Hou, Teoh & Zhang" in spec.citation


def test_the_two_families_are_never_conflated():
    assert {s.family for s in CBOP_FAMILY} == {"cash_operating_profitability"}
    assert {s.family for s in NOA_FAMILY} == {"net_operating_assets"}


def test_default_config_is_the_shared_equity_cost_basis_and_a_fresh_object():
    a, b = default_quality_config(), default_quality_config()
    assert a is not b
    assert a.cost_bps == QUALITY_COST_BPS == 5.0
    assert a.financing_bps_per_year == 0.0


# --- tag extraction: the annual filters ------------------------------------


def test_flow_extraction_keeps_fiscal_years_and_drops_quarters_and_stubs():
    gaap = facts(
        {
            "Revenues": [
                flow("2022-01-01", "2022-12-31", 100.0, "2023-02-01"),  # a fiscal year
                flow("2022-10-01", "2022-12-31", 25.0, "2023-02-01"),  # a quarter
                flow("2023-01-01", "2023-07-31", 55.0, "2023-09-01"),  # a transition stub
            ]
        }
    )["facts"]["us-gaap"]
    series = extract_annual_tag_series(gaap, "Revenues", kind="flow")
    assert series == {date(2022, 12, 31): (100.0, date(2023, 2, 1))}


def test_extraction_ignores_non_annual_forms():
    gaap = facts(
        {
            "Assets": [
                instant("2022-12-31", 500.0, "2023-02-01"),
                instant("2023-03-31", 999.0, "2023-05-01", form="10-Q"),
            ]
        }
    )["facts"]["us-gaap"]
    series = extract_annual_tag_series(gaap, "Assets", kind="instant")
    assert series == {date(2022, 12, 31): (500.0, date(2023, 2, 1))}


def test_earliest_filed_wins_so_restated_comparatives_never_rewrite_history():
    # The same period appears twice: originally filed 2023-02-01, then
    # restated in the NEXT year's 10-K. Point-in-time keeps the original.
    gaap = facts(
        {
            "Assets": [
                instant("2022-12-31", 500.0, "2023-02-01"),
                instant("2022-12-31", 480.0, "2024-02-01"),
            ]
        }
    )["facts"]["us-gaap"]
    series = extract_annual_tag_series(gaap, "Assets", kind="instant")
    assert series == {date(2022, 12, 31): (500.0, date(2023, 2, 1))}


def test_a_cross_filing_entity_scale_conflict_refuses_the_period_entirely():
    # The real TechnipFMC pathology (see CROSS_FILING_SCALE_CONFLICT_RATIO):
    # the shell's own first 10-K reports 2016 assets of $74,100, the next
    # year's 10-K reports $18.7B COMPARATIVES for the same period end.
    # Earliest-filed-wins would keep the shell's number while other items
    # resolve from the real company's filing — an entity-mixed balance
    # sheet. The conflicted (tag, period) must resolve to NOTHING, and the
    # refusal must be counted.
    doc = two_year_company()
    doc["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(
        instant("2022-12-31", 2000.0 * 500.0, "2024-02-15")
    )
    extraction = extract_line_items(doc)
    assert date(2022, 12, 31) not in extraction.items["assets"]
    assert date(2023, 12, 31) in extraction.items["assets"]  # untouched period
    assert extraction.n_cross_filing_scale_conflicts == 1
    # And downstream: no annual pair can form on the refused year, so both
    # factors correctly produce nothing rather than an entity-mixed value.
    obs, _ = compute_noa_observations(extraction)
    assert obs == []


def test_an_ordinary_restatement_is_not_a_scale_conflict():
    # A later filing restating the same period by a few percent (the normal
    # comparative-restatement case) must NOT trip the entity guard —
    # earliest-filed still wins, exactly as before the guard existed.
    doc = two_year_company()
    doc["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(
        instant("2022-12-31", 1900.0, "2024-02-15")
    )
    extraction = extract_line_items(doc)
    assert extraction.n_cross_filing_scale_conflicts == 0
    resolved = extraction.items["assets"][date(2022, 12, 31)]
    assert resolved.value == 2000.0
    assert resolved.filed == date(2023, 2, 10)


def test_a_duration_entry_never_leaks_into_an_instant_item():
    gaap = facts(
        {"Assets": [flow("2022-01-01", "2022-12-31", 500.0, "2023-02-01")]}
    )["facts"]["us-gaap"]
    assert extract_annual_tag_series(gaap, "Assets", kind="instant") == {}


# --- tag normalization: the measured fallback behaviors ---------------------


def test_revenue_resolves_per_year_across_a_mid_history_tag_switch():
    # The Apple pattern observed live: SalesRevenueNet through FY2017, the
    # ASC 606 tag afterward. Both eras must resolve, each under its own tag.
    doc = facts(
        {
            "SalesRevenueNet": [flow("2016-01-01", "2016-12-31", 100.0, "2017-02-01")],
            "RevenueFromContractWithCustomerExcludingAssessedTax": [
                flow("2018-01-01", "2018-12-31", 130.0, "2019-02-01")
            ],
        }
    )
    revenue = extract_line_items(doc).items["revenue"]
    assert revenue[date(2016, 12, 31)].value == 100.0
    assert revenue[date(2016, 12, 31)].tag == "SalesRevenueNet"
    assert revenue[date(2018, 12, 31)].value == 130.0
    assert (
        revenue[date(2018, 12, 31)].tag
        == "RevenueFromContractWithCustomerExcludingAssessedTax"
    )


def test_revenue_priority_prefers_the_asc606_tag_when_both_exist_for_a_year():
    doc = facts(
        {
            "Revenues": [flow("2019-01-01", "2019-12-31", 111.0, "2020-02-01")],
            "RevenueFromContractWithCustomerExcludingAssessedTax": [
                flow("2019-01-01", "2019-12-31", 110.0, "2020-02-01")
            ],
        }
    )
    resolved = extract_line_items(doc).items["revenue"][date(2019, 12, 31)]
    assert resolved.value == 110.0
    assert resolved.tier == 0


def test_cogs_sums_separate_goods_and_services_tags_the_boeing_ge_pattern():
    doc = facts(
        {
            "CostOfGoodsSold": [flow("2015-01-01", "2015-12-31", 70.0, "2016-02-01")],
            "CostOfServices": [flow("2015-01-01", "2015-12-31", 30.0, "2016-02-05")],
        }
    )
    resolved = extract_line_items(doc).items["cogs"][date(2015, 12, 31)]
    assert resolved.value == 100.0
    assert resolved.tag == "CostOfGoodsSold+CostOfServices"
    # A composite is only knowable once BOTH parts are public.
    assert resolved.filed == date(2016, 2, 5)


def test_sga_composite_sums_ga_plus_one_marketing_concept_the_amazon_pattern():
    doc = facts(
        {
            "GeneralAndAdministrativeExpense": [
                flow("2020-01-01", "2020-12-31", 40.0, "2021-02-01")
            ],
            "MarketingExpense": [flow("2020-01-01", "2020-12-31", 25.0, "2021-02-01")],
        }
    )
    resolved = extract_line_items(doc).items["sga"][date(2020, 12, 31)]
    assert resolved.value == 65.0
    assert resolved.tier == 1


def test_deferred_revenue_totals_current_plus_noncurrent_and_tolerates_one_side():
    doc = facts(
        {
            "ContractWithCustomerLiabilityCurrent": [instant("2020-12-31", 20.0, "2021-02-01")],
            "ContractWithCustomerLiabilityNoncurrent": [
                instant("2020-12-31", 15.0, "2021-02-01")
            ],
            "DeferredRevenueCurrent": [instant("2015-12-31", 8.0, "2016-02-01")],
        }
    )
    deferred = extract_line_items(doc).items["deferred_revenue"]
    assert deferred[date(2020, 12, 31)].value == 35.0
    assert deferred[date(2015, 12, 31)].value == 8.0  # noncurrent missing -> one side only


def test_cash_prefers_the_combined_tag_and_falls_back_to_cash_plus_sti_sum():
    doc = facts(
        {
            "CashCashEquivalentsAndShortTermInvestments": [
                instant("2019-12-31", 100.0, "2020-02-01")
            ],
            "CashAndCashEquivalentsAtCarryingValue": [
                instant("2019-12-31", 60.0, "2020-02-01"),
                instant("2020-12-31", 70.0, "2021-02-01"),
            ],
            "ShortTermInvestments": [instant("2020-12-31", 30.0, "2021-02-01")],
        }
    )
    cash = extract_line_items(doc).items["cash_and_short_term_investments"]
    assert cash[date(2019, 12, 31)].value == 100.0  # combined tag wins outright
    assert cash[date(2019, 12, 31)].tier == 0
    assert cash[date(2020, 12, 31)].value == 100.0  # 70 cash + 30 STI
    assert cash[date(2020, 12, 31)].tier == 1


def test_long_term_debt_total_subtracts_the_separately_known_current_portion():
    doc = facts(
        {
            "LongTermDebt": [instant("2018-12-31", 500.0, "2019-02-01")],
            "LongTermDebtCurrent": [instant("2018-12-31", 80.0, "2019-02-01")],
        }
    )
    resolved = extract_line_items(doc).items["long_term_debt"][date(2018, 12, 31)]
    assert resolved.value == 420.0
    assert resolved.tag == "LongTermDebt-LongTermDebtCurrent"


def test_common_equity_is_parent_equity_minus_preferred():
    doc = facts(
        {
            "StockholdersEquity": [instant("2021-12-31", 900.0, "2022-02-01")],
            "PreferredStockValue": [instant("2021-12-31", 25.0, "2022-02-01")],
        }
    )
    resolved = extract_line_items(doc).items["common_equity"][date(2021, 12, 31)]
    assert resolved.value == 875.0


def test_common_equity_falls_back_to_including_nci_minus_minority_the_cat_pattern():
    doc = facts(
        {
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": [
                instant("2021-12-31", 950.0, "2022-02-01")
            ],
            "MinorityInterest": [instant("2021-12-31", 50.0, "2022-02-01")],
        }
    )
    resolved = extract_line_items(doc).items["common_equity"][date(2021, 12, 31)]
    assert resolved.value == 900.0
    assert resolved.tier == 1


def test_the_ap_accrued_double_count_guard_fires_on_the_combined_tag():
    # The KO/T/XOM pattern: AP only exists COMBINED with accrued
    # liabilities. If a separate accrued figure also existed, counting both
    # would double-count the accrued side inside CbOP's +dAccrued term.
    doc = facts(
        {
            AP_COMBINED_TAG: [instant("2019-12-31", 100.0, "2020-02-01")],
            "AccruedLiabilitiesCurrent": [instant("2019-12-31", 40.0, "2020-02-01")],
        }
    )
    extraction = extract_line_items(doc)
    assert extraction.n_ap_accrued_double_count_guard == 1
    assert date(2019, 12, 31) not in extraction.items["accrued_expenses"]
    assert extraction.items["accounts_payable"][date(2019, 12, 31)].value == 100.0


def test_extraction_tallies_tier_usage_for_every_line_item():
    extraction = extract_line_items(two_year_company())
    assert set(extraction.tier_usage) == set(LINE_ITEMS)
    assert extraction.tier_usage["revenue"]["t1:Revenues"] == 2
    assert extraction.tier_usage["assets"]["t0:Assets"] == 2


# --- the CbOP formula, hand-computed against the paper's definition ---------


def test_cbop_matches_the_hand_computed_ball_et_al_value():
    # OP = 1000 - 600 - 100 = 300.
    # Accrual adjustment = -dAR - dINV - dPrepaid + dDefRev + dAP + dAccrued
    #   = -(80-50) - (30-40) - 0 + (25-20) + (50-60) + (15-10)
    #   = -30 + 10 + 0 + 5 - 10 + 5 = -20.
    # CbOP = (300 - 20) / lagged assets 2000 = 0.14.
    obs, diagnostics = compute_cbop_observations(extract_line_items(two_year_company()))
    assert len(obs) == 1
    assert obs[0].end == date(2023, 12, 31)
    assert obs[0].value == pytest.approx(0.14)
    # Prepaid was absent both years: the paper's missing->0 convention.
    assert diagnostics.n_both_missing_zero["prepaid"] == 1
    assert diagnostics.n_one_sided_changes == 0
    assert diagnostics.n_observations == 1


def test_cbop_becomes_public_at_the_latest_filing_used_never_the_period_end():
    obs, _ = compute_cbop_observations(extract_line_items(two_year_company()))
    assert obs[0].available == date(2024, 2, 15)  # the FY2023 10-K, not 2023-12-31


def test_cbop_refuses_a_year_with_no_cogs_which_is_what_keeps_banks_out():
    doc = two_year_company()
    del doc["facts"]["us-gaap"]["CostOfGoodsAndServicesSold"]
    obs, diagnostics = compute_cbop_observations(extract_line_items(doc))
    assert obs == []
    assert diagnostics.n_refused["missing_cogs"] == 1


def test_cbop_treats_missing_sga_as_zero_and_counts_it():
    doc = two_year_company()
    del doc["facts"]["us-gaap"]["SellingGeneralAndAdministrativeExpense"]
    obs, diagnostics = compute_cbop_observations(extract_line_items(doc))
    # OP rises by the 100 SG&A no longer subtracted: (400 - 20) / 2000.
    assert obs[0].value == pytest.approx(0.19)
    assert diagnostics.n_both_missing_zero["sga"] == 1


def test_cbop_one_sided_accrual_account_is_zero_change_and_counted_not_a_level():
    # Inventory exists in 2022 only (the XOM tag-flicker case). The naive
    # missing->0 reading would fabricate dINV = 0 - 40 = -40 and inflate
    # CbOP by +40/2000 = +0.02; the one-sided rule keeps the hand-computed
    # value except inventory's own +10 term, i.e. (280 - 10)/2000 = 0.135.
    doc = two_year_company()
    doc["facts"]["us-gaap"]["InventoryNet"] = node([instant("2022-12-31", 40.0, "2023-02-10")])
    obs, diagnostics = compute_cbop_observations(extract_line_items(doc))
    assert obs[0].value == pytest.approx(0.135)
    assert diagnostics.n_one_sided_changes == 1


def test_cbop_counts_a_change_term_diffed_across_a_tag_switch():
    doc = two_year_company()
    doc["facts"]["us-gaap"]["ContractWithCustomerLiabilityCurrent"] = node(
        [instant("2023-12-31", 25.0, "2024-02-15")]
    )
    doc["facts"]["us-gaap"]["DeferredRevenueCurrent"] = node(
        [instant("2022-12-31", 20.0, "2023-02-10")]
    )
    obs, diagnostics = compute_cbop_observations(extract_line_items(doc))
    assert obs[0].value == pytest.approx(0.14)  # same arithmetic, different tags
    assert diagnostics.n_tag_switch_pairs == 1


def test_a_multi_year_filing_gap_is_never_treated_as_a_one_year_change():
    doc = two_year_company()
    # Push the earlier fiscal year back to 2020: a 3-year gap between
    # consecutive observed year ends must produce NO observation at all.
    for tag_node in doc["facts"]["us-gaap"].values():
        for e in tag_node["units"]["USD"]:
            for key in ("start", "end", "filed"):
                if key in e:
                    e[key] = e[key].replace("2022", "2020").replace("2023-02", "2021-02")
    obs, _ = compute_cbop_observations(extract_line_items(doc))
    assert obs == []


def test_a_shell_to_operating_company_transition_is_refused_by_both_factors():
    # The FTI/LIN pathology found in the 2026-08-28 verification pass (see
    # ASSETS_SCALE_BREAK_RATIO): a newly-formed holding company's first
    # 10-K carries the pre-merger SHELL's balance sheet (TechnipFMC filed
    # total assets of $74,100 against $28.3B the next year), and dividing
    # the real company's year by the shell's lagged assets fabricates an
    # extreme factor value (NOA = +142,065) that pins the name to one end
    # of the ranking for a year. Such a pair must be REFUSED and counted,
    # for CbOP and NOA alike.
    doc = two_year_company()
    doc["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["val"] = 2500.0 / 150.0  # 150x break
    obs, diagnostics = compute_noa_observations(extract_line_items(doc))
    assert obs == []
    assert diagnostics.n_refused["assets_entity_scale_break"] == 1

    obs, diagnostics = compute_cbop_observations(extract_line_items(doc))
    assert obs == []
    assert diagnostics.n_refused["assets_entity_scale_break"] == 1


def test_a_genuine_large_merger_year_is_not_refused_by_the_scale_break_guard():
    # The bound must sit ABOVE real corporate events: the largest genuine
    # year-over-year asset jump in the production sample is CBOE's 11.0x
    # Bats acquisition (measured 2026-08-28, against the shells' 10,135x
    # and 381,427x). An 11x pair stays in.
    doc = two_year_company()
    doc["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["val"] = 2500.0 / 11.0
    obs, diagnostics = compute_noa_observations(extract_line_items(doc))
    assert len(obs) == 1
    assert diagnostics.n_refused["assets_entity_scale_break"] == 0


# --- the NOA formula, hand-computed against the paper's definition ----------


def test_noa_matches_the_hand_computed_hirshleifer_et_al_value():
    # OA = 2500 - 500 = 2000.
    # CEQ = 900 - 25 = 875.
    # OL = 2500 - 100 - 400 - 50 - 25 - 875 = 1050.
    # NOA = (2000 - 1050) / lagged assets 2000 = 0.475.
    obs, diagnostics = compute_noa_observations(extract_line_items(two_year_company()))
    assert len(obs) == 1
    assert obs[0].end == date(2023, 12, 31)
    assert obs[0].value == pytest.approx(0.475)
    assert diagnostics.n_observations == 1


def test_noa_zeroes_missing_debt_items_per_the_papers_stated_convention():
    doc = two_year_company()
    del doc["facts"]["us-gaap"]["DebtCurrent"]
    del doc["facts"]["us-gaap"]["MinorityInterest"]
    obs, diagnostics = compute_noa_observations(extract_line_items(doc))
    # OL grows by the zeroed 100 + 50: OL = 1200; NOA = 800/2000 = 0.40.
    assert obs[0].value == pytest.approx(0.40)
    assert diagnostics.n_missing_treated_as_zero["short_term_debt"] == 1
    assert diagnostics.n_missing_treated_as_zero["minority_interest"] == 1


def test_noa_refuses_when_cash_or_common_equity_is_unobservable():
    doc = two_year_company()
    del doc["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"]
    obs, diagnostics = compute_noa_observations(extract_line_items(doc))
    assert obs == []
    assert diagnostics.n_refused["missing_cash_and_short_term_investments"] == 1

    doc = two_year_company()
    del doc["facts"]["us-gaap"]["StockholdersEquity"]
    obs, diagnostics = compute_noa_observations(extract_line_items(doc))
    assert obs == []
    assert diagnostics.n_refused["missing_common_equity"] == 1


# --- the point-in-time step panel ------------------------------------------


def bdays(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=periods)


def test_panel_makes_a_value_visible_at_its_filing_date_not_its_period_end():
    close = pd.DataFrame(100.0, index=bdays("2024-01-02", 60), columns=["AAA"])
    frame, _, _ = build_point_in_time_factor_frame(
        close, {"AAA": [FactorObservation(date(2023, 12, 31), 0.14, date(2024, 2, 15))]}
    )
    assert frame.loc["2024-02-14", "AAA"] != frame.loc["2024-02-14", "AAA"]  # NaN before
    assert frame.loc["2024-02-15", "AAA"] == 0.14
    assert frame.loc["2024-03-01", "AAA"] == 0.14  # step-forward-filled


def test_panel_never_back_fills_and_never_interpolates():
    close = pd.DataFrame(100.0, index=bdays("2024-01-02", 120), columns=["AAA"])
    frame, _, _ = build_point_in_time_factor_frame(
        close,
        {
            "AAA": [
                FactorObservation(date(2023, 12, 31), 0.10, date(2024, 2, 1)),
                FactorObservation(date(2024, 12, 31), 0.30, date(2024, 6, 3)),
            ]
        },
    )
    assert frame["AAA"].iloc[0] != frame["AAA"].iloc[0]  # NaN before the first filing
    between = frame.loc["2024-04-01":"2024-05-31", "AAA"].dropna().unique()
    assert list(between) == [0.10]  # a flat step, no drift toward 0.30


def test_panel_refuses_a_value_carried_past_the_staleness_bound():
    close = pd.DataFrame(100.0, index=pd.bdate_range("2020-01-02", "2021-12-31"), columns=["AAA"])
    filed = date(2020, 1, 10)
    frame, ages, _ = build_point_in_time_factor_frame(
        close, {"AAA": [FactorObservation(date(2019, 12, 31), 0.2, filed)]}
    )
    cutoff = pd.Timestamp(filed) + pd.Timedelta(days=FUNDAMENTAL_MAX_STALENESS_DAYS)
    before = frame.loc[frame.index <= cutoff, "AAA"].dropna()
    after = frame.loc[frame.index > cutoff, "AAA"]
    assert not before.empty and (before == 0.2).all()
    assert after.isna().all()
    # The age frame measures what the median-staleness diagnostic reports.
    assert ages.loc["2020-01-10", "AAA"] == 0.0
    assert ages.loc["2020-02-10", "AAA"] == 31.0


def test_panel_drops_a_stale_fiscal_year_arriving_after_a_fresher_one():
    close = pd.DataFrame(100.0, index=bdays("2024-01-02", 200), columns=["AAA"])
    frame, _, _ = build_point_in_time_factor_frame(
        close,
        {
            "AAA": [
                FactorObservation(date(2023, 12, 31), 0.30, date(2024, 2, 1)),
                # An amended OLDER year filed later must not overwrite.
                FactorObservation(date(2022, 12, 31), 0.99, date(2024, 5, 1)),
            ]
        },
    )
    assert set(frame["AAA"].dropna().unique()) == {0.30}


def test_panel_is_aligned_with_close_and_reports_unusable_tickers():
    close = pd.DataFrame(100.0, index=bdays("2024-01-02", 30), columns=["AAA", "BBB"])
    frame, ages, unusable = build_point_in_time_factor_frame(
        close, {"AAA": [FactorObservation(date(2023, 12, 31), 0.1, date(2024, 1, 15))]}
    )
    assert unusable == ["BBB"]
    assert frame["BBB"].isna().all()
    validate_cross_sectional_data(CrossSectionalData(close=close, fundamental_signal=frame))
    assert list(frame.columns) == list(close.columns)
    assert ages.index.equals(close.index)


# --- the signal and its directions ------------------------------------------


def quality_view(values: dict[str, float]) -> CrossSectionalData:
    index = bdays("2024-01-02", 5)
    close = pd.DataFrame(100.0, index=index, columns=list(values))
    frame = pd.DataFrame(np.nan, index=index, columns=list(values))
    frame.iloc[-1] = pd.Series(values)
    return CrossSectionalData(close=close, fundamental_signal=frame)


def test_cbop_direction_ranks_the_most_profitable_firm_on_top():
    signal = signal_fundamental_factor(
        quality_view({"HIGH": 0.30, "MID": 0.10, "LOW": -0.05}), direction=+1.0
    )
    assert signal.idxmax() == "HIGH"
    assert signal.idxmin() == "LOW"


def test_noa_direction_ranks_the_leanest_balance_sheet_on_top():
    # High NOA = bloat = the SHORT side per Hirshleifer et al.; the -1.0
    # direction lands low-NOA firms in the harness's long top decile.
    signal = signal_fundamental_factor(
        quality_view({"BLOATED": 0.90, "MID": 0.50, "LEAN": 0.10}), direction=-1.0
    )
    assert signal.idxmax() == "LEAN"
    assert signal.idxmin() == "BLOATED"


def test_signal_refuses_a_ticker_with_no_current_factor_value():
    signal = signal_fundamental_factor(
        quality_view({"AAA": 0.2, "BBB": float("nan")}), direction=+1.0
    )
    assert np.isfinite(signal["AAA"])
    assert signal["BBB"] != signal["BBB"]


def test_signal_raises_loudly_when_the_fundamental_frame_was_never_supplied():
    index = bdays("2024-01-02", 5)
    data = CrossSectionalData(close=pd.DataFrame(100.0, index=index, columns=["AAA"]))
    with pytest.raises(ValueError, match="fundamental_signal"):
        signal_fundamental_factor(data, direction=+1.0)


# --- harness integration ----------------------------------------------------


def test_a_spec_requiring_the_fundamental_frame_fails_loudly_when_it_is_absent():
    spec = CBOP_FAMILY[0]
    index = bdays("2024-01-02", 300)
    data = CrossSectionalData(close=pd.DataFrame(100.0, index=index, columns=["AAA", "BBB"]))
    with pytest.raises(ValueError, match="fundamental_signal"):
        run_cross_sectional_backtest(
            data, spec, CrossSectionalConfig(), fixed_universe_membership(["AAA", "BBB"])
        )


def test_a_misaligned_fundamental_frame_is_rejected_by_the_harness_validator():
    index = bdays("2024-01-02", 30)
    close = pd.DataFrame(100.0, index=index, columns=["AAA"])
    frame = pd.DataFrame(0.1, index=index[:-5], columns=["AAA"])
    with pytest.raises(ValueError, match="fundamental_signal"):
        validate_cross_sectional_data(
            CrossSectionalData(close=close, fundamental_signal=frame)
        )


def test_the_fundamental_frame_is_sliced_to_the_formation_date_so_look_ahead_is_impossible():
    """A future jump in a ticker's factor value must not affect an earlier
    formation's legs — the harness hands the signal only rows <= the
    formation date, whatever the full frame contains."""
    tickers = [f"T{i:02d}" for i in range(12)]
    index = bdays("2024-01-02", 40)
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        100.0 * np.cumprod(1 + rng.normal(0, 0.01, size=(len(index), 12)), axis=0),
        index=index,
        columns=tickers,
    )
    frame = pd.DataFrame(
        np.tile(np.arange(12, dtype=float), (len(index), 1)), index=index, columns=tickers
    )
    # T00 (the weakest name point-in-time) explodes AFTER the first
    # formation. If look-ahead were possible it would rank long immediately.
    frame.iloc[20:, 0] = 999.0

    spec = CrossSectionalSpec(
        pattern_id="lookahead_probe",
        family="test",
        citation="test",
        signal_fn=lambda view: signal_fundamental_factor(view, direction=+1.0),
        lookback_days=1,
        holding_days=10,
        portfolio="long_short",
        rank_fraction=0.2,
        requires_fundamental_signal=True,
    )
    config = CrossSectionalConfig(min_names_per_leg=2)
    result = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=frame),
        spec,
        config,
        fixed_universe_membership(tickers),
    )
    first = result.formations[0]
    assert first.date == index[1]  # lookback 1 -> first formation at row 1
    assert first.long_tickers == ["T11", "T10"]
    assert "T00" in first.short_tickers
    # ...and once the jump is inside the history view, it ranks long.
    later = [f for f in result.formations if f.date >= index[21]]
    assert later and all(f.long_tickers[0] == "T00" for f in later)


def test_existing_close_only_families_are_unaffected_by_the_new_optional_frame():
    index = bdays("2024-01-02", 40)
    close = pd.DataFrame(
        100.0 + np.arange(40)[:, None] * np.array([[1.0, -0.5, 0.2, 0.4]]),
        index=index,
        columns=["A", "B", "C", "D"],
    )
    data = CrossSectionalData(close=close)
    assert data.fundamental_signal is None
    validate_cross_sectional_data(data)  # None frame passes untouched


# --- the pre-registered sample ----------------------------------------------


def test_quality_sample_is_deterministic_capped_and_drawn_from_the_real_union():
    start, end = date(2015, 1, 7), date(2026, 8, 1)
    sample_a, full_size_a = build_quality_sample(start, end)
    sample_b, full_size_b = build_quality_sample(start, end)
    assert sample_a == sample_b
    assert full_size_a == full_size_b
    assert len(sample_a) == min(QUALITY_SAMPLE_SIZE, full_size_a)
    assert sample_a == sorted(sample_a)
    assert len(set(sample_a)) == len(sample_a)
