"""LIQUIDITY SHOCKS (Delta-ILLIQ) — a cross-sectional family expressed
against cross_sectional.py's harness, following the same structural
conventions as cross_sectional_ivol.py and cross_sectional_seasonality.py
(every definition individually cited, the family a bounded literal whose
length is the honest n_trials denominator, point-in-time correctness argued
structurally).

Needs ONLY daily closes and volume — no new data pipeline.


CITATION (verified live 2026-08-28, not from memory)
====================================================
 * Turan G. Bali, Lin Peng, Yannan Shen & Yi Tang, "Liquidity Shocks and
   Stock Market Reactions", THE REVIEW OF FINANCIAL STUDIES, Vol. 27, Issue
   5 (May 2014), pp. 1434-1485. Venue/volume/issue/pages confirmed this
   session against Oxford Academic
   (academic.oup.com/rfs/article-abstract/27/5/1434/1581069) and
   RePEc/EconPapers (RePEc:oup:rfinst:v:27:y:2014:i:5:p:1434-1485).
 * Yakov Amihud, "Illiquidity and stock returns: cross-section and
   time-series effects" (Journal of Financial Markets, 2002) — the source
   of the ILLIQ measure this family is built on, cited as such by Bali et
   al. and quoted through them below rather than from an independent read.
   HONEST FLAG: I did not fetch Amihud (2002) itself this session; the
   ILLIQ definition implemented here is the one Bali et al. state, in their
   words.

   WHAT I ACTUALLY READ: SSRN (abstract_id=2055472) and the Oxford Academic
   full text both refuse automated fetches (HTTP 403). The methodology
   quoted below was read from the authors' working-paper version — Koc
   University-TUSIAD Economic Research Forum Working Paper No. 1304,
   February 2013, draft dated July 3 2012, retrieved from EconStor
   (econstor.eu/bitstream/10419/108624/1/erf_wp_1304.pdf) and
   text-extracted in full this session. HONEST FLAG: the working paper's
   abstract reports the long-short spread as "more than 1% per month" while
   its Table 2 reports 1.23%/month; the published RFS abstract (read on
   Oxford Academic's abstract page this session) states the range "0.70% to
   1.20% per month" across shock measures. That is a real discrepancy
   between the two versions and it is NOT resolved here — the RFS numbers
   are the ones to trust, and the working-paper table values quoted below
   are labelled as working-paper values wherever they appear.

VERIFIED MECHANISM — and the scoping brief was WRONG about the direction
=======================================================================
I was asked to confirm whether this is a REVERSAL after the shock or a
CONTINUATION. It is a CONTINUATION (underreaction). The brief's framing
("stocks with a sudden increase in illiquidity are initially
underpriced/overreacted-to and their returns partially reverse") inverts
the paper's finding; the brief's parenthetical guess of a "6-month
underreaction" is the correct one. Quoted from the working paper's abstract:

  "We find that negative and persistent liquidity shocks not only lead to
   lower contemporaneous returns, but also predict negative returns for up
   to six months in the future. Long-short portfolios sorted on past
   liquidity shocks generate a raw and risk-adjusted return of more than 1%
   per month."

And from Section 1: "There is a continuation... This evidence suggests that
the market underreacts to firm level liquidity shocks. Although stock prices
drop immediately upon negative liquidity shocks, the reaction is not
complete."

So a stock whose illiquidity SPIKES keeps underperforming; a stock whose
illiquidity FALLS keeps outperforming. The trade is long improving
liquidity, short deteriorating liquidity — the opposite sign to what a
reversal reading would put on.

THE TWO FORMULAS, quoted verbatim from Section 2.1
 * ILLIQ: "Following Amihud (2002), we measure the illiquidity of a stock i
   in month t, denoted ILLIQ, as the average daily ratio of the absolute
   stock return to the dollar trading volume within the month:
   ILLIQ_{i,t} = Avg[ |R_{i,d}| / VOLD_{i,d} ], where R_{i,d} and VOLD_{i,d}
   are the daily return and dollar trading volume for stock i on day d,
   respectively. A firm is required to have at least 15 daily return
   observations in month t. The Amihud's illiquidity measure is scaled by
   10^6."
 * LIQU, the shock: "we define liquidity shock, denoted LIQU, as the
   negative difference between ILLIQ and its past 12-month average, and
   standardize the difference by its volatility as follows:
   LIQU_{i,t} = -(ILLIQ_{i,t} - AVGILLIQ_{i|t-12,t-1}) / SDILLIQ_{i|t-12,t-1},
   where AVGILLIQ and SDILLIQ are the mean and standard deviation of
   illiquidity over the past 12 months, respectively."
 * THE SIGN, from their own footnote 6, which settles the question the
   brief got backwards: "According to equation (2), positive (negative)
   liquidity shock indicates an increase (decrease) in liquidity relative to
   its past 12-month average."
 * WHY THE SD STANDARDIZATION IS NOT COSMETIC, Section 2.1: "the average
   correlation coefficient between ILLIQ and its monthly volatility... is
   0.93, and that between ILLIQ and long-term illiquidity volatility...
   is 0.74." Without dividing by SDILLIQ the shock measure is dominated by
   the illiquidity LEVEL, which is a different (and already well-known)
   anomaly. This is exactly what ILLIQ_MEAN_SCALED_MODE below tests.

MEASUREMENT AND HOLDING WINDOWS, both asked about and both confirmed
 * SHOCK WINDOW: one month (month t) for ILLIQ itself, against a baseline
   of the PAST 12 MONTHS (t-12 .. t-1) for the mean and standard deviation.
   Total history consumed: 13 months.
 * HOLDING WINDOW: the paper's headline sort is one month ahead —
   Section 3.1: "Decile portfolios are formed every month from July 1963 to
   November 2010... by sorting stocks based on their past month liquidity
   shocks (denoted by LIQU), where Decile 1 contains stocks with the lowest
   LIQU, and Decile 10 contains stocks with the highest LIQU." The
   SIX-MONTH figure is the horizon over which the continuation persists
   ("predict negative returns for up to six months in the future"), not a
   single six-month holding period. Both are tested here as separate specs.
 * Working-paper Table 2, Panel A: "the average raw return on the LIQU
   portfolios increases almost monotonically from 0.35% to 1.58% per month.
   Effectively, the average raw return difference between Decile 1 and 10
   (i.e., high LIQU vs. low LIQU) is 1.23% per month with a Newey-West
   (1987) t-statistic of 5.86." Three-factor alpha on the spread: "1.42%
   per month with a Newey-West t-statistic of 6.67". Deciles, monthly
   rebalance. (See the HONEST FLAG above on working-paper vs RFS values.)


WHAT THIS IMPLEMENTATION CANNOT REPRODUCE, stated up front
==========================================================
 1. DOLLAR VOLUME IS A PROXY. Bali et al. use CRSP's VOLD. This family
    computes close x share volume off yfinance's adjusted close and
    as-shipped volume. That is the standard proxy, but it is a proxy, and
    it is imperfect in a specific way worth naming: the close is
    split-AND-dividend-adjusted while volume is not dividend-adjusted, so
    the product is not a literal traded dollar amount. It is very nearly
    monotone in one, which is what a cross-sectional RANK needs — and the
    LIQU measure then differences and standardizes each ticker against its
    OWN 12-month history, which removes any per-ticker level scaling that
    is stable across the window. A split inside the window is not stable
    across the window and is the residual known defect.
 2. THE UNIVERSE IS BACKWARDS FOR THIS ANOMALY. The paper's effect is
    explicitly concentrated where this project's universe is thinnest:
    "the documented effect is stronger for small stocks, stocks with low
    analyst coverage and institutional holdings, and for less liquid
    stocks." This family runs on the S&P 500 — the largest, most liquid,
    most heavily covered 500 US stocks, i.e. the subsample in which the
    paper itself predicts the WEAKEST effect. A null here is therefore
    substantially weaker evidence against the anomaly than a null in a
    representative universe would be, and must not be reported as
    "Bali et al. does not replicate". It is declared before the run because
    it is a property of the universe, not of the result.
 3. NYSE/AMEX/NASDAQ 1963-2010 vs S&P 500 2015-2026. Different era,
    different breadth, ~11.6 years of formations against their 47.

CALENDAR MONTHS vs 21-TRADING-DAY BLOCKS: the harness forms every
`holding_days` trading days, so "month" here is a 21-trading-day block
counted backwards from the formation date, not a calendar month. The
paper's 15-daily-observation floor is applied to those blocks unchanged.
This is a real deviation and it is the same one cross_sectional_seasonality
.py discloses; it makes the ILLIQ blocks slightly more uniform in length
than real calendar months, which if anything helps the measure.

POINT-IN-TIME CORRECTNESS, structurally: the harness hands SignalFn a view
sliced to rows <= the formation date, so the shock window CANNOT reach into
the holding window — the holding window's rows are not in the frame. Within
the view, the block algebra below counts strictly BACKWARD from the last
row, so the newest block ends ON the formation date and every baseline
block is strictly older. There is no parameter setting under which a
baseline block overlaps the hold.


FAMILY (8 definitions)
======================
 * 3 holding horizons in ILLIQ_HOLDING_HORIZONS_DAYS (21, 63, 126 trading
   days ~ 1, 3 and 6 months) x 2 portfolio modes (long_short,
   long_universe_hedged) = 6 standardized-LIQU definitions, decile legs,
   12-month baseline. The three horizons ARE the paper's claim: a
   continuation that persists "up to six months" should show up at all
   three and fade, not appear at one.
 * + 1 MEAN-SCALED robustness at hold 21, long_short: -(ILLIQ_t - AVG)/AVG
   instead of / SD. Isolates the paper's SD-standardization choice, which
   Section 2.1 motivates with the 0.93 level-vs-volatility correlation. A
   family that works identically without it was never testing the shock.
 * + 1 SIX-MONTH BASELINE at hold 21, long_short: the same standardized
   measure against a 6-month rather than 12-month baseline window. Tests
   whether the 12-month convention is doing work or is arbitrary.
 = 8, asserted against ILLIQ_SPEC_CEILING in _build_illiq_family.

DIRECTION-VARIANT COUNTING: no reversed variants, for the reason
cross_sectional_patterns.py's docstring gives — a long-short decile
portfolio is antisymmetric under direction reversal up to identical costs.
The paper's own direction (long high LIQU = improving liquidity, short low
LIQU = deteriorating liquidity) is used once per definition. NOTE that this
makes the family a genuine directional test: if the brief's reversal
reading had been right, every long_short spec here would come out
SYSTEMATICALLY NEGATIVE rather than merely null.


PRODUCTION RESULT — A CLEAN, UNIFORM HONEST NEGATIVE
====================================================
Run 2026-08-28 over 2015-01-07 .. 2026-08-27 (run_tag
"illiq_build_2026-08-28", family_key "liquidity_shock_delta_illiq", 8 rows
in cross_sectional_trial_results). 0 skipped formations, ~45.0 names per
leg, 2925 realized trading days, n_trials = 8. Annualized Sharpe, net of
costs (n_form varies with the holding horizon: 140 at hold 21, 47 at 63, 24
at 126):

    illiq_shock_std_h63_ls          -0.0645   DSR 0.210
    illiq_shock_mean_scaled_h21_ls  -0.1729   DSR 0.119
    illiq_shock_std_h126_lh         -0.2899   DSR 0.057
    illiq_shock_std_h21_ls          -0.3044   DSR 0.050
    illiq_shock_std_h63_lh          -0.3254   DSR 0.044
    illiq_shock_std_h21_lh          -0.3736   DSR 0.030
    illiq_shock_std_h126_ls         -0.3824   DSR 0.028
    illiq_shock_std_base6m_h21_ls   -0.4168   DSR 0.022

ALL EIGHT DEFINITIONS ARE NEGATIVE, none by a large margin and none close
to a usable DSR. There is no horizon at which the continuation shows up: 1
month (-0.3044), 3 months (-0.0645) and 6 months (-0.3824) are all negative
in the long-short mode, so the paper's "up to six months" persistence
profile is absent rather than merely attenuated. Neither robustness arm
rescues it — dropping the SD standardization (-0.1729) and shortening the
baseline to 6 months (-0.4168) both stay negative.

WHAT THE UNIFORM NEGATIVITY DOES AND DOES NOT MEAN. Because no reversed
variants are declared, a systematic negative across every long_short spec
is exactly the shape the OPPOSITE sign convention would produce. So it is
worth stating plainly what this run cannot distinguish: an anomaly that is
simply absent here, versus one that runs the other way in this universe.
The magnitudes argue for "absent" — a genuine inverted effect of the
paper's size (1.23%/month) would show far more than a -0.06 to -0.42
Sharpe, and the three horizons do not order themselves monotonically the
way a real signal of either sign should. Flagged rather than resolved,
because this family was not designed to answer it and reading a tradeable
reversed strategy out of these numbers would be exactly the post-hoc
direction-flip this project's trial-counting discipline exists to prevent.

SCOPE OF THE NEGATIVE — this one is weaker evidence than it looks, and the
reason was declared before the run (see "WHAT THIS IMPLEMENTATION CANNOT
REPRODUCE", item 2). Bali et al. report the effect is "stronger for small
stocks, stocks with low analyst coverage and institutional holdings, and
for less liquid stocks". This ran on the S&P 500 — precisely the
large-cap, heavily-covered, highly-liquid subsample where the paper itself
predicts the effect is weakest, over 11.6 years against their 47, with 143
of the point-in-time universe's tickers resolving no price data (the
project's known delisted-securities gap). A null here is close to the null
the paper would predict for this universe. It must NOT be reported as
"Bali, Peng, Shen & Tang does not replicate"; the honest statement is that
Delta-ILLIQ is not harvestable in S&P 500 large-caps over 2015-2026, which
is roughly what the source paper implies.
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

ILLIQ_FAMILY = "liquidity_shock_delta_illiq"

# Deciles — Section 3.1 sorts "all stocks trading at NYSE/AMEX/NASDAQ into
# decile portfolios based on their liquidity shocks".
ILLIQ_RANK_FRACTION = 0.1

# 21 trading days ~ one month. 63 ~ one quarter, 126 ~ the paper's six-month
# continuation horizon.
ILLIQ_HOLDING_HORIZONS_DAYS = (21, 63, 126)

TRADING_DAYS_PER_MONTH = 21

# "A firm is required to have at least 15 daily return observations in
# month t" (Section 2.1), applied to every block, baseline blocks included.
MIN_DAILY_OBSERVATIONS_PER_BLOCK = 15

# "The Amihud's illiquidity measure is scaled by 10^6" (Section 2.1). Pure
# units — a positive constant multiplying every ticker's ILLIQ identically
# cannot change a cross-sectional rank, and cannot change LIQU at all
# (which differences and divides it away). Kept so the intermediate ILLIQ
# values this module exposes are on the paper's scale and comparable to its
# tables, rather than being ~1e-6 numbers that only happen to rank right.
AMIHUD_SCALE = 1e6

# The paper's baseline is the past 12 months (t-12 .. t-1). 6 is the
# robustness variant. Both are baseline LENGTHS, exclusive of month t.
ILLIQ_BASELINE_MONTHS = 12
ILLIQ_SHORT_BASELINE_MONTHS = 6

# How much of the baseline window must actually resolve. The paper requires
# the full 12 months; requiring all 12 here (each already gated by the
# 15-daily-observation floor) would drop otherwise-fine names for a single
# transient yfinance volume gap, so the floor is three quarters of the
# window — 9 of 12, 5 of 6 (ceil). Deliberately a declared constant rather
# than an inline number: it IS a deviation from the paper and belongs where
# a reader looking for deviations will find it. A standard deviation needs
# >= 2 observations regardless, which this floor always satisfies.
MIN_BASELINE_COVERAGE_FRACTION = 0.75

ILLIQ_SPEC_CEILING = 8

ShockMode = Literal["standardized", "mean_scaled"]

ILLIQ_STANDARDIZED_MODE: ShockMode = "standardized"
ILLIQ_MEAN_SCALED_MODE: ShockMode = "mean_scaled"

ILLIQ_CITATION = (
    "Bali, Peng, Shen & Tang, 'Liquidity Shocks and Stock Market Reactions', Review of "
    "Financial Studies 27(5), 2014, pp. 1434-1485, building on Amihud (2002) ILLIQ; "
    "methodology quoted from the authors' Koc University-TUSIAD ERF Working Paper 1304 "
    "(Feb 2013), read in full 2026-08-28 — LIQU = -(ILLIQ_t - AVGILLIQ_{t-12,t-1}) / "
    "SDILLIQ_{t-12,t-1}; the market UNDERREACTS, so negative liquidity shocks predict "
    "CONTINUED negative returns for up to six months (a continuation, not a reversal), "
    "with a decile long-short spread of 1.23%/month (t=5.86) in the working paper and "
    "0.70-1.20%/month across shock measures in the published abstract."
)

# Longest history any spec needs (13 blocks) plus generous slack, in
# calendar days, so the first formation has its full baseline.
ILLIQ_PRICE_PADDING_CALENDAR_DAYS = 900


def amihud_illiq_daily_ratio(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """The per-day |R| / VOLD ratio, scaled by 10^6 — the quantity ILLIQ
    averages over a month (Section 2.1).

    Non-positive dollar volume becomes NaN rather than an infinity: a
    zero-volume day is a day with no usable illiquidity observation, and
    letting it divide through would hand that ticker an infinite ILLIQ that
    would then dominate every mean and standard deviation downstream. The
    15-observation floor applied per block is what turns those NaNs into a
    principled exclusion rather than a silent thinning of the average."""
    returns = close.pct_change(fill_method=None)
    dollar_volume = close * volume
    dollar_volume = dollar_volume.where(dollar_volume > 0)
    return returns.abs().div(dollar_volume) * AMIHUD_SCALE


def _block_illiq(daily_ratio: pd.DataFrame, block_index: int) -> pd.Series:
    """ILLIQ for one 21-trading-day block counted BACKWARD from the end of
    the view: block 0 is the newest (month t, ending on the formation
    date), block 1 the one before it, and so on.

    Counting backward from the formation date rather than forward from the
    start of the view is what makes the block grid independent of how much
    history a particular formation happens to have — the newest block is
    always exactly the 21 trading days that just ended, for every formation
    and every spec, so month t means the same thing throughout.

    Returns NaN for any ticker with fewer than
    MIN_DAILY_OBSERVATIONS_PER_BLOCK usable daily ratios in the block —
    the paper's own floor."""
    n_rows = len(daily_ratio)
    stop = n_rows - block_index * TRADING_DAYS_PER_MONTH
    start = stop - TRADING_DAYS_PER_MONTH
    if start < 0:
        return pd.Series(np.nan, index=daily_ratio.columns, dtype=float)
    block = daily_ratio.iloc[start:stop]
    illiq = block.mean()
    return illiq.where(block.count() >= MIN_DAILY_OBSERVATIONS_PER_BLOCK)


