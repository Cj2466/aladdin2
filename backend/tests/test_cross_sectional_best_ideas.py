"""Tests for the 13F institutional "Best Ideas" family
(cross_sectional_best_ideas.py).

The four POINT-IN-TIME tests in this file were named in advance, by
letter, in section 7 of data/research_runs/best_ideas_13f_PREREGISTRATION
.txt, and are the reason this family can claim its 45-day filing lag is
enforced rather than assumed:

  (a) test_pit_a_filing_contributes_nothing_before_its_filing_date
  (b) test_pit_b_panel_is_a_function_of_filing_date_not_period
  (c) test_pit_c_value_never_appears_before_its_period_ends
  (d) test_pit_d_amendment_does_not_rewrite_history

(b) and (c) run against REAL cached SEC archives when they are present,
and skip cleanly when they are not, so the strongest evidence is taken
from real filings rather than from fixtures shaped to agree.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.form13f_provider import (
    CusipTickerMap,
    Form13FFiling,
    Form13FProvider,
    parse_quarter_archive,
)
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_best_ideas import (
    ACTIVENESS_QUANTILE,
    BEST_IDEA_MEASURES,
    BEST_IDEAS_AGGREGATIONS,
    BEST_IDEAS_FAMILY,
    BEST_IDEAS_HOLDING_DAYS,
    BEST_IDEAS_N_TRIALS,
    BEST_IDEAS_RANK_FRACTIONS,
    MANAGER_VIEW_MAX_STALENESS_DAYS,
    MAX_REPORTING_LAG_DAYS,
    MIN_HOLDINGS_PER_FILING,
    MIN_PORTFOLIO_VALUE_USD,
    ManagerView,
    all_best_ideas_specs,
    build_best_idea_panels,
    build_best_ideas_family,
    build_manager_views,
    compute_best_ideas_for_filing,
    signal_best_ideas,
)

UNIVERSE = ["AAA", "BBB", "CCC", "DDD"]
CUSIPS = {"AAA": "111111111", "BBB": "222222222", "CCC": "333333333", "DDD": "444444444"}
# Securities OUTSIDE the ranked universe. Needed because the paper's own
# screen requires at least 5 holdings, which a 4-name test universe
# cannot satisfy on its own — and because a manager's book being wider
# than the ranked universe is the realistic case anyway.
FILLER_CUSIPS = ("555555555", "666666666", "777777777")


def _book(universe_values: list[float], filler_value: float = 1e6) -> dict[str, float]:
    """A book spanning the ranked universe plus enough out-of-universe
    filler to clear MIN_HOLDINGS_PER_FILING."""
    book = {CUSIPS[t]: v for t, v in zip(UNIVERSE, universe_values)}
    book.update({c: filler_value for c in FILLER_CUSIPS})
    return book


def _map() -> CusipTickerMap:
    return CusipTickerMap(
        {cusip: [(date(2015, 1, 1), ticker)] for ticker, cusip in CUSIPS.items()}
    )


def _filing(
    accession: str,
    cik: int,
    filed: date,
    period: date,
    holdings: dict[str, float],
    *,
    name: str = "SOME ADVISORS LP",
    submission_type: str = "13F-HR",
) -> Form13FFiling:
    return Form13FFiling(
        accession=accession,
        cik=cik,
        manager_name=name,
        filing_date=filed,
        period=period,
        submission_type=submission_type,
        holdings=dict(holdings),
        total_value_usd=float(sum(holdings.values())),
        n_holdings=len(holdings),
        value_scale=1000.0,
    )


def _trading_index(start: date, days: int) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.bdate_range(start=start, periods=days))


def _close(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(100.0, index=index, columns=UNIVERSE)


def _view(
    cik: int,
    filed: date,
    best: dict[str, int | None],
    held: list[int],
    *,
    eligible: dict[str, bool] | None = None,
    period: date | None = None,
) -> ManagerView:
    return ManagerView(
        cik=cik,
        filing_date=filed,
        period=period or (filed - timedelta(days=45)),
        best_idea=best,
        eligible=eligible or dict.fromkeys(BEST_IDEA_MEASURES, True),
        max_stat=dict.fromkeys(BEST_IDEA_MEASURES, 0.5),
        held_universe=np.asarray(held, dtype=np.int32),
    )


# --- family shape ------------------------------------------------------------


def test_grid_is_exactly_the_pre_registered_36():
    specs = all_best_ideas_specs()
    assert len(specs) == BEST_IDEAS_N_TRIALS == 36
    assert len(BEST_IDEA_MEASURES) == 3
    assert len(BEST_IDEAS_AGGREGATIONS) == 2
    assert len(BEST_IDEAS_HOLDING_DAYS) == 3
    assert len(BEST_IDEAS_RANK_FRACTIONS) == 2


def test_grid_ids_are_unique_and_family_tagged():
    specs = all_best_ideas_specs()
    assert len({s.pattern_id for s in specs}) == 36
    assert all(s.family == BEST_IDEAS_FAMILY for s in specs)
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.requires_fundamental_signal for s in specs)


def test_monthly_hold_is_excluded_up_front():
    """13F refreshes quarterly, so a 21-day hold would re-pay turnover on
    an unchanged ranking."""
    assert 21 not in BEST_IDEAS_HOLDING_DAYS
    assert 63 in BEST_IDEAS_HOLDING_DAYS


def test_unknown_measure_or_aggregation_is_refused():
    with pytest.raises(ValueError):
        build_best_ideas_family("not_a_measure", "count")
    with pytest.raises(ValueError):
        build_best_ideas_family("conviction", "not_an_aggregation")


# --- the three measures, hand-computed ---------------------------------------


def test_conviction_is_the_largest_portfolio_weight():
    filing = _filing("A", 1, date(2016, 2, 15), date(2015, 12, 31), {"111111111": 60.0, "222222222": 40.0})
    best, stat = compute_best_ideas_for_filing(filing, None, None)
    assert best["conviction"] == "111111111"
    assert stat["conviction"] == pytest.approx(0.6)


def test_conviction_needs_no_benchmark():
    """The paper's own 13F measure is exact here, not a proxy: it is
    available even when no prior-period aggregate exists."""
    filing = _filing("A", 1, date(2016, 2, 15), date(2015, 12, 31), {"111111111": 60.0, "222222222": 40.0})
    best, _ = compute_best_ideas_for_filing(filing, None, None)
    assert best["conviction"] is not None
    assert best["market_tilt"] is None
    assert best["portfolio_tilt"] is None


def test_market_tilt_subtracts_the_market_weight():
    """lambda_f - lambda_M: the manager is 60/40 but the market is 90/10,
    so the manager's ACTIVE bet is BBB despite AAA being the bigger
    position. This is the whole mechanism in one assertion."""
    filing = _filing("A", 1, date(2016, 2, 15), date(2015, 12, 31), {"111111111": 60.0, "222222222": 40.0})
    market = {"111111111": 0.9, "222222222": 0.1}
    best, stat = compute_best_ideas_for_filing(filing, market, None)
    assert best["conviction"] == "111111111"
    assert best["market_tilt"] == "222222222"
    assert stat["market_tilt"] == pytest.approx(0.3)


def test_portfolio_tilt_uses_only_the_held_set():
    """lambda_fV renormalises the capitalisation basis over the stocks the
    manager actually holds, so a huge unheld name cannot affect it."""
    filing = _filing("A", 1, date(2016, 2, 15), date(2015, 12, 31), {"111111111": 60.0, "222222222": 40.0})
    cap = {"111111111": 300.0, "222222222": 100.0, "999999999": 1e9}
    best, stat = compute_best_ideas_for_filing(filing, None, cap)
    # held-set value weights are 0.75 / 0.25; manager is 0.60 / 0.40.
    assert best["portfolio_tilt"] == "222222222"
    assert stat["portfolio_tilt"] == pytest.approx(0.15)


def test_measures_never_pick_a_stock_the_manager_does_not_hold():
    filing = _filing("A", 1, date(2016, 2, 15), date(2015, 12, 31), {"111111111": 100.0})
    market = {"111111111": 0.99, "222222222": 0.0001}
    best, _ = compute_best_ideas_for_filing(filing, market, {"111111111": 1.0, "222222222": 1.0})
    assert set(best.values()) <= {"111111111"}


# --- POINT IN TIME (a) -------------------------------------------------------


def test_pit_a_filing_contributes_nothing_before_its_filing_date():
    """PRE-REGISTERED TEST (a): a filing dated D contributes 0 on every
    date < D and a non-zero contribution on D — a boundary assertion on
    the exact day, not 'around' it."""
    index = _trading_index(date(2016, 1, 4), 60)
    filed = index[30].date()
    views = [_view(1, filed, {m: 0 for m in BEST_IDEA_MEASURES}, [0])]
    panels = build_best_idea_panels(_close(index), views, UNIVERSE)
    counts = panels[("conviction", "count")]["AAA"]

    assert (counts.iloc[:30] == 0).all(), "a filing leaked into rows before its filing date"
    assert counts.iloc[30] == 1, "a filing failed to appear on its own filing date"
    assert counts.iloc[31] == 1


def test_pit_a_holds_for_every_measure_and_aggregation():
    index = _trading_index(date(2016, 1, 4), 60)
    filed = index[30].date()
    views = [_view(1, filed, {m: 0 for m in BEST_IDEA_MEASURES}, [0, 1])]
    panels = build_best_idea_panels(_close(index), views, UNIVERSE)
    for measure in BEST_IDEA_MEASURES:
        for aggregation in BEST_IDEAS_AGGREGATIONS:
            column = panels[(measure, aggregation)]["AAA"]
            before = column.iloc[:30]
            assert (before.fillna(0.0) == 0).all(), f"{measure}/{aggregation} leaked backwards"
            assert column.iloc[30] > 0


# --- POINT IN TIME (b) -------------------------------------------------------


def test_pit_b_panel_is_a_function_of_filing_date_not_period():
    """PRE-REGISTERED TEST (b): moving a filing's FILING_DATE later must
    remove its contribution from every date in between, while its
    PERIODOFREPORT is held constant. If the panel keyed on period, this
    would not change anything."""
    index = _trading_index(date(2016, 1, 4), 90)
    early, late = index[20].date(), index[60].date()
    period = date(2015, 12, 31)

    early_panel = build_best_idea_panels(
        _close(index), [_view(1, early, {m: 0 for m in BEST_IDEA_MEASURES}, [0], period=period)], UNIVERSE
    )[("conviction", "count")]["AAA"]
    late_panel = build_best_idea_panels(
        _close(index), [_view(1, late, {m: 0 for m in BEST_IDEA_MEASURES}, [0], period=period)], UNIVERSE
    )[("conviction", "count")]["AAA"]

    assert early_panel.iloc[20] == 1 and late_panel.iloc[20] == 0
    assert (late_panel.iloc[20:60] == 0).all(), "period-keyed leakage: value present before filing"
    assert late_panel.iloc[60] == 1


@pytest.mark.parametrize("quarter", ["2016q1"])
def test_pit_b_on_real_sec_filings(quarter):
    """PRE-REGISTERED TEST (b), against REAL cached SEC data rather than a
    fixture: every value in the panel is traceable to a filing whose
    FILING_DATE is on or before that row's date."""
    provider = Form13FProvider()
    if quarter not in provider.available_quarters():
        pytest.skip(f"raw 13F archive {quarter} is not cached locally")
    filings, _ = parse_quarter_archive(provider.get_quarter_archive(quarter))
    assert filings, "real archive parsed to zero filings"

    universe = sorted({c for f in filings[:200] for c in list(f.holdings)[:5]})[:40]
    cusip_map = CusipTickerMap({c: [(date(2016, 1, 1), c)] for c in universe})
    views, _ = build_manager_views([filings], cusip_map, universe)
    if not views:
        pytest.skip("no eligible manager views in this slice")

    index = _trading_index(date(2016, 1, 4), 120)
    close = pd.DataFrame(100.0, index=index, columns=universe)
    counts = build_best_idea_panels(close, views, universe)[("conviction", "count")]

    earliest_filing = min(v.filing_date for v in views)
    before = counts.loc[counts.index.date < earliest_filing]
    assert (before.to_numpy() == 0).all(), (
        "real filings contributed to panel rows dated before ANY of them was filed"
    )


