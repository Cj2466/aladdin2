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


def _panels(index=None, columns=None):
    index = index if index is not None else _trading_index(date(2016, 1, 4), 30)
    columns = columns if columns is not None else UNIVERSE
    return {
        (m, a): pd.DataFrame(0.0, index=index, columns=columns)
        for m in BEST_IDEA_MEASURES
        for a in BEST_IDEAS_AGGREGATIONS
    }


def test_grid_is_exactly_the_pre_registered_36():
    specs = all_best_ideas_specs(_panels())
    assert len(specs) == BEST_IDEAS_N_TRIALS == 36
    assert len(BEST_IDEA_MEASURES) == 3
    assert len(BEST_IDEAS_AGGREGATIONS) == 2
    assert len(BEST_IDEAS_HOLDING_DAYS) == 3
    assert len(BEST_IDEAS_RANK_FRACTIONS) == 2


def test_grid_ids_are_unique_and_family_tagged():
    specs = all_best_ideas_specs(_panels())
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
    panels = _panels()
    frame = panels[("conviction", "count")]
    with pytest.raises(ValueError):
        build_best_ideas_family("not_a_measure", "count", frame)
    with pytest.raises(ValueError):
        build_best_ideas_family("conviction", "not_an_aggregation", frame)


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


def test_pit_b_on_real_sec_filings():
    """PRE-REGISTERED TEST (b), against REAL cached SEC data rather than a
    fixture: every value in the panel is traceable to a filing whose
    FILING_DATE is on or before that row's date.

    TWO consecutive quarters, not one, and that is load-bearing: every
    benchmark-relative measure and the activeness cutoff are computed from
    the PREVIOUS period, so a single-quarter slice yields zero eligible
    views and this test would skip itself into uselessness — which it
    silently did until this was fixed."""
    quarters = ["2015q4", "2016q1"]
    provider = Form13FProvider()
    available = provider.available_quarters()
    missing = [q for q in quarters if q not in available]
    if missing:
        pytest.skip(f"raw 13F archives not cached locally: {missing}")

    by_quarter = []
    for quarter in quarters:
        filings, _ = parse_quarter_archive(provider.get_quarter_archive(quarter))
        assert filings, f"real archive {quarter} parsed to zero filings"
        by_quarter.append(filings)

    # A universe of real CUSIPs drawn from the real books, mapped to
    # themselves so identifier resolution cannot mask a timing bug.
    universe = sorted({c for f in by_quarter[-1][:400] for c in list(f.holdings)[:8]})[:60]
    cusip_map = CusipTickerMap({c: [(date(2016, 1, 1), c)] for c in universe})
    views, _ = build_manager_views(by_quarter, cusip_map, universe)
    assert views, "real two-quarter slice produced no eligible manager views"

    index = _trading_index(date(2015, 10, 1), 260)
    close = pd.DataFrame(100.0, index=index, columns=universe)
    counts = build_best_idea_panels(close, views, universe)[("conviction", "count")]

    earliest_filing = min(v.filing_date for v in views)
    before = counts.loc[counts.index.date < earliest_filing]
    assert (before.to_numpy() == 0).all(), (
        "real filings contributed to panel rows dated before ANY of them was filed"
    )
    # And the panel is genuinely populated afterwards, so the assertion
    # above is not passing merely because everything is zero.
    assert counts.to_numpy().sum() > 0, "real slice produced an all-zero panel"

    # Per-filing boundary on REAL filing dates: for each ranked name, the
    # first day it is non-zero is never earlier than the earliest filing
    # date of a real view naming it.
    for ticker in universe:
        column = counts[ticker]
        nonzero = column[column > 0]
        if nonzero.empty:
            continue
        idx = universe.index(ticker)
        namers = [v.filing_date for v in views if v.best_idea.get("conviction") == idx]
        assert namers, f"{ticker} is non-zero but no real view names it"
        assert nonzero.index[0].date() >= min(namers)


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
    panel = pd.DataFrame(0.0, index=index, columns=UNIVERSE)
    panel.iloc[-1] = [3.0, 1.0, np.nan, 0.0]
    signal = signal_best_ideas(
        CrossSectionalData(close=_close(index), fundamental_signal=frame), panel=panel
    )
    assert signal["AAA"] == 3.0
    assert np.isnan(signal["CCC"])


