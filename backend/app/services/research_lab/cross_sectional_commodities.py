"""The Commodities family: cross-sectional momentum, long-run reversal, and
one momentum+value blend across a fixed 11-ETF single-commodity basket,
expressed against cross_sectional.py's harness.

Structurally this module is cross_sectional_fx.py's sibling (fixed non-equity
universe via fixed_universe_membership, close-only panel, a reversal-based
bad-print scrub, equal/inverse-vol leg weighting, a family-max lookback so
every sibling Sharpe is measured on one sample) — its own family object, its
own n_trials denominator, its own never-pooled DSR correction.

CITATIONS:
 * Erb, C. B. & Harvey, C. R., "The Strategic and Tactical Value of
   Commodity Futures" (Financial Analysts Journal, 2006): trailing-return
   momentum portfolios in commodity futures earn large spreads; the paper's
   central point — a commodity portfolio's return is dominated by roll and
   rebalancing effects rather than spot appreciation — is also exactly why
   this family tests INVESTABLE total returns rather than spot proxies.
 * Miffre, J. & Rallis, G., "Momentum strategies in commodity futures
   markets" (Journal of Banking & Finance, 2007): 13 profitable momentum
   strategies in commodity futures with ranking periods of 1-12 months,
   long past winners / short past losers — the direct cross-sectional
   construction the momentum specs here implement.
 * Asness, C. S., Moskowitz, T. J. & Pedersen, L. H., "Value and Momentum
   Everywhere" (Journal of Finance, 2013): defines commodity VALUE as the
   negative of the trailing ~5-year return and documents value and momentum
   working — and being negatively correlated — within commodities. This is
   the long-run reversal tested below (1260 days primary, 756 the
   robustness variant), and their finding that the value/momentum COMBO is
   stronger than either alone is why exactly one blend is included.
 * De Bondt, W. F. M. & Thaler, R., "Does the Stock Market Overreact?"
   (Journal of Finance, 1985): the original long-horizon reversal evidence
   the value definition generalizes.

============================================================================
WHY ETF PROXIES AND WHY NO CARRY SIGNAL — the load-bearing data finding
============================================================================
Every claim here was re-verified live against yfinance on 2026-08-27 by this
module's author, not inherited from the feasibility scout that first found
it.

Yahoo's raw futures tickers (NG=F, CL=F, GC=F, ZW=F, ...) are a NAIVE
FRONT-MONTH SPLICE: at each roll the series jumps from the expiring
contract's price to the next contract's price with no adjustment, so chained
pct_change() returns credit the contango gap as if it were return, and
expired contracts are purged from the feed so the splice cannot be repaired
after the fact. Measured on NG=F vs UNG (an investable natural-gas proxy
whose NAV pays the true roll cost) over the same 16.6 years of shared
trading days: NG=F's chained-return CAGR is -4.20%/yr while UNG's is
-25.42%/yr — the splice fabricates +28.4%/yr of phantom return on this one
commodity. The fabrication is visibly mechanical: NG=F has 537 days with
|return| >= 5%, and they cluster in the month's roll window (220 in days
21-31 vs 159/158 in the other two thirds), while UNG's 385 such days are
flat across the month (140/125/120). CONSEQUENCE, and it bounds this whole
family's scope: no carry / term-structure / roll-yield signal is honestly
backtestable from free data today — the term structure IS the thing the
splice destroys. This family is therefore momentum/reversal ONLY, and the
separate, clearly-not-yet-usable futures_curve_collector.py exists to start
recording the contract-level data a real carry test would need years from
now. That collector shares no code or imports with this module in either
direction, so its accumulating file cannot leak into these results.

The ETF panel does not have this defect because an ETF's NAV return is what
a real holder earned: the fund itself rolls its futures (USO, UNG, UGA,
CORN, WEAT, SOYB, CPER) or pays storage out of assets (GLD, SLV, PPLT,
PALL), so roll yield, storage and expense ratios (0.25%-0.85%/yr across
this basket) are all INSIDE the price series — costs are embedded, not
forgotten. Two disclosed consequences: (a) these returns are net of real
frictions the futures literature's excess-return indices exclude, so
results here should sit BELOW the cited papers' gross spreads — the honest
direction; (b) the basket mixes physically-backed trusts with futures-based
funds, so relative returns embed different carry channels (storage+expense
vs roll). Momentum on investable total returns ranks on exactly what a
holder of these instruments experienced, which is the tradeable form of the
hypothesis.

============================================================================
THE UNIVERSE: 11 SINGLE-COMMODITY ETFs, ONE INSTRUMENT PER COMMODITY
============================================================================
  Metals    GLD (gold), SLV (silver), PPLT (platinum), PALL (palladium),
            CPER (copper)
  Energy    USO (WTI crude), UNG (natural gas), UGA (gasoline)
  Grains    CORN (corn), WEAT (wheat), SOYB (soybeans)

VERIFIED LIVE 2026-08-27: all eleven resolve on yfinance; the common clean
window — every name priced on the same day — runs 2011-11-15 to 2026-08-26,
3,715 rows (~14.7 years), bounded by CPER's own 2011-11-15 inception.

Two exclusion rules, both applied BEFORE any backtest was run:
 * ONE INSTRUMENT PER COMMODITY: duplicate wrappers of the same metal
   (IAU, SGOL vs GLD) and multi-commodity baskets (DBC, DBA, DBB, DBE,
   GSG) are excluded — a basket inside a cross-section double-counts its
   constituents' signals against the constituents themselves.
 * REDUNDANCY AT 0.90: an instrument whose daily-return correlation with an
   already-included instrument exceeds COMMODITIES_REDUNDANCY_CORR_LIMIT
   (0.90) over the common window is the same bet, not a new one. Exactly
   one candidate fails this: BNO (Brent crude), measured at 0.942 against
   USO — the pair the feasibility scout flagged at "~0.95", re-verified
   here. USO is kept (older, more liquid); BNO is excluded rather than
   letting one economic exposure occupy two of a three-name leg. After the
   exclusion the highest remaining pair is GLD/SLV at 0.796.

WHAT 11 TICKERS ACTUALLY BUYS, measured rather than implied: the
eigenvalue-based effective number of independent bets in this panel
(sum(lambda)^2 / sum(lambda^2) of the daily-return correlation spectrum) is
5.85 — about half the nominal count, because the sectors co-move (GLD/SLV
0.80, USO/UGA 0.79, CORN/WEAT 0.64). Every run recomputes and reports this
as CommoditiesScreeningSummary.effective_breadth; no result from this
family should be read as if 11 names meant 11 independent things. Legs of 3
from a ~6-effective-bet universe are genuinely concentrated, and that is
disclosed in the summary text of every run.

fixed_universe_membership is the right gate for the same reason it is for
bonds and FX: there is no point-in-time index-membership concept to get
wrong, no name in the basket delisted or closed over the window, and the
survivorship machinery was_member exists for has nothing to correct. The
residual hindsight channel fixed_universe_membership's docstring warns
about is real here too and slightly larger than for the bond basket:
today's liquid single-commodity lineup is known only today, and commodity
ETPs HAVE closed over this window (mostly levered/inverse notes, but some
plain ones). None of the eleven chosen ever closed or gapped, so the bias
enters only through the hand-picking of survivors — disclosed, not claimed
away.

============================================================================
DATA REPAIR: TWO PROVEN BAD PRINTS, AND A SCRUB THAT SPARES REAL CRISES
============================================================================
The panel was scanned for FX-style single-day spikes that fully reverse the
next day. At commodity scale almost every such event is REAL — USO fell
17.5% and rebounded 14.0% across 2020-03-18/19, UNG whipsaws >=10% in both
directions routinely, WEAT did it in the 2022 invasion repricing — so this
family's scrub thresholds are far higher than FX's 4%/50%:

  COMMODITY_SPIKE_MIN_ABS_RETURN = 0.25   (vs FX 0.04)
  COMMODITY_SPIKE_REVERSAL_FRACTION = 0.20 (vs FX 0.50)

i.e. only a >=25% single-day move of which more than 80% round-trips the
very next day is treated as fabricated. On the real panel this flags
exactly TWO cells, and both were independently PROVEN fabricated by
cross-checking copper futures on the same dates: CPER printed -33.15% on
2014-12-04 (then +49.89%; two-day net +0.20%) while HG=F moved +1.37%, and
CPER printed -28.66% on 2015-02-02 (then +45.71%) while HG=F moved -0.67%.
Those are thin-closing-print artifacts of a then-tiny fund, not copper.
Meanwhile every verified-real crisis move clears the scrub by construction:
USO 2020-03-09 (-25.3%) reversed only 24% of itself the next day; SLV's
2026-01-30 -28.5% did not reverse at all; UNG's 2026-02-02 -24.85% sits
below the magnitude floor. Left in, the two bad prints would fabricate
double-digit single-day leg returns for whichever leg held CPER and inflate
every inverse-vol weight computed from a window containing them. Flagged
prices become NaN (never interpolated), reusing cross_sectional_fx.
scrub_reversing_bad_prints — the construction is shared; only the
calibration differs, and both are pre-declared constants.

============================================================================
FAMILY SIZE — 24, COMPUTED AND FIXED BEFORE ANY RUN
============================================================================
6 signal definitions x 2 holding periods x 2 leg weightings = 24.
The 6 signal definitions: 3 momentum (63/126/252 trading days — the
1-to-12-month band Miffre-Rallis and Erb-Harvey document) + 2 long-run
reversal (756/1260 — AMP's 5-year commodity value plus a 3-year robustness
variant) + 1 momentum+value rank blend (momentum 126 x reversal 1260, the
middle momentum window and the primary value window, fixed rather than
swept). Holds are {63, 126} and weightings are {equal, inverse_vol}.
COMMODITIES_N_TRIALS is computed from the axes and asserted against the
built list in _build_commodities_family, so a size drift is a loud failure
rather than a silent change to every future run's n_trials denominator. 24
clears deflated_sharpe.MIN_TRIALS_FOR_DSR (5), so the DSR correction proper
computes.

HOLDING PERIODS — NO 21-DAY HOLD, and this family's own cost arithmetic
(not just the project-wide lesson that shorter holds have lost in every
family to date) is the reason. Assumed costs, each stated and justified in
its constant's docstring below: 5.0bp one-way per unit of gross notional
traded and 40bps/yr per unit of gross notional held (an 80bps/yr short-leg
borrow assumption, halved per the harness's documented gross-2.0
arithmetic). A fully formed long-short book carries gross 2.0, so financing
costs ~80bp/yr of equity regardless of hold length, while trading costs
scale with reformation count: at H=63 (~4 reformations/yr) a worst-case
full flip trades 4.0 gross per reformation for 4 x 4.0 x 5bp = 80bp/yr
(realistic overlap makes it less; the run reports the real charge), total
~1.2-1.6%/yr against a measured long-short book volatility in the 10-20%
range — a Sharpe drag of roughly 0.08-0.12. At H=21 the trading term
triples (~240bp/yr worst case) for a drag of 0.2+, spent re-answering a
question every prior family already answered the same way. 63 is therefore
the floor — CONFIRMING, with this basket's own numbers, the scout's
finding that H=63 survives costs here — and {63, 126} the declared axis.
252 is excluded on signal grounds rather than cost: the cited momentum
literature's profitability sits at 1-12 month ranks held 1-6 months, and a
12-month hold is outside it.

LEG WEIGHTING: measured annualized daily vols in this basket span 3x —
GLD 16.5% to UNG 50.4% — so an equally weighted leg of three containing
UNG is mostly a natural-gas bet. "inverse_vol" (1/trailing 63-day realized
vol via CrossSectionalData.leg_weight_basis, the same construction the FX
family added to the harness) is the standard risk-parity correction, and
testing BOTH it and plain "equal" is one of this family's two pre-declared
axes rather than an unexamined default.

Every spec is given the SAME lookback (1260, the family's longest) for the
reason cross_sectional_fx.py documents at length: all 24 specs then form
over the identical date range, so the sibling-Sharpe spread feeding the
DSR's sigma_sr measures differing signals, not differing samples. The cost
is real — formations start ~5 years into the 14.7-year panel, leaving a
~9.7-year replay — and accepted deliberately.

Legs are terciles: rank_fraction 1/3 over 11 ranked names yields
max(1, int(11/3)) = 3 per leg, disjoint (6 <= 11). min_names_per_leg is
set to 3 — below the harness's DEFAULT_MIN_NAMES_PER_LEG = 5 for the same
disclosed reason as FX: an 11-name universe cannot produce disjoint 5-name
legs at any tercile-like fraction, three names per leg is what the
commodity cross-sectional literature itself trades at this universe size,
and the honest cost (single-instrument events move a leg) is disclosed in
every run's summary rather than hidden behind a threshold calibrated for a
700-name equity decile.
"""

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_fx import scrub_reversing_bad_prints

