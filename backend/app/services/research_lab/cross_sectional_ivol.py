"""Build D1: cross-sectional idiosyncratic-volatility anomaly, VALUE-WEIGHTED
by real point-in-time market cap — a new family expressed against
cross_sectional.py's harness, following cross_sectional_patterns.py's own
conventions (every definition individually cited, the whole family a bounded
literal whose length is the honest n_trials denominator, structural
reasoning documented inline) but genuinely new in one respect Round C never
needed: this is the first family in this project weighted by anything other
than the harness's original signal-magnitude scheme (_leg_weights) or plain
equal weight — see cross_sectional.py's CrossSectionalSpec.leg_weighting and
_resolve_leg_weights, added specifically to support this build.

CITATIONS:
 * Ang, Hodrick, Xing & Zhang, "The Cross-Section of Volatility and Expected
   Returns" (Journal of Finance, 2006): stocks with high trailing
   idiosyncratic volatility (the standard deviation of the residual from a
   regression of a stock's daily return on a market-return factor) earn
   LOWER average returns going forward, not higher — "the volatility
   puzzle". Long the low-IVOL quintile, short the high-IVOL quintile.
 * Bali & Cakici, "Idiosyncratic Volatility and the Cross Section of Expected
   Returns" (Journal of Financial and Quantitative Analysis, 2008): shows the
   AHXZ finding is highly sensitive to how the cross-section is weighted and
   screened — the low-IVOL premium is markedly weaker (and less reliably
   signed) under equal-weighting than under value-weighting, because
   equal-weighting hands illiquid, hard-to-trade micro-caps the same
   influence as mega-caps. This is the direct empirical motivation for value
   weighting THIS family specifically, rather than reusing Round C's
   magnitude-weighted scheme: an equal- or magnitude-weighted replay of this
   anomaly risks testing a portfolio no real allocator could actually hold at
   the sizes implied, not the anomaly the literature reports.
 * Blitz & van Vliet, "The Volatility Effect: Lower Risk without Lower
   Return" (Journal of Portfolio Management, 2007): replicates the same
   low-risk premium internationally and across a longer sample using a
   value-weighted decile methodology, reinforcing that value-weighting (not
   equal-weighting) is this literature's own standard reporting convention —
   the convention this build follows, not a deviation invented for it.

WHY VALUE-WEIGHTED, STRUCTURALLY (not just "the papers do it"): every prior
Round used _leg_weights, which sizes each leg member by its own SIGNAL
excess — appropriate when the signal itself is the only available notion of
"how much to trust this name". Real point-in-time market cap is a
genuinely different, economically motivated weighting basis (how much
capital an allocator could actually deploy in the name) that this project
did not have access to before: real historical shares-outstanding data,
confirmed available for free via yfinance's get_shares_full(ticker, start,
end) (see YFinanceProvider.get_shares_outstanding). Building this family is
therefore also the first real test of that data source's plumbing, not just
a new signal.

WHAT "REAL MARKET CAP" TURNED OUT TO REQUIRE (added after the first
production run, which shipped with it wrong): shares x price is only a
market cap when the two are on the SAME basis, and yfinance's two series
are not. Its prices are back-adjusted — for splits AND for dividends —
while get_shares_full returns counts as filed at the time. The first
version of this module multiplied one by the other directly, which made
every pre-split market cap wrong by the cumulative split factor (AAPL's
computed cap jumped 3.96x on 2020-10-22, a day its price moved -0.95%) and
every historical market cap wrong by that ticker's own accumulated dividend
factor (0.448x for T against 1.000x for AMZN as of 2015-01-07 — a
cross-sectional distortion, which is the kind that actually changes a value
weighting). Both halves are fixed: see YFinanceProvider.get_market_cap_basis
for the dividend-unadjusted price and the split ratios, and
split_adjust_share_counts / build_point_in_time_market_cap below for how
the share counts are restated onto the price's own basis. The already-
reported production numbers were re-run against the fix; the family stays a
clean negative either way.

FALLBACK DISCIPLINE (the build's own explicit requirement): a ticker with no
resolvable share-count history at a given formation must not silently vanish
from value-weighting math or be assigned an arbitrary weight — the harness
(_resolve_leg_weights in cross_sectional.py) falls the WHOLE LEG back to the
original magnitude-weighted scheme whenever any member's market cap is
unusable, and every fallback is counted, not just logged: see
CrossSectionalScreeningResult.n_value_weighted_legs /
n_value_weight_fallbacks, populated for every result this module's family
produces, and the (missing_price, tickers_without_shares) lists
run_round_d1_screening below returns alongside its results.

FAMILY (21 definitions):
 * 3 lookbacks w in IVOL_LOOKBACK_DAYS (21, 63, 252 trading days) x 3 holds
   in IVOL_HOLDING_HORIZONS_DAYS (21, 63, 126) x 2 portfolio modes
   (long_short, long_universe_hedged) = 18 residual-IVOL definitions.
 * + 3 robustness definitions at w=63 ONLY: raw volatility (std of the RAW
   daily return, not the market-model residual) in place of residual IVOL,
   long_short only, across the same 3 holds — tests whether it is genuinely
   the IDIOSYNCRATIC (market-model-purged) component doing the work, or
   just plain volatility, which the AHXZ/Bali-Cakici literature treats as a
   materially different (and less specific) hypothesis.
 = 21, inside ROUND_D1_PATTERN_CEILING, asserted in _build_round_d1_family
 exactly like every prior round's ceiling assertion.

DIRECTION-VARIANT COUNTING: no reverse=True variants are listed, for the
same reason cross_sectional_patterns.py's own module docstring gives for
Round C — a long-short decile/quintile portfolio is antisymmetric under
direction reversal up to (identical) costs, so a reversed variant would
double n_trials while adding zero information. AHXZ's own direction (long
low IVOL, short high IVOL) is used once per definition.
"""