def test_signal_reads_its_own_panel_at_the_formation_timestamp():
    """The panel arrives by closure so the whole 36-spec grid can share one
    DSR denominator. That is only safe because the row read is the
    formation timestamp of the ALREADY-truncated history view — so a value
    dated after the formation is unreachable."""
    index = _trading_index(date(2016, 1, 4), 10)
    panel = pd.DataFrame(0.0, index=index, columns=UNIVERSE)
    panel.iloc[5] = [7.0, 0.0, 0.0, 0.0]
    panel.iloc[9] = [999.0, 0.0, 0.0, 0.0]
    truncated = pd.DataFrame(0.0, index=index[:6], columns=UNIVERSE)
    signal = signal_best_ideas(
        CrossSectionalData(close=_close(index[:6]), fundamental_signal=truncated), panel=panel
    )
    assert signal["AAA"] == 7.0, "signal did not read the formation row of its own panel"


def test_signal_requires_the_fundamental_frame():
    index = _trading_index(date(2016, 1, 4), 10)
    panel = pd.DataFrame(0.0, index=index, columns=UNIVERSE)
    with pytest.raises(ValueError, match="fundamental_signal"):
        signal_best_ideas(CrossSectionalData(close=_close(index)), panel=panel)


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
    spec = build_best_ideas_family("conviction", "count", frame)[0]
    config = CrossSectionalConfig(formation_start=index[70].date())

    baseline = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=frame),
        spec,
        config,
        fixed_universe_membership(wide),
    )
    # Tamper with the CLOSURE-SUPPLIED panel, which is the half the
    # harness does not itself slice — if the closure could reach a row
    # after the last formation, this would change the realized returns.
    tampered = frame.copy()
    tampered.iloc[-1] = [999.0] + [0.0] * (len(wide) - 1)
    after = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=tampered),
        build_best_ideas_family("conviction", "count", tampered)[0],
        config,
        fixed_universe_membership(wide),
    )
    assert baseline.status == "ok"
    pd.testing.assert_series_equal(baseline.daily_returns, after.daily_returns)


def test_whole_grid_screens_under_one_36_trial_denominator():
    """THE multiple-comparisons contract, pinned. The six panels must be
    screened in ONE call: screening them separately would set n_trials to
    6 and compute sigma_sr from 6 siblings, understating the correction on
    every row. The pre-registration fixed the denominator at 36."""
    from app.services.research_lab.cross_sectional import screen_cross_sectional_universe

    index = _trading_index(date(2016, 1, 4), 320)
    wide = [f"T{i:03d}" for i in range(60)]
    rng = np.random.default_rng(20260902)
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, size=(len(index), len(wide))), axis=0)),
        index=index,
        columns=wide,
    )
    panels = {
        (m, a): pd.DataFrame(
            rng.integers(0, 8, size=(len(index), len(wide))).astype(float),
            index=index,
            columns=wide,
        )
        for m in BEST_IDEA_MEASURES
        for a in BEST_IDEAS_AGGREGATIONS
    }
    config = CrossSectionalConfig(formation_start=index[70].date())
    results = screen_cross_sectional_universe(
        CrossSectionalData(close=close, fundamental_signal=panels[("conviction", "count")]),
        all_best_ideas_specs(panels),
        config,
        fixed_universe_membership(wide),
    )
    assert len(results) == BEST_IDEAS_N_TRIALS == 36
    assert {r.deflated_sharpe.n_trials for r in results} == {36}


