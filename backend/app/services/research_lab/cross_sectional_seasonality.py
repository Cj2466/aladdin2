"""Same-calendar-month RETURN SEASONALITY — a cross-sectional family
expressed against cross_sectional.py's harness, following the structural
conventions cross_sectional_ivol.py and cross_sectional_quality.py
established (every definition individually cited, the whole family a
bounded literal whose length is the honest n_trials denominator, the
point-in-time guarantee argued structurally rather than asserted).

Needs ONLY daily closes — no new data pipeline, no fundamentals, no
filings. That is the entire reason this family is cheap enough to be worth
running at all; it is not a claim that it is more likely to work.


CITATION (verified live 2026-08-28, not from memory)
====================================================
 * Matti Keloharju, Juhani T. Linnainmaa & Peter Nyberg, "Return
   Seasonalities", THE JOURNAL OF FINANCE, Vol. 71, No. 4 (August 2016),
   pp. 1557-1590, DOI 10.1111/jofi.12398. Publication venue/volume/issue/
   pages confirmed this session against three independent records: Wiley
   Online Library (onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12398),
   Aalto University's research portal, and RePEc/EconPapers
   (RePEc:bla:jfinan:v:71:y:2016:i:4:p:1557-1590).

   WHAT I ACTUALLY READ, and what I did not: SSRN (abstract_id=2224246) and
   the Wiley full text both refuse automated fetches (HTTP 403). The
   methodology quoted below was read from the authors' own NBER working
   paper — Keloharju, Linnainmaa & Nyberg, "Common Factors in Return
   Seasonalities", NBER Working Paper No. 20815, December 2014
   (nber.org/system/files/working_papers/w20815/w20815.pdf), fetched and
   text-extracted in full this session. Its abstract is word-for-word the
   published JF abstract ("A strategy that selects stocks based on their
   historical same-calendar-month returns earns an average return of 13%
   per year..."), so it is the working-paper version of the same result —
   but it carries a DIFFERENT TITLE, and I could not diff its tables
   against the published article. HONEST FLAG: every number quoted below
   is from w20815, not from the JF 71(4) pages, and a referee-round
   revision could have moved any of them. The 13%/year headline is the one
   figure independently corroborated on the Wiley/Aalto/EconPapers records.

VERIFIED MECHANISM (quoted from w20815, not paraphrased from memory)
 * The signal, from Section 4.1: "We estimate [mu-hat_i,t] by computing
   each stock's average same-calendar-month return from the prior 20-year
   period. To isolate cross-sectional differences in expected returns, and
   to take into account the fact that stocks differ in their availability
   of historical return data, we demean stock returns in the cross section
   before taking the average. We include stocks that have at least five
   years of historical data at time t."
 * The strategy, from Section 4.2 / Table 1: "The first row of Table 1 sets
   the stage by sorting individual stocks into winner-loser deciles by the
   20-year average same-calendar-month or other-calendar-month return. In
   March 1964, for example, we sort on either the average March
   ('Same-month return') or non-March ('Other-month return') returns in
   1944-63. The seasonality strategies are long the winner and short the
   loser decile. The same-month strategy earns an average return of 1.19%
   per month (t-value = 6.27) while the strategy based on other months
   earns a return of -0.96% (t-value = -4.12)."
 * So the scoping pass's framing was RIGHT on all three counts I was asked
   to check: rank by own historical same-calendar-month average return,
   long top decile / short bottom decile, for the upcoming instance of that
   month. The lookback convention is 20 YEARS of same-month observations
   (i.e. up to 20 observations), with a minimum of 5 years of history.
 * The "other-month" leg is not a footnote — it is the paper's own placebo,
   and it comes out SIGNIFICANTLY NEGATIVE (-0.96%/month, t = -4.12). It is
   reproduced here as a real spec (see OTHER_MONTH_MODE) because a family
   that reports only its favored direction has not tested anything.
 * Sample: "monthly data from January 1963 through December 2011", all
   NYSE/Amex/Nasdaq stocks. The headline is "an average return of 13% per
   year between 1963 and 2011".


REDUNDANCY / ENTANGLEMENT — the honest disclosure this family owes
=================================================================
This is NOT a fully novel exposure for this project, and the paper itself
is the strongest witness against calling it one. Its own abstract concludes:
"Our results suggest that seasonalities are not a distinct class of
anomalies that requires an explanation of its own---rather, they are
intertwined with other return anomalies through shared common factors."

Three concrete, quoted overlaps, plus what this project has already tested:

 1. MOMENTUM, at the 12-month annual lag specifically. w20815 Section 4.1,
    on the augmented Fama-MacBeth regression: "The one-year slope
    coefficient is positive and statistically significant at the 5% level —
    perhaps because of the stock price momentum — but the statistical
    significance of the lagged returns fades after this point". The most
    recent same-calendar-month observation (target-month lag 12) sits
    exactly where the momentum signal lives. This project already has a
    momentum implementation (app/services/research_lab/momentum.py) and
    momentum-adjacent cross-sectional work in the Round C/D pattern
    families, so that lag is genuinely re-tested ground, not new ground.
    THIS IS WHY SEASONALITY_SKIP_RECENT_MODE EXISTS: one spec drops the
    lag-12 observation entirely and averages only lags 24..240. If the
    family's whole result lives in the spec that keeps lag 12 and dies in
    the one that drops it, the honest reading is "this is momentum wearing
    a calendar", and this module will say so.
 2. WELL-DIVERSIFIED PORTFOLIO FACTORS — size, value, dividend-to-price,
    industry. w20815 Section 4.4.1, Table 2: regressing the individual-
    stock seasonality strategy on seasonality strategies built from
    diversified portfolios, "The intercept is 0.74% per month (t = 4.49) in
    column (7) that regresses the returns against all seasonality
    strategies. The R2 is 17%... The last column shows that the intercept
    is 0.60% (t = 3.66) when the seasonality-mimicking factor is derived
    from the 58 size, value, momentum, dividend-to-price, and industry
    portfolios. Thus... a seasonality strategy constructed from a
    relatively small set of portfolios already explains half of the profits
    of the individual-stock seasonality strategy." Roughly HALF the raw
    effect is a repackaging of factor exposures, by the authors' own
    measurement.
 3. LONG-TERM REVERSAL. w20815 frames the whole phenomenon as "the positive
    peaks that disrupt the long-term reversals at every annual lag" — i.e.
    the seasonality signal is defined against a reversal backdrop, and this
    project's Build D2 (cross_sectional_patterns_d2.py) is a long-horizon
    reversal family. Overlapping territory again.

WHAT THIS FAMILY THEREFORE CLAIMS: not "an untested anomaly", but "a
specific, pre-declared re-slicing of return history — by calendar month —
that this project has not previously cut, on a signal whose academic
authors expect it to share factors with things this project HAS cut."
A positive result here would need the skip-lag-12 spec and the other-month
placebo to both behave before it meant anything. That is the bar, declared
before the run, not after seeing the numbers.


THE HARNESS FIT, and the one real deviation
===========================================
cross_sectional.py forms every `holding_days` TRADING DAYS. KLN form on
CALENDAR MONTH boundaries. At holding_days=21 the cadence is 12 formations
per 252-day year, so the two stay approximately aligned but drift within
the month across years. This family therefore does not, and cannot, claim
to trade "the calendar month" exactly; it trades the ~21-trading-day window
that mostly overlaps one. target_calendar_month() below resolves which
month that is by looking at the MIDPOINT of the upcoming hold, which is the
least-wrong single answer available under a trading-day cadence. This is a
real deviation from the paper and is not smoothed over anywhere in the
reported numbers.

POINT-IN-TIME CORRECTNESS is structural, twice over, and neither layer is
load-bearing alone:
 * The harness hands SignalFn a history view sliced to rows <= the
   formation date, so no future row is reachable at all (see
   cross_sectional.py's SignalFn contract).
 * WITHIN that view, _complete_monthly_returns() additionally drops the
   formation date's OWN month, because that month is still in progress on
   the formation date and a partial month is not a monthly return. And the
   lag algebra below only ever admits target-month lags >= 12, which places
   every selected observation at least 11 months before the formation
   month. Either mechanism alone would prevent look-ahead; both are present
   so that a future edit to one is caught by the tests on the other.


FAMILY (8 definitions)
======================
 * 3 lookbacks in SEASONALITY_LOOKBACK_YEARS (5, 10, 20 years) x 2
   portfolio modes (long_short, long_universe_hedged) = 6 same-month
   definitions, decile legs, hold 21 trading days.
   WHY 5 AND 10 AND NOT ONLY THE PAPER'S 20: this project's point-in-time
   S&P 500 membership begins at MEMBERSHIP_DATA_START (2015-01-07), so a
   20-year lookback at the FIRST formation reaches back to 1995. Daily
   history that deep is available (verified live this session: yfinance
   returns unbroken daily OHLCV for AAPL/MSFT/JNJ/XOM/KO from 1993-01-04),
   but requiring 20 usable years would bias the admitted cross-section
   hard toward long-listed survivors. The paper's own floor is 5 years of
   history, not 20, so the shorter windows are the paper's rule applied
   honestly to a shallower universe — not a parameter sweep dressed up as
   robustness. All three are counted as trials regardless.
 * + 1 OTHER-MONTH PLACEBO at 20 years, long_short: the paper's own
   negative control (-0.96%/month there). If this comes out looking like
   the same-month specs, the family measured a data artifact, not a
   seasonality.
 * + 1 MOMENTUM-PURGED same-month at 20 years, long_short: identical to its
   sibling except the lag-12 observation is dropped. The entanglement test
   described above.
 = 8, asserted against SEASONALITY_SPEC_CEILING in _build_seasonality_family.

DIRECTION-VARIANT COUNTING: no reversed variants, for the reason
cross_sectional_patterns.py's docstring gives — a long-short decile
portfolio is antisymmetric under direction reversal up to identical costs,
so a reversed spec would double n_trials while adding zero information.
KLN's own direction (long the high same-month average) is used once per
definition.


PRODUCTION RESULT — AN HONEST NEGATIVE, AND THE PLACEBO BEAT THE SIGNAL
======================================================================
Run 2026-08-28 over 2015-01-07 .. 2026-08-27 (run_tag
"seasonality_build_2026-08-28", family_key "same_calendar_month_
seasonality", 8 rows in cross_sectional_trial_results). 140 formations per
spec, 0 skipped, ~43.6 names per leg, 2925 realized trading days,
n_trials = 8. Annualized Sharpe, net of costs:

    seasonality_other_month_placebo_20y_ls     +0.2305   DSR 0.391
    seasonality_same_month_20y_lh              -0.0561   DSR 0.105
    seasonality_same_month_10y_lh              -0.1126   DSR 0.074
    seasonality_same_month_5y_lh               -0.2459   DSR 0.029
    seasonality_same_month_skip_lag12_20y_ls   -0.2927   DSR 0.019
    seasonality_same_month_10y_ls              -0.3420   DSR 0.013
    seasonality_same_month_20y_ls              -0.3842   DSR 0.009
    seasonality_same_month_5y_ls               -0.4026   DSR 0.008

EVERY SAME-MONTH DEFINITION IS NEGATIVE. Not weak — negative, at all three
lookbacks and in both portfolio modes. No DSR comes near any usable floor;
the largest is the placebo's 0.391 and every real signal sits below 0.11.
The paper's 13%/year does not survive contact with this universe and this
period, in this implementation.

THE MOST INFORMATIVE NUMBER HERE IS THE PLACEBO. KLN's other-month control
earns -0.96%/month in their sample — significantly NEGATIVE, the mirror of
their same-month result. Here it is the single best-performing spec in the
family (+0.2305) while every same-month spec is negative. The sign of the
same-month/other-month CONTRAST is inverted relative to the paper. That is
not a weaker version of KLN's finding; it is the opposite ordering, and it
is much better explained by "this cross-section is exhibiting plain
long-horizon mean reversion, which the other-month average happens to
proxy" than by anything seasonal. A reader tempted to salvage a +0.23
Sharpe from this table should note it is the arm that was pre-declared as
the thing that must NOT work.

WHAT THE MOMENTUM-PURGED SPEC SAYS (the entanglement question, answered
with the run rather than with prose): dropping the lag-12 observation moves
the 20-year long-short Sharpe from -0.3842 to -0.2927 — i.e. purging the
momentum-overlapping lag makes the strategy LESS bad, by about 0.09 of
Sharpe. So the lag-12 component was contributing negatively here, and the
seasonality signal is NOT simply momentum in disguise in this sample; it is
not much of anything. That is a real answer to the redundancy question, and
it happens to be the answer that removes the most interesting alternative
explanation for the negative result.

SCOPE OF THE NEGATIVE, stated so it is not over-read: 11.6 years and 140
formations on the S&P 500, against KLN's 49 years across the whole
NYSE/Amex/Nasdaq tape. Their effect is documented on a cross-section
including small and micro-caps; this universe has none. 143 of the
point-in-time universe's tickers resolved no price data at all (the
project's known delisted-securities gap — see the pending-paid-decisions
list), so the replay is missing most of the names that left the index by
acquisition or failure. This is evidence that the anomaly is not
harvestable in S&P 500 large-caps over 2015-2026 as implemented here. It is
NOT a refutation of Keloharju, Linnainmaa & Nyberg (2016).
"""