from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    screen_cross_sectional_universe,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)

# The same hard family-size ceiling discipline every prior round respected
# (see cross_sectional_patterns.ROUND_C_PATTERN_CEILING for the underlying
# reason — deflated_sharpe.py's n_trials correction stays statistically
# meaningful in the tens-of-trials range it was validated for). Family size
# is 21 (see module docstring); the ceiling carries the same proportionate
# headroom over its family Round C's 40-over-30 ceiling did (~1.3x).
# Enforced by assertion in _build_round_d1_family, not just documented.
ROUND_D1_PATTERN_CEILING = 30

# A signal window with fewer than this fraction of its possible return
# observations populated is refused (NaN signal) rather than computed on
# whatever little data exists — same guard, same IPO-recency rationale, and
# the same 0.8 engineering-judgment-call value as
# cross_sectional_patterns.MIN_SIGNAL_OBS_FRACTION. Repeated here (not
# imported from that sibling module) so this file's own signal contract is
# self-contained — the same choice cross_sectional_patterns.py itself made
# rather than importing a constant from an earlier module, and Round C's own
# GAO_MIN_OPEN_RETURN-vs-MIN_SIGNAL_OBS_FRACTION precedent (intraday_
# patterns.py vs cross_sectional_patterns.py, different names, same
# register) for "each family module owns its own version of this guard".
MIN_SIGNAL_OBS_FRACTION = 0.8

IVOL_LOOKBACK_DAYS = (21, 63, 252)
IVOL_HOLDING_HORIZONS_DAYS = (21, 63, 126)
IVOL_RANK_FRACTION = 0.2  # quintiles, per AHXZ's own headline construction — not swept, fixed by the brief
IVOL_ROBUSTNESS_LOOKBACK_DAYS = 63

IVOL_CITATION = (
    "Ang, Hodrick, Xing & Zhang, 'The Cross-Section of Volatility and Expected Returns' "
    "(Journal of Finance, 2006); Bali & Cakici, 'Idiosyncratic Volatility and the Cross "
    "Section of Expected Returns' (Journal of Financial and Quantitative Analysis, 2008); "
    "Blitz & van Vliet, 'The Volatility Effect: Lower Risk without Lower Return' "
    "(Journal of Portfolio Management, 2007)"
)