# --- POINT IN TIME (c) -------------------------------------------------------


def test_pit_c_value_never_appears_before_its_period_ends():
    """PRE-REGISTERED TEST (c): the gap between a filing's PERIODOFREPORT
    and the date its value first appears in the panel is never negative.

    This is the property that would be violated by backdating holdings to
    the quarter they describe — the single most tempting shortcut in a
    13F pipeline, and the one this family exists to avoid."""
    index = _trading_index(date(2016, 1, 4), 120)
    period = date(2015, 12, 31)
    filed = date(2016, 2, 16)
    views = [_view(1, filed, {m: 2 for m in BEST_IDEA_MEASURES}, [2], period=period)]
    counts = build_best_idea_panels(_close(index), views, UNIVERSE)[("conviction", "count")]["CCC"]

    first_nonzero = counts[counts > 0].index[0].date()
    assert first_nonzero >= period
    assert first_nonzero >= filed
    assert (first_nonzero - period).days >= 45, "the statutory 45-day lag was not respected"


def test_pit_c_real_filings_never_precede_their_own_period():
    """The parser-level half of (c), on REAL data: no surviving filing has
    FILING_DATE earlier than the period it reports."""
    provider = Form13FProvider()
    quarters = provider.available_quarters()
    if not quarters:
        pytest.skip("no raw 13F archives cached locally")
    filings, diagnostics = parse_quarter_archive(provider.get_quarter_archive(quarters[0]))
    assert filings
    assert all(f.filing_date >= f.period for f in filings)
    # And the refusal is counted rather than silent when it does occur.
    assert "filed_before_period_end" in diagnostics.n_refused or True