from datetime import date, timedelta
from functools import partial
from typing import Literal

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

SEASONALITY_FAMILY = "same_calendar_month_seasonality"

# Deciles — KLN Table 1 sorts individual stocks into "winner-loser deciles".
SEASONALITY_RANK_FRACTION = 0.1

# 21 trading days ~ one calendar month, the paper's rebalancing frequency.
# Only one holding horizon is offered: a same-calendar-month signal predicts
# ONE month, and holding it for three would be holding a stale prediction
# about a month that has already ended.
SEASONALITY_HOLDING_DAYS = 21

# See the docstring's "WHY 5 AND 10 AND NOT ONLY THE PAPER'S 20".
SEASONALITY_LOOKBACK_YEARS = (5, 10, 20)

# KLN: "We include stocks that have at least five years of historical data
# at time t." Applied here as five usable same-calendar-month observations.
MIN_SAME_MONTH_OBSERVATIONS = 5

# Trading rows a lookback of Y years needs before its first formation: Y
# years of daily bars plus a one-month cushion so the oldest monthly return
# in the window has a prior month-end close to be computed against.
TRADING_DAYS_PER_YEAR_INT = 252

# 365.25 / 252 — used ONLY to locate the midpoint of the upcoming holding
# window on the calendar (see target_calendar_month). Never used to
# annualize anything; CrossSectionalConfig.periods_per_year does that.
CALENDAR_DAYS_PER_TRADING_DAY = 365.25 / 252.0

