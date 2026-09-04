"""Country equity index value and momentum, expressed against
cross_sectional.py's harness: cross-sectional momentum and long-horizon
reversal over 15 developed-market single-country equity ETFs (fourteen
iShares MSCI single-country funds plus SPY for the US).

THIS MODULE IS BUILT FROM A PRE-REGISTRATION WRITTEN BEFORE IT EXISTED:
backend/data/research_runs/country_index_value_momentum_PREREGISTRATION.txt
(committed 2026-09-04, before any panel was built or any Sharpe computed).
Every grid axis, cost arm, confound check and pass/fail threshold below is
that document's, transcribed rather than re-derived — the whole point of a
pre-registration is that seeing the data must not change the rules.

CITATION: Asness, C. S., Moskowitz, T. J. & Pedersen, L. H., "Value and
Momentum Everywhere", Journal of Financial Economics... actually Journal of
Finance 68(3), June 2013, 929-985. Table I Panel B (country indices,
01/1978-07/2011, 18 developed markets, equal-weighted terciles): momentum
P3-P1 Sharpe 0.73 (t 4.14), value P3-P1 Sharpe 0.61 (t 3.45), 50/50 blend
Sharpe 1.16, corr(value, momentum) = -0.34.

============================================================================
THE UNIVERSE — 15 fixed tickers, verified live, three of AMP's 18 excluded
============================================================================
    EWA Australia    EWO Austria      EWK Belgium      EWC Canada
    EWQ France       EWG Germany      EWH Hong Kong    EWI Italy
    EWJ Japan        EWN Netherlands  EWP Spain        EWD Sweden
    EWL Switzerland  EWU UK           SPY USA

Norway (ENOR) and Denmark (EDEN) are excluded because both only start
2012, sixteen years into this panel — including them would make the
sibling-Sharpe spread this family's DSR uses differ in SAMPLE rather than
SIGNAL. Portugal (PGAL) is excluded because Global X liquidated it
(announced 2024-01-19, last trade 2024-02-16, liquidation ~2024-02-23) and
it only started in 2013 anyway.

SURVIVORSHIP, MEASURED NOT WAVED AWAY. This family uses
cross_sectional.fixed_universe_membership, so it inherits that function's
own disclosed residual bias: today's liquid ETF list is chosen with
hindsight, and a fund that had already closed would never have been
written down. PGAL is that bias, observed, in this exact universe, in
2024. Independently re-verified 2026-09-04 (not merely copied from the
pre-registration) against the real yfinance history, which still resolves
PGAL's full 2013-11-12 -> 2024-03-05 life through this project's own
price-store-backed provider: total return -1.8% over that span, against
+25.2% for EWU, +33.3% for EWG and +75.2% for EWJ over the identical dates
(the pre-registration's own independently-computed figures were +24.4% /
+33.2% / +76.2% — the small deltas are consistent with the raw-price-store
rebuild that landed the same day the pre-registration was written, and the
finding itself — PGAL was a massive laggard exactly where a short leg would
have wanted it — reproduces without qualification). Portugal is precisely
the kind of name a long-short's SHORT leg would have wanted, so its absence
flatters this family, by an amount that cannot be estimated from free data
and is not guessed at here.

SPY is the one non-MSCI member (tracks the S&P 500, not an MSCI USA index);
disclosed, not smoothed over, per the pre-registration.

============================================================================
THE SIGNALS — one paper-faithful, one a declared, loudly-flagged deviation
============================================================================
mom_2_12 (signal_mom_2_12): AMP's own MOM2-12 — cumulative return from
t-12 months to t-1 month, skipping the most recent month, in trading-day
terms P[t-21]/P[t-252] - 1. PAPER-FAITHFUL.

ltr_5y (signal_ltr_5y): log(mean(P[t-5.5y : t-4.5y]) / P[t]) — the negative
of the ~5-year return, averaged over a one-year band centered near the
5-year mark to damp single-day noise. THIS IS NOT AMP's country-index value
measure (their own is the MSCI index's BE/ME, a paid dataset this project
cannot obtain); it IS the measure AMP themselves use for commodities and
currencies, justified there by Fama & French (1996)'s finding that the
negative 5-year return is highly correlated with BE/ME-sorted portfolios.
MECHANISM FIDELITY HAS ALREADY KILLED FOUR CANDIDATES IN THIS PROJECT
(si_dtc, asset_growth, residual_momentum, best_ideas_13f), always the same
shape: a spec that clears the bar is not the paper's construct. The value
leg here carries a correspondingly LOWER PRIOR than momentum, and the
pre-registration's own pass/fail rule (section 8.2(ii), reproduced below)
says a result carried by this leg does NOT qualify for registration
regardless of its DSR.

============================================================================
THE GRID — 12 sorted specs (2 signals x 3 holds x 2 constructions) + 3
combination series = 15 pre-declared trials, n_trials fixed at 15
============================================================================
ls_tercile: AMP's P3-P1. rank_fraction=1/3 (5 of 15 per leg, disjoint),
leg_weighting="equal" — the paper's own construction for nonstock asset
classes.

rank_weighted: AMP's own alternative factor construction, "weighting each
market in proportion to its signal rank". OPERATIONALIZED HERE, DISCLOSED
RATHER THAN HIDDEN, as: rank_fraction=0.5 (7 of 15 per leg, disjoint,
excluding only the single median-ranked market) with leg_weighting=
"magnitude" applied to a RANK-TRANSFORMED signal (see _rank_transform)
rather than the raw characteristic. cross_sectional.py's existing
"magnitude" scheme already weights a leg's members by their own distance
from that leg's weakest (boundary) member; feeding it a monotonic RANK
transform of the base signal (instead of the raw value) turns that
distance into a rank distance, which is exactly "proportional to signal
rank" restricted to the half of the universe on each side of the median.
This is a genuinely different, disclosed construction from ls_tercile
(more names participate, weighted by rank rather than by raw-signal
magnitude or a flat equal share) built entirely from the harness's EXISTING
leg-selection and leg-weighting machinery — no change to cross_sectional.py
was needed or made, so the ~30 other families sharing that module are
provably untouched by this family's existence. The two constructions still
select the SAME rank ordering (a rank transform is order-preserving), so
"which construction" changes only the WITHIN-LEG weights and the leg size,
never which direction a given market votes.

LEG WEIGHTING IS FIXED PER CONSTRUCTION, NOT SWEPT AS A THIRD AXIS —
ls_tercile is always equal-weighted, rank_weighted is always the rank-
magnitude scheme above. Sweeping leg_weighting as an independent axis would
have made this a 2 x 3 x 2 x 4 = 48-trial family; fixing it per
construction is what keeps n_trials at 15, exactly as the pre-registration
declares.

THREE COMBINATION SERIES (build_combo_daily_returns): the equal-weighted
average, on the common realized-date intersection, of the mom_2_12 and
ltr_5y ls_tercile daily net-return streams at each of the three holds —
AMP's own 50/50 with no free parameter. These are not fresh backtests (no
new price read, no new formation logic); they are a post-hoc combination of
two already-realized return series, counted as 3 of the family's 15
pre-declared trials per the pre-registration (a conservative-only choice:
DSR falls monotonically in n_trials, so counting them can only make a
positive harder to claim, never easier).

============================================================================
THE CONFOUND CHECKS — mandatory, in-module, for every one of the 15 trials
============================================================================
compute_confound_diagnostics runs, for every trial:
 (6.1) equal-weight-basket beta and the beta-HEDGED (not OLS-residual)
       residual Sharpe — y - beta*x, per the vol_regime_timing /
       correlation_risk_premium precedent this project already learned
       from (an OLS residual including its own intercept has mean exactly
       zero by construction and would report every spec as a disguised
       static tilt with total confidence).
 (6.2) dollar-factor beta, hedging BOTH the basket and the dollar jointly.
       DX-Y.NYB (ICE Dollar Index, an INDEX not a traded instrument, but
       covering the full 1996-2026 panel) is the headline; UUP (a REAL
       traded ETF, 2007-03-01 onward only) is a cross-check on the
       post-2007 subsample. Any disagreement between the two is reported,
       not resolved in the family's favour.
 (6.3) static-tilt control: a signal-free book holding the SAME AVERAGE
       long/short weights the spec holds on average (derived from realized
       formation membership frequency, since the harness does not persist
       per-formation weight vectors externally), with all ranking logic
       removed. If this captures most of the headline Sharpe, the result
       is a static country tilt, not a cross-sectional selection effect —
       the check that killed this project's commodities momentum family.
 (6.4) event concentration: the share of total realized gross return
       contributed by the two highest-contributing non-overlapping
       formation blocks, and the Sharpe with those two blocks' days
       dropped entirely.
 (6.5) the non-overlapping formation count itself, always reported.

A circular block bootstrap p-value (block length = the spec's own holding
period, reusing vol_regime_timing.block_bootstrap_sharpe_pvalue verbatim —
not re-derived) is also computed for every trial, because Sharpe is
measured on daily observations while the bets are monthly-to-semiannual.

============================================================================
COSTS
============================================================================
10bp one-way (CVM_BASE_COST_BPS) is THE result; 5bp and 20bp
(CVM_COST_ARMS_BPS) are mandatory sensitivity arms on the IDENTICAL 15
specs, not new trials. Short financing is assumed at 0bp per this
project's standing disclosed convention (financing_bps_per_year stays at
its 0.0 default) — milder here than for single stocks (large-cap
developed-market ETF borrow is real but small) but still an assumption.

============================================================================
PASS / FAIL — fixed in the pre-registration, applied unchanged here
============================================================================
8.1 VALIDATED EDGE: DSR >= 0.95 at n_trials=15 for the best trial.
8.2 FORWARD-VALIDATION REGISTRATION SCREEN, all four required:
    (i)   the single best-by-DSR trial among all 15 has DSR >= 0.50;
    (ii)  THAT trial's signal is mom_2_12 (not ltr_5y, not a combo — a
          result carried by the substitute value leg does not qualify,
          REGARDLESS of its own DSR, even if it happens to be the overall
          best of the 15);
    (iii) that trial's beta-hedged residual Sharpe (6.1 AND 6.2, jointly)
          retains >= 50% of its raw Sharpe, AND its static-tilt control
          (6.3) captures < 50% of the raw Sharpe;
    (iv)  preservation_score computed and reported for that trial, with
          its daily return series persisted.
The pass/fail application itself (and the report) live in the runner
script (data/research_runs/run_country_valmom.py), not here — mirroring
this project's residual_momentum precedent, where the family module
supplies mechanics and diagnostics and the runner applies the pre-declared
rule to the numbers it produces.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    DEFAULT_MIN_NAMES_PER_LEG,
    MIN_REPLAY_TRADING_DAYS,
    CrossSectionalBacktestResult,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    FormationRecord,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.research_lab.vol_regime_timing import block_bootstrap_sharpe_pvalue
from app.services.risk.beta import compute_beta

logger = logging.getLogger(__name__)

# --- universe ---------------------------------------------------------------

# Fourteen iShares MSCI single-country funds plus SPY for the US. Verified
# live 2026-09-04: all fifteen resolve through the point-in-time price
# store with zero missing tickers, 1996-01-02 .. 2026-09-01 (7,717 rows).
COUNTRY_ETF_TICKERS: list[str] = [
    "EWA", "EWO", "EWK", "EWC", "EWQ", "EWG", "EWH", "EWI", "EWJ",
    "EWN", "EWP", "EWD", "EWL", "EWU", "SPY",
]

COUNTRY_ETF_MARKET_NAMES: dict[str, str] = {
    "EWA": "Australia", "EWO": "Austria", "EWK": "Belgium", "EWC": "Canada",
    "EWQ": "France", "EWG": "Germany", "EWH": "Hong Kong", "EWI": "Italy",
    "EWJ": "Japan", "EWN": "Netherlands", "EWP": "Spain", "EWD": "Sweden",
    "EWL": "Switzerland", "EWU": "United Kingdom", "SPY": "United States",
}

# Excluded from the fixed universe entirely (see module docstring) —
# NEVER fetched, never present in the panel, and this is the pre-
# registration's own prescribed handling of the survivorship case: exclude
# and disclose, not include-and-correct (there is no free delisting-return
# data to correct with).
EXCLUDED_TICKERS_AND_WHY: dict[str, str] = {
    "ENOR": "Norway — starts 2012-01-24, 16 years into the panel",
    "EDEN": "Denmark — starts 2012-01-26, 16 years into the panel",
    "PGAL": "Portugal — Global X liquidated it 2024-02-23; also only starts 2013-11-12",
}

# Fetched from here so the 5.5-year value lookback is warmed before the
# earliest date any formation could plausibly occur, regardless of what a
# caller's `start` asks for — same idiom as cross_sectional_fx.py's
# FX_PRICE_HISTORY_START.
COUNTRY_PRICE_HISTORY_START = date(1995, 1, 1)

# The dollar-factor proxies for confound check 6.2. Both verified live
# 2026-09-04: DX-Y.NYB (ICE Dollar Index) 1995-01-02 .. 2026-09-01 (8,038
# rows, an INDEX not a traded instrument — diagnostic, not executable);
# UUP (a real traded ETF) 2007-03-01 .. 2026-09-01 (4,908 rows).
DOLLAR_INDEX_TICKER = "DX-Y.NYB"
DOLLAR_ETF_TICKER = "UUP"


def fetch_country_price_panel(
    provider: YFinanceProvider, end: date, start: date = COUNTRY_PRICE_HISTORY_START
) -> tuple[pd.DataFrame, list[str]]:
    """The 15-column dividend-and-split-adjusted (total-return) Close panel,
    served from the point-in-time price store via get_daily_ohlcv — NOT a
    fresh auto_adjust=True yfinance call, so a fixed historical window
    reproduces identically however long after the first run it is
    re-requested (see price_store.py; this is the project-wide fix landed
    2026-09-04, commits 77e77d7..61bd307, applied here from the start
    rather than retrofitted later).

    Returns (close panel, tickers that resolved no price data at all —
    empty in a healthy run since every one of the 15 was live-verified)."""
    frames, _missing_by_ticker = provider.get_daily_ohlcv(COUNTRY_ETF_TICKERS, start, end)
    if not frames or "close" not in frames or frames["close"].empty:
        return pd.DataFrame(), list(COUNTRY_ETF_TICKERS)
    close = frames["close"]
    missing = [t for t in COUNTRY_ETF_TICKERS if t not in close.columns]
    return close[[t for t in COUNTRY_ETF_TICKERS if t in close.columns]], missing


def fetch_dollar_factor_panel(
    provider: YFinanceProvider, end: date, start: date = COUNTRY_PRICE_HISTORY_START
) -> tuple[pd.Series, pd.Series]:
    """Returns (DX-Y.NYB close, UUP close), each a plain Series indexed by
    date, for confound check 6.2. Neither is reindexed to the country
    panel here — compute_dollar_confound aligns on read, per-spec, via an
    inner join, so a currency proxy's own missing days simply drop out of
    that specific regression rather than propagating NaN into the price
    panel used by every signal."""
    dxy_frames, dxy_missing = provider.get_daily_ohlcv([DOLLAR_INDEX_TICKER], start, end)
    uup_frames, uup_missing = provider.get_daily_ohlcv([DOLLAR_ETF_TICKER], start, end)
    dxy = (
        dxy_frames["close"][DOLLAR_INDEX_TICKER].dropna()
        if dxy_frames and DOLLAR_INDEX_TICKER not in dxy_missing
        else pd.Series(dtype=float)
    )
    uup = (
        uup_frames["close"][DOLLAR_ETF_TICKER].dropna()
        if uup_frames and DOLLAR_ETF_TICKER not in uup_missing
        else pd.Series(dtype=float)
    )
    return dxy, uup


# --- signals ------------------------------------------------------------

# AMP's own MOM2-12 in trading-day terms: ~12 months = 252 trading days,
# ~1 month = 21 trading days, and the most recent month is SKIPPED (the
# window ends 21 trading days before the formation date, not at it).
MOM_LOOKBACK_TRADING_DAYS = 252
MOM_SKIP_TRADING_DAYS = 21
MOM_REQUIRED_HISTORY_DAYS = MOM_LOOKBACK_TRADING_DAYS + 1

# The value substitute's averaging band: 4.5 to 5.5 years, in trading days
# (252/year). Averaging a one-year band around the 5-year mark — rather
# than reading a single day 5 years back — damps the idiosyncratic noise
# of any one day's print, per the pre-registration's own specification.
LTR_WINDOW_FAR_TRADING_DAYS = round(5.5 * TRADING_DAYS_PER_YEAR)  # 1386
LTR_WINDOW_NEAR_TRADING_DAYS = round(4.5 * TRADING_DAYS_PER_YEAR)  # 1134
LTR_REQUIRED_HISTORY_DAYS = LTR_WINDOW_FAR_TRADING_DAYS + 1

# A signal window with fewer than this fraction of its rows populated is
# refused (NaN signal) — same 0.8 register as every other coverage floor
# in this project's cross-sectional families.
MIN_SIGNAL_OBS_FRACTION = 0.8

# Every spec is given the SAME lookback (the family's longest, the value
# leg's 5.5-year window) so all 12 specs form over the IDENTICAL date
# range — the FX/commodities precedent for why sibling Sharpes must be
# measured on one sample rather than differing samples that would partly
# explain the sigma_sr spread the DSR correction relies on.
COUNTRY_LOOKBACK_DAYS = max(MOM_REQUIRED_HISTORY_DAYS, LTR_REQUIRED_HISTORY_DAYS)


def signal_mom_2_12(history: CrossSectionalData) -> pd.Series:
    """AMP's MOM2-12: P[t-1mo] / P[t-12mo] - 1, in trading-day terms
    P[t-21]/P[t-252] - 1. PAPER-FAITHFUL — see module docstring 4.1."""
    close = history.close
    n = len(close)
    columns = list(close.columns)
    if n < MOM_REQUIRED_HISTORY_DAYS:
        return pd.Series(np.nan, index=columns, dtype=float)
    far = close.iloc[n - 1 - MOM_LOOKBACK_TRADING_DAYS]
    near = close.iloc[n - 1 - MOM_SKIP_TRADING_DAYS]
    signal = near / far - 1.0
    return signal.where(np.isfinite(signal))


def signal_ltr_5y(history: CrossSectionalData) -> pd.Series:
    """The declared value substitute: log(mean(P[t-5.5y : t-4.5y]) / P[t]).
    A big multi-year LOSER (low average price relative to today... wait —
    a loser has a HIGH average price 5 years ago relative to today's low
    price, so the ratio > 1 and the log is POSITIVE) scores highest and
    lands in the long leg — De Bondt/Thaler-style long-horizon reversal,
    and AMP's own commodity/currency value proxy. NOT AMP's country-index
    BE/ME measure — see module docstring 4.2 for why, and why this is
    flagged as loudly as it is."""
    close = history.close
    n = len(close)
    columns = list(close.columns)
    if n < LTR_REQUIRED_HISTORY_DAYS:
        return pd.Series(np.nan, index=columns, dtype=float)
    window_start = n - 1 - LTR_WINDOW_FAR_TRADING_DAYS
    window_end = n - LTR_WINDOW_NEAR_TRADING_DAYS  # exclusive upper bound for iloc slicing
    window = close.iloc[window_start:window_end]
    min_obs = int(round((window_end - window_start) * MIN_SIGNAL_OBS_FRACTION))
    coverage = window.notna().sum()
    avg_price = window.mean(axis=0)
    current = close.iloc[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = avg_price / current
        signal = np.log(ratio)
    signal[coverage < min_obs] = np.nan
    signal[~np.isfinite(signal)] = np.nan
    signal[current <= 0] = np.nan
    return signal


def _rank_transform(base_signal_fn):
    """Wraps a base SignalFn into a rank-preserving version for the
    rank_weighted construction (see module docstring). pandas' own
    .rank() assigns NaN a NaN rank (never a middling value — a market
    with no valid signal must not be imputed an average one) and averages
    ties, both matching this harness's existing signal-NaN contract. The
    transform is strictly order-preserving, so select_leg_tickers picks
    the IDENTICAL top/bottom members it would have picked from the raw
    signal; only the within-leg WEIGHTING changes (see _leg_weights'
    excess-from-boundary computation, now operating on rank units)."""

    def _wrapped(history: CrossSectionalData) -> pd.Series:
        raw = base_signal_fn(history)
        return raw.rank(method="average", na_option="keep")

    return _wrapped


# --- the family -----------------------------------------------------------

CVM_MOMENTUM_CITATION = (
    "Asness, Moskowitz & Pedersen, 'Value and Momentum Everywhere' (Journal of Finance, 2013), "
    "Table I Panel B, country-index MOM2-12 (Sharpe 0.73, t 4.14) — PAPER-FAITHFUL signal"
)
CVM_VALUE_CITATION = (
    "Asness, Moskowitz & Pedersen (2013) value-as-negative-5-year-return, the measure they use "
    "for commodities/currencies (citing Fama & French 1996), substituted here for their actual "
    "country-index BE/ME measure (a paid dataset this project cannot obtain) — DECLARED DEVIATION, "
    "see module docstring 4.2"
)
CVM_COMBO_CITATION = (
    "Asness, Moskowitz & Pedersen (2013)'s own 50/50 momentum+value combination, no free parameter"
)

CVM_SIGNAL_FNS: dict[str, object] = {
    "mom_2_12": signal_mom_2_12,
    "ltr_5y": signal_ltr_5y,
}
CVM_SIGNAL_CITATIONS: dict[str, str] = {
    "mom_2_12": CVM_MOMENTUM_CITATION,
    "ltr_5y": CVM_VALUE_CITATION,
}

CVM_HOLDING_DAYS: tuple[int, ...] = (21, 63, 126)
CVM_CONSTRUCTIONS: tuple[str, ...] = ("ls_tercile", "rank_weighted")

# Terciles: max(1, int(15/3)) = 5 per leg, disjoint (10 <= 15) — clears
# cross_sectional.DEFAULT_MIN_NAMES_PER_LEG (5) without a waiver.
CVM_TERCILE_RANK_FRACTION = 1.0 / 3.0
# rank_weighted: half the universe per leg, excluding only the single
# median-ranked market — max(1, int(15*0.5)) = 7 per leg, disjoint
# (14 <= 15). See module docstring for why this operationalizes AMP's
# "weight proportional to signal rank" construction.
CVM_RANK_WEIGHTED_RANK_FRACTION = 0.5

CVM_N_BASE_SPECS = len(CVM_SIGNAL_FNS) * len(CVM_HOLDING_DAYS) * len(CVM_CONSTRUCTIONS)  # 12
CVM_N_COMBOS = len(CVM_HOLDING_DAYS)  # 3
CVM_N_TRIALS = CVM_N_BASE_SPECS + CVM_N_COMBOS  # 15, this family's own, never-pooled denominator

CVM_BASE_COST_BPS = 10.0
CVM_COST_ARMS_BPS: tuple[float, ...] = (5.0, 10.0, 20.0)


def build_country_valmom_family() -> list[CrossSectionalSpec]:
    """The fixed 12-spec grid: 2 signals x 3 holds x 2 constructions.
    Combination series are NOT CrossSectionalSpecs (they are a post-hoc
    blend of two already-realized return streams, see module docstring)
    and are built separately by build_combo_daily_returns."""
    specs: list[CrossSectionalSpec] = []
    for signal_name, base_fn in CVM_SIGNAL_FNS.items():
        citation = CVM_SIGNAL_CITATIONS[signal_name]
        for holding in CVM_HOLDING_DAYS:
            for construction in CVM_CONSTRUCTIONS:
                if construction == "ls_tercile":
                    signal_fn = base_fn
                    rank_fraction = CVM_TERCILE_RANK_FRACTION
                    leg_weighting = "equal"
                else:
                    signal_fn = _rank_transform(base_fn)
                    rank_fraction = CVM_RANK_WEIGHTED_RANK_FRACTION
                    leg_weighting = "magnitude"
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"cvm_{signal_name}_{construction}_h{holding}",
                        family=f"country_valmom_{signal_name}",
                        citation=citation,
                        signal_fn=signal_fn,
                        lookback_days=COUNTRY_LOOKBACK_DAYS,
                        holding_days=holding,
                        portfolio="long_short",
                        rank_fraction=rank_fraction,
                        leg_weighting=leg_weighting,  # type: ignore[arg-type]
                    )
                )
    assert len(specs) == CVM_N_BASE_SPECS, (
        f"country_valmom family has {len(specs)} base specs, not the pre-declared "
        f"{CVM_N_BASE_SPECS} (2 signals x {len(CVM_HOLDING_DAYS)} holds x "
        f"{len(CVM_CONSTRUCTIONS)} constructions) — a size drift here silently changes "
        "n_trials, which this family's whole point is being fixed before any run."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    n_tercile_leg = max(1, int(len(COUNTRY_ETF_TICKERS) * CVM_TERCILE_RANK_FRACTION))
    assert n_tercile_leg == 5 and 2 * n_tercile_leg <= len(COUNTRY_ETF_TICKERS), (
        f"CVM_TERCILE_RANK_FRACTION yields legs of {n_tercile_leg} from "
        f"{len(COUNTRY_ETF_TICKERS)} markets — expected disjoint terciles of 5."
    )
    n_rw_leg = max(1, int(len(COUNTRY_ETF_TICKERS) * CVM_RANK_WEIGHTED_RANK_FRACTION))
    assert n_rw_leg == 7 and 2 * n_rw_leg <= len(COUNTRY_ETF_TICKERS), (
        f"CVM_RANK_WEIGHTED_RANK_FRACTION yields legs of {n_rw_leg} from "
        f"{len(COUNTRY_ETF_TICKERS)} markets — expected disjoint half-splits of 7."
    )
    return specs


def default_country_valmom_config(cost_bps: float = CVM_BASE_COST_BPS) -> CrossSectionalConfig:
    """financing_bps_per_year stays at its 0.0 default: short financing is
    assumed at 0bp per this project's standing disclosed convention (see
    module docstring's COSTS section) — a breakeven annual borrow rate is
    reported separately rather than assuming a nonzero one here."""
    return CrossSectionalConfig(cost_bps=cost_bps, min_names_per_leg=DEFAULT_MIN_NAMES_PER_LEG)


# --- combination series -----------------------------------------------------


def build_combo_daily_returns(
    mom_result: CrossSectionalBacktestResult, ltr_result: CrossSectionalBacktestResult
) -> pd.Series:
    """AMP's own 50/50 momentum+value combination: the equal-weighted
    average of the two ls_tercile daily NET return streams, on their
    common realized-date INTERSECTION (inner join + dropna) — a genuine
    common-sample combination, not a union padded with zeros, since a day
    only one leg realized a return for is not a day the 50/50 book was
    actually half-and-half."""
    aligned = pd.concat(
        [mom_result.daily_returns.rename("mom"), ltr_result.daily_returns.rename("ltr")],
        axis=1,
        join="inner",
    ).dropna()
    return 0.5 * (aligned["mom"] + aligned["ltr"])


def _n_active_formations(result: CrossSectionalBacktestResult) -> int:
    return sum(1 for f in result.formations if f.skipped_reason is None)


# --- confound diagnostics (section 6) --------------------------------------

# Same guard this project already learned to apply (correlation_risk_
# premium.py / vol_regime_timing.py / eigenportfolio.py): a beta-hedged
# stream that is mathematically zero but numerically dust would otherwise
# report a large, meaningless Sharpe (positive OR negative) instead of the
# honest "nothing is left".
RESIDUAL_DEGENERACY_RATIO = 1e-8

# Below this many active formations, the two-block event-concentration
# check and the static-tilt control are not reported (not enough blocks
# for "the best two" to mean anything) — mirrors MIN_REPLAY_TRADING_DAYS'
# own "too thin to mean anything" register.
MIN_FORMATIONS_FOR_EVENT_CHECK = 4


def equal_weight_basket_returns(close: pd.DataFrame) -> pd.Series:
    """Check 6.1's benchmark: the equal-weight daily return of all 15
    ETFs, each day — NOT reformed or ranked, just the flat average of
    whatever's priced that day. A ticker's occasional NaN (should not
    occur on this panel post-inception, but guarded anyway) drops out of
    that day's mean rather than being treated as a zero return."""
    returns = close.pct_change(fill_method=None)
    return returns.mean(axis=1, skipna=True)