def signal_idiosyncratic_volatility(
    history: CrossSectionalData, *, lookback_days: int, raw_vol: bool = False
) -> pd.Series:
    """Per ticker: trailing `lookback_days` daily returns, regressed (OLS,
    with intercept) on the equal-weighted mean return of every OTHER column
    in the view — i.e. the equal-weighted eligible universe, since the view
    handed to this function is already restricted to eligible tickers only
    (see cross_sectional.py's structural look-ahead-impossibility
    guarantee) — and IVOL is the residual's standard deviation (ddof=1,
    matching pandas' own default so this is on the same scale as any plain
    .std() call elsewhere in this project). raw_vol=True skips the
    regression entirely and uses the standard deviation of the RAW return
    instead — the robustness split the build asked for, to separate
    "idiosyncratic" from "just volatile".

    Regression is done per ticker via closed-form simple-OLS (single
    regressor, so beta = cov(market, y) / var(market) — no need for a full
    least-squares solver), on whatever rows have BOTH a finite market value
    and a finite own-return that day (pairwise-complete, not a hard
    every-ticker-must-have-every-day requirement — a name with a few gappy
    days should not lose its whole signal over it, as long as enough real
    observations remain, per MIN_SIGNAL_OBS_FRACTION below).

    Direction: AHXZ's own finding is LOW IVOL -> higher subsequent returns,
    i.e. long low IVOL / short high IVOL. select_leg_tickers's convention
    (used by every family in this project) is top-of-signal == long, so the
    NEGATIVE of the computed volatility is returned — the lowest-vol name
    gets the LARGEST (least negative) signal value and ranks into the top
    (long) leg, exactly mirroring how cross_sectional_patterns.py's own
    signals are written to return values in "higher is more long" order."""
    closes = history.close.iloc[-(lookback_days + 1) :]
    returns = closes.pct_change(fill_method=None).iloc[1:]
    min_obs = int(lookback_days * MIN_SIGNAL_OBS_FRACTION)

    # Equal-weighted mean return of the WHOLE eligible cross-section handed
    # to this signal, one value per day — the "market" this build's signal
    # is specified against. skipna=True: a day with one ticker's return
    # missing still yields a genuine mean over the rest, rather than NaN-ing
    # the whole day's market value for everyone.
    market = returns.mean(axis=1, skipna=True)

    vol = pd.Series(np.nan, index=closes.columns, dtype=float)
    for ticker in closes.columns:
        y = returns[ticker]

        if raw_vol:
            valid = y.dropna()
            if len(valid) < min_obs:
                continue
            vol[ticker] = float(valid.std(ddof=1))
            continue

        mask = y.notna() & market.notna()
        n_obs = int(mask.sum())
        if n_obs < min_obs or n_obs < 2:
            continue
        x = market[mask].to_numpy(dtype=float)
        yy = y[mask].to_numpy(dtype=float)
        x_mean = x.mean()
        x_dev = x - x_mean
        var_x = float(np.dot(x_dev, x_dev))
        if var_x <= 0.0 or not np.isfinite(var_x):
            # No cross-sectional market variation to regress against over
            # this ticker's own valid window (e.g. every eligible name flat
            # the same days this one has data) — cannot identify a slope,
            # so no residual can be attributed to "idiosyncratic" vs
            # "market" here. Refuse rather than divide by zero.
            continue
        y_mean = yy.mean()
        beta = float(np.dot(x_dev, yy - y_mean) / var_x)
        alpha = y_mean - beta * x_mean
        resid = yy - (alpha + beta * x)
        vol[ticker] = float(np.std(resid, ddof=1))

    return -vol


# Tolerance for recognising the share-count series' OWN jump at a split as
# "this is that split" — see _split_boundary_date. 15% is loose enough to
# absorb a genuine share-count change landing in the same gap as the split
# (measured worst real case: NVDA's 10-for-1 on 2024-06-10, where the count
# also moved on ordinary issuance, showed an observed jump of 9.63x against
# a 10.0 ratio = 3.7% off) and still far tighter than the gap to any
# plausible non-split share-count move at these magnitudes.
SPLIT_JUMP_RELATIVE_TOLERANCE = 0.15