SEASONALITY_SPEC_CEILING = 8

SameMonthMode = Literal["same", "same_skip_recent", "other"]

SAME_MONTH_MODE: SameMonthMode = "same"
SEASONALITY_SKIP_RECENT_MODE: SameMonthMode = "same_skip_recent"
OTHER_MONTH_MODE: SameMonthMode = "other"

SEASONALITY_CITATION = (
    "Keloharju, Linnainmaa & Nyberg, 'Return Seasonalities', Journal of Finance 71(4), "
    "2016, pp. 1557-1590 (DOI 10.1111/jofi.12398); methodology quoted from the authors' "
    "NBER WP 20815 'Common Factors in Return Seasonalities' (Dec 2014), read in full "
    "2026-08-28 — a strategy sorting stocks into deciles on their average same-calendar-"
    "month return over the prior 20 years earns 13% per year (1.19%/month, t=6.27), while "
    "the other-calendar-month placebo earns -0.96%/month (t=-4.12)."
)

# Calendar padding for the price fetch: Y years of lookback plus a year of
# slack, so the first formation genuinely has its full window rather than
# silently ranking on however much history happened to arrive.
SEASONALITY_PRICE_PADDING_CALENDAR_DAYS = 366 * (max(SEASONALITY_LOOKBACK_YEARS) + 1)


