"""Build D2: long-horizon price reversal (De Bondt & Thaler, 1985) — a
dedicated, deliberately small (4-definition) cross-sectional family
expressed against cross_sectional.py's harness. This module is Round C's
sibling, not a subset of it: it shares the harness and (for its delisting
handling, see below) a generic harness option, but its family object,
n_trials denominator, and DSR correction are entirely its own — never
pooled with ROUND_C_FAMILY, ROUND_D_LPS_INTRADAY_FAMILY, or any other
family (see screen_cross_sectional_universe's own docstring: n_trials is
always len(specs) for whatever family object is actually passed to it, so
calling it here with THIS 4-spec family, in its own call, is what makes
n_trials=4 real rather than asserted).

CITATIONS:
 * De Bondt, W. F. M. & Thaler, R., "Does the Stock Market Overreact?"
   (Journal of Finance, 1985): stocks ranked into deciles by trailing
   3-5 year cumulative return subsequently reverse — the extreme past
   losers earn significantly higher returns over the following formation
   period than the extreme past winners. Behavioral mechanism: investors
   systematically overreact to a long run of good or bad news, pushing
   price too far from fundamental value; the correction, not a further
   move, is what the ranking period's cumulative return actually predicts.
 * Chopra, N., Lakonishok, J. & Ritter, J. R., "Measuring Abnormal
   Performance: Do Stocks Overreact?" (Journal of Financial Economics,
   1992): replicates the De Bondt & Thaler reversal after controlling for
   size and beta-based risk adjustment, and finds it concentrated in
   losers rather than symmetric across both legs — cited here alongside
   the original because it is the standard robustness check this
   literature is read together with, not a second, independent signal.

SIGNAL: trailing lookback-day cumulative return (P_t / P_{t-lookback} -
1), NEGATED so this harness's own top-quintile-is-long convention (see
select_leg_tickers / _target_weights in cross_sectional.py) puts the
biggest LOSERS (lowest raw trailing return) in the long leg and the
biggest WINNERS in the short leg — the paper's own reversal direction,
expressed as a sign flip on the raw signal rather than a harness-level
direction flag the harness does not have (see
signal_long_horizon_reversal). Quintile-ranked (rank_fraction=0.2), not
decile: De Bondt & Thaler's own headline result IS decile portfolios, but
this project's usable point-in-time universe is a few hundred names, not
NYSE's several thousand, so a decile leg here would often be thinner than
DEFAULT_MIN_NAMES_PER_LEG intends a "portfolio" (as opposed to a stock
pick) to be — quintiles trade some of the original paper's extremity for
a leg that is reliably a real cross-sectional portfolio at this
universe's scale.

TWO LOOKBACKS, ONE HOLD: 756 trading days (~36 months, De Bondt & Thaler's
own headline ranking window) as the primary definition, and 504 trading
days (~24 months, inside their reported 3-5 year range and Chopra/
Lakonishok/Ritter's own robustness horizon) as a disclosed robustness
variant. Every definition HOLDS for 756 trading days regardless of which
lookback ranked it — only the signal's own ranking window differs between
the two; the hold length is a separate, fixed design choice (see
D2_HOLDING_DAYS) matching the paper's own multi-year formation-to-hold
symmetry.

Family (4 defs): portfolio in {long_short, long_universe_hedged} x
lookback in {756, 504} — see _build_d2_family. long_universe_hedged is
included for the same reason cross_sectional_patterns.py includes it for
George & Hwang: De Bondt & Thaler's own results (and Chopra/Lakonishok/
Ritter's follow-up) find the reversal concentrated in the LOSER (long)
leg, not symmetric across both legs — an asymmetric-effect story is
exactly what a universe-hedged long-only variant is built to isolate
(hedging against the whole eligible universe rather than an unhedged raw
long, for the same self-financing-Sharpe reason cross_sectional.py's
module docstring gives).

============================================================================
THE SMALL-SAMPLE PROBLEM, CORRECTED PER THE 2026-08-26 AUDIT — read this
section before trusting any number this family produces
============================================================================
An earlier, uncorrected framing of this family claimed 7-8 independent
non-overlapping 756-day ranking-to-realization windows were available.
That claim was WRONG and has been retracted: this project's point-in-time
S&P 500 membership data (sp500_membership_history.MEMBERSHIP_DATA_START)
only covers 2015-01-07 onward — about 11.6 years to today, not the 20+
years the original 7-8 figure implicitly assumed. A formation dated before
MEMBERSHIP_DATA_START would see was_member answer False for literally
every ticker (a silent, total-universe failure — see that module's own
docstring on "no" vs "unknown" coverage), so no formation for this family
may ever be scheduled earlier than that date; screen_d2_reversal_family
enforces this the same way run_round_c_screening does for Round C.

The honest count: ~11.6 years of usable point-in-time history, divided by
this family's 756-trading-day hold, is only 3 FULL non-overlapping windows
(at the conventional 252-trading-day year, 11.6 * 252 / 756 ~= 3.9), plus
a PARTIAL fourth window covering roughly the remaining ~88% of one more
hold period — i.e. 3-4 truly statistically INDEPENDENT observations of
this strategy's long-run behavior, not 7-8. compute_d2_independent_window_
disclosure computes this precisely (from the actual replayed trading-day
count, not a static estimate) and screen_d2_reversal_family returns it as
an explicit, typed field of D2ScreeningSummary alongside the results --
never only as a comment here that a caller could fail to read.

OVERLAPPING QUARTERLY COHORTS, AND WHY THEY DO NOT FIX THE ABOVE: with
only 3-4 independent 756-day windows available, a NON-overlapping replay
(the harness's own historical default) would produce a single, extremely
noisy daily-return series with almost no formation-date diversification --
one unlucky formation date could dominate the whole result. Every spec in
this family therefore sets cohort_formation_days=D2_COHORT_FORMATION_DAYS
(63 trading days, ~1 quarter), which — per cross_sectional.py's own
opt-in overlapping-cohort machinery (see that module's docstring and
_replay_sleeve) — replays D2_HOLDING_DAYS // D2_COHORT_FORMATION_DAYS = 12
independent, quarter-staggered sleeves and blends whichever are
concurrently active on any given day by simple equal-weighted average.
This is the standard Jegadeesh-Titman construction for SMOOTHING an
overlapping-cohort return stream and is a genuine improvement in
statistical POWER (a less formation-date-dependent daily series, and a
larger nominal n_trading_days for the Sharpe/DSR calculation) — but it is
NOT a source of additional independent long-run observations: all 12
staggered sleeves are still drawing on the SAME underlying ~11.6 years of
price history, so the honest number of non-overlapping multi-year cycles
this backtest can actually speak to remains 3-4, exactly as it would
without overlapping cohorts. Both cautions are real and SEPARATE — the
DSR's own n_trials=4 multiple-comparisons correction (computed fresh in
this family's own screen_cross_sectional_universe call, per the module
docstring above) does not substitute for the independent-window caution,
and vice versa. n_trials=4 is itself below deflated_sharpe.
MIN_TRIALS_FOR_DSR (5), so the DSR correction proper will not even
compute for this family (DeflatedSharpeResult.dsr stays None,
dsr_floor_met stays False) -- only PSR-vs-zero will, and the returned
interpretation string says so plainly. That is not a bug to route around;
it is the honest consequence of deliberately keeping this family small and
undiluted (see the module-docstring's opening paragraph on never pooling
it with a larger family to manufacture DSR headroom).

============================================================================
DELISTING RETURNS -- WHY THIS FAMILY OPTS IN TO THE HARNESS'S SHUMWAY OPTION
============================================================================
cross_sectional.py's DEFAULT delisting handling — a name whose price
disappears mid-hold silently drops out of its leg's mean, liquidated at
its last available price — is a reasonable default for most families, but
is a POOR fit here specifically: this family's LONG leg is, by
construction, the extreme past LOSERS (see the signal direction above),
which is exactly the population most likely to delist mid-hold (financial
distress, bankruptcy, forced delisting). Silently dropping a delisted
loser understates exactly the risk the reversal trade is taking on,
flattering this family's Sharpe more than families whose long leg is not
adversely selected for distress. screen_d2_reversal_family's own default
CrossSectionalConfig therefore sets impute_delisting_returns=True,
applying config.imputed_delisting_return (Shumway 1997 / Shumway & Warther
1999's blended -42.5%, see cross_sectional.py's DEFAULT_IMPUTED_DELISTING_
RETURN) once, on the day a held name's price permanently stops appearing
in the loaded data — a real, disclosed, cited loss instead of a silent
drop. A caller who supplies their own CrossSectionalConfig to
screen_d2_reversal_family keeps whatever choice they made; only the
function's OWN default construction (config=None) opts in, per
cross_sectional.py's module docstring: this is a generic, opt-in harness
option, not something hardcoded only for this family, and every OTHER
family (Round C, Round D) continues silently dropping delisted names by
default exactly as before.
"""

