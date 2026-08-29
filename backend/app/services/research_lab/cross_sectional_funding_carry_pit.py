"""The funding-rate carry family re-run on a POINT-IN-TIME UNIVERSE: the
same 12 pre-declared specs, the same signal, the same cost model and the
same never-pooled DSR denominator as cross_sectional_funding_carry.py,
with exactly one thing changed — which contracts are candidates on each
formation date.

WHY THIS MODULE EXISTS. The parent family's own adversarial verification
(2026-08-29, quoted in its docstring) found its headline positive did not
survive scrutiny, for two combined reasons:
  (1) UNIVERSE DECAY. The candidate list was a STATIC 73-coin roster
      hand-assembled in 2026 and applied uniformly across 2019-2026. Dead
      names leave it as they delist; new listings never join. Eligible
      breadth therefore decayed 66 -> 27 (yearly means 2021 59.6 ... 2026
      31.4) for mechanical reasons, and the best spec — a decile cutoff
      needing >= 50 eligible names — had been 100% IN CASH since 2025-03.
      Its full-sample Sharpe contained ~18 months of structural zeros.
  (2) EDGE DECAY. Every spec that could still form a book lost 34-47% in
      2026, matching what both cited papers predict (BIS WP 1087's
      spot-ETF carry compression, ~36% of the mean; Christin et al.'s own
      "the Sharpe ratios are much smaller in the later part of the
      sample").
The verification's recommended legitimate next step was to fix (1) — and
ONLY (1) — as a new pre-declared family, rather than picking a different
"best" spec on exhausted backward data, which would be the post-hoc
selection this project's methodology forbids. THIS MODULE IS THAT FIX.
It is NOT expected to repair (2): a real decay in the premium itself is
not a data-construction artefact and no universe change can undo it. A
continued honest negative is the anticipated outcome and is reported as
such.

================================================================================
THE DATA THAT MAKES A POINT-IN-TIME UNIVERSE POSSIBLE — VERIFIED LIVE
================================================================================
Two rosters, because neither alone is survivorship-free (every count
below was fetched live 2026-08-29; see BinanceFuturesProvider's docstring
for the endpoint mechanics):
  * /fapi/v1/exchangeInfo serves 654 USDT-quoted contractType=PERPETUAL
    symbols with an `onboardDate` each — but it is SURVIVOR-ONLY:
    SRMUSDT and LUNAUSDT are absent from it entirely, even though their
    funding and kline history is still served. Building a universe from
    exchangeInfo alone would delete every contract that died, which is
    the classic survivorship bias and strictly worse than the static list
    it replaces.
  * data.binance.vision's S3 listing of
    data/futures/um/monthly/fundingRate/ enumerates 833 USDT-quoted
    symbol directories — every UM perp that ever had a funding archive,
    delisted ones included (SRMUSDT, LUNAUSDT, FTTUSDT, COCOSUSDT and the
    BUSD-era pairs are all present). Only perpetuals pay funding, so a
    fundingRate directory IS the marker of an ever-listed perp.
The candidate roster is the UNION of the two (the archive lags the live
roster by a name or two), MINUS contractType=TRADIFI_PERPETUAL — the 180
tokenized-equity/metals perps (XAUUSDT, TSLAUSDT, ...) Binance onboarded
from 2025-12-11 onward. Those are a different asset class, and letting
them into a crypto carry family in the last nine months of the sample
would change what is being measured; the exclusion is by contract type,
is time-invariant, and is stated here rather than discovered later.
Result: 685 candidate contracts against the parent family's 73.

INCEPTION AND DELISTING COME FROM THE DATA, NOT FROM A LIST. exchangeInfo's
`onboardDate` exists only for still-listed symbols, so using it would
smuggle the survivorship hole back in through the date field. Instead each
symbol's listing window is measured from ITS OWN earliest and latest real
market day in the kline panel — a real market meaning a finite close on
strictly positive quote turnover, the parent family's existing
market-or-not rule (a delisted perp keeps printing zero-volume bars; those
are quotes, not markets). Funding-feed first/last dates are carried
alongside as a cross-check and reported, not used as the gate.

================================================================================
WHAT "POINT-IN-TIME CORRECT" MEANS HERE, AND WHY IT CANNOT LEAK
================================================================================
pit_universe_asof(close, day) reads close.loc[:day] and NOTHING ELSE. It
returns the symbols that
  (a) have had at least one real market day on or before `day` — they had
      actually started trading by then, so a 2026 listing cannot appear in
      a 2021 cross-section; and
  (b) have at least one real market day in the trailing
      FUNDING_LIQUIDITY_WINDOW_DAYS ending at `day` — they have not
      stopped trading as of that date, so a contract delisted in 2022
      cannot appear in a 2023 cross-section.
Both clauses are computable by an observer standing on `day`. Neither can
consult a future row, because there are no future rows in the slice. The
matrix form (build_pit_membership) is a vectorized restatement —
`priced.cummax() & priced.rolling(window, min_periods=1).max()` — and a
test asserts it agrees with the as-of function row for row on a synthetic
panel with a known inception and a known delisting, which is the property
that would silently break if a future-looking operation ever crept in.

The liveness window is FUNDING_LIQUIDITY_WINDOW_DAYS (30) REUSED, not a
new knob: the parent family's turnover gate already needs 20 turnover
observations inside a 30-day rolling window, so a contract that has been
dead for 30 days is already ineligible there. Which is the honest headline
of this whole exercise:

    THE PARENT FAMILY'S ELIGIBILITY GATE WAS ALREADY POINT-IN-TIME AT THE
    SYMBOL LEVEL. Its defect was never the gate; it was the ROSTER the
    gate was applied to. The explicit membership mask below is therefore
    deliberately redundant with that gate — it exists to be TESTABLE and
    auditable, and a test asserts that ANDing it in never adds a name the
    gate alone would have rejected. The measurable change in this module
    is 685 candidates instead of 73.

================================================================================
WHAT IS DELIBERATELY IDENTICAL TO THE PARENT FAMILY
================================================================================
Not re-implemented — IMPORTED, so a methodology drift is impossible:
build_funding_carry_family (the same 12 specs, the same assertions),
funding_carry_signal, build_funding_eligibility, run_funding_carry_backtest,
screen_funding_carry_family, FundingCarryConfig, FUNDING_CARRY_N_TRIALS=12,
FUNDING_CARRY_COST_BPS=10, FUNDING_CARRY_MIN_NAMES_PER_LEG=5,
FUNDING_CARRY_FORMATION_START=2020-10-01, periods_per_year=365. The parent
module gained exactly two default-preserving seams for this (a `symbols`
argument on build_funding_carry_panels and an injectable `eligibility` on
screen_funding_carry_family); nothing else about it changed, and its own
persisted results are untouched — this family persists under its own
family_key, FUNDING_CARRY_PIT_FAMILY_KEY.

RESIDUAL LIMITATIONS, disclosed rather than discovered later:
  * The archive listing is Binance's own and is assumed complete for UM
    perps. A contract that both left exchangeInfo AND never got a monthly
    funding archive would be invisible to both sources. No such case was
    found, and none can be ruled out from outside Binance.
  * FIVE roster contracts have a funding history but no klines Binance
    will serve (the -1121/-1122 table above). The roster is
    survivorship-clean; the PRICE FEED is not, for those five. They are
    silently absent from every cross-section and no construction in this
    module can recover them.
  * Every other caveat of the parent family still applies in full:
    single-venue funding (Binance only, measured 8-61% richer than
    Gate.io/KuCoin), 10bp assumed one-way cost, and the four unmodelled
    risks (exchange bankruptcy, liquidation spirals, funding caps binding
    in a crisis, USDT depeg).
  * This family widens the roster to ~9x the parent's. That admits many
    smaller, newer, thinner alt perps than the parent's majors-heavy list
    behind the SAME $10M/day turnover gate and the SAME 10bp cost
    assumption. 10bp was sized for liquid perps; on the long tail it is
    more likely optimistic than conservative. Breakeven costs are reported
    per spec for exactly this reason, and the summary says so.

================================================================================
RESULTS — REAL RUN 2026-08-29, run_tag funding_carry_pit_universe_2026-08-29
================================================================================
Panel 2019-09-08 .. 2026-08-29 (2548 rows), formations from 2020-10-01,
2158 return days per spec. 685 candidate contracts; 680 resolved at least
one real kline market day; 662 passed the $10M/day turnover gate on at
least one formation-window day. Persisted under family_key
funding_carry_pit; the parent family's three run_tags are untouched.

FIVE candidates, not one, are all-NaN columns — corrected here by the
independent verification pass 2026-08-29, which measured every one of
them live against /fapi/v1/klines rather than inferring:
    GAIBUSDT    HTTP 400 / -1122 "Invalid symbol status"   871 funding events
    AERGOUSDT   HTTP 400 / -1121 "Invalid symbol."        4360 funding events
    BDXNUSDT    HTTP 400 / -1121 "Invalid symbol."        2461 funding events
    BTCSTUSDT   HTTP 400 / -1121 "Invalid symbol."        5811 funding events
    SXPUSDT     HTTP 400 / -1121 "Invalid symbol."        6156 funding events
Each has a full funding history — thousands of settlements, so each WAS a
listed perp for years — and Binance simply will not serve its klines, with
or without a time range. Since this family's market-or-not rule is a
finite close on positive turnover, all five are excluded on every date.
That is a REAL RESIDUAL SURVIVORSHIP HOLE (4 dead contracts and 1 live
one), not a roster miss: the roster found them, the price feed does not
exist. It is small (5 of 685, none of them majors) and it cannot be closed
from outside Binance, but it is stated because the alternative is a
coverage number that quietly counts an all-NaN column as data. The
summary's n_with_data now counts real market days, and n_klines_absent
names these five.

1. THE UNIVERSE DEFECT IS FIXED — BREADTH IS NOW REAL. Mean eligible
   names per day, point-in-time roster vs the IDENTICAL panel and gate
   restricted to the parent family's 73 static names:
       year   PIT    static(73)
       2020    42.0    34.6
       2021   103.0    59.6
       2022   124.6    63.0
       2023   140.8    59.0
       2024   195.9    53.5
       2025   205.5    44.3
       2026   117.9    31.3
   The static column is the mechanical decay the verification found
   (66 -> 27). The PIT column grows roughly 5x from 2020 to 2025 as new
   contracts list, because they can now arrive at all.

2. THE PREVIOUSLY-100%-CASH SPEC TRADES AGAIN. xf_carry_w30_h7_f10 — the
   parent family's headline spec, in cash since 2025-03 because a decile
   leg of 5 needs >= 50 eligible names — now forms 295 books and skips 14.
   Every one of those 14 skips is at the very START of the sample
   (2020-10-01 .. 2021-01-07), when breadth was genuinely thin; ZERO
   formations are skipped on or after 2025-03-01, where it forms 78 books
   at an average leg of 15.7 names. All six f10 specs behave the same way.
   The structural zeros are gone.

3. AND THE HONEST RESULT IS WORSE, NOT BETTER. Removing the cash padding
   removes the number it was inflating:
       xf_carry_w30_h7_f20   +0.308   DSR 0.281
       xf_carry_w7_h7_f20    +0.280   DSR 0.260
       xf_carry_w14_h7_f20   +0.241   DSR 0.230
       xf_carry_w7_h7_f10    +0.186   DSR 0.192
       xf_carry_w30_h7_f10   +0.120   DSR 0.150   <- the parent's +0.812
       xf_carry_w14_h7_f10   +0.021   DSR 0.101
       xf_carry_w7_h30_f20   -0.108   DSR 0.056
       xf_carry_w14_h30_f20  -0.215   DSR 0.032
       xf_carry_w30_h30_f20  -0.397   DSR 0.011
       xf_carry_w14_h30_f10  -0.465   DSR 0.007
       xf_carry_w7_h30_f10   -0.529   DSR 0.005
       xf_carry_w30_h30_f10  -0.536   DSR 0.004
   Family median Sharpe -0.044 (the parent family's was positive); 6 of 12
   positive; best DSR 0.281 against the parent's 0.761, which this project
   had ALREADY rejected as insufficient. The parent's headline spec falls
   from +0.812 to +0.120 once it has to hold a real book instead of cash.

4. THE DECAY (gap 2) IS UNTOUCHED AND NOW UNCONFOUNDED — which is the
   point. Net return by calendar year, across all 12 specs:
       2024:  3/12 positive, -48.3% .. +29.5%
       2025:  1/12 positive, -78.4% .. +35.3%
       2026:  0/12 positive, -88.3% .. -53.8%
   2026 is negative for EVERY spec on a universe averaging 118 eligible
   names and legs of 15-28. Under the static roster this collapse could be
   waved away as thin breadth; it cannot be now. Three consecutive
   deteriorating years on a healthy cross-section is what both cited
   papers predict (BIS WP 1087's spot-ETF carry compression; Christin et
   al.'s "much smaller in the later part of the sample").

5. THE FUNDING IS STILL BEING HARVESTED — THE PRICE LEG EATS IT. Every
   spec's attribution is a large positive funding component against a
   large negative price component (e.g. xf_carry_w30_h7_f20: +289.5%
   funding, -182.2% price, -29.9% costs, +77.4% net). The mechanism is
   real and is doing exactly what the papers say it does: the carry is
   compensation for the price risk of the spread, not free money. A
   reader who sees only the Sharpe would miss that the strategy harvested
   what it was supposed to and still lost most of it back.

6. COSTS. Breakevens for the six positive specs run 11.5-35.9bp one-way
   against the assumed 10bp. On a roster 9x wider than the parent's —
   admitting far thinner alt perps — 10bp is more likely optimistic than
   conservative, so the positive half of the family has little headroom.

DISCLOSED DATA-FRESHNESS BLEMISH, measured not waved away: the panel's
final row (2026-08-29) is ragged. 468 contracts were fetched at ~01:30
UTC that day, so their 2026-08-29 bar is a PARTIAL day; 56 contracts
(the parent family's earlier cache, legitimately reused inside
CACHE_FRESH_DAYS=3) stop at 2026-08-28 and are NaN on it. This is why the
static-73 subset reads 0 eligible on 2026-08-29 specifically — a cache
artifact, NOT a finding. Re-screening on the panel truncated to the last
complete UTC day (2026-08-28) was RUN, not assumed: every spec's Sharpe
moves by at most 0.0066 (largest: xf_carry_w14_h30_f10, -0.00655), and
all 12 deltas are NEGATIVE, so the numbers
reported above are marginally generous rather than flattered by the
artifact. No conclusion depends on that row.

VERDICT: the universe fix works and is worth keeping — it is the
methodologically correct construction and it removes a real distortion.
It does NOT rescue the strategy. It does the opposite: with structural
zeros removed the family median is negative, the best DSR is 0.281, and
2026 is negative across all 12 specs on genuinely broad breadth. This is
a CLEAN HONEST NEGATIVE, and a more credible one than the parent
family's, because the decay can no longer be attributed to a shrinking
roster. NO forward-validation registration is made and none is
recommended: there is nothing here to register. The remaining open
question this run does NOT answer — whether a delta-neutral
(short-perp/long-spot) construction like the papers' own trade survives
where this dollar-neutral cross-sectional one does not — is a different
family and would need its own pre-declaration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.services.market_data.binance_futures_provider import (
    BinanceFuturesProvider,
    PerpRoster,
)
from app.services.research_lab.cross_sectional_crypto import (
    CryptoFactorExposure,
    compute_crypto_factor_exposure,
)
from app.services.research_lab.cross_sectional_funding_carry import (
    FUNDING_CARRY_COST_BPS,
    FUNDING_CARRY_DATA_START,
    FUNDING_CARRY_N_TRIALS,
    FUNDING_CARRY_UNIVERSE,
    FUNDING_LIQUIDITY_WINDOW_DAYS,
    FUNDING_MIN_QUOTE_VOLUME,
    CrossVenueCheckRow,
    FundingCarryConfig,
    FundingCarryPanels,
    FundingCarrySpecResult,
    FundingCoverage,
    build_funding_carry_family,
    build_funding_carry_panels,
    build_funding_eligibility,
    cross_venue_funding_check,
    default_funding_carry_config,
    screen_funding_carry_family,
)

logger = logging.getLogger(__name__)

FUNDING_CARRY_PIT_FAMILY_KEY = "funding_carry_pit"

# The trailing window a contract must have shown at least one real market
# day in to count as still listed. REUSED from the parent family's
# turnover gate (30 days) rather than introduced as a new tunable — see
# the module docstring's note on why this mask is redundant on purpose.
PIT_LIVENESS_WINDOW_DAYS = FUNDING_LIQUIDITY_WINDOW_DAYS


# --- symbol lifetimes --------------------------------------------------------


@dataclass(frozen=True)
class SymbolLifetime:
    """One contract's measured listing window. `first_traded` /
    `last_traded` come from the contract's own klines (finite close on
    strictly positive turnover); the funding dates are a cross-check the
    summary reports, never the gate. `still_listed` means the contract's
    last real market day IS the panel's last row — it has not stopped, as
    far as this panel can tell."""

    symbol: str
    first_traded: date | None
    last_traded: date | None
    first_funding: date | None
    last_funding: date | None
    still_listed: bool
    n_market_days: int = 0


def measure_symbol_lifetimes(
    close: pd.DataFrame, coverage: dict[str, FundingCoverage] | None = None
) -> dict[str, SymbolLifetime]:
    """Each column's listing window, measured from the panel itself.

    A column with no real market day anywhere gets first/last None — it is
    a contract this project's market-or-not rule never saw trade, and
    pit_universe_asof excludes it on every date."""
    coverage = coverage or {}
    panel_end = close.index[-1] if len(close.index) else None
    lifetimes: dict[str, SymbolLifetime] = {}
    for symbol in close.columns:
        priced = close[symbol].dropna()
        first = priced.index[0].date() if len(priced) else None
        last = priced.index[-1].date() if len(priced) else None
        cov = coverage.get(symbol)
        lifetimes[symbol] = SymbolLifetime(
            symbol=symbol,
            first_traded=first,
            last_traded=last,
            first_funding=cov.first_funding if cov else None,
            last_funding=cov.last_funding if cov else None,
            still_listed=bool(len(priced) and panel_end is not None and priced.index[-1] == panel_end),
            n_market_days=len(priced),
        )
    return lifetimes


# --- the point-in-time universe ----------------------------------------------


def pit_universe_asof(
    close: pd.DataFrame,
    day: pd.Timestamp | date,
    liveness_window_days: int = PIT_LIVENESS_WINDOW_DAYS,
) -> list[str]:
    """THE point-in-time universe as of `day`, computed from
    close.loc[:day] and nothing else.

    A contract is in it when it has (a) at least one real market day on or
    before `day` — it had actually listed by then — and (b) at least one
    real market day in the `liveness_window_days` rows ending at `day` — it
    had not already stopped trading. Sorted, so a caller's downstream
    ranking is deterministic.

    THE LOOK-AHEAD ARGUMENT, which is the whole point of this function
    existing separately from the vectorized mask: the slice physically
    contains no row after `day`, so no future information — which
    contracts survive, which delist next month, which list next year — is
    reachable from inside it. A test asserts that truncating the panel at
    `day` before calling this changes nothing, on a synthetic panel with a
    known inception date and a known delisting date."""
    stamp = pd.Timestamp(day)
    history = close.loc[:stamp]
    if history.empty:
        return []
    priced = history.notna()
    listed = priced.any(axis=0)
    alive = priced.iloc[-liveness_window_days:].any(axis=0)
    return sorted(map(str, priced.columns[(listed & alive).to_numpy()]))


def build_pit_membership(
    close: pd.DataFrame, liveness_window_days: int = PIT_LIVENESS_WINDOW_DAYS
) -> pd.DataFrame:
    """The whole-panel boolean form of pit_universe_asof: (dates x
    symbols), True where the contract was in the point-in-time universe on
    that date.

    `cummax()` is "has traded at or before this row" and
    `rolling(window, min_periods=1).max()` is "has traded within the
    trailing window ending at this row" — both are causal by construction
    (pandas' expanding/rolling reductions read backwards only). A test
    asserts this agrees with pit_universe_asof row for row, so the
    vectorization can never silently diverge from the auditable
    definition."""
    if close.empty:
        return pd.DataFrame(index=close.index, columns=close.columns, dtype=bool)
    priced = close.notna()
    listed = priced.cummax()
    alive = priced.rolling(liveness_window_days, min_periods=1).max().fillna(0.0).astype(bool)
    return (listed & alive).astype(bool)


def build_pit_eligibility(
    close: pd.DataFrame,
    quote_volume: pd.DataFrame,
    liveness_window_days: int = PIT_LIVENESS_WINDOW_DAYS,
) -> pd.DataFrame:
    """The parent family's eligibility gate AND the point-in-time
    membership mask.

    Deliberately redundant — the gate's 30-day/20-observation turnover
    rolling window already refuses a contract that has not traded — and
    deliberately kept anyway, so "is this universe point-in-time?" is a
    question about one named, tested function rather than an emergent
    property of a rolling median. A test asserts the AND never removes a
    name the gate alone accepted (i.e. the redundancy claim is measured,
    not asserted)."""
    return (
        build_funding_eligibility(close, quote_volume)
        & build_pit_membership(close, liveness_window_days)
    ).astype(bool)


# --- breadth diagnostics -----------------------------------------------------


@dataclass
class BreadthYear:
    """One calendar year of measured universe breadth — the number the
    parent family's verification found decaying for mechanical reasons.
    `static_mean_eligible` restricts the IDENTICAL panel and gate to the
    parent family's 73 static symbols, so the two columns are an
    apples-to-apples comparison rather than a comparison across runs."""

    year: int
    mean_eligible: float
    min_eligible: int
    max_eligible: int
    n_first_eligible: int  # contracts eligible for the first time this year
    n_last_eligible: int  # contracts eligible for the last time ever this year
    static_mean_eligible: float


def measure_breadth(
    eligibility: pd.DataFrame,
    formation_start: date,
    static_symbols: set[str],
) -> list[BreadthYear]:
    in_window = eligibility.loc[eligibility.index >= pd.Timestamp(formation_start)]
    if in_window.empty:
        return []
    counts = in_window.sum(axis=1)
    static_cols = [c for c in in_window.columns if c in static_symbols]
    static_counts = in_window[static_cols].sum(axis=1)

    first_seen: dict[str, int] = {}
    last_seen: dict[str, int] = {}
    for symbol in in_window.columns:
        flags = in_window[symbol]
        on = flags.index[flags.to_numpy()]
        if len(on):
            first_seen[symbol] = int(on[0].year)
            last_seen[symbol] = int(on[-1].year)

    years = sorted({int(ts.year) for ts in in_window.index})
    rows: list[BreadthYear] = []
    for year in years:
        mask = in_window.index.year == year
        rows.append(
            BreadthYear(
                year=year,
                mean_eligible=float(counts[mask].mean()),
                min_eligible=int(counts[mask].min()),
                max_eligible=int(counts[mask].max()),
                n_first_eligible=sum(1 for y in first_seen.values() if y == year),
                n_last_eligible=sum(1 for y in last_seen.values() if y == year),
                static_mean_eligible=float(static_counts[mask].mean()),
            )
        )
    return rows


# --- summary -----------------------------------------------------------------


@dataclass
class FundingCarryPitScreeningSummary:
    results: list[FundingCarrySpecResult]
    n_trials: int
    periods_per_year: float
    panel_start: date | None
    panel_end: date | None
    n_panel_rows: int
    formation_start: date
    roster: PerpRoster | None
    n_candidates: int
    # Contracts with at least one REAL MARKET DAY (finite close on positive
    # turnover) somewhere in the panel — NOT the column count. A contract
    # whose funding archive survives but whose klines Binance no longer
    # serves is an all-NaN column: it is a candidate, it is not data, and
    # conflating the two would overstate coverage. `n_klines_absent` /
    # `klines_absent_symbols` are exactly those, disclosed rather than
    # absorbed (see the module docstring's residual-limitations note).
    n_with_data: int
    n_ever_eligible: int
    n_klines_absent: int = 0
    klines_absent_symbols: list[str] = field(default_factory=list)
    breadth: list[BreadthYear] = field(default_factory=list)
    lifetimes: dict[str, SymbolLifetime] = field(default_factory=dict)
    min_eligible: int = 0
    median_eligible: float = 0.0
    max_eligible: int = 0
    factor_exposures: dict[str, CryptoFactorExposure] = field(default_factory=dict)
    cross_venue: list[CrossVenueCheckRow] = field(default_factory=list)
    yearly_returns: dict[str, dict[int, float]] = field(default_factory=dict)
    text: str = ""
    warnings: list[str] = field(default_factory=list)


def _build_summary_text(summary: FundingCarryPitScreeningSummary) -> str:
    roster = summary.roster
    lines = [
        (
            f"FUNDING-RATE CARRY, POINT-IN-TIME UNIVERSE — the parent family's 12 pre-declared "
            f"specs with ONE thing changed: the candidate roster. Pre-declared family size "
            f"{summary.n_trials} (3 funding windows x 2 holds x 2 cutoffs), used as the DSR's "
            f"n_trials in this family's own never-pooled screening. Signal, cost model "
            f"({FUNDING_CARRY_COST_BPS}bp one-way), turnover gate "
            f"(${FUNDING_MIN_QUOTE_VOLUME:,.0f}/day trailing median, shift(1)), holding rules and "
            f"periods_per_year={summary.periods_per_year:.0f} are IMPORTED from "
            f"cross_sectional_funding_carry.py, not re-implemented."
        ),
        (
            f"UNIVERSE: {summary.n_candidates} ever-listed USDT-margined crypto perps "
            + (
                f"({len(roster.live_symbols)} in exchangeInfo today, "
                f"{len(roster.archive_only_symbols)} known ONLY from Binance's own data archive "
                f"because they delisted and left exchangeInfo entirely, "
                f"{len(roster.excluded_tradifi)} tokenized-equity/metals perps excluded by "
                f"contract type) "
                if roster is not None
                else ""
            )
            + f"against the parent family's {len(set(FUNDING_CARRY_UNIVERSE.values()))} static "
            f"hand-assembled names. {summary.n_with_data} resolved at least one real market day"
            + (
                f"; {summary.n_klines_absent} did NOT — Binance still serves their funding "
                f"archive but answers HTTP 400 on their klines, so they are all-NaN columns the "
                f"universe excludes on every date, a residual survivorship hole this family "
                f"cannot close from outside Binance "
                f"({', '.join(summary.klines_absent_symbols)})"
                if summary.n_klines_absent
                else ""
            )
            + f". {summary.n_ever_eligible} were eligible on at least one formation-window day. "
            f"Each contract's listing window is measured from ITS OWN first and last real market "
            f"day (finite close, positive turnover) — never from exchangeInfo's onboardDate, "
            f"which exists only for survivors."
        ),
        (
            f"PANEL: {summary.n_panel_rows} rows ({summary.panel_start} .. {summary.panel_end}); "
            f"formations from {summary.formation_start}. Eligible names per formation day: "
            f"{summary.min_eligible}..{summary.max_eligible}, median {summary.median_eligible:.0f}."
        ),
    ]

    if summary.breadth:
        lines.append(
            "BREADTH BY YEAR (mean eligible names per day; 'static' is the IDENTICAL panel and "
            "gate restricted to the parent family's 73-name list — the decay the verification "
            "found):"
        )
        for b in summary.breadth:
            lines.append(
                f"  {b.year}: PIT mean {b.mean_eligible:5.1f} (min {b.min_eligible}, max "
                f"{b.max_eligible}) vs static mean {b.static_mean_eligible:5.1f} | "
                f"{b.n_first_eligible} first-eligible, {b.n_last_eligible} last-ever-eligible"
            )

    if summary.results:
        lines.append("PER-SPEC RESULTS (net of turnover cost; attribution gross):")
        for r in sorted(summary.results, key=lambda x: -x.sharpe_annualized):
            dsr = r.deflated_sharpe.dsr
            net = r.total_price_pnl + r.total_funding_pnl - r.total_cost_drag
            breakeven = ""
            if r.sharpe_annualized > 0 and r.total_cost_drag > 0:
                gross = net + r.total_cost_drag
                breakeven_bps = FUNDING_CARRY_COST_BPS * gross / r.total_cost_drag
                breakeven = f", breakeven ~{breakeven_bps:.1f}bp one-way"
            lines.append(
                f"  {r.pattern_id}: Sharpe {r.sharpe_annualized:+.3f}, DSR "
                f"{'n/a' if dsr is None else format(dsr, '.3f')}, {r.n_formations} formations "
                f"({r.n_skipped_formations} skipped), avg leg {r.avg_names_per_leg:.1f} | "
                f"cumulative net {net:+.2%} = price {r.total_price_pnl:+.2%} + funding "
                f"{r.total_funding_pnl:+.2%} - costs {r.total_cost_drag:.2%}{breakeven}"
            )

    if summary.yearly_returns:
        lines.append("YEARLY NET RETURN BY SPEC (the decay check the universe fix does NOT address):")
        years = sorted({y for per in summary.yearly_returns.values() for y in per})
        lines.append("  " + "spec".ljust(24) + "".join(str(y).rjust(9) for y in years))
        for pattern_id in sorted(summary.yearly_returns):
            per = summary.yearly_returns[pattern_id]
            cells = "".join(
                (f"{per[y]:+.1%}".rjust(9) if y in per else "—".rjust(9)) for y in years
            )
            lines.append("  " + pattern_id.ljust(24) + cells)

    if summary.cross_venue:
        lines.append(
            "CROSS-VENUE SANITY CHECK (daily-summed funding vs Binance, trailing window; a "
            "reasonableness check, NOT a cross-venue study):"
        )
        for row in summary.cross_venue:
            if row.note:
                lines.append(f"  {row.venue} {row.venue_symbol}: {row.note}")
            else:
                lines.append(
                    f"  {row.venue} {row.venue_symbol}: corr {row.daily_sum_correlation:.3f} over "
                    f"{row.n_days_compared} days; mean daily funding binance "
                    f"{row.mean_daily_binance:+.5%} vs {row.venue} {row.mean_daily_venue:+.5%}"
                )

    lines.append(
        "COST CAVEAT SPECIFIC TO THIS VARIANT: a ~9x wider roster admits far thinner alt perps "
        f"than the parent family's majors, behind the same {FUNDING_CARRY_COST_BPS}bp one-way "
        "assumption — which was sized for liquid perps and is therefore more likely optimistic "
        "than conservative here. Read the per-spec breakevens above as the load-bearing number. "
        "NOT MODELED, unchanged from the parent family: exchange-bankruptcy risk, "
        "liquidation/margin spirals, funding caps binding in a crisis, USDT depeg."
    )
    if summary.warnings:
        lines.append("WARNINGS: " + " | ".join(summary.warnings))
    return "\n".join(lines)


# --- production entry point --------------------------------------------------


def run_funding_carry_pit_screening(
    end: date | None = None,
    provider: BinanceFuturesProvider | None = None,
    config: FundingCarryConfig | None = None,
    with_cross_venue_check: bool = True,
    symbols: list[str] | None = None,
) -> FundingCarryPitScreeningSummary:
    """THE production entry point for the point-in-time-universe variant.

    Discovers the ever-listed roster, builds the identical panels over it,
    replays the identical 12 specs against the point-in-time eligibility,
    and DSR-corrects at the identical n_trials=12. `symbols` overrides the
    discovered roster (tests only) — production passes nothing and lets
    the roster be discovered, because a hand-passed list is precisely the
    thing this module exists to stop doing.

    Persistence stays a separate explicit call
    (persist_cross_sectional_trial_results with
    FUNDING_CARRY_PIT_FAMILY_KEY), per that module's contract."""
    end = end if end is not None else date.today()  # noqa: DTZ011 — fetch end bound only
    provider = provider if provider is not None else BinanceFuturesProvider()
    config = config if config is not None else default_funding_carry_config()

    warnings: list[str] = []
    roster: PerpRoster | None = None
    if symbols is None:
        roster = provider.get_usdt_perp_roster(end)
        candidates = list(roster.usdt_perp_symbols)
    else:
        candidates = list(symbols)

    panels: FundingCarryPanels = build_funding_carry_panels(
        provider, end, FUNDING_CARRY_DATA_START, symbols=candidates
    )
    if panels.close.empty:
        summary = FundingCarryPitScreeningSummary(
            results=[],
            n_trials=FUNDING_CARRY_N_TRIALS,
            periods_per_year=config.periods_per_year,
            panel_start=None,
            panel_end=None,
            n_panel_rows=0,
            formation_start=config.formation_start,
            roster=roster,
            n_candidates=len(candidates),
            n_with_data=0,
            n_ever_eligible=0,
            warnings=["No Binance perp data resolved — nothing was screened."],
        )
        summary.text = _build_summary_text(summary)
        return summary

    close = panels.close
    lifetimes = measure_symbol_lifetimes(close, panels.coverage)
    eligibility = build_pit_eligibility(close, panels.quote_volume)

    in_window = eligibility.loc[eligibility.index >= pd.Timestamp(config.formation_start)]
    counts = in_window.sum(axis=1)
    ever_eligible = int(in_window.any(axis=0).sum())

    specs = build_funding_carry_family()
    results, daily_by_pattern = screen_funding_carry_family(panels, specs, config, eligibility)

    btc = close["BTCUSDT"].pct_change(fill_method=None) if "BTCUSDT" in close else pd.Series(dtype=float)
    basket = close.pct_change(fill_method=None).where(eligibility).mean(axis=1, skipna=True)
    exposures = {
        pattern_id: compute_crypto_factor_exposure(
            pattern_id, series, btc.reindex(series.index), basket.reindex(series.index)
        )
        for pattern_id, series in daily_by_pattern.items()
    }
    yearly = {
        pattern_id: {
            int(year): float(np.prod(1.0 + group.to_numpy()) - 1.0)
            for year, group in series.groupby(series.index.year)
        }
        for pattern_id, series in daily_by_pattern.items()
    }

    cross_venue: list[CrossVenueCheckRow] = []
    if with_cross_venue_check:
        cross_venue = cross_venue_funding_check(provider)

    # A column is a CANDIDATE that resolved something; a column with a real
    # market day is DATA. The two differ for contracts whose funding
    # archive survives while their klines 400 permanently, and reporting
    # the column count as "resolved data" would overstate coverage and
    # hide a residual survivorship hole. Measured from the panel, not from
    # symbols_missing (which only catches symbols that resolved NOTHING).
    klines_absent = sorted(str(s) for s in close.columns[~close.notna().any(axis=0).to_numpy()])
    n_with_market_data = len(close.columns) - len(klines_absent)
    if klines_absent:
        warnings.append(
            f"{len(klines_absent)} roster contract(s) have a funding history but NO kline data "
            f"Binance will serve ({', '.join(klines_absent)}) — all-NaN columns, excluded on "
            f"every date. Their funding archives prove they were listed perps, so this is a "
            f"residual survivorship hole, not an empty roster entry."
        )

    static_symbols = set(FUNDING_CARRY_UNIVERSE.values())
    missing_static = sorted(static_symbols - set(close.columns))
    if missing_static:
        warnings.append(
            f"{len(missing_static)} of the parent family's static names resolved no data in this "
            f"panel ({', '.join(missing_static)}) — the static comparison column excludes them."
        )

    summary = FundingCarryPitScreeningSummary(
        results=results,
        n_trials=FUNDING_CARRY_N_TRIALS,
        periods_per_year=config.periods_per_year,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        n_panel_rows=len(close),
        formation_start=config.formation_start,
        roster=roster,
        n_candidates=len(candidates),
        n_with_data=n_with_market_data,
        n_ever_eligible=ever_eligible,
        n_klines_absent=len(klines_absent),
        klines_absent_symbols=klines_absent,
        breadth=measure_breadth(eligibility, config.formation_start, static_symbols),
        lifetimes=lifetimes,
        min_eligible=int(counts.min()) if len(counts) else 0,
        median_eligible=float(counts.median()) if len(counts) else 0.0,
        max_eligible=int(counts.max()) if len(counts) else 0,
        factor_exposures=exposures,
        cross_venue=cross_venue,
        yearly_returns=yearly,
        warnings=warnings,
    )
    summary.text = _build_summary_text(summary)
    return summary


__all__ = [
    "FUNDING_CARRY_PIT_FAMILY_KEY",
    "PIT_LIVENESS_WINDOW_DAYS",
    "BreadthYear",
    "FundingCarryPitScreeningSummary",
    "SymbolLifetime",
    "build_pit_eligibility",
    "build_pit_membership",
    "measure_breadth",
    "measure_symbol_lifetimes",
    "pit_universe_asof",
    "run_funding_carry_pit_screening",
]