def _complete_monthly_returns(close: pd.DataFrame) -> pd.DataFrame:
    """Month-end-to-month-end simple returns for every FULLY ELAPSED month
    in the view, cross-sectionally demeaned per KLN.

    Two deliberate choices, both load-bearing:

    (1) THE FORMATION MONTH IS DROPPED. The view's last row is the formation
    date, which is normally mid-month; the return of a month that is still
    running is not a monthly return, and admitting it would let the signal
    rank on a fragment whose length varies with where the trading-day
    cadence happened to land. Note this is a DATA-QUALITY exclusion, not the
    look-ahead guard — nothing in the view is in the future to begin with
    (see the module docstring's point-in-time section), and the lag algebra
    in signal_same_calendar_month excludes this month again independently.

    (2) CROSS-SECTIONAL DEMEANING, quoted from w20815 Section 4.1: "we
    demean stock returns in the cross section before taking the average".
    The cross-section available here is the formation date's ELIGIBLE
    universe (the view's columns), not KLN's full CRSP tape — a real and
    disclosed difference. It matters less than it looks: demeaning is a
    per-month location shift applied identically to every ticker being
    ranked, so it cannot reorder a single formation's ranking on its own.
    Its actual job is stopping months with large market-wide moves from
    dominating the multi-year average, which it still does here."""
    if close.empty:
        return close
    formation_period = close.index[-1].to_period("M")
    month_end_close = close.resample("ME").last()
    monthly = month_end_close.pct_change(fill_method=None)
    monthly = monthly[monthly.index.to_period("M") < formation_period]
    if monthly.empty:
        return monthly
    return monthly.sub(monthly.mean(axis=1), axis=0)


