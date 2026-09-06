"""Tests for the IPO share-lockup expiration family.

The mechanism-fidelity checks F1-F5 named in
data/research_runs/ipo_lockup_expiration_PREREGISTRATION.txt section 11 live
here; F6-F10 are reporting requirements and are checked in the runner's output
rather than as assertions.

The two most important tests in this file are:

  test_equation_1_is_compounded_not_additive   — the formula-from-memory guard.
      Field & Hanka Eq. (1) p.477 is a PRODUCT of gross-return ratios. An
      additive SUM(R_i - R_m) is a different statistic and this pins the
      difference against a value worked out by hand in the test body.

  test_cnob_2013_is_rejected_despite_a_sec_name_match — the regression pin on
      the real, independently verified ticker-recycling case that motivated the
      whole identity protocol. SEC's own ticker map name-matches this row and is
      wrong; only the first-trade anchor catches it.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab import ipo_lockup_expiration as ipo
from app.services.research_lab.ipo_lockup_expiration import (
    BASELINE_COST_ARM,
    CIK_NAME_MATCH,
    COST_ARMS_BY_KEY,
    EVENT_WINDOWS,
    IPO_LOCKUP_N_TRIALS,
    LOCKUP_CALENDAR_DAYS,
    PLACEBO_CALENDAR_DAYS,
    VC_FLAG_GROWTH_CAPITAL,
    VC_FLAG_VENTURE,
    IpoRow,
    abnormal_volume,
    build_event_panel,
    build_family,
    classify_cik_status,
    classify_ticker_info,
    compound_abnormal_return,
    filter_universe,
    first_trade_anchor_ok,
    load_ritter_universe,
    load_sec_ticker_map,
    name_similarity,
    normalise_company_name,
    policy_d_denominators,
)

DATA_PRESENT = ipo.RITTER_IPO_AGE_PATH.exists() and ipo.SEC_COMPANY_TICKERS_PATH.exists()
needs_data = pytest.mark.skipif(
    not DATA_PRESENT,
    reason="data/ipo_lockup/ not populated — run data/research_runs/fetch_ipo_lockup_data.py",
)


# --- F1: Equation (1) --------------------------------------------------------


def test_equation_1_is_compounded_not_additive():
    """[FH01] Eq. (1), p.477. Hand-computed, in full, in this test body.

    stock  = [0.01, -0.02, 0.005]
    market = [0.002, -0.001, 0.003]

    The product of ratios is the ratio of products, which is what makes this
    checkable by hand without any floating-point library:

      numerator   = 1.01 * 0.98 * 1.005
                  = 0.9898 * 1.005
                  = 0.9947490
      denominator = 1.002 * 0.999 * 1.003
                  = 1.000998 * 1.003
                  = 1.004000994
      ratio       = 0.9947490 / 1.004000994
                  = 0.99078487565720477...
      CAR         = ratio - 1
                  = -0.00921512434279522...

    (Re-derived to 40 significant digits with Python's `decimal` module in a
    separate process, independent of numpy's float64 path, before this value
    was written down. An earlier draft of this test carried a WRONG hand value
    of -0.009068 — a slip in the running product, not a code bug — which this
    check caught. That is the entire point of pinning a hand-derived number.)

    The ADDITIVE approximation SUM(R_i - R_m) is
      0.008 + (-0.019) + 0.002 = -0.009 exactly,
    which differs in the fourth decimal place. Both are small; only one is the
    paper's statistic.
    """
    stock = np.array([0.01, -0.02, 0.005])
    market = np.array([0.002, -0.001, 0.003])

    car = compound_abnormal_return(stock, market)
    expected = float(np.prod((1 + stock) / (1 + market)) - 1.0)
    assert car == pytest.approx(expected, abs=1e-15)
    assert car == pytest.approx(-0.00921512434279522, abs=1e-15)

    additive = float(np.sum(stock - market))
    assert additive == pytest.approx(-0.009, abs=1e-15)
    assert abs(car - additive) > 2e-4


def test_equation_1_raw_arm_uses_no_market_leg():
    """[FH01] p.477: "We also examined raw returns"."""
    stock = np.array([0.01, -0.02, 0.005])
    assert compound_abnormal_return(stock, None) == pytest.approx(
        float(np.prod(1 + stock) - 1.0), abs=1e-15
    )


def test_equation_1_refuses_degenerate_and_mismatched_input():
    assert compound_abnormal_return(np.array([]), None) is None
    assert compound_abnormal_return(np.array([0.1, np.nan]), None) is None
    assert compound_abnormal_return(np.array([-1.0]), None) is None  # 1 + R == 0
    assert compound_abnormal_return(np.array([0.1]), np.array([-1.0])) is None
    assert compound_abnormal_return(np.array([0.1, 0.2]), np.array([0.1])) is None


# --- Equation (2) ------------------------------------------------------------


def test_equation_2_abnormal_volume():
    """[FH01] Eq. (2), p.478. Baseline mean 100, observed mean 180 -> +80%,
    which is also the figure the paper reports for day +1 (Figure 3, p.480)."""
    baseline = np.full(45, 100.0)
    assert abnormal_volume(np.array([180.0]), baseline) == pytest.approx(0.80)
    assert abnormal_volume(np.array([120.0, 180.0, 132.0]), baseline) == pytest.approx(0.44)
    assert abnormal_volume(np.array([100.0]), np.zeros(45)) is None
    assert abnormal_volume(np.array([]), baseline) is None


def test_equation_2_normalisation_window_is_45_days():
    """-50..-6 inclusive is 45 trading days, which is Eq. (2)'s 1/45."""
    assert ipo.VOLUME_NORM_LAST_DAY - ipo.VOLUME_NORM_FIRST_DAY + 1 == 45