def _hedge_and_residual_sharpe(
    y: pd.Series, factors: dict[str, pd.Series]
) -> tuple[dict[str, float], float, int]:
    """OLS-hedges `y` against one or more `factors` jointly (intercept
    included in the fit, EXCLUDED from the hedge — see module docstring's
    6.1 for why: hedged = y - sum(beta_i * x_i), not the zero-mean OLS
    residual y - alpha - sum(beta_i * x_i)). Returns (betas by factor
    name, residual Sharpe, n observations used).

    A single factor reuses app.services.risk.beta.compute_beta exactly
    (no re-derivation); two or more factors are fit by ordinary least
    squares via numpy so the SAME "hedge without the intercept" contract
    holds however many factors are supplied."""
    frame = pd.concat(
        [y.rename("y")] + [f.rename(name) for name, f in factors.items()], axis=1, sort=False
    ).dropna()
    n = len(frame)
    if n < 3:
        return {name: 0.0 for name in factors}, 0.0, n

    if len(factors) == 1:
        (name,) = factors.keys()
        beta = compute_beta(frame["y"], frame[name])
        if not np.isfinite(beta):
            beta = 0.0
        betas = {name: float(beta)}
    else:
        design = np.column_stack([np.ones(n)] + [frame[name].to_numpy() for name in factors])
        try:
            coeffs, *_ = np.linalg.lstsq(design, frame["y"].to_numpy(), rcond=None)
            betas = {name: float(coeffs[i + 1]) for i, name in enumerate(factors)}
        except np.linalg.LinAlgError:
            betas = {name: 0.0 for name in factors}

    hedged = frame["y"].copy()
    for name, beta in betas.items():
        hedged = hedged - beta * frame[name]

    y_std = float(frame["y"].std(ddof=1))
    hedged_std = float(hedged.std(ddof=1))
    fully_explained = y_std > 0 and hedged_std <= RESIDUAL_DEGENERACY_RATIO * y_std
    residual_sharpe = 0.0 if fully_explained else sharpe_ratio(hedged)
    return betas, residual_sharpe, n