def signal_liquidity_shock(
    data: CrossSectionalData,
    *,
    baseline_months: int = ILLIQ_BASELINE_MONTHS,
    mode: ShockMode = ILLIQ_STANDARDIZED_MODE,
) -> pd.Series:
    """Bali/Peng/Shen/Tang's LIQU. Higher = liquidity IMPROVED relative to
    the trailing baseline = ranked into the long leg (select_leg_tickers
    takes the top), which is the paper's own direction under its footnote-6
    sign convention.

    "standardized" is equation (2) exactly:
        LIQU = -(ILLIQ_t - AVGILLIQ_{t-12,t-1}) / SDILLIQ_{t-12,t-1}
    "mean_scaled" replaces the denominator with AVGILLIQ — the robustness
    variant isolating the SD standardization (see the module docstring).
    A raw undivided difference is deliberately NOT offered: ILLIQ levels
    span orders of magnitude across a cross-section, so an unscaled
    difference would rank almost purely on the illiquidity LEVEL, which is
    Amihud's separate anomaly rather than this one.

    NaN (the SignalFn contract's "no valid signal today") whenever month t
    is unusable, the baseline is thinner than MIN_BASELINE_COVERAGE_FRACTION
    of its window, or the denominator is non-positive — a zero SD means a
    ticker whose illiquidity never moved, for which a standardized shock is
    undefined rather than infinite."""
    if data.volume is None:
        raise ValueError(
            "signal_liquidity_shock needs CrossSectionalData.volume — the spec must set "
            "requires_volume=True so run_cross_sectional_backtest checks for it on formation zero."
        )
    close = data.close
    empty = pd.Series(np.nan, index=close.columns, dtype=float)
    needed_rows = (baseline_months + 1) * TRADING_DAYS_PER_MONTH
    if len(close) < needed_rows:
        return empty

    # Computed over the WHOLE view before slicing, so the oldest block does
    # not silently lose its first day to pct_change's leading NaN.
    daily_ratio = amihud_illiq_daily_ratio(close, data.volume)

    current = _block_illiq(daily_ratio, 0)
    baseline = pd.DataFrame(
        {i: _block_illiq(daily_ratio, i) for i in range(1, baseline_months + 1)}
    ).T

    min_baseline = int(np.ceil(MIN_BASELINE_COVERAGE_FRACTION * baseline_months))
    enough_baseline = baseline.count() >= min_baseline
    avg_illiq = baseline.mean()

    if mode == ILLIQ_STANDARDIZED_MODE:
        denominator = baseline.std(ddof=1)
    elif mode == ILLIQ_MEAN_SCALED_MODE:
        denominator = avg_illiq
    else:
        raise ValueError(f"unknown liquidity-shock mode {mode!r}")

    usable = enough_baseline & current.notna() & avg_illiq.notna() & (denominator > 0)
    shock = -(current - avg_illiq) / denominator
    return shock.where(usable).reindex(close.columns)


