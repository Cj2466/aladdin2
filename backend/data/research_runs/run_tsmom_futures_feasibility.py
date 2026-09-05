"""STEP 4 OF THE TSMOM UNIVERSE-VALIDATION PREP PLAN ("Option 2 feasibility"):
can this project get real futures data good enough to trust a TSMOM pass/fail
verdict on, and if so how would a continuous contract be constructed?

FEASIBILITY SCOPING ONLY. This run builds NO TSMOM signal, registers nothing,
modifies no family module, and does not commit this project to a futures
pipeline. It answers five questions and stops.

WHY THIS RUN EXISTS
====================
Step 1 (run_combined_universe_effective_breadth.py, merged) measured the
pooled effective breadth of the existing bonds+FX+commodities+country_valmom
ETF/cash universe at 7.10 of 43 nominal tickers, against a pre-declared floor
of 15. Step 3 (run_expand_tsmom_universe.py, merged) added 25 verified,
non-redundant ETF/cash instruments and reached only 8.11 of 68 -- and stated
why more of the same cannot fix it: "the dominant source of correlation is a
shared global-risk/equity factor that more ETFs of the same instrument types
cannot diversify away". Its own honest implication was that Option 2 -- real
futures, which span term structure, roll yield, storage and convenience yield
that ETF wrappers structurally cannot reach -- is likely necessary first.

This run tests whether Option 2 is actually AVAILABLE to this project, before
anyone spends effort on it.

============================================================================
THE FIVE QUESTIONS, AND THE SHORT ANSWERS THIS RUN MEASURED
============================================================================

Q1. WHAT FREE CONTINUOUS/ROLL-ADJUSTED FUTURES DATA CAN THIS PROJECT GET?
    Answer: none that is adequate. Yahoo (already wired up, yfinance) serves
    ~35 liquid `=F` continuous tickers with ~26 years of daily history, but
    they are RAW, UNADJUSTED FRONT-MONTH SPLICES. That was not assumed from
    the ticker's reputation -- it was PROVEN three independent ways below
    (PROOF_1/2/3). Every free alternative checked either no longer exists,
    is unverifiable from this environment, or is not a licensed roll-adjusted
    source. See DATA_SOURCES_CHECKED.

Q2. WHAT IS THE CORRECT, CITABLE CONSTRUCTION METHOD?
    Answer: Moskowitz/Ooi/Pedersen (2012) Section 2.1, p.231, quoted verbatim
    in MOP_2012_SECTION_2_1 below. Their convention avoids "back-adjustment"
    as a concept entirely: compound the daily return of the contract you
    actually HOLD. This run proves numerically (test + synthetic fixture)
    that it is EXACTLY EQUIVALENT to ratio/proportional back-adjustment, and
    that it is NOT equivalent to arithmetic/"Panama" back-adjustment.

Q3. HOW MANY MARKETS COULD REALISTICALLY BE ASSEMBLED?
    Answer: see CONTINUOUS_UNIVERSE_BY_ASSET_CLASS and the measured coverage
    table. The count is reported from live pulls, not asserted.

Q4. VALIDATED PROOF OF CONCEPT.
    Built and validated two ways -- synthetic-with-known-answer (below and in
    tests/test_tsmom_futures_feasibility.py) and against real ES contract
    data -- WITHOUT being turned into a pipeline.

Q5. VERDICT. See VERDICT_* below and the report's own section.

============================================================================
PROOF THAT YAHOO'S `=F` SERIES IS AN UNADJUSTED SPLICE (measured, not assumed)
============================================================================

PROOF_1 -- THE NEGATIVE-PRICE PRINT.
  CL=F carries Close = -37.630001 on 2020-04-20 and Low = -40.320000. That is
  the real settlement of the expiring May-2020 WTI contract. NO back-adjusted
  series can carry that value at that level: back-adjustment shifts or scales
  all history by the accumulated roll gaps, so the 2020 level in an adjusted
  series is not the as-traded level. Its presence is proof the series is
  as-traded front month, spliced. It also makes a RETURN series undefined
  through that date -- pct_change across a sign change is meaningless -- and
  this run measures CL=F's implied returns as -306.0% then -126.6% on the two
  days concerned.

PROOF_2 -- THE CONTRACT-IDENTITY MATCH.
  Yahoo also serves individual contract months for CURRENTLY-LISTED contracts
  (e.g. ESU26.CME, GCZ26.CMX, CLZ26.NYM). Comparing a `=F` splice against
  those, `=F` is found to be BYTE-EQUAL to one specific contract over a long
  contiguous block, then to switch to the next. ES=F equals ESU26.CME exactly
  on every one of the 54 trading days from 2026-06-22 to 2026-09-04, and
  differs before. That is what a splice is, observed directly.

PROOF_3 -- THE INJECTED ROLL RETURN.
  On the switch date the splice's own pct_change is (P_new / P_old_prev - 1),
  a return no holder of either contract earned. Measured at every empirically
  detected switch date that clears this run's own block guard: ES=F +0.827 pct
  pts and NQ=F +1.505 pct pts on 2026-06-22, ZN=F -0.269, 6E=F +0.142, and
  three near-zero cases in the metals. Cross-checked calendar-free against the
  CASH index (see CASH_BENCHMARK_METHOD): ES=F vs ^GSPC on 2026-06-22 gives
  d = +80.8bp against a robust daily sigma of 10.8bp (z = +7.5), with the
  neighbouring days at +4.6bp and +6.1bp.

  THE ARTIFACT IS NOT AN OUTLIER, AND THAT IS THE WORST PART. Measured in the
  proof of concept: on the roll date the correctly constructed ES series
  returned -0.3796% (robust z -0.70) and the naive splice returned +0.5283%
  (robust z +0.65). The splice's number is +0.9079 pct pts of pure fiction and
  it is STILL an unremarkable day for a 15%-vol instrument -- less extreme, on
  its own series, than the true return was on its own. So no outlier filter,
  winsorisation or jump screen can find it, let alone remove it. It is
  detectable only against an INDEPENDENT benchmark (the cash index, which
  exists for equity indices and does not exist for commodities), and it is
  systematic rather than random: across all 764 candidate roll dates in the
  ESU26/ESZ26 overlap the artifact was POSITIVE ON EVERY SINGLE ONE (share
  positive 1.000, mean +0.778 pct pts, range +0.024 to +1.604).

WHY PROOF_3's DAMAGE IS NOT REPAIRED BY "IT ALL CANCELS IN THE END"
-------------------------------------------------------------------
It very nearly does cancel at the level of a long-horizon endpoint, and that
is exactly what makes it dangerous rather than harmless. Compounding the
splice's daily pct_change telescopes to P_end/P_start, and the nearest-to-
expiry price series is MOP's own proxy for the SPOT price path (MOP Section
6.3: "prices are measured as the nearest-to-expiration futures price"). So
the splice reproduces the SPOT path and omits the ROLL RETURN, which is the
entire difference between spot and a futures position:

    MOP (2012) Section 6.3, p.247, quoted verbatim:
      "Futures return_{t-12,t} = Price change_{t-12,t} + Roll return_{t-12,t}"
      "In financial futures with little storage costs or convenience yield,
       the roll return is close to zero, but, in commodity markets, the roll
       return can be substantial."

A TSMOM signal does not read endpoints. It reads (a) the SIGN of a trailing
12-month return and (b) an ex-ante volatility estimate with a 60-day centre of
mass (MOP Eq. 1). A fabricated one-day jump corrupts both: it enters the
lookback window for a full year, and it enters the volatility estimate that
sets the position size. "The level is roughly right at the end" is not the
property this family needs.

HOW OFTEN, stated only as far as it was actually measured. This run does NOT
hard-code any exchange roll calendar, so it does not claim a roll frequency
from a contract specification. What it measured is the length of each
identity block (PROOF_2): ES=F and NQ=F each held one contract for 54
consecutive trading days and ZN=F for 53 -- consistent with roughly four
switches a year for those markets -- while the metals blocks ran 22 days and
the FX blocks 19 and 14. Block lengths are truncated by Yahoo's own purge
window, so they are a LOWER bound on the holding period and an UPPER bound on
the frequency; the honest summary is "at least several times a year in every
market measured, more often in the shorter-cycle ones", not a specific count.

============================================================================
WHY THIS PROJECT CANNOT SELF-BUILD A CORRECT SERIES FROM YAHOO EITHER
============================================================================
The obvious repair -- download the individual contract months and chain them
per MOP -- was tested and DOES NOT WORK, for one measured reason: YAHOO
PURGES EXPIRED CONTRACTS. Swept live (see EXPIRED_RETENTION):

  * ES quarterly contracts, 2015Q1..2026Q4 (48 symbols): 3 resolve. Two are
    currently listed (ESU26, ESZ26); the third, ESZ20, returns a ONE-ROW stub.
    So the number of genuinely expired ES contract months with usable history
    is ZERO out of 48.
  * GC even-month contracts 2015..2026 (72 symbols): 3 resolve, all of them
    currently listed or days-expired (GCZ25, GCV26, GCZ26). Same story.

The contracts that DO carry long histories are DEFERRED ones (CLZ26.NYM back
to 2017-11-21; NGZ26.NYM back to 2013-11-27), which is not a substitute: they
were not the front month on those historical dates and they were not
tradeable on them either. Measured median daily volume for CLZ26.NYM was 0
contracts in 2018 (250 of 251 days with zero volume) and 0 in 2020, reaching
92,140 only in 2026 as it approached the front. Backtesting a position in a
contract that had no volume is not a backtest.

CONSEQUENCE: from Yahoo, a correct historical continuous series cannot be
built at all -- not by taking the splice (wrong, PROOF_1/2/3) and not by
rebuilding it from contracts (the contracts are not retained). A FORWARD
collection programme, recording front-month contracts from today onward before
they expire, is possible and is noted as such; it produces no history now.

============================================================================
TWO MORE DATA-QUALITY DEFECTS FOUND WHILE MEASURING (not hypothetical)
============================================================================
DEFECT_A -- 6J=F CARRIES A 10x SCALE BREAK. Yahoo's JPY future prints
  0.007923 on 2001-12-13, then 0.000783 on 2001-12-17, then 0.007860 on
  2001-12-18. One day, off by a factor of ~10. Implied returns -90.0% then
  +903.8%. A 12-month TSMOM lookback would carry that contamination for a
  full year.
DEFECT_B -- THIS PROJECT'S OWN INGEST WOULD SILENTLY HIDE PROOF_1.
  price_store.drop_implausible keeps only rows with close > MIN_PLAUSIBLE_
  PRICE (1e-6), so routing CL=F through YFinanceProvider would DROP the
  2020-04-20 negative print rather than surface it, leaving a one-day hole
  and then computing a return straight across the gap. That is why every
  measurement in this run reads yfinance DIRECTLY rather than through this
  project's provider: the object under study is the vendor series as it
  actually is, before any of this project's cleaning. This is a finding about
  the existing pipeline's futures-readiness, logged, not fixed here.

============================================================================
THE RECOMMENDED CONSTRUCTION, AND WHY (Q2)
============================================================================
RECOMMENDED: MOP (2012) Section 2.1's own convention, implemented by
chained_contract_daily_returns() below. Quoted verbatim from the paper
(Journal of Financial Economics 104(2):228-250, Section 2.1 "Futures returns
data", p.231):

    "We construct a return series for each instrument as follows. Each day,
     we compute the daily excess return of the most liquid futures contract
     (typically the nearest or next nearest-to-delivery contract), and then
     compound the daily returns to a cumulative return index from which we
     can compute returns at any horizon."

Three things that sentence settles, and that this run does NOT decide for
itself:
  (i)  The daily return is computed WITHIN one contract. The splice boundary
       is never a return. This is why MOP need no back-adjustment step.
  (ii) "the most liquid futures contract (typically the nearest or next
       nearest-to-delivery contract)" is the selection rule. MOP report the
       robustness check themselves: "As a robustness test, we also use the
       'far' futures contract... for the commodity futures, time series
       momentum profits are in fact slightly stronger for the far contract,
       and, for the financial futures, time series momentum returns hardly
       change" (p.231).
  (iii) The return is already an EXCESS return, with no financing subtraction
       applied to it. MOP subtract the risk-free rate when they build a SPOT
       price change (Section 6.3: "Price change_{t-12,t} =
       (Price_t - Price_{t-12})/Price_{t-12} - r^f_{t-12,t}") and do not
       subtract it from the futures return in the same decomposition. A
       fully-collateralised futures position earns the collateral's rate plus
       the contract's price return, so the price return IS the excess return.

EQUIVALENT FALLBACK, PROVEN NUMERICALLY HERE RATHER THAN ASSERTED: ratio
(proportional) back-adjustment, ratio_back_adjusted_prices() below. Its
adjustment factor is derived independently (walking roll gaps backwards from
the last segment), and a test asserts its pct_change equals MOP's chained
returns to float tolerance. This matters because a price SERIES is sometimes
more convenient than a return series, and this shows the two are the same
object.

REJECTED, ALSO PROVEN NUMERICALLY: arithmetic / difference / "Panama"
back-adjustment, panama_back_adjusted_prices() below, kept ONLY so the test
suite can demonstrate that it does NOT reproduce the true returns. It
preserves price DIFFERENCES, not RATIOS, so every historical percentage
return is distorted. On this run's synthetic fixture, whose true day-1 return
is exactly 1.000000%, Panama yields 0.907441% -- a hand-checkable error.
Norgate Data (norgatedata.com/futurespackage.php, read 2026-09-05) states
its back-adjustment "is calculated arithmetically", i.e. this rejected form;
a buyer of that product must therefore use its UNADJUSTED series and chain
returns per MOP, not consume its back-adjusted prices as if they were a
return series. Recorded so a later paid-data decision does not walk into it.

============================================================================
WHAT THIS RUN DOES NOT ESTABLISH
============================================================================
  * It does not backtest TSMOM, on any universe, for any parameter.
  * It does not measure the effective breadth of a futures universe. That
    needs the data this run concludes is not freely available; the 7.10/8.11
    ETF numbers are NOT evidence about what a futures basket would score.
  * It does not decide the paid-data question. Per CLAUDE.md, the gap is
    logged in PENDING_PAID_DATA_DECISIONS.md and left for the repo owner.
  * The alternative-source survey is bounded by what this environment could
    reach. Nasdaq Data Link and Stooq both answered with bot-protection
    interstitials (Incapsula; a JS proof-of-work challenge) rather than data,
    so their CURRENT state is recorded as UNVERIFIED-FROM-HERE, never as
    "unavailable". That distinction is the whole point of the rule.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate (same pattern as
# run_combined_universe_effective_breadth.py and run_expand_tsmom_universe.py).
# Running this file by path puts data/research_runs/ on sys.path[0], NOT
# backend/, and this worktree's venv is a SYMLINK to the main worktree's venv,
# whose site-packages would otherwise resolve `app` to the MAIN worktree's
# backend/app -- silently measuring the wrong checkout's code.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The measurement would have used another checkout's code."
    )

import yfinance as yf  # noqa: E402

from app.services.market_data.price_store import MIN_PLAUSIBLE_PRICE  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr
)
log = logging.getLogger("tsmom_futures_feasibility")

RUN_DATE = "2026-09-05"
OUT_DIR = _BACKEND / "data" / "research_runs"
OUT_JSON = OUT_DIR / f"tsmom_futures_feasibility_{RUN_DATE}.json"
OUT_TXT = OUT_DIR / f"tsmom_futures_feasibility_{RUN_DATE}.txt"


# ---------------------------------------------------------------------------
# VERBATIM SOURCE QUOTES -- the citations this run's method rests on.
# Held as constants so the report prints the SOURCE, not a paraphrase of it.
# ---------------------------------------------------------------------------

MOP_2012_CITE = (
    "Moskowitz, Ooi & Pedersen (2012), 'Time Series Momentum', Journal of Financial "
    "Economics 104(2):228-250"
)

MOP_2012_SECTION_2_1 = (
    "We construct a return series for each instrument as follows. Each day, we compute the "
    "daily excess return of the most liquid futures contract (typically the nearest or next "
    "nearest-to-delivery contract), and then compound the daily returns to a cumulative "
    "return index from which we can compute returns at any horizon."
)

MOP_2012_SECTION_6_3_DECOMPOSITION = (
    "Futures return_{t-12,t} = Price change_{t-12,t} + Roll return_{t-12,t}"
)

MOP_2012_SECTION_6_3_MAGNITUDE = (
    "In financial futures with little storage costs or convenience yield, the roll return is "
    "close to zero, but, in commodity markets, the roll return can be substantial."
)

MOP_2012_SECTION_6_3_PRICE_BASIS = (
    "where prices are measured as the nearest-to-expiration futures price"
)

MOP_2012_FAR_CONTRACT_ROBUSTNESS = (
    "As a robustness test, we also use the 'far' futures contract (the next maturity after "
    "the most liquid one). For the commodity futures, time series momentum profits are in "
    "fact slightly stronger for the far contract, and, for the financial futures, time series "
    "momentum returns hardly change if we use far futures."
)

MOP_2012_EQUITY_CASH_CORRELATION = (
    "For the equity indexes, our return series are almost perfectly correlated with the "
    "corresponding returns of the underlying cash indexes in excess of the Treasury bill rate."
)

# MOP Eq. (1), p.234 -- reproduced ONLY to state what a TSMOM build would later
# need; this run does not implement or use it.
MOP_2012_EQ1_EX_ANTE_VOL = (
    "sigma_t^2 = 261 * sum_{i=0..inf} (1-delta) delta^i (r_{t-1-i} - rbar_t)^2, with delta "
    "chosen so that the centre of mass of the weights, sum (1-delta) delta^i i = "
    "delta/(1-delta), is 60 days (MOP 2012 Eq. 1, p.234)"
)


# ---------------------------------------------------------------------------
# THE UNIVERSE PROBED (Q3) -- liquid, long-history, 4 asset classes
# ---------------------------------------------------------------------------
# Chosen to mirror MOP's own four asset classes (commodities, equity indexes,
# bonds, currencies). NOT a proposed trading universe -- a coverage probe.
CONTINUOUS_UNIVERSE_BY_ASSET_CLASS: dict[str, list[str]] = {
    "equity_index": ["ES=F", "NQ=F", "YM=F", "RTY=F"],
    "government_bond": ["ZT=F", "ZF=F", "ZN=F", "ZB=F"],
    "currency": ["6E=F", "6J=F", "6B=F", "6A=F", "6C=F", "6S=F"],
    "commodity_energy": ["CL=F", "BZ=F", "NG=F", "HO=F", "RB=F"],
    "commodity_metal": ["GC=F", "SI=F", "HG=F", "PL=F", "PA=F"],
    "commodity_ag": ["ZC=F", "ZS=F", "ZW=F", "ZL=F", "ZM=F", "KC=F", "SB=F", "CT=F",
                     "LE=F", "HE=F"],
}

# Cash indices / spot rates used as ROLL-FREE benchmarks (see
# CASH_BENCHMARK_METHOD). Only the equity-index pairs are used for the headline
# detector: MOP's own p.231 sentence licenses the equity-index/cash-index
# comparison specifically, and the measured correlations below confirm it
# (~0.97) while Yahoo's spot FX series do NOT line up with its FX futures at
# all (corr 0.36 for EUR, 0.01 for JPY -- a timestamp/basis mismatch in Yahoo's
# own spot series, not evidence about the futures). Reported, not used.
CASH_BENCHMARK_PAIRS: list[tuple[str, str, str]] = [
    ("ES=F", "^GSPC", "S&P 500"),
    ("NQ=F", "^NDX", "Nasdaq 100"),
    ("YM=F", "^DJI", "Dow Jones Industrial Average"),
    ("RTY=F", "^RUT", "Russell 2000"),
]
FX_BENCHMARK_PAIRS_REPORTED_ONLY: list[tuple[str, str, str]] = [
    ("6E=F", "EURUSD=X", "EUR spot"),
    ("6J=F", "JPYUSD=X", "JPY spot"),
    ("6B=F", "GBPUSD=X", "GBP spot"),
]

CASH_BENCHMARK_METHOD = (
    "d_t = r(=F splice)_t - r(cash index)_t. MOP 2012 p.231 licenses the comparison directly: "
    "'For the equity indexes, our return series are almost perfectly correlated with the "
    "corresponding returns of the underlying cash indexes in excess of the Treasury bill rate.' "
    "The cash index has NO roll, so on an ordinary day d_t is small (basis drift plus the "
    "16:00 cash / 17:00 futures close-time mismatch), while on a splice day d_t jumps by the "
    "full basis between the outgoing and incoming contract. This detects roll artifacts over "
    "the whole history WITHOUT knowing any exchange roll calendar -- which matters because "
    "this run declines to hard-code an expiry rule it has not verified against the exchange."
)

# Individual contract months to sweep for the expired-contract retention test.
EXPIRED_RETENTION_SWEEP_YEARS = range(15, 27)
MONTH_CODE = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
              7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}

# A contract "resolves" the moment Yahoo returns one row, which flatters the
# retention picture: ESZ20.CME resolves with EXACTLY ONE row. A quarter of
# trading days is the floor for calling a series usable enough to chain. The
# threshold is generous on purpose -- the finding is that nothing expired
# survives at all, so it does not turn on where this line is drawn.
MIN_USABLE_CONTRACT_ROWS = 63

# Splice/contract pairs whose switch date this run detects and measures. Each
# is a `=F` splice plus one individual contract Yahoo still serves.
SWITCH_PROBE_PAIRS: list[tuple[str, str]] = [
    ("ES=F", "ESU26.CME"),
    ("NQ=F", "NQU26.CME"),
    ("ZN=F", "ZNU26.CBT"),
    ("GC=F", "GCZ25.CMX"),
    ("GC=F", "GCZ26.CMX"),
    ("SI=F", "SIZ25.CMX"),
    ("HG=F", "HGZ25.CMX"),
    ("6E=F", "6EZ25.CME"),
    ("6E=F", "6EU26.CME"),
]

# A "switch" is only believed when the splice matches the contract on a
# CONTIGUOUS RUN of at least this many trading days. A single coincidental
# exact price match is common in low-decimal markets (corn quoted to 0.25
# cents, crude to 0.01) and would otherwise be reported as a roll that never
# happened -- observed live for CL=F/CLV26.NYM and ZC=F/ZCU26.CBT during this
# run's development, which is why the guard exists at all.
MIN_SWITCH_BLOCK_TRADING_DAYS = 10

# Contracts used for the REAL-DATA proof of concept. ES is the most liquid
# futures contract in the world and both legs are currently listed with a
# multi-year overlap, so the construction can be exercised on real prices.
POC_NEAR_CONTRACT = "ESU26.CME"
POC_FAR_CONTRACT = "ESZ26.CME"
POC_CASH_INDEX = "^GSPC"
# Pre-declared BEFORE any basis between the two legs was measured: the one
# date inside the overlap that this run had already independently established
# (via detect_switch_blocks, PROOF_2) to be a real Yahoo roll date. Fixing it
# this way rather than picking a date after seeing the basis is what stops the
# single-roll illustration from being a cherry-pick. The full distribution over
# EVERY candidate roll date in the overlap is reported alongside it, so the
# choice carries no weight in the conclusion either way.
POC_ROLL_DATE = pd.Timestamp("2026-06-22")

# Deferred contracts whose volume history shows why a long deferred series is
# not a substitute for a front-month one.
DEFERRED_LIQUIDITY_PROBE = ["CLZ26.NYM", "GCZ26.CMX", "GCZ27.CMX", "ESZ26.CME", "NGZ26.NYM"]

# A single-day move this large in a front-month futures series is a scale break
# or a sign change, not a market event: no liquid futures market moves 50% in a
# day under normal contract terms. Used as a screen, and every hit is reported
# individually rather than counted, so a real event could not hide inside it.
SCALE_BREAK_ABS_RETURN = 0.50

# Robust-z threshold for flagging a day in the cash-benchmark detector. 5 is
# deliberately far looser than the 20 an initial pass used: the real ES roll
# artifact measured z = +7.5, so a threshold of 20 would have MISSED the very
# thing the detector exists to find. Recorded because tightening it back would
# silently restore that blind spot.
CASH_BENCHMARK_Z_THRESHOLD = 5.0

# Tolerance for the synthetic known-answer validation. These are exact
# closed-form values derived by hand in the fixture's own docstring, compared
# against float64 arithmetic -- so the bar is numerical noise, not "close".
SYNTHETIC_TOLERANCE = 1e-12


# ---------------------------------------------------------------------------
# THE CONSTRUCTION -- pure functions, no network, no clock (Q2/Q4)
# ---------------------------------------------------------------------------


def chained_contract_daily_returns(
    closes_by_contract: dict[str, pd.Series], holding: pd.Series
) -> pd.Series:
    """MOP (2012) Section 2.1, p.231, implemented literally:

        "Each day, we compute the daily excess return of the most liquid
         futures contract (typically the nearest or next nearest-to-delivery
         contract), and then compound the daily returns to a cumulative return
         index from which we can compute returns at any horizon."

    `holding` maps each date t to the contract symbol whose return over
    (t-1, t] is earned. Both prices in every ratio come from the SAME contract,
    so a splice boundary is NEVER a return -- which is precisely why MOP need
    no back-adjustment step and why this project should not invent one.

    A ROLL THEREFORE REQUIRES AN OVERLAP DAY on which the incoming contract is
    already quoted: to earn the incoming contract's return on the roll date,
    its previous close must exist. This raises rather than silently producing a
    NaN, because a silently-NaN roll day is exactly the failure this whole run
    is about.

    The first date carries NaN (no previous close), matching pandas'
    pct_change() convention so the two are directly comparable in tests."""
    dates = list(holding.index)
    out = pd.Series(np.nan, index=holding.index, dtype=float)
    for i in range(1, len(dates)):
        now, prev = dates[i], dates[i - 1]
        symbol = holding.iloc[i]
        series = closes_by_contract.get(symbol)
        if series is None:
            raise KeyError(f"holding names contract {symbol!r} with no price series")
        if now not in series.index or prev not in series.index:
            raise ValueError(
                f"contract {symbol!r} is not priced on both {prev.date()} and {now.date()}; a "
                "roll needs an overlap day on which the incoming contract is already quoted"
            )
        out.iloc[i] = float(series.loc[now]) / float(series.loc[prev]) - 1.0
    return out


def ratio_back_adjusted_prices(
    closes_by_contract: dict[str, pd.Series], holding: pd.Series
) -> pd.Series:
    """Ratio (proportional) back-adjustment -- the standard practitioner form,
    derived here INDEPENDENTLY of chained_contract_daily_returns so that the
    two agreeing is evidence rather than a tautology.

    Walking backwards from the final segment, each earlier segment is scaled by
    k = P_incoming(d_prev) / P_outgoing(d_prev), where d_prev is the last date
    the outgoing contract was held. Algebraically this makes the adjusted
    series' pct_change equal the chained within-contract return on every date,
    including the roll date:

        A(d)/A(d_prev) = P_new(d) / (P_old(d_prev) * k)
                       = P_new(d) / P_new(d_prev)

    which is the incoming contract's OWN return -- MOP's quantity exactly. The
    test asserts this equality numerically rather than trusting the derivation.

    Scaling (not shifting) is what preserves percentage returns; see
    panama_back_adjusted_prices for the form that does not."""
    dates = list(holding.index)
    segments: list[tuple[str, int, int]] = []
    start = 0
    for i in range(1, len(dates) + 1):
        if i == len(dates) or holding.iloc[i] != holding.iloc[start]:
            segments.append((holding.iloc[start], start, i - 1))
            start = i

    factors = [1.0] * len(segments)
    for s in range(len(segments) - 2, -1, -1):
        outgoing, _, out_end = segments[s]
        incoming = segments[s + 1][0]
        d_prev = dates[out_end]
        p_out = float(closes_by_contract[outgoing].loc[d_prev])
        p_in = float(closes_by_contract[incoming].loc[d_prev])
        factors[s] = factors[s + 1] * (p_in / p_out)

    values = np.empty(len(dates), dtype=float)
    for (symbol, lo, hi), factor in zip(segments, factors):
        for i in range(lo, hi + 1):
            values[i] = float(closes_by_contract[symbol].loc[dates[i]]) * factor
    return pd.Series(values, index=holding.index)


def panama_back_adjusted_prices(
    closes_by_contract: dict[str, pd.Series], holding: pd.Series
) -> pd.Series:
    """Arithmetic / difference / "Panama canal" back-adjustment -- REJECTED for
    this project, implemented ONLY so the test suite can demonstrate that it
    fails to reproduce the true returns rather than asserting that it does.

    Each earlier segment is SHIFTED by g = P_incoming(d_prev) - P_outgoing(d_prev)
    instead of scaled. That preserves price DIFFERENCES and destroys price
    RATIOS, so every historical percentage return is wrong: on this run's
    synthetic fixture the true day-1 return is exactly 1.000000% and this
    returns 0.907441%. It can also drive deep history negative, at which point
    a return is not merely wrong but undefined.

    Named here because a paid vendor may ship this form as its default:
    Norgate Data states its back-adjustment "is calculated arithmetically"
    (norgatedata.com/futurespackage.php, read 2026-09-05). A buyer must chain
    that vendor's UNADJUSTED series per MOP rather than consume its
    back-adjusted prices as a return series."""
    dates = list(holding.index)
    segments: list[tuple[str, int, int]] = []
    start = 0
    for i in range(1, len(dates) + 1):
        if i == len(dates) or holding.iloc[i] != holding.iloc[start]:
            segments.append((holding.iloc[start], start, i - 1))
            start = i

    offsets = [0.0] * len(segments)
    for s in range(len(segments) - 2, -1, -1):
        outgoing, _, out_end = segments[s]
        incoming = segments[s + 1][0]
        d_prev = dates[out_end]
        p_out = float(closes_by_contract[outgoing].loc[d_prev])
        p_in = float(closes_by_contract[incoming].loc[d_prev])
        offsets[s] = offsets[s + 1] + (p_in - p_out)

    values = np.empty(len(dates), dtype=float)
    for (symbol, lo, hi), offset in zip(segments, offsets):
        for i in range(lo, hi + 1):
            values[i] = float(closes_by_contract[symbol].loc[dates[i]]) + offset
    return pd.Series(values, index=holding.index)


def naive_spliced_prices(
    closes_by_contract: dict[str, pd.Series], holding: pd.Series
) -> pd.Series:
    """What Yahoo's `=F` series is: each date carries the held contract's own
    as-traded price, with NO adjustment of any kind across the boundary. Its
    pct_change on the roll date is (P_new(d) / P_old(d_prev) - 1) -- a return
    no holder of either contract earned. Implemented so the artifact can be
    measured against the correct construction rather than described."""
    dates = list(holding.index)
    values = [float(closes_by_contract[holding.iloc[i]].loc[dates[i]]) for i in range(len(dates))]
    return pd.Series(values, index=holding.index)


def roll_artifact_per_date(
    closes_by_contract: dict[str, pd.Series], holding: pd.Series
) -> pd.Series:
    """naive splice return minus the true chained return, per date. Zero
    everywhere except roll dates; on a roll date it is the injected artifact,
    which is MOP's roll return with the sign flipped (the splice omits the roll
    return, so its return exceeds the true one by exactly that amount)."""
    naive = naive_spliced_prices(closes_by_contract, holding).pct_change()
    true = chained_contract_daily_returns(closes_by_contract, holding)
    return naive - true


def detect_switch_blocks(
    splice: pd.Series, contract: pd.Series, *, min_block: int = MIN_SWITCH_BLOCK_TRADING_DAYS
) -> list[dict[str, Any]]:
    """PROOF_2's detector: find contiguous runs of dates on which a `=F` splice
    is EXACTLY equal to one individual contract, i.e. the window over which the
    splice IS that contract.

    Exact equality (not a tolerance) is the right test: a splice does not
    approximate its constituent, it republishes it. Runs shorter than
    `min_block` are discarded as coincidental price collisions -- in
    low-decimal markets two different contract months genuinely print the same
    close now and then, and treating that as a roll manufactures rolls that
    never happened."""
    joined = pd.concat([splice.rename("splice"), contract.rename("contract")], axis=1).dropna()
    if joined.empty:
        return []
    equal = (joined["splice"] - joined["contract"]).abs() == 0.0
    blocks: list[dict[str, Any]] = []
    run_start: int | None = None
    positions = list(range(len(joined)))
    for i in positions:
        if equal.iloc[i] and run_start is None:
            run_start = i
        if (not equal.iloc[i] or i == positions[-1]) and run_start is not None:
            run_end = i if (equal.iloc[i] and i == positions[-1]) else i - 1
            length = run_end - run_start + 1
            if length >= min_block:
                blocks.append(
                    {
                        "first_date": str(joined.index[run_start].date()),
                        "last_date": str(joined.index[run_end].date()),
                        "n_trading_days": int(length),
                    }
                )
            run_start = None
    return blocks


def annualized_volatility(daily_returns: pd.Series, periods_per_year: int = 252) -> float:
    """Plain annualised sample standard deviation of daily returns. Used only
    as an ORDER-OF-MAGNITUDE sanity check ("does this look like a real equity
    index, or like noise"), never as an input to any decision here. MOP's own
    ex-ante estimator is the exponentially-weighted Eq. (1) quoted in
    MOP_2012_EQ1_EX_ANTE_VOL, deliberately NOT implemented in this run: this
    run does not build a TSMOM signal, and implementing its volatility model
    would be the first step of doing so."""
    clean = daily_returns.dropna()
    if len(clean) < 2:
        return float("nan")
    return float(clean.std(ddof=1) * np.sqrt(periods_per_year))


# ---------------------------------------------------------------------------
# SYNTHETIC KNOWN-ANSWER FIXTURE (Q4a) -- the CLAUDE.md formula rule
# ---------------------------------------------------------------------------


def synthetic_two_contract_roll() -> dict[str, Any]:
    """A two-contract roll whose every answer is derivable BY HAND, so the
    implementation is checked against arithmetic rather than against itself.

    CONSTRUCTION. One true underlying path U over days 0..5:
        U = [100, 101, 102, 103, 104, 105]
    Contract A is quoted on days 0..3 at exactly U:
        A = [100, 101, 102, 103]
    Contract B is quoted on days 1..5 at exactly 1.10 * U, i.e. a constant
    proportional basis of +10%:
        B = [111.1, 112.2, 113.3, 114.4, 115.5]
    A is held for the returns on days 1 and 2; the roll happens at the close of
    day 2, so B is held for the returns on days 3, 4 and 5. Day 2 is the
    overlap day on which both are quoted, which is what makes the roll legal.

    THE KNOWN TRUE ANSWERS, all exact:

      1. Chained daily returns equal U's OWN daily returns exactly, because
         B's constant 1.10 factor cancels inside every within-B ratio:
             day1 101/100 - 1,  day2 102/101 - 1,  day3 103/102 - 1,
             day4 104/103 - 1,  day5 105/104 - 1
      2. Cumulative chained return over days 0..5 = 105/100 - 1 = 0.05 EXACTLY.
      3. Ratio back-adjusted prices = [110, 111.1, 112.2, 113.3, 114.4, 115.5]
         (segment A scaled by k = B(day2)/A(day2) = 112.2/102 = 1.10 exactly),
         whose total return is 115.5/110 - 1 = 0.05 -- the same 5%.
      4. The NAIVE SPLICE is [100, 101, 102, 113.3, 114.4, 115.5]. Its total
         return is 115.5/100 - 1 = 0.155, i.e. the true 5% inflated by exactly
         the 10% basis: 1.155 / 1.05 = 1.10 EXACTLY.
      5. The injected artifact on the roll date is, in closed form,
             B(3)/A(2) - B(3)/B(2)
               = 113.3 * (112.2 - 102) / (102 * 112.2)
               = 113.3 * 10.2 / 11444.4
               = 1155.66 / 11444.4
               = 0.100980392156862745...
      6. PANAMA (arithmetic) adjustment shifts segment A by
         g = B(day2) - A(day2) = 112.2 - 102 = 10.2, giving
         [110.2, 111.2, 112.2, ...]. Its day-1 return is 111.2/110.2 - 1 =
         0.009074410163339... which is NOT the true 0.01 -- the demonstration
         that difference-adjustment does not preserve returns.

    Every one of those six is checked, both here (so a live run aborts) and in
    tests/test_tsmom_futures_feasibility.py (so a regression is caught without
    a network call)."""
    days = pd.date_range("2020-01-01", periods=6, freq="D")
    underlying = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    contract_a = pd.Series(underlying[:4], index=days[:4])
    contract_b = pd.Series([1.10 * u for u in underlying[1:]], index=days[1:])
    holding = pd.Series(["A", "A", "A", "B", "B", "B"], index=days)
    return {
        "closes_by_contract": {"A": contract_a, "B": contract_b},
        "holding": holding,
        "expected_daily_returns": [
            np.nan, 101 / 100 - 1, 102 / 101 - 1, 103 / 102 - 1, 104 / 103 - 1, 105 / 104 - 1
        ],
        "expected_cumulative_return": 105.0 / 100.0 - 1.0,
        "expected_ratio_adjusted_prices": [110.0, 111.1, 112.2, 113.3, 114.4, 115.5],
        "expected_naive_splice_total_return": 115.5 / 100.0 - 1.0,
        "expected_roll_artifact": 113.3 * (112.2 - 102.0) / (102.0 * 112.2),
        "expected_panama_day1_return": 111.2 / 110.2 - 1.0,
        "basis": 0.10,
    }


def validate_against_synthetic() -> dict[str, Any]:
    """Run every known-answer check in synthetic_two_contract_roll and return
    the measured deltas. The caller ABORTS the whole run on any failure --
    a construction that cannot reproduce arithmetic must not be pointed at real
    money markets, and a report that quietly noted the failure would be worse
    than no report."""
    fixture = synthetic_two_contract_roll()
    closes, holding = fixture["closes_by_contract"], fixture["holding"]

    returns = chained_contract_daily_returns(closes, holding)
    ratio = ratio_back_adjusted_prices(closes, holding)
    panama = panama_back_adjusted_prices(closes, holding)
    naive = naive_spliced_prices(closes, holding)
    artifact = roll_artifact_per_date(closes, holding)

    cumulative = float((1.0 + returns.dropna()).prod() - 1.0)
    ratio_total = float(ratio.iloc[-1] / ratio.iloc[0] - 1.0)
    naive_total = float(naive.iloc[-1] / naive.iloc[0] - 1.0)

    checks = {
        "chained_daily_returns_match_hand_derived": float(
            np.nanmax(np.abs(returns.to_numpy() - np.array(fixture["expected_daily_returns"])))
        ),
        "chained_cumulative_return_is_exactly_5pct": abs(
            cumulative - fixture["expected_cumulative_return"]
        ),
        "ratio_adjusted_prices_match_hand_derived": float(
            np.max(np.abs(ratio.to_numpy() - np.array(fixture["expected_ratio_adjusted_prices"])))
        ),
        # THE EQUIVALENCE CLAIM, proven rather than asserted: ratio
        # back-adjustment's pct_change IS MOP's chained return, on every date.
        "ratio_adjusted_pct_change_equals_chained_returns": float(
            np.nanmax(np.abs(ratio.pct_change().to_numpy() - returns.to_numpy()))
        ),
        "ratio_adjusted_total_return_is_exactly_5pct": abs(
            ratio_total - fixture["expected_cumulative_return"]
        ),
        "naive_splice_total_return_matches_hand_derived": abs(
            naive_total - fixture["expected_naive_splice_total_return"]
        ),
        # The splice's total return is the true one inflated by exactly the basis.
        "naive_splice_inflated_by_exactly_the_basis": abs(
            (1.0 + naive_total) / (1.0 + cumulative) - (1.0 + fixture["basis"])
        ),
        "roll_artifact_matches_closed_form": abs(
            float(artifact.iloc[3]) - fixture["expected_roll_artifact"]
        ),
        "roll_artifact_is_zero_on_non_roll_days": float(
            np.nanmax(np.abs(artifact.drop(artifact.index[3]).to_numpy()))
        ),
        "panama_day1_return_matches_hand_derived": abs(
            float(panama.pct_change().iloc[1]) - fixture["expected_panama_day1_return"]
        ),
    }
    # Not a tolerance check -- an assertion that Panama really does DIFFER from
    # the truth. If this ever became ~0, the "rejected" recommendation would be
    # unfounded and the report must not print it.
    panama_error = abs(float(panama.pct_change().iloc[1]) - (101.0 / 100.0 - 1.0))

    failures = {k: v for k, v in checks.items() if not (v <= SYNTHETIC_TOLERANCE)}
    return {
        "tolerance": SYNTHETIC_TOLERANCE,
        "checks": {k: float(v) for k, v in checks.items()},
        "worst_delta": float(max(checks.values())),
        "failures": sorted(failures),
        "panama_day1_error_vs_truth": float(panama_error),
        "panama_demonstrably_differs": bool(panama_error > 1e-6),
        "measured_cumulative_return": cumulative,
        "measured_naive_splice_total_return": naive_total,
        "measured_roll_artifact": float(artifact.iloc[3]),
    }


# ---------------------------------------------------------------------------
# DATA ACCESS -- deliberately RAW yfinance, see DEFECT_B in the module docstring
# ---------------------------------------------------------------------------


def _history(symbol: str) -> pd.DataFrame | None:
    try:
        frame = yf.Ticker(symbol).history(period="max", auto_adjust=False)
    except Exception:  # noqa: BLE001 -- one unresolvable symbol out of a 100+ symbol
        # sweep must return "no data" and let the sweep continue; yfinance raises a
        # different type for a bad ticker, a delisted one and a transient network
        # failure, and for a COVERAGE probe all three mean the same thing.
        return None
    if frame is None or frame.empty:
        return None
    frame = frame.copy()
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def close_series(symbol: str) -> pd.Series | None:
    frame = _history(symbol)
    return None if frame is None else frame["Close"].astype(float)


def volume_series(symbol: str) -> pd.Series | None:
    frame = _history(symbol)
    return None if frame is None else frame["Volume"].astype(float)


# ---------------------------------------------------------------------------
# PROBES
# ---------------------------------------------------------------------------


def probe_continuous_coverage() -> dict[str, Any]:
    """Q3: what `=F` continuous coverage actually exists, measured."""
    per_ticker: dict[str, Any] = {}
    for asset_class, tickers in CONTINUOUS_UNIVERSE_BY_ASSET_CLASS.items():
        for ticker in tickers:
            series = close_series(ticker)
            per_ticker[ticker] = {
                "asset_class": asset_class,
                "resolved": series is not None,
                "n_rows": 0 if series is None else int(len(series)),
                "start": None if series is None else str(series.index.min().date()),
                "end": None if series is None else str(series.index.max().date()),
            }
            log.info("coverage %s -> %s", ticker, per_ticker[ticker]["n_rows"])
    resolved = [v for v in per_ticker.values() if v["resolved"]]
    classes = sorted({v["asset_class"] for v in resolved})
    return {
        "per_ticker": per_ticker,
        "n_probed": len(per_ticker),
        "n_resolved": len(resolved),
        "n_asset_classes_with_coverage": len(classes),
        "asset_classes_with_coverage": classes,
        "min_history_start": min((v["start"] for v in resolved), default=None),
        "max_history_start": max((v["start"] for v in resolved), default=None),
    }


def probe_scale_breaks() -> dict[str, Any]:
    """DEFECT_A / PROOF_1: single-day moves too large to be a market event."""
    hits: list[dict[str, Any]] = []
    negative_price_tickers: list[dict[str, Any]] = []
    all_tickers = [t for group in CONTINUOUS_UNIVERSE_BY_ASSET_CLASS.values() for t in group]
    for ticker in all_tickers:
        series = close_series(ticker)
        if series is None:
            continue
        negatives = series[series <= MIN_PLAUSIBLE_PRICE]
        if len(negatives):
            negative_price_tickers.append(
                {
                    "ticker": ticker,
                    "n_rows_at_or_below_min_plausible_price": int(len(negatives)),
                    "dates": [str(d.date()) for d in negatives.index[:5]],
                    "values": [float(v) for v in negatives.to_numpy()[:5]],
                }
            )
        returns = series.pct_change().dropna()
        extreme = returns[returns.abs() > SCALE_BREAK_ABS_RETURN]
        for when, value in extreme.items():
            hits.append({"ticker": ticker, "date": str(when.date()), "return": float(value)})
    return {
        "threshold_abs_return": SCALE_BREAK_ABS_RETURN,
        "hits": hits,
        "n_hits": len(hits),
        "min_plausible_price": float(MIN_PLAUSIBLE_PRICE),
        "tickers_with_rows_this_projects_ingest_would_drop": negative_price_tickers,
    }


def probe_expired_contract_retention() -> dict[str, Any]:
    """The finding that closes off self-building a correct series from Yahoo."""
    results: dict[str, Any] = {}
    for root, exchange, months in (("ES", "CME", (3, 6, 9, 12)),
                                   ("GC", "CMX", (2, 4, 6, 8, 10, 12))):
        probed, resolved = [], []
        for year in EXPIRED_RETENTION_SWEEP_YEARS:
            for month in months:
                symbol = f"{root}{MONTH_CODE[month]}{year:02d}.{exchange}"
                probed.append(symbol)
                series = close_series(symbol)
                if series is not None:
                    resolved.append(
                        {
                            "symbol": symbol,
                            "n_rows": int(len(series)),
                            "start": str(series.index.min().date()),
                            "end": str(series.index.max().date()),
                        }
                    )
                    log.info("retention %s -> %d rows", symbol, len(series))
        # "Resolved" overstates the case, so the sharper number is reported
        # alongside it: ESZ20 resolves with a SINGLE row, which is a stub, not
        # a price history anyone could chain. A contract is only counted as
        # usable if it carries at least a quarter of trading days.
        usable = [c for c in resolved if c["n_rows"] >= MIN_USABLE_CONTRACT_ROWS]
        results[root] = {
            "exchange": exchange,
            "n_probed": len(probed),
            "n_resolved": len(resolved),
            "n_resolved_with_usable_history": len(usable),
            "min_usable_contract_rows": MIN_USABLE_CONTRACT_ROWS,
            "resolved": resolved,
        }
    return results


def probe_switch_dates_and_artifacts() -> dict[str, Any]:
    """PROOF_2 and PROOF_3 together: find where each splice IS a given contract,
    then measure what the splice's own pct_change did on the day it switched in.

    The artifact is computed the direct way -- splice return minus the incoming
    contract's OWN return on the same date -- which needs no roll calendar and
    no assumption about which contract the splice was on beforehand."""
    out: list[dict[str, Any]] = []
    for splice_symbol, contract_symbol in SWITCH_PROBE_PAIRS:
        splice = close_series(splice_symbol)
        contract = close_series(contract_symbol)
        if splice is None or contract is None:
            out.append({"splice": splice_symbol, "contract": contract_symbol, "resolved": False})
            continue
        blocks = detect_switch_blocks(splice, contract)
        measured = []
        for block in blocks:
            switch_date = pd.Timestamp(block["first_date"])
            s_pos = list(splice.index).index(switch_date)
            c_pos = list(contract.index).index(switch_date)
            if s_pos == 0 or c_pos == 0:
                continue
            splice_return = float(splice.iloc[s_pos] / splice.iloc[s_pos - 1] - 1.0)
            contract_return = float(contract.iloc[c_pos] / contract.iloc[c_pos - 1] - 1.0)
            measured.append(
                {
                    "switch_date": block["first_date"],
                    "block_trading_days": block["n_trading_days"],
                    "prior_date": str(splice.index[s_pos - 1].date()),
                    "splice_prev_close": float(splice.iloc[s_pos - 1]),
                    "contract_prev_close": float(contract.iloc[c_pos - 1]),
                    "basis_pct": float(
                        100.0 * (contract.iloc[c_pos - 1] / splice.iloc[s_pos - 1] - 1.0)
                    ),
                    "splice_return_pct": 100.0 * splice_return,
                    "contract_own_return_pct": 100.0 * contract_return,
                    "artifact_pct_points": 100.0 * (splice_return - contract_return),
                }
            )
        out.append(
            {
                "splice": splice_symbol,
                "contract": contract_symbol,
                "resolved": True,
                "min_block_trading_days": MIN_SWITCH_BLOCK_TRADING_DAYS,
                "n_blocks": len(blocks),
                "switches": measured,
            }
        )
        log.info("switch probe %s/%s -> %d block(s)", splice_symbol, contract_symbol, len(blocks))
    return {"pairs": out}


def probe_cash_benchmark_detector() -> dict[str, Any]:
    """The calendar-free roll detector described in CASH_BENCHMARK_METHOD."""

    def one(fut: str, cash: str, label: str) -> dict[str, Any] | None:
        f, c = close_series(fut), close_series(cash)
        if f is None or c is None:
            return None
        joined = pd.concat(
            [f.pct_change().rename("fut"), c.pct_change().rename("cash")], axis=1
        ).dropna()
        if joined.empty:
            return None
        diff = joined["fut"] - joined["cash"]
        scale = float((diff - diff.median()).abs().median() * 1.4826)
        z = (diff - diff.median()) / scale
        flagged = diff[z.abs() > CASH_BENCHMARK_Z_THRESHOLD]
        quarterly_months = [3, 6, 9, 12]
        in_quarterly = flagged[flagged.index.month.isin(quarterly_months)]
        third_friday_week = in_quarterly[
            (in_quarterly.index.day >= 18) & (in_quarterly.index.day <= 24)
        ]
        return {
            "futures": fut,
            "cash": cash,
            "label": label,
            "n_days": int(len(joined)),
            "window_start": str(joined.index.min().date()),
            "window_end": str(joined.index.max().date()),
            "return_correlation": float(joined["fut"].corr(joined["cash"])),
            "robust_sigma_bp": 1e4 * scale,
            "n_flagged": int(len(flagged)),
            "flagged_per_year": float(len(flagged) / (len(joined) / 252.0)),
            "share_of_flags_in_quarterly_months": float(
                len(in_quarterly) / len(flagged)) if len(flagged) else float("nan"),
            "unconditional_share_of_quarterly_months": float(
                np.mean(joined.index.month.isin(quarterly_months))),
            "share_of_quarterly_flags_in_days_18_to_24": float(
                len(third_friday_week) / len(in_quarterly)) if len(in_quarterly) else float("nan"),
            "unconditional_share_of_days_18_to_24": float(
                np.mean((joined.index.day >= 18) & (joined.index.day <= 24))),
        }

    equity = [r for r in (one(*p) for p in CASH_BENCHMARK_PAIRS) if r is not None]

    # The one verified roll date, examined day by day in every equity pair.
    verified: list[dict[str, Any]] = []
    for fut, cash, _label in CASH_BENCHMARK_PAIRS:
        f, c = close_series(fut), close_series(cash)
        if f is None or c is None:
            continue
        joined = pd.concat(
            [f.pct_change().rename("fut"), c.pct_change().rename("cash")], axis=1
        ).dropna()
        if POC_ROLL_DATE not in joined.index:
            continue
        diff = joined["fut"] - joined["cash"]
        scale = float((diff - diff.median()).abs().median() * 1.4826)
        row = joined.loc[POC_ROLL_DATE]
        verified.append(
            {
                "futures": fut,
                "date": str(POC_ROLL_DATE.date()),
                "futures_return_pct": float(100.0 * row["fut"]),
                "cash_return_pct": float(100.0 * row["cash"]),
                "d_bp": float(1e4 * (row["fut"] - row["cash"])),
                "robust_z": float((row["fut"] - row["cash"] - diff.median()) / scale),
            }
        )

    fx_reported_only = [r for r in (one(*p) for p in FX_BENCHMARK_PAIRS_REPORTED_ONLY)
                        if r is not None]
    return {
        "method": CASH_BENCHMARK_METHOD,
        "z_threshold": CASH_BENCHMARK_Z_THRESHOLD,
        "equity_index_pairs": equity,
        "on_the_verified_roll_date": verified,
        "fx_pairs_reported_only": fx_reported_only,
    }


def probe_deferred_liquidity() -> dict[str, Any]:
    """Why a deferred contract's long history is not a usable substitute."""
    out: list[dict[str, Any]] = []
    for symbol in DEFERRED_LIQUIDITY_PROBE:
        vol = volume_series(symbol)
        if vol is None:
            continue
        by_year = []
        for year in sorted({int(y) for y in vol.index.year}):
            slice_ = vol[vol.index.year == year]
            by_year.append(
                {
                    "year": year,
                    "n_days": int(len(slice_)),
                    "median_daily_volume": float(np.median(slice_.to_numpy())),
                    "zero_volume_days": int((slice_ == 0).sum()),
                }
            )
        out.append(
            {
                "symbol": symbol,
                "start": str(vol.index.min().date()),
                "end": str(vol.index.max().date()),
                "n_rows": int(len(vol)),
                "by_year": by_year,
            }
        )
    return {"contracts": out}


def proof_of_concept_real_pair() -> dict[str, Any]:
    """Q4b: run the recommended construction on REAL contract prices, and check
    the result against something independently observable.

    Two independent real-data checks, neither of which can be satisfied by an
    implementation that merely returns its own input:
      (1) NO ARTIFICIAL JUMP, AND -- THE FINDING THAT MATTERS MORE -- THE
          SPLICE'S JUMP IS NOT DETECTABLE AS ONE. The constructed series takes
          its roll-date return entirely from the incoming contract, so it has
          no artifact by construction. The naive splice's roll-date return
          differs from it by the full basis. A first draft of this run expected
          the splice's roll day to stand out as a statistical outlier and said
          so; MEASUREMENT REFUTED THAT and the claim was removed. Both series'
          roll-date returns are ordinary days by robust z-score, and the
          splice's is the LESS extreme of the two. A ~+0.9 pct pt fabrication
          hides inside the ordinary daily noise of a 15%-vol instrument. The
          consequence is the one that matters for this project: no outlier
          filter, winsorisation or jump screen can find the artifact, so
          "clean the data first" is not an available repair. It shows up only
          against an INDEPENDENT benchmark -- which exists for equity indices
          (the cash index) and does not exist for commodities.
      (2) IT MUST LOOK LIKE THE MARKET IT CLAIMS TO BE. The constructed ES
          series' annualised volatility and its return correlation against the
          S&P 500 cash index must be those of a real large-cap equity index,
          not of noise.
    Plus the full distribution of the roll artifact over EVERY candidate roll
    date in the overlap, so the single pre-declared date carries no weight --
    and so the systematic SIGN of the artifact is visible, which is what makes
    it a bias rather than a nuisance."""
    near = close_series(POC_NEAR_CONTRACT)
    far = close_series(POC_FAR_CONTRACT)
    cash = close_series(POC_CASH_INDEX)
    if near is None or far is None:
        return {"resolved": False}

    common = near.index.intersection(far.index).sort_values()
    if POC_ROLL_DATE not in common:
        return {"resolved": False, "reason": "pre-declared roll date outside the overlap"}

    closes = {POC_NEAR_CONTRACT: near, POC_FAR_CONTRACT: far}
    holding = pd.Series(
        [POC_NEAR_CONTRACT if d < POC_ROLL_DATE else POC_FAR_CONTRACT for d in common],
        index=common,
    )
    chained = chained_contract_daily_returns(closes, holding)
    adjusted = ratio_back_adjusted_prices(closes, holding)
    naive = naive_spliced_prices(closes, holding)
    naive_returns = naive.pct_change()
    artifact = roll_artifact_per_date(closes, holding)

    def robust_z(series: pd.Series, at: pd.Timestamp) -> float:
        clean = series.dropna()
        scale = float((clean - clean.median()).abs().median() * 1.4826)
        return float((series.loc[at] - clean.median()) / scale)

    # The equivalence check, on REAL prices this time, not only synthetic ones.
    equivalence_delta = float(
        np.nanmax(np.abs(adjusted.pct_change().to_numpy() - chained.to_numpy()))
    )

    # Every candidate roll date in the overlap -> the artifact it would inject.
    all_artifacts = []
    positions = list(common)
    for i in range(1, len(positions)):
        d, prev = positions[i], positions[i - 1]
        splice_ret = float(far.loc[d] / near.loc[prev] - 1.0)
        true_ret = float(far.loc[d] / far.loc[prev] - 1.0)
        all_artifacts.append(100.0 * (splice_ret - true_ret))
    artifacts = np.array(all_artifacts)

    cash_stats: dict[str, Any] = {}
    if cash is not None:
        cash_returns = cash.pct_change().reindex(chained.index)
        pair = pd.concat(
            [chained.rename("constructed"), cash_returns.rename("cash")], axis=1
        ).dropna()
        if len(pair) > 2:
            cash_stats = {
                "cash_index": POC_CASH_INDEX,
                "n_overlapping_days": int(len(pair)),
                "constructed_annualized_vol": annualized_volatility(pair["constructed"]),
                "cash_annualized_vol": annualized_volatility(pair["cash"]),
                "return_correlation": float(pair["constructed"].corr(pair["cash"])),
            }

    return {
        "resolved": True,
        "near_contract": POC_NEAR_CONTRACT,
        "far_contract": POC_FAR_CONTRACT,
        "overlap_start": str(common.min().date()),
        "overlap_end": str(common.max().date()),
        "n_overlap_days": int(len(common)),
        "roll_date": str(POC_ROLL_DATE.date()),
        "roll_date_pre_declared": True,
        "basis_at_roll_pct": float(
            100.0 * (far.loc[POC_ROLL_DATE] / near.loc[POC_ROLL_DATE] - 1.0)
        ),
        "constructed_return_on_roll_date_pct": float(100.0 * chained.loc[POC_ROLL_DATE]),
        "naive_splice_return_on_roll_date_pct": float(100.0 * naive_returns.loc[POC_ROLL_DATE]),
        "artifact_on_roll_date_pct_points": float(100.0 * artifact.loc[POC_ROLL_DATE]),
        "constructed_robust_z_on_roll_date": robust_z(chained, POC_ROLL_DATE),
        "naive_splice_robust_z_on_roll_date": robust_z(naive_returns, POC_ROLL_DATE),
        "ratio_adjusted_equals_chained_max_delta": equivalence_delta,
        "constructed_annualized_vol": annualized_volatility(chained),
        "artifact_distribution_over_all_candidate_roll_dates": {
            "n_candidate_dates": int(len(artifacts)),
            "mean_pct_points": float(np.mean(artifacts)),
            "median_pct_points": float(np.median(artifacts)),
            "p05_pct_points": float(np.percentile(artifacts, 5)),
            "p95_pct_points": float(np.percentile(artifacts, 95)),
            "min_pct_points": float(np.min(artifacts)),
            "max_pct_points": float(np.max(artifacts)),
            "share_positive": float(np.mean(artifacts > 0)),
        },
        "cash_index_sanity_check": cash_stats,
    }


# ---------------------------------------------------------------------------
# DATA SOURCES CHECKED (Q1) -- what was verified, and what could not be
# ---------------------------------------------------------------------------

DATA_SOURCES_CHECKED: list[dict[str, str]] = [
    {
        "source": "Yahoo Finance `=F` continuous tickers (via yfinance, already wired up in "
                  "app/services/market_data/yfinance_provider.py)",
        "cost": "free",
        "status": "VERIFIED LIVE 2026-09-05 -- INADEQUATE",
        "finding": "~26 years of daily history across 34 liquid contracts spanning all four of "
                   "MOP's asset classes, but the series are RAW UNADJUSTED FRONT-MONTH SPLICES "
                   "(PROOF_1/2/3 in the module docstring). Roll artifacts of -0.27 to +1.50 pct "
                   "pts are injected as one-day returns; they are systematically signed (positive "
                   "on 764 of 764 candidate ES roll dates) and are NOT detectable as day-level "
                   "outliers, so no filter removes them. CL=F additionally goes negative in April "
                   "2020, which makes a return series undefined there; 6J=F carries a 10x one-day "
                   "scale break in December 2001.",
    },
    {
        "source": "Yahoo Finance individual contract months (e.g. ESU26.CME, GCZ26.CMX, "
                  "CLZ26.NYM)",
        "cost": "free",
        "status": "VERIFIED LIVE 2026-09-05 -- INADEQUATE FOR HISTORY",
        "finding": "Currently-listed contracts resolve, and some carry years of history. But "
                   "EXPIRED contracts are purged: over 2015-2026, 3 of 48 ES quarterly contract "
                   "months and 3 of 72 GC contract months resolve at all, and every one of those "
                   "is currently listed or days-expired except a single-row ESZ20 stub -- so the "
                   "count of genuinely expired contract months with usable history is ZERO in "
                   "both roots. A historical front-month chain cannot be rebuilt. A FORWARD "
                   "collection programme starting today would work and yields no history now.",
    },
    {
        "source": "Nasdaq Data Link / Quandl free continuous futures (CHRIS, SCF)",
        "cost": "was free",
        "status": "UNVERIFIED FROM THIS ENVIRONMENT -- reported as deprecated",
        "finding": "Every direct API call from here (data.nasdaq.com and www.quandl.com, with "
                   "and without a browser user-agent) returned an Incapsula bot-protection "
                   "interstitial rather than JSON or an error, including for the known-retired "
                   "WIKI control dataset -- so the block is indiscriminate and proves nothing "
                   "about CHRIS specifically. Third-party reports (a Packt cookbook issue "
                   "thread) describe CHRIS as deprecated and no longer updating, and Nasdaq's "
                   "own docs site is stated to retire 2026-08-31. NOT recorded as 'unavailable': "
                   "recorded as not checkable from here, needing a browser session to settle.",
    },
    {
        "source": "Stooq free CSV endpoint (stooq.com/q/d/l/)",
        "cost": "free",
        "status": "UNVERIFIED FROM THIS ENVIRONMENT",
        "finding": "Returns a JavaScript proof-of-work browser challenge, not CSV, for every "
                   "futures symbol tried. Whether it still carries continuous futures could not "
                   "be established from here. Stooq is also an aggregator without a stated "
                   "exchange licence or a documented roll/adjustment methodology, so even if "
                   "reachable it would not meet the 'licensed, non-scraped, documented "
                   "roll-adjustment' bar this question was asked against.",
    },
    {
        "source": "AQR data library -- 'Time Series Momentum: Original Paper Data'",
        "cost": "free",
        "status": "EXISTS, BUT IS NOT AN INPUT",
        "finding": "AQR publishes the MOP 2012 FACTOR return series (monthly TSMOM factors, "
                   "Jan 1985 - Dec 2009). Those are the paper's OUTPUT, not per-instrument "
                   "prices, so nothing in this project can be built on them. They are a genuine "
                   "free BENCHMARK to validate a future build against, and are worth "
                   "remembering for that, but they answer a different question.",
    },
    {
        "source": "Databento (CME Globex MDP 3.0, GLBX.MDP3)",
        "cost": "paid; USD 125 sign-up credit; CME subscription plans reported from USD 179/mo",
        "status": "PAID -- licensed distributor",
        "finding": "Official licensed distributor of CME/CBOT/NYMEX/COMEX data with documented "
                   "continuous-contract symbology and roll rules. The correct shape of answer; "
                   "the monthly subscription is the obstacle for this project's scale.",
    },
    {
        "source": "Norgate Data -- Futures package",
        "cost": "paid; USD 270 / 12 months, USD 148.50 / 6 months (read 2026-09-05)",
        "status": "PAID -- the best cost/coverage fit found",
        "finding": "~100 futures markets across 11 exchange groups, history back to ~1980 or "
                   "first trading day, supplied as BOTH unadjusted and back-adjusted spot-month "
                   "continuous contracts, with a stated roll rule ('For cash-settled futures "
                   "contracts, the roll out of the expiring contract is performed on the "
                   "business day prior to the last day of trading; for deliverable contracts, "
                   "the roll is performed on the business day prior to First Notice Day'). "
                   "IMPORTANT CAVEAT, recorded so a buyer does not walk into it: its "
                   "back-adjustment 'is calculated arithmetically', i.e. the Panama form this "
                   "run rejects. Its UNADJUSTED series chained per MOP is the thing to use.",
    },
    {
        "source": "CSI Data -- Unfair Advantage",
        "cost": "paid; price not published on the pages reachable from here",
        "status": "PAID -- not priced",
        "finding": "Long-established futures data vendor with a personal-use tier. Could not "
                   "retrieve a current price; not pursued further since Norgate already answers "
                   "the same need at a published price.",
    },
    {
        "source": "Interactive Brokers TWS/Client Portal API",
        "cost": "free with a funded brokerage account",
        "status": "NOT TESTED -- no account, and testing one would be a paid decision",
        "finding": "Serves individual contracts and continuous futures to account holders. "
                   "Named for completeness. Historical depth for futures is limited relative to "
                   "the 26+ years this family wants, and opening/funding an account is exactly "
                   "the kind of decision CLAUDE.md says to log rather than take mid-task.",
    },
]


# ---------------------------------------------------------------------------
# VERDICT (Q5)
# ---------------------------------------------------------------------------

VERDICT_CODE = "FEASIBLE_ONLY_WITH_A_PAID_DATA_DECISION"

VERDICT_STATEMENT = (
    "Option 2 is NOT feasible on this project's free/retail data, and IS feasible for a "
    "modest, specific paid decision that is now logged and left to the repo owner. The free "
    "route fails on data, not on method: Yahoo's `=F` series -- the only free futures source "
    "this project has wired up -- is a raw unadjusted front-month splice, proven three "
    "independent ways here. At every contract switch it injects a one-day return no holder "
    "earned: measured at -0.27 to +1.50 percentage points across the switches this run could "
    "certify, including +0.83 (ES) and +1.50 (NQ) in the two largest equity-index markets. "
    "Worse than the size is the SHAPE. Across all 764 candidate roll dates in the ES contract "
    "overlap the artifact was positive on EVERY ONE (mean +0.78 pct pts), so it does not "
    "average away; and on the roll date itself it is not a statistical outlier in the splice's "
    "own series (robust z +0.65, actually less extreme than the true return's own -0.70), so "
    "no outlier filter, winsorisation or jump screen can find it. Systematic, signed, and "
    "invisible day-by-day is the worst combination available. The obvious repair (rebuild the "
    "chain from individual contract months, per MOP 2012 Section 2.1) is closed off by a "
    "second measured fact: Yahoo purges expired contracts. Of 48 ES quarterly contract months "
    "over 2015-2026, the number of genuinely EXPIRED ones with usable history is ZERO (the one "
    "expired survivor, ESZ20, is a single-row stub); of 72 GC contract months, the three that "
    "resolve are all currently listed or days-expired. There is "
    "nothing to chain. Two further defects found while measuring -- CL=F's undefined returns "
    "through April 2020's negative settlement, and 6J=F's 10x one-day scale break in December "
    "2001 -- are each on their own enough to void a 12-month-lookback backtest in that market "
    "for a year.\n\n"
    "The method question, by contrast, is fully SETTLED and cost nothing: MOP 2012 Section "
    "2.1's convention is quoted verbatim, implemented, and validated against a synthetic case "
    "whose every answer is derivable by hand, including the proof that ratio back-adjustment "
    "is exactly equivalent to it and that arithmetic/Panama back-adjustment is not. That work "
    "does not expire and is reusable the moment data exists.\n\n"
    "So the honest shape of this result is neither 'feasible' nor 'impossible'. It is: the "
    "blocker is a single USD 270/year data purchase (Norgate's futures package -- ~100 markets, "
    "history to ~1980, unadjusted series available to chain per MOP), the methodology is "
    "already built and validated, and NOTHING further should be built on Yahoo `=F` futures "
    "data in the meantime. Building a TSMOM family on the splice would not be a weak test of "
    "trend-following; it would be a test of Yahoo's roll calendar, and it could just as easily "
    "manufacture a false positive as a false negative -- which is this project's stated worst "
    "outcome. Per CLAUDE.md the purchase is LOGGED (PENDING_PAID_DATA_DECISIONS.md, P4) and "
    "NOT acted on here."
)

# Each entry is explicitly parenthesised rather than relying on implicit
# adjacent-string concatenation inside the list: a future editor who forgets a
# comma would otherwise silently MERGE two warnings into one and delete a third
# of this list without any error.
WHAT_NOT_TO_DO = [
    (
        "Do NOT build a TSMOM family on Yahoo `=F` series, with or without an outlier filter. "
        "An outlier filter cannot even FIND the roll artifact -- measured here, the ES splice's "
        "roll-date return was a less extreme day by robust z-score than the true return was. "
        "And if it could find it, deleting the day would not recover the roll return; it would "
        "delete the evidence that the roll return is missing and leave MOP's spot-price path "
        "wearing a futures label."
    ),
    (
        "Do NOT substitute the deferred contracts that DO have long Yahoo history (CLZ26.NYM "
        "back to 2017, NGZ26.NYM back to 2013). Measured median daily volume for CLZ26.NYM was "
        "0 contracts in 2018 and 0 in 2020 -- a backtest of a position that could not have been "
        "taken."
    ),
    (
        "Do NOT read this run's silence on futures effective breadth as an estimate. Whether a "
        "futures basket would clear the 15 floor that the ETF universe missed at 7.10 and 8.11 "
        "is UNMEASURED and unmeasurable without the data; assuming it would clear is the single "
        "easiest way to turn this chain of honest negatives into a false positive."
    ),
    (
        "Do NOT route futures through YFinanceProvider without addressing DEFECT_B first: "
        "price_store.drop_implausible would silently drop CL=F's negative-price rows and then "
        "compute a return across the hole."
    ),
]


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main() -> None:
    log.info("validating construction against the synthetic known-answer fixture")
    synthetic = validate_against_synthetic()
    if synthetic["failures"]:
        raise SystemExit(
            "REFUSING TO RUN: the continuous-contract construction failed its synthetic "
            f"known-answer validation on {synthetic['failures']} (worst delta "
            f"{synthetic['worst_delta']:.3e}, tolerance {SYNTHETIC_TOLERANCE:.0e}). "
            "No real-data measurement below would be trustworthy."
        )
    if not synthetic["panama_demonstrably_differs"]:
        raise SystemExit(
            "REFUSING TO RUN: arithmetic/Panama back-adjustment did NOT differ from the true "
            "return on the synthetic fixture, so this run's recommendation against it would be "
            "unfounded."
        )
    log.info("synthetic validation passed (worst delta %.3e)", synthetic["worst_delta"])

    payload: dict[str, Any] = {
        "run_date": RUN_DATE,
        "generated_for": "TSMOM prep Step 4 -- Option 2 (real futures) feasibility scoping",
        "purpose": (
            "Decide whether this project can obtain futures data good enough to trust a TSMOM "
            "pass/fail verdict on, and settle the citable construction method for a continuous "
            "contract. Builds no TSMOM signal, registers nothing, and takes no paid-data "
            "decision."
        ),
        "citations": {
            "mop_2012": MOP_2012_CITE,
            "section_2_1_construction": MOP_2012_SECTION_2_1,
            "section_6_3_decomposition": MOP_2012_SECTION_6_3_DECOMPOSITION,
            "section_6_3_magnitude": MOP_2012_SECTION_6_3_MAGNITUDE,
            "section_6_3_price_basis": MOP_2012_SECTION_6_3_PRICE_BASIS,
            "far_contract_robustness": MOP_2012_FAR_CONTRACT_ROBUSTNESS,
            "equity_cash_correlation": MOP_2012_EQUITY_CASH_CORRELATION,
            "eq1_ex_ante_volatility_not_implemented_here": MOP_2012_EQ1_EX_ANTE_VOL,
        },
        "synthetic_validation": synthetic,
    }

    log.info("probing continuous `=F` coverage")
    payload["continuous_coverage"] = probe_continuous_coverage()
    log.info("screening for scale breaks and non-positive prices")
    payload["scale_breaks"] = probe_scale_breaks()
    log.info("sweeping expired-contract retention")
    payload["expired_contract_retention"] = probe_expired_contract_retention()
    log.info("detecting splice switch dates and measuring injected artifacts")
    payload["switch_dates_and_artifacts"] = probe_switch_dates_and_artifacts()
    log.info("running the calendar-free cash-benchmark roll detector")
    payload["cash_benchmark_detector"] = probe_cash_benchmark_detector()
    log.info("measuring deferred-contract liquidity")
    payload["deferred_liquidity"] = probe_deferred_liquidity()
    log.info("running the real-data proof of concept")
    payload["proof_of_concept"] = proof_of_concept_real_pair()

    payload["data_sources_checked"] = DATA_SOURCES_CHECKED
    payload["verdict_code"] = VERDICT_CODE
    payload["verdict_statement"] = VERDICT_STATEMENT
    payload["what_not_to_do"] = WHAT_NOT_TO_DO

    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    OUT_TXT.write_text(render_report(payload))
    log.info("wrote %s and %s", OUT_JSON.name, OUT_TXT.name)


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words, cur = paragraph.split(), ""
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
    a(f"TSMOM FUTURES-DATA FEASIBILITY -- TSMOM PREP STEP 4 / OPTION 2 -- {p['run_date']}")
    a("=" * 100)
    a("")
    for line in _wrap(p["purpose"], 96):
        a(line)
    a("")
    a("SCOPE: feasibility scoping ONLY. No TSMOM signal is built, no registration is touched,")
    a("no family module is modified, and no paid-data decision is taken.")
    a("")

    a("VERDICT")
    a("-" * 100)
    a(f"  {p['verdict_code']}")
    a("")
    for line in _wrap(p["verdict_statement"], 96):
        a(f"  {line}")
    a("")

    a("Q1. WHAT FREE OR LOW-COST FUTURES DATA IS ACTUALLY AVAILABLE")
    a("-" * 100)
    for src in p["data_sources_checked"]:
        a(f"  [{src['status']}]")
        a(f"    source: {src['source']}")
        a(f"    cost:   {src['cost']}")
        for line in _wrap(src["finding"], 88):
            a(f"    {line}")
        a("")

    cov = p["continuous_coverage"]
    a("Q3. REALISTIC SCOPE -- MEASURED YAHOO `=F` COVERAGE (live pulls, not assumed)")
    a("-" * 100)
    a(f"  probed {cov['n_probed']} tickers; {cov['n_resolved']} resolved across "
      f"{cov['n_asset_classes_with_coverage']} asset-class buckets "
      f"({', '.join(cov['asset_classes_with_coverage'])})")
    a(f"  earliest history start among resolved: {cov['min_history_start']}")
    a(f"  latest   history start among resolved: {cov['max_history_start']}")
    a("")
    for line in _wrap(
        "THE ANSWER TO Q3, STATED PLAINLY AND WITH ITS CAVEAT ATTACHED. On BREADTH the free "
        "route is fine: 34 of 34 probed tickers resolved, covering all four of MOP's asset "
        "classes (equity index, government bond, currency, commodity -- the last split three "
        "ways here), with ~26 years of daily history each and no gaps in the ticker list. "
        "Against MOP's own 58 instruments and Hurst/Ooi/Pedersen (2017)'s 67, roughly 30-35 "
        "liquid markets is a defensible universe size for this project. That is NOT the "
        "constraint. The constraint is that every one of those 34 series is the wrong "
        "QUANTITY -- a spot-price path, not a futures return -- so the count above is a "
        "measure of how much data would become usable IF a correctly-rolled source were "
        "obtained, not a count of usable data today. Reporting the 34 without that sentence "
        "attached would be the single most misleading thing this run could do.", 96):
        a(f"  {line}")
    a("")
    a(f"  {'ticker':<9} {'asset class':<19} {'rows':>7} {'start':>12} {'end':>12}")
    for ticker, v in cov["per_ticker"].items():
        if not v["resolved"]:
            a(f"  {ticker:<9} {v['asset_class']:<19} {'MISSING':>7}")
            continue
        a(f"  {ticker:<9} {v['asset_class']:<19} {v['n_rows']:>7} {v['start']:>12} {v['end']:>12}")
    a("")

    a("PROOF_1 / DEFECT_A -- SINGLE-DAY MOVES THAT CANNOT BE MARKET EVENTS")
    a("-" * 100)
    sb = p["scale_breaks"]
    a(f"  screen: |daily return| > {100*sb['threshold_abs_return']:.0f}% on the `=F` close series")
    if sb["hits"]:
        for h in sb["hits"]:
            a(f"    {h['ticker']:<7} {h['date']}  implied return {100*h['return']:+10.1f}%")
    else:
        a("    none")
    a("")
    a(f"  rows at or below this project's own MIN_PLAUSIBLE_PRICE "
      f"({sb['min_plausible_price']:.0e}), which price_store.drop_implausible REJECTS at ingest:")
    if sb["tickers_with_rows_this_projects_ingest_would_drop"]:
        for t in sb["tickers_with_rows_this_projects_ingest_would_drop"]:
            a(f"    {t['ticker']:<7} {t['n_rows_at_or_below_min_plausible_price']} row(s): "
              f"{', '.join(f'{d} {v:.4f}' for d, v in zip(t['dates'], t['values']))}")
        a("")
        for line in _wrap(
            "DEFECT_B: routing these tickers through YFinanceProvider would DROP those rows "
            "rather than surface them, leaving a hole and then computing a return straight "
            "across it. Every measurement in this run therefore reads yfinance directly. This "
            "is a finding about the existing ingest pipeline's futures-readiness -- logged "
            "here, not fixed here.", 92):
            a(f"    {line}")
    else:
        a("    none")
    a("")

    a("PROOF_2 -- THE `=F` SERIES *IS* ONE CONTRACT, THEN SWITCHES (identity match)")
    a("-" * 100)
    for line in _wrap(
        "A contiguous run of EXACT equality between a splice and one individual contract is "
        f"what a splice is, observed directly. Runs shorter than "
        f"{MIN_SWITCH_BLOCK_TRADING_DAYS} trading days are discarded as coincidental price "
        "collisions, which do occur in low-decimal markets.", 96):
        a(f"  {line}")
    a("")
    a("PROOF_3 -- THE ARTIFACT THE SWITCH INJECTS, MEASURED AT EACH DETECTED SWITCH")
    a("-" * 100)
    a(f"  {'splice':<7} {'contract':<13} {'switch date':<12} {'blk':>4} {'basis %':>9} "
      f"{'splice ret%':>11} {'true ret%':>10} {'ARTIFACT pp':>12}")
    for pair in p["switch_dates_and_artifacts"]["pairs"]:
        if not pair.get("resolved"):
            a(f"  {pair['splice']:<7} {pair['contract']:<13} UNRESOLVED")
            continue
        if not pair["switches"]:
            a(f"  {pair['splice']:<7} {pair['contract']:<13} "
              f"no block >= {MIN_SWITCH_BLOCK_TRADING_DAYS}d")
            continue
        for s in pair["switches"]:
            a(f"  {pair['splice']:<7} {pair['contract']:<13} {s['switch_date']:<12} "
              f"{s['block_trading_days']:>4} {s['basis_pct']:>9.4f} "
              f"{s['splice_return_pct']:>11.4f} {s['contract_own_return_pct']:>10.4f} "
              f"{s['artifact_pct_points']:>+12.4f}")
    a("")
    for line in _wrap(
        "Read the last column as: a holder of the incoming contract earned the 'true ret%' "
        "column that day. Anyone computing pct_change on the splice recorded the 'splice ret%' "
        "column instead. The difference is fiction, and it enters a 12-month TSMOM lookback for "
        "a full year and the ex-ante volatility estimate (MOP Eq. 1, 60-day centre of mass) for "
        "months.", 96):
        a(f"  {line}")
    a("")

    a("PROOF_3, CROSS-CHECKED CALENDAR-FREE AGAINST THE CASH INDEX")
    a("-" * 100)
    cb = p["cash_benchmark_detector"]
    for line in _wrap(cb["method"], 96):
        a(f"  {line}")
    a("")
    a(f"  {'futures':<7} {'cash':<8} {'days':>6} {'corr':>8} {'sigma bp':>9} {'flags':>6} "
      f"{'/yr':>6} {'in QRT mo':>10} {'(uncond)':>9} {'day 18-24':>10} {'(uncond)':>9}")
    for r in cb["equity_index_pairs"]:
        a(f"  {r['futures']:<7} {r['cash']:<8} {r['n_days']:>6} {r['return_correlation']:>8.4f} "
          f"{r['robust_sigma_bp']:>9.2f} {r['n_flagged']:>6} {r['flagged_per_year']:>6.1f} "
          f"{r['share_of_flags_in_quarterly_months']:>10.2f} "
          f"{r['unconditional_share_of_quarterly_months']:>9.2f} "
          f"{r['share_of_quarterly_flags_in_days_18_to_24']:>10.2f} "
          f"{r['unconditional_share_of_days_18_to_24']:>9.2f}")
    a("")
    for line in _wrap(
        "The two right-hand pairs are the signature. Flags concentrate in the March/June/"
        "September/December quarterly-roll months far above those months' unconditional share "
        "of the calendar, and WITHIN those months they concentrate again in days 18-24, the "
        "week containing the third Friday. That is a roll signature located WITHOUT hard-coding "
        "any exchange expiry rule -- which this run deliberately declined to do, having not "
        "verified one against the exchange itself.", 96):
        a(f"  {line}")
    a("")
    a("  the one independently verified roll date, day by day:")
    for r in cb["on_the_verified_roll_date"]:
        a(f"    {r['futures']:<7} {r['date']}  futures {r['futures_return_pct']:+7.3f}%  "
          f"cash {r['cash_return_pct']:+7.3f}%  d {r['d_bp']:+8.1f}bp  robust z {r['robust_z']:+6.1f}")
    a("")
    a("  FX pairs -- REPORTED, NOT USED, and why:")
    for r in cb["fx_pairs_reported_only"]:
        a(f"    {r['futures']:<7} vs {r['cash']:<10} return correlation "
          f"{r['return_correlation']:>7.4f}  ({r['n_days']} days)")
    for line in _wrap(
        "MOP's p.231 sentence licenses the equity-index/cash-index comparison specifically, and "
        "the measured ~0.97 correlations above bear it out. Yahoo's own SPOT FX series do not "
        "line up with its FX futures at all at these correlations, which is a defect in the "
        "spot series' timestamping rather than evidence about the futures -- so those pairs are "
        "printed for completeness and carry no weight in any conclusion here.", 92):
        a(f"    {line}")
    a("")

    a("WHY THE OBVIOUS REPAIR FAILS -- YAHOO PURGES EXPIRED CONTRACTS")
    a("-" * 100)
    for root, r in p["expired_contract_retention"].items():
        a(f"  {root} ({r['exchange']}): {r['n_resolved']} of {r['n_probed']} contract months "
          f"across 2015-2026 resolve at all; {r['n_resolved_with_usable_history']} carry at "
          f"least {r['min_usable_contract_rows']} rows")
        for c in r["resolved"]:
            stub = "  <- STUB, not a price history" if c["n_rows"] < r["min_usable_contract_rows"] else ""
            a(f"      {c['symbol']:<13} {c['n_rows']:>5} rows  {c['start']} .. {c['end']}{stub}")
    a("")
    for line in _wrap(
        "Every survivor is currently listed or days-expired. There is no historical front-month "
        "chain to rebuild, so MOP's construction -- which this run implemented and validated -- "
        "has nothing to run on. A FORWARD collection programme recording front-month contracts "
        "from today onward would work; it produces no history now, and history is what a TSMOM "
        "verdict needs.", 96):
        a(f"  {line}")
    a("")

    a("AND WHY THE LONG-HISTORY DEFERRED CONTRACTS ARE NOT A SUBSTITUTE")
    a("-" * 100)
    for c in p["deferred_liquidity"]["contracts"]:
        a(f"  {c['symbol']:<13} {c['n_rows']:>5} rows  {c['start']} .. {c['end']}")
        for y in c["by_year"]:
            if y["year"] % 2 == 0 or y["year"] >= 2025:
                a(f"      {y['year']}  median daily volume {y['median_daily_volume']:>12,.0f}  "
                  f"(n={y['n_days']}, zero-volume days {y['zero_volume_days']})")
    a("")
    for line in _wrap(
        "These deferred months carry the long histories, but they were neither the front month "
        "nor tradeable on those historical dates. A backtest of a position with no volume is "
        "not a backtest.", 96):
        a(f"  {line}")
    a("")

    a("Q2. THE RECOMMENDED CONSTRUCTION, WITH ITS SOURCE QUOTED VERBATIM")
    a("-" * 100)
    cites = p["citations"]
    a(f"  PRIMARY SOURCE: {cites['mop_2012']}")
    a("")
    a("  Section 2.1 'Futures returns data', p.231 -- the construction itself:")
    for line in _wrap(f"\"{cites['section_2_1_construction']}\"", 92):
        a(f"    {line}")
    a("")
    for line in _wrap(
        "Implemented literally by chained_contract_daily_returns(): each daily return is "
        "computed WITHIN one contract, so a splice boundary is never a return. That is why MOP "
        "need no back-adjustment step, and why this project should not invent one. A roll "
        "therefore requires an overlap day on which the incoming contract is already quoted; "
        "the implementation raises rather than silently yielding NaN if that day is absent.", 92):
        a(f"    {line}")
    a("")
    a("  Section 6.3, p.247 -- what a raw splice omits:")
    for line in _wrap(f"\"{cites['section_6_3_decomposition']}\"", 92):
        a(f"    {line}")
    for line in _wrap(f"\"{cites['section_6_3_magnitude']}\"", 92):
        a(f"    {line}")
    a("")
    for line in _wrap(
        "MOP measure their 'Price change' from the nearest-to-expiration futures price "
        f"(\"{cites['section_6_3_price_basis']}\") -- which is exactly what Yahoo's `=F` series "
        "is. So compounding pct_change on a Yahoo `=F` series reproduces MOP's SPOT price path "
        "and omits the roll return entirely. That is the precise, citable statement of what is "
        "wrong with it, and it is why 'the endpoints roughly cancel' is no defence: TSMOM reads "
        "the trailing sign and the volatility, not the endpoints.", 92):
        a(f"    {line}")
    a("")
    a("  Section 2.1 also settles the contract-selection robustness question:")
    for line in _wrap(f"\"{cites['far_contract_robustness']}\"", 92):
        a(f"    {line}")
    a("")
    a("  EQUIVALENT FALLBACK -- ratio (proportional) back-adjustment.")
    for line in _wrap(
        "Derived independently in ratio_back_adjusted_prices() by walking roll gaps backwards "
        "from the final segment, scaling each earlier segment by k = P_incoming(d_prev) / "
        "P_outgoing(d_prev). The equivalence to MOP's chained returns is PROVEN numerically "
        "below, on both synthetic and real prices, not asserted.", 92):
        a(f"    {line}")
    a("")
    a("  REJECTED -- arithmetic / difference / 'Panama' back-adjustment.")
    for line in _wrap(
        "Shifting rather than scaling preserves price DIFFERENCES and destroys price RATIOS, so "
        "every historical percentage return is wrong; it can also drive deep history negative. "
        "Demonstrated numerically below rather than assumed. Recorded because a paid vendor may "
        "ship this as its default: Norgate states its back-adjustment 'is calculated "
        "arithmetically', so a buyer must chain that vendor's UNADJUSTED series per MOP rather "
        "than consume its back-adjusted prices as a return series.", 92):
        a(f"    {line}")
    a("")
    a("  NOT IMPLEMENTED HERE, ON PURPOSE -- MOP's ex-ante volatility model:")
    for line in _wrap(cites["eq1_ex_ante_volatility_not_implemented_here"], 92):
        a(f"    {line}")
    for line in _wrap(
        "Quoted so a later build does not re-derive it from memory, and deliberately left "
        "unimplemented: it is the first step of building the signal, which this run is scoped "
        "out of.", 92):
        a(f"    {line}")
    a("")

    a("Q4a. SYNTHETIC VALIDATION AGAINST A KNOWN TRUE ANSWER (CLAUDE.md formula rule)")
    a("-" * 100)
    sv = p["synthetic_validation"]
    for line in _wrap(
        "Two contracts over six days: a true underlying path U = [100..105], contract A quoted "
        "at exactly U, contract B quoted at exactly 1.10 * U (a constant +10% basis), rolled at "
        "the close of day 2. Every expected value below is derived BY HAND in "
        "synthetic_two_contract_roll()'s docstring and compared against the implementation -- "
        "the code is checked against arithmetic, not against itself.", 96):
        a(f"  {line}")
    a("")
    a(f"  tolerance: {sv['tolerance']:.0e}")
    for name, delta in sv["checks"].items():
        a(f"    {'PASS' if delta <= sv['tolerance'] else 'FAIL'}  {name:<52} delta {delta:.3e}")
    a(f"  worst delta across all checks: {sv['worst_delta']:.3e}")
    a("")
    a(f"  measured true cumulative return          : {100*sv['measured_cumulative_return']:.6f}%  "
      f"(hand-derived: exactly 5%)")
    a(f"  measured naive-splice cumulative return   : "
      f"{100*sv['measured_naive_splice_total_return']:.6f}%  (hand-derived: exactly 15.5%)")
    a(f"  measured injected roll artifact           : {100*sv['measured_roll_artifact']:.6f} pp  "
      f"(closed form 113.3*10.2/11444.4)")
    a(f"  Panama day-1 error vs the true 1.000000%  : "
      f"{100*sv['panama_day1_error_vs_truth']:.6f} pp -> demonstrably differs: "
      f"{sv['panama_demonstrably_differs']}")
    a("")
    for line in _wrap(
        "The run ABORTS rather than reporting anything below if any check fails, or if Panama "
        "adjustment fails to differ from the truth (which would make the recommendation against "
        "it unfounded). The same checks are pinned in "
        "tests/test_tsmom_futures_feasibility.py so a regression is caught with no network "
        "call.", 96):
        a(f"  {line}")
    a("")

    a("Q4b. PROOF OF CONCEPT ON REAL CONTRACT PRICES")
    a("-" * 100)
    poc = p["proof_of_concept"]
    if not poc.get("resolved"):
        a(f"  UNRESOLVED: {poc.get('reason', 'contract data did not resolve')}")
    else:
        a(f"  contracts: {poc['near_contract']} -> {poc['far_contract']} "
          f"(E-mini S&P 500, the most liquid futures contract in the world; both currently "
          f"listed)")
        a(f"  overlap:   {poc['overlap_start']} .. {poc['overlap_end']} "
          f"({poc['n_overlap_days']} trading days both quoted)")
        a(f"  roll date: {poc['roll_date']} -- PRE-DECLARED before any basis was measured, as "
          f"the one date")
        a("             in the overlap independently established as a real Yahoo roll date")
        a("")
        a(f"    basis between the two legs at the roll        : {poc['basis_at_roll_pct']:+.4f}%")
        a(f"    correctly constructed return on the roll date : "
          f"{poc['constructed_return_on_roll_date_pct']:+.4f}%   "
          f"(robust z {poc['constructed_robust_z_on_roll_date']:+.2f})")
        a(f"    naive splice return on the same date          : "
          f"{poc['naive_splice_return_on_roll_date_pct']:+.4f}%   "
          f"(robust z {poc['naive_splice_robust_z_on_roll_date']:+.2f})")
        a(f"    ARTIFACT the splice injects                   : "
          f"{poc['artifact_on_roll_date_pct_points']:+.4f} percentage points")
        a("")
        for line in _wrap(
            "CHECK 1 -- THE CONSTRUCTED SERIES HAS NO ARTIFICIAL JUMP, AND THE SPLICE'S JUMP "
            "CANNOT BE FILTERED OUT. The constructed series takes its roll-date return entirely "
            "from the incoming contract, so it carries no artifact by construction. The splice's "
            "return on the same date is the number above, inflated by the artifact column. This "
            "run EXPECTED the splice's roll day to stand out as a statistical outlier and "
            "measured that it does NOT: both robust z-scores above are ordinary days, and the "
            "splice's is the LESS extreme of the two. A fabrication of nearly a full percentage "
            "point hides inside the ordinary daily noise of a 15%-vol instrument. So no outlier "
            "filter, winsorisation or jump screen can find it, and 'clean the data first' is not "
            "an available repair. The artifact is visible only against an INDEPENDENT benchmark "
            "-- the cash index, which exists for equity indices and does not exist for "
            "commodities, where MOP say the roll return is largest.", 92):
            a(f"    {line}")
        a("")
        cs = poc.get("cash_index_sanity_check") or {}
        if cs:
            a("    CHECK 2 -- DOES IT LOOK LIKE THE MARKET IT CLAIMS TO BE?")
            a(f"      constructed series annualised vol : {100*cs['constructed_annualized_vol']:.2f}%")
            a(f"      {cs['cash_index']} annualised vol             : "
              f"{100*cs['cash_annualized_vol']:.2f}%")
            a(f"      return correlation with {cs['cash_index']}     : "
              f"{cs['return_correlation']:.4f}  ({cs['n_overlapping_days']} days)")
            a("")
            for line in _wrap(
                "A real large-cap equity index, not noise, and not a series that has been "
                "smoothed into something else. MOP p.231: "
                f"\"{cites['equity_cash_correlation']}\"", 92):
                a(f"      {line}")
            a("")
        a("    ratio-back-adjusted pct_change vs MOP chained returns, on REAL prices:")
        a(f"      max |delta| = {poc['ratio_adjusted_equals_chained_max_delta']:.3e}  "
          f"-- the equivalence holds outside the synthetic case too")
        a("")
        d = poc["artifact_distribution_over_all_candidate_roll_dates"]
        a(f"    THE SINGLE ROLL DATE CARRIES NO WEIGHT -- artifact over ALL "
          f"{d['n_candidate_dates']} candidate roll dates in the overlap:")
        a(f"      mean {d['mean_pct_points']:+.4f} pp   median {d['median_pct_points']:+.4f} pp   "
          f"p05 {d['p05_pct_points']:+.4f}   p95 {d['p95_pct_points']:+.4f}")
        a(f"      min  {d['min_pct_points']:+.4f} pp   max    {d['max_pct_points']:+.4f} pp   "
          f"share positive {d['share_positive']:.3f}")
        a("")
        for line in _wrap(
            "The artifact is not a rare accident with an occasional bad draw: it is a "
            "persistent, signed quantity -- the cost-of-carry basis between adjacent contract "
            "months -- injected on every roll. That is why it does not average away and why an "
            "outlier filter cannot repair it.", 92):
            a(f"    {line}")
    a("")

    a("WHAT MUST NOT BE DONE ON THE BACK OF THIS RUN")
    a("-" * 100)
    for item in p["what_not_to_do"]:
        for i, line in enumerate(_wrap(item, 92)):
            a(f"  {'* ' if i == 0 else '  '}{line}")
        a("")

    a("PAID-DATA GAP -- LOGGED, NOT ACTED ON")
    a("-" * 100)
    for line in _wrap(
        "Per CLAUDE.md ('Paid-data gaps found mid-task get logged, not acted on immediately'), "
        "the roll-adjusted futures gap is recorded as P4 in "
        "data/research_runs/PENDING_PAID_DATA_DECISIONS.md, with the stand-in, the direction it "
        "biases results, and the specific products that would close it. No purchase is "
        "recommended as an action here; the decision is the repo owner's and belongs in the "
        "single pre-go-live review that file exists to serve.", 96):
        a(f"  {line}")
    a("")

    a("WHAT THIS RUN DOES NOT ESTABLISH")
    a("-" * 100)
    for line in _wrap(
        "It does not backtest TSMOM on any universe or parameter. It does not measure what a "
        "futures universe's effective breadth would be -- that needs the data this run "
        "concludes is not freely available, and the ETF universe's 7.10/8.11 are NOT evidence "
        "about a futures basket in either direction. It does not decide the paid-data question. "
        "Its alternative-source survey is bounded by what this environment could reach: Nasdaq "
        "Data Link and Stooq both answered with bot-protection interstitials rather than data, "
        "so their current state is recorded as UNVERIFIED-FROM-HERE and explicitly NOT as "
        "'unavailable'. Settling those two needs a browser session, and neither would change "
        "the verdict on Yahoo, which is what this project actually has wired up.", 96):
        a(f"  {line}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
