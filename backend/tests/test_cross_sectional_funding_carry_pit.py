"""Tests for the POINT-IN-TIME universe variant of the funding-carry
family.

THE ONE THING THAT MUST BE TESTED RIGOROUSLY, and the reason this file
exists, is that the universe is genuinely point-in-time. Getting it wrong
— letting a 2026 listing into a 2021 cross-section, or keeping a contract
that delisted in 2022 alive through 2023, or (subtlest and worst) letting
"which contracts survived" leak backwards — would silently reintroduce
look-ahead bias into every number the family reports, and would do it
invisibly: the Sharpe would simply be better.

So the universe is attacked from four directions:
  * KNOWN BOUNDARIES — a synthetic panel with a contract of known
    inception and a contract of known delisting, asserted at the exact
    day before, the day of, and the day after each boundary.
  * FUTURE-MUTATION IMMUNITY — every row after the formation date is
    overwritten with contradictory data (the dead contract rises from the
    grave, the late listing never lists) and the as-of universe must be
    bit-identical. This is the property a look-ahead bug breaks.
  * TRUNCATION INVARIANCE — computing the as-of universe from a panel
    physically truncated at the formation date must give the same answer.
  * VECTORIZATION AGREEMENT — the whole-panel boolean mask the backtest
    actually consumes must equal the auditable as-of function, row for
    row, on that same synthetic panel.

Calendar-day indexes throughout: crypto trades 24/7/365 (the parent
family's and the sibling crypto family's convention)."""

from datetime import date

import httpx
import numpy as np
import pandas as pd
import pytest

from app.services.market_data.binance_futures_provider import (
    FAPI_BASE_URL,
    BinanceFuturesProvider,
)
from app.services.research_lab.cross_sectional_funding_carry import (
    FUNDING_CARRY_N_TRIALS,
    FundingCarryConfig,
    build_funding_eligibility,
)
from app.services.research_lab.cross_sectional_funding_carry_pit import (
    FUNDING_CARRY_PIT_FAMILY_KEY,
    PIT_LIVENESS_WINDOW_DAYS,
    build_pit_eligibility,
    build_pit_membership,
    measure_breadth,
    measure_symbol_lifetimes,
    pit_universe_asof,
    run_funding_carry_pit_screening,
)

# The synthetic panel every universe test uses. Four contracts with
# deliberately different lives:
#   OLDUSDT   trades every day of the panel        (always in)
#   DEADUSDT  trades until 2021-03-01, then never  (delisting boundary)
#   LATEUSDT  does not trade until 2021-04-01      (inception boundary)
#   GHOSTUSDT never trades at all                  (must never appear)
PANEL_START = "2021-01-01"
PANEL_DAYS = 181  # 2021-01-01 .. 2021-06-30
DEAD_LAST_DAY = pd.Timestamp("2021-03-01")
LATE_FIRST_DAY = pd.Timestamp("2021-04-01")


def _lifecycle_close() -> pd.DataFrame:
    index = pd.date_range(PANEL_START, periods=PANEL_DAYS, freq="D")
    close = pd.DataFrame(100.0, index=index, columns=["OLDUSDT", "DEADUSDT", "LATEUSDT", "GHOSTUSDT"])
    close.loc[close.index > DEAD_LAST_DAY, "DEADUSDT"] = np.nan
    close.loc[close.index < LATE_FIRST_DAY, "LATEUSDT"] = np.nan
    close["GHOSTUSDT"] = np.nan
    return close


# --- the point-in-time universe: known boundaries ----------------------------


def test_late_listing_is_absent_before_its_inception_and_present_from_it():
    close = _lifecycle_close()
    assert "LATEUSDT" not in pit_universe_asof(close, "2021-01-15")
    assert "LATEUSDT" not in pit_universe_asof(close, LATE_FIRST_DAY - pd.Timedelta(days=1))
    assert "LATEUSDT" in pit_universe_asof(close, LATE_FIRST_DAY)
    assert "LATEUSDT" in pit_universe_asof(close, "2021-06-30")


