"""STEP 3 OF THE TSMOM UNIVERSE-VALIDATION PREP PLAN ("Option 1b"): before
accepting the data risk of a real futures-with-roll-mechanics pipeline, try
expanding the existing ETF/cash universe with MORE of the same safe
instrument types, and re-measure pooled effective breadth against the same
15 floor Step 1 used.

WHY THIS RUN EXISTS
====================
Step 1 (run_combined_universe_effective_breadth.py, committed, merged to
main) measured the pooled eigenvalue-based effective breadth of the existing
bonds+FX+commodities+country_valmom ETF/cash universe at 7.10 of 43 nominal
tickers -- below the pre-declared 15 floor. Per that run's own gate
language: "before risking a new futures pipeline, first try expanding the
ETF basket with more of the same safe instrument types (more
currency/commodity/bond-maturity ETFs) -- a SEPARATE, later task". This run
is that separate, later task.

THE HYPOTHESIS, stated before any candidate's correlation was measured
========================================================================
Step 1's own per-universe numbers point at WHERE the redundancy lives:
  bonds           2.09 / 8   -- a single Treasury duration ladder (SHY..TLT)
                                is nearly one interest-rate bet at five
                                durations, plus TIP/LQD/HYG, all still USD
                                and all still US credit/rate risk.
  commodities     5.69 / 11  -- already has its own redundancy-exclusion
                                discipline (COMMODITIES_REDUNDANCY_CORR_LIMIT
                                = 0.90, COMMODITIES_EXCLUDED_REDUNDANT);
                                reused unchanged here for anything added.
  fx              2.69 / 9   -- G10-vs-USD only. G10 currencies share
                                risk-on/risk-off and USD-driven factors
                                (Lustig/Roussanov/Verdelhan 2011's HML-FX
                                factor is exactly this shared component) --
                                EM currencies have documented, economically
                                distinct drivers (local monetary policy,
                                EM carry, commodity-linkage) that plausibly
                                buy real independence.
  country_valmom  2.02 / 15  -- ALL FIFTEEN are developed markets; not one
                                emerging market is present. Developed-market
                                equity indices are known to share a large
                                global-equity-factor loading (this is
                                exactly what "2.02 of 15" already says);
                                emerging markets carry additional,
                                distinct macro/political/currency risk.

The hypothesis, per category:
  FX and country_valmom are the most promising (their existing baskets are
  each missing an entire, economically distinct risk dimension -- EM
  currency regimes, EM equity/political risk -- not just "more of the same
  bucket"). Bonds and commodities are lower priority: bonds' existing
  8-ETF book is already diversified across duration AND credit, so the only
  genuinely NEW risk dimension left is currency/EM sovereign exposure
  (international ex-US treasuries, EM debt) rather than another US
  Treasury-ladder rung; commodities already runs its own redundancy
  discipline and most remaining single-commodity ETPs from the 2010s
  iPath/ETN generation have since been discontinued (verified live below,
  not assumed).

EVERY CANDIDATE BELOW WAS VERIFIED LIVE THROUGH THIS PROJECT'S OWN PRICE
PROVIDER (YFinanceProvider.get_daily_ohlcv), NOT ASSUMED FROM MEMORY, on
2026-09-05:
  * inception/history length and whether the ticker is still recently
    priced (a candidate whose last trade is far in the past is discontinued
    -- see COMMODITIES_CANDIDATES_TO_CHECK_FOR_STALENESS below, and the module docstring
    warning this task brief itself carried: "many single-commodity ETNs
    from this era... have been discontinued");
  * each ETF's actual currency-denomination / index-methodology claim was
    checked against a live source rather than assumed from the ticker's
    name alone (see BONDS CANDIDATES section below for the VWOB finding --
    it is NOT the local-currency EM debt instrument its name might suggest
    to someone recalling the ETF universe from memory; EMLC is).

THE REDUNDANCY DISCIPLINE -- REUSED, NOT REINVENTED
====================================================
cross_sectional_commodities.COMMODITIES_REDUNDANCY_CORR_LIMIT (0.90) is
imported and reused UNCHANGED as this run's own redundancy limit, applied
to every category being expanded, exactly per the task's instruction to
"apply the SAME redundancy discipline commodities already uses... to every
category you're expanding". A candidate whose daily-return correlation
with an already-accepted instrument in the SAME category (original member
or a new addition already accepted ahead of it in a fixed, pre-declared
order) exceeds 0.90 is excluded and logged with the measured correlation
and the instrument it duplicates -- the same record shape
COMMODITIES_EXCLUDED_REDUNDANT uses for BNO.

SCOPE OF THE REDUNDANCY CHECK: WITHIN-CATEGORY, not cross-category. This
matches the existing precedent exactly -- COMMODITIES_EXCLUDED_REDUNDANT
tests BNO only against other COMMODITIES tickers, never against bonds/FX/
country_valmom. A new bond ETF and a new FX pair are different asset
classes measuring different things even if their return series happen to
correlate somewhat (both load partly on global risk sentiment); pooling
and effective_breadth() are exactly the machinery built to measure how much
independence survives THAT correlation, in aggregate, without a hard
per-pair cross-category cutoff. This scope decision is stated here rather
than silently assumed.

Correlation is computed over the INNER-JOINED overlap of the two series'
own trading days (not truncated to whatever the full category's common
window happens to be), so a newer or older candidate is tested against a
comparator on every day both series actually have a price -- the natural
generalization of "over the common window" once candidates no longer all
share one basket's exact history. A comparison with fewer than
MIN_OVERLAP_TRADING_DAYS_FOR_REDUNDANCY_TEST days of overlap is not used to
judge redundancy (logged separately if it is ever the ONLY comparison
available for some candidate) -- correlation on a handful of shared days is
not evidence either way.

ONE REFINEMENT ON TOP OF THE COMMODITIES PRECEDENT, ADDED BECAUSE A REAL
CASE DEMANDED IT (not a hypothetical): a single full-overlap correlation
number was tried first and would have WRONGLY ACCEPTED PCY (Invesco EM
Sovereign Debt ETF) as non-redundant with EMB -- PCY's own pre-2013 history
trades thin/stale enough to depress the full-sample correlation to 0.61
even though every complete year since 2013 measures 0.93-0.97. See
RECENT_REGIME_WINDOW_TRADING_DAYS and the BONDS CANDIDATES section below
for the full finding. Every redundancy comparison in this run therefore
uses the MORE CONSERVATIVE of the full-overlap correlation and the
correlation over just the most recent 1260 trading days (~5 years, this
project's own standing "recent regime" convention) of that overlap, not
the full-overlap number alone. This is a refinement of the SAME 0.90 limit
commodities already uses, not a different threshold -- disclosed here per
the task's own instruction to state clearly if a different-but-justified
methodology is used.

CANDIDATES CONSIDERED, VERIFIED, AND WHAT HAPPENED TO EACH
============================================================

FX (NEW_FX_CANDIDATES) -- the six EM currencies the task brief itself named,
plus two more with equally good live-verified history that the same
reasoning applies to:
  MXN (USDMXN=X), ZAR (USDZAR=X), BRL (USDBRL=X), TRY (USDTRY=X),
  INR (USDINR=X), KRW (USDKRW=X), PLN (USDPLN=X), SGD (USDSGD=X).
All eight are quoted foreign-currency-units-per-USD on yfinance (the same
"USDxxx=X" convention as the existing G10 book's JPY/CHF/CAD/SEK/NOK legs),
so the same invert=True reciprocal-to-USD-per-foreign transform FX_PAIRS
already uses is reused unchanged, and the same scrub_reversing_bad_prints
construction and G10 calibration (4% spike / 50% reversal) is reused
unchanged too -- these are the identical asset class (spot currency pairs
against USD), so the construction AND calibration both carry over, not just
the construction (contrast cross_sectional_commodities.py, which reuses
scrub_reversing_bad_prints' CONSTRUCTION but recalibrates the thresholds
because commodities genuinely whipsaw at magnitudes that would be FX
artifacts).
  REJECTED, insufficient data: CNH (USDCNH=X) resolved a single usable row
    through the price store on the date checked -- nowhere near enough
    history to include or even correlation-test.
  CONSIDERED, not tested: EWS-style "just another currency" padding was not
    pursued beyond these eight; the intent was the smallest well-reasoned,
    regionally-diverse set (Latin America: MXN, BRL; Africa: ZAR; Middle
    East/Europe border: TRY; Asia: INR, KRW; Central Europe: PLN; a
    managed-float Asian financial-center currency: SGD), not an unbounded
    currency dump.

COUNTRY_VALMOM (NEW_COUNTRY_CANDIDATES) -- fourteen emerging/frontier
single-country ETFs, the most direct hypothesis test in this run since the
existing 15-name basket has ZERO emerging markets:
  EWZ Brazil, EWY Korea, EWT Taiwan, EZA South Africa, EWM Malaysia,
  THD Thailand, TUR Turkey, INDA India, FXI China, MCHI China (a second
  China wrapper, deliberately included to let the redundancy discipline
  make the FXI-vs-MCHI call on measured correlation rather than a hand-wave
  -- see result below), EWW Mexico, EIDO Indonesia, EPHE Philippines,
  EPOL Poland.
  All fourteen resolve with long, currently-priced histories through the
  provider (verified live 2026-09-05; earliest of the fourteen, INDA,
  starts 2012-02-03 -- see the "WHAT THIS COSTS" note in the report for
  what that inception date does to the pooled common window and to this
  category's own before/after comparability).

BONDS (NEW_BONDS_CANDIDATES) -- international and EM-sovereign-debt ETFs,
the one dimension the existing 8-ETF all-USD ladder+credit book has none of.
Six candidates were tested; only THREE survive the redundancy screen, and
getting to that final three required catching a real, verified data-quality
confound (see RECENT_REGIME_WINDOW_TRADING_DAYS below) that a naive single-
window correlation test would have missed:
  ACCEPTED:
  BWX  (SPDR Bloomberg International Treasury Bond ETF, tracks the
        Bloomberg Global Treasury ex-US Capped Index) -- developed-market-
        heavy, LOCAL-CURRENCY sovereign debt, so it carries genuine non-USD
        rate risk AND currency risk this basket has never had.
  EMB  (iShares JPMorgan USD Emerging Markets Bond ETF) -- USD-denominated
        EM sovereign credit risk.
  EMLC (VanEck J.P. Morgan EM Local Currency Bond ETF) -- the one instrument
        added here that carries EM LOCAL CURRENCY exposure specifically
        (as opposed to EMB's USD-denominated EM sovereign credit exposure);
        verified live via WebSearch 2026-09-05 against VanEck's own fund
        page, not assumed from the ticker's name.
  REJECTED as redundant (measured, not assumed):
  IGOV (iShares International Treasury Bond ETF, S&P/Citigroup
        International Treasury Bond Index Ex-US) -- BWX's closest sibling
        by construction (same local-currency-ex-US-treasury concept, a
        different index provider). Its FULL-WINDOW correlation against BWX
        (0.8561) would have narrowly CLEARED the 0.90 limit on a naive
        single-window test; its RECENT-1260-day correlation (0.9217) does
        not -- the two funds have converged into the same bet in their
        current trading regime even though their longer joint history
        shows more daylight. Excluded on the operative (more conservative)
        statistic, per RECENT_REGIME_WINDOW_TRADING_DAYS below.
  PCY  (Invesco Emerging Markets Sovereign Debt ETF, DB Emerging Market USD
        Liquid Balanced Index) -- USD-denominated EM sovereign debt, the
        SAME risk dimension EMB already claims (confirmed by a live
        WebSearch of the fund's own factsheet/index description 2026-09-05
        BEFORE trusting any correlation number, per this project's "never
        fabricate" rule: a ticker's name or category label is not evidence
        of what it actually holds). PCY is the case that MOTIVATED the two-
        window redundancy check in the first place: its full-window
        correlation against EMB measures only 0.6061 (comfortably under
        the limit) because PCY's own pre-2013 return series shows the
        signature of thin/stale trading in a then-small fund (4.7% zero-
        return days vs EMB's 1.0%, 73% higher volatility over that
        stretch) -- but every complete calendar year from 2013 onward
        measures 0.93-0.97, and the recent-1260-day figure is 0.9610. A
        single full-window test would have WRONGLY ACCEPTED PCY as a
        genuinely different bet; it is not.
  VWOB (Vanguard Emerging Markets Government Bond ETF, Bloomberg USD
        Emerging Markets Government RIC Capped Index) -- also USD-
        denominated EM sovereign debt (same live-WebSearch verification as
        PCY). VWOB is NOT the local-currency EM debt instrument its
        "Emerging Markets Government Bond" name might suggest from memory
        alone -- this was verified via WebSearch before being treated as a
        fact anywhere in this run. Full-window correlation against EMB
        0.9462, recent-1260-day 0.9869 -- excluded on either statistic.

COMMODITIES (NEW_COMMODITIES_CANDIDATES) -- lowest priority per the task
brief, and the live check below confirms why: most single-commodity ETNs
from the 2010s iPath generation are gone.
  ACCEPTED: CANE (Teucrium Sugar Fund) -- the one still-actively-traded,
    genuinely new single-commodity ETF found; sugar is not represented at
    all in the existing 11-name basket (which has three grains -- CORN,
    WEAT, SOYB -- but no softs).
  REJECTED, discontinued (verified live via the same provider, not assumed
    from "iPath products especially" being named in the task brief): JO
    (iPath Bloomberg Coffee), NIB (iPath Bloomberg Cocoa), BAL (iPath
    Bloomberg Cotton), COW (iPath Bloomberg Livestock) all stopped
    returning priced data on 2023-07-21 in this project's own price store
    -- see COMMODITIES_CANDIDATES_TO_CHECK_FOR_STALENESS and
    STALENESS_THRESHOLD_DAYS below for the systematic (not eyeballed) rule
    applied.

WHAT THIS RUN DOES AND DOES NOT ESTABLISH
==========================================
This measures whether a well-reasoned, honestly-verified expansion of the
SAME FOUR ETF/cash categories clears the same 15-floor gate Step 1 applied.
It does not build a TSMOM signal, does not touch any of the four existing
family modules or their constants (BONDS_UNIVERSE, COMMODITIES_UNIVERSE,
FX_PAIRS, COUNTRY_ETF_TICKERS are imported read-only, exactly as Step 1
imported them), and if the gate still is not cleared, the honest
implication is that Option 2 (a real futures-with-roll-mechanics pipeline)
is likely necessary -- a separate, later decision, not executed here.

Run from backend/ with:
    ./venv/bin/python data/research_runs/run_expand_tsmom_universe.py
"""