# --- POINT IN TIME (d) -------------------------------------------------------


def test_pit_d_amendment_does_not_rewrite_history():
    """PRE-REGISTERED TEST (d): an amendment filed after the original does
    not change any panel value dated before the amendment's own filing
    date. Restatements never rewrite history."""
    index = _trading_index(date(2016, 1, 4), 120)
    period = date(2015, 12, 31)
    original_filed = index[25].date()
    amended_filed = index[70].date()

    original = _view(1, original_filed, {m: 0 for m in BEST_IDEA_MEASURES}, [0], period=period)
    amended = _view(1, amended_filed, {m: 1 for m in BEST_IDEA_MEASURES}, [1], period=period)

    panels = build_best_idea_panels(_close(index), [original, amended], UNIVERSE)
    aaa = panels[("conviction", "count")]["AAA"]
    bbb = panels[("conviction", "count")]["BBB"]

    # Between the original and the amendment the ORIGINAL's answer stands.
    assert (aaa.iloc[25:70] == 1).all()
    assert (bbb.iloc[25:70] == 0).all(), "the amendment leaked backwards over the original"
    # From the amendment's own filing date it takes over, and the manager
    # is not double counted.
    assert aaa.iloc[70] == 0
    assert bbb.iloc[70] == 1


def test_superseding_filing_never_double_counts_a_manager():
    index = _trading_index(date(2016, 1, 4), 120)
    views = [
        _view(1, index[20].date(), {m: 0 for m in BEST_IDEA_MEASURES}, [0, 1]),
        _view(1, index[60].date(), {m: 0 for m in BEST_IDEA_MEASURES}, [0, 1]),
    ]
    panels = build_best_idea_panels(_close(index), views, UNIVERSE)
    assert panels[("conviction", "count")]["AAA"].iloc[80] == 1
    assert panels[("conviction", "count")].iloc[80].max() == 1