def test_delisted_contract_is_present_while_alive_and_gone_after_the_liveness_window():
    close = _lifecycle_close()
    # Alive: before and on its last real market day.
    assert "DEADUSDT" in pit_universe_asof(close, "2021-01-15")
    assert "DEADUSDT" in pit_universe_asof(close, DEAD_LAST_DAY)
    # The liveness window is a trailing window of rows INCLUDING the
    # current one, so the last day it can still be seen is
    # last_day + (window - 1) rows.
    last_visible = DEAD_LAST_DAY + pd.Timedelta(days=PIT_LIVENESS_WINDOW_DAYS - 1)
    assert "DEADUSDT" in pit_universe_asof(close, last_visible)
    assert "DEADUSDT" not in pit_universe_asof(close, last_visible + pd.Timedelta(days=1))
    # ...and never returns.
    for day in pd.date_range(last_visible + pd.Timedelta(days=1), close.index[-1], freq="D"):
        assert "DEADUSDT" not in pit_universe_asof(close, day)


def test_a_contract_that_never_traded_is_never_in_the_universe():
    close = _lifecycle_close()
    for day in close.index:
        assert "GHOSTUSDT" not in pit_universe_asof(close, day)


def test_universe_composition_at_three_representative_dates():
    close = _lifecycle_close()
    # Only the two early contracts exist yet.
    assert pit_universe_asof(close, "2021-02-01") == ["DEADUSDT", "OLDUSDT"]
    # DEAD has aged out of the liveness window; LATE has not listed.
    assert pit_universe_asof(close, "2021-03-31") == ["OLDUSDT"]
    # LATE has listed; DEAD is gone for good.
    assert pit_universe_asof(close, "2021-05-01") == ["LATEUSDT", "OLDUSDT"]


def test_empty_history_before_the_panel_starts_is_an_empty_universe():
    close = _lifecycle_close()
    assert pit_universe_asof(close, "2020-12-31") == []


# --- the point-in-time universe: it cannot see the future --------------------


@pytest.mark.parametrize("formation", ["2021-01-20", "2021-02-15", "2021-03-31", "2021-05-10"])
def test_universe_is_immune_to_mutating_every_future_row(formation: str):
    """THE look-ahead test. Rows strictly after the formation date are
    rewritten to contradict the real future — the delisted contract
    resumes trading, the late listing never lists, a brand-new contract
    appears — and the as-of universe must not move one symbol. A universe
    built with any knowledge of who survives would change here."""
    close = _lifecycle_close()
    baseline = pit_universe_asof(close, formation)

    mutated = close.copy()
    future = mutated.index > pd.Timestamp(formation)
    mutated.loc[future, "DEADUSDT"] = 100.0  # resurrect the dead contract
    mutated.loc[future, "LATEUSDT"] = np.nan  # the late listing never arrives
    mutated.loc[future, "GHOSTUSDT"] = 100.0  # a contract that never was, now trades
    mutated.loc[future, "OLDUSDT"] = np.nan  # the survivor dies

    assert pit_universe_asof(mutated, formation) == baseline


def test_universe_is_invariant_to_physically_truncating_the_panel():
    close = _lifecycle_close()
    for day in close.index:
        assert pit_universe_asof(close, day) == pit_universe_asof(close.loc[:day], day)


def test_a_contract_listed_after_the_panel_end_cannot_appear_anywhere():
    """The roster is discovered today and contains contracts listed in
    2026; none of them may touch a 2021 cross-section."""
    close = _lifecycle_close()
    close["FUTUREUSDT"] = np.nan  # in the roster, no data in this window
    for day in close.index:
        assert "FUTUREUSDT" not in pit_universe_asof(close, day)


# --- the vectorized mask must equal the auditable definition -----------------


def test_membership_matrix_matches_the_asof_function_row_for_row():
    close = _lifecycle_close()
    membership = build_pit_membership(close)
    for day in close.index:
        expected = pit_universe_asof(close, day)
        got = sorted(membership.columns[membership.loc[day].to_numpy()])
        assert got == expected, f"membership disagrees with pit_universe_asof on {day.date()}"


def test_membership_of_an_empty_panel_is_empty_not_an_error():
    empty = pd.DataFrame()
    assert build_pit_membership(empty).empty


# --- the redundancy claim the module docstring makes, measured ---------------


