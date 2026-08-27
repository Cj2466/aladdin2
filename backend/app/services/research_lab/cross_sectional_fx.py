"""FX cross-sectional family: G10-vs-USD carry, momentum, long-run
reversal, and one carry+momentum blend, expressed against
cross_sectional.py's harness. Structurally this module is
cross_sectional_patterns_d2.py's sibling — its own family object, its own
n_trials denominator, its own never-pooled DSR correction — but it is the
first NON-EQUITY family in the project, and almost everything unusual below
follows from that one fact.

CITATIONS:
 * Fama, E. F., "Forward and Spot Exchange Rates" (Journal of Monetary
   Economics, 1984): the forward premium puzzle. The interest-rate
   differential predicts the SPOT move with the wrong sign relative to
   uncovered interest parity — high-yield currencies do not depreciate
   enough to offset their yield advantage. This is the entire economic
   basis of the carry trade and the reason a carry signal is tested here.
 * Lustig, H., Roussanov, N. & Verdelhan, A., "Common Risk Factors in
   Currency Markets" (Review of Financial Studies, 2011): sorting
   currencies into portfolios on their interest-rate differential produces
   a monotone cross-section of average returns; the high-minus-low
   portfolio ("HML-FX"/carry factor) is the standard cross-sectional
   construction this family's carry specs implement.
 * Menkhoff, L., Sarno, L., Schmeling, M. & Schrimpf, A., "Currency
   Momentum Strategies" (Journal of Financial Economics, 2012): cross-
   sectional momentum in currencies — rank on trailing total return, long
   past winners, short past losers — is significant and largely
   independent of carry, which is why both are tested here and why one
   deliberate blend is included rather than treating them as substitutes.
 * Asness, C. S., Moskowitz, T. J. & Pedersen, L. H., "Value and Momentum
   Everywhere" (Journal of Finance, 2013): defines the currency VALUE
   signal as the negative of the trailing ~5-year return (a real-exchange-
   rate/PPP reversion proxy), and documents its negative correlation with
   momentum across asset classes. This is exactly the long-run reversal
   tested below, and is why the 1260-day (5-year) lookback is the primary
   reversal definition rather than an arbitrary long window.

============================================================================
THE DATA IS DEFECTIVE IN SPECIFIC, MEASURED WAYS — read this before
trusting anything downstream
============================================================================
Every claim in this section was re-verified live against yfinance and FRED
on 2026-08-27 by this module's author, not inherited from a scouting note.

(1) Close falls OUTSIDE [Low, High] on 1.6%-6.2% of days, every pair
    affected (measured: NOK 1.60%, SEK 1.62%, CHF 1.69%, GBP 1.73%, CAD
    1.91%, EUR 2.17%, AUD 2.77%, JPY 4.22%, NZD 6.20%). An OHLC bar whose
    Close is not inside its own range is not a coherent bar, so NO
    range-based, intraday-based, or OHLC-based signal can be defined on
    this data at any horizon. THIS FAMILY IS THEREFORE CLOSE-ONLY, and
    that is enforced structurally, not by convention: _build_fx_family
    asserts no spec sets requires_open or requires_volume, and
    build_fx_price_panel never even reads Open/High/Low.

(2) Volume is IDENTICALLY ZERO on all nine pairs (0 non-zero
    observations out of 5,275-6,137 rows per pair). No volume-, turnover-,
    or liquidity-weighted signal is possible — the Grinblatt-Han-style
    turnover proxy cross_sectional_patterns.py builds for equities has no
    analogue here and must not be faked from a constant.

(3) Triangular cross-rate consistency has a fat tail: implied EURGBP
    (EURUSD/GBPUSD) against directly-quoted EURGBP=X has a median error of
    1.2bp but a 99th percentile of 20.8bp and a MAXIMUM of 1,549bp
    (2008-12-08). This family's response is structural avoidance rather
    than a scrub: it CONSTRUCTS NO CROSS RATES AT ALL. All nine
    instruments are quoted against USD, and the five that yfinance quotes
    USD-first (JPY, CHF, CAD, SEK, NOK) are turned into USD-per-foreign by
    exact reciprocal — 1/x of one series, which introduces no second
    series and therefore no triangular inconsistency. See FX_PAIRS.

(4) NOT flagged by the feasibility scout, found by this module's own
    verification and materially more dangerous than (3): the Close series
    itself carries BAD PRINTS — single-day spikes that fully reverse the
    very next day. Measured examples: EUR +17.31% on 2008-12-08 followed
    by -13.35% (two-day net +1.64%); JPY -15.03%/+18.35% on the same two
    days; NOK +39.35% on 2020-03-20 followed by -34.22%; NOK +11.51% on
    2021-01-01 (a New Year's Day row that should not exist) followed by
    -10.51%. Five of the nineteen detected events fall on the 8th of a
    month in 2008, a clear provider artifact rather than market history.
    Left in, these fabricate enormous fake returns for whichever leg holds
    the currency AND corrupt any volatility estimate: NOK's daily return
    standard deviation falls from 1.108% to 0.784% once they are removed,
    i.e. the bad prints were inflating NOK's measured volatility by 41%,
    which would have directly mis-weighted every inverse-volatility leg in
    this family. scrub_reversing_bad_prints handles this — see its
    docstring for why the test is REVERSAL-based rather than a magnitude
    cap, and how the genuine 2015 SNB de-peg survives it.

(5) The panel contains rows on real holidays (2021-01-01, 2020-12-25 and
    similar are all present), which is where several of (4)'s bad prints
    live. These are not removed wholesale — a stale-but-harmless holiday
    quote mostly produces a ~0% return that costs nothing — but they are
    the reason the scrub in (4) is mandatory rather than optional.

============================================================================
RETURNS ARE TOTAL RETURNS, NOT SPOT — and why that is required here
============================================================================
The harness realizes returns from CrossSectionalData.close via
pct_change(). If `close` held raw SPOT rates, a carry strategy backtested
here would measure only whether the interest differential predicts the SPOT
move — which is the Fama (1984) forward-premium REGRESSION, not the carry
TRADE. The carry trade's return is the differential you actually earn plus
whatever spot does; testing carry on spot alone would systematically omit
the single component the entire literature says carry earns its return
from, and would report a spuriously flat/negative result for a strategy
never actually tested.

build_fx_total_return_panel therefore compounds the realized daily interest
differential onto the scrubbed spot series:
    TR_c(t) = Spot_c(t) * prod_{u <= t} (1 + (r_c(u) - r_usd(u)) / 100 / 365)
so close.pct_change() yields spot return PLUS carry accrual, the standard
FX total-return index. Two consequences that must stay disclosed:

 * The rates used for REALIZED accrual are CONTEMPORANEOUS, deliberately,
   and this is NOT look-ahead. You do not need to know a published
   statistic to earn the rate it measures — the differential is embedded in
   the swap points actually transacted. Look-ahead is a constraint on what
   the SIGNAL may read (see the point-in-time section below), not on what
   the position physically earns while held. These are two genuinely
   different uses of the same panel, and the asymmetry is intentional.
 * Because realized accrual needs a contemporaneous rate for every day, the
   backtest CANNOT run past the last month for which every currency's rate
   is published. That truncation is applied explicitly and reported as
   FXScreeningSummary.carry_data_end, never silently forward-filled — a
   forward-fill past the end of published data would fabricate carry.

The 25bps/yr financing charge (see FX_FINANCING_BPS_PER_YEAR) is the
BROKER'S ROLLOVER MARKUP, charged on top of this — the bid/ask spread on
swap points, not the differential itself. The two are separate, and folding
one into the other in either direction would be double-counting.

============================================================================
POINT-IN-TIME CARRY: THE PUBLICATION LAG IS REAL AND IS 7 MONTHS
============================================================================
FRED's OECD 3-month interbank series (IR3TIB01{CC}M156N) covers all nine
currencies plus USD, MONTHLY, and every one was verified live on
2026-08-27. Publication staleness measured that day, per series: AUD, CHF,
CAD, NZD, SEK, NOK, USD last observation 2026-06-01 (2 months); JPY
2026-05-01 (3 months); EUR and GBP 2026-01-01 (SEVEN months).

The feasibility scout proposed a 6-month point-in-time lag. THAT WOULD BE
LOOK-AHEAD and is not used: on 2026-08-27 a 6-month rule reaches for the
February 2026 observation, which does not exist for EUR or GBP. This module
uses EIGHT months (FX_CARRY_PUBLICATION_LAG_MONTHS) — one month of margin
beyond the worst lag actually observed — so the signal only ever reads a
figure that was comfortably published by the formation date.

The cost of the extra lag is small and was measured rather than assumed.
Mean cross-sectional Spearman correlation between the rate differential
and its own k-months-earlier value, over 285 monthly observations
(2002-04 .. 2026-01): k=1 0.9905, k=3 0.9745, k=6 0.9543, k=7 0.9477, k=9
0.9349, k=12 0.9155. (The scout's 0.956-at-6-months figure reproduces:
0.9543 here.) Carry RANKS — the only thing a cross-sectional sort uses —
are extremely persistent, so an eight-month-old differential ranks the
cross-section almost identically to today's. That persistence is what makes
a monthly, heavily-lagged carry proxy legitimate; it is not an argument
that the lag is free.

KNOWN LIMIT, not closed here: a fixed lag is an APPROXIMATION of a true
vintage reconstruction. FRED/ALFRED expose real-time vintages
(realtime_start/realtime_end) that would say exactly what was published on
any past date; this module does not use them, so it cannot rule out that
some series was even staler at some point in the past than any series is
today. The eight-month margin is a defensible buffer, not a proof. A
vintage-accurate rebuild is the real fix if this family ever produces
something worth trading.

============================================================================
FAMILY SIZE — 36, computed and fixed BEFORE any run
============================================================================
9 signal definitions x 2 holding periods x 2 leg weightings = 36.
The 9 signal definitions are: 3 carry (smoothing windows 1/3/6 months) + 3
momentum (63/126/252 trading days) + 2 long-run reversal (756/1260) + 1
carry+momentum blend. Holds are {63, 126} and weightings are {equal,
inverse_vol}. FX_N_TRIALS is asserted against the built list in
_build_fx_family, so a size drift is a loud import-time failure rather than
a silent change to every future run's n_trials denominator. 36 is
comfortably above deflated_sharpe.MIN_TRIALS_FOR_DSR (5), so unlike D2 this
family's DSR correction proper does compute.

NO 21-DAY HOLD, deliberately, and the reasoning is the whole point of the
two-cost split cross_sectional.py's CONVENTIONS document. This family's
dominant cost is TIME-based (rollover markup, FX_FINANCING_BPS_PER_YEAR:
25bps/yr on gross notional, so 50bps/yr of equity on a fully formed
2.0-gross book), not turnover-based (FX_SPREAD_BPS_ONE_WAY: 1.3bp one-way,
so at most ~2.6bp per full reformation and ~10bp/yr at a 63-day cadence).
Shortening the hold therefore does NOT reduce the cost that actually
dominates — it only multiplies the small one — while carry and value
signals decay over quarters, not weeks. A 21-day variant would spend three
of this family's pre-declared trials re-answering a question the cost
structure already settles.

============================================================================
UNIVERSE AND ITS RESIDUAL BIAS
============================================================================
Membership is cross_sectional.fixed_universe_membership(FX_CURRENCIES) —
the explicit, named gate for an asset class with no point-in-time
index-membership concept. G10-vs-USD is not an index whose constituents
change; no currency here was added or deleted over the window, none
delisted, and the survivorship machinery was_member exists for has nothing
to correct. Passing membership_fn=None would instead route to the S&P 500
gate, make all nine ineligible on every date, and produce a silent
all-zero-return run — the exact failure fixed_universe_membership and
EmptyEligibleUniverseError were built to prevent.

What that does NOT eliminate: G10 is itself a hindsight-flavored choice of
the currencies that are liquid and floating TODAY. A currency that had been
pegged, redenominated, or had capital controls imposed mid-window would
never have made this list. The nine here were all freely floating across
the whole 2006-2026 window, so the effect is small — but "small" is not
"zero", and the 2015 CHF de-peg is a live reminder that the floating/pegged
boundary moves. Disclose it; do not claim it away.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

import httpx
import numpy as np
import pandas as pd

from app.config import settings
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    fixed_universe_membership,
    screen_cross_sectional_universe,
)

logger = logging.getLogger(__name__)

# --- universe -------------------------------------------------------------

# currency -> (yfinance ticker, whether that ticker quotes USD FIRST).
# invert=True means the raw series is FOREIGN per USD (e.g. USDJPY=X is yen
# per dollar) and must be reciprocated to put every column on ONE basis:
# USD per unit of foreign currency, so that "the series went up" means the
# same thing ("the foreign currency appreciated against USD") for all nine.
# Without this the cross-section would rank five currencies on exactly the
# negative of the quantity it ranks the other four on.
#
# A reciprocal is used rather than a directly-quoted inverse ticker on
# purpose: 1/x is an exact transform of a single series, so it cannot
# introduce the triangular inconsistency documented in the module
# docstring's defect (3). No cross rate is ever constructed here.
FX_PAIRS: dict[str, tuple[str, bool]] = {
    "EUR": ("EURUSD=X", False),
    "GBP": ("GBPUSD=X", False),
    "JPY": ("USDJPY=X", True),
    "AUD": ("AUDUSD=X", False),
    "CHF": ("USDCHF=X", True),
    "CAD": ("USDCAD=X", True),
    "NZD": ("NZDUSD=X", False),
    "SEK": ("USDSEK=X", True),
    "NOK": ("USDNOK=X", True),
}

FX_CURRENCIES: list[str] = list(FX_PAIRS)

# FRED OECD 3-month interbank rate series, per currency, plus the USD leg
# every differential is taken against. Verified live 2026-08-27: all ten
# resolve, monthly, complete (no interior gaps) from 2002-04 onward, which
# is the binding start (JPY's) and comfortably precedes the FX panel's own
# 2006-05-16 common start.
FRED_RATE_SERIES: dict[str, str] = {
    "EUR": "IR3TIB01EZM156N",
    "GBP": "IR3TIB01GBM156N",
    "JPY": "IR3TIB01JPM156N",
    "AUD": "IR3TIB01AUM156N",
    "CHF": "IR3TIB01CHM156N",
    "CAD": "IR3TIB01CAM156N",
    "NZD": "IR3TIB01NZM156N",
    "SEK": "IR3TIB01SEM156N",
    "NOK": "IR3TIB01NOM156N",
}
FRED_USD_RATE_SERIES = "IR3TIB01USM156N"

# Earliest date the price fetch asks for. Before every pair's first quote
# (the earliest is JPY at 2003-01-01), so the real common-history start is
# discovered from the data rather than assumed — measured live 2026-08-27 as
# 2006-05-16 (AUDUSD=X is the binding constraint), giving 5,252 rows on
# which all nine are simultaneously quoted. Fetching from a fixed early date
# rather than padding backwards from the caller's `start`
# (cross_sectional_patterns_d2's idiom) is deliberate: this universe has a
# hard natural beginning, so "fetch everything and let formation_start pin
# the formations" always warms the lookbacks maximally, whatever start the
# caller asks for.
FX_PRICE_HISTORY_START = date(2003, 1, 1)


# --- defect (4): the bad-print scrub --------------------------------------

# A day must move at least this much to be considered for scrubbing at all.
# G10 daily volatility is ~0.5-1.1%, so 4% is a 4-7 sigma day: rare enough
# that examining it costs nothing, common enough that every real crisis day
# is examined rather than assumed clean.
FX_SPIKE_MIN_ABS_RETURN = 0.04

# ...and the spike is only treated as a BAD PRINT if the next day gives back
# enough of it that the two-day compounded move is at most this fraction of
# the one-day move. 0.5 means "more than half the move round-tripped
# immediately".
FX_SPIKE_REVERSAL_FRACTION = 0.5


def scrub_reversing_bad_prints(
    prices: pd.DataFrame,
    min_abs_return: float = FX_SPIKE_MIN_ABS_RETURN,
    reversal_fraction: float = FX_SPIKE_REVERSAL_FRACTION,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Removes single-day price spikes that fully reverse the next day —
    the provider artifact documented as defect (4) in the module docstring.
    Returns (scrubbed prices, boolean flag frame).

    The two thresholds default to this module's FX calibration and are
    overridable because the CONSTRUCTION (persistence separates a bad print
    from a real jump) is asset-class-generic while the calibration is not:
    cross_sectional_commodities.py reuses this exact function at much
    higher thresholds (25% spike, 20% reversal) because commodities
    genuinely whipsaw at magnitudes that would be provider artifacts in G10
    FX — see that module's own calibration evidence. Defaults preserve this
    module's original behavior byte-for-byte.

    WHY THE TEST IS REVERSAL-BASED AND NOT A MAGNITUDE CAP. A plain "reject
    any move over X%" filter cannot work on this data, because the largest
    single move in the whole panel is REAL: the 2015-01-16 Swiss National
    Bank de-peg, CHF +19.26% against USD, which does NOT reverse (the next
    day is -0.44%, and the level holds thereafter). That is the single most
    important tail event in G10 carry history — a carry strategy short CHF
    took exactly that loss — and a magnitude cap would delete it, flattering
    every carry spec in this family in precisely the way this project's
    disclosures exist to prevent. What separates a bad print from a real
    jump is not size but PERSISTENCE: a real repricing stays, a bad print
    round-trips within one day. So the rule is: |r_t| >= FX_SPIKE_MIN_ABS_
    RETURN AND |(1+r_t)(1+r_{t+1}) - 1| <= FX_SPIKE_REVERSAL_FRACTION *
    |r_t|. Verified live 2026-08-27 on the real panel: 19 cells flagged out
    of 47,268 (0.04%), the SNB de-peg not among them, Brexit (GBP -7.60%,
    2016-06-27) not among them, and the 2022 gilt-crisis GBP move not among
    them.

    A flagged day's PRICE is set to NaN rather than repaired to an
    interpolated value. Two reasons, both load-bearing: (a) NaN is already
    this harness's documented convention for "no usable price" — the
    currency drops out of its leg's weighted mean for that day and the
    survivors renormalize (see _leg_weighted_return) — so nothing new has
    to be taught to the replay loop; (b) interpolating would FABRICATE a
    price, and while the fabricated value would probably be close to right
    (the spike round-trips, so the true level barely moved), this module
    has no way to verify that per-event and no business asserting it.
    Setting the price to NaN also NaNs both adjacent returns under
    pct_change — the fake spike AND its fake reversal — which is exactly
    the intent: both halves of the artifact are excluded, and the genuine
    two-day move they straddle is forgone rather than guessed at.

    The final row can never be flagged (there is no next day to reverse
    into), which is correct: a spike on the last available day is not yet
    distinguishable from a real repricing, and this function refuses to
    guess."""
    returns = prices.pct_change(fill_method=None)
    next_returns = returns.shift(-1)
    two_day = (1.0 + returns) * (1.0 + next_returns) - 1.0
    flags = (returns.abs() >= min_abs_return) & (
        two_day.abs() <= reversal_fraction * returns.abs()
    )
    flags = flags.fillna(False).astype(bool)
    return prices.mask(flags), flags