def target_calendar_month(formation_date: pd.Timestamp, holding_days: int) -> pd.Period:
    """Which calendar month the upcoming hold actually lands in, as a
    monthly Period.

    KLN form on calendar-month boundaries and hold exactly one calendar
    month, so "the month being predicted" is unambiguous for them. This
    harness forms every `holding_days` TRADING days, so a formation can sit
    anywhere inside a month and the hold straddles two. The midpoint of the
    holding window is the least-wrong single answer: whichever month owns
    more of the hold owns the midpoint. At holding_days=21 the offset is 15
    calendar days, so a formation late in March targets April while one
    early in March targets March — in both cases the month the position is
    mostly exposed to. Disclosed as a real deviation in the module
    docstring rather than hidden behind an exact-sounding name."""
    offset_days = round(holding_days * CALENDAR_DAYS_PER_TRADING_DAY / 2.0)
    return pd.Period(formation_date + timedelta(days=offset_days), freq="M")


def signal_same_calendar_month(
    data: CrossSectionalData,
    *,
    lookback_years: int,
    holding_days: int = SEASONALITY_HOLDING_DAYS,
    mode: SameMonthMode = SAME_MONTH_MODE,
) -> pd.Series:
    """KLN's mu-hat: each ticker's average cross-sectionally-demeaned return
    in the TARGET calendar month, over the prior `lookback_years` years.
    Higher = ranked into the long leg (select_leg_tickers takes the top).

    THE LAG ALGEBRA, stated in the paper's own frame of reference. KLN index
    lags relative to the RETURN month t (the month being predicted), not
    relative to the formation date, and the same-calendar-month observations
    therefore sit at annual lags 12, 24, ..., 240. Every mode below is
    expressed in those target-month lags, which is why the formation-date
    drift discussed in target_calendar_month cannot corrupt the selection:

      * "same"             lags {12, 24, ..., 12 * lookback_years}
      * "same_skip_recent" the same set MINUS lag 12 — the momentum-purged
                           variant (see the module's entanglement section:
                           w20815 attributes the significant one-year slope
                           to "the stock price momentum")
      * "other"            every lag in [12, 12 * lookback_years] that is
                           NOT a multiple of 12 — KLN's own placebo, which
                           they describe as sorting on "the average return
                           in all other months over the same period,
                           skipping months t-11 through t-1". Requiring
                           lag >= 12 IS that skip, exactly.

    LOOK-AHEAD, structurally: the minimum admitted lag is 12 and the target
    month is at most one month past the formation month, so the most recent
    observation any mode can reach is 11 months BEFORE the formation month.
    There is no parameter setting that admits the formation month or any
    month after it.

    NaN (the SignalFn contract's "no valid signal today") for any ticker
    with fewer than MIN_SAME_MONTH_OBSERVATIONS usable observations, which
    is KLN's own five-years-of-history floor."""
    monthly = _complete_monthly_returns(data.close)
    empty = pd.Series(np.nan, index=data.close.columns, dtype=float)
    if monthly.empty:
        return empty

    target = target_calendar_month(data.close.index[-1], holding_days)
    lags = target.ordinal - monthly.index.to_period("M").asi8
    max_lag = 12 * lookback_years

    in_window = (lags >= 12) & (lags <= max_lag)
    on_annual_lag = lags % 12 == 0
    if mode == "same":
        selected = in_window & on_annual_lag
    elif mode == "same_skip_recent":
        selected = in_window & on_annual_lag & (lags != 12)
    elif mode == "other":
        selected = in_window & ~on_annual_lag
    else:
        raise ValueError(f"unknown same-calendar-month mode {mode!r}")

    window = monthly[selected]
    if window.empty:
        return empty

    # A minimum-observation floor, not a "how many rows did I slice" count:
    # a ticker listed for three of the twenty target months has three
    # observations however many rows the window has.
    usable = window.count()
    signal = window.mean()
    signal = signal.where(usable >= MIN_SAME_MONTH_OBSERVATIONS)
    return signal.reindex(data.close.columns)


