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


def build_point_in_time_market_cap(
    close: pd.DataFrame, shares_outstanding: dict[str, pd.Series]
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

    A ticker absent from `shares_outstanding`, or present with an empty
    series, gets an all-NaN market-cap column and is added to the returned
    `tickers_with_no_shares_data` list — never zero, never an
    extrapolated guess. A ticker WITH a real series still carries NaN
    market cap on every date strictly before its first known share-count
    observation (no backward-fill) — real point-in-time behavior, not a
    bug: this project's free data cannot know a company's share count
    before the earliest SEC filing yfinance surfaces for it.

    Accepts any ticker -> Series mapping (not specifically
    get_shares_outstanding's own return shape) so this function is directly
    unit-testable against a hand-built dict, independent of network access
    or that method's own dedup/tz-normalization concerns."""
    aligned: dict[str, pd.Series] = {}
    tickers_with_no_shares_data: list[str] = []

    for ticker in close.columns:
        raw = shares_outstanding.get(ticker)
        if raw is None or raw.empty:
            tickers_with_no_shares_data.append(ticker)
            aligned[ticker] = pd.Series(np.nan, index=close.index)
            continue
        # Union the sparse filing-date index with close's own trading-day
        # index so ffill has every filing date available to propagate FROM
        # — including one that lands on a non-trading day — then read back
        # only close's own dates.
        unioned_index = raw.index.union(close.index).sort_values()
        filled = raw.reindex(unioned_index).ffill()
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
    """The full Build D1 screening pass — THE production entry point, to be
    launched when compute frees up (deliberately NOT run at scale as part of
    building this module — this function exists and is correctness-tested
    against a fake provider below, but the real, expensive, per-ticker
    yfinance-share-count fetch this needs is a separate, later step, exactly
    as instructed).

    Universe: get_universe_over(start, end) — every ticker that was an S&P
    500 member on ANY day of the screening window (the survivorship-free
    candidate pool primitive), NOT today's snapshot — same primitive, same
    reasoning as cross_sectional_patterns.run_round_c_screening. `start`
    must be >= MEMBERSHIP_DATA_START, enforced loudly by get_universe_over
    itself.

    Data fetch is two steps, deliberately sequenced: (1) Close-only daily
    prices for the whole point-in-time universe via get_price_history — this
    family's signal needs Close only, unlike Round C's LPS/CGO signals, so
    there is no reason to pay for Open/Volume the way get_daily_ohlcv would.
    (2) Real point-in-time shares-outstanding history via
    get_shares_outstanding, fetched ONLY for tickers that actually resolved
    a price (`close.columns`, not the full requested universe) — a ticker
    with no price data can never be eligible for a formation regardless of
    its share count, so fetching shares for it would be pure waste, and
    get_shares_outstanding is a per-ticker network call (see that method's
    own docstring), not a cheap batch one.

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

    shares, missing_shares_fetch = provider.get_shares_outstanding(
        list(close.columns), padded_start, end
    )
    market_cap, never_resolved_shares = build_point_in_time_market_cap(close, shares)
    tickers_without_shares = sorted(set(missing_shares_fetch) | set(never_resolved_shares))

    data = CrossSectionalData(close=close, market_cap=market_cap)
    results = screen_cross_sectional_universe(data, ROUND_D1_FAMILY, config)
    return results, missing_price, tickers_without_shares