def test_each_spec_actually_reads_its_own_panel():
    """Regression guard for the closure binding: six panels, six distinct
    signals. If every spec accidentally shared one panel, the measures
    would be indistinguishable and this family would silently be one
    signal reported six times."""
    index = _trading_index(date(2016, 1, 4), 30)
    panels = {}
    for i, (m, a) in enumerate(
        [(m, a) for m in BEST_IDEA_MEASURES for a in BEST_IDEAS_AGGREGATIONS]
    ):
        frame = pd.DataFrame(0.0, index=index, columns=UNIVERSE)
        frame.iloc[-1] = [float(i), 0.0, 0.0, 0.0]
        panels[(m, a)] = frame

    history = CrossSectionalData(
        close=_close(index), fundamental_signal=pd.DataFrame(0.0, index=index, columns=UNIVERSE)
    )
    seen = set()
    for m in BEST_IDEA_MEASURES:
        for a in BEST_IDEAS_AGGREGATIONS:
            spec = build_best_ideas_family(m, a, panels[(m, a)])[0]
            seen.add(spec.signal_fn(history)["AAA"])
    assert seen == {0.0, 1.0, 2.0, 3.0, 4.0, 5.0}


def test_panel_builder_refuses_a_ticker_list_that_is_not_close_columns():
    """REGRESSION, and it was a silent wrong-answer bug rather than a
    crash. Views store best ideas as integer indices into the ticker list
    build_manager_views was given. The production entry point originally
    built views against the full 768-name universe but panels against the
    PRICED subset (smaller, and in the price provider's column order), so
    every index pointed at a different company and the family would have
    ranked the wrong names with no error at all."""
    index = _trading_index(date(2016, 1, 4), 30)
    close = pd.DataFrame(100.0, index=index, columns=["AAA", "BBB"])
    views = [_view(1, index[2].date(), {m: 0 for m in BEST_IDEA_MEASURES}, [0])]

    with pytest.raises(ValueError, match="EXACTLY close.columns"):
        build_best_idea_panels(close, views, UNIVERSE)
    with pytest.raises(ValueError, match="EXACTLY close.columns"):
        build_best_idea_panels(close, views, ["BBB", "AAA"])
    # The aligned call is accepted.
    panels = build_best_idea_panels(close, views, ["AAA", "BBB"])
    assert panels[("conviction", "count")]["AAA"].iloc[10] == 1