logger = logging.getLogger(__name__)

# --- universe ---------------------------------------------------------------

# One instrument per distinct commodity — see the module docstring's
# UNIVERSE section for the two pre-declared exclusion rules (no duplicate
# wrappers or baskets; nothing over the redundancy correlation limit).
COMMODITIES_UNIVERSE: tuple[str, ...] = (
    "GLD",  # gold (physically backed)
    "SLV",  # silver (physically backed)
    "PPLT",  # platinum (physically backed)
    "PALL",  # palladium (physically backed)
    "CPER",  # copper (futures-based)
    "USO",  # WTI crude (futures-based)
    "UNG",  # natural gas (futures-based)
    "UGA",  # gasoline (futures-based)
    "CORN",  # corn (futures-based)
    "WEAT",  # wheat (futures-based)
    "SOYB",  # soybeans (futures-based)
)

# The pre-declared redundancy rule: a candidate whose daily-return
# correlation with an already-included instrument exceeds this over the
# common window is the same bet wearing a second ticker and is excluded.
COMMODITIES_REDUNDANCY_CORR_LIMIT = 0.90

# Candidates excluded by that rule, with the measured correlation and the
# name they duplicated — a typed record of the decision, verified live
# 2026-08-27, so the choice is auditable rather than folklore. BNO is the
# only casualty; the next-highest pair in the retained basket is GLD/SLV
# at 0.796, comfortably under the limit.
COMMODITIES_EXCLUDED_REDUNDANT: dict[str, tuple[str, float]] = {
    "BNO": ("USO", 0.942),
}