from dataclasses import dataclass
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

# A signal window with fewer than this fraction of its rows populated is
# refused (NaN signal). This is a SECONDARY guard here, not the primary
# IPO-recency defense George & Hwang's trailing-max or Grinblatt & Han's
# turnover-weighted recursion need (see cross_sectional_patterns.py's own
# MIN_SIGNAL_OBS_FRACTION): a raw two-point cumulative return already gets
# a free NaN whenever its OWN window-start endpoint is missing (a recently
# listed ticker has no price 'lookback days ago', so P_{t-lookback} is
# itself NaN and the return is NaN with no extra code needed). What this
# guard catches instead is the residual case where BOTH endpoints happen
# to be populated but the window's interior is mostly missing (a data
# quality problem, not an IPO) -- rare given point-in-time membership
# already filters the candidate pool, but cheap to guard against, and kept
# at the same 0.8 register as the rest of this project's coverage floors
# for consistency, not because it was independently recalibrated here.
MIN_SIGNAL_OBS_FRACTION = 0.8


def signal_long_horizon_reversal(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """De Bondt & Thaler (1985): trailing lookback_days cumulative return,
    P_t / P_{t-lookback} - 1, computed per ticker at the formation date's
    close, then NEGATED so this harness's top-quintile-is-long convention
    (select_leg_tickers / _target_weights in cross_sectional.py) puts the
    biggest LOSERS (lowest raw trailing return -> highest negated signal)
    in the long leg and the biggest WINNERS in the short leg -- the
    paper's own reversal direction.

    Deliberately just the window's two endpoint prices, not a path-
    dependent statistic: this is exactly what "cumulative return over the
    ranking period" means in the cited literature, and unlike George &
    Hwang's trailing max or Grinblatt & Han's turnover-weighted recursion
    it needs no PRIMARY interior-coverage guard to avoid an IPO-recency
    artifact -- a ticker missing its own window-start price already gets a
    NaN signal for free (see MIN_SIGNAL_OBS_FRACTION above for the
    residual, secondary guard)."""
    window = history.close.iloc[-lookback_days:]
    first = window.iloc[0]
    last = window.iloc[-1]
    n_obs = window.notna().sum()
    cumulative_return = last / first - 1.0
    signal = -cumulative_return
    signal[n_obs < int(lookback_days * MIN_SIGNAL_OBS_FRACTION)] = np.nan
    signal[~np.isfinite(signal)] = np.nan
    return signal


D2_CITATION = (
    "De Bondt & Thaler, 'Does the Stock Market Overreact?' (Journal of Finance, 1985); "
    "Chopra, Lakonishok & Ritter, 'Measuring Abnormal Performance: Do Stocks Overreact?' "
    "(Journal of Financial Economics, 1992)"
)

# Every cohort's hold length -- fixed across both lookback variants, see
# module docstring's "TWO LOOKBACKS, ONE HOLD".
D2_HOLDING_DAYS = 756

# Overlapping-cohort cadence: ~1 quarter, matching this project's existing
# "1 quarter" convention (cross_sectional_patterns.HOLDING_HORIZONS_DAYS
# already uses 63 for the same reason). 756 / 63 = 12 exactly, so this
# family replays 12 evenly-staggered sleeves with no phase drift -- see
# module docstring's "OVERLAPPING QUARTERLY COHORTS" section for why this
# is necessary (statistical power) and does not fix the independent-window
# problem (it is drawn from the same underlying history either way).
D2_COHORT_FORMATION_DAYS = 63

# The signal's own ranking-window lookbacks -- see module docstring's "TWO
# LOOKBACKS, ONE HOLD".
D2_LOOKBACK_DAYS: tuple[int, int] = (756, 504)

# Quintiles, not deciles -- see module docstring's SIGNAL section for why.
D2_RANK_FRACTION = 0.2

# This family's fixed, pre-declared size -- the honest n_trials denominator
# for its OWN, never-pooled DSR correction (see module docstring). Not a
# growable ceiling like Round C's ROUND_C_PATTERN_CEILING: this is an
# exact, closed enumeration of {long_short, long_universe_hedged} x
# {756, 504}, asserted exactly in _build_d2_family rather than merely
# documented.
D2_N_TRIALS = 4


def _build_d2_family() -> list[CrossSectionalSpec]:
    """Assembles the full, fixed D2 family: every (portfolio, lookback)
    pair in {long_short, long_universe_hedged} x D2_LOOKBACK_DAYS, each
    holding D2_HOLDING_DAYS trading days with D2_COHORT_FORMATION_DAYS
    overlapping-cohort staggering. pattern_ids encode both axes so a
    screening result names its own definition unambiguously."""
    specs: list[CrossSectionalSpec] = []
    for portfolio in ("long_short", "long_universe_hedged"):
        for lookback in D2_LOOKBACK_DAYS:
            specs.append(
                CrossSectionalSpec(
                    pattern_id=f"d2_reversal_{portfolio}_l{lookback}",
                    family="long_horizon_price_reversal",
                    citation=D2_CITATION,
                    signal_fn=partial(signal_long_horizon_reversal, lookback_days=lookback),
                    lookback_days=lookback,
                    holding_days=D2_HOLDING_DAYS,
                    cohort_formation_days=D2_COHORT_FORMATION_DAYS,
                    portfolio=portfolio,
                    rank_fraction=D2_RANK_FRACTION,
                )
            )
    assert len(specs) == D2_N_TRIALS, (
        f"D2's long-horizon reversal family has {len(specs)} definitions, not the pre-declared "
        f"{D2_N_TRIALS} -- this family's entire point is being an exact, fixed enumeration of "
        "portfolio x lookback (see module docstring); a size drift here silently changes n_trials "
        "for every future run."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.family == "long_horizon_price_reversal" for s in specs)
    assert all(s.holding_days == D2_HOLDING_DAYS for s in specs)
    assert all(s.cohort_formation_days == D2_COHORT_FORMATION_DAYS for s in specs)
    assert all(s.rank_fraction == D2_RANK_FRACTION for s in specs)
    return specs


D2_FAMILY: list[CrossSectionalSpec] = _build_d2_family()

# Calendar padding fetched BEFORE the requested screening start purely to
# warm up the longer of the two signal lookbacks (756 trading days -- the
# 504-day variant needs less, but one padded fetch serves both). 756
# trading days ~= 756 * 365 / 252 == 1095 calendar days EXACTLY (756 is a
# clean 3 * 252); +45 calendar days (~4.1%) for holiday clustering --
# slightly more buffer than cross_sectional_patterns.PRICE_HISTORY_
# PADDING_CALENDAR_DAYS's own +28/822 (~3.4%) since three years of
# holidays compounds a little more than that constant's ~2.2-year longest
# lookback. Formations themselves never occur in the padding --
# CrossSectionalConfig.formation_start pins them to the requested start --
# so no formation can predate point-in-time membership data either.
D2_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 1140


@dataclass(frozen=True)
class D2IndependentWindowDisclosure:
    """The small-independent-window caution as typed data, not just a
    module-docstring comment a caller could fail to read -- see the module
    docstring's own "THE SMALL-SAMPLE PROBLEM" section for the full
    reasoning this summarizes."""

    n_trading_days_replayed: int
    holding_days: int
    n_full_independent_windows: int
    partial_window_fraction: float  # fraction of one more holding_days window the remainder covers
    text: str


def compute_d2_independent_window_disclosure(
    n_trading_days_replayed: int, holding_days: int = D2_HOLDING_DAYS
) -> D2IndependentWindowDisclosure:
    """Computes the true count of statistically INDEPENDENT (non-
    overlapping) holding_days-long windows the replayed data actually
    contains -- from the REAL replayed trading-day count (not a static,
    pre-data estimate), so this stays accurate as "today" moves and the
    real trading calendar (not a 252-day approximation) decides the exact
    figure. See module docstring's "THE SMALL-SAMPLE PROBLEM" section."""
    n_full = n_trading_days_replayed // holding_days if holding_days > 0 else 0
    remainder = n_trading_days_replayed - n_full * holding_days
    partial_fraction = (remainder / holding_days) if holding_days > 0 else 0.0
    upper = n_full + (1 if partial_fraction > 0 else 0)
    text = (
        f"D2 (long-horizon price reversal) INDEPENDENT-WINDOW DISCLOSURE -- read before trusting "
        f"any Sharpe/DSR number this family produces. Usable point-in-time history for this family "
        f"is {n_trading_days_replayed} trading days (MEMBERSHIP_DATA_START-gated: no formation may "
        f"predate 2015-01-07), and each cohort holds for {holding_days} trading days, so this "
        f"replay contains only {n_full} truly STATISTICALLY INDEPENDENT non-overlapping "
        f"{holding_days}-day window(s), plus a partial window covering {partial_fraction:.0%} of "
        f"one more -- call it {n_full}-{upper} independent observations of this strategy's "
        f"long-run behavior, corrected down from an earlier, retracted 7-8-window claim (see module "
        f"docstring). This family forms OVERLAPPING quarterly cohorts "
        f"(cohort_formation_days={D2_COHORT_FORMATION_DAYS}) for statistical POWER -- a smoother "
        f"daily return stream and a larger nominal sample for the Sharpe/DSR calculation -- but "
        f"overlapping cohorts share the same underlying price history and do NOT create additional "
        f"independent long-run observations; the honest number of non-overlapping cycles this "
        f"backtest can actually speak to is still {n_full}-{upper}, not the dozens of daily "
        f"observations or the {D2_HOLDING_DAYS // D2_COHORT_FORMATION_DAYS} staggered cohorts might "
        f"otherwise suggest. This is a SEPARATE caution from the DSR's own n_trials={D2_N_TRIALS} "
        f"multiple-comparisons correction (run in this family's own, never-pooled screening call) -- "
        f"neither substitutes for the other, and {D2_N_TRIALS} trials is itself below "
        "deflated_sharpe.MIN_TRIALS_FOR_DSR (5), so the DSR correction proper will not even compute "
        "for this family; only PSR-vs-zero will."
    )
    return D2IndependentWindowDisclosure(
        n_trading_days_replayed=n_trading_days_replayed,
        holding_days=holding_days,
        n_full_independent_windows=n_full,
        partial_window_fraction=partial_fraction,
        text=text,
    )


@dataclass
class D2ScreeningSummary:
    """screen_d2_reversal_family's full result: the screening results
    themselves, which tickers resolved no price data, AND the independent-
    window disclosure as an explicit, always-present field -- never hidden
    behind a result a caller has to know to go compute separately."""

    results: list[CrossSectionalScreeningResult]
    missing_price_data: list[str]
    independent_window_disclosure: D2IndependentWindowDisclosure


def screen_d2_reversal_family(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> D2ScreeningSummary:
    """The full D2 screening pass, scoped to ONLY D2_FAMILY's 4
    definitions -- mirrors cross_sectional_patterns.run_round_c_screening's
    shape (same universe primitive, same point-in-time membership gate,
    same missing-tickers contract) but is otherwise this family's own:
    its own price-history padding (D2_PRICE_HISTORY_PADDING_CALENDAR_DAYS),
    its own default delisting-imputation opt-in (see module docstring's
    "DELISTING RETURNS" section), and its own independent-window
    disclosure computed from the real replayed data.

    Universe: get_universe_over(start, end) -- every ticker that was an
    S&P 500 member on ANY day of the screening window (the survivorship-
    free candidate pool primitive), NOT today's snapshot. `start` must be
    >= MEMBERSHIP_DATA_START, enforced loudly by get_universe_over itself
    and re-checked here so the error names the actual fix.

    Returns a D2ScreeningSummary: results, missing price data (per
    sp500_membership_history's KNOWN LIMITS, ~48% of departed members
    resolve nothing on yfinance -- the honest read of any D2 result
    requires knowing how much of the point-in-time universe was actually
    priceable), and the independent-window disclosure. Recommended call
    for this family's own short-history situation is start=
    MEMBERSHIP_DATA_START (the earliest point-in-time coverage allows) --
    a later start only shrinks the already-small independent-window count
    further."""
    if start < MEMBERSHIP_DATA_START:
        # get_universe_over would also reject this; checking here too makes
        # the error message name the actual fix.
        raise ValueError(
            f"D2 screening start {start.isoformat()} predates point-in-time membership coverage "
            f"({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that date would silently "
            "see an empty universe."
        )
    provider = provider if provider is not None else YFinanceProvider()
    # Opt in to the harness's generic Shumway delisting-return imputation
    # ONLY when the caller did not supply their own config -- see module
    # docstring's "DELISTING RETURNS" section for why this family wants it
    # on by default, and cross_sectional.py's module docstring for why the
    # option itself stays off by default at the harness level.
    config = config if config is not None else CrossSectionalConfig(impute_delisting_returns=True)
    config.formation_start = start

    universe = get_universe_over(start, end)
    padded_start = start - timedelta(days=D2_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    frames, missing = provider.get_daily_ohlcv(universe, padded_start, end)
    if not frames:
        disclosure = compute_d2_independent_window_disclosure(0)
        return D2ScreeningSummary(results=[], missing_price_data=missing, independent_window_disclosure=disclosure)

    data = CrossSectionalData(close=frames["close"], open=frames["open"], volume=frames["volume"])
    results = screen_cross_sectional_universe(data, D2_FAMILY, config)

    n_trading_days_replayed = int((data.close.index.date >= start).sum())
    disclosure = compute_d2_independent_window_disclosure(n_trading_days_replayed)
    return D2ScreeningSummary(
        results=results, missing_price_data=missing, independent_window_disclosure=disclosure
    )