# How far either side of the ex-date to look for that jump. yfinance's
# share-count series is filing-driven, so its switch can LAG the ex-date by
# a full reporting cycle (measured: AAPL's 4-for-1 on 2020-08-31 did not show
# a post-split count until 2020-10-22, 52 days later) or LEAD it by weeks
# (measured: NVDA's 10-for-1 on 2024-06-10 switched on 2024-06-08, two days
# early; ICE's 5-for-1 on 2016-11-04 switched on 2016-08-29, 67 days early;
# MNST's 3-for-1 on 2016-11-10 switched on 2016-09-02, 69 days early). 200
# days forward covers a full 10-K filing lag with margin; 120 days back
# covers the measured lead cases with margin.
SPLIT_JUMP_WINDOW_BEFORE_DAYS = 120
SPLIT_JUMP_WINDOW_AFTER_DAYS = 200


def _split_boundary_date(raw: pd.Series, ex_date: pd.Timestamp, ratio: float) -> pd.Timestamp | None:
    """The date from which `raw`'s own share counts are already expressed in
    POST-split units — every observation strictly before it is in pre-split
    units and needs multiplying by `ratio`. Returns None when the series
    shows no sign of the split at all, meaning NO adjustment should be
    applied (see below — that is a real answer, not a failure).

    Why this is found from the DATA rather than just taken to be the split's
    ex-date: yfinance's get_shares_full is filing-driven, and empirically
    (verified live 2026-08-26 across the 224 real split events, over 164
    tickers, in this project's own 2015-2026 S&P 500 universe) its switch to
    the post-split count does NOT
    reliably coincide with the ex-date. AAPL's 2020-08-31 4-for-1 still
    reported 4.28e9 shares on the ex-date itself and only switched to
    17.10e9 on 2020-10-22, seven weeks LATER; NVDA's 2024-06-10 10-for-1
    switched two days EARLY; ICE's 2016-11-04 5-for-1 switched 67 days
    early. Keying off the ex-date would have left AAPL's market cap 4x
    understated for seven weeks and NVDA's 10x OVERSTATED for two days —
    the same class of error this whole function exists to remove.

    So: scan for the first pair of consecutive observations whose ratio
    matches the split's own ratio (within SPLIT_JUMP_RELATIVE_TOLERANCE),
    anywhere in a window around the ex-date, and take the later of the two.
    The window is what keeps a merger-scale share issuance elsewhere in the
    history from being mistaken for the split.

    NO JUMP FOUND -> NO ADJUSTMENT, which is deliberate and load-bearing.
    yfinance does not always serve as-filed counts: for many older splits it
    serves a series ALREADY restated onto today's share basis, with no jump
    anywhere (measured: NKE's 2-for-1 on 2015-12-24, whose series reads
    1.704e9 on 2015-10-06, ten weeks BEFORE the split, and 1.703e9 in
    January 2017 — flat across the split, i.e. post-split units throughout).
    Adjusting such a series at the ex-date would SPLIT one consistent basis
    into two and manufacture exactly the discontinuity this function exists
    to remove — measured across this universe, an ex-date fallback left 24
    of the 224 split events discontinuous by more than 1.5x, and in about
    20 of those the fallback itself was what created the gap (the residual
    came out equal to the split ratio). Switching to "no adjustment" cut
    that to 7. The absence of a jump is therefore evidence
    that no adjustment is owed: any observation after the split's filing
    cycle must be in post-split units, so a series continuous with those is
    in post-split units throughout.

    KNOWN RESIDUAL, measured not assumed. Over the 224 split events in this
    project's real 2015-2026 S&P 500 universe, 127 were adjusted from a
    detected jump and 97 correctly left alone; 7 still leave the share
    series discontinuous by more than 1.5x across the split. Most of those 7
    are genuine simultaneous corporate actions rather than adjustment
    failures (HLT's 2017 timeshare/REIT spin-offs, AIV's 2020 AIRC
    separation, MTCH's 2020 separation from IAC — the share count really did
    move). The rest are corrupt source data no date convention can rescue:
    TSLA's 2020-08-31 5-for-1, where yfinance reports a single 4.66e9 on the
    ex-date, 25x the pre-split count (the ratio applied twice), before
    settling to the correct 9.34e8; TTD's 2021 10-for-1, where a
    transitional 8.77e7 sits between the 4.76e7 pre- and 4.76e8 post-split
    levels so no single step matches the ratio; and PARA, whose whole
    yfinance history is spliced across a ticker reassignment. These names
    carry a wrong market cap for the stretch the bad rows cover — an
    UNFIXED, disclosed limitation of the free data, materially smaller than
    the bug this function removes (which mis-scaled every one of the 224
    events, by factors from 1e-4 to 70x) but not zero."""
    lo = ex_date - pd.Timedelta(days=SPLIT_JUMP_WINDOW_BEFORE_DAYS)
    hi = ex_date + pd.Timedelta(days=SPLIT_JUMP_WINDOW_AFTER_DAYS)
    previous: float | None = None
    for observed_date, value in raw.items():
        current = float(value)
        if (
            previous is not None
            and previous > 0.0
            and np.isfinite(current)
            and lo <= observed_date <= hi
            and abs((current / previous) / ratio - 1.0) <= SPLIT_JUMP_RELATIVE_TOLERANCE
        ):
            return observed_date
        if np.isfinite(current):
            previous = current
    return None