# --- price panel ----------------------------------------------------------


def build_fx_price_panel(
    provider: YFinanceProvider, end: date, start: date = FX_PRICE_HISTORY_START
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """The clean G10-vs-USD SPOT panel: one column per currency, all on a
    USD-per-foreign basis, restricted to days on which ALL nine are quoted,
    with reversing bad prints scrubbed out.

    Returns (spot panel, scrub flag frame, currencies with no price data).

    Close-only by construction — Open/High/Low are never read, because
    defect (1) in the module docstring makes them incoherent on this data.
    get_daily_ohlcv is still the fetch primitive (it is the project's one
    batched, retried, alignment-guaranteeing daily fetch) but only its
    "close" frame is used; its "volume" frame is identically zero here, per
    defect (2), and is deliberately dropped rather than passed on to the
    harness where some future signal might innocently read it.

    The dropna(how="any") that defines the common window is what makes this
    a genuine CROSS-SECTION: a formation date on which only six of nine
    currencies are quoted would rank a different, smaller universe than the
    rest of the replay, and with legs of three that is a materially
    different strategy, not a slightly thinner one."""
    tickers = [t for t, _ in FX_PAIRS.values()]
    # get_daily_ohlcv's own missing list is by TICKER; `missing` below is
    # rederived by CURRENCY from the frame that actually came back, which is
    # the vocabulary every other field in this module speaks and covers a
    # ticker that is absent for any reason, not only the empty-Close one.
    frames, _missing_tickers = provider.get_daily_ohlcv(tickers, start, end)
    if not frames or "close" not in frames or frames["close"].empty:
        return pd.DataFrame(), pd.DataFrame(), list(FX_CURRENCIES)

    raw_close = frames["close"]
    missing = [c for c, (t, _) in FX_PAIRS.items() if t not in raw_close.columns]

    columns: dict[str, pd.Series] = {}
    for currency, (ticker, invert) in FX_PAIRS.items():
        if ticker not in raw_close.columns:
            continue
        series = pd.to_numeric(raw_close[ticker], errors="coerce")
        # Non-positive quotes are data errors, not prices; reciprocating one
        # would produce an infinity that np.isfinite gates would then have
        # to catch further downstream.
        series = series.where(series > 0.0)
        columns[currency] = (1.0 / series) if invert else series

    if not columns:
        return pd.DataFrame(), pd.DataFrame(), list(FX_CURRENCIES)

    panel = pd.DataFrame(columns).sort_index()
    panel = panel.dropna(how="any")
    scrubbed, flags = scrub_reversing_bad_prints(panel)
    n_scrubbed = int(flags.to_numpy().sum())
    if n_scrubbed:
        # WARNING, not INFO: these are fabricated prices in a vendor feed,
        # and a run in which this number suddenly jumps is a data-quality
        # event the reader must see even if they never open the summary.
        logger.warning(
            "FX panel: scrubbed %d single-day bad print(s) that fully reversed the next day, "
            "out of %d cells (%s). See scrub_reversing_bad_prints.",
            n_scrubbed,
            flags.size,
            {c: int(flags[c].sum()) for c in flags.columns if int(flags[c].sum())},
        )
    return scrubbed, flags, missing


# --- rates, carry, and the total-return panel -----------------------------

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"

# The project's own FredProvider uses a 10-second timeout, which was
# measured to time out repeatedly on these 25-year monthly histories
# (2026-08-27). This module fetches the same endpoint with a longer timeout
# and a retry, rather than lowering FredProvider's timeout for every other
# caller of a much smaller request.
FRED_TIMEOUT_SECONDS = 60
FRED_ATTEMPTS = 4


def _fetch_fred_series(series_id: str, api_key: str) -> pd.Series:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "units": "lin",
        "observation_start": "1995-01-01",
    }
    last_error: Exception | None = None
    for attempt in range(FRED_ATTEMPTS):
        try:
            with httpx.Client(timeout=FRED_TIMEOUT_SECONDS) as client:
                response = client.get(FRED_OBSERVATIONS_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            values: dict[pd.Timestamp, float] = {}
            for obs in payload.get("observations", []):
                raw = obs.get("value")
                if raw is None or raw == ".":
                    continue  # FRED's own missing sentinel — never fabricate
                values[pd.Timestamp(datetime.strptime(obs["date"], "%Y-%m-%d").date())] = float(raw)
            return pd.Series(values, dtype=float).sort_index()
        except Exception as exc:  # noqa: BLE001 — retried, then re-raised below
            last_error = exc
    raise RuntimeError(f"FRED fetch failed for {series_id} after {FRED_ATTEMPTS} attempts: {last_error}")


def fetch_rate_differentials(api_key: str | None = None) -> pd.DataFrame:
    """The monthly (foreign - USD) 3-month interbank differential panel, in
    ANNUALIZED PERCENT, one column per currency, indexed by observation
    month start. Rows where any currency is missing are dropped, so the
    frame is a complete rectangle — a partially-populated month would rank a
    smaller cross-section than the rest of the replay (same reasoning as
    build_fx_price_panel's dropna).

    This is the RAW panel. It is used two different ways downstream and the
    difference is the point-in-time question:
     * carry SIGNAL — through signal_fx_carry, which applies
       FX_CARRY_PUBLICATION_LAG_MONTHS so a formation only ever reads a
       figure genuinely published by then.
     * carry ACCRUAL — through build_fx_total_return_panel, which uses the
       CONTEMPORANEOUS row, because a held position earns the rate whether
       or not the statistic measuring it has been released yet.
    See the module docstring's total-return and publication-lag sections."""
    key = api_key if api_key is not None else settings.fred_api_key
    if not key:
        raise RuntimeError(
            "FRED_API_KEY is not configured — the FX carry signal cannot be built without the "
            "OECD 3-month interbank panel (see FRED_RATE_SERIES)."
        )
    usd = _fetch_fred_series(FRED_USD_RATE_SERIES, key)
    columns: dict[str, pd.Series] = {}
    for currency, series_id in FRED_RATE_SERIES.items():
        columns[currency] = _fetch_fred_series(series_id, key)
    frame = pd.DataFrame(columns)
    frame = frame.sub(usd, axis=0)
    return frame.dropna(how="any").sort_index()[FX_CURRENCIES]


# See the module docstring's publication-lag section. EIGHT, not the six the
# feasibility scout proposed: the worst staleness measured live on
# 2026-08-27 was SEVEN months (EUR and GBP), so a six-month rule would read
# an observation that did not yet exist. One month of margin on top of the
# worst observed lag.
FX_CARRY_PUBLICATION_LAG_MONTHS = 8

# Financing accrues on CALENDAR days, matching cross_sectional.
# FINANCING_DAYS_PER_YEAR and the fact that an FX position is rolled every
# calendar night including weekends.
DAYS_PER_YEAR = 365.0


def build_fx_total_return_panel(
    spot: pd.DataFrame, rate_differentials: pd.DataFrame
) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Compounds realized daily carry accrual onto the scrubbed spot panel,
    producing the total-return index the harness's pct_change() should see.
    Returns (total-return panel, last date with published rates for every
    currency).

    See the module docstring's total-return section for WHY this is
    required (a spot-only panel tests the Fama forward-premium regression,
    not the carry trade) and why contemporaneous rates are not look-ahead.

    Mechanics: the monthly differential is forward-filled onto the daily
    index — a month's published 3-month rate applies to that month's days —
    and accrued at (differential / 100) / 365 per CALENDAR day elapsed, so a
    weekend carries three days of it exactly as a real rolled position does.
    The accrual factor is built from the RATE panel alone, which has no
    interior gaps, so it never introduces NaNs of its own; the returned
    frame is NaN exactly where the scrubbed spot was NaN. That property is
    what keeps a single scrubbed bad print a single-cell gap instead of
    poisoning every later row through a cumulative product.

    TRUNCATION, and why it is explicit: forward-filling past the last
    published month would fabricate carry for the very period the module
    docstring says is unpublished (EUR/GBP run seven months behind). So the
    panel is CUT at the last date on which every currency has a published
    rate, and that date is returned for the caller to report rather than
    being buried."""
    if spot.empty or rate_differentials.empty:
        return spot, None

    # A month's observation is dated to its first day and governs that whole
    # month, so the last covered day is the end of the last observed month.
    last_month_start = rate_differentials.index.max()
    carry_end = pd.Timestamp(last_month_start) + pd.offsets.MonthEnd(1)

    truncated = spot.loc[spot.index <= carry_end]
    if truncated.empty:
        return truncated, carry_end

    daily_rates = (
        rate_differentials.reindex(rate_differentials.index.union(truncated.index))
        .ffill()
        .reindex(truncated.index)[list(truncated.columns)]
    )

    elapsed = truncated.index.to_series().diff().dt.days.fillna(0.0).to_numpy()
    per_day = (daily_rates.to_numpy(dtype=float) / 100.0) / DAYS_PER_YEAR
    accrual = np.cumprod(1.0 + per_day * elapsed[:, None], axis=0)
    accrual_frame = pd.DataFrame(accrual, index=truncated.index, columns=truncated.columns)

    return truncated * accrual_frame, carry_end


# --- inverse-volatility weighting basis -----------------------------------

# Trailing window for the realized-volatility estimate the inverse-vol legs
# are weighted by. 63 trading days (~1 quarter) is long enough that the
# estimate is not dominated by a handful of days and short enough to track a
# genuine volatility regime change — the same quarter-length convention
# cross_sectional_patterns.TURNOVER_NORMALIZATION_WINDOW already uses, and a
# disclosed judgment call rather than a calibrated constant.
FX_VOL_WINDOW_DAYS = 63
FX_VOL_MIN_PERIODS = 21


def build_inverse_vol_basis(prices: pd.DataFrame) -> pd.DataFrame:
    """1 / trailing realized volatility per currency, aligned to `prices`
    exactly — the leg_weight_basis the "inverse_vol" specs weight their legs
    by (see cross_sectional._resolve_leg_weights).

    Point-in-time by construction: a rolling standard deviation at row i
    reads only rows <= i, so no formation can be weighted by volatility it
    could not have measured. The harness reads the formation row of this
    frame directly, the same row it reads the formation close from.

    WHY INVERSE VOL AT ALL: G10 daily volatilities differ by roughly 2x
    across this panel (measured post-scrub 2026-08-27: CAD 0.53% to AUD/NZD
    0.77%), so an equally weighted leg of three is really a bet dominated by
    whichever currency happens to be most volatile. Inverse-vol weighting is
    the standard risk-parity correction, and testing BOTH it and plain equal
    weighting is exactly why leg weighting is one of this family's two
    pre-declared axes rather than an unexamined default.

    A non-finite or zero volatility yields NaN rather than an infinite
    weight; _resolve_leg_weights treats any unusable basis value as grounds
    to fall back to magnitude weighting for the WHOLE leg, and
    screen_cross_sectional_universe counts how often that happened."""
    returns = prices.pct_change(fill_method=None)
    vol = returns.rolling(FX_VOL_WINDOW_DAYS, min_periods=FX_VOL_MIN_PERIODS).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        basis = 1.0 / vol
    return basis.replace([np.inf, -np.inf], np.nan)


# --- signals --------------------------------------------------------------

# A signal window with fewer than this fraction of its rows populated is
# refused (NaN signal). Same 0.8 register as every other coverage floor in
# this project (cross_sectional_patterns.MIN_SIGNAL_OBS_FRACTION,
# cross_sectional_patterns_d2's own), kept identical for consistency rather
# than recalibrated here. On this panel it is a light guard — the common-
# window dropna already removes partial cross-sections — but it is what
# catches a currency whose window is mostly scrubbed bad prints.
MIN_SIGNAL_OBS_FRACTION = 0.8


def signal_fx_carry(
    history: CrossSectionalData,
    *,
    rate_differentials: pd.DataFrame,
    smoothing_months: int,
    lag_months: int = FX_CARRY_PUBLICATION_LAG_MONTHS,
) -> pd.Series:
    """Lustig/Roussanov/Verdelhan (2011) carry: rank on the (foreign - USD)
    3-month interbank differential, long the highest-yielding tercile, short
    the lowest. Higher differential is a higher signal, which this harness's
    top-is-long convention turns into the long leg — the literature's own
    direction, and Fama's (1984) forward premium puzzle is the reason it is
    expected to pay rather than be arbitraged flat.

    POINT-IN-TIME. The formation date is read from the history view's own
    last row — the view is already truncated to rows <= the formation date
    by the harness, so this cannot see the future even if the arithmetic
    below were wrong. From it, only rate observations dated at or before
    (formation date - lag_months) are eligible, and the signal is the mean
    of the last `smoothing_months` of those. See the module docstring for
    why lag_months is 8 and what it costs (very little: 8-month-lagged
    differentials rank the cross-section at ~0.94 Spearman against
    contemporaneous ones).

    smoothing_months=1 is the raw latest available differential; 3 and 6
    average away month-to-month noise in a series that is already a monthly
    average, at the price of an even older effective observation. All three
    are pre-declared family members, not a search."""
    columns = list(history.close.columns)
    if history.close.empty or rate_differentials.empty:
        return pd.Series(np.nan, index=columns, dtype=float)

    formation = pd.Timestamp(history.close.index[-1])
    cutoff = formation - pd.DateOffset(months=lag_months)
    available = rate_differentials.loc[rate_differentials.index <= cutoff]
    if available.empty:
        return pd.Series(np.nan, index=columns, dtype=float)

    window = available.iloc[-smoothing_months:]
    # A smoothing window that is not fully populated is refused outright
    # rather than silently averaging fewer months than the definition says:
    # two specs differing only in smoothing_months must not collapse to the
    # same signal at the front of the sample.
    if len(window) < smoothing_months:
        return pd.Series(np.nan, index=columns, dtype=float)

    signal = window.mean(axis=0).reindex(columns)
    return signal.where(np.isfinite(signal))


def signal_fx_momentum(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Menkhoff/Sarno/Schmeling/Schrimpf (2012) currency momentum: trailing
    lookback_days total return, P_t / P_{t-lookback} - 1, long past winners
    and short past losers (the paper's own direction, expressed directly
    since higher-is-long is this harness's convention).

    "Total" is literal here, not loose: `history.close` is the total-return
    panel built by build_fx_total_return_panel, so this ranks on spot moves
    PLUS realized carry accrual, which is what the cited paper ranks on. A
    spot-only momentum signal would be a different (and, in that
    literature, weaker) definition."""
    window = history.close.iloc[-lookback_days:]
    first = window.iloc[0]
    last = window.iloc[-1]
    n_obs = window.notna().sum()
    signal = last / first - 1.0
    signal[n_obs < int(lookback_days * MIN_SIGNAL_OBS_FRACTION)] = np.nan
    signal[~np.isfinite(signal)] = np.nan
    return signal


def signal_fx_long_run_reversal(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Asness/Moskowitz/Pedersen (2013) currency VALUE, and De Bondt-Thaler
    style long-horizon reversal generally: the NEGATED trailing
    lookback_days return, so the biggest multi-year LOSERS score highest and
    land in the long leg. AMP define the currency value signal as (minus)
    the ~5-year return precisely as a real-exchange-rate/PPP reversion
    proxy — a currency that has depreciated far over five years is cheap
    relative to purchasing-power parity — which is why 1260 trading days
    (5 years) is the primary definition here and 756 (3 years) the
    disclosed robustness variant.

    The sign flip is done on the signal rather than through a harness-level
    direction flag for the same reason cross_sectional_patterns_d2.
    signal_long_horizon_reversal does it: the harness has no such flag, and
    a negation is exactly equivalent."""
    return -signal_fx_momentum(history, lookback_days=lookback_days)


def _cross_sectional_rank(values: pd.Series) -> pd.Series:
    """Ranks to [0, 1] across the currencies that have a finite value, so
    two signals on completely different scales can be averaged. NaNs stay
    NaN (they must not be imputed to a middling rank — a currency with no
    valid signal is not a currency with an average one)."""
    finite = values[np.isfinite(values)]
    if len(finite) < 2:
        return pd.Series(np.nan, index=values.index, dtype=float)
    ranked = finite.rank(method="average") / float(len(finite))
    return ranked.reindex(values.index)


def signal_fx_carry_momentum_blend(
    history: CrossSectionalData,
    *,
    rate_differentials: pd.DataFrame,
    smoothing_months: int,
    momentum_lookback_days: int,
    lag_months: int = FX_CARRY_PUBLICATION_LAG_MONTHS,
) -> pd.Series:
    """The family's ONE blend definition: the equally weighted average of
    the cross-sectional RANKS of carry and of momentum.

    Ranks, not raw values or z-scores, because the two signals are on
    incommensurable scales — carry is an annualized percentage differential
    (roughly -5 to +6 across this panel) and momentum is a multi-month
    fractional return (roughly -0.3 to +0.3). Averaging them raw would make
    the blend a carry signal with rounding error; z-scoring across only nine
    names is dominated by whichever signal happens to have the fatter tail
    that month. A rank average is scale-free and, with nine names, stable.

    Included as exactly ONE definition rather than a grid over blend
    weights and component parameters, which is what "one carry+momentum
    blend" means in the pre-declared family: Asness/Moskowitz/Pedersen
    (2013) report carry/value/momentum combinations as the natural test of
    whether the components are independent, and one honest combination
    answers that. A blend-weight sweep would multiply n_trials to answer a
    question this family has no power to resolve.

    A currency missing EITHER component gets a NaN blend — no partial
    blending, the same no-partial-state discipline the harness applies to
    leg weighting."""
    carry = signal_fx_carry(
        history,
        rate_differentials=rate_differentials,
        smoothing_months=smoothing_months,
        lag_months=lag_months,
    )
    momentum = signal_fx_momentum(history, lookback_days=momentum_lookback_days)
    blended = (_cross_sectional_rank(carry) + _cross_sectional_rank(momentum)) / 2.0
    return blended.where(np.isfinite(blended))


# --- the family -----------------------------------------------------------

FX_CARRY_CITATION = (
    "Fama, 'Forward and Spot Exchange Rates' (Journal of Monetary Economics, 1984); "
    "Lustig, Roussanov & Verdelhan, 'Common Risk Factors in Currency Markets' "
    "(Review of Financial Studies, 2011)"
)
FX_MOMENTUM_CITATION = (
    "Menkhoff, Sarno, Schmeling & Schrimpf, 'Currency Momentum Strategies' "
    "(Journal of Financial Economics, 2012)"
)
FX_REVERSAL_CITATION = (
    "Asness, Moskowitz & Pedersen, 'Value and Momentum Everywhere' (Journal of Finance, 2013); "
    "De Bondt & Thaler, 'Does the Stock Market Overreact?' (Journal of Finance, 1985)"
)
FX_BLEND_CITATION = (
    "Asness, Moskowitz & Pedersen, 'Value and Momentum Everywhere' (Journal of Finance, 2013), "
    "on combining carry/value/momentum across asset classes"
)

# The four pre-declared axes. Their product IS the family size — see
# FX_N_TRIALS, which is asserted against the built list.
FX_CARRY_SMOOTHING_MONTHS: tuple[int, ...] = (1, 3, 6)
FX_MOMENTUM_LOOKBACK_DAYS: tuple[int, ...] = (63, 126, 252)
FX_REVERSAL_LOOKBACK_DAYS: tuple[int, ...] = (756, 1260)
FX_HOLDING_DAYS: tuple[int, ...] = (63, 126)
FX_LEG_WEIGHTINGS: tuple[str, ...] = ("equal", "inverse_vol")

# The blend's own component parameters: the MIDDLE carry smoothing and the
# MIDDLE momentum lookback, fixed rather than swept (see
# signal_fx_carry_momentum_blend on why the blend is one definition).
FX_BLEND_SMOOTHING_MONTHS = 3
FX_BLEND_MOMENTUM_LOOKBACK_DAYS = 126

# 3 carry + 3 momentum + 2 reversal + 1 blend.
FX_N_SIGNAL_DEFINITIONS = (
    len(FX_CARRY_SMOOTHING_MONTHS)
    + len(FX_MOMENTUM_LOOKBACK_DAYS)
    + len(FX_REVERSAL_LOOKBACK_DAYS)
    + 1
)

# The pre-declared family size and the honest n_trials denominator for this
# family's OWN, never-pooled DSR correction: 9 signal definitions x 2 holds
# x 2 leg weightings = 36. Computed from the axes above rather than typed as
# a literal, so the two can never disagree; _build_fx_family asserts the
# built list matches it.
FX_N_TRIALS = FX_N_SIGNAL_DEFINITIONS * len(FX_HOLDING_DAYS) * len(FX_LEG_WEIGHTINGS)

# Terciles. With nine currencies this is the only sort that yields legs
# which are portfolios rather than single picks while staying disjoint:
# floor(9 * 1/3) = 3 per leg, 6 of 9 names used. It is also the standard G10
# construction in the cited literature (Lustig/Roussanov/Verdelhan sort a
# much larger currency universe into 5-6 portfolios; at G10 scale terciles
# are the conventional reduction). Asserted in _build_fx_family, because
# floating-point drift in this constant would silently change every leg's
# size.
FX_RANK_FRACTION = 1.0 / 3.0

# Below cross_sectional.DEFAULT_MIN_NAMES_PER_LEG (5), and that is a
# deliberate, disclosed departure rather than an oversight. That default
# encodes "a leg smaller than 5 is a stock pick, not a decile portfolio" —
# reasoning calibrated for a several-hundred-name equity cross-section. A
# nine-instrument universe cannot produce a five-name long leg AND a
# disjoint five-name short leg at all (2 * 5 > 9), so keeping the default
# would not make this family more rigorous; it would make it produce
# literally nothing. Three is what the G10 carry literature itself uses.
# The honest cost is that these legs ARE concentrated, single-currency
# events move them, and that is disclosed in FXScreeningSummary rather than
# hidden behind a threshold that was never meant for this asset class.
FX_MIN_NAMES_PER_LEG = 3

# Every spec is given the SAME lookback (the family's longest, the 5-year
# reversal window), not its own signal's minimum. This costs the
# short-lookback specs some replay length and buys something worth more: all
# 36 specs form over the IDENTICAL date range, so their Sharpes are
# measured on one sample. That matters concretely here because
# screen_cross_sectional_universe derives the DSR's sigma_sr from the spread
# of sibling Sharpes — siblings measured over different windows (one
# including the 2008 crisis, another starting after it) would make that
# spread partly an artifact of differing samples rather than of differing
# signals, and would let a spec look good merely by having skipped a bad
# regime. Signals still read only what they need (each slices its own tail
# out of the view).
FX_LOOKBACK_DAYS = max(FX_REVERSAL_LOOKBACK_DAYS)

# One-way cost per unit of gross notional traded, charged per formation.
# G10 spot spreads are the tightest in any asset class this project trades:
# roughly 0.1-0.5 pips on EURUSD in normal conditions, wider on NOK/SEK/NZD.
# 1.3bp blended one-way is a deliberately conservative institutional
# estimate across the nine — several times the top-of-book spread on the
# majors — and it is SMALL on purpose, because for this family it is the
# minor cost (see FX_FINANCING_BPS_PER_YEAR).
FX_SPREAD_BPS_ONE_WAY = 1.3

# THE DOMINANT COST, and the reason this family has no 21-day hold. 25bps
# per YEAR per unit of gross notional HELD: the broker's markup on rolling
# an FX position (the bid/ask on tom-next swap points), NOT the interest
# differential itself — that is already earned inside the total-return panel
# (see build_fx_total_return_panel). Passed as a per-unit-of-gross rate
# because BOTH legs of an FX book finance, which is exactly the case
# cross_sectional.CrossSectionalConfig.financing_bps_per_year documents as
# "pass the per-unit rate directly": a fully formed long_short book carries
# gross 2.0, so this costs 50bps/yr of equity. Compare the turnover charge
# above: ~2.6bp per full reformation, ~10bp/yr at the 63-day cadence. Time
# dominates turnover by roughly 5x, so shortening the hold raises total cost
# rather than lowering it.
FX_FINANCING_BPS_PER_YEAR = 25.0


def _build_fx_family(rate_differentials: pd.DataFrame) -> list[CrossSectionalSpec]:
    """Assembles the full, fixed 36-definition FX family: 9 signal
    definitions x FX_HOLDING_DAYS x FX_LEG_WEIGHTINGS, every one
    long_short (there is no universe-hedged variant — hedging a nine-name
    cross-section against its own equally weighted self leaves a three-name
    tilt, not a meaningfully different hypothesis, and would spend trials
    on a construction artifact).

    `rate_differentials` is bound into the carry and blend signal functions
    at build time via closures, which is why the family is BUILT rather
    than a module-level constant: those two signal kinds need a data panel
    that only exists after a network fetch. Nothing else about a spec
    depends on it — pattern_ids, axes and count are fixed — so tests can
    build the identical family shape from any frame."""
    specs: list[CrossSectionalSpec] = []

    def add(pattern_id: str, family: str, citation: str, signal_fn) -> None:
        for holding in FX_HOLDING_DAYS:
            for weighting in FX_LEG_WEIGHTINGS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"{pattern_id}_h{holding}_{weighting}",
                        family=family,
                        citation=citation,
                        signal_fn=signal_fn,
                        lookback_days=FX_LOOKBACK_DAYS,
                        holding_days=holding,
                        portfolio="long_short",
                        rank_fraction=FX_RANK_FRACTION,
                        leg_weighting=weighting,  # type: ignore[arg-type]
                    )
                )

    for months in FX_CARRY_SMOOTHING_MONTHS:
        add(
            f"fx_carry_s{months}",
            "fx_carry",
            FX_CARRY_CITATION,
            lambda h, m=months: signal_fx_carry(
                h, rate_differentials=rate_differentials, smoothing_months=m
            ),
        )

    for lookback in FX_MOMENTUM_LOOKBACK_DAYS:
        add(
            f"fx_momentum_l{lookback}",
            "fx_momentum",
            FX_MOMENTUM_CITATION,
            lambda h, lb=lookback: signal_fx_momentum(h, lookback_days=lb),
        )

    for lookback in FX_REVERSAL_LOOKBACK_DAYS:
        add(
            f"fx_reversal_l{lookback}",
            "fx_long_run_reversal",
            FX_REVERSAL_CITATION,
            lambda h, lb=lookback: signal_fx_long_run_reversal(h, lookback_days=lb),
        )

    add(
        f"fx_blend_s{FX_BLEND_SMOOTHING_MONTHS}_l{FX_BLEND_MOMENTUM_LOOKBACK_DAYS}",
        "fx_carry_momentum_blend",
        FX_BLEND_CITATION,
        lambda h: signal_fx_carry_momentum_blend(
            h,
            rate_differentials=rate_differentials,
            smoothing_months=FX_BLEND_SMOOTHING_MONTHS,
            momentum_lookback_days=FX_BLEND_MOMENTUM_LOOKBACK_DAYS,
        ),
    )

    assert len(specs) == FX_N_TRIALS, (
        f"FX family has {len(specs)} definitions, not the pre-declared {FX_N_TRIALS} "
        f"({FX_N_SIGNAL_DEFINITIONS} signal definitions x {len(FX_HOLDING_DAYS)} holds x "
        f"{len(FX_LEG_WEIGHTINGS)} weightings) — this family's whole point is being an exact, "
        "fixed enumeration declared before any run; a size drift here silently changes n_trials."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    # Close-only, structurally — see the module docstring's defects (1) and
    # (2). If any future signal here sets one of these, the OHLC/volume
    # defects make it unsound on this data and the family must be
    # reconsidered, not silently allowed.
    assert not any(s.requires_open or s.requires_volume or s.requires_market_cap for s in specs), (
        "the FX panel's Open/High/Low are incoherent (Close falls outside [Low,High] on up to 6.2% "
        "of days) and its Volume is identically zero — this family must stay Close-only."
    )
    assert all(s.holding_days in FX_HOLDING_DAYS for s in specs)
    assert 21 not in FX_HOLDING_DAYS, (
        "a 21-day hold would multiply this family's DOMINANT time-based financing cost's number of "
        "reformations without reducing it — see FX_FINANCING_BPS_PER_YEAR."
    )
    assert all(s.leg_weighting in FX_LEG_WEIGHTINGS for s in specs)
    assert all(s.lookback_days == FX_LOOKBACK_DAYS for s in specs)
    # Guards the floating-point leg-size arithmetic FX_RANK_FRACTION feeds:
    # select_leg_tickers computes max(1, int(n * rank_fraction)), and at
    # n = 9 that must be 3 with the two legs disjoint.
    n_leg = max(1, int(len(FX_CURRENCIES) * FX_RANK_FRACTION))
    assert n_leg == 3 and 2 * n_leg <= len(FX_CURRENCIES), (
        f"FX_RANK_FRACTION yields legs of {n_leg} from {len(FX_CURRENCIES)} currencies — expected "
        "disjoint terciles of 3."
    )
    return specs


def build_fx_family(rate_differentials: pd.DataFrame) -> list[CrossSectionalSpec]:
    """Public wrapper over _build_fx_family — see that function."""
    return _build_fx_family(rate_differentials)


# --- production entry point -----------------------------------------------


@dataclass
class FXScreeningSummary:
    """screen_fx_family's full result. Every caution this family carries is
    a TYPED FIELD here, not a docstring paragraph a caller could skip: the
    data defects that were repaired, how much data they cost, where the
    carry data actually ends, and how concentrated the legs are."""

    results: list[CrossSectionalScreeningResult]
    n_trials: int
    panel_start: date | None
    panel_end: date | None
    n_panel_rows: int
    # Currencies for which no price data resolved at all (empty in every
    # healthy run — reported for the same reason Round C reports its
    # missing tickers: a result read without knowing how much of the
    # universe was priceable is not interpretable).
    missing_price_data: list[str]
    # Defect (4): how many single-day bad prints the reversal scrub removed,
    # in total and per currency. A first-class count so "the scrub did
    # something enormous this run" can never go unnoticed.
    n_bad_prints_scrubbed: int
    bad_prints_by_currency: dict[str, int]
    # The last date on which every currency's 3-month rate is published;
    # the backtest is truncated here rather than forward-filling fabricated
    # carry. See build_fx_total_return_panel.
    carry_data_end: date | None
    carry_publication_lag_months: int
    leg_size: int
    text: str = ""
    warnings: list[str] = field(default_factory=list)


def _build_summary_text(summary: FXScreeningSummary) -> str:
    return (
        f"FX CROSS-SECTIONAL FAMILY — READ BEFORE TRUSTING ANY NUMBER. Pre-declared family size "
        f"{summary.n_trials} definitions (9 signal definitions x {len(FX_HOLDING_DAYS)} holds x "
        f"{len(FX_LEG_WEIGHTINGS)} leg weightings), fixed before the run and used as the DSR's "
        f"n_trials denominator in this family's own, never-pooled screening call. Universe: "
        f"{len(FX_CURRENCIES)} G10 currencies vs USD, gated by fixed_universe_membership (there is "
        f"no point-in-time index membership to respect for FX, and passing membership_fn=None would "
        f"have made every currency ineligible on every date). Legs are terciles of "
        f"{summary.leg_size} currencies — genuinely concentrated, below the harness's own "
        f"DEFAULT_MIN_NAMES_PER_LEG=5, because a 9-name universe cannot produce disjoint 5-name "
        f"legs; single-currency events move these legs and no Sharpe here should be read as though "
        f"it came from a diversified decile portfolio. Panel: {summary.n_panel_rows} rows "
        f"{summary.panel_start} .. {summary.panel_end}. DATA REPAIRS APPLIED: "
        f"{summary.n_bad_prints_scrubbed} single-day bad prints (spikes that fully reversed the "
        f"next day) were removed as NaN — the provider's Close series carries these, and left in "
        f"they fabricate returns and inflate volatility (NOK's measured daily vol falls 41% once "
        f"they are gone). The panel is CLOSE-ONLY because Close falls outside [Low,High] on up to "
        f"6.2% of days, and no volume signal exists because Volume is identically zero on all nine "
        f"pairs. RETURNS ARE TOTAL RETURNS: realized daily carry accrual is compounded onto spot, "
        f"so carry specs are testing the carry TRADE and not merely the Fama forward-premium "
        f"regression; realized accrual uses contemporaneous rates (which is not look-ahead — a "
        f"position earns a rate whether or not the statistic measuring it is published), while the "
        f"carry SIGNAL uses only rates lagged {summary.carry_publication_lag_months} months, one "
        f"month beyond the worst publication lag observed live (7 months, EUR/GBP). Carry data ends "
        f"{summary.carry_data_end}; the backtest is truncated there rather than forward-filling "
        f"carry that was never published. Costs are split by construction: "
        f"{FX_SPREAD_BPS_ONE_WAY}bp one-way per unit of gross notional TRADED, and "
        f"{FX_FINANCING_BPS_PER_YEAR}bps/yr per unit of gross notional HELD (the rollover markup, "
        f"not the differential) — the time-based charge dominates by roughly 5x, which is why this "
        f"family declares no 21-day hold: a shorter hold would multiply the small cost without "
        f"reducing the large one."
    )


def screen_fx_family(
    end: date,
    start: date | None = None,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
    rate_differentials: pd.DataFrame | None = None,
) -> FXScreeningSummary:
    """The full FX screening pass, scoped to ONLY this family's 36
    definitions — mirrors cross_sectional_patterns_d2.screen_d2_reversal_
    family's shape (own family object, own n_trials, own config default, own
    typed disclosure) with the differences this asset class forces.

    `start` is the earliest FORMATION date (config.formation_start), not the
    earliest data date: price history is always fetched from
    FX_PRICE_HISTORY_START so the 5-year lookback is warmed as fully as the
    data allows regardless of what the caller asks for. Left None, formations
    begin as soon as the lookback is satisfied — the recommended call, since
    this family's whole sample is only ~20 years and a later start only
    shrinks it.

    `rate_differentials` is injectable so tests need no network; left None it
    is fetched from FRED (see fetch_rate_differentials).

    The default config sets this family's two real costs (see
    FX_SPREAD_BPS_ONE_WAY and FX_FINANCING_BPS_PER_YEAR) and the tercile leg
    floor. A caller-supplied config is used EXACTLY as given and never
    silently patched — the same contract screen_d2_reversal_family keeps —
    except for formation_start, which is derived from `start`."""
    provider = provider if provider is not None else YFinanceProvider()
    if config is None:
        config = CrossSectionalConfig(
            cost_bps=FX_SPREAD_BPS_ONE_WAY,
            financing_bps_per_year=FX_FINANCING_BPS_PER_YEAR,
            min_names_per_leg=FX_MIN_NAMES_PER_LEG,
        )
    if start is not None:
        config.formation_start = start

    warnings: list[str] = []

    spot, flags, missing = build_fx_price_panel(provider, end)
    if spot.empty:
        summary = FXScreeningSummary(
            results=[],
            n_trials=FX_N_TRIALS,
            panel_start=None,
            panel_end=None,
            n_panel_rows=0,
            missing_price_data=missing,
            n_bad_prints_scrubbed=0,
            bad_prints_by_currency={},
            carry_data_end=None,
            carry_publication_lag_months=FX_CARRY_PUBLICATION_LAG_MONTHS,
            leg_size=max(1, int(len(FX_CURRENCIES) * FX_RANK_FRACTION)),
            warnings=["No FX price data resolved — nothing was screened."],
        )
        summary.text = _build_summary_text(summary)
        return summary

    if missing:
        warnings.append(
            f"{len(missing)} of {len(FX_CURRENCIES)} currencies resolved no price data ({missing}); "
            "the cross-section screened is smaller than the declared universe."
        )

    if rate_differentials is None:
        rate_differentials = fetch_rate_differentials()

    total_return, carry_end = build_fx_total_return_panel(spot, rate_differentials)
    if total_return.empty:
        warnings.append(
            "The price panel and the published-rate window do not overlap — no total-return panel "
            "could be built."
        )

    basis = build_inverse_vol_basis(total_return)
    data = CrossSectionalData(close=total_return, leg_weight_basis=basis)

    specs = build_fx_family(rate_differentials)
    results = (
        screen_cross_sectional_universe(
            data, specs, config, fixed_universe_membership(FX_CURRENCIES)
        )
        if not total_return.empty
        else []
    )

    per_currency = {c: int(flags[c].sum()) for c in flags.columns} if not flags.empty else {}
    summary = FXScreeningSummary(
        results=results,
        n_trials=FX_N_TRIALS,
        panel_start=total_return.index[0].date() if not total_return.empty else None,
        panel_end=total_return.index[-1].date() if not total_return.empty else None,
        n_panel_rows=len(total_return),
        missing_price_data=missing,
        n_bad_prints_scrubbed=int(sum(per_currency.values())),
        bad_prints_by_currency=per_currency,
        carry_data_end=carry_end.date() if carry_end is not None else None,
        carry_publication_lag_months=FX_CARRY_PUBLICATION_LAG_MONTHS,
        leg_size=max(1, int(len(FX_CURRENCIES) * FX_RANK_FRACTION)),
        warnings=warnings,
    )
    summary.text = _build_summary_text(summary)
    return summary