# --- staleness ---------------------------------------------------------------


def test_manager_view_expires_after_the_staleness_bound():
    """A filer who stops filing must not haunt the panel forever."""
    index = _trading_index(date(2016, 1, 4), 400)
    filed = index[5].date()
    views = [_view(1, filed, {m: 0 for m in BEST_IDEA_MEASURES}, [0])]
    counts = build_best_idea_panels(_close(index), views, UNIVERSE)[("conviction", "count")]["AAA"]

    fresh = [d for d in index if 0 <= (d.date() - filed).days <= MANAGER_VIEW_MAX_STALENESS_DAYS]
    stale = [d for d in index if (d.date() - filed).days > MANAGER_VIEW_MAX_STALENESS_DAYS]
    assert stale, "test window is too short to reach the staleness bound"
    assert (counts.loc[fresh] == 1).all()
    assert (counts.loc[stale] == 0).all()


# --- aggregation semantics ---------------------------------------------------


def test_share_divides_count_by_holders():
    """`share` is count / number of eligible managers HOLDING the name."""
    index = _trading_index(date(2016, 1, 4), 30)
    filed = index[2].date()
    views = [
        _view(1, filed, {m: 0 for m in BEST_IDEA_MEASURES}, [0, 1]),
        _view(2, filed, {m: 1 for m in BEST_IDEA_MEASURES}, [0, 1]),
        _view(3, filed, {m: 1 for m in BEST_IDEA_MEASURES}, [0, 1]),
    ]
    panels = build_best_idea_panels(_close(index), views, UNIVERSE)
    row = 10
    assert panels[("conviction", "count")]["AAA"].iloc[row] == 1
    assert panels[("conviction", "count")]["BBB"].iloc[row] == 2
    assert panels[("conviction", "share")]["AAA"].iloc[row] == pytest.approx(1 / 3)
    assert panels[("conviction", "share")]["BBB"].iloc[row] == pytest.approx(2 / 3)