def split_adjust_share_counts(raw: pd.Series, splits: pd.Series | None) -> pd.Series:
    """Restates a raw, as-filed share-count series in TODAY's share units —
    the same units Yahoo's price series is already expressed in.

    THE BUG THIS EXISTS TO FIX: yfinance's price history is back-adjusted
    for splits (every price before a split is divided by the split ratio, so
    the whole series is quoted in today's share units), while
    get_shares_full returns the share counts as they were actually filed at
    the time. Multiplying the two together — which is what this module did
    before — computes a market cap that is wrong by the cumulative split
    factor for every date before a later split. Confirmed live 2026-08-26:
    AAPL's computed market cap was $517B on 2020-08-28 and $1,918B on
    2020-10-22, a 3.96x jump on a day the price moved -0.95%, purely because
    the share count crossed the 4-for-1 split's filing boundary. AAPL's real
    market cap was ~$2.1T throughout; the pre-boundary figure was understated
    exactly 4x. The same error hits every mega-cap that split inside this
    project's screening window — NVDA (4-for-1 2021, 10-for-1 2024), AMZN
    (20-for-1 2022), GOOGL (20-for-1 2022), TSLA (5-for-1 2020, 3-for-1
    2022) — i.e. precisely the names a VALUE weighting leans hardest on.

    The correction is per-observation, not per-trading-day, and applied
    BEFORE any forward-fill (see build_point_in_time_market_cap): a count
    filed on 2020-08-04 is in pre-split units no matter which later trading
    day it is carried forward to, so the multiplier has to follow the
    observation's own date, not the date it is read at. Doing it after the
    ffill would put the boundary in the wrong place for exactly the stretch
    where it matters most.

    Worked example (AAPL, real numbers): raw count 4.2756e9 on 2020-08-28,
    split ratio 4.0 at a boundary of 2020-10-22, so the adjusted count is
    4.2756e9 * 4 = 1.7102e10 — identical to the 1.7102e10 the series itself
    reports from 2020-10-22 onward, i.e. continuous across the boundary,
    which is what a pure stock split must be. Times the 2020-08-28
    split-adjusted close of $124.81 that gives $2.135T, AAPL's real market
    cap that day, instead of the $533B the unadjusted count produces.

    `splits` is a ticker's own ex-date -> ratio series (YFinanceProvider.
    get_market_cap_basis's per-ticker value). None or empty means "this
    ticker had no splits in the window", which is the common case and needs
    no adjustment at all."""
    if raw.empty or splits is None or splits.empty:
        return raw

    # Sorted defensively: _split_boundary_date reads consecutive PAIRS, so an
    # out-of-order index would manufacture jumps that never happened.
    # get_shares_outstanding already sorts, and the ffill downstream sorts
    # its union index anyway — this only makes that a precondition of this
    # function rather than an assumption about its caller.
    raw = raw.sort_index()
    factors = pd.Series(1.0, index=raw.index)
    for ex_date, ratio in splits.items():
        value = float(ratio)
        if not np.isfinite(value) or value <= 0.0 or value == 1.0:
            continue
        boundary = _split_boundary_date(raw, pd.Timestamp(ex_date), value)
        if boundary is None:
            # No sign of this split in the series — already on one basis.
            continue
        factors.loc[raw.index < boundary] *= value
    return raw * factors