from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Same pattern as
# run_combined_universe_effective_breadth.py: running this file by path puts
# data/research_runs/ on sys.path[0], NOT backend/, and this worktree's venv
# is a SYMLINK to the main worktree's venv, whose site-packages would
# otherwise resolve `app` to the MAIN worktree's backend/app -- silently
# measuring the wrong checkout's code.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The measurement would have used another checkout's code."
    )

from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.cross_sectional_bonds import (  # noqa: E402
    BONDS_UNIVERSE,
)
from app.services.research_lab.cross_sectional_commodities import (  # noqa: E402
    COMMODITIES_REDUNDANCY_CORR_LIMIT,
    COMMODITIES_UNIVERSE,
    build_commodities_price_panel,
    effective_breadth,
    scrub_commodity_bad_prints,
)
from app.services.research_lab.cross_sectional_country_valmom import (  # noqa: E402
    COUNTRY_ETF_TICKERS,
    fetch_country_price_panel,
)
from app.services.research_lab.cross_sectional_fx import (  # noqa: E402
    FX_PAIRS,
    build_fx_price_panel,
    scrub_reversing_bad_prints,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr
)
log = logging.getLogger("expand_tsmom_universe")

RUN_DATE = "2026-09-05"
END = date(2026, 9, 5)
# Fetched from well before any candidate's plausible inception, same
# "fetch everything, let the data define the window" idiom Step 1 and every
# family module already use, rather than assuming any start date.
CANDIDATE_FETCH_START = date(1995, 1, 1)
BONDS_PRICE_FETCH_START = date(2000, 1, 1)

OUT_DIR = _BACKEND / "data" / "research_runs"
OUT_JSON = OUT_DIR / f"expand_tsmom_universe_{RUN_DATE}.json"
OUT_TXT = OUT_DIR / f"expand_tsmom_universe_{RUN_DATE}.txt"

# The Step 1 gate, unchanged, per the task brief's own framing that this run
# measures against "the same 15 floor". Not re-litigated here -- see Step
# 1's own module docstring for the derivation of 15 as the qualifying floor
# of the brief's named 15-25+ band.
BREADTH_GATE_FLOOR = 15.0
BREADTH_GATE_BAND_TOP = 25.0

# Reused UNCHANGED from commodities -- see module docstring's REDUNDANCY
# DISCIPLINE section for why this is applied to every expanded category,
# not just commodities.
EXPANSION_REDUNDANCY_CORR_LIMIT = COMMODITIES_REDUNDANCY_CORR_LIMIT

