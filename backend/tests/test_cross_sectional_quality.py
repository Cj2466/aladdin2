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

import httpx
import numpy as np
import pandas as pd
import pytest

from app.services.market_data.edgar_xbrl_provider import (
    AP_COMBINED_TAG,
    LINE_ITEMS,
    MAX_PREDECESSOR_CANDIDATES,
    CikResolutionReport,
    EdgarFetchError,
    EdgarNotFoundError,
    EdgarXbrlProvider,
    annual_accessions_from_facts,
    count_annual_facts,
    extract_annual_tag_series,
    extract_line_items,
    filer_cik_counts,
    normalize_entity_name,
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


# --- successor-shell CIK resolution -----------------------------------------
#
# The bug: SEC's company_tickers.json maps a ticker to whichever registrant
# currently CARRIES it, which after a holding-company reorganization is a
# newly-registered successor with no annual filing history. XOM resolved to
# CIK 2115436 ("ExxonMobil Holdings Corp": 29 filings from 2026-07-01 to
# 2026-08-28, ZERO of them 10-Ks) instead of CIK 34088 ("EXXON MOBIL CORP": 3,554 filings from
# 1994, 10-Ks through 2026-02-18) — so a top-10 S&P 500 constituent produced
# no line item in any year, in silence, in every EDGAR-XBRL family.
#
# Every fixture below reproduces a shape MEASURED live on 2026-09-02, cited
# per test; the tests themselves touch no network (httpx.MockTransport
# everywhere), matching this file's and test_edgar_filing_text_provider.py's
# standing no-network contract.

# The two real CIKs, kept as named constants so the fixtures below read as
# the case they encode.
XOM_SHELL_CIK = 2115436
XOM_REAL_CIK = 34088
XOM_ENTITY_NAME = "Exxon Mobil Corporation"  # BOTH documents carry this


def accn(cik: int, seq: int) -> str:
    """A well-formed accession number issued under `cik` — the real format
    is "0000034088-26-000093" (filer CIK, 2-digit year, 6-digit sequence)."""
    return f"{cik:010d}-26-{seq:06d}"


def shell_facts() -> dict:
    """The successor shell as measured: 10-Q facts ONLY, every one of them
    filed under the PREDECESSOR's accession prefix (269 of the real
    document's 274 facts were), plus a handful under a filing agent's
    (RR Donnelley, CIK 1193125 — the real document had 5)."""
    return {
        "cik": XOM_SHELL_CIK,
        "entityName": XOM_ENTITY_NAME,
        "facts": {
            "us-gaap": {
                "Assets": {
                    "label": "Assets",
                    "units": {
                        "USD": [
                            {
                                "end": "2026-06-30",
                                "val": 4.5e11,
                                "filed": "2026-08-03",
                                "form": "10-Q",
                                "accn": accn(XOM_REAL_CIK, 93),
                            },
                            {
                                "end": "2026-03-31",
                                "val": 4.4e11,
                                "filed": "2026-05-01",
                                "form": "10-Q",
                                "accn": accn(XOM_REAL_CIK, 70),
                            },
                        ]
                    },
                }
            },
            "ffd": {
                "OfferingFee": {
                    "label": "fee",
                    "units": {
                        "USD": [
                            {
                                "end": "2026-07-01",
                                "val": 1.0,
                                "filed": "2026-07-01",
                                "form": "POSASR",
                                "accn": accn(1193125, 292453),
                            }
                        ]
                    },
                }
            },
        },
    }


def predecessor_facts(entity_name: str = XOM_ENTITY_NAME) -> dict:
    """The real operating company: annual (10-K) facts, same entityName."""
    doc = two_year_company()
    doc["cik"] = XOM_REAL_CIK
    doc["entityName"] = entity_name
    for tag_node in doc["facts"]["us-gaap"].values():
        for entries in tag_node["units"].values():
            for i, entry in enumerate(entries):
                entry["accn"] = accn(XOM_REAL_CIK, 45 + i)
    return doc


def mock_provider(handler, **kwargs) -> EdgarXbrlProvider:
    """Same shape as test_edgar_filing_text_provider.py's `_provider`: a
    real provider over an httpx.MockTransport, so every fetch path runs for
    real and no socket is opened. cache_dir=None keeps each test's fetches
    entirely in memory."""
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    kwargs.setdefault("cache_dir", None)
    kwargs.setdefault("min_request_interval", 0.0)
    return EdgarXbrlProvider(client=client, sleep=lambda _s: None, **kwargs)


def companyfacts_handler(documents: dict[int, dict], calls: list[str] | None = None):
    """Serves /api/xbrl/companyfacts/CIK##########.json from `documents`,
    404ing anything absent — which is exactly what a FILING AGENT's CIK
    does in reality (1193125, 1144204 and 1140361 all 404, verified live
    2026-09-02)."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if calls is not None:
            calls.append(url)
        if "company_tickers" in url:
            return httpx.Response(
                200,
                json={
                    "0": {"cik_str": XOM_SHELL_CIK, "ticker": "XOM", "title": "ExxonMobil Holdings"},
                    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"},
                },
            )
        for cik, doc in documents.items():
            if f"CIK{cik:010d}" in url:
                return httpx.Response(200, json=doc)
        return httpx.Response(404)

    return handler


# --- the pure helpers -------------------------------------------------------


def test_count_annual_facts_counts_only_annual_forms_across_every_taxonomy():
    assert count_annual_facts(shell_facts()) == 0  # 10-Q + POSASR only
    assert count_annual_facts(predecessor_facts()) > 0
    mixed = facts({"Assets": [instant("2023-12-31", 1.0, "2024-02-01", form="10-Q")]})
    assert count_annual_facts(mixed) == 0
    mixed["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(
        instant("2023-12-31", 1.0, "2024-02-01", form="10-K/A")
    )
    assert count_annual_facts(mixed) == 1


def test_filer_cik_counts_reads_accession_prefixes_and_ignores_malformed_ones():
    counts = filer_cik_counts(shell_facts())
    assert counts[XOM_REAL_CIK] == 2  # the predecessor filed the 10-Q facts
    assert counts[1193125] == 1  # the filing agent filed the POSASR fee
    # Junk accessions are ignored, never guessed at.
    doc = facts({"Assets": [instant("2023-12-31", 1.0, "2024-02-01")]})
    doc["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["accn"] = "not-an-accession"
    assert filer_cik_counts(doc) == {}


def test_entity_name_normalization_ignores_case_and_punctuation_but_not_suffixes():
    assert normalize_entity_name("Exxon Mobil Corporation") == normalize_entity_name(
        "EXXON MOBIL CORP.ORATION"
    )
    assert normalize_entity_name(None) == ""
    # Suffix stripping is deliberately NOT done: it would make two different
    # companies compare equal, and this comparison is the only gate between a
    # coincidental accession prefix and a wrong filing history.
    assert normalize_entity_name("Acme Holdings") != normalize_entity_name("Acme Group")
    assert normalize_entity_name("Acme Corp") != normalize_entity_name("Acme Inc")


# --- resolve_company_facts: the redirect and its two gates ------------------


def test_the_real_xom_case_redirects_to_the_cik_that_holds_the_filing_history():
    """The bug, end to end on the measured shapes: a resolved CIK with no
    annual facts whose own document says the predecessor filed it."""
    provider = mock_provider(
        companyfacts_handler({XOM_SHELL_CIK: shell_facts(), XOM_REAL_CIK: predecessor_facts()})
    )
    filing_cik, resolved = provider.resolve_company_facts(XOM_SHELL_CIK)

    assert filing_cik == XOM_REAL_CIK
    assert count_annual_facts(resolved) > 0
    # And the line items the pipeline actually consumes now exist.
    extraction = extract_line_items(resolved)
    assert extraction.items["assets"], "the redirected document must yield annual line items"

    redirect = provider.cik_resolution.redirects[XOM_SHELL_CIK]
    assert redirect.filing_cik == XOM_REAL_CIK
    assert redirect.n_annual_facts == count_annual_facts(resolved)
    assert "2115436" in provider.cik_resolution.describe()
    assert "34088" in provider.cik_resolution.describe()
    assert not provider.cik_resolution.without_annual_history


def test_a_cik_with_annual_history_is_never_redirected_and_costs_no_extra_fetch():
    """The regression guard for every currently-working ticker: 150 of the
    162 production companyfacts documents contain facts filed under some
    OTHER CIK (filing agents), so a foreign accession prefix must NOT on its
    own trigger anything."""
    doc = predecessor_facts()
    doc["cik"] = 320193
    # An agent-filed fact, exactly like the real documents carry.
    doc["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["accn"] = accn(1193125, 1)
    calls: list[str] = []
    provider = mock_provider(companyfacts_handler({320193: doc}, calls))

    filing_cik, resolved = provider.resolve_company_facts(320193)

    assert filing_cik == 320193
    assert resolved is not None and count_annual_facts(resolved) > 0
    assert provider.cik_resolution.redirects == {}
    assert provider.cik_resolution.without_annual_history == {}
    assert provider.cik_resolution.describe() == ""
    assert len(calls) == 1, f"a healthy CIK must cost exactly one fetch, got {calls}"


def test_a_candidate_without_companyfacts_is_refused_and_reported_not_silently_dropped():
    """Sea Limited's real shape: a foreign private issuer that files 20-F,
    so it genuinely has no annual facts, and whose three foreign accession
    prefixes are all filing agents whose CIKs 404 on the companyfacts
    endpoint. The right answer is to refuse AND say so."""
    shell = shell_facts()
    shell["entityName"] = "Sea Limited"
    provider = mock_provider(companyfacts_handler({XOM_SHELL_CIK: shell}))  # nothing else served

    filing_cik, resolved = provider.resolve_company_facts(XOM_SHELL_CIK)

    assert filing_cik == XOM_SHELL_CIK  # unchanged: no candidate passed
    assert count_annual_facts(resolved) == 0
    assert provider.cik_resolution.redirects == {}
    assert provider.cik_resolution.without_annual_history == {XOM_SHELL_CIK: "Sea Limited"}
    assert "no candidate predecessor CIK passed validation" in (
        provider.cik_resolution.describe()
    )


def test_a_candidate_naming_a_different_company_is_refused():
    """Gate (2) doing real work: the candidate HAS annual history, but it is
    somebody else's. Accepting it would silently graft the wrong company's
    balance sheet onto this ticker — far worse than excluding the ticker."""
    provider = mock_provider(
        companyfacts_handler(
            {
                XOM_SHELL_CIK: shell_facts(),
                XOM_REAL_CIK: predecessor_facts(entity_name="Some Other Company Inc"),
            }
        )
    )

    filing_cik, _ = provider.resolve_company_facts(XOM_SHELL_CIK)

    assert filing_cik == XOM_SHELL_CIK
    assert provider.cik_resolution.redirects == {}
    assert XOM_SHELL_CIK in provider.cik_resolution.without_annual_history


def test_a_candidate_with_no_annual_history_of_its_own_is_refused():
    """Gate (1): redirecting from one fundamentals-empty CIK to another
    fixes nothing and would hide the problem behind a 'redirected' label."""
    empty_candidate = shell_facts()
    empty_candidate["cik"] = XOM_REAL_CIK
    provider = mock_provider(
        companyfacts_handler({XOM_SHELL_CIK: shell_facts(), XOM_REAL_CIK: empty_candidate})
    )

    filing_cik, _ = provider.resolve_company_facts(XOM_SHELL_CIK)

    assert filing_cik == XOM_SHELL_CIK
    assert XOM_SHELL_CIK in provider.cik_resolution.without_annual_history


def test_candidate_probing_is_capped_and_ordered_by_who_filed_the_most():
    """The cap bounds what one pathological document can cost, and the
    order means the entity that filed the bulk of it is always tried
    first (the real shell: 269 predecessor facts vs 5 agent facts)."""
    shell = shell_facts()
    usd = shell["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    # Five distinct foreign filers, each with fewer facts than the real one.
    for i, agent in enumerate((7001, 7002, 7003, 7004, 7005)):
        usd.append(
            {
                "end": f"2026-0{i + 1}-28",
                "val": 1.0,
                "filed": "2026-08-03",
                "form": "10-Q",
                "accn": accn(agent, i),
            }
        )
    calls: list[str] = []
    provider = mock_provider(
        companyfacts_handler({XOM_SHELL_CIK: shell, XOM_REAL_CIK: predecessor_facts()}, calls)
    )

    filing_cik, _ = provider.resolve_company_facts(XOM_SHELL_CIK)

    assert filing_cik == XOM_REAL_CIK  # the majority filer is tried FIRST
    companyfacts_calls = [c for c in calls if "companyfacts" in c]
    # The shell itself plus at most MAX_PREDECESSOR_CANDIDATES probes.
    assert len(companyfacts_calls) <= 1 + MAX_PREDECESSOR_CANDIDATES

    # And when nothing can pass, the cap really binds.
    calls.clear()
    capped = mock_provider(companyfacts_handler({XOM_SHELL_CIK: shell}, calls))
    capped.resolve_company_facts(XOM_SHELL_CIK)
    assert len([c for c in calls if "companyfacts" in c]) == 1 + MAX_PREDECESSOR_CANDIDATES


def test_a_refusal_is_remembered_so_it_is_not_re_probed_or_re_logged():
    """Every fetch entry point resolves the same CIK independently (the
    NOA-neutral path calls both), so an un-memoized refusal would re-spend
    MAX_PREDECESSOR_CANDIDATES requests against SEC's shared public service
    on every pass."""
    shell = shell_facts()
    shell["entityName"] = "Sea Limited"
    calls: list[str] = []
    provider = mock_provider(companyfacts_handler({XOM_SHELL_CIK: shell}, calls))

    provider.resolve_company_facts(XOM_SHELL_CIK)
    after_first = len([c for c in calls if "companyfacts" in c])
    # The shell's own fetch plus one probe per distinct foreign filer in it
    # (this fixture has two: the predecessor and one filing agent).
    foreign = [c for c in filer_cik_counts(shell) if c != XOM_SHELL_CIK]
    assert len(foreign) == 2
    assert after_first == 1 + len(foreign) == 3

    filing_cik, _ = provider.resolve_company_facts(XOM_SHELL_CIK)
    assert filing_cik == XOM_SHELL_CIK
    # Only the shell's own (cached-by-the-caller) fetch, no re-probe.
    assert len([c for c in calls if "companyfacts" in c]) == after_first + 1
    assert provider.cik_resolution.without_annual_history == {XOM_SHELL_CIK: "Sea Limited"}


def test_a_transient_candidate_failure_is_not_memoized_as_a_permanent_refusal():
    """Found by the independent verification pass, reproduced here: a 404
    from a candidate is EDGAR ANSWERING (a filing agent has no companyfacts,
    and retrying cannot change that), but a 503 is an OUTAGE. Treating them
    alike memoized the outage, so once the probe hit a bad minute the
    company was dropped for the whole rest of the run — silently, which is
    the exact failure mode this whole change exists to remove."""
    calls: list[str] = []
    base = companyfacts_handler(
        {XOM_SHELL_CIK: shell_facts(), XOM_REAL_CIK: predecessor_facts()}, calls
    )
    outage = {"on": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if outage["on"] and f"CIK{XOM_REAL_CIK:010d}" in str(request.url):
            calls.append(str(request.url))
            return httpx.Response(503)
        return base(request)

    provider = mock_provider(handler)

    filing_cik, _ = provider.resolve_company_facts(XOM_SHELL_CIK)
    assert filing_cik == XOM_SHELL_CIK  # nothing could be validated
    assert XOM_SHELL_CIK in provider.cik_resolution.without_annual_history
    # ...but the refusal is flagged PROVISIONAL, and says so out loud.
    assert provider.cik_resolution.provisional_refusals == {XOM_SHELL_CIK}
    assert "PROVISIONAL" in provider.cik_resolution.describe()

    outage["on"] = False
    filing_cik, resolved = provider.resolve_company_facts(XOM_SHELL_CIK)

    assert filing_cik == XOM_REAL_CIK, "a healed outage must be re-probed"
    assert count_annual_facts(resolved) > 0
    # And the stale refusal is cleared rather than left to contradict the
    # redirect in the same report.
    assert provider.cik_resolution.without_annual_history == {}
    assert provider.cik_resolution.provisional_refusals == set()
    assert "PROVISIONAL" not in provider.cik_resolution.describe()


def test_a_404_candidate_is_a_real_answer_and_stays_memoized():
    """The other half of the distinction: EdgarNotFoundError means EDGAR
    answered "no such document", which is exactly what a filing agent's CIK
    returns. That refusal IS decided, so it must not be re-probed."""
    shell = shell_facts()
    shell["entityName"] = "Sea Limited"
    calls: list[str] = []
    provider = mock_provider(companyfacts_handler({XOM_SHELL_CIK: shell}, calls))

    provider.resolve_company_facts(XOM_SHELL_CIK)
    assert provider.cik_resolution.provisional_refusals == set()
    assert "PROVISIONAL" not in provider.cik_resolution.describe()
    after_first = len([c for c in calls if "companyfacts" in c])

    provider.resolve_company_facts(XOM_SHELL_CIK)
    assert len([c for c in calls if "companyfacts" in c]) == after_first + 1


def test_a_404_raises_the_not_found_subclass_of_the_ordinary_fetch_error():
    """The subclass is what lets the probe tell an answer from an outage.
    It must stay a SUBCLASS so every existing `except EdgarFetchError`
    keeps catching it unchanged."""
    assert issubclass(EdgarNotFoundError, EdgarFetchError)
    provider = mock_provider(lambda _request: httpx.Response(404))
    with pytest.raises(EdgarNotFoundError):
        provider.get_company_facts(42)
    with pytest.raises(EdgarFetchError):  # the base class still catches it
        provider.get_company_facts(42)


def test_a_redirect_is_remembered_so_the_candidate_probe_runs_once_per_provider():
    calls: list[str] = []
    provider = mock_provider(
        companyfacts_handler(
            {XOM_SHELL_CIK: shell_facts(), XOM_REAL_CIK: predecessor_facts()}, calls
        )
    )
    provider.resolve_company_facts(XOM_SHELL_CIK)
    first = len(calls)
    provider.resolve_company_facts(XOM_SHELL_CIK)
    # Second call: the shell doc and the known predecessor doc, no re-probe.
    assert len(calls) - first <= 2
    assert provider.cik_resolution.redirects[XOM_SHELL_CIK].filing_cik == XOM_REAL_CIK


# --- the two fetch entry points -------------------------------------------


def test_fetch_line_items_gives_the_shell_ticker_its_real_filing_history():
    """What the whole fix is for: XOM ranks again. Before it, this ticker
    resolved a CIK, fetched 200 OK, and produced an extraction whose every
    item dict was empty — indistinguishable from a name with no data."""
    documents = {XOM_SHELL_CIK: shell_facts(), XOM_REAL_CIK: predecessor_facts()}
    documents[320193] = predecessor_facts(entity_name="Apple Inc.")
    documents[320193]["cik"] = 320193
    provider = mock_provider(companyfacts_handler(documents))

    extractions, missing_cik, failed = provider.fetch_line_items_for_tickers(["XOM", "AAPL"])

    assert missing_cik == [] and failed == []
    assert extractions["XOM"].items["assets"], "XOM must now carry annual line items"
    assert extractions["XOM"].items["revenue"]
    # The unaffected sibling is untouched, and nothing about it is reported.
    assert extractions["AAPL"].items["assets"]
    assert set(provider.cik_resolution.redirects) == {XOM_SHELL_CIK}


def test_the_pre_fix_behaviour_really_was_an_empty_silent_extraction():
    """Pins the bug itself, so a regression is a failing test and not a
    silently smaller cross-section: WITHOUT the redirect, the shell yields
    an extraction with no observations at all and no failure signal."""
    empty = extract_line_items(shell_facts())
    assert all(series == {} for series in empty.items.values())
    assert empty.n_cross_filing_scale_conflicts == 0


def test_sic_history_reads_headers_under_the_cik_that_actually_filed_them():
    """An archived filing lives under the CIK that FILED it, so using the
    shell's CIK in the /Archives/edgar/data/{cik}/... path would 404 on
    every one of the predecessor's 10-Ks. The SIC series must therefore be
    keyed to the same filing events the line items came from."""
    fetched_urls: list[str] = []
    base = companyfacts_handler({XOM_SHELL_CIK: shell_facts(), XOM_REAL_CIK: predecessor_facts()})

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/Archives/" in url:
            fetched_urls.append(url)
            return httpx.Response(
                200,
                text=(
                    f"CENTRAL INDEX KEY:\t\t\t{XOM_REAL_CIK:010d}\n"
                    "STANDARD INDUSTRIAL CLASSIFICATION:\tPETROLEUM REFINING [2911]\n"
                ),
            )
        if "/submissions/" in url:
            return httpx.Response(200, json={"sic": "2911"})
        return base(request)

    provider = mock_provider(handler)
    histories, missing_cik, failed = provider.fetch_sic_history_for_tickers(["XOM"])

    assert missing_cik == [] and failed == []
    history = histories["XOM"]
    assert history.cik == XOM_REAL_CIK
    assert history.events and all(sic == 2911 for _filed, sic in history.events)
    assert history.n_header_fetch_failures == 0
    assert history.current_sic == 2911
    assert fetched_urls, "no filing header was fetched at all"
    assert all(f"/data/{XOM_REAL_CIK}/" in url for url in fetched_urls), fetched_urls


def test_annual_accessions_come_from_the_redirected_document():
    provider = mock_provider(
        companyfacts_handler({XOM_SHELL_CIK: shell_facts(), XOM_REAL_CIK: predecessor_facts()})
    )
    accessions = provider.get_annual_accessions(XOM_SHELL_CIK)
    assert accessions == annual_accessions_from_facts(predecessor_facts())
    assert accessions, "the shell alone would have yielded none"


def test_an_empty_resolution_report_describes_itself_as_nothing_to_say():
    assert CikResolutionReport().describe() == ""


# --- pins added by the SECOND independent verification pass -----------------
#
# Each of the five below was written because a MUTATION of the shipped fix
# survived the whole suite (all 2,990 tests, not just this file). Each was
# then confirmed to fail against its mutation and pass against the real
# code, so it pins behaviour rather than merely describing it.


def test_annual_accessions_include_only_annual_forms():
    """MUTATION SURVIVOR: dropping the ANNUAL_FORMS filter inside
    annual_accessions_from_facts left all 2,990 tests green, because every
    fixture that reached it held 10-K entries only and the one assertion
    about it compares the function against ITSELF.

    The filter is load-bearing, not cosmetic. fetch_sic_history_for_tickers
    turns these accessions into the point-in-time SIC step series, and
    get_annual_accessions' own docstring is that the series is "keyed to the
    same filing events as the factor" — the factor being 10-K-only. Letting
    10-Q accessions in would add industry-change events on dates no annual
    line item ever came from, in exactly the family whose whole design
    exists to avoid projecting today's industry onto the past."""
    mixed = facts(
        {
            "Assets": [
                instant("2023-12-31", 1.0, "2024-02-01", form="10-K"),
                instant("2024-03-31", 2.0, "2024-05-01", form="10-Q"),
                instant("2024-12-31", 3.0, "2025-02-01", form="10-K/A"),
                instant("2025-06-30", 4.0, "2025-08-01", form="8-K"),
            ]
        }
    )
    usd = mixed["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    for i, entry in enumerate(usd):
        entry["accn"] = accn(999, i)

    accessions = annual_accessions_from_facts(mixed)

    assert set(accessions) == {accn(999, 0), accn(999, 2)}, (
        "only the 10-K and 10-K/A accessions may become SIC-history filing events"
    )


def test_a_document_with_no_entity_name_refuses_every_candidate():
    """MUTATION SURVIVOR: deleting the `not normalized or` guard left the
    whole suite green, yet it turns gate (2) vacuous exactly when it is
    needed most — a resolved document carrying no entityName would then
    accept any candidate that also carries none, on the accession prefix
    alone. That prefix is worth nothing by itself: 150 of the 162 production
    companyfacts documents contain facts filed under some other CIK.

    Refusal is the safe direction (a refused ticker is reported and
    excluded), so an unnameable document must refuse, not match."""
    nameless = shell_facts()
    del nameless["entityName"]
    candidate = predecessor_facts()
    del candidate["entityName"]
    provider = mock_provider(
        companyfacts_handler({XOM_SHELL_CIK: nameless, XOM_REAL_CIK: candidate})
    )

    filing_cik, _ = provider.resolve_company_facts(XOM_SHELL_CIK)

    assert filing_cik == XOM_SHELL_CIK, "an unnameable document cannot be name-matched"
    assert provider.cik_resolution.redirects == {}
    assert XOM_SHELL_CIK in provider.cik_resolution.without_annual_history


def test_a_documents_own_cik_is_never_probed_as_its_own_predecessor():
    """MUTATION SURVIVOR: removing the `candidate != cik` filter left the
    suite green, because in the real XOM shape not one of the shell's 274
    facts carries the shell's OWN accession prefix — the predecessor filed
    them all. That will not hold for the next such shell: a successor that
    has begun filing under its own accession numbers is its own MAJORITY
    prefix, so it would take probe slot 1 (a wasted request that can only
    ever fail gate (1), since it is the very document already known to have
    no annual facts) and push the genuine predecessor past the cap.

    Here the shell filed the bulk itself and the real predecessor is only
    the fourth-ranked prefix, so the self-probe is the difference between
    recovering XOM and losing it."""
    shell = shell_facts()
    usd = shell["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    for entry in usd:  # the shell now filed its own 10-Q facts
        entry["accn"] = accn(XOM_SHELL_CIK, 1)
    for i, agent in enumerate((7001, 7002)):
        for _ in range(2):  # each agent outranks the single predecessor fact
            usd.append(
                {
                    "end": f"2026-0{i + 1}-28",
                    "val": 1.0,
                    "filed": "2026-08-03",
                    "form": "10-Q",
                    "accn": accn(agent, i),
                }
            )
    usd.append(
        {
            "end": "2026-06-30",
            "val": 1.0,
            "filed": "2026-08-03",
            "form": "10-Q",
            "accn": accn(XOM_REAL_CIK, 93),
        }
    )
    calls: list[str] = []
    provider = mock_provider(
        companyfacts_handler({XOM_SHELL_CIK: shell, XOM_REAL_CIK: predecessor_facts()}, calls)
    )

    filing_cik, _ = provider.resolve_company_facts(XOM_SHELL_CIK)

    assert filing_cik == XOM_REAL_CIK, "the self-prefix must not consume a probe slot"
    assert not any(
        f"CIK{XOM_SHELL_CIK:010d}" in url for url in calls[1:]
    ), f"the shell was re-fetched as its own candidate: {calls}"


def test_an_accession_shaped_prefix_is_not_enough_to_become_a_candidate():
    """MUTATION SURVIVOR: loosening _ACCESSION_RE to match a bare leading
    10 digits left the suite green, because the only malformed fixture in
    it ("not-an-accession") fails any regex at all. A real accession is
    "0000034088-26-000093" — CIK, 2-digit year, 6-digit sequence — and a
    string that merely STARTS with ten digits is not one. Parsing one
    anyway invents a candidate CIK out of a malformed field and spends a
    capped probe slot on it."""
    doc = facts({"Assets": [instant("2023-12-31", 1.0, "2024-02-01")]})
    entries = doc["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    template = entries[0]
    entries.clear()
    for bad in (
        "00000340882600093",  # no separators
        "0000034088-26-00093",  # 5-digit sequence
        "0000034088-2026-000093",  # 4-digit year
        "0000034088-26-000093-01",  # trailing co-registrant suffix
        "000034088-26-000093",  # 9-digit CIK
    ):
        entries.append({**template, "accn": bad})

    assert filer_cik_counts(doc) == {}, "only a well-formed accession may name a filer"


def test_the_third_candidate_is_still_reachable_under_the_cap():
    """MUTATION SURVIVOR: lowering MAX_PREDECESSOR_CANDIDATES from 3 to 2
    left the suite green. 3 is not arbitrary — it is the measured shape of
    the OTHER zero-annual-facts document in the production population: Sea
    Limited's facts carry exactly three foreign filer prefixes (1140361,
    1193125 and 1144204, all filing agents). A cap below 3 would stop
    short of the last of them, so a predecessor ranked third by fact count
    would be silently unreachable. This pins that the cap is at least 3."""
    shell = shell_facts()
    usd = shell["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    usd.clear()
    # Three foreign filers, the real predecessor LAST by fact count.
    for agent, n in ((7001, 3), (7002, 2)):
        for i in range(n):
            usd.append(
                {
                    "end": "2026-06-30",
                    "val": 1.0,
                    "filed": "2026-08-03",
                    "form": "10-Q",
                    "accn": accn(agent, i),
                }
            )
    usd.append(
        {
            "end": "2026-06-30",
            "val": 1.0,
            "filed": "2026-08-03",
            "form": "10-Q",
            "accn": accn(XOM_REAL_CIK, 93),
        }
    )
    assert [c for c, _ in filer_cik_counts(shell).most_common()][2] == XOM_REAL_CIK

    provider = mock_provider(
        companyfacts_handler({XOM_SHELL_CIK: shell, XOM_REAL_CIK: predecessor_facts()})
    )

    filing_cik, _ = provider.resolve_company_facts(XOM_SHELL_CIK)

    assert filing_cik == XOM_REAL_CIK, (
        "a third-ranked predecessor must still be reachable — Sea Limited's measured "
        "shape has exactly three foreign filer prefixes"
    )