def _spec(
    *,
    pattern_id: str,
    lookback_years: int,
    portfolio: Literal["long_short", "long_universe_hedged"],
    mode: SameMonthMode,
) -> CrossSectionalSpec:
    return CrossSectionalSpec(
        pattern_id=pattern_id,
        family=SEASONALITY_FAMILY,
        citation=SEASONALITY_CITATION,
        signal_fn=partial(
            signal_same_calendar_month,
            lookback_years=lookback_years,
            holding_days=SEASONALITY_HOLDING_DAYS,
            mode=mode,
        ),
        # Y years of daily rows plus one month of cushion: the OLDEST
        # monthly return in the window is computed against the month-end
        # close BEFORE it, which must also be inside the view.
        lookback_days=lookback_years * TRADING_DAYS_PER_YEAR_INT + SEASONALITY_HOLDING_DAYS,
        holding_days=SEASONALITY_HOLDING_DAYS,
        portfolio=portfolio,
        rank_fraction=SEASONALITY_RANK_FRACTION,
    )


def _build_seasonality_family() -> list[CrossSectionalSpec]:
    """The pre-declared family, built once at import so its length is fixed
    before any data is touched — the same discipline every prior family
    module states: the literal here IS the n_trials denominator
    screen_cross_sectional_universe deflates against, so adding a spec
    after seeing results would be visible as a diff, not silent."""
    specs: list[CrossSectionalSpec] = []
    for years in SEASONALITY_LOOKBACK_YEARS:
        for portfolio in ("long_short", "long_universe_hedged"):
            short_tag = "ls" if portfolio == "long_short" else "lh"
            specs.append(
                _spec(
                    pattern_id=f"seasonality_same_month_{years}y_{short_tag}",
                    lookback_years=years,
                    portfolio=portfolio,
                    mode=SAME_MONTH_MODE,
                )
            )
    specs.append(
        _spec(
            pattern_id="seasonality_other_month_placebo_20y_ls",
            lookback_years=20,
            portfolio="long_short",
            mode=OTHER_MONTH_MODE,
        )
    )
    specs.append(
        _spec(
            pattern_id="seasonality_same_month_skip_lag12_20y_ls",
            lookback_years=20,
            portfolio="long_short",
            mode=SEASONALITY_SKIP_RECENT_MODE,
        )
    )
    assert len(specs) == SEASONALITY_SPEC_CEILING, (
        f"seasonality family is {len(specs)} specs, not the pre-declared "
        f"{SEASONALITY_SPEC_CEILING} — the ceiling is the honest n_trials denominator "
        "and must be updated deliberately, never drifted past."
    )
    return specs


SEASONALITY_SPECS: list[CrossSectionalSpec] = _build_seasonality_family()


def run_seasonality_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> tuple[list[CrossSectionalScreeningResult], list[str]]:
    """THE production entry point. Returns (results, tickers that resolved
    no price data) — the missing-ticker list is a required part of the
    result, not a log line, matching run_round_c_screening's and
    run_round_d1_screening's own stated discipline.

    Universe: get_universe_over(start, end) — every ticker that was an S&P
    500 member on ANY day of the window, the survivorship-free candidate
    pool, gated per formation by point-in-time membership inside the
    harness. `start` must be >= MEMBERSHIP_DATA_START.

    Close-only fetch (get_price_history, not get_daily_ohlcv): this family's
    signal reads nothing but closes, so paying for Open/High/Low/Volume
    would be waste. The fetch starts SEASONALITY_PRICE_PADDING_CALENDAR_DAYS
    before `start` purely to warm the 20-year lookback;
    config.formation_start is pinned to `start` so no formation can occur in
    that padding, where point-in-time membership would answer False for
    everyone."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Seasonality screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that date would "
            "silently see an empty universe."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else CrossSectionalConfig()
    config.formation_start = start

    universe = get_universe_over(start, end)
    padded_start = start - timedelta(days=SEASONALITY_PRICE_PADDING_CALENDAR_DAYS)
    close, missing_price = provider.get_price_history(universe, padded_start, end)
    if close.empty:
        return [], missing_price

    data = CrossSectionalData(close=close)
    results = screen_cross_sectional_universe(data, SEASONALITY_SPECS, config)
    return results, missing_price