# --- F2/F3: the unlock-day calendar ------------------------------------------


def test_180_days_maps_monday_tuesday_wednesday_offers_onto_monday():
    """[FH01] Sec III.C p.488: "because of the weekend, unlock days tend to fall
    on Monday". 180 = 25*7 + 5, so an offer on Monday/Tuesday/Wednesday lands on
    Saturday/Sunday/Monday and therefore on Monday once mapped to the next
    session — three of the five weekday cases."""
    assert LOCKUP_CALENDAR_DAYS % 7 == 5
    landing = {}
    for weekday in range(5):
        # 2013-01-07 is a Monday.
        offer = date(2013, 1, 7) + timedelta(days=weekday)
        assert offer.weekday() == weekday
        landing[weekday] = (offer + timedelta(days=LOCKUP_CALENDAR_DAYS)).weekday()
    # Monday->Saturday(5), Tuesday->Sunday(6), Wednesday->Monday(0),
    # Thursday->Tuesday(1), Friday->Wednesday(2).
    assert landing == {0: 5, 1: 6, 2: 0, 3: 1, 4: 2}


def test_predicted_unlock_weekday_is_the_exact_deterministic_mapping():
    """F2, IN ITS STRICTER FORM.

    The pre-registration (section 11) predicted Monday would be the MODAL
    unlock weekday and said a failure would make the construction suspect. The
    prediction was NOT met on real data — Tuesday is modal — and the cause was
    investigated rather than waived: it has an unstated premise, a roughly
    uniform distribution of OFFER weekdays, which is false. In 2012-2019, 40.5%
    of filtered universe rows have a THURSDAY offer date (US IPOs price the
    evening before and open Thursday or Friday), and Thursday + 180 days is a
    Tuesday that is already a full trading day, so no weekend forwarding
    happens for the largest cohort.

    [FH01]'s MECHANISM is intact and is what this pins: Monday, Tuesday and
    Wednesday offers all land on Saturday, Sunday and Monday respectively and
    therefore unlock on a Monday, which is exactly Sec III.C p.488's "because of
    the weekend, unlock days tend to fall on Monday". The run report carries the
    measured predicted-vs-observed distribution for both event types."""
    assert LOCKUP_CALENDAR_DAYS % 7 == 5
    assert PLACEBO_CALENDAR_DAYS % 7 == 2
    #                                     Mon Tue Wed Thu Fri Sat Sun
    assert [ipo.predicted_unlock_weekday(w, LOCKUP_CALENDAR_DAYS) for w in range(7)] == [
        0,  # Mon -> Sat -> Mon
        0,  # Tue -> Sun -> Mon
        0,  # Wed -> Mon
        1,  # Thu -> Tue   <-- the 40.5% cohort, and why Tuesday is modal
        2,  # Fri -> Wed
        3,  # Sat -> Thu
        4,  # Sun -> Fri
    ]
    assert [ipo.predicted_unlock_weekday(w, PLACEBO_CALENDAR_DAYS) for w in range(7)] == [
        2, 3, 4, 0, 0, 0, 1
    ]