def _spec(
    *,
    pattern_id: str,
    holding_days: int,
    portfolio: Literal["long_short", "long_universe_hedged"],
    baseline_months: int,
    mode: ShockMode,
) -> CrossSectionalSpec:
    return CrossSectionalSpec(
        pattern_id=pattern_id,
        family=ILLIQ_FAMILY,
        citation=ILLIQ_CITATION,
        signal_fn=partial(
            signal_liquidity_shock,
            baseline_months=baseline_months,
            mode=mode,
        ),
        # month t plus the baseline window, plus one block of cushion so the
        # OLDEST baseline block is a full 21 rows rather than a truncated one.
        lookback_days=(baseline_months + 2) * TRADING_DAYS_PER_MONTH,
        holding_days=holding_days,
        portfolio=portfolio,
        rank_fraction=ILLIQ_RANK_FRACTION,
        requires_volume=True,
    )


def _build_illiq_family() -> list[CrossSectionalSpec]:
    """The pre-declared family, built once at import so its length is fixed
    before any data is touched — the literal here IS the n_trials
    denominator screen_cross_sectional_universe deflates against."""
    specs: list[CrossSectionalSpec] = []
    for hold in ILLIQ_HOLDING_HORIZONS_DAYS:
        for portfolio in ("long_short", "long_universe_hedged"):
            short_tag = "ls" if portfolio == "long_short" else "lh"
            specs.append(
                _spec(
                    pattern_id=f"illiq_shock_std_h{hold}_{short_tag}",
                    holding_days=hold,
                    portfolio=portfolio,
                    baseline_months=ILLIQ_BASELINE_MONTHS,
                    mode=ILLIQ_STANDARDIZED_MODE,
                )
            )
    specs.append(
        _spec(
            pattern_id="illiq_shock_mean_scaled_h21_ls",
            holding_days=21,
            portfolio="long_short",
            baseline_months=ILLIQ_BASELINE_MONTHS,
            mode=ILLIQ_MEAN_SCALED_MODE,
        )
    )
    specs.append(
        _spec(
            pattern_id="illiq_shock_std_base6m_h21_ls",
            holding_days=21,
            portfolio="long_short",
            baseline_months=ILLIQ_SHORT_BASELINE_MONTHS,
            mode=ILLIQ_STANDARDIZED_MODE,
        )
    )
    assert len(specs) == ILLIQ_SPEC_CEILING, (
        f"liquidity-shock family is {len(specs)} specs, not the pre-declared "
        f"{ILLIQ_SPEC_CEILING} — the ceiling is the honest n_trials denominator and must be "
        "updated deliberately, never drifted past."
    )
    return specs