def build_point_in_time_market_cap(
    close: pd.DataFrame,
    shares_outstanding: dict[str, pd.Series],
    splits: dict[str, pd.Series],
) -> tuple[pd.DataFrame, list[str]]:
    """Joins YFinanceProvider.get_shares_outstanding's sparse, event-dated
    per-ticker share-count series onto `close`'s own trading-day index via
    FORWARD-FILL ONLY — each trading day's shares value is the most recent
    SEC-filed count known as of (on or before) that day. This is what makes
    the resulting market_cap frame safe to random-access at any row from
    run_cross_sectional_backtest's formation loop (see
    cross_sectional._resolve_leg_weights' docstring): the point-in-time-
    safety work happens exactly once, here, before any backtest replay
    runs, rather than being re-derived (and risking a look-ahead bug) at
    every formation.

    TWO INPUTS, ONE BASIS. `close` must be a SPLIT-ADJUSTED, DIVIDEND-
    UNADJUSTED price — YFinanceProvider.get_market_cap_basis's close, NOT
    get_price_history's (which is dividend-adjusted too, and would scale
    every ticker's market cap down by its own dividend history: 0.448x for
    T against 1.000x for AMZN as of 2015-01-07, a distortion of the same
    order as the split bug and in the same direction of wrongness — a
    cross-sectional weight that is not comparable across tickers).
    `splits` supplies the ex-date -> ratio series used to restate the raw
    share counts into the same split basis that close is already on; it is
    a REQUIRED argument, not an optional refinement, because omitting it
    silently reproduces the original bug (see split_adjust_share_counts for
    the full confirmation, with real AAPL numbers). A ticker with no splits
    in the window is simply absent from the dict.

    A ticker absent from `shares_outstanding`, or present with an empty
    series, gets an all-NaN market-cap column and is added to the returned
    `tickers_with_no_shares_data` list — never zero, never an
    extrapolated guess. A ticker WITH a real series still carries NaN
    market cap on every date strictly before its first known share-count
    observation (no backward-fill) — real point-in-time behavior, not a
    bug: this project's free data cannot know a company's share count
    before the earliest SEC filing yfinance surfaces for it.

    Accepts any ticker -> Series mappings (not specifically
    get_shares_outstanding's / get_market_cap_basis's own return shapes) so
    this function is directly unit-testable against hand-built dicts,
    independent of network access or those methods' own dedup/tz-
    normalization concerns."""
    aligned: dict[str, pd.Series] = {}
    tickers_with_no_shares_data: list[str] = []

    for ticker in close.columns:
        raw = shares_outstanding.get(ticker)
        if raw is None or raw.empty:
            tickers_with_no_shares_data.append(ticker)
            aligned[ticker] = pd.Series(np.nan, index=close.index)
            continue
        # Split-adjust FIRST, on the sparse filing-dated series, so each
        # count carries the multiplier its own filing date implies — see
        # split_adjust_share_counts on why doing this after the ffill would
        # put the boundary in the wrong place.
        adjusted = split_adjust_share_counts(raw, splits.get(ticker))
        # Union the sparse filing-date index with close's own trading-day
        # index so ffill has every filing date available to propagate FROM
        # — including one that lands on a non-trading day — then read back
        # only close's own dates.
        unioned_index = adjusted.index.union(close.index).sort_values()
        filled = adjusted.reindex(unioned_index).ffill()
        aligned[ticker] = filled.reindex(close.index)

    shares_df = pd.DataFrame(aligned, index=close.index)[list(close.columns)]
    market_cap = shares_df * close
    return market_cap, tickers_with_no_shares_data