def test_pit_eligibility_equals_the_parent_gate_exactly():
    """The module claims the parent family's gate was ALREADY
    point-in-time at the symbol level, and that the explicit mask is
    redundant-on-purpose. That is a checkable theorem, not a slogan: the
    gate requires a finite close on the formation day, which implies the
    contract both had listed and had traded within the liveness window —
    so the AND can never remove a name the gate accepted. If this ever
    fails, one of the two definitions has drifted."""
    close = _lifecycle_close()
    # A turnover panel with a realistic zombie tail: the delisted contract
    # keeps printing zero-volume bars after its last real market day.
    volume = pd.DataFrame(1e9, index=close.index, columns=close.columns)
    volume.loc[volume.index > DEAD_LAST_DAY, "DEADUSDT"] = 0.0
    volume.loc[volume.index < LATE_FIRST_DAY, "LATEUSDT"] = 0.0
    volume["GHOSTUSDT"] = 0.0

    base = build_funding_eligibility(close, volume)
    pit = build_pit_eligibility(close, volume)
    assert pit.equals(base)
    # And the gate really is doing the point-in-time work claimed of it.
    assert not bool(base.loc[LATE_FIRST_DAY - pd.Timedelta(days=1), "LATEUSDT"])
    assert not bool(base.loc[close.index[-1], "DEADUSDT"])


# --- lifetimes ---------------------------------------------------------------


def test_lifetimes_are_measured_from_the_data_not_from_a_roster():
    close = _lifecycle_close()
    lifetimes = measure_symbol_lifetimes(close)

    assert lifetimes["DEADUSDT"].first_traded == date(2021, 1, 1)
    assert lifetimes["DEADUSDT"].last_traded == DEAD_LAST_DAY.date()
    assert lifetimes["DEADUSDT"].still_listed is False

    assert lifetimes["LATEUSDT"].first_traded == LATE_FIRST_DAY.date()
    assert lifetimes["LATEUSDT"].still_listed is True

    assert lifetimes["OLDUSDT"].still_listed is True
    assert lifetimes["OLDUSDT"].n_market_days == PANEL_DAYS

    assert lifetimes["GHOSTUSDT"].first_traded is None
    assert lifetimes["GHOSTUSDT"].last_traded is None
    assert lifetimes["GHOSTUSDT"].still_listed is False


# --- the roster: survivorship-free by construction ---------------------------