def _formation_blocks(
    formations: list[FormationRecord], daily_index: pd.DatetimeIndex
) -> list[tuple[pd.Timestamp, pd.Series]]:
    """Partitions `daily_index` into ONE contiguous, non-overlapping block
    per formation (active or skipped — a skipped formation's block is all
    exact-zero return days, contributing nothing, which is correct). Every
    realized date belongs to exactly one block; this is only valid for a
    single-sleeve (non-overlapping) replay, which is what this family
    always runs (cohort_formation_days is never set on any spec here)."""
    if not formations:
        return []
    ordered = sorted(formations, key=lambda f: f.date)
    bounds = [f.date for f in ordered] + [daily_index.max() + pd.Timedelta(days=1)]
    blocks = []
    for k, f in enumerate(ordered):
        mask = (daily_index > bounds[k]) & (daily_index <= bounds[k + 1])
        blocks.append((f.date, daily_index[mask]))
    return blocks


@dataclass(frozen=True)
class CvmConfoundDiagnostic:
    """Every one of section 6's checks, for ONE trial. Computed for all 15
    trials, always — never deferred to a follow-up study."""

    pattern_id: str
    raw_sharpe: float
    n_formations: int
    n_trading_days: int
    # 6.1
    basket_beta: float
    basket_hedged_sharpe: float
    basket_retention: float | None
    # 6.2 — DX-Y.NYB headline (full sample), hedging basket AND dollar jointly
    dxy_n_observations: int
    dxy_beta: float
    both_hedged_sharpe_dxy: float
    both_retention_dxy: float | None
    # 6.2 — UUP cross-check (2007-03-01 onward only)
    uup_n_observations: int
    uup_subsample_raw_sharpe: float | None
    uup_beta: float | None
    both_hedged_sharpe_uup: float | None
    both_retention_uup: float | None
    # 6.3
    static_tilt_sharpe: float | None
    static_tilt_capture: float | None
    # 6.4
    top2_block_share_of_gross: float | None
    sharpe_ex_top2_blocks: float | None
    # 6.5
    n_nonoverlapping_formations: int
    # bootstrap, section 9
    bootstrap_p_value: float | None