def _build_round_d1_family() -> list[CrossSectionalSpec]:
    """Assembles the full, fixed Build D1 family — 21 definitions (18
    residual-IVOL + 3 raw-vol robustness), inside ROUND_D1_PATTERN_CEILING.
    This list's literal length is the n_trials denominator
    screen_cross_sectional_universe uses — every definition here counts,
    whether or not it survives the data floors. Every spec sets
    leg_weighting="value" and requires_market_cap=True — this build's whole
    point (see module docstring) — never "magnitude", which stays every
    OTHER family's (Round C's) default and is unaffected by this family
    existing."""
    specs: list[CrossSectionalSpec] = []

    for lookback in IVOL_LOOKBACK_DAYS:
        for portfolio in ("long_short", "long_universe_hedged"):
            portfolio_tag = "ls" if portfolio == "long_short" else "hedged"
            for horizon in IVOL_HOLDING_HORIZONS_DAYS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"ivol_resid_w{lookback}_{portfolio_tag}_h{horizon}",
                        family="idiosyncratic_volatility",
                        citation=IVOL_CITATION,
                        signal_fn=partial(
                            signal_idiosyncratic_volatility, lookback_days=lookback, raw_vol=False
                        ),
                        # +1 row: pct_change needs one prior price to produce
                        # `lookback` genuine return observations — same
                        # convention cross_sectional_patterns.py's LPS specs
                        # use for the identical reason (see that module's
                        # _build_round_c_family comment on lookback_days).
                        lookback_days=lookback + 1,
                        holding_days=horizon,
                        portfolio=portfolio,
                        rank_fraction=IVOL_RANK_FRACTION,
                        leg_weighting="value",
                        requires_market_cap=True,
                    )
                )

    # Robustness: w=63 only, raw volatility (not residual IVOL), long_short
    # only, across the same 3 holds — see module docstring.
    for horizon in IVOL_HOLDING_HORIZONS_DAYS:
        specs.append(
            CrossSectionalSpec(
                pattern_id=f"ivol_rawvol_w{IVOL_ROBUSTNESS_LOOKBACK_DAYS}_ls_h{horizon}",
                family="idiosyncratic_volatility",
                citation=IVOL_CITATION,
                signal_fn=partial(
                    signal_idiosyncratic_volatility,
                    lookback_days=IVOL_ROBUSTNESS_LOOKBACK_DAYS,
                    raw_vol=True,
                ),
                lookback_days=IVOL_ROBUSTNESS_LOOKBACK_DAYS + 1,
                holding_days=horizon,
                portfolio="long_short",
                rank_fraction=IVOL_RANK_FRACTION,
                leg_weighting="value",
                requires_market_cap=True,
            )
        )

    assert len(specs) == 21, f"Build D1 family has {len(specs)} definitions, expected exactly 21."
    assert len(specs) <= ROUND_D1_PATTERN_CEILING, (
        f"Build D1 family has {len(specs)} definitions, over the {ROUND_D1_PATTERN_CEILING} ceiling — "
        "see ROUND_D1_PATTERN_CEILING for why this is a hard statistical limit, not a style rule."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.leg_weighting == "value" and s.requires_market_cap for s in specs)
    return specs


ROUND_D1_FAMILY: list[CrossSectionalSpec] = _build_round_d1_family()

# Calendar padding fetched BEFORE the requested screening start purely to
# warm up the longest signal lookback this family uses: max spec.lookback_
# days is 252 + 1 = 253 trading rows. 253 trading days ~= 253 * 365 / 252
# ~= 367 calendar days; rounded up for holiday clustering to 400 (the same
# ~3.5-9% buffer register cross_sectional_patterns.PRICE_HISTORY_PADDING_
# CALENDAR_DAYS and cross_sectional_patterns_round_d.ROUND_D_PRICE_HISTORY_
# PADDING_CALENDAR_DAYS both use over their own raw estimates). Formations
# themselves never occur in the padding — CrossSectionalConfig.formation_
# start pins them to the requested start — so no formation can predate the
# point-in-time membership data either.
PRICE_HISTORY_PADDING_CALENDAR_DAYS = 400