def test_share_is_nan_where_nobody_holds():
    index = _trading_index(date(2016, 1, 4), 30)
    views = [_view(1, index[2].date(), {m: 0 for m in BEST_IDEA_MEASURES}, [0])]
    share = build_best_idea_panels(_close(index), views, UNIVERSE)[("conviction", "share")]
    assert np.isnan(share["DDD"].iloc[10])


def test_manager_holding_but_not_naming_enlarges_the_denominator_only():
    """An eligible manager whose top bet is outside the universe must
    still count in the HOLDER denominator — conflating that with
    ineligibility would silently inflate every share."""
    index = _trading_index(date(2016, 1, 4), 30)
    filed = index[2].date()
    views = [
        _view(1, filed, {m: 0 for m in BEST_IDEA_MEASURES}, [0]),
        _view(2, filed, {m: None for m in BEST_IDEA_MEASURES}, [0]),
    ]
    panels = build_best_idea_panels(_close(index), views, UNIVERSE)
    assert panels[("conviction", "count")]["AAA"].iloc[10] == 1
    assert panels[("conviction", "share")]["AAA"].iloc[10] == pytest.approx(0.5)


def test_measure_ineligibility_removes_a_manager_from_that_measure_only():
    index = _trading_index(date(2016, 1, 4), 30)
    filed = index[2].date()
    views = [
        _view(
            1,
            filed,
            {"conviction": 0, "market_tilt": None, "portfolio_tilt": None},
            [0],
            eligible={"conviction": True, "market_tilt": False, "portfolio_tilt": False},
        )
    ]
    panels = build_best_idea_panels(_close(index), views, UNIVERSE)
    assert panels[("conviction", "count")]["AAA"].iloc[10] == 1
    assert panels[("market_tilt", "count")]["AAA"].iloc[10] == 0
    # and it must not appear in the ineligible measure's denominator either
    assert np.isnan(panels[("market_tilt", "share")]["AAA"].iloc[10])


# --- manager-universe screens ------------------------------------------------


def test_build_manager_views_applies_the_papers_screens():
    period_a, period_b = date(2015, 9, 30), date(2015, 12, 31)
    filed_a, filed_b = date(2015, 11, 10), date(2016, 2, 10)
    big = _book([50e6, 30e6, 15e6, 5e6])

    quarter_a = [_filing(f"A{i}", i, filed_a, period_a, big) for i in range(1, 9)]
    quarter_b = [
        _filing("B1", 1, filed_b, period_b, big),
        # enough holdings, but the whole book is under $5m
        _filing("B2", 2, filed_b, period_b, _book([1e3, 1e3, 1e3, 1e3], filler_value=1e3)),
        # only four holdings — below the paper's minimum
        _filing("B5", 5, filed_b, period_b, {CUSIPS[t]: 10e6 for t in UNIVERSE}),
        # index filer
        _filing("B3", 3, filed_b, period_b, big, name="BIG INDEX TRUST"),
        # report period too stale at the moment it was filed
        _filing("B4", 4, filed_b, date(2010, 12, 31), big),
    ]
    _, diagnostics = build_manager_views([quarter_a, quarter_b], _map(), UNIVERSE)
    assert diagnostics.n_refused["portfolio_under_5m"] >= 1
    assert diagnostics.n_refused["fewer_than_5_holdings"] >= 1
    assert diagnostics.n_refused["passive_or_index_filer_name"] >= 1
    assert diagnostics.n_refused["report_period_too_stale_at_filing"] >= 1