# Earliest date the price fetch asks for: before PPLT/PALL's 2010-01-08
# inception, so the real common-history start is discovered from the data
# (measured live 2026-08-27: 2011-11-15, CPER's inception binding) rather
# than assumed. Same "fetch everything, let the data define the window"
# idiom as FX_PRICE_HISTORY_START.
COMMODITIES_PRICE_HISTORY_START = date(2009, 1, 1)

# --- bad-print scrub calibration -------------------------------------------

# See the module docstring's DATA REPAIR section for the full calibration
# evidence. The CONSTRUCTION is cross_sectional_fx.scrub_reversing_bad_
# prints unchanged (a spike is fabricated iff it round-trips the next day);
# only these thresholds differ, because commodities genuinely whipsaw at
# magnitudes that would be provider artifacts in G10 FX. 0.25/0.20 flags
# exactly the two HG=F-cross-checked CPER prints on the real panel and
# provably spares USO 2020-03-09, SLV 2026-01-30, and UNG 2026-02-02.
COMMODITY_SPIKE_MIN_ABS_RETURN = 0.25
COMMODITY_SPIKE_REVERSAL_FRACTION = 0.20


def scrub_commodity_bad_prints(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The FX reversal-based scrub at commodity calibration — see the
    constants above and the module docstring's DATA REPAIR section."""
    return scrub_reversing_bad_prints(
        prices,
        min_abs_return=COMMODITY_SPIKE_MIN_ABS_RETURN,
        reversal_fraction=COMMODITY_SPIKE_REVERSAL_FRACTION,
    )


# --- price panel ------------------------------------------------------------


def build_commodities_price_panel(
    provider: YFinanceProvider, end: date, start: date = COMMODITIES_PRICE_HISTORY_START
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """The clean 11-ETF total-return panel: one column per ticker,
    restricted to days on which ALL are priced, with the two proven bad
    prints (and any future ones meeting the same calibrated test) scrubbed
    to NaN. Returns (panel, scrub flag frame, tickers with no price data).

    Close-only by design: no signal in this family reads open/volume, and
    get_daily_ohlcv's close frame is the dividend/split-adjusted
    total-return basis every realized return must come from (several of
    these funds never distribute, but the basis choice must not depend on
    that staying true).

    The dropna(how="any") defines the common window for the same reason
    build_fx_price_panel's does: a formation ranking 8 of 11 names is a
    materially different strategy than one ranking all 11, not a slightly
    thinner one."""
    tickers = list(COMMODITIES_UNIVERSE)
    frames, _missing_tickers = provider.get_daily_ohlcv(tickers, start, end)
    if not frames or "close" not in frames or frames["close"].empty:
        return pd.DataFrame(), pd.DataFrame(), tickers

    raw_close = frames["close"]
    missing = [t for t in tickers if t not in raw_close.columns]

    present = [t for t in tickers if t in raw_close.columns]
    panel = raw_close[present].apply(pd.to_numeric, errors="coerce")
    panel = panel.where(panel > 0.0).sort_index().dropna(how="any")
    if panel.empty:
        return pd.DataFrame(), pd.DataFrame(), missing

    scrubbed, flags = scrub_commodity_bad_prints(panel)
    n_scrubbed = int(flags.to_numpy().sum())
    if n_scrubbed:
        # WARNING, not INFO — same reasoning as the FX panel's scrub log: a
        # fabricated price in a vendor feed is a data-quality event, and a
        # run in which this count jumps must be visible even to a reader who
        # never opens the summary.
        logger.warning(
            "Commodities panel: scrubbed %d single-day bad print(s) (>=%.0f%% moves that "
            "round-tripped >=%.0f%% the next day) out of %d cells (%s).",
            n_scrubbed,
            COMMODITY_SPIKE_MIN_ABS_RETURN * 100,
            (1.0 - COMMODITY_SPIKE_REVERSAL_FRACTION) * 100,
            flags.size,
            {t: int(flags[t].sum()) for t in flags.columns if int(flags[t].sum())},
        )
    return scrubbed, flags, missing


# --- inverse-volatility weighting basis ------------------------------------

# Same trailing window and floor as the FX family's inverse-vol basis, kept
# identical for cross-family consistency rather than recalibrated: one
# quarter of trailing daily returns, refusing an estimate from fewer than a
# month of them.
COMMODITY_VOL_WINDOW_DAYS = 63
COMMODITY_VOL_MIN_PERIODS = 21


def build_inverse_vol_basis(prices: pd.DataFrame) -> pd.DataFrame:
    """1 / trailing realized volatility per ticker, aligned to `prices` —
    the leg_weight_basis the "inverse_vol" specs weight legs by. Point-in-
    time by construction (a rolling std at row i reads rows <= i only).

    WHY IT MATTERS MORE HERE THAN IN FX: G10 vols span ~2x; this basket
    spans 3x (GLD 16.5% to UNG 50.4% measured), so an equally weighted leg
    containing UNG is dominated by it. Non-finite or zero vol yields NaN,
    which _resolve_leg_weights treats as grounds to fall back to magnitude
    weighting for the whole leg — counted, not silent."""
    returns = prices.pct_change(fill_method=None)
    vol = returns.rolling(COMMODITY_VOL_WINDOW_DAYS, min_periods=COMMODITY_VOL_MIN_PERIODS).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        basis = 1.0 / vol
    return basis.replace([np.inf, -np.inf], np.nan)


# --- signals ----------------------------------------------------------------

# Same 0.8 register as every other coverage floor in this project — a
# signal window under 80% populated is refused (NaN) rather than computed
# on whatever little data exists. On this panel it is a light guard (the
# common-window dropna removes partial cross-sections); it exists to catch
# a ticker whose window is mostly scrubbed cells.
MIN_SIGNAL_OBS_FRACTION = 0.8


def signal_commodity_momentum(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Miffre-Rallis / Erb-Harvey cross-sectional commodity momentum:
    trailing lookback_days total return, P_t / P_{t-L} - 1, long past
    winners and short past losers (higher-is-long is the harness's
    convention and the literature's direction).

    Ranks on INVESTABLE total returns — the ETF's NAV return, roll yield
    and expenses included — which is the tradeable form of the futures
    excess-return momentum the papers document (see the module docstring's
    ETF-vs-splice section)."""
    window = history.close.iloc[-lookback_days:]
    first = window.iloc[0]
    last = window.iloc[-1]
    n_obs = window.notna().sum()
    signal = last / first - 1.0
    signal[n_obs < int(lookback_days * MIN_SIGNAL_OBS_FRACTION)] = np.nan
    signal[~np.isfinite(signal)] = np.nan
    return signal


def signal_commodity_long_run_reversal(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Asness/Moskowitz/Pedersen commodity VALUE, De Bondt-Thaler reversal
    generally: the NEGATED trailing lookback_days return, so multi-year
    losers score highest and land in the long leg. AMP define commodity
    value as (minus) the ~5-year return, which is why 1260 days is the
    primary definition and 756 the disclosed robustness variant. The sign
    flip lives on the signal because the harness has no direction flag and
    a negation is exactly equivalent — same as the FX and D2 reversals."""
    return -signal_commodity_momentum(history, lookback_days=lookback_days)


def _cross_sectional_rank(values: pd.Series) -> pd.Series:
    """Ranks to [0, 1] across finite values so two signals on different
    scales can be averaged; NaN stays NaN (a ticker with no valid signal is
    not a ticker with an average one). Identical construction to
    cross_sectional_fx._cross_sectional_rank, restated locally because each
    family module owns its signal code end-to-end (the project's
    per-family-module convention)."""
    finite = values[np.isfinite(values)]
    if len(finite) < 2:
        return pd.Series(np.nan, index=values.index, dtype=float)
    ranked = finite.rank(method="average") / float(len(finite))
    return ranked.reindex(values.index)


def signal_commodity_momentum_value_blend(
    history: CrossSectionalData, *, momentum_lookback_days: int, reversal_lookback_days: int
) -> pd.Series:
    """The family's ONE blend: the equally weighted average of the
    cross-sectional RANKS of momentum and of long-run reversal (value).
    Ranks because the components are on incommensurable scales (a 6-month
    return vs a negated 5-year return); one fixed definition rather than a
    weight/parameter sweep because AMP's finding is that the combination of
    the two is the natural test of their independence, and one honest
    combination answers that without multiplying n_trials. A ticker missing
    EITHER component gets NaN — no partial blending."""
    momentum = signal_commodity_momentum(history, lookback_days=momentum_lookback_days)
    value = signal_commodity_long_run_reversal(history, lookback_days=reversal_lookback_days)
    blended = (_cross_sectional_rank(momentum) + _cross_sectional_rank(value)) / 2.0
    return blended.where(np.isfinite(blended))


# --- the family -------------------------------------------------------------

COMMODITY_MOMENTUM_CITATION = (
    "Erb & Harvey, 'The Strategic and Tactical Value of Commodity Futures' "
    "(Financial Analysts Journal, 2006); Miffre & Rallis, 'Momentum strategies in commodity "
    "futures markets' (Journal of Banking & Finance, 2007)"
)
COMMODITY_REVERSAL_CITATION = (
    "Asness, Moskowitz & Pedersen, 'Value and Momentum Everywhere' (Journal of Finance, 2013); "
    "De Bondt & Thaler, 'Does the Stock Market Overreact?' (Journal of Finance, 1985)"
)
COMMODITY_BLEND_CITATION = (
    "Asness, Moskowitz & Pedersen, 'Value and Momentum Everywhere' (Journal of Finance, 2013), "
    "on combining value and momentum within commodities"
)

# The pre-declared axes. Their product IS the family size — see
# COMMODITIES_N_TRIALS, asserted against the built list.
COMMODITY_MOMENTUM_LOOKBACK_DAYS: tuple[int, ...] = (63, 126, 252)
COMMODITY_REVERSAL_LOOKBACK_DAYS: tuple[int, ...] = (756, 1260)
COMMODITY_HOLDING_DAYS: tuple[int, ...] = (63, 126)
COMMODITY_LEG_WEIGHTINGS: tuple[str, ...] = ("equal", "inverse_vol")

# The blend's fixed component parameters: the MIDDLE momentum window and
# the PRIMARY (AMP 5-year) value window.
COMMODITY_BLEND_MOMENTUM_LOOKBACK_DAYS = 126
COMMODITY_BLEND_REVERSAL_LOOKBACK_DAYS = 1260

# 3 momentum + 2 reversal + 1 blend.
COMMODITIES_N_SIGNAL_DEFINITIONS = (
    len(COMMODITY_MOMENTUM_LOOKBACK_DAYS) + len(COMMODITY_REVERSAL_LOOKBACK_DAYS) + 1
)

# The pre-declared family size and this family's honest, never-pooled DSR
# n_trials denominator: 6 signal definitions x 2 holds x 2 weightings = 24.
# Computed from the axes rather than typed as a literal so the two can
# never disagree; _build_commodities_family asserts the built list matches.
COMMODITIES_N_TRIALS = (
    COMMODITIES_N_SIGNAL_DEFINITIONS * len(COMMODITY_HOLDING_DAYS) * len(COMMODITY_LEG_WEIGHTINGS)
)

# Terciles: max(1, int(11 * 1/3)) = 3 per leg, 6 of 11 names used, disjoint.
# Asserted in _build_commodities_family so floating-point drift cannot
# silently change every leg's size.
COMMODITIES_RANK_FRACTION = 1.0 / 3.0

# Below the harness's DEFAULT_MIN_NAMES_PER_LEG (5) for the same disclosed
# reason as FX_MIN_NAMES_PER_LEG: an 11-name universe cannot produce
# disjoint 5-name legs, and 3 per leg is what the commodity cross-sectional
# literature trades at this universe size. The honest cost — these legs are
# concentrated, and the panel's effective breadth is ~6 bets, not 11 — is
# reported in every run's summary.
COMMODITIES_MIN_NAMES_PER_LEG = 3

# Every spec shares the family-max lookback so all 24 form over the
# identical date range and the DSR's sigma_sr measures signal differences,
# not sample differences — cross_sectional_fx.FX_LOOKBACK_DAYS' argument,
# adopted wholesale.
COMMODITIES_LOOKBACK_DAYS = max(COMMODITY_REVERSAL_LOOKBACK_DAYS)

# One-way trading cost per unit of gross notional traded, charged per
# formation. NOT the near-zero figure the mega-liquid names alone would
# justify: GLD/SLV/USO quote at ~1-3bp spreads, but PALL/CPER/WEAT/SOYB/UGA
# are thin ETFs whose quoted spreads reach tens of bps in normal markets.
# 5.0bp one-way blended across a book that always holds some of the thin
# names is an assumption sized between the two groups — numerically equal
# to the harness's equity default, but justified here on this basket's own
# spread structure rather than inherited. It is an assumption, not a
# measured execution cost, and the run reports each positive spec's
# BREAKEVEN cost so a reader can see how much any result leans on it.
COMMODITIES_COST_BPS = 5.0

# THE TIME-BASED COST: 40bps/yr per unit of gross notional held,
# representing an 80bps/yr SHORT-LEG borrow assumption via the harness
# field's own documented arithmetic (financing accrues on gross 2.0; half
# the book is short; 80bps on the 1.0 short leg = 40bps on gross 2.0). 80
# is deliberately above the bond family's 40: several of these funds are
# small (CPER, WEAT, SOYB, PALL) and commodity ETP borrow genuinely
# tightens — GLD/SLV/USO sit near general collateral (~25-50bps) while the
# small names can print hard-to-borrow rates of hundreds of bps in
# stressed periods. A blended 80bps/yr is an assumption, not a sourced
# borrow quote (a real borrow feed is a paid data source, already on the
# project's pending-paid list); short AVAILABILITY is not modeled at any
# price, per the harness's own disclosure.
COMMODITIES_SHORT_BORROW_BPS_PER_YEAR = 80.0
COMMODITIES_FINANCING_BPS_PER_YEAR = COMMODITIES_SHORT_BORROW_BPS_PER_YEAR / 2.0


def _build_commodities_family() -> list[CrossSectionalSpec]:
    """Assembles the full, fixed 24-definition Commodities family: 6 signal
    definitions x COMMODITY_HOLDING_DAYS x COMMODITY_LEG_WEIGHTINGS, every
    one long_short (a universe-hedged variant of an 11-name cross-section
    hedges a 3-name leg against its own average — a construction artifact,
    not a distinct hypothesis, per the FX family's identical reasoning)."""
    specs: list[CrossSectionalSpec] = []

    def add(pattern_id: str, family: str, citation: str, signal_fn) -> None:
        for holding in COMMODITY_HOLDING_DAYS:
            for weighting in COMMODITY_LEG_WEIGHTINGS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"{pattern_id}_h{holding}_{weighting}",
                        family=family,
                        citation=citation,
                        signal_fn=signal_fn,
                        lookback_days=COMMODITIES_LOOKBACK_DAYS,
                        holding_days=holding,
                        portfolio="long_short",
                        rank_fraction=COMMODITIES_RANK_FRACTION,
                        leg_weighting=weighting,  # type: ignore[arg-type]
                    )
                )

    for lookback in COMMODITY_MOMENTUM_LOOKBACK_DAYS:
        add(
            f"cmd_momentum_l{lookback}",
            "commodities_momentum",
            COMMODITY_MOMENTUM_CITATION,
            lambda h, lb=lookback: signal_commodity_momentum(h, lookback_days=lb),
        )

    for lookback in COMMODITY_REVERSAL_LOOKBACK_DAYS:
        add(
            f"cmd_reversal_l{lookback}",
            "commodities_long_run_reversal",
            COMMODITY_REVERSAL_CITATION,
            lambda h, lb=lookback: signal_commodity_long_run_reversal(h, lookback_days=lb),
        )

    add(
        f"cmd_blend_m{COMMODITY_BLEND_MOMENTUM_LOOKBACK_DAYS}_r{COMMODITY_BLEND_REVERSAL_LOOKBACK_DAYS}",
        "commodities_momentum_value_blend",
        COMMODITY_BLEND_CITATION,
        lambda h: signal_commodity_momentum_value_blend(
            h,
            momentum_lookback_days=COMMODITY_BLEND_MOMENTUM_LOOKBACK_DAYS,
            reversal_lookback_days=COMMODITY_BLEND_REVERSAL_LOOKBACK_DAYS,
        ),
    )

    assert len(specs) == COMMODITIES_N_TRIALS, (
        f"Commodities family has {len(specs)} definitions, not the pre-declared "
        f"{COMMODITIES_N_TRIALS} ({COMMODITIES_N_SIGNAL_DEFINITIONS} signal definitions x "
        f"{len(COMMODITY_HOLDING_DAYS)} holds x {len(COMMODITY_LEG_WEIGHTINGS)} weightings) — "
        "this family's whole point is being an exact, fixed enumeration declared before any "
        "run; a size drift here silently changes n_trials."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    # Close-only, structurally: no signal here reads open/volume/market cap/
    # the price-only basis, and none may quietly start to without this
    # family being re-declared.
    assert not any(
        s.requires_open or s.requires_volume or s.requires_market_cap or s.requires_price_only_close
        for s in specs
    ), "the commodities family is close-only by design"
    assert all(s.holding_days in COMMODITY_HOLDING_DAYS for s in specs)
    assert 21 not in COMMODITY_HOLDING_DAYS, (
        "a 21-day hold triples this family's turnover cost without touching its time-based "
        "financing cost — see the module docstring's HOLDING PERIODS arithmetic — and shorter "
        "holds have lost to their longer siblings in every family this project has screened."
    )
    assert all(s.leg_weighting in COMMODITY_LEG_WEIGHTINGS for s in specs)
    assert all(s.lookback_days == COMMODITIES_LOOKBACK_DAYS for s in specs)
    assert all(s.cohort_formation_days is None for s in specs)
    # Guards the floating-point leg-size arithmetic: at n = 11, terciles
    # must yield disjoint legs of exactly 3.
    n_leg = max(1, int(len(COMMODITIES_UNIVERSE) * COMMODITIES_RANK_FRACTION))
    assert n_leg == 3 and 2 * n_leg <= len(COMMODITIES_UNIVERSE), (
        f"COMMODITIES_RANK_FRACTION yields legs of {n_leg} from {len(COMMODITIES_UNIVERSE)} "
        "tickers — expected disjoint terciles of 3."
    )
    # The redundancy rule is part of the family's identity: the universe
    # must never silently re-admit an excluded near-duplicate.
    assert not (set(COMMODITIES_EXCLUDED_REDUNDANT) & set(COMMODITIES_UNIVERSE)), (
        "a ticker excluded by the redundancy rule is in the universe"
    )
    return specs


def build_commodities_family() -> list[CrossSectionalSpec]:
    """Public wrapper over _build_commodities_family — see that function.
    Built per call (not a module-level constant) purely for symmetry with
    the FX family's API; nothing in a spec depends on runtime data."""
    return _build_commodities_family()


def default_commodities_config() -> CrossSectionalConfig:
    """This family's own cost/leg configuration, as a function rather than
    a module-level singleton so callers cannot mutate a shared object (the
    harness writes formation_start onto whatever config it is given)."""
    return CrossSectionalConfig(
        cost_bps=COMMODITIES_COST_BPS,
        min_names_per_leg=COMMODITIES_MIN_NAMES_PER_LEG,
        financing_bps_per_year=COMMODITIES_FINANCING_BPS_PER_YEAR,
    )


# --- diagnostics ------------------------------------------------------------


def effective_breadth(daily_returns: pd.DataFrame) -> float:
    """The eigenvalue-based effective number of independent bets in a
    return panel: (sum lambda)^2 / sum(lambda^2) over the correlation
    matrix's spectrum — n for n uncorrelated series, 1 for n copies of one
    series. This is the number every run reports so '11 tickers' is never
    silently read as '11 independent things' (measured 5.85 on the real
    panel at design time). NaN when fewer than 2 columns have usable
    returns."""
    usable = daily_returns.dropna(how="any")
    if usable.shape[1] < 2 or len(usable) < 3:
        return float("nan")
    corr = usable.corr().to_numpy()
    if not np.all(np.isfinite(corr)):
        return float("nan")
    lam = np.linalg.eigvalsh(corr)
    denom = float((lam**2).sum())
    if denom <= 0.0:
        return float("nan")
    return float(lam.sum() ** 2 / denom)


def _signal_kind_of(pattern_id: str) -> str:
    """'cmd_momentum_l63_h63_equal' -> 'momentum'."""
    for kind in ("momentum", "reversal", "blend"):
        if pattern_id.startswith(f"cmd_{kind}"):
            return kind
    return "unknown"


@dataclass
class CommoditiesScreeningSummary:
    """run_commodities_screening's full result. Every caution this family
    carries is a TYPED FIELD, not a docstring paragraph a caller could
    skip: what was scrubbed and why, how much independent breadth the
    basket really has, which near-duplicates were excluded, where the
    panel starts/ends, and the cost/breakeven disclosure."""

    results: list[CrossSectionalScreeningResult]
    n_trials: int
    panel_start: date | None
    panel_end: date | None
    n_panel_rows: int
    missing_price_data: list[str]
    # The reversal-based scrub's work this run — expected to be exactly the
    # two proven CPER prints on the current feed; a jump in this count is a
    # data-quality event.
    n_bad_prints_scrubbed: int
    bad_prints_by_ticker: dict[str, int]
    # Honest breadth: the eigenvalue-based effective number of independent
    # bets in the panel's daily returns (measured 5.85 of 11 at design
    # time), plus the largest remaining pairwise correlation.
    effective_breadth: float
    max_pair_correlation: float
    max_pair: tuple[str, str] | None
    # The pre-declared redundancy exclusions (ticker -> (kept name, corr)).
    excluded_redundant: dict[str, tuple[str, float]]
    leg_size: int
    # Correlations between the three signal kinds' own blended return
    # streams (momentum/reversal/blend), measured from the real replay —
    # AMP predict momentum and value are negatively correlated; this
    # reports whether they actually were here.
    signal_kind_correlations: dict[tuple[str, str], float] = field(default_factory=dict)
    text: str = ""
    warnings: list[str] = field(default_factory=list)


def build_commodities_disclosure(
    results: list[CrossSectionalScreeningResult],
    config: CrossSectionalConfig,
    daily_by_pattern: dict[str, pd.Series] | None = None,
) -> str:
    """The cost/assumption disclosure, computed from the run's own numbers
    — same construction and arithmetic as cross_sectional_bonds.
    build_bonds_disclosure (gross = net + charged; breakeven cost_bps =
    cost_bps * gross / charged), restated here with this family's own
    assumptions. Financing is never folded into the breakeven: it scales
    with time held, not with turnover, so it does not move when cost_bps
    does."""
    lines = [
        "COMMODITIES FAMILY COST DISCLOSURE.",
        (
            f"  Trading: {config.cost_bps} bps one-way per unit of gross notional traded — an "
            "assumption blended across a basket whose quoted spreads span ~1bp (GLD) to tens of "
            "bps (CPER/WEAT/SOYB/PALL), not a measured execution cost."
        ),
        (
            f"  Financing: {config.financing_bps_per_year} bps/yr on gross notional held, "
            f"representing a {COMMODITIES_SHORT_BORROW_BPS_PER_YEAR} bps/yr SHORT-LEG borrow "
            "assumption (halved because financing accrues on gross 2.0 and half the book is "
            "short). An assumption, not a sourced borrow quote; short availability is not "
            "modeled at any price."
        ),
        (
            f"  min_names_per_leg={config.min_names_per_leg} (harness default is 5): tercile "
            "legs of 3 from an 11-name basket whose effective breadth is ~6 independent bets — "
            "single-instrument events move these legs."
        ),
    ]
    positive = [r for r in results if r.sharpe_annualized > 0]
    if not positive:
        lines.append(
            "  Breakeven cost: not applicable — no spec produced a positive Sharpe, so no "
            "positive result depends on the trading-cost assumption."
        )
        return "\n".join(lines)

    lines.append("  Breakeven one-way trading cost for each spec with a positive Sharpe:")
    for r in sorted(positive, key=lambda x: -x.sharpe_annualized):
        charged = r.total_cost_drag
        series = (daily_by_pattern or {}).get(r.pattern_id)
        if charged <= 0 or series is None or series.empty:
            lines.append(
                f"    {r.pattern_id}: Sharpe {r.sharpe_annualized:+.3f}; breakeven not "
                "computable (no turnover cost charged, or no return series available)."
            )
            continue
        net = float(series.sum())
        gross = net + charged
        breakeven_bps = config.cost_bps * gross / charged
        lines.append(
            f"    {r.pattern_id}: Sharpe {r.sharpe_annualized:+.3f}, cumulative net {net:+.2%} "
            f"after {charged:.2%} of trading cost -> breakeven at ~{breakeven_bps:.1f} bps "
            f"one-way ({breakeven_bps / config.cost_bps:.1f}x the assumption)."
        )
    return "\n".join(lines)


def _build_summary_text(summary: CommoditiesScreeningSummary) -> str:
    return (
        f"COMMODITIES CROSS-SECTIONAL FAMILY — READ BEFORE TRUSTING ANY NUMBER. Pre-declared "
        f"family size {summary.n_trials} definitions ({COMMODITIES_N_SIGNAL_DEFINITIONS} signal "
        f"definitions x {len(COMMODITY_HOLDING_DAYS)} holds x {len(COMMODITY_LEG_WEIGHTINGS)} leg "
        f"weightings), fixed before the run and used as the DSR's n_trials denominator in this "
        f"family's own, never-pooled screening call. Universe: {len(COMMODITIES_UNIVERSE)} "
        f"single-commodity ETFs gated by fixed_universe_membership (no point-in-time index "
        f"membership exists for commodities), one instrument per commodity, with "
        f"{list(summary.excluded_redundant)} excluded under the pre-declared "
        f"{COMMODITIES_REDUNDANCY_CORR_LIMIT} redundancy correlation limit (BNO/USO measured "
        f"0.942). HONEST BREADTH: the panel's effective number of independent bets is "
        f"{summary.effective_breadth:.2f} of {len(COMMODITIES_UNIVERSE)} nominal tickers"
        + (
            f" (largest remaining pair {summary.max_pair[0]}/{summary.max_pair[1]} at "
            f"{summary.max_pair_correlation:+.3f})"
            if summary.max_pair is not None
            else ""
        )
        + f"; tercile legs of {summary.leg_size} are genuinely concentrated and no Sharpe here "
        f"should be read as coming from a diversified decile portfolio. Panel: "
        f"{summary.n_panel_rows} rows {summary.panel_start} .. {summary.panel_end}, "
        f"total-return basis (roll yield, storage and expense ratios are inside the returns — "
        f"investable, and conservative relative to the literature's gross futures spreads). "
        f"DATA REPAIRS: {summary.n_bad_prints_scrubbed} single-day bad prints scrubbed to NaN "
        f"under the calibrated >=25%-spike/>=80%-reversal test (the two known ones are CPER "
        f"prints cross-checked against copper futures; real crises like USO 2020-03 and SLV "
        f"2026-01-30 provably survive the test). NO CARRY SIGNAL EXISTS in this family because "
        f"Yahoo's raw futures tickers are a naive front-month splice (measured: NG=F fabricates "
        f"+28.4%/yr vs the investable proxy) — term-structure signals are not backtestable from "
        f"free data and are NOT tested here; futures_curve_collector.py is collecting the data "
        f"a future carry round would need, and shares nothing with this family. Costs are split "
        f"by construction: {COMMODITIES_COST_BPS}bp one-way per unit of gross notional TRADED "
        f"plus {COMMODITIES_FINANCING_BPS_PER_YEAR}bps/yr per unit of gross notional HELD (an "
        f"{COMMODITIES_SHORT_BORROW_BPS_PER_YEAR}bps/yr short-leg borrow assumption), which is "
        f"why this family's holding floor is 63 trading days: at H=21 the turnover charge "
        f"triples while the financing charge stands, a Sharpe drag of ~0.2 spent re-answering a "
        f"question every prior family answered the same way."
    )


# --- production entry point -------------------------------------------------


def run_commodities_screening(
    end: date | None = None,
    start: date | None = None,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> CommoditiesScreeningSummary:
    """THE production entry point for the Commodities family, scoped to
    exactly the 24 pre-declared definitions and their own n_trials.

    `start` is the earliest FORMATION date (config.formation_start), not
    the earliest data date: price history is always fetched from
    COMMODITIES_PRICE_HISTORY_START so the 5-year lookback is warmed as
    fully as the data allows. Left None (recommended — the sample is only
    ~14.7 years and a later start only shrinks it), formations begin as
    soon as the shared lookback is satisfied.

    A caller-supplied config is used exactly as given and never silently
    patched, except formation_start, which is derived from `start` — the
    same contract screen_fx_family keeps."""
    end = end if end is not None else date.today()  # noqa: DTZ011 — fetch end bound only; see run_bonds_screening's note
    provider = provider if provider is not None else YFinanceProvider()
    if config is None:
        config = default_commodities_config()
    if start is not None:
        config.formation_start = start

    warnings: list[str] = []
    leg_size = max(1, int(len(COMMODITIES_UNIVERSE) * COMMODITIES_RANK_FRACTION))

    panel, flags, missing = build_commodities_price_panel(provider, end)
    if panel.empty:
        summary = CommoditiesScreeningSummary(
            results=[],
            n_trials=COMMODITIES_N_TRIALS,
            panel_start=None,
            panel_end=None,
            n_panel_rows=0,
            missing_price_data=missing,
            n_bad_prints_scrubbed=0,
            bad_prints_by_ticker={},
            effective_breadth=float("nan"),
            max_pair_correlation=float("nan"),
            max_pair=None,
            excluded_redundant=dict(COMMODITIES_EXCLUDED_REDUNDANT),
            leg_size=leg_size,
            warnings=["No commodity ETF price data resolved — nothing was screened."],
        )
        summary.text = _build_summary_text(summary)
        return summary

    if missing:
        warnings.append(
            f"{len(missing)} of {len(COMMODITIES_UNIVERSE)} universe tickers resolved no price "
            f"data ({missing}); the cross-section screened is smaller than the declared universe."
        )

    daily = panel.pct_change(fill_method=None)
    breadth = effective_breadth(daily)
    max_pair: tuple[str, str] | None = None
    max_corr = float("nan")
    usable = daily.dropna(how="any")
    if usable.shape[1] >= 2 and len(usable) >= 3:
        corr = usable.corr()
        upper = corr.where(np.triu(np.ones_like(corr, dtype=bool), 1))
        stacked = upper.stack()
        if not stacked.empty:
            idx = stacked.abs().idxmax()
            max_pair = (str(idx[0]), str(idx[1]))
            max_corr = float(stacked.loc[idx])

    basis = build_inverse_vol_basis(panel)
    data = CrossSectionalData(close=panel, leg_weight_basis=basis)
    membership_fn = fixed_universe_membership(COMMODITIES_UNIVERSE)

    specs = build_commodities_family()
    results = screen_cross_sectional_universe(data, specs, config, membership_fn)

    # A second, clearly-labelled replay pass purely for diagnostics — the
    # screening call returns aggregates, and the breakeven arithmetic and
    # the momentum-vs-value correlation need each spec's daily series.
    # Replaying 24 specs over 11 tickers is cheap; doing it here keeps the
    # shared harness's return type unchanged for every other family (the
    # exact trade-off run_bonds_screening documents).
    daily_by_pattern: dict[str, pd.Series] = {}
    spec_by_id = {s.pattern_id: s for s in specs}
    for r in results:
        replay = run_cross_sectional_backtest(data, spec_by_id[r.pattern_id], config, membership_fn)
        if replay.status == "ok":
            daily_by_pattern[r.pattern_id] = replay.daily_returns

    by_kind: dict[str, list[pd.Series]] = {}
    for pattern_id, series in daily_by_pattern.items():
        by_kind.setdefault(_signal_kind_of(pattern_id), []).append(series)
    blended = {
        kind: pd.concat(streams, axis=1).mean(axis=1) for kind, streams in sorted(by_kind.items())
    }
    kind_correlations: dict[tuple[str, str], float] = {}
    names = sorted(blended)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            joined = pd.concat([blended[a], blended[b]], axis=1).dropna()
            if len(joined) >= 2:
                kind_correlations[(a, b)] = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))

    per_ticker = {t: int(flags[t].sum()) for t in flags.columns} if not flags.empty else {}
    summary = CommoditiesScreeningSummary(
        results=results,
        n_trials=COMMODITIES_N_TRIALS,
        panel_start=panel.index[0].date(),
        panel_end=panel.index[-1].date(),
        n_panel_rows=len(panel),
        missing_price_data=missing,
        n_bad_prints_scrubbed=int(sum(per_ticker.values())),
        bad_prints_by_ticker={t: n for t, n in per_ticker.items() if n},
        effective_breadth=breadth,
        max_pair_correlation=max_corr,
        max_pair=max_pair,
        excluded_redundant=dict(COMMODITIES_EXCLUDED_REDUNDANT),
        leg_size=leg_size,
        signal_kind_correlations=kind_correlations,
        warnings=warnings,
    )
    summary.text = (
        _build_summary_text(summary)
        + "\n"
        + build_commodities_disclosure(results, config, daily_by_pattern)
    )
    return summary


__all__ = [
    "COMMODITIES_COST_BPS",
    "COMMODITIES_EXCLUDED_REDUNDANT",
    "COMMODITIES_FINANCING_BPS_PER_YEAR",
    "COMMODITIES_LOOKBACK_DAYS",
    "COMMODITIES_MIN_NAMES_PER_LEG",
    "COMMODITIES_N_TRIALS",
    "COMMODITIES_PRICE_HISTORY_START",
    "COMMODITIES_RANK_FRACTION",
    "COMMODITIES_REDUNDANCY_CORR_LIMIT",
    "COMMODITIES_SHORT_BORROW_BPS_PER_YEAR",
    "COMMODITIES_UNIVERSE",
    "COMMODITY_BLEND_MOMENTUM_LOOKBACK_DAYS",
    "COMMODITY_BLEND_REVERSAL_LOOKBACK_DAYS",
    "COMMODITY_HOLDING_DAYS",
    "COMMODITY_LEG_WEIGHTINGS",
    "COMMODITY_MOMENTUM_LOOKBACK_DAYS",
    "COMMODITY_REVERSAL_LOOKBACK_DAYS",
    "COMMODITY_SPIKE_MIN_ABS_RETURN",
    "COMMODITY_SPIKE_REVERSAL_FRACTION",
    "CommoditiesScreeningSummary",
    "build_commodities_disclosure",
    "build_commodities_family",
    "build_commodities_price_panel",
    "build_inverse_vol_basis",
    "default_commodities_config",
    "effective_breadth",
    "run_commodities_screening",
    "scrub_commodity_bad_prints",
    "signal_commodity_long_run_reversal",
    "signal_commodity_momentum",
    "signal_commodity_momentum_value_blend",
]