def test_first_trading_day_on_or_after_target(synthetic_panel_inputs):
    """F3. The mapping used by build_event_panel is "the first index date >=
    offer + N calendar days"; pinned end to end through a real panel build."""
    panel = _build_panel(synthetic_panel_inputs)
    lockups = panel.for_event_type("lockup")
    assert lockups, "synthetic fixture should produce a lockup event"
    event = lockups[0]
    target = event.offer_date + timedelta(days=LOCKUP_CALENDAR_DAYS)
    assert event.unlock_date >= target
    calendar = synthetic_panel_inputs["close_index"]
    earlier = [d.date() for d in calendar if target <= d.date() < event.unlock_date]
    assert earlier == [], f"an earlier trading day existed: {earlier}"


def test_placebo_window_cannot_overlap_the_lockup_window():
    """Pre-registration section 8: 240 - 180 = 60 calendar days, far wider than
    the -5..+1 window, so the control arm cannot see the treated event."""
    widest = max(last - first for first, last in EVENT_WINDOWS.values())
    assert PLACEBO_CALENDAR_DAYS - LOCKUP_CALENDAR_DAYS > widest + 2


# --- F4: identity ------------------------------------------------------------


def test_first_trade_anchor_boundaries():
    offer = date(2013, 2, 11)
    assert first_trade_anchor_ok(offer, offer) is True
    assert first_trade_anchor_ok(offer + timedelta(days=1), offer) is True
    assert first_trade_anchor_ok(offer + timedelta(days=7), offer) is True
    assert first_trade_anchor_ok(offer + timedelta(days=8), offer) is False
    assert first_trade_anchor_ok(offer - timedelta(days=1), offer) is False
    assert first_trade_anchor_ok(offer - timedelta(days=224), offer) is False


def test_synthetic_pre_ipo_history_is_rejected(synthetic_panel_inputs):
    """F4(a). A row whose price series begins before its own offer date is
    rejected by G2, and the rejection is COUNTED, not silent."""
    inputs = dict(synthetic_panel_inputs)
    row = inputs["universe"][0]
    inputs["universe"] = [
        IpoRow(
            offer_date=row.offer_date + timedelta(days=200),  # series now predates the offer
            name=row.name,
            ticker=row.ticker,
            cusip=row.cusip,
            adr_flag=row.adr_flag,
            vc_flag=row.vc_flag,
            dual_flag=row.dual_flag,
            internet_flag=row.internet_flag,
            crsp_permno=row.crsp_permno,
            founding_year=row.founding_year,
        )
    ]
    panel = _build_panel(inputs)
    assert panel.events == []
    assert panel.identity.g2_rejected_recycled == 1


def test_normalise_and_similarity():
    assert normalise_company_name("ConnectOne Bancorp, Inc.") == "CONNECTONE BANCORP"
    assert normalise_company_name("The Container Store Group Inc") == "CONTAINER STORE"
    # Ritter truncates to ~30 characters; a prefix must still match.
    assert name_similarity("Greenway Medical Tech Inc", "Greenway Medical Technologies, Inc.") == 1.0
    assert name_similarity("Pandora Media Inc", "Everpure, Inc.") < ipo.NAME_SIMILARITY_FLOOR