def compute_confound_diagnostics(
    pattern_id: str,
    replay: CrossSectionalBacktestResult,
    holding_days: int,
    close: pd.DataFrame,
    basket_returns: pd.Series,
    dxy_prices: pd.Series,
    uup_prices: pd.Series,
) -> CvmConfoundDiagnostic:
    daily = replay.daily_returns
    raw_sharpe = sharpe_ratio(daily)
    n_active = _n_active_formations(replay)

    # 6.1
    basket_betas, basket_hedged_sharpe, _ = _hedge_and_residual_sharpe(daily, {"basket": basket_returns})
    basket_beta = basket_betas["basket"]
    basket_retention = (basket_hedged_sharpe / raw_sharpe) if raw_sharpe != 0 else None

    # 6.2 — DX-Y.NYB headline, full sample, hedge basket AND dollar jointly
    dxy_change = dxy_prices.pct_change(fill_method=None)
    both_betas_dxy, both_hedged_sharpe_dxy, n_dxy = _hedge_and_residual_sharpe(
        daily, {"basket": basket_returns, "dollar": dxy_change}
    )
    both_retention_dxy = (both_hedged_sharpe_dxy / raw_sharpe) if raw_sharpe != 0 else None

    # 6.2 — UUP cross-check, 2007-03-01 onward only
    uup_change = uup_prices.pct_change(fill_method=None)
    if len(uup_change.dropna()) > 0:
        uup_start = uup_change.dropna().index.min()
        daily_uup_window = daily.loc[daily.index >= uup_start]
        uup_subsample_raw_sharpe = (
            sharpe_ratio(daily_uup_window) if len(daily_uup_window) >= MIN_REPLAY_TRADING_DAYS else None
        )
        both_betas_uup, both_hedged_sharpe_uup, n_uup = _hedge_and_residual_sharpe(
            daily_uup_window, {"basket": basket_returns, "dollar": uup_change}
        )
        uup_beta = both_betas_uup["dollar"] if n_uup >= 3 else None
        both_retention_uup = (
            (both_hedged_sharpe_uup / uup_subsample_raw_sharpe)
            if uup_subsample_raw_sharpe not in (None, 0.0)
            else None
        )
    else:
        n_uup = 0
        uup_subsample_raw_sharpe = None
        uup_beta = None
        both_hedged_sharpe_uup = None
        both_retention_uup = None

    # 6.3 — static tilt: average realized long/short membership frequency,
    # equal-share-within-leg-at-that-formation, applied as a FIXED,
    # never-reformed weight vector to the raw ticker return panel over the
    # spec's own realized date range.
    active = [f for f in replay.formations if f.skipped_reason is None]
    static_tilt_sharpe: float | None = None
    static_tilt_capture: float | None = None
    if len(active) >= MIN_FORMATIONS_FOR_EVENT_CHECK:
        weight_sum: dict[str, float] = {t: 0.0 for t in close.columns}
        for f in active:
            leg_size = len(f.long_tickers) or 1
            for t in f.long_tickers:
                weight_sum[t] = weight_sum.get(t, 0.0) + 1.0 / leg_size
            short_leg_size = len(f.short_tickers) or 1
            for t in f.short_tickers:
                weight_sum[t] = weight_sum.get(t, 0.0) - 1.0 / short_leg_size
        static_weights = {t: w / len(active) for t, w in weight_sum.items()}
        ticker_returns = close.pct_change(fill_method=None)
        static_series = ticker_returns.loc[daily.index]
        weight_row = pd.Series(static_weights).reindex(static_series.columns).fillna(0.0)
        valid = static_series.notna()
        weighted = static_series.mul(weight_row, axis=1)
        denom = valid.mul(weight_row.abs(), axis=1).sum(axis=1).replace(0.0, np.nan)
        static_returns = weighted.sum(axis=1) / denom.where(denom.notna(), 1.0)
        static_returns = static_returns.fillna(0.0)
        static_tilt_sharpe = sharpe_ratio(static_returns)
        static_tilt_capture = (static_tilt_sharpe / raw_sharpe) if raw_sharpe != 0 else None

    # 6.4 — event concentration
    top2_share: float | None = None
    sharpe_ex_top2: float | None = None
    if len(active) >= MIN_FORMATIONS_FOR_EVENT_CHECK:
        blocks = _formation_blocks(replay.formations, daily.index)
        contributions = [(dts, float(daily.loc[dts].sum())) for _f_date, dts in blocks if len(dts) > 0]
        total_gross = sum(value for _dts, value in contributions)
        ranked_blocks = sorted(contributions, key=lambda pair: pair[1], reverse=True)
        top2 = ranked_blocks[:2]
        top2_sum = sum(value for _dts, value in top2)
        top2_share = (top2_sum / total_gross) if total_gross != 0 else None
        top2_dates = pd.DatetimeIndex([])
        for dts, _value in top2:
            top2_dates = top2_dates.union(dts)
        remainder = daily.drop(index=top2_dates, errors="ignore")
        sharpe_ex_top2 = sharpe_ratio(remainder) if len(remainder) >= MIN_REPLAY_TRADING_DAYS else None

    bootstrap_p = block_bootstrap_sharpe_pvalue(daily, holding_days)

    return CvmConfoundDiagnostic(
        pattern_id=pattern_id,
        raw_sharpe=raw_sharpe,
        n_formations=n_active,
        n_trading_days=len(daily),
        basket_beta=float(basket_beta),
        basket_hedged_sharpe=float(basket_hedged_sharpe),
        basket_retention=basket_retention,
        dxy_n_observations=n_dxy,
        dxy_beta=float(both_betas_dxy["dollar"]),
        both_hedged_sharpe_dxy=float(both_hedged_sharpe_dxy),
        both_retention_dxy=both_retention_dxy,
        uup_n_observations=n_uup,
        uup_subsample_raw_sharpe=uup_subsample_raw_sharpe,
        uup_beta=uup_beta,
        both_hedged_sharpe_uup=both_hedged_sharpe_uup,
        both_retention_uup=both_retention_uup,
        static_tilt_sharpe=static_tilt_sharpe,
        static_tilt_capture=static_tilt_capture,
        top2_block_share_of_gross=top2_share,
        sharpe_ex_top2_blocks=sharpe_ex_top2,
        n_nonoverlapping_formations=n_active,
        bootstrap_p_value=bootstrap_p,
    )