ILLIQ_SPECS: list[CrossSectionalSpec] = _build_illiq_family()


def run_illiq_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> tuple[list[CrossSectionalScreeningResult], list[str]]:
    """THE production entry point. Returns (results, tickers that resolved
    no price data) — the missing-ticker list is a required part of the
    result, not a log line.

    Universe: get_universe_over(start, end), the survivorship-free
    point-in-time S&P 500 candidate pool, gated per formation inside the
    harness. `start` must be >= MEMBERSHIP_DATA_START.

    Fetches via get_daily_ohlcv rather than get_price_history because this
    family's signal genuinely needs VOLUME (there is no dollar volume, and
    so no Amihud ILLIQ, without it). Only close and volume are passed on to
    CrossSectionalData; open/high/low are fetched by that call and dropped,
    which is the accepted cost of the one batched call that carries
    volume."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Liquidity-shock screening start {start.isoformat()} predates point-in-time "
            f"membership coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that "
            "date would silently see an empty universe."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else CrossSectionalConfig()
    config.formation_start = start

    universe = get_universe_over(start, end)
    padded_start = start - timedelta(days=ILLIQ_PRICE_PADDING_CALENDAR_DAYS)
    frames, missing_price = provider.get_daily_ohlcv(universe, padded_start, end)
    close = frames["close"]
    if close.empty:
        return [], missing_price

    data = CrossSectionalData(close=close, volume=frames["volume"])
    results = screen_cross_sectional_universe(data, ILLIQ_SPECS, config)
    return results, missing_price