def test_g3_keeps_rows_whose_info_is_unavailable():
    """A case the pre-registration did not specify, resolved in the module and
    asserted here: rejecting on a missing metadata call would delete exactly the
    delisted names whose retention LIMITS the survivorship bias."""
    row = IpoRow(date(2013, 1, 1), "Some Co", "SMC", None, 1, 1, 0, 0, None, 2005)
    assert classify_ticker_info(row, None) == ipo.G3_INFO_UNAVAILABLE
    assert classify_ticker_info(row, {"error": "boom"}) == ipo.G3_INFO_UNAVAILABLE
    assert classify_ticker_info(row, {"quoteType": "ETF", "longName": "Some Co"}) == ipo.G3_REJECT_QUOTE_TYPE
    assert classify_ticker_info(row, {"quoteType": "EQUITY", "longName": "Totally Other"}) == ipo.G3_REJECT_NAME
    assert classify_ticker_info(row, {"quoteType": "EQUITY", "longName": "Some Co Inc"}) == ipo.G3_OK


@needs_data
def test_cnob_2013_is_rejected_despite_a_sec_name_match():
    """F4(b) — THE REGRESSION PIN.

    Verified independently 2026-09-06: Center Bancorp (Nasdaq: CNBC, CIK
    712771, filing since the 1980s) survived its 2014-07-01 merger with
    ConnectOne Bancorp (CIK 1462694, IPO 2013-02-11), renamed itself ConnectOne
    Bancorp and kept the CNOB symbol. So today's CNOB price series is Center
    Bancorp's, and SEC's own current ticker map name-matches a Ritter row it
    does not describe.

    This test asserts BOTH halves of that: the CIK/name check passes, and the
    first-trade anchor still rejects."""
    rows = load_ritter_universe()
    universe, _counts = filter_universe(rows)
    cnob = [r for r in universe if r.ticker == "CNOB"]
    assert len(cnob) == 1, "the 2013 ConnectOne row should survive the universe filter"
    row = cnob[0]
    assert row.offer_date == date(2013, 2, 11)

    sec_map = load_sec_ticker_map()
    status, cik, title = classify_cik_status(row, sec_map)
    assert status == CIK_NAME_MATCH, "the point of this test is that the CIK/name check ACCEPTS it"
    assert cik == 712771, "SEC maps CNOB to Center Bancorp's registrant, not the 2013 IPO entity"
    assert title.startswith("ConnectOne")

    store_path = ipo.PRICE_STORE_DIR / "CNOB.csv.gz"
    if not store_path.exists():
        pytest.skip("price store not populated for CNOB")
    stored = pd.read_csv(store_path, index_col=0, parse_dates=True, compression="gzip")
    first_observation = stored.dropna(subset=["close"]).index[0].date()
    assert first_observation < row.offer_date, "the stored series should predate the IPO"
    assert first_trade_anchor_ok(first_observation, row.offer_date) is False


# --- F5: the cost model cannot see the event ---------------------------------


def test_half_spread_is_read_as_of_day_minus_six_and_ignores_later_data(synthetic_panel_inputs):
    """F5. Replacing every OHLC row after day -6 with garbage must leave the
    charged half-spread bit-identical."""
    panel_before = _build_panel(synthetic_panel_inputs)
    event_before = panel_before.for_event_type("lockup")[0]

    mutated = dict(synthetic_panel_inputs)
    spreads = {t: s.copy() for t, s in synthetic_panel_inputs["half_spread"].items()}
    ticker = event_before.ticker
    index = spreads[ticker].index
    unlock_position = int(index.get_loc(pd.Timestamp(event_before.unlock_date)))
    spreads[ticker].iloc[unlock_position + ipo.COST_AS_OF_DAY + 1 :] = 999.0
    mutated["half_spread"] = spreads

    panel_after = _build_panel(mutated)
    event_after = panel_after.for_event_type("lockup")[0]
    assert event_after.half_spread == event_before.half_spread


# --- the grid, the ladder, the cost arms -------------------------------------