# --- breakeven cost / financing (section 7) ---------------------------------


def breakeven_cost_bps(
    replay: CrossSectionalBacktestResult, cost_bps_used: float
) -> float | None:
    """The one-way cost_bps that would exactly zero out this spec's total
    (additive, non-compounded) realized return, holding turnover fixed —
    the standard linear breakeven approximation: cost scales linearly in
    cost_bps at fixed turnover, so gross_total = net_total + cost_charged,
    and breakeven = cost_bps_used * gross_total / cost_charged. Additive
    (not compounded) and therefore approximate at these return magnitudes
    — disclosed, not treated as exact."""
    cost_charged = replay.total_cost
    if cost_charged <= 0:
        return None
    gross_total = float(replay.daily_returns.sum()) + cost_charged
    return cost_bps_used * gross_total / cost_charged


def breakeven_borrow_bps_per_year(replay: CrossSectionalBacktestResult) -> float | None:
    """The annual short-financing rate (bps/yr on gross notional) that
    would exactly zero out this spec's total realized return, given the
    ACTUAL (0bp) financing charged. Approximates gross notional held at a
    constant 2.0 (a fully formed long_short book) for the whole realized
    calendar-day span — disclosed as an approximation, not a re-derivation
    of the harness's own per-day financing accrual."""
    if len(replay.daily_returns) < 2:
        return None
    calendar_days = (replay.daily_returns.index.max() - replay.daily_returns.index.min()).days
    if calendar_days <= 0:
        return None
    gross_total = float(replay.daily_returns.sum())
    # rate_bps_per_year * 2.0(gross) * calendar_days / 365 / 10000 == gross_total
    return gross_total * 365.0 * 10000.0 / (2.0 * calendar_days)


