"""LETF end-of-day rebalancing pressure on SPY, QQQ and IWM.

THE CLAIM. A leveraged ETF with target exposure L and net assets A must trade
(L^2 - L) * A * r of its index near the close on a day the index returns r, to
restore target exposure. That flow is mechanically predictable from a return
already observed by 15:00/15:30, is one-directional across bull and bear funds,
and — the part that is an empirical claim rather than an identity — moves the
price of the index's constituents in the last hour, then reverses the next day.

SOURCES, OBTAINED AND READ
==========================
1. THE MECHANICAL FORMULA — two independent statements of the same expression,
   both read in full:
   * Ivanov & Lenkey, "Are Concerns About Leveraged ETFs Overblown?", Federal
     Reserve Board FEDS Working Paper 2014-106, **Eq. (6)**:
         delta x_t = A_t * m * (m - 1) * r_t + f_t
     (`m` is the target multiple, `A_t` net assets, `r_t` the index return,
     `f_t` the investor capital flow). Setting f_t = 0 gives the pure
     rebalancing term used here. The paper's own note beneath Eq. (6): "the
     relation characterized by (6) holds for both leveraged and inverse ETFs",
     i.e. bull and bear funds trade the SAME direction — which is why K below
     sums (L^2 - L) over all four funds with a plus sign. Ivanov & Lenkey also
     record (their text at Eq. (6)) that "relations similar to (6) have been
     derived by Cheng and Madhavan (2009) and Jarrow (2010)".
   * Shum, Hejazi, Haryanto & Rodier, "Intraday Share Price Volatility and
     Leveraged ETF Rebalancing", Review of Finance 20(6) 2016, 2379-2409,
     **Eq. (1)**, read in the University of Toronto TSpace post-print:
         RA_t = NAV_{t-1} * (x^2 - x) * r_t
     with NAV_{t-1} the previous close's net asset value and x the exposure.
     Identical to Ivanov-Lenkey Eq. (6) with f_t = 0, and attributed by that
     paper to Cheng & Madhavan (2009) with its own appendix-A derivation.
   CHENG & MADHAVAN (2009) ITSELF WAS NOT OBTAINED — SSRN returns HTTP 403 to
   automated retrieval and the one indexed copy found was a corrupt PDF. It is
   cited here ONLY as those two papers cite it. Two independent peer-reviewed /
   Federal-Reserve statements of the same equation are what this module relies
   on; no formula in this file was written from memory.

2. THE TIMING — Shum et al. section 2: rebalancing "could begin as early as
   3:30PM"; their own empirical windows are the last three 15-minute intervals.
   Tuzun (below) uses "the last hour of trading", 15:00-16:00. Hence the two
   pre-registered windows w = 15:30 (primary) and w = 15:00 (secondary).

3. THE RETURN EFFECT AND THE REGRESSION FORM — Tuzun, "Are Leveraged and
   Inverse ETFs the New Portfolio Insurers?", Federal Reserve Board FEDS
   Working Paper 2013-48. Sample 2006-06-19 (the first US equity LETF) to
   2011-12-31, TAQ intraday prices. Read for this module: sections C.1-C.3 and
   Tables IV, V and VI.
   * **Eq. (2)**, the specification `regression_4_1` below implements, quoted
     from the paper: `dlog(P_i,c)/sigma_i = b0 + b1 * (LETFFlow_i/ADV_i)
     + b2 * (dlog(P_(i,15:00))/sigma_i) + e_i`, where the dependent variable is
     "the return on a stock i between 15:00pm(ET) and 16:00pm (ET)" scaled by
     "sigma_i - the standard deviation of previous 20 days' returns";
     `LETFFlow_i` is the stock's share of the LETF rebalancing flow implied by
     "the target index return between the previous day's close and 15:00pm";
     `ADV_i` is "the past 20 day average dollar trading volume of stock i"; and
     "standard errors are clustered daily". Every one of those five choices is
     reproduced below, with the two disclosed substitutions in
     DEVIATIONS_FROM_SOURCE.
   * **Table IV Panel A, control-included columns** (the effect size the power
     block is calibrated against): LETF Flow/ADV coefficient 4.32, clustered
     s.e. 0.57, 684,869 observations, adj-R^2 1.36% for Large Cap; 3.83 (0.83),
     129,800 obs, adj-R^2 0.76% for Technology; 0.86 (0.08), 2,220,771 obs,
     adj-R^2 2.14% for Small Cap. All three read off the paper's own table.
   * **The paper's own translation into basis points**, section C.1 verbatim:
     "The end-of-day price reaction is 6.9 basis points (4.32 x 0.8% x 2%) in an
     average large stock, 5.5 basis points (4.28 x 0.6% x 2%) in an average mid
     cap stock, 12.7 basis points (0.86 x 5% x 2.9%) in an average small stock
     and 6.3 basis points (3.83 x 0.75% x 2.2%) in an average technology stock"
     — at December-2011 AUM, on a 1% index day. 6.9 bp is TUZUN_LARGE_CAP_BP_PER_1PCT.
   * **Eq. (3) and Table VI Panel A**, the reversal `regression_reversal`
     implements: the next day's return "from today's market close to 15:00 next
     day, scaled by its daily volatility" on the ONE-DAY-LAGGED flow and lagged
     return. Coefficients -3.52 (s.e. 1.08) Large Cap, -4.24 (1.65) Technology,
     -0.35 (0.10) Small Cap; "compared with the results from Table IV, these
     coefficients are similar in magnitude, suggesting that prices revert back
     the next day after LETF rebalancing".

4. KNOWN OFFSETS, declared in the pre-registration and repeated here so no
   result is read without them: Ivanov & Lenkey Table III measure that investor
   flows cut the REALISED rebalancing coefficient to 1.5-3.5 (m = +3) and
   7.3-8.8 (m = -3) against the mechanical 6 and 12 in the tail return
   quintiles. That is the 50%-of-Tuzun arm the power block reports. Jain,
   Mishra, Pagano & Rodriguez (EFMA 2024 working paper) find the effect
   state-dependent on index-return autocorrelation through 2020. Neither paper
   reports a decay to zero, and Tuzun's claim is unconditional, so the test here
   is unconditional and NO regime split is declared (CLAUDE.md section 4's
   conditional rule applies only to explicitly conditional source claims).

ENTIRELY OUT OF SAMPLE. Tuzun's sample ends 2011-12-31. The earliest bar here is
2016-01-04. Zero overlap. This is not a replication and cannot be one.

PRE-REGISTRATION AND ITS ONE ADDENDUM
=====================================
data/research_runs/letf_rebalancing_2026-09-11/PREREGISTRATION.md fixes every
construction, spec, control, cost arm, gate and the power-block procedure, and
was committed and merged to main before this module was written.
ADDENDUM_01_CONTROL_DEGENERACY_AND_GRID_COUNT.md, committed before any strategy
return existed, records that controls C1 and C2 are ALGEBRAICALLY IDENTICAL to
the specs they control (K > 0 and ADV > 0 make sign(x) == sign(r) identically, so
rescaling or permuting K cannot change a sign rule), that the grid is
nevertheless implemented verbatim with n_local = 20, that C1 is one pooled spec,
that a regression-level permutation placebo is added as a DIAGNOSTIC outside
n_local, and what sigma_SR the power block uses.

DEVIATIONS FROM SOURCE — see DEVIATIONS_FROM_SOURCE below. There are three, all
forced by the unit of observation being an ETF rather than a constituent stock,
all pre-registered, and all disclosed in the run report and on the scorecard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import time as dt_time

import numpy as np
import pandas as pd

from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.research_lab.preservation_score import compute_preservation_metrics

logger = logging.getLogger(__name__)

FAMILY_KEY = "letf_rebalancing_eod"

TUZUN_CITATION = (
    "Tuzun, 'Are Leveraged and Inverse ETFs the New Portfolio Insurers?', Federal "
    "Reserve Board FEDS 2013-48, Eq. (2) and Table IV Panel A (sample 2006-06-19.."
    "2011-12-31)"
)
MECHANICAL_FORMULA_CITATION = (
    "Ivanov & Lenkey, FEDS 2014-106, Eq. (6) with f_t = 0; identically Shum, Hejazi, "
    "Haryanto & Rodier, Review of Finance 20(6) 2016, Eq. (1); both attribute the "
    "expression to Cheng & Madhavan (2009), which was NOT obtained"
)

# --- Tuzun's numbers, read off the paper, used only where cited -------------
# Table IV Panel A, control-included columns.
TUZUN_TABLE_IV_PANEL_A = {
    "large_cap": {"beta": 4.32, "se": 0.57, "n_obs": 684_869, "adj_r2_pct": 1.36},
    "technology": {"beta": 3.83, "se": 0.83, "n_obs": 129_800, "adj_r2_pct": 0.76},
    "small_cap": {"beta": 0.86, "se": 0.08, "n_obs": 2_220_771, "adj_r2_pct": 2.14},
}
# Table VI Panel A, the next-day reversal on the LAGGED flow.
TUZUN_TABLE_VI_PANEL_A = {
    "large_cap": {"beta": -3.52, "se": 1.08},
    "technology": {"beta": -4.24, "se": 1.65},
    "small_cap": {"beta": -0.35, "se": 0.10},
}
# Section C.1 verbatim: "6.9 basis points (4.32 x 0.8% x 2%) in an average large
# stock" on a 1% index day at December-2011 AUM. The power block's claimed effect.
TUZUN_LARGE_CAP_BP_PER_1PCT = 6.9
# Ivanov & Lenkey Table III's flow offset, as the pre-registration's second
# power calibration: the realised coefficient is roughly half the mechanical one.
IVANOV_LENKEY_OFFSET_FRACTION = 0.50
TUZUN_SAMPLE = "2006-06-19..2011-12-31"
# Which underlying maps to which of Tuzun's categories, for reporting only —
# never used in a calculation.
UNDERLYING_TO_TUZUN_CATEGORY = {"SPY": "large_cap", "QQQ": "technology", "IWM": "small_cap"}

DEVIATIONS_FROM_SOURCE = (
    (
        "D1. UNIT OF OBSERVATION. Tuzun's Eq. (2) is estimated on CONSTITUENT STOCKS "
        "(684,869 large-cap stock-days), with LETFFlow_i the stock's share of the total "
        "flow implied by its index weight and ADV_i the STOCK's 20-day average dollar "
        "volume. This family observes the INDEX ETF itself: one observation per "
        "underlying per session, flow not split by index weight, and ADV20 the ETF's own "
        "20-session average dollar volume. Pre-registered (section 3) and forced -- "
        "constituent-level intraday data for 500+ names over 10 years is not available "
        "here. CONSEQUENCE: b in section 4.1 is NOT on Tuzun's scale and its point "
        "estimate must not be compared to 4.32 as though it were. The pre-registration "
        "says so explicitly and the run report repeats it next to every b."
    ),
    (
        "D2. ADV IS AN UPPER BOUND ON THE RELEVANT LIQUIDITY. Real rebalancing is "
        "executed in constituents and in swaps, not in the index ETF, so dividing the "
        "dollar flow by the ETF's own volume understates the flow-to-liquidity ratio by "
        "an unknown factor. Feasibility memo Q5; disclosed, not corrected."
    ),
    (
        "D3. THE COEFFICIENT OMITS EVERY NON-ProShares FUND, and the three -1x ProShares "
        "funds (SH, PSQ, RWM). Only the twelve funds the pre-registration names enter K, "
        "because no free daily AUM history exists for Direxion. K is therefore a strict "
        "LOWER BOUND on the true rebalancing coefficient, by a time-varying and "
        "historically unmeasurable factor. A strictly positive rescaling changes neither "
        "the sign of any position nor the sign or significance of b -- only b's units, "
        "which D1 has already put off Tuzun's scale. Measured and reported in the run "
        "report's scaling-omission section; evidence in SCALING_OMISSION_EVIDENCE.json."
    ),
)

# --- session geometry -------------------------------------------------------
# Alpaca bar timestamps are bar-START times (alpaca_provider.py: "a regular-
# session bar starts at or after 09:30 and strictly before 16:00 ET"), so the
# last regular-session bar starts at 15:59 and its CLOSE is the closing print.
SESSION_OPEN = dt_time(9, 30)
SESSION_LAST_BAR_START = dt_time(15, 59)
BLOCK_MINUTES = 30
N_HALF_HOURS = 13

# --- usability rules, copied unchanged from intraday_momentum_spy.py --------
# PREREGISTRATION section 2: "Session usability rules U1-U3 and the no-predecessor
# rule are copied unchanged from intraday_momentum_spy.py (>= 380 bars, last bar
# start >= 15:55, each block complete); a session is used only if all three
# underlyings pass, so the panel is balanced."
MIN_SESSION_BARS = 380  # U3
MIN_LAST_BAR_START = dt_time(15, 55)  # U2
MAX_PREVIOUS_SESSION_GAP_DAYS = 5

# --- windows (PREREGISTRATION section 3) ------------------------------------
PRIMARY_WINDOW = dt_time(15, 30)
SECONDARY_WINDOW = dt_time(15, 0)
WINDOWS = (PRIMARY_WINDOW, SECONDARY_WINDOW)
# C3's wrong-window control: the pooled A rule on 10:00 -> 10:30.
CONTROL_WINDOW_OPEN = dt_time(10, 0)
CONTROL_WINDOW_CLOSE = dt_time(10, 29)
# The reversal target's next-day endpoint, Tuzun Eq. (3)'s "today's market close
# to 15:00 next day".
REVERSAL_WINDOW = dt_time(15, 0)

UNDERLYINGS = ("SPY", "QQQ", "IWM")

# --- trailing-window lengths ------------------------------------------------
# Tuzun Table IV's own note: sigma is "the standard deviation of previous 20
# days' returns" and ADV is "the past 20 day average dollar trading volume".
TRAILING_SESSIONS = 20

# --- spec B's cut (PREREGISTRATION section 3) -------------------------------
# "a fixed number chosen before any data (it is the |r| at which Tuzun's
# Dec-2011 large-cap effect is ~3.5 bp, roughly the round-trip cost of the
# verdict arm); it will not be moved."
ABS_RETURN_CUT = 0.0050

# --- C2's permutation seed (PREREGISTRATION section 3) ----------------------
SHUFFLE_SEED = 12345

# --- costs (PREREGISTRATION section 4.2) ------------------------------------
CROSSINGS_PER_TRADED_DAY = 2

VALIDATED_EDGE_BAR = 0.95
SCREENING_FLOOR = 0.50

# The pre-registered grid size. Section 3: 17 trading specs + C1 + C2 + C3.
PRE_REGISTERED_N_LOCAL = 20


class LetfRebalancingError(ValueError):
    """A data or configuration problem that must not be papered over."""


# ---------------------------------------------------------------------------
# panel construction
# ---------------------------------------------------------------------------


def _block_index(times: pd.Series) -> np.ndarray:
    """Which half-hour block (1..13) each bar-START time falls in. Copied from
    intraday_momentum_spy._block_index so U1 is literally the same rule."""
    minutes = times.dt.hour * 60 + times.dt.minute
    open_minutes = SESSION_OPEN.hour * 60 + SESSION_OPEN.minute
    return ((minutes - open_minutes) // BLOCK_MINUTES + 1).to_numpy()


@dataclass(frozen=True)
class SessionAudit:
    """Why each calendar date was kept or dropped, per underlying and then
    jointly. Every drop is counted and reported by reason."""

    per_ticker_sessions: dict[str, int]
    per_ticker_usable: dict[str, int]
    dropped_too_few_bars: dict[str, list[str]]  # U3
    dropped_late_bar: dict[str, list[str]]  # U2
    dropped_incomplete_blocks: dict[str, list[str]]  # U1
    dropped_missing_window_bar: dict[str, list[str]]
    dropped_not_common_to_all: list[str]
    dropped_no_previous: list[str]
    dropped_short_trailing: list[str]
    n_panel_sessions: int


@dataclass(frozen=True)
class SessionQuotes:
    """The handful of prints one usable session contributes."""

    close_1559: float
    dollar_volume: float
    window_open: dict[dt_time, float]
    control_open: float
    control_close: float


def _session_quotes(group: pd.DataFrame) -> SessionQuotes | None:
    """Pull the prints the constructions need out of one session's minute bars.

    Returns None if a bar the constructions REQUIRE is absent. That is not a
    discretionary filter: `r_open->w` is defined in PREREGISTRATION section 3 as
    a return "to the OPEN of the bar starting at w", which is undefined if no bar
    starts at w. Counted and reported separately from U1-U3 so it can be seen to
    be zero (or not)."""
    times = pd.DatetimeIndex(group.index)
    by_time = {t.time(): i for i, t in enumerate(times)}
    if SESSION_LAST_BAR_START not in by_time:
        return None
    needed = [*WINDOWS, CONTROL_WINDOW_OPEN, CONTROL_WINDOW_CLOSE]
    if any(t not in by_time for t in needed):
        return None
    opens = group["open"].to_numpy(float)
    closes = group["close"].to_numpy(float)
    volumes = group["volume"].to_numpy(float)
    return SessionQuotes(
        close_1559=float(closes[by_time[SESSION_LAST_BAR_START]]),
        # Dollar volume of the session, the input to ADV20. Sum of close*volume
        # over the regular-session minute bars -- the finest-grained dollar
        # volume these bars support; a minute's close is inside its own NBBO.
        dollar_volume=float(np.nansum(closes * volumes)),
        window_open={t: float(opens[by_time[t]]) for t in WINDOWS},
        control_open=float(opens[by_time[CONTROL_WINDOW_OPEN]]),
        control_close=float(closes[by_time[CONTROL_WINDOW_CLOSE]]),
    )


def usable_sessions(bars: pd.DataFrame) -> tuple[dict[pd.Timestamp, SessionQuotes], dict[str, list[str]]]:
    """Apply U1-U3 to one ticker's minute bars and pull each usable session's
    quotes. Returns (quotes by session date, drop lists by reason)."""
    if bars.empty:
        raise LetfRebalancingError("no bars supplied")
    for column in ("open", "close", "volume"):
        if column not in bars.columns:
            raise LetfRebalancingError(f"bars missing {column!r}; have {list(bars.columns)}")

    index = pd.DatetimeIndex(bars.index)
    frame = bars.copy()
    # Session dates are carried TZ-NAIVE throughout the panel. Alpaca bars are
    # tz-aware America/New_York, the ProShares AUM file's Date column is a naive
    # calendar date, and comparing the two raises rather than mis-aligning; the
    # calendar day is the only thing either side means, so the offset is dropped
    # once, here, rather than guessed at every join.
    local = index.tz_localize(None) if index.tz is not None else index
    frame["_date"] = local.normalize()
    frame["_block"] = _block_index(pd.Series(index, index=bars.index))

    drops: dict[str, list[str]] = {
        "too_few_bars": [],
        "late_bar": [],
        "incomplete_blocks": [],
        "missing_window_bar": [],
    }
    quotes: dict[pd.Timestamp, SessionQuotes] = {}
    for session_date, group in frame.groupby("_date", sort=True):
        label = pd.Timestamp(session_date).strftime("%Y-%m-%d")
        if len(group) < MIN_SESSION_BARS:  # U3
            drops["too_few_bars"].append(label)
            continue
        if pd.Timestamp(group.index[-1]).time() < MIN_LAST_BAR_START:  # U2
            drops["late_bar"].append(label)
            continue
        present_blocks = set(group["_block"].unique().tolist())
        if not all(j in present_blocks for j in range(1, N_HALF_HOURS + 1)):  # U1
            drops["incomplete_blocks"].append(label)
            continue
        session = _session_quotes(group)
        if session is None:
            drops["missing_window_bar"].append(label)
            continue
        quotes[pd.Timestamp(session_date)] = session
    return quotes, drops


@dataclass(frozen=True)
class AumCoefficients:
    """K_{u,t} for every underlying and session, plus the inputs it was built
    from, so the run report can show its level and growth."""

    coefficient: pd.DataFrame  # index = session date, columns = underlyings
    fund_leverage: dict[str, tuple[str, float]]
    as_of_date: pd.DataFrame  # which AUM row date fed each cell


def build_coefficients(
    aum: pd.DataFrame,
    sessions: pd.DatetimeIndex,
    fund_map: dict[str, tuple[str, float]],
) -> AumCoefficients:
    """K_{u,t} = sum_i A_{i,t-1} * (L_i^2 - L_i) over the underlying's funds.

    Ivanov & Lenkey FEDS 2014-106 Eq. (6) with f_t = 0, equivalently Shum et al.
    2016 Eq. (1), summed over funds. `A_{i,t-1}` is the fund's AUM row dated the
    LAST DATE STRICTLY BEFORE session t -- published after that day's close and
    therefore known before day t's open, as PREREGISTRATION section 2 requires.
    No row on or after t is ever read; this is the whole point-in-time contract
    of this family and it is asserted, not assumed, by tests.

    `aum` must carry columns Date (datetime), Ticker, and the AUM value in a
    column named 'aum'."""
    missing = {"Date", "Ticker", "aum"} - set(aum.columns)
    if missing:
        raise LetfRebalancingError(f"aum frame missing {sorted(missing)}")
    sessions = pd.DatetimeIndex(sessions).normalize().sort_values()
    underlyings = sorted({u for u, _ in fund_map.values()})
    coefficient = pd.DataFrame(np.nan, index=sessions, columns=underlyings, dtype=float)
    as_of = pd.DataFrame(pd.NaT, index=sessions, columns=underlyings, dtype="datetime64[ns]")

    contributions: dict[str, list[pd.Series]] = {u: [] for u in underlyings}
    as_of_parts: dict[str, list[pd.Series]] = {u: [] for u in underlyings}
    for ticker, (underlying, leverage) in fund_map.items():
        rows = aum[aum["Ticker"] == ticker].sort_values("Date")
        if rows.empty:
            raise LetfRebalancingError(f"no AUM rows for fund {ticker!r}")
        dates = pd.DatetimeIndex(rows["Date"]).normalize()
        values = rows["aum"].to_numpy(float)
        # searchsorted 'left' on the session date gives the count of AUM dates
        # STRICTLY BEFORE it, so position-1 is the last row dated before t.
        position = np.searchsorted(dates.to_numpy(), sessions.to_numpy(), side="left") - 1
        ok = position >= 0
        picked = np.where(ok, values[np.clip(position, 0, None)], np.nan)
        picked_date = np.where(ok, dates.to_numpy()[np.clip(position, 0, None)], np.datetime64("NaT", "ns"))
        weight = leverage**2 - leverage
        if weight <= 0:
            raise LetfRebalancingError(
                f"fund {ticker!r} has L^2-L = {weight}, which the mechanism forbids"
            )
        contributions[underlying].append(pd.Series(picked * weight, index=sessions))
        as_of_parts[underlying].append(pd.Series(picked_date, index=sessions))

    for underlying in underlyings:
        stacked = pd.concat(contributions[underlying], axis=1)
        # Every fund must have a row before t; a partial sum would silently
        # shrink K on early sessions.
        coefficient[underlying] = stacked.sum(axis=1).where(stacked.notna().all(axis=1))
        as_of[underlying] = pd.concat(as_of_parts[underlying], axis=1).max(axis=1)
    return AumCoefficients(coefficient=coefficient, fund_leverage=dict(fund_map), as_of_date=as_of)


def build_panel(
    bars_by_ticker: dict[str, pd.DataFrame],
    aum: pd.DataFrame,
    fund_map: dict[str, tuple[str, float]],
) -> tuple[pd.DataFrame, SessionAudit]:
    """One long-format row per (session, underlying), carrying everything
    PREREGISTRATION section 3 defines.

    Columns: date, underlying, r_1530, r_1500, y_1530, y_1500, sigma20, adv20,
    K, x_1530, x_1500, close, prev_close, z_next, c3_r, c3_y.

    The panel is BALANCED: a session appears only if all three underlyings
    passed U1-U3 and have a usable predecessor and a full trailing window
    (section 2's "a session is used only if all three underlyings pass")."""
    quotes: dict[str, dict[pd.Timestamp, SessionQuotes]] = {}
    drops_by_ticker: dict[str, dict[str, list[str]]] = {}
    for ticker, bars in bars_by_ticker.items():
        quotes[ticker], drops_by_ticker[ticker] = usable_sessions(bars)

    per_ticker_usable = {t: set(q) for t, q in quotes.items()}
    common = sorted(set.intersection(*per_ticker_usable.values()))
    if not common:
        raise LetfRebalancingError("no session is usable for all three underlyings")
    not_common = sorted(
        {d.strftime("%Y-%m-%d") for t in quotes for d in per_ticker_usable[t]}
        - {d.strftime("%Y-%m-%d") for d in common}
    )

    coefficients = build_coefficients(aum, pd.DatetimeIndex(common), fund_map)

    rows: list[dict] = []
    dropped_no_previous: list[str] = []
    dropped_short_trailing: list[str] = []
    for i, session_date in enumerate(common):
        label = session_date.strftime("%Y-%m-%d")
        if i == 0:
            dropped_no_previous.append(label)
            continue
        previous = common[i - 1]
        if (session_date.normalize() - previous.normalize()).days > MAX_PREVIOUS_SESSION_GAP_DAYS:
            dropped_no_previous.append(label)
            continue
        if i < TRAILING_SESSIONS:
            dropped_short_trailing.append(label)
            continue
        trailing = common[i - TRAILING_SESSIONS : i]
        for underlying in UNDERLYINGS:
            today = quotes[underlying][session_date]
            yesterday = quotes[underlying][previous]
            prev_close = yesterday.close_1559
            # sigma20: Tuzun Table IV's note, "the standard deviation of previous
            # 20 days' returns". Close-to-close, the 20 sessions strictly before t.
            trailing_closes = [quotes[underlying][d].close_1559 for d in [*trailing, previous]]
            trailing_returns = np.diff(np.asarray(trailing_closes, dtype=float)) / np.asarray(
                trailing_closes[:-1], dtype=float
            )
            sigma20 = float(np.std(trailing_returns, ddof=1))
            # ADV20: Tuzun Table IV's note, "the past 20 day average dollar
            # trading volume", the 20 sessions strictly before t.
            adv20 = float(np.mean([quotes[underlying][d].dollar_volume for d in trailing]))
            k = coefficients.coefficient.at[session_date, underlying]
            row = {
                "date": session_date,
                "underlying": underlying,
                "close": today.close_1559,
                "prev_close": prev_close,
                "sigma20": sigma20,
                "adv20": adv20,
                "K": float(k) if pd.notna(k) else np.nan,
                "K_as_of": coefficients.as_of_date.at[session_date, underlying],
            }
            for window in WINDOWS:
                tag = window.strftime("%H%M")
                window_open = today.window_open[window]
                # r_open->w: previous session's 15:59 CLOSE to the OPEN of the
                # bar starting at w (PREREGISTRATION section 3). Tuzun's
                # "previous day's close to 15:00" predictor, at our window.
                r = window_open / prev_close - 1.0
                # y: open of the bar starting at w -> close of the 15:59 bar.
                row[f"r_{tag}"] = r
                row[f"y_{tag}"] = today.close_1559 / window_open - 1.0
                # x = K * r / ADV20 (section 3's D/ADV20).
                row[f"x_{tag}"] = (row["K"] * r / adv20) if adv20 > 0 else np.nan
            # C3's wrong window: the same rule on 10:00 -> 10:30.
            row["c3_r"] = today.control_open / prev_close - 1.0
            row["c3_y"] = today.control_close / today.control_open - 1.0
            rows.append(row)

    panel = pd.DataFrame(rows)
    if panel.empty:
        raise LetfRebalancingError("no session survived the pre-registered rules")

    # z_{u,t+1}: close of session t -> open of the bar starting 15:00 on t+1
    # (Tuzun Eq. (3)'s "today's market close to 15:00 next day"). Built by
    # shifting within each underlying, so it is NEVER available at t and is only
    # ever used as a TARGET, never as an input to a position held on t.
    reversal_tag = REVERSAL_WINDOW.strftime("%H%M")
    panel = panel.sort_values(["underlying", "date"]).reset_index(drop=True)
    next_open = panel.groupby("underlying")[f"r_{reversal_tag}"].shift(-1)
    next_date = panel.groupby("underlying")["date"].shift(-1)
    # A row's successor in the balanced panel is only the NEXT CALENDAR session
    # if it is within the same gap tolerance the panel already enforces; a
    # dropped session in between would otherwise let shift(-1) reach across it
    # and silently redefine z. Blank those rows rather than approximate them.
    gap_days = (next_date - panel["date"]).dt.days
    adjacent = next_date.notna() & (gap_days <= MAX_PREVIOUS_SESSION_GAP_DAYS)
    panel["z_next"] = np.where(adjacent, next_open, np.nan)
    panel["z_next_date"] = next_date.where(adjacent)

    audit = SessionAudit(
        per_ticker_sessions={
            t: int(pd.DatetimeIndex(b.index).tz_localize(None).normalize().nunique())
            if pd.DatetimeIndex(b.index).tz is not None
            else int(pd.DatetimeIndex(b.index).normalize().nunique())
            for t, b in bars_by_ticker.items()
        },
        per_ticker_usable={t: len(q) for t, q in quotes.items()},
        dropped_too_few_bars={t: d["too_few_bars"] for t, d in drops_by_ticker.items()},
        dropped_late_bar={t: d["late_bar"] for t, d in drops_by_ticker.items()},
        dropped_incomplete_blocks={t: d["incomplete_blocks"] for t, d in drops_by_ticker.items()},
        dropped_missing_window_bar={t: d["missing_window_bar"] for t, d in drops_by_ticker.items()},
        dropped_not_common_to_all=not_common,
        dropped_no_previous=dropped_no_previous,
        dropped_short_trailing=dropped_short_trailing,
        n_panel_sessions=int(panel["date"].nunique()),
    )
    return panel, audit


# ---------------------------------------------------------------------------
# specs (PREREGISTRATION section 3, verbatim; ADDENDUM_01 for the controls)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LetfSpec:
    spec_id: str
    kind: str  # "A" | "B" | "P" | "R" | "C1" | "C2" | "C3"
    window: dt_time | None
    underlyings: tuple[str, ...]
    is_control: bool
    citation: str
    hypothesis: str


def _window_tag(window: dt_time) -> str:
    return window.strftime("%H%M")


def build_family() -> list[LetfSpec]:
    """The 20 pre-registered specs, in the pre-registered order.

    17 trading specs (A x 6, B x 6, P x 2, R x 3) plus the three controls C1,
    C2, C3. Controls are INCLUDED in n_local -- the conservative choice, since a
    larger denominator can only make the DSR gate stricter. The count is fixed
    at PRE_REGISTERED_N_LOCAL = 20 by PREREGISTRATION section 3 and no spec may
    be added or dropped (section 4.4)."""
    specs: list[LetfSpec] = []
    for window in WINDOWS:
        tag = _window_tag(window)
        for underlying in UNDERLYINGS:
            specs.append(
                LetfSpec(
                    spec_id=f"A_{underlying}_{tag}",
                    kind="A",
                    window=window,
                    underlyings=(underlying,),
                    is_control=False,
                    citation=TUZUN_CITATION,
                    hypothesis=(
                        f"Tuzun Eq. (2) / Table IV: implied LETF rebalancing flow, signed by "
                        f"the {tag} predictor return, pushes the underlying in the SAME "
                        f"direction over the closing window. Long y if x > 0, short if "
                        f"x <= 0 (tie = short, the same convention as GHLZ Eq. 4 in "
                        f"intraday_momentum_spy). Single underlying {underlying}."
                    ),
                )
            )
    for window in WINDOWS:
        tag = _window_tag(window)
        for underlying in UNDERLYINGS:
            specs.append(
                LetfSpec(
                    spec_id=f"B_{underlying}_{tag}",
                    kind="B",
                    window=window,
                    underlyings=(underlying,),
                    is_control=False,
                    citation=TUZUN_CITATION,
                    hypothesis=(
                        f"As A_{underlying}_{tag} but FLAT when |r_open->{tag}| < "
                        f"{ABS_RETURN_CUT:.4f}. The cut is a fixed number chosen before any "
                        "data: the |r| at which Tuzun's Dec-2011 large-cap effect is about "
                        "3.5 bp, roughly the round-trip cost of the verdict arm "
                        "(PREREGISTRATION section 3). It is not gridded and will not be moved."
                    ),
                )
            )
    for window in WINDOWS:
        tag = _window_tag(window)
        specs.append(
            LetfSpec(
                spec_id=f"P_{tag}",
                kind="P",
                window=window,
                underlyings=UNDERLYINGS,
                is_control=False,
                citation=TUZUN_CITATION,
                hypothesis=(
                    f"Equal-weight average of A_u_{tag} across SPY, QQQ and IWM. The "
                    "pooled spec, and the one the section 4.1 mechanism gate and the C2 "
                    "and C3 controls are written against."
                ),
            )
        )
    for underlying in UNDERLYINGS:
        specs.append(
            LetfSpec(
                spec_id=f"R_{underlying}",
                kind="R",
                window=PRIMARY_WINDOW,
                underlyings=(underlying,),
                is_control=False,
                citation=(
                    "Tuzun FEDS 2013-48 Eq. (3) and Table VI Panel A (lagged-flow "
                    "coefficients -3.52 large cap, -4.24 technology, -0.35 small cap)"
                ),
                hypothesis=(
                    "REVERSAL. Tuzun Table VI finds the next-day close->15:00 return loads "
                    "NEGATIVELY on the lagged flow, 'suggesting that prices revert back the "
                    "next day after LETF rebalancing'. Short z_{t+1} if x_t > 0, long if "
                    "x_t <= 0. Held OVERNIGHT, which the pre-registered cost arms do not "
                    "charge borrow for -- disclosed, and it understates this spec's cost."
                ),
            )
        )
    specs.append(
        LetfSpec(
            spec_id="C1_constant_aum_P_1530",
            kind="C1",
            window=PRIMARY_WINDOW,
            underlyings=UNDERLYINGS,
            is_control=True,
            citation="pre-registered control, not a claim of the source paper",
            hypothesis=(
                "CONSTANT-AUM CONTROL. The pooled 15:30 spec with each underlying's K "
                "replaced by that underlying's sample mean -- i.e. plain intraday "
                "momentum. PREREGISTRATION section 3 expects A to beat C1 only through "
                "the time variation of K/ADV. ADDENDUM_01 records, from the definitions "
                "and before any return existed, that this control is DEGENERATE on a "
                "sign-rule grid: K > 0 and ADV > 0 make sign(x) == sign(r) identically, "
                "so rescaling K by a positive constant cannot change a single position. "
                "This spec's series is EXACTLY EQUAL to P_1530's, by construction."
            ),
        )
    )
    specs.append(
        LetfSpec(
            spec_id="C2_shuffled_aum_P_1530",
            kind="C2",
            window=PRIMARY_WINDOW,
            underlyings=UNDERLYINGS,
            is_control=True,
            citation="pre-registered placebo, not a claim of the source paper",
            hypothesis=(
                f"SHUFFLED-AUM PLACEBO, one draw, seed {SHUFFLE_SEED}, on the pooled 15:30 "
                "spec. PREREGISTRATION section 3: 'Must not pass.' ADDENDUM_01 records "
                "that this requirement is VACUOUS on the trading grid for the same reason "
                "C1 is degenerate -- a permutation of positive numbers is still positive, "
                "so the sign of x is unchanged and this series is EXACTLY EQUAL to "
                "P_1530's. Where the permutation does bite is the section 4.1 regression, "
                "and it is run there as a reported DIAGNOSTIC outside n_local."
            ),
        )
    )
    specs.append(
        LetfSpec(
            spec_id="C3_wrong_window_P_1000",
            kind="C3",
            window=CONTROL_WINDOW_OPEN,
            underlyings=UNDERLYINGS,
            is_control=True,
            citation="pre-registered control, not a claim of the source paper",
            hypothesis=(
                "WRONG-WINDOW CONTROL. The pooled A rule applied to 10:00->10:30 instead "
                "of the closing window. The mechanism predicts nothing here: LETF "
                "rebalancing is executed near the close (Shum et al. section 2, 'as early "
                "as 3:30PM'; Tuzun, 'the last hour of trading'), so a mid-morning window "
                "carries the same instrument, the same scale and the same noise structure "
                "with none of the flow. NOT degenerate -- unlike C1 and C2 this control "
                "changes the window rather than the coefficient, so it is the only "
                "surviving discriminating control on the trading grid."
            ),
        )
    )
    if len(specs) != PRE_REGISTERED_N_LOCAL:
        raise LetfRebalancingError(
            f"grid is {len(specs)} specs but PREREGISTRATION section 3 declares "
            f"{PRE_REGISTERED_N_LOCAL}; no spec may be added or dropped (section 4.4)"
        )
    return specs


# ---------------------------------------------------------------------------
# cost arms (PREREGISTRATION section 4.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostArm:
    key: str
    description: str
    one_way_bps: float


COST_ARMS: tuple[CostArm, ...] = (
    CostArm(
        key="cost_free",
        description="0 bp -- the GROSS signal. Attribution only, NEVER a verdict input.",
        one_way_bps=0.0,
    ),
    CostArm(
        key="verdict",
        description=(
            "1.0 bp one-way -- THE VERDICT ARM, fixed by PREREGISTRATION section 4.2. "
            "The same arm intraday_momentum_spy's ADDENDUM_01 settled on: SPY's one-cent "
            "minimum tick permits at most about 0.14 bp of half-spread at a $360 close, "
            "so 1.0 bp is roughly 7x the quoted half-spread, with the margin reserved for "
            "entry and closing-auction impact, and it covers QQQ and IWM too. No "
            "commission (retail equity commissions went to zero in 2019). No borrow: the "
            "closing-window specs are flat overnight, though the reversal specs are NOT "
            "and this arm therefore understates their cost -- disclosed."
        ),
        one_way_bps=1.0,
    ),
    CostArm(
        key="stress",
        description="2.0 bp one-way -- the pre-registered stress arm. Double the verdict arm.",
        one_way_bps=2.0,
    ),
)
BASELINE_COST_ARM = "verdict"


def cost_arm(key: str) -> CostArm:
    for arm in COST_ARMS:
        if arm.key == key:
            return arm
    raise LetfRebalancingError(f"unknown cost arm {key!r}; have {[a.key for a in COST_ARMS]}")


# ---------------------------------------------------------------------------
# the replay
# ---------------------------------------------------------------------------


def _wide(panel: pd.DataFrame, column: str) -> pd.DataFrame:
    return panel.pivot(index="date", columns="underlying", values=column)


def shuffled_coefficient(panel: pd.DataFrame, seed: int = SHUFFLE_SEED) -> pd.DataFrame:
    """C2's placebo K: one draw, permuted across SESSIONS, per underlying.

    A single numpy Generator seeded with `seed` is drawn from once per
    underlying in a fixed underlying order, so the permutation is reproducible
    to the row for a given panel -- asserted by a test rather than assumed."""
    wide = _wide(panel, "K")
    rng = np.random.default_rng(seed)
    out = wide.copy()
    for underlying in UNDERLYINGS:
        out[underlying] = rng.permutation(wide[underlying].to_numpy())
    return out


def spec_signal(panel: pd.DataFrame, spec: LetfSpec) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(x, target) as wide date x underlying frames for one spec.

    Every quantity in `x` is measurable by the window open on session t: the
    previous session's close, the AUM row dated strictly before t, and the
    trailing-20-session ADV. `target` is what the resulting position earns
    AFTERWARDS. There is no path by which the target can influence the weight
    that earns it -- the timing contract this family lives or dies by."""
    if spec.kind == "C3":
        return (
            _wide(panel, "K") * _wide(panel, "c3_r") / _wide(panel, "adv20"),
            _wide(panel, "c3_y"),
        )
    if spec.kind == "R":
        tag = _window_tag(PRIMARY_WINDOW)
        return _wide(panel, f"x_{tag}"), _wide(panel, "z_next")
    tag = _window_tag(spec.window)
    if spec.kind == "C1":
        wide_k = _wide(panel, "K")
        constant_k = pd.DataFrame(
            {u: np.full(len(wide_k), float(wide_k[u].mean())) for u in wide_k.columns},
            index=wide_k.index,
        )
        return (
            constant_k * _wide(panel, f"r_{tag}") / _wide(panel, "adv20"),
            _wide(panel, f"y_{tag}"),
        )
    if spec.kind == "C2":
        return (
            shuffled_coefficient(panel) * _wide(panel, f"r_{tag}") / _wide(panel, "adv20"),
            _wide(panel, f"y_{tag}"),
        )
    return _wide(panel, f"x_{tag}"), _wide(panel, f"y_{tag}")


def build_positions(panel: pd.DataFrame, spec: LetfSpec) -> pd.DataFrame:
    """w in {-1, 0, +1} per underlying leg, before pooling weights.

    The tie convention is `x <= 0 => SHORT`, never flat -- PREREGISTRATION
    section 3 fixes it and names GHLZ Eq. (4), the same convention
    intraday_momentum_spy implements."""
    x, _ = spec_signal(panel, spec)
    columns = list(spec.underlyings)
    x = x[columns]
    if spec.kind == "R":
        # Reversal: SHORT z if x_t > 0, LONG if x_t <= 0.
        raw = np.where(x.to_numpy() > 0, -1.0, 1.0)
    else:
        raw = np.where(x.to_numpy() > 0, 1.0, -1.0)
    positions = pd.DataFrame(raw, index=x.index, columns=columns)
    if spec.kind == "B":
        tag = _window_tag(spec.window)
        # Flat when |r_open->w| < the pre-registered cut. The cut is on |r|, the
        # predictor return itself, NOT on |x| -- section 3's wording.
        r = _wide(panel, f"r_{tag}")[columns]
        positions = positions.where(r.abs() >= ABS_RETURN_CUT, 0.0)
    positions = positions.where(x.notna(), np.nan)
    return positions


def spec_returns(
    panel: pd.DataFrame, spec: LetfSpec, one_way_bps: float
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(net, gross, traded notional) daily series for one spec.

    Legs are equal-weighted: a single-underlying spec holds +/-1 unit, a pooled
    spec holds +/-1/3 in each of three. Cost is charged on the ABSOLUTE traded
    notional at CROSSINGS_PER_TRADED_DAY crossings a day, so a flat leg pays
    nothing and a pooled day costs the same as a single-name day when all three
    legs are on. There is never netting across days: every spec closes its
    position at the window end, so the next entry is a fresh crossing."""
    if one_way_bps < 0:
        raise LetfRebalancingError(f"one_way_bps must be non-negative, got {one_way_bps}")
    positions = build_positions(panel, spec)
    _, target = spec_signal(panel, spec)
    columns = list(spec.underlyings)
    target = target[columns]
    weight = 1.0 / len(columns)
    gross = (positions * target * weight).sum(axis=1, min_count=len(columns))
    notional = (positions.abs() * weight).sum(axis=1, min_count=len(columns))
    costs = notional * CROSSINGS_PER_TRADED_DAY * one_way_bps / 1e4
    net = gross - costs
    valid = net.notna() & gross.notna()
    return net[valid], gross[valid], notional[valid]


@dataclass
class LetfReplay:
    spec_id: str
    status: str
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    gross_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    notional: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    total_cost: float = 0.0
    n_traded_days: int = 0
    n_flat_days: int = 0
    hit_rate: float | None = None
    first_day: str | None = None
    last_day: str | None = None


def replay_spec(panel: pd.DataFrame, spec: LetfSpec, one_way_bps: float) -> LetfReplay:
    net, gross, notional = spec_returns(panel, spec, one_way_bps)
    if net.empty:
        return LetfReplay(spec_id=spec.spec_id, status="no_realized_days")
    traded = notional > 0
    return LetfReplay(
        spec_id=spec.spec_id,
        status="ok",
        daily_returns=net,
        gross_returns=gross,
        notional=notional,
        total_cost=float((notional * CROSSINGS_PER_TRADED_DAY * one_way_bps / 1e4).sum()),
        n_traded_days=int(traded.sum()),
        n_flat_days=int((~traded).sum()),
        hit_rate=float((net[traded] > 0).mean()) if traded.any() else None,
        first_day=net.index[0].strftime("%Y-%m-%d"),
        last_day=net.index[-1].strftime("%Y-%m-%d"),
    )


# ---------------------------------------------------------------------------
# section 4.1 -- THE MECHANISM GATE
# ---------------------------------------------------------------------------

# PREREGISTRATION section 4.1: "Pass iff b > 0 with t >= 2.0 at w = 15:30."
MECHANISM_GATE_MIN_T = 2.0


@dataclass(frozen=True)
class MechanismRegression:
    """One estimate of PREREGISTRATION section 4.1, which is Tuzun Eq. (2) in
    this family's units:

        y_{u,t}/sigma20_{u,t} = a + b * (x_{u,t} * 100) + c * (r_open->w / sigma20) + e

    with standard errors CLUSTERED BY SESSION -- Tuzun's Table IV note, "standard
    errors are clustered daily". `x * 100` puts x in percent of ADV so that b is
    on Tuzun's *scale of measurement*; it is NOT on Tuzun's *scale of value*,
    because his ADV is the constituent stock's and ours is the ETF's
    (DEVIATIONS_FROM_SOURCE D1). The point estimate is reported next to his 4.32
    with that caveat attached, never as a like-for-like comparison."""

    label: str
    window: str
    n_observations: int
    n_clusters: int
    b: float
    b_t: float
    b_se: float
    c: float
    c_t: float
    a: float
    r_squared_pct: float
    tuzun_reference: dict | None
    is_placebo: bool

    def passes_gate(self) -> bool:
        return bool(self.b > 0 and self.b_t >= MECHANISM_GATE_MIN_T)


def _cluster_ols(
    y: pd.Series, regressors: pd.DataFrame, clusters: pd.Series
) -> tuple[object, int]:
    import statsmodels.api as sm

    design = sm.add_constant(regressors)
    frame = pd.concat([y.rename("_y"), design, clusters.rename("_cluster")], axis=1).dropna()
    if frame.empty:
        raise LetfRebalancingError("no complete observations for the regression")
    fit = sm.OLS(frame["_y"], frame[design.columns]).fit(
        cov_type="cluster", cov_kwds={"groups": frame["_cluster"]}
    )
    return fit, int(frame["_cluster"].nunique())


def regression_4_1(
    panel: pd.DataFrame,
    window: dt_time = PRIMARY_WINDOW,
    *,
    coefficient: pd.DataFrame | None = None,
    label: str | None = None,
    is_placebo: bool = False,
) -> MechanismRegression:
    """Estimate section 4.1 pooled across underlyings and sessions.

    `coefficient`, when given, replaces K -- the hook ADDENDUM_01 declares for
    the seed-12345 permutation DIAGNOSTIC. That diagnostic is not a spec, is not
    in n_local, persists no row and changes no verdict; the gate is always read
    off the estimate with the REAL K."""
    tag = _window_tag(window)
    frame = panel.copy()
    if coefficient is not None:
        long_k = coefficient.stack().rename("K_alt")
        long_k.index = long_k.index.set_names(["date", "underlying"])
        frame = frame.merge(long_k.reset_index(), on=["date", "underlying"], how="left")
        frame[f"x_{tag}"] = frame["K_alt"] * frame[f"r_{tag}"] / frame["adv20"]
    sigma = frame["sigma20"].replace(0.0, np.nan)
    y = frame[f"y_{tag}"] / sigma
    regressors = pd.DataFrame(
        {
            "flow": frame[f"x_{tag}"] * 100.0,
            "ret_to_window": frame[f"r_{tag}"] / sigma,
        }
    )
    fit, n_clusters = _cluster_ols(y, regressors, frame["date"])
    return MechanismRegression(
        label=label or f"section 4.1, w={tag}",
        window=tag,
        n_observations=int(fit.nobs),
        n_clusters=n_clusters,
        b=float(fit.params["flow"]),
        b_t=float(fit.tvalues["flow"]),
        b_se=float(fit.bse["flow"]),
        c=float(fit.params["ret_to_window"]),
        c_t=float(fit.tvalues["ret_to_window"]),
        a=float(fit.params["const"]),
        r_squared_pct=float(fit.rsquared * 100.0),
        tuzun_reference=None if coefficient is not None else TUZUN_TABLE_IV_PANEL_A,
        is_placebo=is_placebo,
    )


def regression_reversal(
    panel: pd.DataFrame, window: dt_time = PRIMARY_WINDOW
) -> MechanismRegression:
    """PREREGISTRATION section 4.1's second half: "the same regression with
    z_{u,t+1} on x_{u,t}; sign reported, not gating." This is Tuzun Eq. (3) /
    Table VI, whose Panel A lagged-flow coefficients are -3.52 (large cap),
    -4.24 (technology) and -0.35 (small cap)."""
    tag = _window_tag(window)
    sigma = panel["sigma20"].replace(0.0, np.nan)
    y = panel["z_next"] / sigma
    regressors = pd.DataFrame(
        {"flow": panel[f"x_{tag}"] * 100.0, "ret_to_window": panel[f"r_{tag}"] / sigma}
    )
    fit, n_clusters = _cluster_ols(y, regressors, panel["date"])
    return MechanismRegression(
        label=f"section 4.1 reversal, z_(t+1) on x_t, w={tag}",
        window=tag,
        n_observations=int(fit.nobs),
        n_clusters=n_clusters,
        b=float(fit.params["flow"]),
        b_t=float(fit.tvalues["flow"]),
        b_se=float(fit.bse["flow"]),
        c=float(fit.params["ret_to_window"]),
        c_t=float(fit.tvalues["ret_to_window"]),
        a=float(fit.params["const"]),
        r_squared_pct=float(fit.rsquared * 100.0),
        tuzun_reference=TUZUN_TABLE_VI_PANEL_A,
        is_placebo=False,
    )


# ---------------------------------------------------------------------------
# section 4.3 -- THE POWER BLOCK, computed from sigma(y) and |r| ONLY
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PowerInputs:
    """Everything section 4.3 permits the power block to see: the sigma of y and
    the |r| distribution. NO strategy return, position or Sharpe is an input,
    and none is computed to produce this."""

    window: str
    n_observations: int
    periods_per_year: float
    sigma_y: float
    mean_abs_r: float
    median_abs_r: float
    p90_abs_r: float
    expected_gross_daily_return_full: float
    expected_gross_daily_return_half: float
    round_trip_cost: float
    sigma_sr_annualized: float


def power_inputs(panel: pd.DataFrame, window: dt_time = PRIMARY_WINDOW) -> PowerInputs:
    """The claimed effect, translated onto this sample WITHOUT touching a return
    series.

    PREREGISTRATION section 4.3: "the claimed effect is the Tuzun Dec-2011
    large-cap number, 6.9 bp of window return per 1% of |r_open->w|, applied
    linearly to the sample's |r_open->15:30| distribution, giving an expected
    gross daily return E[6.9 bp x |r|/1%] and a Sharpe against the sample's
    realised sigma of y; net of 2 bp round trip."

    sigma_sr is the value ADDENDUM_01 section 4 declares before it is computed:
    sqrt(periods_per_year / n_observations), the null sampling standard error of
    a single annualized Sharpe. This project's own choice, not a source formula,
    and the conservative side (correlated specs disperse LESS, and a larger
    sigma_SR raises the required observed Sharpe and so lowers power)."""
    tag = _window_tag(window)
    pooled = panel.groupby("date")[[f"y_{tag}", f"r_{tag}"]].mean().dropna()
    n = len(pooled)
    if n < 2:
        raise LetfRebalancingError("not enough sessions for the power block")
    span_years = (pooled.index[-1] - pooled.index[0]).days / 365.25
    periods_per_year = n / span_years if span_years > 0 else TRADING_DAYS_PER_YEAR
    sigma_y = float(pooled[f"y_{tag}"].std(ddof=1))
    abs_r = pooled[f"r_{tag}"].abs()
    # 6.9 bp per 1% of |r|, applied linearly, session by session.
    per_session = TUZUN_LARGE_CAP_BP_PER_1PCT / 1e4 * (abs_r / 0.01)
    full = float(per_session.mean())
    return PowerInputs(
        window=tag,
        n_observations=n,
        periods_per_year=periods_per_year,
        sigma_y=sigma_y,
        mean_abs_r=float(abs_r.mean()),
        median_abs_r=float(abs_r.median()),
        p90_abs_r=float(abs_r.quantile(0.90)),
        expected_gross_daily_return_full=full,
        expected_gross_daily_return_half=full * IVANOV_LENKEY_OFFSET_FRACTION,
        round_trip_cost=CROSSINGS_PER_TRADED_DAY * cost_arm(BASELINE_COST_ARM).one_way_bps / 1e4,
        sigma_sr_annualized=float(np.sqrt(periods_per_year / n)),
    )


def claimed_sharpe(inputs: PowerInputs, *, fraction: float) -> float:
    """Annualized Sharpe of the claimed effect at `fraction` of Tuzun, NET of
    the pre-registered round trip. Sigma is the sample's realised sigma of y --
    the claim is about the MEAN, not the variance, so the denominator is the
    variance the strategy would actually run at."""
    gross = inputs.expected_gross_daily_return_full * fraction
    net = gross - inputs.round_trip_cost
    return float(net / inputs.sigma_y * np.sqrt(inputs.periods_per_year))


# ---------------------------------------------------------------------------
# screening
# ---------------------------------------------------------------------------


def policy_d_denominators(n_local: int | None = None) -> list[int]:
    """{dsr_n_trials(n_local)} plus the pooled rungs from dsr_policy_n.json.
    Same derivation and same artifact as every other family. The default is this
    family's own pre-declared grid size (PRE_REGISTERED_N_LOCAL = 20) so the
    ladder call-site test can call it with no arguments."""
    from app.services.research_lab.dsr_policy_n import dsr_policy_denominators

    if n_local is None:
        n_local = PRE_REGISTERED_N_LOCAL
    return dsr_policy_denominators(dsr_n_trials(int(n_local)))


def dsr_across_denominators(
    sharpe_annualized: float,
    returns: pd.Series,
    sigma_sr_annualized: float | None,
    denominators: list[int],
    periods_per_year: float,
) -> dict[int, float | None]:
    """DSR at each N. None means the machinery could not produce one there and is
    treated downstream as NOT clearing the bar."""
    return {
        int(n): compute_deflated_sharpe(
            sharpe_annualized,
            returns,
            int(n),
            sigma_sr_annualized,
            periods_per_year=periods_per_year,
        ).dsr
        for n in denominators
    }


@dataclass
class LetfResult:
    spec_id: str
    kind: str
    window: str
    underlyings: tuple[str, ...]
    is_control: bool
    citation: str
    hypothesis: str
    cost_arm: str
    one_way_bps: float
    n_trading_days: int
    first_day: str | None
    last_day: str | None
    sharpe_annualized: float
    gross_sharpe_annualized: float
    annualized_return: float
    annualized_volatility: float
    hit_rate: float | None
    n_traded_days: int
    n_flat_days: int
    total_cost_drag: float
    breakeven_one_way_bps: float | None
    dsr_by_n: dict[int, float | None]
    preservation: dict[str, float | int | bool | None]
    deflated_sharpe: object


def breakeven_one_way_bps(replay: LetfReplay) -> float | None:
    """The one-way cost at which this spec's mean NET daily return hits zero.
    Reported because neither source paper reports a break-even, so this number
    is labelled as this project's own."""
    traded_notional = float(replay.notional.mean())
    if traded_notional <= 0:
        return None
    return float(replay.gross_returns.mean()) / (traded_notional * CROSSINGS_PER_TRADED_DAY) * 1e4


def screen_letf_rebalancing(
    panel: pd.DataFrame,
    specs: list[LetfSpec],
    *,
    cost_arm_key: str = BASELINE_COST_ARM,
    denominators: list[int] | None = None,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> list[LetfResult]:
    """One Sharpe per spec, DSR-corrected at every pre-declared denominator.

    n_trials is the family's literal pre-declared size, controls included,
    raised by dsr_n_trials if that is larger, and NEVER shrunk to however many
    specs happened to survive. sigma_sr is the ddof=1 standard deviation of
    every sibling spec's Sharpe from this same pass."""
    arm = cost_arm(cost_arm_key)
    denominators = denominators if denominators is not None else policy_d_denominators(len(specs))
    n_local = dsr_n_trials(len(specs)) if specs else 0

    replays: dict[str, LetfReplay] = {}
    for spec in specs:
        replay = replay_spec(panel, spec, arm.one_way_bps)
        if replay.status != "ok":
            logger.info("letf_rebalancing spec %s not replayed: %s", spec.spec_id, replay.status)
            continue
        replays[spec.spec_id] = replay

    sharpes = {
        sid: sharpe_ratio(r.daily_returns, periods_per_year=periods_per_year)
        for sid, r in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.spec_id: s for s in specs}
    results: list[LetfResult] = []
    for spec_id, replay in replays.items():
        spec = spec_by_id[spec_id]
        net = replay.daily_returns
        sharpe = sharpes[spec_id]
        dsr_by_n = dsr_across_denominators(sharpe, net, sigma_sr, denominators, periods_per_year)
        deflated_local = compute_deflated_sharpe(
            sharpe, net, n_local, sigma_sr, periods_per_year=periods_per_year
        )
        # preservation_score is a STANDARD SECONDARY CHECK WITH NO EXCEPTIONS
        # (CLAUDE.md section 4). Computed for every spec, controls included.
        preservation = compute_preservation_metrics(
            net, dsr=dsr_by_n.get(n_local), periods_per_year=periods_per_year
        ).as_dict()
        results.append(
            LetfResult(
                spec_id=spec_id,
                kind=spec.kind,
                window=_window_tag(spec.window) if spec.window else "",
                underlyings=spec.underlyings,
                is_control=spec.is_control,
                citation=spec.citation,
                hypothesis=spec.hypothesis,
                cost_arm=arm.key,
                one_way_bps=arm.one_way_bps,
                n_trading_days=len(net),
                first_day=replay.first_day,
                last_day=replay.last_day,
                sharpe_annualized=sharpe,
                gross_sharpe_annualized=sharpe_ratio(
                    replay.gross_returns, periods_per_year=periods_per_year
                ),
                annualized_return=float(net.mean() * periods_per_year),
                annualized_volatility=float(net.std(ddof=1) * np.sqrt(periods_per_year)),
                hit_rate=replay.hit_rate,
                n_traded_days=replay.n_traded_days,
                n_flat_days=replay.n_flat_days,
                total_cost_drag=replay.total_cost,
                breakeven_one_way_bps=breakeven_one_way_bps(replay),
                dsr_by_n=dsr_by_n,
                preservation=preservation,
                deflated_sharpe=deflated_local,
            )
        )
    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


@dataclass
class LetfSummary:
    audit: SessionAudit
    panel: pd.DataFrame
    n_local: int
    denominators: list[int]
    periods_per_year: float
    sigma_sr_annualized: float | None
    results_by_arm: dict[str, list[LetfResult]]
    mechanism: MechanismRegression
    mechanism_secondary: MechanismRegression
    mechanism_placebo: MechanismRegression
    reversal: MechanismRegression

    def baseline_results(self) -> list[LetfResult]:
        return self.results_by_arm[BASELINE_COST_ARM]

    def result(self, spec_id: str) -> LetfResult | None:
        return next((r for r in self.baseline_results() if r.spec_id == spec_id), None)

    def best_candidate(self) -> LetfResult | None:
        live = [r for r in self.baseline_results() if not r.is_control]
        return max(live, key=lambda r: r.sharpe_annualized) if live else None

    def best_control(self) -> LetfResult | None:
        controls = [r for r in self.baseline_results() if r.is_control]
        return max(controls, key=lambda r: r.sharpe_annualized) if controls else None

    def degenerate_controls(self) -> dict[str, bool]:
        """ADDENDUM_01's algebraic claim, checked NUMERICALLY on the run's own
        series rather than asserted: C1 and C2 must equal P_1530 to the last
        decimal place, and C3 must not."""
        pooled = self.result("P_1530")
        out: dict[str, bool] = {}
        for spec_id in ("C1_constant_aum_P_1530", "C2_shuffled_aum_P_1530", "C3_wrong_window_P_1000"):
            control = self.result(spec_id)
            out[spec_id] = bool(
                pooled is not None
                and control is not None
                and np.isclose(control.sharpe_annualized, pooled.sharpe_annualized, rtol=0, atol=1e-12)
            )
        return out

    def mechanism_gate_passes(self) -> bool:
        """PREREGISTRATION section 4.1, read off the 15:30 estimate with the REAL
        K -- never off the placebo, and never off the secondary window."""
        return self.mechanism.passes_gate()

    def verdict(self, threshold: float = VALIDATED_EDGE_BAR) -> tuple[str, str]:
        """Section 4 read MECHANICALLY. The mechanism gate comes first: section
        4.1 says that if it fails, "the family's verdict is written as 'momentum,
        not LETF' whatever the trading specs show, and no spec is recommended for
        registration"."""
        best = self.best_candidate()
        if best is None:
            return "no_candidate", "no non-control spec replayed"
        if not self.mechanism_gate_passes():
            return (
                "momentum_not_letf",
                (
                    f"section 4.1 gate FAILS at w=15:30: b = {self.mechanism.b:+.6f}, "
                    f"clustered t = {self.mechanism.b_t:+.4f} (needs b > 0 and t >= "
                    f"{MECHANISM_GATE_MIN_T}). No spec is recommended for registration "
                    "whatever the trading grid shows."
                ),
            )
        rungs = sorted(best.dsr_by_n)
        n_local = rungs[0]
        local_dsr = best.dsr_by_n.get(n_local)
        if local_dsr is None or local_dsr < threshold:
            return (
                "fails_at_n_local",
                (
                    f"{best.spec_id}: DSR at n_local={n_local} is {local_dsr} < {threshold}. "
                    "Whether this reads DEFINITE_NEGATIVE or UNDERPOWERED is decided by the "
                    "power block (section 4.3), not here."
                ),
            )
        failing = [n for n in rungs if (best.dsr_by_n.get(n) or 0.0) < threshold]
        if failing:
            return (
                "unresolved",
                f"{best.spec_id}: clears {threshold} at n_local={n_local} but fails at {failing}",
            )
        return "passes_all_rungs", f"{best.spec_id}: clears {threshold} at every rung {rungs}"


def run_letf_screening(
    bars_by_ticker: dict[str, pd.DataFrame],
    aum: pd.DataFrame,
    fund_map: dict[str, tuple[str, float]],
) -> LetfSummary:
    """The whole family, every cost arm. Persistence is a SEPARATE call
    (cross_sectional_persistence.persist_cross_sectional_trial_results), never a
    hidden side effect here -- the convention that module's docstring sets."""
    panel, audit = build_panel(bars_by_ticker, aum, fund_map)
    specs = build_family()
    denominators = policy_d_denominators(len(specs))
    periods_per_year = power_inputs(panel).periods_per_year
    results_by_arm = {
        arm.key: screen_letf_rebalancing(
            panel,
            specs,
            cost_arm_key=arm.key,
            denominators=denominators,
            periods_per_year=periods_per_year,
        )
        for arm in COST_ARMS
    }
    baseline = results_by_arm[BASELINE_COST_ARM]
    sigma_sr = (
        float(np.std([r.sharpe_annualized for r in baseline], ddof=1)) if len(baseline) >= 2 else None
    )
    return LetfSummary(
        audit=audit,
        panel=panel,
        n_local=dsr_n_trials(len(specs)),
        denominators=denominators,
        periods_per_year=periods_per_year,
        sigma_sr_annualized=sigma_sr,
        results_by_arm=results_by_arm,
        mechanism=regression_4_1(panel, PRIMARY_WINDOW),
        mechanism_secondary=regression_4_1(panel, SECONDARY_WINDOW),
        mechanism_placebo=regression_4_1(
            panel,
            PRIMARY_WINDOW,
            coefficient=shuffled_coefficient(panel),
            label=f"DIAGNOSTIC: section 4.1 with K permuted across sessions, seed {SHUFFLE_SEED}",
            is_placebo=True,
        ),
        reversal=regression_reversal(panel, PRIMARY_WINDOW),
    )