def test_grid_is_the_pre_registered_twenty_four():
    specs = build_family()
    assert len(specs) == IPO_LOCKUP_N_TRIALS == 24
    assert len({s.spec_id for s in specs}) == 24
    assert sum(1 for s in specs if s.is_control) == 12
    assert {s.event_type for s in specs} == {"lockup", "placebo"}
    assert {s.window for s in specs} == set(EVENT_WINDOWS)
    assert {s.benchmark for s in specs} == {"spy", "raw"}
    assert {s.cross_section for s in specs} == {"all", "vc", "nonvc"}


def test_policy_d_ladder_matches_the_committed_artifact():
    assert policy_d_denominators() == [24, 481, 857]


def test_cost_arms_are_bounded_on_both_sides():
    free = COST_ARMS_BY_KEY["cost_free"]
    cheap = COST_ARMS_BY_KEY["cheap"]
    baseline = COST_ARMS_BY_KEY[BASELINE_COST_ARM]
    assert free.stock_half_spread_bps == 0.0 and free.borrow_bps_per_year == 0.0
    assert cheap.stock_half_spread_bps == 2.5  # one $0.01 tick on a $20 stock, one way
    assert cheap.borrow_bps_per_year == 34.0  # general collateral
    assert baseline.stock_half_spread_bps is None  # per-name EDGE
    assert baseline.borrow_bps_per_year == 430.0  # hard to borrow


# --- the universe ------------------------------------------------------------


@needs_data
def test_universe_filter_matches_the_pre_registered_counts():
    """Pre-registration section 5.2 states these counts in advance. If the
    committed Ritter file is ever refreshed this test is the thing that says the
    universe moved."""
    rows = load_ritter_universe()
    universe, counts = filter_universe(rows)
    assert counts.total_rows == 16030
    assert counts.in_window == 1704
    assert counts.ticker_present == 1704
    assert counts.ordinary_common == 1488
    assert counts.not_unit_offer == 1310
    assert counts.not_spac_name == 1289
    assert counts.operating_history == 1205
    assert len(universe) == 1205
    assert counts.vc_backed == 566
    assert counts.not_vc_backed == 561
    assert counts.growth_capital == 78


@needs_data
def test_growth_capital_rows_are_in_all_but_in_neither_vc_arm():
    """Ritter's VC column codes 2 as GROWTH-CAPITAL-backed, established against
    his own Table 4c (pre-registration 5.1). Those 78 rows belong to `all` and
    to neither cross-sectional arm, so they cannot be moved between arms after
    a result is seen."""
    rows = load_ritter_universe()
    universe, _counts = filter_universe(rows)
    growth = [r for r in universe if r.vc_flag == VC_FLAG_GROWTH_CAPITAL]
    assert len(growth) == 78
    assert all(not r.is_venture_backed and not r.is_not_venture_backed for r in growth)

    specs = {s.cross_section: s for s in build_family() if s.event_type == "lockup"}
    fake = ipo.IpoLockupEvent(
        ticker="X", name="X", offer_date=date(2013, 1, 1), event_type="lockup",
        vc_flag=VC_FLAG_GROWTH_CAPITAL, unlock_date=date(2013, 7, 1), window_dates={},
        window_stock_returns={}, window_market_returns={}, half_spread=0.0,
        half_spread_is_fallback=False, as_traded_close_day_m6=10.0, abnormal_volume_3day=None,
        abnormal_volume_day_p1=None, unlock_weekday=0, cik_status=CIK_NAME_MATCH, g3_status=ipo.G3_OK,
    )
    assert ipo.event_matches(fake, specs["all"]) is True
    assert ipo.event_matches(fake, specs["vc"]) is False
    assert ipo.event_matches(fake, specs["nonvc"]) is False


# --- the verdict rule --------------------------------------------------------