# --- orchestration -----------------------------------------------------


@dataclass
class CvmScreeningSummary:
    """The full screening pass at the BASE (10bp) cost arm: all 15 trials'
    CrossSectionalScreeningResult rows (12 real specs + 3 combinations,
    sharing ONE sigma_sr and ONE n_trials=15 DSR denominator — see module
    docstring), every trial's confound diagnostic (section 6, unconditional),
    the two cost-sensitivity arms (Sharpe only, NOT new trials), and
    breakeven figures. Assembled here; the pass/fail verdict itself is
    applied by the runner script (data/research_runs/run_country_valmom.py),
    mirroring the residual_momentum precedent."""

    results: list[CrossSectionalScreeningResult]
    confounds: dict[str, CvmConfoundDiagnostic]
    sensitivity_sharpe: dict[str, dict[float, float]]  # pattern_id -> {cost_bps: sharpe}
    breakeven_cost: dict[str, float | None]
    breakeven_borrow: dict[str, float | None]
    # Every trial's own realized (base-cost) daily net return series, keyed
    # by pattern_id — persisted here explicitly so a later preservation_score
    # (or any other) computation never has to re-run the backtest to get it,
    # closing the exact gap that made best_ideas_13f's score incomputable
    # (see module docstring's condition (iv)).
    raw_returns: dict[str, pd.Series]
    panel_start: date | None
    panel_end: date | None
    n_panel_rows: int
    missing_price_data: list[str]
    dxy_start: date | None
    dxy_end: date | None
    uup_start: date | None
    uup_end: date | None
    n_trials: int
    warnings: list[str] = field(default_factory=list)