# A pairwise correlation computed on fewer days than this is not trusted to
# judge redundancy either way -- roughly one trading year, comfortably more
# than enough to detect "same bet wearing a second ticker" (BNO/USO's own
# redundancy call used a multi-year common window) while still being far
# short of any candidate's actual overlap in this run (every real
# comparison below has thousands of overlapping days -- see the persisted
# report).
MIN_OVERLAP_TRADING_DAYS_FOR_REDUNDANCY_TEST = 250

# FOUND LIVE, NOT ASSUMED, 2026-09-05, and the reason the redundancy check
# below uses TWO windows rather than one: PCY's full common-window
# correlation against EMB measured 0.6061 (comfortably under the 0.90
# limit) on a first pass, but PCY's own early-history return series shows
# elevated zero-return-day frequency (4.7% of days pre-2013 vs EMB's 1.0%)
# and 73% higher volatility than EMB over that same stretch -- the
# signature of thin/stale trading in a then-small fund, not a genuinely
# different return process. Splitting the same overlap by calendar year
# confirms it: 2007-2013 correlation 0.31, but every complete year from
# 2013 onward measures 0.93-0.97 -- PCY and EMB have moved as effectively
# the same instrument for well over a decade; the depressed full-window
# number is an artifact of PCY's own earliest, thinnest-traded years, not
# evidence of real diversification. Applying only a single full-window
# correlation test would have ACCEPTED PCY as non-redundant on exactly the
# kind of stale-price artifact this project's other scrubs exist to catch.
# The fix generalizes rather than one-off-patches PCY: every redundancy
# comparison below is judged on the MORE CONSERVATIVE (higher) of the full-
# overlap correlation and the correlation over just the most recent
# RECENT_REGIME_WINDOW_TRADING_DAYS of that overlap, so a candidate whose
# current trading regime is a near-duplicate of an existing instrument is
# caught even when its own older history dilutes the full-sample number.
# 1260 trading days (~5 years) is this project's own standing "recent
# regime" convention elsewhere (e.g. cross_sectional_country_valmom.py's
# and cross_sectional_commodities.py's 1260-day long-run-reversal window),
# reused here rather than a value chosen to fit this one finding.
RECENT_REGIME_WINDOW_TRADING_DAYS = 1260

# A raw ticker whose most recent priced row through this project's own
# price store is more than this many CALENDAR days before END is treated as
# discontinued/delisted rather than merely "had a quiet week" -- roughly
# six months, comfortably longer than any real trading halt or holiday
# cluster this project's price store has ever shown, and far short of the
# ~3-year gaps the actually-discontinued iPath ETNs below show.
STALENESS_THRESHOLD_DAYS = 180

# Tolerance for the independent eigenvalue cross-check -- same as Step 1's
# INDEPENDENT_VERIFICATION_TOLERANCE and for the identical reason: both
# effective_breadth() and this run's own independent_effective_breadth are
# float64 LAPACK symmetric eigensolvers over the identical matrix, so they
# should agree to numerical noise, not to a "close enough" figure.
INDEPENDENT_VERIFICATION_TOLERANCE = 1e-9

# Step 1's own persisted "before" numbers (combined_universe_effective_
# breadth_2026-09-05.json, same run date as this run), reproduced here as
# an integrity check on this run's own "before" recomputation -- see
# REPRODUCTION CHECK below. Both runs fetch through the same point-in-time
# price store on the same day, so these should match closely, not just
# approximately.
STEP1_PUBLISHED_BEFORE = {
    "bonds": 2.0884996380245826,
    "commodities": 5.689581350754558,
    "fx": 2.6880919228196505,
    "country_valmom": 2.020022761231478,
    "pooled": 7.09886263295679,
}
STEP1_REPRODUCTION_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# NEW CANDIDATE UNIVERSES -- additive only. NONE of BONDS_UNIVERSE,
# COMMODITIES_UNIVERSE, FX_PAIRS, COUNTRY_ETF_TICKERS is modified anywhere
# in this file; they are imported read-only above and used as-is.
# ---------------------------------------------------------------------------

# currency -> (yfinance ticker, invert). All eight are quoted foreign-per-
# USD on yfinance ("USDxxx=X"), the same convention as the existing G10
# book's JPY/CHF/CAD/SEK/NOK legs, so the same invert=True reciprocal
# transform applies unchanged. See module docstring's CANDIDATES section
# for the per-currency rationale and the CNH_fx rejection.
NEW_FX_CANDIDATES: dict[str, tuple[str, bool]] = {
    "MXN": ("USDMXN=X", True),
    "ZAR": ("USDZAR=X", True),
    "BRL": ("USDBRL=X", True),
    "TRY": ("USDTRY=X", True),
    "INR": ("USDINR=X", True),
    "KRW": ("USDKRW=X", True),
    "PLN": ("USDPLN=X", True),
    "SGD": ("USDSGD=X", True),
}

# Rejected before any correlation test -- insufficient data through this
# project's own price store, verified live 2026-09-05.
FX_CANDIDATES_REJECTED_INSUFFICIENT_DATA: dict[str, str] = {
    "USDCNH=X": "resolved a single usable row through the price store on the date checked",
}

# Ordered so FXI (longer history, 2004) precedes MCHI (2011) -- MCHI is
# tested against FXI's own correlation and is expected to be caught by the
# 0.90 redundancy rule as "the same China bet wearing a second ticker",
# exactly the BNO/USO precedent, verified rather than assumed here.
NEW_COUNTRY_CANDIDATES: list[str] = [
    "EWZ", "EWY", "EWT", "EZA", "EWM", "THD", "TUR", "INDA", "FXI", "MCHI",
    "EWW", "EIDO", "EPHE", "EPOL",
]

NEW_COUNTRY_MARKET_NAMES: dict[str, str] = {
    "EWZ": "Brazil", "EWY": "Korea", "EWT": "Taiwan", "EZA": "South Africa",
    "EWM": "Malaysia", "THD": "Thailand", "TUR": "Turkey", "INDA": "India",
    "FXI": "China (FTSE China 50)", "MCHI": "China (MSCI China)",
    "EWW": "Mexico", "EIDO": "Indonesia", "EPHE": "Philippines", "EPOL": "Poland",
}

# Ordered BWX/EMB first (the two "keeper" instruments in each near-duplicate
# pair, by inception/liquidity), then the candidates expected to test as
# redundant against them, then EMLC last (expected NOT to be redundant --
# see module docstring's BONDS CANDIDATES section for the verified currency-
# denomination distinction that motivates this order).
NEW_BONDS_CANDIDATES: list[str] = ["BWX", "EMB", "IGOV", "PCY", "VWOB", "EMLC"]

NEW_COMMODITIES_CANDIDATES: list[str] = ["CANE"]

# Checked live 2026-09-05 via the same provider and STALENESS_THRESHOLD_
# DAYS rule as every other candidate; all four are the iPath-generation
# single-commodity ETNs the task brief itself warned "have been
# discontinued" -- confirmed, not assumed. Populated by main() with each
# ticker's actual last-priced date; the dict below records only the raw
# tickers checked and rejected for staleness so the report can show real
# vs. reasoned-away numbers.
COMMODITIES_CANDIDATES_TO_CHECK_FOR_STALENESS: list[str] = ["JO", "NIB", "BAL", "COW"]


# ---------------------------------------------------------------------------
# LOADERS -- new tickers only. Original-universe loaders are IMPORTED
# UNCHANGED from each family module (or, for bonds, replicated in the exact
# idiom Step 1 used, since bonds has no premade get_daily_ohlcv panel
# builder of its own -- see that run's module docstring for why this is not
# a second data path in substance).
# ---------------------------------------------------------------------------


def build_bonds_price_panel(
    provider: YFinanceProvider, end: date, start: date = BONDS_PRICE_FETCH_START
) -> tuple[pd.DataFrame, list[str]]:
    """The original 8-ETF BONDS_UNIVERSE close panel -- byte-identical idiom
    to run_combined_universe_effective_breadth.py's own build_bonds_price_
    panel, replicated here (not imported from that script) so this run does
    not depend on Step 1's file continuing to exist at a stable import
    path. See this run's module docstring and Step 1's for why a fresh
    get_daily_ohlcv-close-then-dropna loader is not a second data path in
    substance."""
    tickers = list(BONDS_UNIVERSE)
    frames, _missing_tickers = provider.get_daily_ohlcv(tickers, start, end)
    if not frames or "close" not in frames or frames["close"].empty:
        return pd.DataFrame(), tickers
    raw_close = frames["close"]
    missing = [t for t in tickers if t not in raw_close.columns]
    present = [t for t in tickers if t in raw_close.columns]
    panel = raw_close[present].apply(pd.to_numeric, errors="coerce")
    panel = panel.where(panel > 0.0).sort_index().dropna(how="any")
    return panel, missing