def _summary(local_dsr: float, conservative_dsr: float, placebo_dsr: float | None) -> ipo.IpoLockupSummary:
    def result(spec: ipo.IpoLockupSpec, dsr_local: float, dsr_cons: float) -> ipo.IpoLockupScreeningResult:
        return ipo.IpoLockupScreeningResult(
            spec_id=spec.spec_id, event_type=spec.event_type, window=spec.window,
            benchmark=spec.benchmark, cross_section=spec.cross_section, citation="",
            hypothesis="", is_control=spec.is_control, cost_arm=BASELINE_COST_ARM,
            n_trading_days=1000, n_events=100, first_date=None, last_date=None,
            sharpe_annualized=1.0, dsr_by_n={24: dsr_local, 481: dsr_cons, 857: dsr_cons},
            preservation={}, streams={}, active_day_fraction=0.5, fallback_fraction=0.0,
            total_cost_drag=0.0, bootstrap_p_value=None, deflated_sharpe=None,
            diagnostics=None,  # type: ignore[arg-type]
        )

    specs = build_family()
    treated = next(s for s in specs if not s.is_control)
    control = next(s for s in specs if s.is_control)
    results = [result(treated, local_dsr, conservative_dsr)]
    if placebo_dsr is not None:
        results.append(result(control, placebo_dsr, placebo_dsr))
    return ipo.IpoLockupSummary(
        panel=None,  # type: ignore[arg-type]
        specs=specs,
        denominators=[24, 481, 857],
        n_local=24,
        results_by_cost_arm={BASELINE_COST_ARM: results},
    )


def test_verdict_definite_negative_below_the_lenient_bar():
    verdict, spec_id, reason = _summary(0.40, 0.10, None).verdict()
    assert verdict == "DEFINITE_NEGATIVE"
    assert spec_id is not None and "0.4000" in reason


def test_verdict_unresolved_between_the_two_bars():
    verdict, _spec_id, reason = _summary(0.99, 0.10, None).verdict()
    assert verdict == "UNRESOLVED"
    assert "857" in reason


def test_verdict_pass_at_the_most_conservative_n():
    verdict, _spec_id, _reason = _summary(0.99, 0.99, None).verdict()
    assert verdict == "PASS"


def test_placebo_override_turns_a_pass_into_a_negative():
    """Pre-registration section 12(i), binding: if the day-240 control clears
    the same bar, the effect is not attributable to lockup expiration."""
    verdict, _spec_id, reason = _summary(0.99, 0.99, 0.98).verdict()
    assert verdict == "DEFINITE_NEGATIVE"
    assert "PLACEBO OVERRIDE" in reason


def test_placebo_that_fails_does_not_override():
    verdict, _spec_id, _reason = _summary(0.99, 0.99, 0.20).verdict()
    assert verdict == "PASS"


# --- streams -----------------------------------------------------------------


def test_event_stream_periods_per_year_is_measured_not_assumed():
    index = pd.DatetimeIndex(pd.date_range("2013-01-01", "2016-12-31", periods=240))
    series = pd.Series(np.zeros(240), index=index)
    ppy = ipo.event_stream_periods_per_year(series)
    assert ppy == pytest.approx(240 / 4.0, rel=0.02)


def test_degenerate_stream_reports_zero_sharpe_not_dust():
    flat = pd.Series(np.zeros(500))
    assert ipo._annualised_sharpe(flat, 252) == 0.0


# --- the synthetic panel fixture ---------------------------------------------


@pytest.fixture
def synthetic_panel_inputs():
    """One well-formed ticker with a clean IPO-anchored series, enough history
    for Equation (2)'s -50 day and both event windows, and a benchmark."""
    offer = date(2013, 3, 1)
    index = pd.bdate_range(start=offer, periods=400)
    rng = np.random.default_rng(20260906)
    close = pd.Series(20.0 * np.cumprod(1 + rng.normal(0, 0.01, len(index))), index=index)
    volume = pd.Series(1_000_000.0, index=index)
    bench = pd.Series(200.0 * np.cumprod(1 + rng.normal(0, 0.005, len(index))), index=index)
    row = IpoRow(
        offer_date=offer, name="Synthetic Widgets Inc", ticker="SYNW", cusip=None, adr_flag=1,
        vc_flag=VC_FLAG_VENTURE, dual_flag=0, internet_flag=0, crsp_permno=None, founding_year=2001,
    )
    return {
        "universe": [row],
        "close_index": index,
        "adjusted": {
            "SYNW": {
                "open": close, "high": close * 1.01, "low": close * 0.99,
                "close": close, "volume": volume,
            }
        },
        "as_traded": {"SYNW": close},
        "half_spread": {"SYNW": pd.Series(0.0015, index=index)},
        "benchmark": bench,
    }