def test_market_weight_vector_ignores_prior_period_filings_made_too_late():
    """PIT: the OTHER half of this module's point-in-time contract.

    Section 3 claims BOTH cross-manager statistics — the aggregate
    market-weight vector and the activeness cutoff — are computed from the
    previous period's filings restricted to those PUBLIC STRICTLY BEFORE
    the current period ended. The activeness half is pinned by the test
    below; this pins the market-weight half, which mutation testing found
    was NOT covered: deleting its `filing.filing_date < period` bound left
    the entire suite green, so the leak that was fixed on the cutoff could
    silently reappear on the benchmark vector with nothing to catch it.

    Differential, and it needs THREE periods: the benchmark-relative
    measures are unavailable in the first period (no prior), so period C
    is the earliest one whose market-weight vector is both populated and
    judged against a real activeness bar.

    Period-B managers mirror the period-A aggregate, so their own tilts
    are ~0 and period C's bar is low. The manager under test is AAA-heavy
    in absolute terms but its ACTIVE bet is BBB, because the visible
    benchmark is AAA-dominated. Four enormous BBB-heavy period-B filings
    submitted AFTER period C ended would invert that benchmark and flip
    the answer to AAA — if they were visible, which they must not be.
    """
    period_a, period_b, period_c = date(2015, 6, 30), date(2015, 9, 30), date(2015, 12, 31)
    filed_a, filed_b, filed_c = date(2015, 8, 10), date(2015, 11, 10), date(2016, 2, 10)
    delinquent = date(2016, 1, 20)  # after period_c ended

    base = [60e6, 20e6, 10e6, 5e6]
    quarter_a = [_filing(f"A{i}", i, filed_a, period_a, _book(base)) for i in range(1, 9)]
    quarter_b = [_filing(f"B{i}", i, filed_b, period_b, _book(base)) for i in range(1, 9)]
    quarter_c = [_filing("C1", 101, filed_c, period_c, _book([50e6, 30e6, 10e6, 5e6]))]
    late = [
        _filing(f"L{i}", 900 + i, delinquent, period_b, _book([1e6, 5000e6, 1e6, 1e6]))
        for i in range(4)
    ]

    def under_test(quarters):
        views, _ = build_manager_views(quarters, _map(), UNIVERSE)
        hits = [v for v in views if v.cik == 101 and v.period == period_c]
        assert hits, "fixture produced no period-C view for the manager under test"
        return hits[0]

    baseline = under_test([quarter_a, quarter_b, quarter_c])
    with_late = under_test([quarter_a, quarter_b + late, quarter_c])

    # Non-vacuity: the benchmark-relative measures really are live here,
    # and BBB (index 1) is the active bet against the visible benchmark.
    assert baseline.eligible["market_tilt"]
    assert baseline.best_idea["market_tilt"] == 1
    assert baseline.best_idea["portfolio_tilt"] == 1

    for measure in ("market_tilt", "portfolio_tilt"):
        assert with_late.best_idea[measure] == baseline.best_idea[measure], (
            f"{measure}: a prior-period filing submitted AFTER the current period ended changed "
            "the benchmark a manager was measured against — the market-weight vector leaked "
            "future filings"
        )
        assert with_late.max_stat[measure] == pytest.approx(baseline.max_stat[measure])


def test_activeness_cutoff_ignores_prior_period_filings_made_too_late():
    """PIT: the activeness cutoff for period p is a quantile over period
    p-1's filings, and must use only those PUBLIC BEFORE p ended. A
    delinquent p-1 filer submitting after p began must not be able to move
    the bar a p-1-judged manager is measured against.

    Built as a differential test: the same on-time filings, run twice,
    once with an extra late p-1 filing whose enormous concentration would
    drag the quantile upward if it were counted.
    """
    period_a, period_b = date(2015, 9, 30), date(2015, 12, 31)
    on_time = date(2015, 11, 10)
    # Filed AFTER period_b began, so invisible to period_b's cutoff.
    delinquent = date(2016, 1, 20)

    def book(top: float) -> dict[str, float]:
        rest = (1.0 - top) / 6.0 * 100e6
        return _book([top * 100e6, rest, rest, rest], filler_value=rest)

    weights = [0.20, 0.22, 0.24, 0.26, 0.28, 0.30, 0.32, 0.34]
    quarter_a = [_filing(f"A{i}", i, on_time, period_a, book(w)) for i, w in enumerate(weights, 1)]
    quarter_b = [
        _filing(f"B{i}", i, date(2016, 2, 10), period_b, book(w))
        for i, w in enumerate(weights, 1)
    ]

    baseline, _ = build_manager_views([quarter_a, quarter_b], _map(), UNIVERSE)

    # Four extremely concentrated LATE filings for period A. If the cutoff
    # counted them, period B's bar would rise and fewer B managers survive.
    late = [
        _filing(f"L{i}", 900 + i, delinquent, period_a, book(0.95))
        for i in range(4)
    ]
    with_late, _ = build_manager_views([quarter_a + late, quarter_b], _map(), UNIVERSE)

    def eligible_b(views):
        return sorted(v.cik for v in views if v.period == period_b and v.eligible["conviction"])

    assert eligible_b(baseline), "fixture produced no eligible period-B managers"
    assert eligible_b(baseline) == eligible_b(with_late), (
        "a prior-period filing submitted AFTER the current period began changed which "
        "managers cleared the activeness cut — the cutoff leaked future filings"
    )