def _roster_transport() -> httpx.MockTransport:
    """A Binance stand-in whose two rosters disagree exactly the way the
    real ones do: exchangeInfo has forgotten the delisted contract, and
    the data archive still remembers it. Also serves a TRUNCATED first
    S3 page so pagination is exercised rather than assumed."""
    page_one = (
        "<ListBucketResult>"
        "<CommonPrefixes><Prefix>data/futures/um/monthly/fundingRate/AAAUSDT/</Prefix></CommonPrefixes>"
        "<CommonPrefixes><Prefix>data/futures/um/monthly/fundingRate/DEADUSDT/</Prefix></CommonPrefixes>"
        "<IsTruncated>true</IsTruncated>"
        "<NextMarker>data/futures/um/monthly/fundingRate/DEADUSDT/</NextMarker>"
        "</ListBucketResult>"
    )
    page_two = (
        "<ListBucketResult>"
        "<CommonPrefixes><Prefix>data/futures/um/monthly/fundingRate/TSLAUSDT/</Prefix></CommonPrefixes>"
        "<CommonPrefixes><Prefix>data/futures/um/monthly/fundingRate/BBBUSDC/</Prefix></CommonPrefixes>"
        "<IsTruncated>false</IsTruncated>"
        "</ListBucketResult>"
    )
    exchange_info = {
        "symbols": [
            {
                "symbol": "AAAUSDT",
                "contractType": "PERPETUAL",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "onboardDate": 1609459200000,  # 2021-01-01
            },
            {
                "symbol": "NEWUSDT",  # live, too new to have an archive directory
                "contractType": "PERPETUAL",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "onboardDate": 1767225600000,  # 2026-01-01
            },
            {
                "symbol": "TSLAUSDT",  # tokenized equity — a different asset class
                "contractType": "TRADIFI_PERPETUAL",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "onboardDate": 1765411200000,
            },
            {
                "symbol": "BTCUSDC",  # not USDT-margined
                "contractType": "PERPETUAL",
                "quoteAsset": "USDC",
                "status": "TRADING",
                "onboardDate": 1609459200000,
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "exchangeInfo" in request.url.path:
            return httpx.Response(200, json=exchange_info)
        marker = request.url.params.get("marker") or ""
        return httpx.Response(200, text=page_two if marker else page_one)

    return httpx.MockTransport(handler)


def _roster_provider() -> BinanceFuturesProvider:
    return BinanceFuturesProvider(
        cache_dir=None,
        sleep=lambda _seconds: None,
        clock=lambda: 0.0,
        client=httpx.Client(transport=_roster_transport(), base_url=FAPI_BASE_URL),
    )


def test_roster_keeps_delisted_contracts_that_exchange_info_has_forgotten():
    roster = _roster_provider().get_usdt_perp_roster(date(2026, 8, 29))
    # DEADUSDT exists ONLY in the archive — the whole point of using it.
    assert "DEADUSDT" in roster.usdt_perp_symbols
    assert roster.archive_only_symbols == ("DEADUSDT",)


def test_roster_is_the_union_so_a_brand_new_listing_is_not_lost():
    roster = _roster_provider().get_usdt_perp_roster(date(2026, 8, 29))
    assert "NEWUSDT" in roster.usdt_perp_symbols  # live-only, no archive yet
    assert "AAAUSDT" in roster.usdt_perp_symbols  # in both


def test_roster_excludes_tokenized_equity_perps_and_non_usdt_margin():
    roster = _roster_provider().get_usdt_perp_roster(date(2026, 8, 29))
    assert "TSLAUSDT" not in roster.usdt_perp_symbols
    assert roster.excluded_tradifi == ("TSLAUSDT",)
    assert "BTCUSDC" not in roster.usdt_perp_symbols
    assert "BBBUSDC" not in roster.usdt_perp_symbols
    assert roster.usdt_perp_symbols == ("AAAUSDT", "DEADUSDT", "NEWUSDT")


def test_roster_onboard_dates_are_metadata_only_and_never_the_gate():
    """onboardDate exists only for survivors, so it must not be what the
    universe is built from — this pins that it is carried for
    cross-checking and that the delisted contract simply has none."""
    roster = _roster_provider().get_usdt_perp_roster(date(2026, 8, 29))
    assert roster.onboard_dates["AAAUSDT"] == date(2021, 1, 1)
    assert "DEADUSDT" not in roster.onboard_dates


# --- end to end: breadth grows, and the decile spec starts trading -----------

N_EARLY = 30
N_LATE = 30
E2E_DAYS = 500
LATE_LISTING_ROW = 250


class _FakeProvider:
    """Serves pre-built panels through the provider's two data methods —
    the same shape build_funding_carry_panels consumes."""

    def __init__(self, klines: dict[str, pd.DataFrame], funding: dict[str, pd.DataFrame]) -> None:
        self._klines = klines
        self._funding = funding

    # The real provider's empty frames are DatetimeIndex-ed even when they
    # have no rows (a RangeIndex here would be a fake that is easier to
    # satisfy than production — see
    # test_provider_empty_frames_are_datetime_indexed_fresh_and_cached).
    EMPTY_KLINES = pd.DataFrame(
        {"close": pd.Series(dtype=float), "quote_volume": pd.Series(dtype=float)},
        index=pd.DatetimeIndex([]),
    )
    EMPTY_FUNDING = pd.DataFrame(
        {"funding_rate": pd.Series(dtype=float)}, index=pd.DatetimeIndex([])
    )

    def get_daily_klines(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return self._klines.get(symbol, self.EMPTY_KLINES)

    def get_funding_history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return self._funding.get(symbol, self.EMPTY_FUNDING)


def _e2e_provider() -> tuple[_FakeProvider, list[str]]:
    index = pd.date_range("2021-01-01", periods=E2E_DAYS, freq="D")
    klines: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    symbols: list[str] = []
    for i in range(N_EARLY + N_LATE):
        symbol = f"S{i:03d}USDT"
        symbols.append(symbol)
        late = i >= N_EARLY
        first_row = LATE_LISTING_ROW if late else 0
        own = index[first_row:]
        klines[symbol] = pd.DataFrame(
            {"close": 100.0, "quote_volume": 1e9}, index=own
        )
        # A distinct constant daily funding rate per contract, so the
        # cross-sectional ranking is well defined and prices are flat —
        # the return is then purely the harvested funding.
        rate = (i - (N_EARLY + N_LATE) / 2.0) * 1e-5
        funding[symbol] = pd.DataFrame({"funding_rate": rate}, index=own)
    return _FakeProvider(klines, funding), symbols


def test_end_to_end_new_listings_make_the_decile_spec_trade_again():
    """The mechanism the whole module is for: with a static roster the
    universe can only shrink, so a decile leg (which needs >= 50 eligible
    names for a leg of 5) eventually sits in cash forever. Here the
    universe DOUBLES mid-sample because new contracts list, and the decile
    specs go from skipping every formation to forming real books."""
    provider, symbols = _e2e_provider()
    config = FundingCarryConfig(formation_start=date(2021, 2, 15))
    summary = run_funding_carry_pit_screening(
        end=date(2022, 5, 15),
        provider=provider,  # type: ignore[arg-type]
        config=config,
        with_cross_venue_check=False,
        symbols=symbols,
    )

    assert summary.n_candidates == N_EARLY + N_LATE
    assert summary.n_with_data == N_EARLY + N_LATE
    # Breadth grows rather than decays — the defect being fixed.
    assert summary.min_eligible == N_EARLY
    assert summary.max_eligible == N_EARLY + N_LATE

    decile = {r.pattern_id: r for r in summary.results if r.pattern_id.endswith("_f10")}
    assert decile, "the four decile specs must be screened, not dropped"
    for result in decile.values():
        # Early formations skip (a leg of 3 from 30 names is below the
        # 5-name floor); later ones form books once breadth doubles.
        assert result.n_skipped_formations > 0
        assert result.n_formations > 0
        assert result.avg_names_per_leg >= 5.0


def test_end_to_end_results_carry_the_persistence_contract_and_the_family_key():
    provider, symbols = _e2e_provider()
    summary = run_funding_carry_pit_screening(
        end=date(2022, 5, 15),
        provider=provider,  # type: ignore[arg-type]
        config=FundingCarryConfig(formation_start=date(2021, 2, 15)),
        with_cross_venue_check=False,
        symbols=symbols,
    )
    assert FUNDING_CARRY_PIT_FAMILY_KEY == "funding_carry_pit"
    assert summary.n_trials == FUNDING_CARRY_N_TRIALS == 12
    assert len(summary.results) == 12
    for r in summary.results:
        assert r.pattern_id
        assert np.isfinite(r.sharpe_annualized)
        assert r.n_trading_days > 0
        # The DSR denominator is the pre-declared family size, never the
        # survivor count.
        assert r.deflated_sharpe.n_trials == 12
    assert summary.text.startswith("FUNDING-RATE CARRY, POINT-IN-TIME UNIVERSE")


def test_provider_empty_frames_are_datetime_indexed_fresh_and_cached(tmp_path):
    """REGRESSION, found by the independent verification pass 2026-08-29.

    Five real roster contracts serve funding while Binance 400s their
    klines, so the empty-frame path is production behaviour, not an edge
    case. It used to return a RangeIndex on the FRESH fetch and a
    DatetimeIndex on the CACHED read (_read_cache coerces). The
    disagreement was invisible behind a warm cache and fatal on a cold one:
    an int64 empty index poisons pd.concat's index union, the whole panel
    comes back object-indexed, and measure_breadth then dies on
    `index.year`. The funding-gap tripwire died even earlier, on `.dt`.

    Both shapes must be datetime-indexed, and the fresh and cached reads
    must agree — that agreement is the actual invariant."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(400, json={"code": -1122, "msg": "Invalid symbol status."})

    provider = BinanceFuturesProvider(
        cache_dir=tmp_path,
        sleep=lambda _s: None,
        clock=lambda: 0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler), base_url=FAPI_BASE_URL),
    )
    fresh_k = provider.get_daily_klines("GAIBUSDT", date(2026, 1, 1), date(2026, 8, 29))
    fresh_f = provider.get_funding_history("GAIBUSDT", date(2026, 1, 1), date(2026, 8, 29))
    assert calls, "the fresh path must actually have hit the transport"
    cached_k = provider.get_daily_klines("GAIBUSDT", date(2026, 1, 1), date(2026, 8, 29))
    cached_f = provider.get_funding_history("GAIBUSDT", date(2026, 1, 1), date(2026, 8, 29))

    for frame in (fresh_k, fresh_f, cached_k, cached_f):
        assert frame.empty
        assert isinstance(frame.index, pd.DatetimeIndex), f"{type(frame.index).__name__}"

    # The exact two operations that used to blow up on the fresh shape.
    assert fresh_f.index.to_series().diff().dt.total_seconds().empty
    good = pd.Series(1.0, index=pd.date_range("2021-01-01", periods=400, freq="D"))
    panel = pd.concat(
        {f"S{i}": good for i in range(60)} | {"GAIBUSDT": fresh_k["close"]}, axis=1
    ).sort_index()
    assert isinstance(panel.index, pd.DatetimeIndex)
    assert set(panel.index.year) == {2021, 2022}


def test_a_funding_only_contract_is_counted_as_a_hole_not_as_coverage():
    """REGRESSION, found by the independent verification pass 2026-08-29.

    Five of the 685 real roster contracts (GAIBUSDT on -1122; AERGOUSDT,
    BDXNUSDT, BTCSTUSDT, SXPUSDT on -1121) serve a full funding history
    while Binance refuses their klines outright. build_funding_carry_panels
    only reports a symbol in symbols_missing when BOTH feeds are empty, so
    such a contract silently becomes an all-NaN column — and the summary
    used to count it as a symbol that 'resolved real market data', which
    overstated coverage and hid a residual survivorship hole. n_with_data
    must count REAL MARKET DAYS, and the hole must be named."""
    provider, symbols = _e2e_provider()
    ghost = "GHOSTUSDT"
    # Exactly the real failure shape: klines refused, funding served.
    provider._klines[ghost] = _FakeProvider.EMPTY_KLINES
    provider._funding[ghost] = pd.DataFrame(
        {"funding_rate": 1e-4},
        index=pd.date_range("2021-01-01", periods=E2E_DAYS, freq="D"),
    )
    summary = run_funding_carry_pit_screening(
        end=date(2022, 5, 15),
        provider=provider,  # type: ignore[arg-type]
        config=FundingCarryConfig(formation_start=date(2021, 2, 15)),
        with_cross_venue_check=False,
        symbols=[*symbols, ghost],
    )

    assert summary.n_candidates == N_EARLY + N_LATE + 1
    # It is a column (it resolved funding) but it is NOT market data.
    assert summary.n_with_data == N_EARLY + N_LATE
    assert summary.n_klines_absent == 1
    assert summary.klines_absent_symbols == [ghost]
    assert ghost in summary.text
    assert any(ghost in w for w in summary.warnings)


def test_breadth_table_reports_first_and_last_eligibility_years():
    _provider, symbols = _e2e_provider()
    index = pd.date_range("2021-01-01", periods=E2E_DAYS, freq="D")
    close = pd.DataFrame(
        {s: pd.Series(100.0, index=index[LATE_LISTING_ROW if i >= N_EARLY else 0 :])
         for i, s in enumerate(symbols)}
    )
    volume = close.notna().astype(float) * 1e9
    eligibility = build_pit_eligibility(close, volume)
    rows = measure_breadth(eligibility, date(2021, 2, 15), static_symbols=set(symbols[:N_EARLY]))
    assert [r.year for r in rows] == [2021, 2022]
    # The late contracts first become eligible in the year the listing row
    # falls in; nothing has stopped being eligible by the panel's end.
    assert sum(r.n_first_eligible for r in rows) == N_EARLY + N_LATE
    # The static-subset column stays flat while the full universe grows —
    # the exact contrast the real run reports.
    assert rows[-1].static_mean_eligible == pytest.approx(float(N_EARLY))
    assert rows[-1].mean_eligible > rows[0].mean_eligible