def run_country_valmom_screening(
    end: date,
    start: date | None = None,
    provider: YFinanceProvider | None = None,
    base_cost_bps: float = CVM_BASE_COST_BPS,
    cost_arms_bps: tuple[float, ...] = CVM_COST_ARMS_BPS,
) -> CvmScreeningSummary:
    """The full pre-registered screening pass: fetches the 15-ETF panel,
    replays all 12 specs at the base cost, builds the 3 combination
    series, computes ONE shared sigma_sr / DSR denominator (n_trials=15)
    across all 15, runs every mandatory confound check (section 6) on
    every one of them, and re-replays the 12 specs at the two cost-
    sensitivity arms (section 7). No forward-validation registration
    happens here — see module docstring's OUT OF SCOPE note."""
    provider = provider if provider is not None else YFinanceProvider()
    fetch_start = start if start is not None else COUNTRY_PRICE_HISTORY_START
    close, missing = fetch_country_price_panel(provider, end, fetch_start)
    warnings: list[str] = []
    if close.empty:
        return CvmScreeningSummary(
            results=[],
            confounds={},
            sensitivity_sharpe={},
            breakeven_cost={},
            breakeven_borrow={},
            raw_returns={},
            panel_start=None,
            panel_end=None,
            n_panel_rows=0,
            missing_price_data=missing,
            dxy_start=None,
            dxy_end=None,
            uup_start=None,
            uup_end=None,
            n_trials=CVM_N_TRIALS,
            warnings=["No country ETF price data resolved — nothing was screened."],
        )
    if missing:
        warnings.append(
            f"{len(missing)} of {len(COUNTRY_ETF_TICKERS)} tickers resolved no price data: {missing}"
        )

    data = CrossSectionalData(close=close)
    specs = build_country_valmom_family()
    membership = fixed_universe_membership(COUNTRY_ETF_TICKERS)

    def _replay_all(cost_bps: float) -> dict[str, CrossSectionalBacktestResult]:
        config = default_country_valmom_config(cost_bps)
        return {spec.pattern_id: run_cross_sectional_backtest(data, spec, config, membership) for spec in specs}

    base_replays = _replay_all(base_cost_bps)
    usable = {
        pid: r
        for pid, r in base_replays.items()
        if r.status == "ok" and len(r.daily_returns) >= MIN_REPLAY_TRADING_DAYS
    }
    if len(usable) < len(specs):
        missing_specs = sorted(set(base_replays) - set(usable))
        warnings.append(
            f"{len(missing_specs)} of {len(specs)} base specs produced no usable replay: {missing_specs}"
        )

    sharpes: dict[str, float] = {
        pid: sharpe_ratio(r.daily_returns, periods_per_year=TRADING_DAYS_PER_YEAR) for pid, r in usable.items()
    }
    combo_returns: dict[str, pd.Series] = {}
    for holding in CVM_HOLDING_DAYS:
        mom_id = f"cvm_mom_2_12_ls_tercile_h{holding}"
        ltr_id = f"cvm_ltr_5y_ls_tercile_h{holding}"
        combo_id = f"cvm_combo_h{holding}"
        if mom_id in usable and ltr_id in usable:
            combo = build_combo_daily_returns(usable[mom_id], usable[ltr_id])
            if len(combo) >= MIN_REPLAY_TRADING_DAYS:
                combo_returns[combo_id] = combo
                sharpes[combo_id] = sharpe_ratio(combo, periods_per_year=TRADING_DAYS_PER_YEAR)
            else:
                warnings.append(f"{combo_id}: combined series too short ({len(combo)} days) to score")
        else:
            missing_leg = mom_id if mom_id not in usable else ltr_id
            warnings.append(f"{combo_id}: {missing_leg} unusable — combination not built")

    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    results: list[CrossSectionalScreeningResult] = []
    for pid, sharpe in sharpes.items():
        dsr = compute_deflated_sharpe(
            sharpe,
            usable[pid].daily_returns if pid in usable else combo_returns[pid],
            CVM_N_TRIALS,
            sigma_sr,
            periods_per_year=TRADING_DAYS_PER_YEAR,
        )
        if pid in usable:
            replay = usable[pid]
            spec = next(s for s in specs if s.pattern_id == pid)
            formed = [f for f in replay.formations if f.skipped_reason is None]
            avg_leg = float(np.mean([len(f.long_tickers) for f in formed])) if formed else 0.0
            results.append(
                CrossSectionalScreeningResult(
                    pattern_id=pid,
                    family=spec.family,
                    citation=spec.citation,
                    n_formations=len(formed),
                    n_skipped_formations=len(replay.formations) - len(formed),
                    avg_names_per_leg=avg_leg,
                    n_trading_days=len(replay.daily_returns),
                    sharpe_annualized=sharpe,
                    total_cost_drag=replay.total_cost,
                    total_financing_drag=replay.total_financing_cost,
                    deflated_sharpe=dsr,
                    total_turnover=float(sum(f.turnover for f in replay.formations)),
                )
            )
        else:
            holding = int(pid.rsplit("_h", 1)[1])
            mom_r = usable[f"cvm_mom_2_12_ls_tercile_h{holding}"]
            ltr_r = usable[f"cvm_ltr_5y_ls_tercile_h{holding}"]
            results.append(
                CrossSectionalScreeningResult(
                    pattern_id=pid,
                    family="country_valmom_combo",
                    citation=CVM_COMBO_CITATION,
                    n_formations=min(_n_active_formations(mom_r), _n_active_formations(ltr_r)),
                    n_skipped_formations=0,
                    avg_names_per_leg=5.0,  # both legs of an ls_tercile combo are 5-name terciles
                    n_trading_days=len(combo_returns[pid]),
                    sharpe_annualized=sharpe,
                    total_cost_drag=0.5 * (mom_r.total_cost + ltr_r.total_cost),
                    total_financing_drag=0.0,
                    deflated_sharpe=dsr,
                    total_turnover=0.5
                    * (
                        sum(f.turnover for f in mom_r.formations)
                        + sum(f.turnover for f in ltr_r.formations)
                    ),
                )
            )

    if len(results) != CVM_N_TRIALS:
        warnings.append(
            f"only {len(results)} of the pre-declared {CVM_N_TRIALS} trials produced a usable result"
        )

    # --- confound diagnostics, every trial, unconditional (section 6) ---
    basket_returns = equal_weight_basket_returns(close)
    dxy_prices, uup_prices = fetch_dollar_factor_panel(provider, end, fetch_start)
    confounds: dict[str, CvmConfoundDiagnostic] = {}
    for r in results:
        holding = int(r.pattern_id.rsplit("_h", 1)[1])
        if r.pattern_id in usable:
            replay = usable[r.pattern_id]
        else:
            # A combination row has no formation records of its own (it is
            # a post-hoc blend of two already-realized streams — see
            # build_combo_daily_returns). Its formation SCHEDULE is shared
            # exactly with its two parent specs (both use the family's one
            # shared COUNTRY_LOOKBACK_DAYS, so mom_2_12 and ltr_5y at the
            # same holding period form on the identical dates), so the
            # momentum leg's own FormationRecords are reused for the
            # block-partition (6.4) and static-tilt (6.3) checks — a
            # disclosed proxy, not a blended reconstruction of both legs'
            # actual combined composition, and reported as such.
            mom_r = usable[f"cvm_mom_2_12_ls_tercile_h{holding}"]
            replay = CrossSectionalBacktestResult(
                status="ok",
                daily_returns=combo_returns[r.pattern_id],
                formations=mom_r.formations,
                total_cost=r.total_cost_drag,
            )
        confounds[r.pattern_id] = compute_confound_diagnostics(
            r.pattern_id, replay, holding, close, basket_returns, dxy_prices, uup_prices
        )

    # --- cost-sensitivity arms: Sharpe only, same 15 trials, not new ones ---
    sensitivity_sharpe: dict[str, dict[float, float]] = {pid: {base_cost_bps: sharpes[pid]} for pid in sharpes}
    for cost_bps in cost_arms_bps:
        if cost_bps == base_cost_bps:
            continue
        arm_replays = _replay_all(cost_bps)
        arm_usable = {
            pid: r
            for pid, r in arm_replays.items()
            if r.status == "ok" and len(r.daily_returns) >= MIN_REPLAY_TRADING_DAYS
        }
        for pid, r in arm_usable.items():
            sensitivity_sharpe.setdefault(pid, {})[cost_bps] = sharpe_ratio(
                r.daily_returns, periods_per_year=TRADING_DAYS_PER_YEAR
            )
        for holding in CVM_HOLDING_DAYS:
            mom_id = f"cvm_mom_2_12_ls_tercile_h{holding}"
            ltr_id = f"cvm_ltr_5y_ls_tercile_h{holding}"
            combo_id = f"cvm_combo_h{holding}"
            if mom_id in arm_usable and ltr_id in arm_usable:
                combo = build_combo_daily_returns(arm_usable[mom_id], arm_usable[ltr_id])
                if len(combo) >= MIN_REPLAY_TRADING_DAYS:
                    sensitivity_sharpe.setdefault(combo_id, {})[cost_bps] = sharpe_ratio(
                        combo, periods_per_year=TRADING_DAYS_PER_YEAR
                    )

    breakeven_cost = {
        pid: (breakeven_cost_bps(usable[pid], base_cost_bps) if pid in usable else None) for pid in sharpes
    }
    breakeven_borrow = {
        pid: (breakeven_borrow_bps_per_year(usable[pid]) if pid in usable else None) for pid in sharpes
    }

    # Every trial's own base-cost daily return series, persisted on the
    # summary itself (see CvmScreeningSummary.raw_returns) so a downstream
    # preservation_score (or any other) computation never has to re-run.
    raw_returns: dict[str, pd.Series] = {
        pid: (usable[pid].daily_returns if pid in usable else combo_returns[pid]) for pid in sharpes
    }

    return CvmScreeningSummary(
        results=sorted(results, key=lambda r: r.sharpe_annualized, reverse=True),
        confounds=confounds,
        sensitivity_sharpe=sensitivity_sharpe,
        breakeven_cost=breakeven_cost,
        breakeven_borrow=breakeven_borrow,
        raw_returns=raw_returns,
        panel_start=close.index.min().date(),
        panel_end=close.index.max().date(),
        n_panel_rows=len(close),
        missing_price_data=missing,
        dxy_start=dxy_prices.index.min().date() if len(dxy_prices) else None,
        dxy_end=dxy_prices.index.max().date() if len(dxy_prices) else None,
        uup_start=uup_prices.index.min().date() if len(uup_prices) else None,
        uup_end=uup_prices.index.max().date() if len(uup_prices) else None,
        n_trials=CVM_N_TRIALS,
        warnings=warnings,
    )