def fetch_close_panel(
    provider: YFinanceProvider, tickers: list[str], start: date, end: date
) -> tuple[pd.DataFrame, list[str]]:
    """Generic close-only panel loader for new country/bonds/commodities
    CANDIDATES. Deliberately NOT dropna(how="any") across all requested
    tickers -- unlike an already-fixed family's own loader (which legitimately
    wants one common window across a basket that is never partially used),
    a candidate GROUP here is provisional: some candidates will be excluded
    by the redundancy screen below, and an excluded candidate's own late
    inception (e.g. VWOB's 2013-06-04) must not be allowed to truncate every
    OTHER candidate's usable history before that screen even runs. Each
    column therefore keeps its own individual valid range; only fully-NaN
    rows (a date none of the requested tickers has data for) are dropped.
    Returns (panel, tickers that resolved no price data at all)."""
    frames, _missing_tickers = provider.get_daily_ohlcv(tickers, start, end)
    if not frames or "close" not in frames or frames["close"].empty:
        return pd.DataFrame(), list(tickers)
    raw_close = frames["close"]
    missing = [t for t in tickers if t not in raw_close.columns]
    present = [t for t in tickers if t in raw_close.columns]
    panel = raw_close[present].apply(pd.to_numeric, errors="coerce")
    panel = panel.where(panel > 0.0).sort_index().dropna(how="all")
    return panel, missing