def _build_panel(inputs: dict) -> ipo.IpoLockupPanel:
    return build_event_panel(
        inputs["universe"],
        adjusted_by_ticker=inputs["adjusted"],
        as_traded_close_by_ticker=inputs["as_traded"],
        half_spread_by_ticker=inputs["half_spread"],
        benchmark_close=inputs["benchmark"],
        sec_map={},
        ticker_info={},
        universe_counts=ipo.UniverseFilterCounts(),
        fallback_half_spread=ipo.CHEAP_HALF_SPREAD_BPS / 1e4,
    )


def test_synthetic_panel_produces_both_event_types(synthetic_panel_inputs):
    panel = _build_panel(synthetic_panel_inputs)
    assert {e.event_type for e in panel.events} == {"lockup", "placebo"}
    for event in panel.events:
        assert set(event.window_dates) == set(EVENT_WINDOWS)
        assert len(event.window_dates["w_m1_p1"]) == 3
        assert len(event.window_dates["w_m5_p1"]) == 7
        assert event.as_traded_close_day_m6 >= ipo.MIN_PRICE_DOLLARS
        assert event.abnormal_volume_3day == pytest.approx(0.0)  # flat synthetic volume


def test_penny_stock_filter_uses_the_as_traded_price(synthetic_panel_inputs):
    """D5: as-traded, not adjusted. A series whose ADJUSTED level is far above
    $5 but whose AS-TRADED price is below it must be rejected — which is the
    Beyond Meat reverse-split case the feasibility run documented."""
    inputs = dict(synthetic_panel_inputs)
    inputs["as_traded"] = {"SYNW": inputs["as_traded"]["SYNW"] * 0.1}  # ~$2/share as traded
    panel = _build_panel(inputs)
    assert panel.events == []
    assert panel.identity.penny_rejected == len(ipo.EVENT_TYPE_DAYS)


def test_backtest_costs_scale_with_the_cost_arm(synthetic_panel_inputs):
    panel = _build_panel(synthetic_panel_inputs)
    spec = next(s for s in build_family() if s.spec_id == "lockup|w_m1_p1|spy|all")
    # MIN_EVENTS_PER_SPEC would reject a one-event panel, so exercise the trade
    # arithmetic directly rather than through the screen.
    event = panel.for_event_type("lockup")[0]
    free_entry, free_exit, free_borrow = ipo._event_cost(event, spec, COST_ARMS_BY_KEY["cost_free"], 3)
    assert (free_entry, free_exit, free_borrow) == (0.0, 0.0, 0.0)
    cheap_entry, _cheap_exit, cheap_borrow = ipo._event_cost(event, spec, COST_ARMS_BY_KEY["cheap"], 3)
    assert cheap_entry == pytest.approx((2.5 + 2.0) / 1e4)
    assert cheap_borrow == pytest.approx((34.0 / 1e4) * (3 / 252))
    base_entry, _base_exit, base_borrow = ipo._event_cost(event, spec, COST_ARMS_BY_KEY["baseline"], 3)
    assert base_entry == pytest.approx(0.0015 + 2.0 / 1e4)  # the fixture's own EDGE half-spread
    assert base_borrow == pytest.approx((430.0 / 1e4) * (3 / 252))


def test_raw_arm_charges_no_hedge_leg(synthetic_panel_inputs):
    panel = _build_panel(synthetic_panel_inputs)
    event = panel.for_event_type("lockup")[0]
    raw_spec = next(s for s in build_family() if s.spec_id == "lockup|w_m1_p1|raw|all")
    entry, _exit, _borrow = ipo._event_cost(event, raw_spec, COST_ARMS_BY_KEY["cheap"], 3)
    assert entry == pytest.approx(2.5 / 1e4)
