"""Round C pattern families: the two highest-priority cross-sectional
directions the literature review identified, expressed against
cross_sectional.py's harness. Every definition is individually cited,
matching intraday_patterns.py's convention exactly, and the whole family
is a bounded literal — ROUND_C_FAMILY, currently 30 definitions — whose
size is the honest n_trials denominator for the DSR correction, same
discipline as every prior round.

Family (a), disposition-effect cluster:
 * George & Hwang, "The 52-Week High and Momentum Investing" (Journal of
   Finance, 2004): nearness of the current price to its trailing 52-week
   high is a cross-sectional predictor of future returns — long the
   nearest decile, short the farthest — reported to dominate plain
   trailing-return momentum. Behavioral mechanism: traders anchor on the
   52-week high (a universally published reference point) and underreact
   to news that pushes price toward it.
 * Grinblatt & Han, "Prospect Theory, Mental Accounting, and Momentum"
   (Journal of Financial Economics, 2005): the capital-gains overhang —
   how far price sits above the average holder's reference (purchase)
   price, with the reference price built as a turnover-weighted average of
   past prices — predicts returns cross-sectionally: disposition-effect
   selling pressure makes prices underreact for stocks with large
   unrealized gains, so high-overhang stocks subsequently outperform.

Family (b), overnight-vs-intraday decomposition ("tug of war"):
 * Lou, Polk & Skouras, "A Tug of War: Overnight Versus Intraday Expected
   Returns" (Journal of Financial Economics, 2019): decompose each day's
   close-to-close return into an overnight component (prior close -> open)
   and an intraday component (open -> close); each component's
   cross-sectional ranking persists in its own future component while the
   cross-period effects reverse. Tested here by ranking on each trailing
   component separately.

Direction-variant counting, decided deliberately: intraday_patterns.py's
Gao family tested reverse=True as a co-equal alternative because its
single-ticker entry/exit rules are NOT symmetric under sign flip (the
threshold state machine, cost timing, and hold length all change). A
long-short decile portfolio IS antisymmetric under direction reversal up
to (identical) costs — the reversed rule's return stream is exactly the
negation — so listing reversed variants here would double n_trials while
adding literally zero information (a strongly negative Sharpe already IS
the reversed result). Each definition below therefore uses its
literature's own direction once, and only genuinely distinct parameter
choices (lookback, horizon, decile width, portfolio construction) are
counted as trials.
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

# The same hard family-size ceiling every prior round respected, for the
# same reason: deflated_sharpe.py's n_trials correction stays statistically
# meaningful in the tens-of-trials range it was validated for (see that
# module's docstring and MIN_TRIALS_FOR_DSR's simulation evidence) — an
# unbounded pattern generator would either break the correction or
# invalidate it. Enforced by an assertion in _build_round_c_family, not
# just documented.
ROUND_C_PATTERN_CEILING = 40

# A signal window with fewer than this fraction of its rows populated is
# refused (NaN signal) rather than computed on whatever little data exists.
# The concrete failure this prevents: a ticker listed 3 months ago has a
# trailing "52-week high" equal to roughly its recent max, so its nearness
# ratio is mechanically ~1.0 and it would systematically (and spuriously)
# land in the long decile — an IPO-recency artifact, not anchoring. 0.8 is
# an engineering judgment call at the same disclosed-not-calibrated
# register as intraday_patterns.py's GAO_MIN_OPEN_RETURN.
MIN_SIGNAL_OBS_FRACTION = 0.8

# --- Grinblatt & Han turnover proxy -----------------------------------
# Grinblatt & Han (2005) weight past prices by TURNOVER — the fraction of
# shares outstanding traded — which needs shares outstanding, a field this
# project's free OHLCV data does not carry. Proxy: scale each day's volume
# by its own trailing mean and by an assumed typical large-cap daily
# turnover level of 1% — i.e. treat "average recent volume" as 1% of the
# float turning over, the right order of magnitude for US large caps
# (annual share turnover of roughly 100-250%, e.g. Lo & Wang, "Trading
# Volume: Definitions, Data Analysis, and Implications of Portfolio
# Theory", Review of Financial Studies, 2000, report NYSE/AMEX weekly
# turnover averaging ~0.78% in their sample — order 0.1-0.2% daily — with
# strong secular growth since; ~1%/day is the modern large-cap ballpark).
# The level constant matters only through the reference price's effective
# decay half-life (ln 2 / turnover ~= 69 trading days at 1%), and the
# truncated lookbacks below are sized to capture ~92%/99% of that weight —
# so a factor-of-2 error in the assumed level shifts the effective
# averaging horizon, not the sign or structure of the signal. Disclosed
# approximation, not a calibrated constant.
ASSUMED_MEAN_DAILY_TURNOVER = 0.01
# One quarter of trading days for the volume normalization mean — long
# enough to smooth earnings-day volume spikes, short enough to adapt to
# genuine liquidity-regime changes (and to a split's volume-level jump
# within a quarter). Judgment call, disclosed as such.
TURNOVER_NORMALIZATION_WINDOW = 63
# rolling(...).mean() min_periods: a third of the window, so early rows get
# a coarser-but-real mean rather than NaN'ing out the first quarter of
# every ticker's usable history. Mirrors the window-fraction reasoning
# above, not independently calibrated.
TURNOVER_NORMALIZATION_MIN_PERIODS = TURNOVER_NORMALIZATION_WINDOW // 3


def signal_52_week_high_nearness(history: CrossSectionalData, *, lookback_days: int = 252) -> pd.Series:
    """George & Hwang (2004): nearness = P_t / max(P over the trailing 52
    weeks), computed per ticker at the formation date's close. Long the
    top decile (nearest the high), short the bottom — the paper's own
    direction. NaN below MIN_SIGNAL_OBS_FRACTION coverage (IPO-recency
    guard, see that constant)."""
    window = history.close.iloc[-lookback_days:]
    last = window.iloc[-1]
    high = window.max()
    n_obs = window.notna().sum()
    signal = last / high
    signal[n_obs < int(lookback_days * MIN_SIGNAL_OBS_FRACTION)] = np.nan
    return signal


def _turnover_proxy(volume: pd.DataFrame) -> pd.DataFrame:
    """Per-day pseudo-turnover in [0, 1] — see ASSUMED_MEAN_DAILY_TURNOVER
    for the construction and its disclosed limits. Clipped at 1.0 because
    the Grinblatt-Han recursion reads turnover as a probability (the
    chance a share last traded at that day's price); a proxy value above 1
    is a normalization artifact, not a >100% chance."""
    mean_volume = volume.rolling(
        TURNOVER_NORMALIZATION_WINDOW, min_periods=TURNOVER_NORMALIZATION_MIN_PERIODS
    ).mean()
    proxy = ASSUMED_MEAN_DAILY_TURNOVER * volume / mean_volume
    return proxy.clip(lower=0.0, upper=1.0)


def signal_capital_gains_overhang(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Grinblatt & Han (2005) capital-gains overhang, daily-frequency and
    truncated. Their reference price is
        RP_t = k^-1 * sum_n [ V_{t-n} * prod_{tau<n} (1 - V_{t-n+tau}) ] * P_{t-n},
    a turnover-weighted average of past prices where each price's weight is
    the probability shares last changed hands at it. That infinite sum has
    an exact forward recursion, RP_t = V_t * P_t + (1 - V_t) * RP_{t-1}
    (each day, a fraction V_t of the float re-anchors at today's price),
    which is what is computed here — initialized at the truncated window's
    first price, so early prices carry the initialization mass the
    untruncated history would have distributed further back. Truncation is
    honest at the lookbacks used below: at the assumed ~1%/day turnover,
    252 days carries ~92% of the untruncated weight and 504 days ~99%
    (1 - 0.99^n), which is why those two windows — "reasonable truncated
    versions" of Grinblatt & Han's 1-5 year weekly windows — were chosen.

    The overhang is g = (P_t - RP_{t-1}) / P_t: reference price strictly
    from prices BEFORE the formation close being compared against it
    (Grinblatt & Han lag the reference price for the same
    no-mechanical-overlap reason). Long high overhang, short low — the
    paper's direction (disposition-effect selling pressure depresses
    high-gain stocks' prices today, so they subsequently outperform)."""
    closes = history.close.iloc[-lookback_days:]
    turnover = _turnover_proxy(history.volume).iloc[-lookback_days:]

    prices = closes.to_numpy(dtype=float)
    turn = np.nan_to_num(turnover.to_numpy(dtype=float), nan=0.0)
    n_rows, _n_tickers = prices.shape

    ref = np.full(prices.shape[1], np.nan)
    initialized = np.zeros(prices.shape[1], dtype=bool)
    # Rows 0 .. n_rows-2 only: the formation-day price (last row) must not
    # enter its own reference price — see the lag note above.
    for t in range(n_rows - 1):
        p = prices[t]
        v = turn[t]
        fresh = ~initialized & np.isfinite(p)
        ref[fresh] = p[fresh]
        initialized |= fresh
        update = initialized & np.isfinite(p)
        ref[update] = v[update] * p[update] + (1.0 - v[update]) * ref[update]

    last = prices[-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        overhang = (last - ref) / last

    signal = pd.Series(overhang, index=closes.columns)
    n_obs = closes.notna().sum()
    signal[n_obs < int(lookback_days * MIN_SIGNAL_OBS_FRACTION)] = np.nan
    signal[~np.isfinite(signal)] = np.nan
    return signal


def signal_component_persistence(
    history: CrossSectionalData, *, component: Literal["overnight", "intraday"], lookback_days: int
) -> pd.Series:
    """Lou, Polk & Skouras (2019): each ticker's trailing mean of one
    return component — overnight (o_t / c_{t-1} - 1) or intraday
    (c_t / o_t - 1) — as the ranking signal, long the top decile
    (the persistence direction: a component's own cross-sectional ranking
    continues in that component). The two components compound exactly to
    the close-to-close return, (1+overnight)*(1+intraday) = c_t/c_{t-1},
    which is what makes this a genuine decomposition and not two arbitrary
    features.

    Honest deviation from the paper, stated plainly: LPS's cleanest
    finding is component-to-component (past overnight predicts future
    OVERNIGHT), but harvesting a future overnight component alone requires
    a buy-at-close/sell-at-open round trip every single day — exactly the
    cost-per-unit-of-signal profile Rounds A/B established this project's
    10bps assumption destroys (LPS's own Section 5 concedes the point for
    their strategies). What is tested here is the tradeable version this
    round exists for: whether the decomposed component ranking predicts
    holdable multi-week TOTAL returns better than the undecomposed return
    does. Mean rather than sum over the window so tickers with a few
    missing days rank on the same scale as complete ones; no skip-month
    gap is applied (that convention belongs to 12-month plain momentum's
    short-term-reversal contamination, not to component persistence at
    these mostly-shorter lookbacks)."""
    if component == "overnight":
        comp = history.open / history.close.shift(1) - 1.0
    else:
        comp = history.close / history.open - 1.0
    window = comp.iloc[-lookback_days:]
    n_obs = window.notna().sum()
    signal = window.mean()
    signal[n_obs < int(lookback_days * MIN_SIGNAL_OBS_FRACTION)] = np.nan
    return signal


# Holding horizons in trading days: 1, 3, and 6 months — the horizons
# George & Hwang (2004) and Grinblatt & Han (2005) themselves report
# (their tables span 1-12 months with 6-month holds as the headline;
# 12-month holds are omitted here to keep the family inside the ceiling,
# the shorter horizons being where the cost-amortization question this
# round exists to answer actually bites).
HOLDING_HORIZONS_DAYS = (21, 63, 126)

# Lou/Polk/Skouras component-persistence lookbacks in trading days: one
# month (their monthly-formation base case), one quarter, and one year
# (their longer-window persistence evidence) — and holds of 1 and 3 months
# (component persistence decays faster than the disposition anomalies, so
# the 6-month hold is spent on the family where its literature actually
# reports it).
LPS_LOOKBACK_DAYS = (21, 63, 252)
LPS_HOLDING_DAYS = (21, 63)

# Grinblatt-Han reference-price lookbacks — see the truncation-coverage
# arithmetic in signal_capital_gains_overhang's docstring for why exactly
# these two.
CGO_LOOKBACK_DAYS = (252, 504)

GH52_CITATION = "George & Hwang, 'The 52-Week High and Momentum Investing' (Journal of Finance, 2004)"
CGO_CITATION = (
    "Grinblatt & Han, 'Prospect Theory, Mental Accounting, and Momentum' "
    "(Journal of Financial Economics, 2005)"
)
LPS_CITATION = (
    "Lou, Polk & Skouras, 'A Tug of War: Overnight Versus Intraday Expected Returns' "
    "(Journal of Financial Economics, 2019)"
)


def _build_round_c_family() -> list[CrossSectionalSpec]:
    """Assembles the full, fixed Round C family — currently 30 definitions
    (9 George-Hwang 52-week-high + 9 Grinblatt-Han overhang + 12
    Lou-Polk-Skouras component persistence), inside the hard 40-definition
    ceiling. This list's literal length is the n_trials denominator
    screen_cross_sectional_universe uses — every definition here counts,
    whether or not it survives the data floors."""
    specs: list[CrossSectionalSpec] = []

    # George-Hwang 52-week high: deciles and quintiles long-short at each
    # horizon (their decile sort is the headline; the quintile variant
    # tests sensitivity to the arbitrary 10% width), plus a
    # universe-hedged long-only decile (their anchoring story is
    # asymmetric — the long side is where underreaction-to-good-news
    # lives — so the long leg alone is a distinct, literature-motivated
    # hypothesis, hedged per cross_sectional.py's convention).
    for horizon in HOLDING_HORIZONS_DAYS:
        specs.append(
            CrossSectionalSpec(
                pattern_id=f"gh52_ls_decile_h{horizon}",
                family="disposition_52wk_high",
                citation=GH52_CITATION,
                signal_fn=partial(signal_52_week_high_nearness, lookback_days=252),
                lookback_days=252,
                holding_days=horizon,
                portfolio="long_short",
                rank_fraction=0.1,
            )
        )
    for horizon in HOLDING_HORIZONS_DAYS:
        specs.append(
            CrossSectionalSpec(
                pattern_id=f"gh52_ls_quintile_h{horizon}",
                family="disposition_52wk_high",
                citation=GH52_CITATION,
                signal_fn=partial(signal_52_week_high_nearness, lookback_days=252),
                lookback_days=252,
                holding_days=horizon,
                portfolio="long_short",
                rank_fraction=0.2,
            )
        )
    for horizon in HOLDING_HORIZONS_DAYS:
        specs.append(
            CrossSectionalSpec(
                pattern_id=f"gh52_long_hedged_decile_h{horizon}",
                family="disposition_52wk_high",
                citation=GH52_CITATION,
                signal_fn=partial(signal_52_week_high_nearness, lookback_days=252),
                lookback_days=252,
                holding_days=horizon,
                portfolio="long_universe_hedged",
                rank_fraction=0.1,
            )
        )

    # Grinblatt-Han overhang: two truncated reference-price windows at each
    # horizon (deciles), plus a quintile sensitivity variant at the shorter
    # window. lookback_days budgets extra rows for the turnover proxy's own
    # rolling normalization window on top of the reference-price window.
    for lookback in CGO_LOOKBACK_DAYS:
        for horizon in HOLDING_HORIZONS_DAYS:
            specs.append(
                CrossSectionalSpec(
                    pattern_id=f"cgo_ls_decile_l{lookback}_h{horizon}",
                    family="disposition_capital_gains_overhang",
                    citation=CGO_CITATION,
                    signal_fn=partial(signal_capital_gains_overhang, lookback_days=lookback),
                    lookback_days=lookback + TURNOVER_NORMALIZATION_WINDOW,
                    holding_days=horizon,
                    portfolio="long_short",
                    rank_fraction=0.1,
                    requires_volume=True,
                )
            )
    for horizon in HOLDING_HORIZONS_DAYS:
        specs.append(
            CrossSectionalSpec(
                pattern_id=f"cgo_ls_quintile_l252_h{horizon}",
                family="disposition_capital_gains_overhang",
                citation=CGO_CITATION,
                signal_fn=partial(signal_capital_gains_overhang, lookback_days=252),
                lookback_days=252 + TURNOVER_NORMALIZATION_WINDOW,
                holding_days=horizon,
                portfolio="long_short",
                rank_fraction=0.2,
                requires_volume=True,
            )
        )

    # Lou-Polk-Skouras: each component x lookback x horizon, deciles.
    for component in ("overnight", "intraday"):
        for lookback in LPS_LOOKBACK_DAYS:
            for horizon in LPS_HOLDING_DAYS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"lps_{component}_l{lookback}_h{horizon}",
                        family="overnight_intraday_tug_of_war",
                        citation=LPS_CITATION,
                        signal_fn=partial(
                            signal_component_persistence, component=component, lookback_days=lookback
                        ),
                        # +1 row so the overnight component's close.shift(1)
                        # has a real prior close on the window's first day.
                        lookback_days=lookback + 1,
                        holding_days=horizon,
                        portfolio="long_short",
                        rank_fraction=0.1,
                        requires_open=True,
                    )
                )

    assert len(specs) <= ROUND_C_PATTERN_CEILING, (
        f"Round C family has {len(specs)} definitions, over the {ROUND_C_PATTERN_CEILING} ceiling — "
        "see ROUND_C_PATTERN_CEILING for why this is a hard statistical limit, not a style rule."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    return specs


ROUND_C_FAMILY: list[CrossSectionalSpec] = _build_round_c_family()

# Calendar padding fetched BEFORE the requested screening start purely to
# warm up the longest signal lookback (504 + 63 = 567 trading rows for the
# 2-year Grinblatt-Han window; 567 trading days ~= 567 * 365 / 252 ~= 822
# calendar days, rounded up for holiday clustering). Formations themselves
# never occur in the padding — CrossSectionalConfig.formation_start pins
# them to the requested start — so no formation can predate the
# point-in-time membership data either.
PRICE_HISTORY_PADDING_CALENDAR_DAYS = 850


def run_round_c_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> tuple[list[CrossSectionalScreeningResult], list[str]]:
    """The full Round C screening pass — THE production entry point, to be
    launched when compute frees up (deliberately not run at scale as part
    of building this module; see the Round C commit message).

    Universe: get_universe_over(start, end) — every ticker that was an S&P
    500 member on ANY day of the screening window (the survivorship-free
    candidate pool primitive, see that function's docstring), NOT today's
    snapshot. `start` must be >= MEMBERSHIP_DATA_START, enforced loudly by
    get_universe_over itself. Per-formation-date eligibility inside the
    harness then narrows this pool to actual members on each formation
    date via was_member.

    Returns (screening results, tickers that resolved no price data). The
    missing list is a required part of the result, not a logging detail:
    per sp500_membership_history's KNOWN LIMITS, ~48% of departed members
    resolve nothing on yfinance, and the honest read of any Round C result
    requires knowing how much of the point-in-time universe was actually
    priceable."""
    if start < MEMBERSHIP_DATA_START:
        # get_universe_over would also reject this; checking here too makes
        # the error message name the actual fix.
        raise ValueError(
            f"Round C screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that date "
            "would silently see an empty universe."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else CrossSectionalConfig()
    config.formation_start = start

    universe = get_universe_over(start, end)
    padded_start = start - timedelta(days=PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    frames, missing = provider.get_daily_ohlcv(universe, padded_start, end)
    if not frames:
        return [], missing

    data = CrossSectionalData(close=frames["close"], open=frames["open"], volume=frames["volume"])
    results = screen_cross_sectional_universe(data, ROUND_C_FAMILY, config)
    return results, missing