def run_round_d1_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> tuple[list[CrossSectionalScreeningResult], list[str], list[str]]:
    """The full Build D1 screening pass — THE production entry point. Run
    against real data twice: once on 2026-08-26 as first shipped, and again
    after the market-cap basis fix (see the module docstring's "WHAT 'REAL
    MARKET CAP' TURNED OUT TO REQUIRE"), which changed every value-weighted
    leg the first run produced. Also correctness-tested offline against a
    fake provider below, since the real per-ticker yfinance share-count
    fetch is far too expensive for a test suite.

    Universe: get_universe_over(start, end) — every ticker that was an S&P
    500 member on ANY day of the screening window (the survivorship-free
    candidate pool primitive), NOT today's snapshot — same primitive, same
    reasoning as cross_sectional_patterns.run_round_c_screening. `start`
    must be >= MEMBERSHIP_DATA_START, enforced loudly by get_universe_over
    itself.

    Data fetch is three steps, deliberately sequenced: (1) Close-only daily
    prices for the whole point-in-time universe via get_price_history — this
    family's signal needs Close only, unlike Round C's LPS/CGO signals, so
    there is no reason to pay for Open/Volume the way get_daily_ohlcv would.
    (2) The MARKET-CAP BASIS — a split-adjusted, dividend-UNadjusted close
    plus per-ticker split ratios — via get_market_cap_basis, one extra
    batched call. Step (1)'s price is the right one for a total-return
    SIGNAL and the wrong one for a market cap; step (2)'s is the reverse.
    (3) Real point-in-time shares-outstanding history via
    get_shares_outstanding, fetched ONLY for tickers that actually resolved
    a price (`close.columns`, not the full requested universe) — a ticker
    with no price data can never be eligible for a formation regardless of
    its share count, so fetching shares for it would be pure waste, and
    get_shares_outstanding is a per-ticker network call (see that method's
    own docstring), not a cheap batch one. Steps (2) and (3) are what
    build_point_in_time_market_cap combines onto one consistent basis.

    Returns (screening results, tickers that resolved no price data, tickers
    with no usable point-in-time share-count history among the priced
    ones). Both diagnostic lists are a required part of the result, not a
    logging detail — same discipline run_round_c_screening's own docstring
    states for its one missing-tickers list, extended here to the second
    list this build's own "log how often the fallback fires" requirement
    needs: `tickers_without_shares` is the STRUCTURAL half of that answer
    (which names can NEVER be value-weighted, for the whole run), while
    CrossSectionalScreeningResult.n_value_weight_fallbacks (populated by
    screen_cross_sectional_universe) is the PER-FORMATION half (how often a
    leg that COULD have been value-weighted actually had to fall back,
    formation by formation) — together a complete accounting, deliberately
    returned as structured data rather than printed, matching this
    project's established convention (see run_round_c_screening's own
    docstring) of treating this kind of number as a required result field,
    not something that could go unread in a log."""
    if start < MEMBERSHIP_DATA_START:
        # get_universe_over would also reject this; checking here too makes
        # the error message name the actual fix.
        raise ValueError(
            f"Build D1 screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that date "
            "would silently see an empty universe."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else CrossSectionalConfig()
    config.formation_start = start

    universe = get_universe_over(start, end)
    padded_start = start - timedelta(days=PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    close, missing_price = provider.get_price_history(universe, padded_start, end)
    if close.empty:
        return [], missing_price, []

    priced = list(close.columns)
    # The market-cap BASIS price and the split ratios, in one batched call —
    # deliberately not get_price_history's close, which is dividend-adjusted
    # and therefore not a market cap when multiplied by a share count. See
    # build_point_in_time_market_cap's "TWO INPUTS, ONE BASIS" note and
    # get_market_cap_basis's own docstring. Reindexed onto the signal
    # close's exact index/columns so the market_cap frame stays row-aligned
    # with the frame the formation loop indexes by position; any date or
    # ticker this second fetch failed to resolve lands as NaN, which the
    # harness already treats as "not value-weightable" and falls that whole
    # leg back to magnitude weighting rather than guessing.
    mcap_close, splits, _ = provider.get_market_cap_basis(priced, padded_start, end)
    mcap_close = (
        pd.DataFrame(np.nan, index=close.index, columns=close.columns)
        if mcap_close.empty
        else mcap_close.reindex(index=close.index, columns=close.columns)
    )

    shares, missing_shares_fetch = provider.get_shares_outstanding(priced, padded_start, end)
    market_cap, never_resolved_shares = build_point_in_time_market_cap(mcap_close, shares, splits)
    tickers_without_shares = sorted(set(missing_shares_fetch) | set(never_resolved_shares))

    data = CrossSectionalData(close=close, market_cap=market_cap)
    results = screen_cross_sectional_universe(data, ROUND_D1_FAMILY, config)
    return results, missing_price, tickers_without_shares