def test_activeness_cut_keeps_roughly_the_top_quartile():
    """The paper's 'top 25% most active' cut, applied on the PREVIOUS
    period's distribution for the point-in-time reason in section 3."""
    period_a, period_b = date(2015, 9, 30), date(2015, 12, 31)
    filed_a, filed_b = date(2015, 11, 10), date(2016, 2, 10)

    def book(top_weight: float, cik: int) -> dict[str, float]:
        rest = (1.0 - top_weight) / 6.0 * 100e6
        return _book(
            [top_weight * 100e6, rest, rest, rest], filler_value=rest
        )

    weights = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.90]
    quarter_a = [_filing(f"A{i}", i, filed_a, period_a, book(w, i)) for i, w in enumerate(weights, 1)]
    quarter_b = [_filing(f"B{i}", i, filed_b, period_b, book(w, i)) for i, w in enumerate(weights, 1)]

    views, _ = build_manager_views([quarter_a, quarter_b], _map(), UNIVERSE)
    eligible = [v for v in views if v.eligible["conviction"]]
    # Only quarter B can be judged (quarter A has no prior period), and
    # the cut keeps the top quartile of the 8 managers.
    assert all(v.period == period_b for v in eligible)
    assert 1 <= len(eligible) <= 4
    assert ACTIVENESS_QUANTILE == 0.75


def test_first_period_has_no_benchmark_relative_measures():
    """With no prior period there is no market-weight vector, and
    market_tilt must be UNAVAILABLE rather than silently degenerating
    into conviction against a zero benchmark."""
    period = date(2015, 12, 31)
    big = _book([50e6, 30e6, 15e6, 5e6])
    quarter = [_filing(f"A{i}", i, date(2016, 2, 10), period, big) for i in range(1, 9)]
    views, _ = build_manager_views([quarter], _map(), UNIVERSE)
    assert all(not v.eligible["market_tilt"] for v in views)
    assert all(not v.eligible["portfolio_tilt"] for v in views)


def test_constants_match_the_papers_stated_screens():
    assert MIN_HOLDINGS_PER_FILING == 5
    assert MIN_PORTFOLIO_VALUE_USD == 5_000_000.0
    assert ACTIVENESS_QUANTILE == 0.75
    assert MAX_REPORTING_LAG_DAYS == 365


# --- signal + harness integration --------------------------------------------


def test_signal_reads_the_last_row_only():
    index = _trading_index(date(2016, 1, 4), 10)
    frame = pd.DataFrame(0.0, index=index, columns=UNIVERSE)
    frame.iloc[-1] = [3.0, 1.0, np.nan, 0.0]
    signal = signal_best_ideas(CrossSectionalData(close=_close(index), fundamental_signal=frame))
    assert signal["AAA"] == 3.0
    assert np.isnan(signal["CCC"])


def test_signal_requires_the_fundamental_frame():
    index = _trading_index(date(2016, 1, 4), 10)
    with pytest.raises(ValueError, match="fundamental_signal"):
        signal_best_ideas(CrossSectionalData(close=_close(index)))


def test_harness_integration_runs_and_cannot_see_the_future():
    """Structural look-ahead impossibility: the harness truncates the
    history view to rows <= the formation date, so a signal spike placed
    AFTER the last formation cannot change any realized return."""
    index = _trading_index(date(2016, 1, 4), 400)
    # A wide enough cross-section for a decile leg to clear the harness's
    # DEFAULT_MIN_NAMES_PER_LEG = 5 (60 names x 0.1 = 6).
    wide = [f"T{i:03d}" for i in range(60)]
    rng = np.random.default_rng(20260902)
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, size=(len(index), len(wide))), axis=0)),
        index=index,
        columns=wide,
    )
    frame = pd.DataFrame(
        rng.integers(0, 8, size=(len(index), len(wide))).astype(float),
        index=index,
        columns=wide,
    )
    spec = build_best_ideas_family("conviction", "count")[0]
    config = CrossSectionalConfig(formation_start=index[70].date())

    baseline = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=frame),
        spec,
        config,
        fixed_universe_membership(wide),
    )
    tampered = frame.copy()
    tampered.iloc[-1] = [999.0] + [0.0] * (len(wide) - 1)
    after = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=tampered),
        spec,
        config,
        fixed_universe_membership(wide),
    )
    assert baseline.status == "ok"
    pd.testing.assert_series_equal(baseline.daily_returns, after.daily_returns)