def fetch_new_fx_panel(
    provider: YFinanceProvider, pairs: dict[str, tuple[str, bool]], start: date, end: date
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """The new EM-currency panel, on the identical USD-per-foreign basis
    and identical bad-print scrub (construction AND calibration -- see
    module docstring) as build_fx_price_panel uses for the existing G10
    book. Deliberately NOT dropna(how="any") across all requested pairs --
    same reasoning as fetch_close_panel: a candidate group here is
    provisional ahead of the redundancy screen, so one currency's own
    inception must not truncate every other candidate's usable history.
    Returns (scrubbed panel with each column's own individual range
    preserved, scrub flag frame, currencies with no price data)."""
    tickers = [t for t, _ in pairs.values()]
    frames, _missing_tickers = provider.get_daily_ohlcv(tickers, start, end)
    if not frames or "close" not in frames or frames["close"].empty:
        return pd.DataFrame(), pd.DataFrame(), list(pairs)

    raw_close = frames["close"]
    missing = [c for c, (t, _inv) in pairs.items() if t not in raw_close.columns]

    columns: dict[str, pd.Series] = {}
    for currency, (ticker, invert) in pairs.items():
        if ticker not in raw_close.columns:
            continue
        series = pd.to_numeric(raw_close[ticker], errors="coerce")
        series = series.where(series > 0.0)
        columns[currency] = (1.0 / series) if invert else series

    if not columns:
        return pd.DataFrame(), pd.DataFrame(), list(pairs)

    panel = pd.DataFrame(columns).sort_index().dropna(how="all")
    scrubbed, flags = scrub_reversing_bad_prints(panel)
    n_scrubbed = int(flags.to_numpy().sum())
    if n_scrubbed:
        log.warning(
            "new FX candidates: scrubbed %d single-day bad print(s) that fully reversed the next "
            "day, out of %d cells (%s).",
            n_scrubbed,
            flags.size,
            {c: int(flags[c].sum()) for c in flags.columns if int(flags[c].sum())},
        )
    return scrubbed, flags, missing


def check_recency(
    provider: YFinanceProvider, ticker: str, end: date, max_staleness_days: int = STALENESS_THRESHOLD_DAYS
) -> dict[str, Any]:
    """Verifies a single raw ticker actually has recent price data through
    this project's own price store, rather than assuming a ticker known to
    have existed at some point is still tradeable today. Returns a dict
    with ok=True/first/last/n_rows/days_stale on success, ok=False with a
    reason otherwise."""
    frames, missing = provider.get_daily_ohlcv([ticker], CANDIDATE_FETCH_START, end)
    if not frames or "close" not in frames or frames["close"].empty or ticker in missing:
        return {"ticker": ticker, "ok": False, "reason": "no price data resolved"}
    close = frames["close"][ticker].dropna()
    if close.empty:
        return {"ticker": ticker, "ok": False, "reason": "empty after dropna"}
    first = close.index[0].date()
    last = close.index[-1].date()
    days_stale = (end - last).days
    ok = days_stale <= max_staleness_days
    return {
        "ticker": ticker,
        "ok": ok,
        "first": str(first),
        "last": str(last),
        "n_rows": int(len(close)),
        "days_stale": int(days_stale),
        "reason": None if ok else f"last priced {days_stale} days before end date -- discontinued",
    }


# ---------------------------------------------------------------------------
# INDEPENDENT VERIFICATION -- a second derivation, not a second call. Typed
# fresh here (numpy.linalg.eigh, formula hand-typed from source) rather than
# imported from Step 1's own independent_effective_breadth, so this run's
# cross-check does not depend on -- or share a bug with -- that script's.
# ---------------------------------------------------------------------------


def independent_effective_breadth(daily_returns: pd.DataFrame) -> tuple[float, int]:
    """A from-scratch re-derivation of cross_sectional_commodities.
    effective_breadth: sum(lambda)^2 / sum(lambda^2) over the correlation
    spectrum, typed fresh from the source formula rather than copied from
    that function's body, via numpy.linalg.eigh (the general symmetric
    eigendecomposition) rather than numpy.linalg.eigvalsh (the eigenvalues-
    only routine effective_breadth itself calls). Returns (effective
    breadth, n columns used after dropna(how="any"))."""
    usable = daily_returns.dropna(how="any")
    corr = usable.corr().to_numpy()
    eigenvalues, _eigenvectors = np.linalg.eigh(corr)
    numerator = eigenvalues.sum() ** 2
    denominator = (eigenvalues**2).sum()
    return float(numerator / denominator), int(usable.shape[1])


# ---------------------------------------------------------------------------
# TICKER-OVERLAP CHECK -- typed fresh here for the same self-containment
# reason as independent_effective_breadth (not imported from Step 1).
# ---------------------------------------------------------------------------


def find_ticker_overlaps(universes: dict[str, list[str]]) -> dict[str, list[str]]:
    """{instrument_id: [universe names that both claim it]} for any column
    identifier appearing in more than one universe's namespace."""
    owners: dict[str, list[str]] = defaultdict(list)
    for name, tickers in universes.items():
        for t in tickers:
            owners[t].append(name)
    return {t: names for t, names in owners.items() if len(names) > 1}


# ---------------------------------------------------------------------------
# THE REDUNDANCY SCREEN -- the same discipline commodities already uses,
# applied live, per candidate, in a fixed pre-declared order.
# ---------------------------------------------------------------------------


def _pair_correlation(
    series_a: pd.Series, series_b: pd.Series, min_overlap_days: int,
    recent_window_days: int = RECENT_REGIME_WINDOW_TRADING_DAYS,
) -> dict[str, Any] | None:
    """One candidate/comparator pair's redundancy statistic: the MORE
    CONSERVATIVE (higher) of the full-overlap correlation and the
    correlation over just the most recent `recent_window_days` of that same
    overlap -- see RECENT_REGIME_WINDOW_TRADING_DAYS's docstring for why a
    single full-window number is not trusted alone (the PCY/EMB finding:
    thin early-history trading can depress a full-sample correlation well
    below what the same two instruments show in their current, mature
    trading regime). Returns None if the overlap is too short to trust at
    all (fewer than min_overlap_days). The recent-window figure is skipped
    (recorded None) rather than computed on too few days if the overlap
    itself is shorter than a reasonable fraction of recent_window_days."""
    joined = pd.concat([series_a, series_b], axis=1, join="inner").dropna()
    if len(joined) < min_overlap_days:
        return None
    full_corr = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
    recent = joined.iloc[-recent_window_days:]
    recent_corr = (
        float(recent.iloc[:, 0].corr(recent.iloc[:, 1]))
        if len(recent) >= min_overlap_days
        else None
    )
    operative = max(full_corr, recent_corr) if recent_corr is not None else full_corr
    return {
        "operative_correlation": operative,
        "full_window_correlation": full_corr,
        "recent_window_correlation": recent_corr,
        "recent_window_days_used": int(len(recent)) if recent_corr is not None else None,
        "overlap_days": int(len(joined)),
    }


def screen_redundant_candidates(
    candidate_returns: dict[str, pd.Series],
    base_returns: dict[str, pd.Series],
    order: list[str],
    corr_limit: float = EXPANSION_REDUNDANCY_CORR_LIMIT,
    min_overlap_days: int = MIN_OVERLAP_TRADING_DAYS_FOR_REDUNDANCY_TEST,
) -> tuple[dict[str, pd.Series], dict[str, dict[str, Any]]]:
    """Sequentially tests each candidate in `order` against the union of
    `base_returns` (the existing family's own tickers) and every candidate
    already accepted ahead of it. Each pairwise comparison's statistic is
    _pair_correlation's "operative_correlation" -- the more conservative of
    the full-overlap and recent-window correlations, not the full-overlap
    number alone (see RECENT_REGIME_WINDOW_TRADING_DAYS). A candidate whose
    WORST (highest operative correlation) comparison against that accepted
    set exceeds corr_limit is excluded (logged with which ticker it
    duplicates and both correlation figures); otherwise it is accepted and
    joins the comparison set for candidates still to come, exactly the
    sequential, order-dependent process COMMODITIES_EXCLUDED_REDUNDANT's
    own BNO-vs-USO call is a (single-candidate) instance of.

    Returns (accepted {label: return series}, decisions {label: record}) --
    decisions covers every candidate in `order`, accepted or not, so the
    caller/report never has to re-derive which happened from `accepted`
    alone. A candidate with no comparison meeting min_overlap_days is
    accepted but flagged status="accepted_untested_insufficient_overlap"
    rather than silently treated as "tested and found non-redundant"."""
    accepted_pool: dict[str, pd.Series] = dict(base_returns)
    accepted_new: dict[str, pd.Series] = {}
    decisions: dict[str, dict[str, Any]] = {}

    for label in order:
        series = candidate_returns[label]
        worst: tuple[str, dict[str, Any]] | None = None
        for other_label, other_series in accepted_pool.items():
            stats = _pair_correlation(series, other_series, min_overlap_days)
            if stats is None:
                continue
            if worst is None or stats["operative_correlation"] > worst[1]["operative_correlation"]:
                worst = (other_label, stats)

        if worst is None:
            accepted_pool[label] = series
            accepted_new[label] = series
            decisions[label] = {
                "status": "accepted_untested_insufficient_overlap",
                "max_correlation": None,
                "full_window_correlation": None,
                "recent_window_correlation": None,
                "compared_against": None,
                "overlap_days": None,
            }
        elif worst[1]["operative_correlation"] > corr_limit:
            decisions[label] = {
                "status": "excluded_redundant",
                "max_correlation": round(worst[1]["operative_correlation"], 4),
                "full_window_correlation": round(worst[1]["full_window_correlation"], 4),
                "recent_window_correlation": (
                    round(worst[1]["recent_window_correlation"], 4)
                    if worst[1]["recent_window_correlation"] is not None else None
                ),
                "compared_against": worst[0],
                "overlap_days": worst[1]["overlap_days"],
            }
        else:
            accepted_pool[label] = series
            accepted_new[label] = series
            decisions[label] = {
                "status": "accepted",
                "max_correlation": round(worst[1]["operative_correlation"], 4),
                "full_window_correlation": round(worst[1]["full_window_correlation"], 4),
                "recent_window_correlation": (
                    round(worst[1]["recent_window_correlation"], 4)
                    if worst[1]["recent_window_correlation"] is not None else None
                ),
                "compared_against": worst[0],
                "overlap_days": worst[1]["overlap_days"],
            }
    return accepted_new, decisions


# ---------------------------------------------------------------------------
# THE GATE DECISION -- same pure function shape as Step 1's branch_for/
# branch_statement, same floor (BREADTH_GATE_FLOOR = 15.0, not re-litigated
# here). Typed fresh rather than imported for the same self-containment
# reason as the other two "typed fresh" functions above.
# ---------------------------------------------------------------------------


def branch_for(pooled_effective_breadth: float) -> str:
    return "proceed" if pooled_effective_breadth >= BREADTH_GATE_FLOOR else "expand_further_or_build_futures_pipeline"


def branch_statement(pooled_effective_breadth: float) -> str:
    branch = branch_for(pooled_effective_breadth)
    if branch == "proceed":
        where = (
            "within the 15-25+ band"
            if pooled_effective_breadth <= BREADTH_GATE_BAND_TOP
            else "above the 15-25+ band entirely"
        )
        return (
            f"PROCEED: the expanded pooled effective breadth {pooled_effective_breadth:.2f} clears "
            f"the {BREADTH_GATE_FLOOR:.0f} floor ({where}) -- proceed to building TSMOM on this "
            "expanded ETF/cash universe. No further expansion or futures pipeline is indicated by "
            "this number."
        )
    return (
        f"STILL BELOW FLOOR: the expanded pooled effective breadth {pooled_effective_breadth:.2f} "
        f"remains below the {BREADTH_GATE_FLOOR:.0f} floor even after a well-reasoned, honestly-"
        "verified expansion of all four ETF/cash categories. This is not a failure to fix by adding "
        "more tickers of the same kind -- the per-category numbers show WHY (see report): the "
        "dominant source of correlation is a shared global-risk/equity factor that more ETFs of the "
        "same instrument types cannot diversify away. The honest implication is that Option 2 (a "
        "real futures-with-roll-mechanics pipeline, spanning asset classes and mechanisms this ETF/ "
        "cash substitute structurally cannot reach) is likely necessary before a TSMOM pass/fail "
        "verdict on this project's data would be trustworthy. That is a separate, later decision, "
        "not executed here."
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main() -> None:
    provider = YFinanceProvider()

    # --- BEFORE: reproduce the four original panels, exactly Step 1's own
    # loaders (imported unchanged; bonds replicated in the same idiom). ---
    log.info("fetching ORIGINAL bonds panel (%d tickers)...", len(BONDS_UNIVERSE))
    bonds_before, bonds_before_missing = build_bonds_price_panel(provider, END)
    log.info("fetching ORIGINAL commodities panel (%d tickers)...", len(COMMODITIES_UNIVERSE))
    commodities_before, _cmd_scrub, commodities_before_missing = build_commodities_price_panel(provider, END)
    log.info("fetching ORIGINAL fx panel (%d currencies)...", len(FX_PAIRS))
    fx_before, _fx_scrub, fx_before_missing = build_fx_price_panel(provider, END)
    log.info("fetching ORIGINAL country_valmom panel (%d tickers)...", len(COUNTRY_ETF_TICKERS))
    country_before, country_before_missing = fetch_country_price_panel(provider, END)
    country_before = country_before.dropna(how="any")

    for label, panel, missing in (
        ("bonds", bonds_before, bonds_before_missing),
        ("commodities", commodities_before, commodities_before_missing),
        ("fx", fx_before, fx_before_missing),
        ("country_valmom", country_before, country_before_missing),
    ):
        if panel.empty:
            raise SystemExit(f"REFUSING TO RUN: original {label} panel came back empty (missing={missing})")
        if missing:
            log.warning("%s: %d original ticker(s) resolved no price data: %s", label, len(missing), missing)

    # --- staleness/recency checks on every raw candidate ticker, including
    # the ones expected to fail (JO/NIB/BAL/COW, USDCNH=X) -- verified live,
    # not assumed. ---------------------------------------------------------
    staleness_checks: dict[str, dict[str, Any]] = {}
    for ticker in COMMODITIES_CANDIDATES_TO_CHECK_FOR_STALENESS:
        staleness_checks[ticker] = check_recency(provider, ticker, END)
        log.info("staleness check %s: %s", ticker, staleness_checks[ticker])
    for ticker in list(FX_CANDIDATES_REJECTED_INSUFFICIENT_DATA):
        staleness_checks[ticker] = check_recency(provider, ticker, END)
        log.info("staleness check %s: %s", ticker, staleness_checks[ticker])
    # Also check every candidate actually being tested, so a silent
    # mid-history delisting (rather than a fully rejected one) would still
    # be caught rather than assumed away.
    for ticker in (
        [t for t, _ in NEW_FX_CANDIDATES.values()]
        + NEW_COUNTRY_CANDIDATES
        + NEW_BONDS_CANDIDATES
        + NEW_COMMODITIES_CANDIDATES
    ):
        if ticker not in staleness_checks:
            staleness_checks[ticker] = check_recency(provider, ticker, END)
    stale_among_tested = {t: c for t, c in staleness_checks.items() if not c["ok"]}
    if stale_among_tested:
        log.warning("candidates failing the recency check: %s", stale_among_tested)

    # --- fetch new-candidate panels ---------------------------------------
    log.info("fetching NEW fx candidate panel (%d currencies)...", len(NEW_FX_CANDIDATES))
    new_fx_panel, _new_fx_scrub, new_fx_missing = fetch_new_fx_panel(
        provider, NEW_FX_CANDIDATES, CANDIDATE_FETCH_START, END
    )
    log.info("fetching NEW country candidate panel (%d tickers)...", len(NEW_COUNTRY_CANDIDATES))
    new_country_panel, new_country_missing = fetch_close_panel(
        provider, NEW_COUNTRY_CANDIDATES, CANDIDATE_FETCH_START, END
    )
    log.info("fetching NEW bonds candidate panel (%d tickers)...", len(NEW_BONDS_CANDIDATES))
    new_bonds_panel, new_bonds_missing = fetch_close_panel(
        provider, NEW_BONDS_CANDIDATES, CANDIDATE_FETCH_START, END
    )
    log.info("fetching NEW commodities candidate panel (%d tickers)...", len(NEW_COMMODITIES_CANDIDATES))
    new_commodities_panel_raw, new_commodities_missing = fetch_close_panel(
        provider, NEW_COMMODITIES_CANDIDATES, CANDIDATE_FETCH_START, END
    )
    new_commodities_panel, _commod_scrub_flags = scrub_commodity_bad_prints(new_commodities_panel_raw)

    for label, missing in (
        ("new_fx", new_fx_missing), ("new_country", new_country_missing),
        ("new_bonds", new_bonds_missing), ("new_commodities", new_commodities_missing),
    ):
        if missing:
            log.warning("%s: %d candidate ticker(s) resolved no price data: %s", label, len(missing), missing)

    # --- redundancy screen, per category, in the pre-declared order ------
    def returns_dict(panel: pd.DataFrame) -> dict[str, pd.Series]:
        """Each column's OWN daily-return series, dropna'd individually --
        NOT a joint dropna(how="any") across every column in `panel`. For
        the four ORIGINAL family panels this makes no difference (each is
        already one internally-consistent common-window panel by
        construction). For the CANDIDATE panels it is load-bearing: a
        joint dropna here would let one candidate's late inception (or a
        candidate later excluded as redundant) truncate every other
        candidate's own history before screen_redundant_candidates' own
        pairwise inner-join comparisons even run."""
        return {c: panel[c].pct_change(fill_method=None).dropna() for c in panel.columns}

    bonds_before_ret = returns_dict(bonds_before)
    commodities_before_ret = returns_dict(commodities_before)
    fx_before_ret = returns_dict(fx_before)
    country_before_ret = returns_dict(country_before)

    fx_candidate_ret = returns_dict(new_fx_panel)
    country_candidate_ret = returns_dict(new_country_panel)
    bonds_candidate_ret = returns_dict(new_bonds_panel)
    commodities_candidate_ret = returns_dict(new_commodities_panel)

    fx_order = [c for c in NEW_FX_CANDIDATES if c in fx_candidate_ret]
    fx_accepted_ret, fx_decisions = screen_redundant_candidates(fx_candidate_ret, fx_before_ret, fx_order)

    country_order = [c for c in NEW_COUNTRY_CANDIDATES if c in country_candidate_ret]
    country_accepted_ret, country_decisions = screen_redundant_candidates(
        country_candidate_ret, country_before_ret, country_order
    )

    bonds_order = [c for c in NEW_BONDS_CANDIDATES if c in bonds_candidate_ret]
    bonds_accepted_ret, bonds_decisions = screen_redundant_candidates(
        bonds_candidate_ret, bonds_before_ret, bonds_order
    )

    commodities_order = [c for c in NEW_COMMODITIES_CANDIDATES if c in commodities_candidate_ret]
    commodities_accepted_ret, commodities_decisions = screen_redundant_candidates(
        commodities_candidate_ret, commodities_before_ret, commodities_order
    )

    for label, decisions in (
        ("fx", fx_decisions), ("country_valmom", country_decisions),
        ("bonds", bonds_decisions), ("commodities", commodities_decisions),
    ):
        for ticker, d in decisions.items():
            log.info("%-14s %-6s %s", label, ticker, d)

    # --- build the ACCEPTED new-ticker panels (columns actually kept) ----
    fx_accepted_cols = list(fx_accepted_ret)
    country_accepted_cols = list(country_accepted_ret)
    bonds_accepted_cols = list(bonds_accepted_ret)
    commodities_accepted_cols = list(commodities_accepted_ret)

    new_fx_accepted_panel = new_fx_panel[fx_accepted_cols]
    new_country_accepted_panel = new_country_panel[country_accepted_cols]
    new_bonds_accepted_panel = new_bonds_panel[bonds_accepted_cols]
    new_commodities_accepted_panel = new_commodities_panel[commodities_accepted_cols]

    # --- ticker-overlap check across the FOUR EXPANDED universes ---------
    universes_for_overlap = {
        "bonds": list(bonds_before.columns) + bonds_accepted_cols,
        "commodities": list(commodities_before.columns) + commodities_accepted_cols,
        "fx": list(fx_before.columns) + fx_accepted_cols,
        "country_valmom": list(country_before.columns) + country_accepted_cols,
    }
    overlaps = find_ticker_overlaps(universes_for_overlap)
    if overlaps:
        log.warning("TICKER OVERLAP ACROSS EXPANDED UNIVERSES: %s", overlaps)
    else:
        log.info("no ticker overlap across the four expanded universes")

    # --- per-category effective breadth, before vs after, with independent
    # verification on every single call. ------------------------------
    per_category: dict[str, dict[str, Any]] = {}
    category_specs = (
        ("bonds", bonds_before, new_bonds_accepted_panel),
        ("commodities", commodities_before, new_commodities_accepted_panel),
        ("fx", fx_before, new_fx_accepted_panel),
        ("country_valmom", country_before, new_country_accepted_panel),
    )
    worst_delta_overall = 0.0
    for label, before_panel, new_panel in category_specs:
        before_returns = before_panel.pct_change(fill_method=None)
        eb_before = effective_breadth(before_returns)
        eb_before_indep, _n_before_indep = independent_effective_breadth(before_returns)
        delta_before = abs(eb_before - eb_before_indep)

        after_panel = pd.concat([before_panel, new_panel], axis=1, join="outer", sort=False).sort_index()
        after_panel = after_panel.dropna(how="any")
        after_returns = after_panel.pct_change(fill_method=None)
        eb_after = effective_breadth(after_returns)
        eb_after_indep, _n_after_indep = independent_effective_breadth(after_returns)
        delta_after = abs(eb_after - eb_after_indep)

        worst_delta_overall = max(worst_delta_overall, delta_before, delta_after)
        for tag, delta in (("before", delta_before), ("after", delta_after)):
            if delta > INDEPENDENT_VERIFICATION_TOLERANCE:
                raise SystemExit(
                    f"REFUSING TO REPORT: {label} ({tag})'s independent eigenvalue re-derivation "
                    f"disagrees with effective_breadth() by {delta:.3e}, over the "
                    f"{INDEPENDENT_VERIFICATION_TOLERANCE:.0e} tolerance."
                )

        usable_before = before_returns.dropna(how="any")
        usable_after = after_returns.dropna(how="any")
        per_category[label] = {
            "n_nominal_before": int(before_panel.shape[1]),
            "n_nominal_after": int(after_panel.shape[1]),
            "n_new_accepted": int(new_panel.shape[1]),
            "effective_breadth_before": eb_before,
            "effective_breadth_after": eb_after,
            "independent_verification_delta_before": delta_before,
            "independent_verification_delta_after": delta_after,
            "window_before": [str(usable_before.index[0].date()), str(usable_before.index[-1].date())]
            if len(usable_before) else [None, None],
            "window_after": [str(usable_after.index[0].date()), str(usable_after.index[-1].date())]
            if len(usable_after) else [None, None],
            "n_rows_before": int(len(usable_before)),
            "n_rows_after": int(len(usable_after)),
        }
        log.info(
            "%-14s before: n=%2d eb=%.4f (%s..%s, %d rows)  after: n=%2d eb=%.4f (%s..%s, %d rows)",
            label, before_panel.shape[1], eb_before,
            per_category[label]["window_before"][0], per_category[label]["window_before"][1],
            per_category[label]["n_rows_before"],
            after_panel.shape[1], eb_after,
            per_category[label]["window_after"][0], per_category[label]["window_after"][1],
            per_category[label]["n_rows_after"],
        )

    # --- STEP 1 REPRODUCTION CHECK on this run's own "before" numbers ----
    reproduction_deltas = {
        label: abs(per_category[label]["effective_breadth_before"] - STEP1_PUBLISHED_BEFORE[label])
        for label in ("bonds", "commodities", "fx", "country_valmom")
    }
    reproduction_ok = all(d <= STEP1_REPRODUCTION_TOLERANCE for d in reproduction_deltas.values())
    log.info(
        "Step 1 reproduction check (this run's BEFORE numbers vs Step 1's persisted numbers): %s -> %s",
        reproduction_deltas, "OK" if reproduction_ok else "MISMATCH -- investigate before trusting this run",
    )
    if not reproduction_ok:
        log.warning(
            "This run's own 'before' recomputation does not match Step 1's persisted numbers within "
            "%.4f. Both runs fetch through the same point-in-time price store, so a mismatch here "
            "would mean something about this run's loaders or the underlying data has drifted since "
            "Step 1 -- reported, not hidden, but not a hard abort since the AFTER numbers (this run's "
            "actual deliverable) are independently verified in their own right above.",
            STEP1_REPRODUCTION_TOLERANCE,
        )

    # --- pooled: BEFORE (the original 43) and AFTER (43 + accepted) ------
    pooled_before_close = pd.concat(
        [bonds_before, commodities_before, fx_before, country_before], axis=1, join="outer", sort=False
    ).sort_index()
    pooled_before_returns = pooled_before_close.pct_change(fill_method=None)
    pooled_eb_before = effective_breadth(pooled_before_returns)
    pooled_eb_before_indep, _n = independent_effective_breadth(pooled_before_returns)
    pooled_before_delta = abs(pooled_eb_before - pooled_eb_before_indep)

    pooled_after_returns_raw = pd.concat(
        [
            bonds_before, new_bonds_accepted_panel,
            commodities_before, new_commodities_accepted_panel,
            fx_before, new_fx_accepted_panel,
            country_before, new_country_accepted_panel,
        ],
        axis=1, join="outer", sort=False,
    ).sort_index()
    pooled_after_returns = pooled_after_returns_raw.pct_change(fill_method=None)
    pooled_eb_after = effective_breadth(pooled_after_returns)
    pooled_eb_after_indep, _n2 = independent_effective_breadth(pooled_after_returns)
    pooled_after_delta = abs(pooled_eb_after - pooled_eb_after_indep)

    worst_delta_overall = max(worst_delta_overall, pooled_before_delta, pooled_after_delta)
    for tag, delta in (("pooled before", pooled_before_delta), ("pooled after", pooled_after_delta)):
        if delta > INDEPENDENT_VERIFICATION_TOLERANCE:
            raise SystemExit(
                f"REFUSING TO REPORT: {tag}'s independent eigenvalue re-derivation disagrees with "
                f"effective_breadth() by {delta:.3e}, over the {INDEPENDENT_VERIFICATION_TOLERANCE:.0e} "
                "tolerance."
            )

    pooled_usable_before = pooled_before_returns.dropna(how="any")
    pooled_usable_after = pooled_after_returns.dropna(how="any")
    n_nominal_before = pooled_before_close.shape[1]
    n_nominal_after = pooled_after_returns_raw.shape[1]

    log.info(
        "POOLED before: n=%d eb=%.4f (%s..%s, %d rows)  after: n=%d eb=%.4f (%s..%s, %d rows)",
        n_nominal_before, pooled_eb_before,
        pooled_usable_before.index[0].date(), pooled_usable_before.index[-1].date(), len(pooled_usable_before),
        n_nominal_after, pooled_eb_after,
        pooled_usable_after.index[0].date(), pooled_usable_after.index[-1].date(), len(pooled_usable_after),
    )

    branch = branch_for(pooled_eb_after)
    statement = branch_statement(pooled_eb_after)
    log.info(statement)

    def decisions_payload(decisions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return decisions

    payload: dict[str, Any] = {
        "run_date": RUN_DATE,
        "purpose": (
            "STEP 3 ('Option 1b') of the TSMOM universe-validation prep plan. Expands the bonds/"
            "commodities/fx/country_valmom ETF/cash universe with verified, non-redundant additions "
            "per category and re-measures pooled effective breadth against the same 15 floor Step 1 "
            "used, using cross_sectional_commodities.effective_breadth() unchanged. Builds no TSMOM "
            "signal and does not modify any of the four existing family modules' constants."
        ),
        "method": (
            "sum(lambda)^2 / sum(lambda^2) over the correlation spectrum of a daily-return panel "
            "(cross_sectional_commodities.effective_breadth, imported and called unchanged), before "
            "vs. after adding the accepted new tickers per category."
        ),
        "redundancy_discipline": {
            "corr_limit": EXPANSION_REDUNDANCY_CORR_LIMIT,
            "source": "cross_sectional_commodities.COMMODITIES_REDUNDANCY_CORR_LIMIT, imported unchanged",
            "scope": "within-category only (candidate vs. existing+already-accepted tickers in the "
            "SAME category), matching the existing COMMODITIES_EXCLUDED_REDUNDANT precedent's own scope",
            "min_overlap_trading_days": MIN_OVERLAP_TRADING_DAYS_FOR_REDUNDANCY_TEST,
            "recent_window_trading_days": RECENT_REGIME_WINDOW_TRADING_DAYS,
            "operative_statistic": "max(full-overlap correlation, correlation over the most recent "
            f"{RECENT_REGIME_WINDOW_TRADING_DAYS} trading days of that overlap) -- see PCY/EMB finding "
            "in the module docstring for why a single full-window number is not trusted alone",
        },
        "staleness_checks": staleness_checks,
        "staleness_threshold_days": STALENESS_THRESHOLD_DAYS,
        "candidate_decisions": {
            "fx": decisions_payload(fx_decisions),
            "country_valmom": decisions_payload(country_decisions),
            "bonds": decisions_payload(bonds_decisions),
            "commodities": decisions_payload(commodities_decisions),
        },
        "fx_rejected_insufficient_data": FX_CANDIDATES_REJECTED_INSUFFICIENT_DATA,
        "gate": {
            "floor": BREADTH_GATE_FLOOR,
            "band_top": BREADTH_GATE_BAND_TOP,
            "rule": ">= floor -> proceed to building TSMOM on the expanded universe; below -> the "
            "honest implication is that a real futures pipeline (Option 2) is likely necessary.",
        },
        "step1_reproduction_check": {
            "published_before": STEP1_PUBLISHED_BEFORE,
            "measured_before": {
                "bonds": per_category["bonds"]["effective_breadth_before"],
                "commodities": per_category["commodities"]["effective_breadth_before"],
                "fx": per_category["fx"]["effective_breadth_before"],
                "country_valmom": per_category["country_valmom"]["effective_breadth_before"],
                "pooled": pooled_eb_before,
            },
            "deltas": {**reproduction_deltas, "pooled": abs(pooled_eb_before - STEP1_PUBLISHED_BEFORE["pooled"])},
            "tolerance": STEP1_REPRODUCTION_TOLERANCE,
            "reproduced_within_tolerance": reproduction_ok
            and abs(pooled_eb_before - STEP1_PUBLISHED_BEFORE["pooled"]) <= STEP1_REPRODUCTION_TOLERANCE,
        },
        "per_category": per_category,
        "ticker_overlaps": overlaps,
        "pooled": {
            "n_nominal_before": n_nominal_before,
            "n_nominal_after": n_nominal_after,
            "n_new_accepted": n_nominal_after - n_nominal_before,
            "effective_breadth_before": pooled_eb_before,
            "effective_breadth_after": pooled_eb_after,
            "effective_breadth_before_independent": pooled_eb_before_indep,
            "effective_breadth_after_independent": pooled_eb_after_indep,
            "independent_verification_delta_before": pooled_before_delta,
            "independent_verification_delta_after": pooled_after_delta,
            "common_window_before": [
                str(pooled_usable_before.index[0].date()), str(pooled_usable_before.index[-1].date())
            ] if len(pooled_usable_before) else [None, None],
            "common_window_after": [
                str(pooled_usable_after.index[0].date()), str(pooled_usable_after.index[-1].date())
            ] if len(pooled_usable_after) else [None, None],
            "n_common_trading_days_before": int(len(pooled_usable_before)),
            "n_common_trading_days_after": int(len(pooled_usable_after)),
        },
        "branch": branch,
        "branch_statement": statement,
        "verification": {
            "every_effective_breadth_call_independently_rederived": True,
            "independent_method": (
                "numpy.linalg.eigh on the same correlation matrix (vs effective_breadth()'s own "
                "numpy.linalg.eigvalsh), sum(lambda)^2/sum(lambda^2) hand-typed fresh from the source "
                "formula, typed independently of Step 1's own independent_effective_breadth"
            ),
            "tolerance": INDEPENDENT_VERIFICATION_TOLERANCE,
            "worst_delta_any_call": worst_delta_overall,
        },
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    OUT_TXT.write_text(render_report(payload))
    log.info("wrote %s and %s", OUT_JSON.name, OUT_TXT.name)


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def render_report(p: dict[str, Any]) -> str:
    L: list[str] = []
    a = L.append
    a(f"EXPAND TSMOM UNIVERSE -- TSMOM PREP STEP 3 / OPTION 1B -- {p['run_date']}")
    a("=" * 100)
    a("")
    for line in _wrap(p["purpose"], 96):
        a(line)
    a("")
    a(f"METHOD: {p['method']}")
    a("")
    a("REDUNDANCY DISCIPLINE")
    a("-" * 100)
    rd = p["redundancy_discipline"]
    a(f"  correlation limit: {rd['corr_limit']:.2f}  (source: {rd['source']})")
    a(f"  scope: {rd['scope']}")
    a(f"  minimum overlap required to trust a comparison: {rd['min_overlap_trading_days']} trading days")
    a(f"  operative statistic: {rd['operative_statistic']}")
    a("")
    a("STEP 1 REPRODUCTION CHECK (this run's own BEFORE numbers vs Step 1's persisted numbers)")
    a("-" * 100)
    s1 = p["step1_reproduction_check"]
    a(f"  {'category':16s} {'step1 published':>16s} {'this run (before)':>18s} {'delta':>10s}")
    for label in ("bonds", "commodities", "fx", "country_valmom", "pooled"):
        a(f"  {label:16s} {s1['published_before'][label]:16.4f} {s1['measured_before'][label]:18.4f} "
          f"{s1['deltas'][label]:10.2e}")
    a(f"  tolerance {s1['tolerance']:.4f} -> "
      f"{'reproduced' if s1['reproduced_within_tolerance'] else 'MISMATCH -- see log/warnings'}")
    a("")
    a("CANDIDATE DECISIONS, BY CATEGORY")
    a("-" * 100)
    for label in ("fx", "country_valmom", "bonds", "commodities"):
        a(f"  [{label}]")
        for ticker, d in p["candidate_decisions"][label].items():
            recent = (
                f", recent-{p['redundancy_discipline']['recent_window_trading_days']}d "
                f"{d['recent_window_correlation']:.4f}" if d.get("recent_window_correlation") is not None else ""
            )
            if d["status"] == "excluded_redundant":
                a(f"    {ticker:6s} EXCLUDED (redundant): operative corr {d['max_correlation']:.4f} "
                  f"(full-window {d['full_window_correlation']:.4f}{recent}) vs {d['compared_against']} "
                  f"(over {d['overlap_days']} overlapping days)")
            elif d["status"] == "accepted":
                a(f"    {ticker:6s} accepted: operative corr {d['max_correlation']:.4f} "
                  f"(full-window {d['full_window_correlation']:.4f}{recent}) vs {d['compared_against']} "
                  f"(over {d['overlap_days']} overlapping days)")
            else:
                a(f"    {ticker:6s} {d['status']}")
    if p["fx_rejected_insufficient_data"]:
        a("  [fx, rejected before any correlation test -- insufficient data]")
        for ticker, reason in p["fx_rejected_insufficient_data"].items():
            a(f"    {ticker}: {reason}")
    a("")
    a(f"STALENESS/RECENCY CHECKS (threshold: {p['staleness_threshold_days']} calendar days)")
    a("-" * 100)
    for ticker, c in p["staleness_checks"].items():
        if c["ok"]:
            a(f"  {ticker:10s} OK    last priced {c['last']}, {c['n_rows']} rows, {c['days_stale']} days stale")
        else:
            a(f"  {ticker:10s} FAIL  {c.get('reason')}")
    a("")
    a("PER-CATEGORY EFFECTIVE BREADTH, BEFORE vs AFTER")
    a("-" * 100)
    a(f"{'category':16s} {'n before':>9s} {'eb before':>10s} {'n after':>8s} {'eb after':>9s} "
      f"{'window before':>27s} {'window after':>27s}")
    for label, v in p["per_category"].items():
        wb = f"{v['window_before'][0]}..{v['window_before'][1]}"
        wa = f"{v['window_after'][0]}..{v['window_after'][1]}"
        a(f"{label:16s} {v['n_nominal_before']:9d} {v['effective_breadth_before']:10.4f} "
          f"{v['n_nominal_after']:8d} {v['effective_breadth_after']:9.4f} {wb:>27s} {wa:>27s}")
    a("")
    a("WHAT THIS COSTS (sample-length trade-off from adding later-inception tickers)")
    a("-" * 100)
    for line in _wrap(
        "country_valmom's own before/after window shrinks the most (INDA's 2012-02-03 inception "
        "binds the AFTER window for that category alone) -- the per-category before/after numbers "
        "above are therefore not measured on identical sample lengths within country_valmom. The "
        "POOLED window (below) was already bound by commodities' 2011-11-15 CPER inception even "
        "BEFORE this expansion, so the pooled cost of including INDA is only the gap between that "
        "and INDA's own start, not the full 16-year gap country_valmom's own solo comparison shows.",
        96,
    ):
        a(f"  {line}")
    a("")
    a("TICKER OVERLAP ACROSS THE FOUR EXPANDED UNIVERSES")
    a("-" * 100)
    if p["ticker_overlaps"]:
        for t, names in p["ticker_overlaps"].items():
            a(f"  {t}: claimed by {names}")
    else:
        a("  none -- every accepted instrument identifier is unique across the four expanded universes")
    a("")
    a("THE POOLED NUMBER -- THE GATE THIS RUN EXISTS TO MEASURE")
    a("-" * 100)
    pl = p["pooled"]
    a(f"  nominal tickers pooled: {pl['n_nominal_before']} -> {pl['n_nominal_after']} "
      f"(+{pl['n_new_accepted']} accepted additions)")
    a(f"  common window before: {pl['common_window_before'][0]} .. {pl['common_window_before'][1]} "
      f"({pl['n_common_trading_days_before']} trading days)")
    a(f"  common window after:  {pl['common_window_after'][0]} .. {pl['common_window_after'][1]} "
      f"({pl['n_common_trading_days_after']} trading days)")
    a(f"  POOLED EFFECTIVE BREADTH BEFORE: {pl['effective_breadth_before']:.4f} of {pl['n_nominal_before']}")
    a(f"  POOLED EFFECTIVE BREADTH AFTER:  {pl['effective_breadth_after']:.4f} of {pl['n_nominal_after']}")
    a(f"    (independent re-derivation before: {pl['effective_breadth_before_independent']:.4f}, delta "
      f"{pl['independent_verification_delta_before']:.2e})")
    a(f"    (independent re-derivation after:  {pl['effective_breadth_after_independent']:.4f}, delta "
      f"{pl['independent_verification_delta_after']:.2e})")
    a("")
    a(f"  gate: >= {p['gate']['floor']:.0f} -> proceed; < {p['gate']['floor']:.0f} -> real futures pipeline "
      f"likely necessary (band named in Step 1's brief: {p['gate']['floor']:.0f}-{p['gate']['band_top']:.0f}+)")
    a("")
    a("BRANCH THIS NUMBER IMPLIES")
    a("-" * 100)
    for line in _wrap(p["branch_statement"], 96):
        a(f"  {line}")
    a("")
    a("INDEPENDENT VERIFICATION (CLAUDE.md 'never fabricate' cross-check)")
    a("-" * 100)
    v = p["verification"]
    for line in _wrap(
        "Every effective_breadth() call above (4 categories x before/after + pooled x before/after = "
        "10 calls) was independently re-derived via numpy.linalg.eigh on the same correlation matrix "
        "(effective_breadth() itself uses numpy.linalg.eigvalsh), sum(lambda)^2/sum(lambda^2) "
        "hand-typed fresh from the source formula. The run aborts rather than reporting a number if "
        "any delta exceeds tolerance.", 96,
    ):
        a(f"  {line}")
    a(f"  tolerance: {v['tolerance']:.0e}")
    a(f"  worst delta across all 10 calls: {v['worst_delta_any_call']:.2e}")
    a("")
    a("WHAT THIS RUN DOES NOT ESTABLISH")
    a("-" * 100)
    for line in _wrap(
        "This is a diagnostic of how many independent bets the FOUR EXPANDED categories' baskets "
        "contain together, not a backtest of any TSMOM signal, and not a decision about which "
        "specific TSMOM parameters to use. None of BONDS_UNIVERSE, COMMODITIES_UNIVERSE, FX_PAIRS or "
        "COUNTRY_ETF_TICKERS was modified -- every accepted new ticker lives only in this script's "
        "own NEW_*_CANDIDATES lists, additive to the four existing family modules.", 96,
    ):
        a(f"  {line}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
