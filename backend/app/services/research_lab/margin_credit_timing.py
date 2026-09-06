"""The Margin-Credit family: a ONE-INSTRUMENT (SPY vs cash) monthly market-timing
overlay built from Deuskar, Kumar & Poland's aggregate margin-credit predictor,
screened as exactly 24 PRE-DECLARED specs with its own n_trials denominator.

PRE-REGISTRATION: data/research_runs/margin_credit_PREREGISTRATION.txt,
committed as c50fb89 BEFORE this module or any backtest existed. Every
construction constant below is fixed there; this module implements that
document and does not extend it.

============================================================================
THE SOURCE, READ DIRECTLY
============================================================================
[DKP16] Deuskar, Prachi; Kumar, Nitin & Poland, Jeramia Allan, "Margin Credit
and Stock Return Predictability", Indian School of Business, September 1, 2016.
Read page-by-page from the PDF (53 pages): pp.1-19, 27-32, 33-40. Every
equation, page number and verbatim quotation below was read off those pages,
not from memory and not from a summary.

[DKP20] THE PEER-REVIEWED VERSION EXISTS AND COULD NOT BE OBTAINED. The same
work was published as "Signal on the Margin: Behavior of Levered Investors and
Future Economic Conditions", REVIEW OF FINANCE 24(5), September 2020,
pp.1039-1077, DOI 10.1093/rof/rfaa006. Oxford Academic paywalls it, SSRN blocks
automated fetches, and ISB's repository says "Full text not available from this
repository". Its abstract's "aggregate excess debt capacity of investors buying
securities on margin" is word-for-word the same object as the working paper's
margin credit, but the published text may differ in details (added macro
outcome variables, renamed terminology, revised specifications) THAT WERE NOT
VERIFIED. Disclosed wherever this family's results are, not glossed.

MECHANISM, AND WHAT KIND OF CANDIDATE THIS ACTUALLY IS. [DKP16] p.2 verbatim:
"A credit in the margin account is typically posted when a levered long
position appreciates in value and the investor decides not to reinvest the
gain... Hence, a decision not to reinvest the gain results in excess debt
capacity. This is a 'hold' signal coming from winning investors."

THIS IS NOT A MECHANICAL FORCED-FLOW SIGNAL AND IS NOT WRITTEN UP AS ONE. The
paper explicitly rejects the forced-deleveraging reading for its own measure.
p.9 verbatim, about margin DEBT: "In case of such forced deleveraging, margin
debt balance drops AFTER the fall in price, and hence is not useful as a
predictive signal for future price movements." p.6 verbatim: "we empirically
show that VOLUNTARY reduction in leverage by margin investors has information
about future returns." The correct placement is the "aggregate positioning
reveals information" tradition (Lou 2012; Frazzini-Lamont "Dumb Money";
Rapach-Ringgenberg-Zhou 2016 aggregate short interest, which [DKP16] uses as
its closest comparison), NOT the Coval-Stafford / gamma-hedging / index-
inclusion mechanical tradition. Both Lou (2012) and Dumb Money have already
been tested and declined in this project, which is a reason for MORE scepticism
here, not less.

============================================================================
THE CONSTRUCTION, EQUATION BY EQUATION
============================================================================
THE TWO RAW SERIES (Section 3, p.11, verbatim): "monthly data on the value
borrowed by all investors with NYSE member organizations and the amount held by
the same investors which could be withdrawn."

THE CONCEPTUAL IDENTITY (Section 2.2, p.8, verbatim):

    Margin Credit = (Position Value) * (1 - Margin Requirement) - Margin Debt

This is EXPOSITORY, not the empirical recipe -- the paper builds its measure
from the REPORTED free-credit-balance series, and so does this module.
`margin_credit_identity` exists only so the paper's own four-row worked example
(p.7-8) can be pinned in a unit test, as a formula-from-memory guard.

SCALING (p.11, verbatim): "We scale these values so they are relative to the
size of the economy by dividing by nominal GDP."

THE TWO-MONTH REPORTING LAG (p.11, verbatim): "To account for the two month
reporting delay, we use margin debt and credit numbers that are two months old
to avoid look-ahead bias. For example, we use the June 1995 numbers for August
1995." Implemented as REPORTING_LAG_MONTHS = 2 and asserted in the tests
against that exact example.

THE DETRENDING REGRESSIONS (p.16, verbatim displayed equations):

    MarginCredit_t / GDP_t = alpha_c + beta_c * t + u_t
    MarginDebt_t   / GDP_t = alpha_d + beta_d * t + v_t

"The residuals from these regressions u_t and v_t are our predictors, MC and
MD, respectively... standardized with mean zero and standard deviation 1... For
out-of-sample tests, MC and MD are computed RECURSIVELY using only the data
available up to time t to avoid look-ahead bias."

THAT LAST SENTENCE IS THE WHOLE ANTI-LOOK-AHEAD POINT OF THIS MODULE. The
`insample` and `recursive` estimation arms are built separately, screened
separately and reported separately; they are never averaged and never collapsed
into one number. test_recursive_signal_ignores_the_future is the direct
regression test for getting this wrong.

THE PREDICTIVE REGRESSION (Eq. (1), p.18, verbatim):

    r_{t:t+H} = alpha + beta * x_t + eps_{t:t+H}                            (1)

"where r_{t:t+H} is the average monthly S&P 500 log excess return for month t+1
to month t+H". H = 1 here (pre-registration deviation D8). Expected beta < 0.

THE MEAN-VARIANCE WEIGHT (Eq. (9), p.26, verbatim):

    w_t = (1 / gamma) * (r_hat_{t+1} / sigma_hat^2_{t+1})                   (9)

"We follow Campbell and Thompson (2008) and estimate sigma_hat^2_{t+1} using
monthly returns over a 10 year moving window. As in Rapach, Ringgenberg, and
Zhou (2016), we restrict w_t to lie between -0.5 and 1.5 and consider gamma =
3." Those three constants are INHERITED, not searched.

THE LONG-ONLY WEIGHT (p.28, verbatim): "a long only investor that invests
either 100% in the equity market or 100% in the risk-free asset... THE
INVESTMENT WEIGHT IS 1 IN S&P 500, WHEN THE PREDICTION IS POSITIVE AND 0
OTHERWISE."

NOTE WHAT THAT MEANS, because it is the easiest thing here to get wrong: the
weight is NOT a function of MC's level or sign. It is a function of the sign of
a RECURSIVELY-ESTIMATED FORECAST r_hat = alpha_hat_t + beta_hat_t * MC_t whose
coefficients use data through t only. The signal enters only through that
forecast.

============================================================================
THE DATA DEVIATION -- THE 2010-02 DEFINITIONAL BREAK. THE BIG ONE.
============================================================================
FINRA's free file (data/margin_credit/margin-statistics.xlsx, sha256
af947a17abf21df44b2d3657bd4e9fe7ea0c30db7cb367ab0483e394148fbf05) reports
column D, "Free Credit Balances in Customers' Securities Margin Accounts" --
[DKP16]'s actual measure -- ONLY FROM 2010-02. The first 157 of its 355 monthly
rows have that cell empty.

FINRA'S OWN FOOTNOTE, verbatim from its margin-statistics page: "Through
January 2010, NYSE and FINRA each independently collected similar margin data
from their respective member firms but COMBINED THE FREE CREDIT BALANCES IN
BOTH CASH AND MARGIN INTO A SINGLE AMOUNT."

This is the same class of problem the authors hit at the other end of history
and is handled the same way they handled it (p.12, verbatim): "revisions to Reg
T in June 1983 make post-1983 margin credit incomparable to pre-1983 margin
credit. To insure comparability of data across time we begin our sample in
1984."

TWO ARMS, BOTH BUILT, NEITHER SILENTLY STANDING IN FOR THE OTHER:
  `faithful`  MC = column D alone. [DKP16]'s measure exactly. Window 2010-02+,
              which after the 120-month burn-in leaves a THIN realized sample.
  `proxy`     MC = the reconstructed COMBINED free credit balance (column C
              alone through 2010-01, where C *is* the combined figure; C + D
              from 2010-02). Continuous by construction and, measured at the
              seam, continuous in fact. It is NOT the paper's measure -- it
              pools cash-account balances belonging to investors who are by
              definition not levered -- and is labelled a PROXY everywhere.

MARGIN DEBT has no such problem: column B is continuous across all 355 months,
which makes `md` the clean control separating DEFINITION effects from WINDOW
effects.

[DKP16]'S EXACT MC SERIES COULD NOT BE REPRODUCED FROM FREE DATA, and that was
established by trying rather than assumed. Their p.17 says MC/GDP peaks at
"2.6%, occurring in October of 2008"; column C in October 2008 gives 2.625%,
which matches the level, but under column C the 2008 maximum is AUGUST (3.558%)
-- so the level match is a coincidence. Their Figure 1 (p.38) shows MC/GDP near
0.002 in 1997 where column C gives 0.0085. The NYSE series they used
(nyxdata.com factbook) reported the cash/margin split historically; it is
defunct and FINRA's free file does not. Neither arm here is claimed to BE their
series.

============================================================================
WHY THE VERDICT READS OFF THE OVERLAY STREAM, NOT THE STRATEGY STREAM
============================================================================
The long-only strategy is long equities most of the time. A DSR computed on it
would largely be measuring the EQUITY RISK PREMIUM -- an exposure obtainable
for free by doing nothing -- and reporting it as a signal. So both streams are
computed for every spec and both are always reported:

    strategy_{t+1} = w_t       * (R_SPY - RF)_{t+1} - costs   [DKP16]'s object
    overlay_{t+1}  = (w_t - 1) * (R_SPY - RF)_{t+1} - costs   the incremental bet

and the pre-registration fixes the VERDICT to the `overlay` stream. A spec
whose `strategy` Sharpe beats buy-and-hold but whose `overlay` DSR fails is a
FAIL. Turnover is identical between the two streams because the w=1 benchmark
never trades, so both carry the same cost.

MONTHLY, NOT DAILY (pre-registration D7). The signal changes at most once a
month; marking the same monthly bet daily would multiply the observation count
feeding PSR/DSR by ~21 without adding one independent draw. periods_per_year is
12 everywhere in this module. This is the CONSERVATIVE choice and makes the bar
harder to clear.

What IS reused unmodified: metrics.sharpe_ratio, deflated_sharpe.
compute_deflated_sharpe, preservation_score.compute_preservation_metrics,
global_effective_n.dsr_n_trials, registration_scorecard.policy_d_verdict, and
vol_regime_timing's own _ols_beta_alpha and block_bootstrap_sharpe_pvalue --
imported, not re-implemented.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.research_lab.borrow_cost import GENERAL_COLLATERAL_BPS_PER_YEAR
from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe

# dsr_n_trials is imported ALONE and on one line, for the same reason
# rebalancing_pressure_timing.py documents: it is the one import here whose
# absence would silently make every DSR in this file more lenient.
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.preservation_score import compute_preservation_metrics
from app.services.research_lab.registration_scorecard import policy_d_verdict
from app.services.research_lab.vol_regime_timing import (
    _ols_beta_alpha,
    block_bootstrap_sharpe_pvalue,
)

logger = logging.getLogger(__name__)

MARGIN_CREDIT_CITATION = (
    "Deuskar, Kumar & Poland, 'Margin Credit and Stock Return Predictability', Indian School "
    "of Business working paper, 2016-09-01 (read directly, pp.1-19/27-32/33-40). Published as "
    "'Signal on the Margin', Review of Finance 24(5) 2020 1039-1077, DOI 10.1093/rof/rfaa006 "
    "-- PEER-REVIEWED but PAYWALLED and NOT obtained; the published text may differ."
)

# --- paths to the committed, git-durable inputs ----------------------------

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
MARGIN_CREDIT_DIR = _DATA_DIR / "margin_credit"
FINRA_CSV = MARGIN_CREDIT_DIR / "finra_margin_statistics.csv"
GDP_LATEST_CSV = MARGIN_CREDIT_DIR / "gdp_nominal_latest_vintage.csv"
GDP_REALTIME_CSV = MARGIN_CREDIT_DIR / "gdp_nominal_realtime.csv"
FAMA_FRENCH_CSV = _DATA_DIR / "fama_french_factors_monthly.csv"
SPY_CSV = _DATA_DIR / "price_store" / "v1" / "SPY.csv.gz"

EQUITY_TICKER = "SPY"

# --- the paper's own constants, inherited and never searched ---------------

# [DKP16] p.11: "we use margin debt and credit numbers that are two months old".
REPORTING_LAG_MONTHS = 2

# [DKP16] Eq. (9), p.26: gamma = 3, w clipped to [-0.5, 1.5], sigma^2 from a
# 10-year (120-month) moving window.
RISK_AVERSION_GAMMA = 3.0
WEIGHT_CLIP_LOW = -0.5
WEIGHT_CLIP_HIGH = 1.5
VARIANCE_WINDOW_MONTHS = 120

# The initial estimation window, matching the paper's own 10 years (sample
# starts 1984-01, out-of-sample starts 1994-01). FIXED IN THE PRE-REGISTRATION,
# NOT A GRID ARM -- a burn-in chosen after seeing results is a free parameter
# that flatters.
BURN_IN_MONTHS = 120

# The 2010-02 seam documented in the module docstring.
SPLIT_FIRST_MONTH = "2010-02"

MONTHS_PER_YEAR = 12.0

# Same floor as vol_regime_timing.MIN_REPLAY_TRADING_DAYS in spirit, restated
# in MONTHS because this family's observations are months. 36 months is the
# smallest window on which a monthly Sharpe is worth printing at all; it is
# deliberately low so that a thin `faithful` arm is REPORTED AS THIN rather
# than silently dropped.
MIN_REPLAY_MONTHS = 36

# Block length for the circular block bootstrap, in MONTHS. A long-only switch
# holds the same weight for many consecutive months, so the overlay stream has
# real serial dependence through the position even though the SIGNAL is
# refreshed monthly; a one-month (iid) block would ignore that. Three months is
# a quarter, and it is the largest block that still leaves the thin `faithful`
# arm above vol_regime_timing.MIN_FORMATIONS_FOR_BOOTSTRAP = 8 distinct blocks.
#
# NOTE ON UNITS, so it is not later mistaken for a bug: the imported helper
# annualizes with its own daily default internally. That does NOT matter here,
# because a bootstrap p-value compares the observed Sharpe against replicate
# Sharpes computed on the identical scale, so the scale factor cancels
# exactly. The p-value is a DESCRIPTIVE diagnostic in this family and is not a
# gate; the verdict is Policy D on the DSR ladder.
BOOTSTRAP_BLOCK_MONTHS = 3

# --- costs (pre-registration section 8) ------------------------------------

MARGIN_CREDIT_COST_BPS = 2.0
MARGIN_CREDIT_BORROW_BPS_PER_YEAR = GENERAL_COLLATERAL_BPS_PER_YEAR

# --- grid (pre-registration section 5) -------------------------------------

PREDICTORS: tuple[str, ...] = ("mc", "md", "histmean")
DEFINITION_ARMS: tuple[str, ...] = ("faithful", "proxy")
ESTIMATION_MODES: tuple[str, ...] = ("insample", "recursive")
STRATEGIES: tuple[str, ...] = ("longonly", "meanvar")

MARGIN_CREDIT_N_TRIALS = (
    len(PREDICTORS) * len(DEFINITION_ARMS) * len(ESTIMATION_MODES) * len(STRATEGIES)
)  # 24

VALIDATED_EDGE_BAR = 0.95
SCREENING_FLOOR = 0.50

# [DKP16]'s own reported numbers, for the fidelity comparison only. NOT targets.
PAPER_INSAMPLE_R2_MONTHLY = 0.0625
PAPER_OOS_R2_MONTHLY = 0.0745
PAPER_ONE_SD_EFFECT_PP_PER_MONTH = -1.1
PAPER_LONG_ONLY_SHARPE = 0.92
PAPER_MEANVAR_SHARPE = 1.0
PAPER_SAMPLE_START = date(1984, 1, 31)
PAPER_SAMPLE_END = date(2014, 12, 31)


# ---------------------------------------------------------------------------
# the paper's expository identity -- test fixture only, not a production path
# ---------------------------------------------------------------------------


def margin_credit_identity(
    position_value: float, margin_requirement: float, margin_debt: float
) -> float:
    """[DKP16] Section 2.2, p.8, verbatim: "Margin Credit = (Position Value) *
    (1 - Margin Requirement) - Margin Debt."

    Floored at zero because the identity describes EXCESS debt capacity: an
    investor whose equity has fallen below the margin requirement has a margin
    CALL, not negative credit, and the paper's own Situation 1 (p.7) reports
    margin credit 0 there rather than -100.

    NOT USED BY THE SCREEN. The empirical measure is the reported
    free-credit-balance series (p.11). This exists so the paper's four-row
    worked example can be pinned in a unit test, per CLAUDE.md's rule against
    implementing a published formula from memory."""
    return max(0.0, position_value * (1.0 - margin_requirement) - margin_debt)


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _quarter_start_of(month_key: str) -> str:
    year = int(month_key[:4])
    month = int(month_key[5:7])
    return f"{year:04d}-{((month - 1) // 3) * 3 + 1:02d}-01"


def _shift_month(month_key: str, months: int) -> str:
    year = int(month_key[:4])
    month = int(month_key[5:7])
    total = year * 12 + (month - 1) + months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def load_finra_margin_statistics(path: Path | None = None) -> pd.DataFrame:
    """The FINRA Rule 4521(d) monthly aggregates, in MILLIONS of dollars, with
    the two margin-credit definition arms already derived.

    `mc_faithful` is NaN before 2010-02 ON PURPOSE and is never back-filled:
    the series does not exist there (see the module docstring's break section),
    and a filled value would be an invention."""
    path = path or FINRA_CSV
    rows = list(csv.DictReader(path.open()))
    records = []
    for r in rows:
        ym = r["year_month"]
        debit = float(r["debit_margin_musd"])
        cash = float(r["free_credit_cash_musd"])
        margin_raw = r["free_credit_margin_musd"].strip()
        margin = float(margin_raw) if margin_raw else float("nan")
        if ym < SPLIT_FIRST_MONTH:
            # Column C IS the combined cash+margin figure in this era --
            # FINRA's own footnote, quoted in the module docstring.
            combined = cash
            faithful = float("nan")
        else:
            combined = cash + margin
            faithful = margin
        records.append(
            {
                "month": ym,
                "debit_margin": debit,
                "free_credit_cash_reported": cash,
                "free_credit_margin_reported": margin,
                "mc_faithful": faithful,
                "mc_proxy": combined,
            }
        )
    frame = pd.DataFrame.from_records(records).set_index("month").sort_index()
    if frame.empty:
        raise ValueError(f"{path} produced no rows")
    return frame


def load_gdp_latest_vintage(path: Path | None = None) -> dict[str, float]:
    path = path or GDP_LATEST_CSV
    return {
        r["quarter_start"]: float(r["gdp_nominal_bnusd"]) for r in csv.DictReader(path.open())
    }


def load_gdp_realtime(path: Path | None = None) -> dict[str, tuple[str, float]]:
    """month_key -> (gdp_quarter_start, gdp_nominal_bnusd) as PUBLISHED on that
    month's last calendar day. See fetch_margin_credit_data.py for the ALFRED
    query and for the reproduction of [DKP16]'s own August-1997 example."""
    path = path or GDP_REALTIME_CSV
    out: dict[str, tuple[str, float]] = {}
    for r in csv.DictReader(path.open()):
        signal_date = r["signal_month_end"]
        out[signal_date[:7]] = (r["gdp_quarter_start"], float(r["gdp_nominal_bnusd"]))
    return out


def load_monthly_risk_free(path: Path | None = None) -> pd.Series:
    """Fama-French's monthly 1-month T-bill rate, as a SIMPLE monthly return.

    The file states its own provenance in its header: "The 1-month TBill rate
    data until 202405 are from Ibbotson Associates. Starting from 202406, the
    1-month TBill rate is from ICE BofA US 1-Month Treasury Bill Index." Values
    are in PERCENT, hence the /100."""
    path = path or FAMA_FRENCH_CSV
    frame = pd.read_csv(path, skiprows=3)
    frame = frame.rename(columns={frame.columns[0]: "period"})
    frame["period"] = frame["period"].astype(str).str.strip()
    monthly = frame[frame["period"].str.fullmatch(r"\d{6}")].copy()
    monthly["month"] = monthly["period"].str[:4] + "-" + monthly["period"].str[4:6]
    series = pd.Series(
        monthly["RF"].astype(float).to_numpy() / 100.0,
        index=monthly["month"].to_numpy(),
        name="rf",
    )
    return series.sort_index()


SPY_HISTORY_START = date(1996, 12, 1)


def load_monthly_spy_returns(close: pd.DataFrame | None = None) -> pd.Series:
    """SPY's simple monthly TOTAL return.

    Built from YFinanceProvider.get_price_history -- THE SAME CALL
    rebalancing_pressure_timing.py uses -- rather than from a hand-rolled
    re-adjustment of the raw store. That provider serves the
    dividend-and-split-adjusted close from the committed point-in-time price
    store (data/price_store/v1/), so it is deterministic and offline: an
    identical (tickers, start, end) request returns an identical frame however
    long after the first one it runs. Re-deriving the adjustment here would be
    a second, unvalidated implementation of a convention this project already
    decided once (see price_store.py's CRSP-convention section and
    data/research_runs/dividend_convention_2026-09-04.txt).

    The final month is dropped unless the stored history actually reaches its
    end, so a partial month never gets reported as a short one."""
    if close is None:
        from app.services.market_data.yfinance_provider import YFinanceProvider

        close, missing = YFinanceProvider().get_price_history(
            [EQUITY_TICKER], SPY_HISTORY_START, date.today()
        )
        if missing or EQUITY_TICKER not in close.columns:
            raise ValueError(f"{EQUITY_TICKER} is absent from the price store; cannot replay")

    series = close[EQUITY_TICKER].astype(float).dropna()
    monthly_close = series.groupby(series.index.to_period("M")).last()
    monthly = monthly_close.pct_change().dropna()
    monthly.index = monthly.index.astype(str)
    monthly.name = "spy_total_return"

    last_day = series.index.max()
    last_month = f"{last_day.year:04d}-{last_day.month:02d}"
    if last_day.day < 25:  # an incomplete final month
        monthly = monthly[monthly.index < last_month]
    return monthly.sort_index()


@dataclass(frozen=True)
class MarginCreditPanel:
    """One monthly panel shared by every spec, so no two specs can silently see
    different inputs.

    Indexed by SIGNAL MONTH (the month at whose end a position is formed).
    `excess_simple` and `excess_log` are the return EARNED OVER THE FOLLOWING
    MONTH, i.e. already shifted, which is what makes the timing contract
    checkable in one place instead of in every spec."""

    frame: pd.DataFrame
    finra: pd.DataFrame

    @property
    def months(self) -> list[str]:
        return list(self.frame.index)


def build_margin_credit_panel(
    *,
    finra: pd.DataFrame | None = None,
    gdp_latest: dict[str, float] | None = None,
    gdp_realtime: dict[str, tuple[str, float]] | None = None,
    spy_monthly: pd.Series | None = None,
    rf_monthly: pd.Series | None = None,
) -> MarginCreditPanel:
    """Assembles the monthly panel, applying the two-month reporting lag.

    THE TIMING CONTRACT, in one place: row `month` carries
      * margin readings for month - REPORTING_LAG_MONTHS   ([DKP16] p.11)
      * the GDP an investor could see on that month's last day (real-time arm)
        or the final-revision GDP for the margin reading's own quarter
        (in-sample arm)                                     ([DKP16] p.12)
      * excess_simple / excess_log for month + 1            (Eq. 1's r_{t+1})
    There is no path by which month+1's return can reach the signal that earned
    it."""
    finra = finra if finra is not None else load_finra_margin_statistics()
    gdp_latest = gdp_latest if gdp_latest is not None else load_gdp_latest_vintage()
    gdp_realtime = gdp_realtime if gdp_realtime is not None else load_gdp_realtime()
    spy_monthly = spy_monthly if spy_monthly is not None else load_monthly_spy_returns()
    rf_monthly = rf_monthly if rf_monthly is not None else load_monthly_risk_free()

    records = []
    for signal_month in sorted(gdp_realtime):
        data_month = _shift_month(signal_month, -REPORTING_LAG_MONTHS)
        if data_month not in finra.index:
            continue
        next_month = _shift_month(signal_month, 1)
        if next_month not in spy_monthly.index or next_month not in rf_monthly.index:
            continue

        rt_quarter, rt_gdp = gdp_realtime[signal_month]
        is_quarter = _quarter_start_of(data_month)
        is_gdp = gdp_latest.get(is_quarter)
        if is_gdp is None:
            continue

        row = finra.loc[data_month]
        spy = float(spy_monthly[next_month])
        rf = float(rf_monthly[next_month])
        records.append(
            {
                "month": signal_month,
                "data_month": data_month,
                "gdp_realtime_quarter": rt_quarter,
                "gdp_realtime": rt_gdp,
                "gdp_insample_quarter": is_quarter,
                "gdp_insample": is_gdp,
                "debit_margin": float(row["debit_margin"]),
                "mc_faithful": float(row["mc_faithful"]),
                "mc_proxy": float(row["mc_proxy"]),
                "spy_total_return": spy,
                "rf": rf,
                "excess_simple": spy - rf,
                "excess_log": float(np.log1p(spy) - np.log1p(rf)),
            }
        )

    frame = pd.DataFrame.from_records(records).set_index("month").sort_index()
    if frame.empty:
        raise ValueError("margin-credit panel is empty; check the committed data snapshots")
    return MarginCreditPanel(frame=frame, finra=finra)


# ---------------------------------------------------------------------------
# signal construction -- the detrend, in-sample and recursive
# ---------------------------------------------------------------------------


# When the trend regression's residual standard deviation falls to this
# fraction of the SERIES' own standard deviation, the trend explained
# essentially all of it and the "residual" is floating-point dust. Dividing
# dust by the standard deviation of dust yields O(1) numbers that look like a
# real standardized signal and are pure numerical noise -- caught by
# test_detrend_is_degenerate_on_a_pure_line_rather_than_dividing_by_zero, where
# a perfect line produced residuals of 2.6e-15 against a series std of 8.7
# (ratio 3.0e-16) and the unguarded code happily returned values spanning
# -0.94 to +2.73. An `== 0` guard does not catch this because floating-point
# residuals are never exactly zero.
#
# Same failure mode and same register as
# vol_regime_timing.RESIDUAL_DEGENERACY_RATIO, which documents a replay where
# an unguarded hedged stream reported a confident +0.5497 with nothing left in
# it. NOT reachable on this family's real data -- the actual ratio series have
# residual-to-series std ratios around 0.1-0.4 -- so this guards the machinery,
# not the reported numbers.
TREND_DEGENERACY_RATIO = 1e-10


def _ols_trend_residuals(values: np.ndarray) -> tuple[float, float, np.ndarray]:
    """OLS of `values` on [1, t] where t = 0..n-1. Returns (intercept, slope,
    residuals). This is [DKP16] p.16's displayed regression."""
    n = len(values)
    t = np.arange(n, dtype=float)
    design = np.column_stack([np.ones(n), t])
    coeffs, *_ = np.linalg.lstsq(design, values, rcond=None)
    fitted = design @ coeffs
    return float(coeffs[0]), float(coeffs[1]), values - fitted


def _residual_std_or_none(values: np.ndarray, resid: np.ndarray) -> float | None:
    """The standard deviation to standardize a detrended series by, or None
    when the trend explained so much of the series that what is left is
    numerical dust (see TREND_DEGENERACY_RATIO)."""
    std = float(np.std(resid, ddof=1))
    if std <= 0 or not np.isfinite(std):
        return None
    series_std = float(np.std(values, ddof=1))
    if series_std > 0 and std <= TREND_DEGENERACY_RATIO * series_std:
        return None
    return std


def detrend_full_sample(ratio: pd.Series) -> pd.Series:
    """[DKP16] p.16 with the FULL sample used for the fit -- the in-sample arm.

    LOOKS AHEAD BY CONSTRUCTION and is labelled that way everywhere. The
    standardization divides by the residual standard deviation only, because an
    OLS fit with an intercept already has mean-zero residuals."""
    clean = ratio.dropna()
    if len(clean) < 3:
        return pd.Series(dtype=float)
    values = clean.to_numpy(dtype=float)
    _, _, resid = _ols_trend_residuals(values)
    std = _residual_std_or_none(values, resid)
    if std is None:
        return pd.Series(dtype=float)
    return pd.Series(resid / std, index=clean.index, name=ratio.name)


def detrend_recursive(ratio: pd.Series, *, min_observations: int = 24) -> pd.Series:
    """[DKP16] p.16 verbatim: "For out-of-sample tests, MC and MD are computed
    RECURSIVELY using only the data available up to time t to avoid look-ahead
    bias."

    At each index i the trend is re-fitted on observations 0..i ONLY, the
    residual at i is taken from that fit, and it is standardized by the
    standard deviation of THAT fit's residuals. Nothing after i is touched.

    O(n^2) by design. n is a few hundred months; a clever incremental update
    would be faster and would make the look-ahead property much harder to
    verify by reading, which is the wrong trade for the one function in this
    module where a subtle bug would invalidate every out-of-sample number."""
    clean = ratio.dropna()
    values = clean.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        if i + 1 < min_observations:
            continue
        window = values[: i + 1]
        _, _, resid = _ols_trend_residuals(window)
        std = _residual_std_or_none(window, resid)
        if std is None:
            continue
        out[i] = resid[-1] / std
    return pd.Series(out, index=clean.index, name=ratio.name)


@dataclass(frozen=True)
class TrendDiagnostics:
    """Pre-registration fidelity check F5: the paper's trend finding RE-TESTED
    on this sample rather than assumed to carry over from its 1984-2014 NYSE
    data."""

    arm: str
    series: str
    n_observations: int
    slope_per_month: float
    slope_t_stat_nw: float
    adf_stat_on_residual: float | None
    residual_std: float


def _newey_west_t_stat(values: np.ndarray, lags: int = 12) -> tuple[float, float]:
    """(slope, HAC t-statistic) for the trend regression. Newey-West with the
    given lag truncation, because the ratio series is strongly autocorrelated
    (the paper reports autocorrelation "above 0.95 for margin credit", p.15)
    and an OLS t-statistic there is meaningless."""
    n = len(values)
    t = np.arange(n, dtype=float)
    design = np.column_stack([np.ones(n), t])
    coeffs, *_ = np.linalg.lstsq(design, values, rcond=None)
    resid = values - design @ coeffs
    xtx_inv = np.linalg.pinv(design.T @ design)
    s = (design * resid[:, None]).T @ (design * resid[:, None])
    for lag in range(1, min(lags, n - 1) + 1):
        weight = 1.0 - lag / (lags + 1.0)
        a = (design[lag:] * resid[lag:, None]).T @ (design[:-lag] * resid[:-lag, None])
        s = s + weight * (a + a.T)
    cov = xtx_inv @ s @ xtx_inv
    se = float(np.sqrt(max(cov[1, 1], 0.0)))
    slope = float(coeffs[1])
    return slope, (slope / se if se > 0 else float("nan"))


def _adf_statistic(values: np.ndarray) -> float | None:
    try:
        from statsmodels.tsa.stattools import adfuller
    except Exception:  # pragma: no cover - statsmodels is a hard dependency
        return None
    if len(values) < 20:
        return None
    try:
        return float(adfuller(values, autolag="AIC")[0])
    except Exception:
        return None


def compute_trend_diagnostics(panel: MarginCreditPanel, arm: str) -> list[TrendDiagnostics]:
    out = []
    for series_key in ("mc", "md"):
        ratio = build_ratio_series(panel, arm=arm, predictor=series_key, mode="insample")
        clean = ratio.dropna()
        if len(clean) < 24:
            continue
        values = clean.to_numpy(dtype=float)
        slope, t_stat = _newey_west_t_stat(values)
        _, _, resid = _ols_trend_residuals(values)
        out.append(
            TrendDiagnostics(
                arm=arm,
                series=series_key,
                n_observations=len(values),
                slope_per_month=slope,
                slope_t_stat_nw=t_stat,
                adf_stat_on_residual=_adf_statistic(resid),
                residual_std=float(np.std(resid, ddof=1)),
            )
        )
    return out


def build_ratio_series(
    panel: MarginCreditPanel, *, arm: str, predictor: str, mode: str
) -> pd.Series:
    """MarginX_t / GDP_t, restricted to the arm's window ([DKP16] p.11).

    The GDP denominator differs by ESTIMATION MODE, exactly as the paper does
    it (p.12): the in-sample arm uses the final-revision vintage for the
    quarter containing the margin reading's own month; the recursive arm uses
    the vintage an investor could actually see on the signal date."""
    if predictor == "histmean":
        return pd.Series(dtype=float)
    frame = panel.frame
    numerator_col = {"mc": {"faithful": "mc_faithful", "proxy": "mc_proxy"}[arm], "md": "debit_margin"}[
        predictor
    ]
    numerator = frame[numerator_col].astype(float)
    if arm == "faithful":
        # md and histmean share the mc arm's WINDOW so that any difference
        # between arms is attributable to the definition, not the window.
        numerator = numerator.where(frame["data_month"] >= SPLIT_FIRST_MONTH)
    gdp_bn = frame["gdp_insample" if mode == "insample" else "gdp_realtime"].astype(float)
    # numerator is $ millions, gdp is $ billions
    return (numerator / 1000.0 / gdp_bn).rename(f"{predictor}_{arm}_{mode}")


def build_standardized_signal(
    panel: MarginCreditPanel, *, arm: str, predictor: str, mode: str
) -> pd.Series:
    if predictor == "histmean":
        return pd.Series(dtype=float)
    ratio = build_ratio_series(panel, arm=arm, predictor=predictor, mode=mode)
    return detrend_full_sample(ratio) if mode == "insample" else detrend_recursive(ratio)


# ---------------------------------------------------------------------------
# forecasts -- [DKP16] Eq. (1) estimated in-sample and recursively
# ---------------------------------------------------------------------------


def build_forecasts(
    panel: MarginCreditPanel, *, arm: str, predictor: str, mode: str
) -> pd.Series:
    """r_hat_{t+1}: the forecast of next month's LOG excess return.

    `insample` fits Eq. (1) once on the whole sample and reports its fitted
    values -- the paper's in-sample analogue, look-ahead by construction.
    `recursive` fits, at every month t, on the pairs (signal_j, realized
    return_{j+1}) whose realized return was already known at the end of month
    t, i.e. j <= t-1. THAT OFF-BY-ONE IS LOAD-BEARING: including pair j = t
    would use the very return being forecast.

    `histmean` is the control -- the Campbell-Thompson / Goyal-Welch benchmark
    [DKP16] itself measures against -- and carries no margin data at all."""
    frame = panel.frame
    realized = frame["excess_log"].astype(float)

    if predictor == "histmean":
        if arm == "faithful":
            mask = frame["data_month"] >= SPLIT_FIRST_MONTH
            realized = realized.where(mask)
        clean = realized.dropna()
        out = pd.Series(np.nan, index=frame.index, dtype=float)
        if mode == "insample":
            if len(clean) >= BURN_IN_MONTHS:
                out.loc[clean.index] = float(clean.mean())
            return out
        values = clean.to_numpy(dtype=float)
        for i in range(len(values)):
            if i < BURN_IN_MONTHS:
                continue
            out.loc[clean.index[i]] = float(values[:i].mean())
        return out

    signal = build_standardized_signal(panel, arm=arm, predictor=predictor, mode=mode)
    aligned = pd.concat(
        [signal.rename("x"), realized.rename("y")], axis=1, join="inner"
    ).dropna()
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    if len(aligned) < BURN_IN_MONTHS + 1:
        return out

    x = aligned["x"].to_numpy(dtype=float)
    y = aligned["y"].to_numpy(dtype=float)

    if mode == "insample":
        design = np.column_stack([np.ones(len(x)), x])
        coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
        out.loc[aligned.index] = design @ coeffs
        return out

    for i in range(len(x)):
        if i < BURN_IN_MONTHS:
            continue
        design = np.column_stack([np.ones(i), x[:i]])
        coeffs, *_ = np.linalg.lstsq(design, y[:i], rcond=None)
        out.loc[aligned.index[i]] = float(coeffs[0] + coeffs[1] * x[i])
    return out


def trailing_variance(panel: MarginCreditPanel, window: int = VARIANCE_WINDOW_MONTHS) -> pd.Series:
    """sigma_hat^2_{t+1} from [DKP16] Eq. (9): "monthly returns over a 10 year
    moving window". Uses returns realized THROUGH month t (hence the shift),
    never including the month being forecast."""
    excess = panel.frame["excess_simple"].astype(float)
    return excess.shift(1).rolling(window, min_periods=window).var(ddof=1)


# ---------------------------------------------------------------------------
# specs and backtest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarginCreditSpec:
    spec_id: str
    predictor: str
    arm: str
    mode: str
    strategy: str
    is_control: bool
    hypothesis: str
    citation: str = MARGIN_CREDIT_CITATION


def _build_family() -> list[MarginCreditSpec]:
    specs = []
    for predictor in PREDICTORS:
        for arm in DEFINITION_ARMS:
            for mode in ESTIMATION_MODES:
                for strategy in STRATEGIES:
                    specs.append(
                        MarginCreditSpec(
                            spec_id=f"{predictor}__{arm}__{mode}__{strategy}",
                            predictor=predictor,
                            arm=arm,
                            mode=mode,
                            strategy=strategy,
                            is_control=(predictor == "histmean"),
                            hypothesis=_hypothesis_for(predictor, arm, mode, strategy),
                        )
                    )
    return specs


def _hypothesis_for(predictor: str, arm: str, mode: str, strategy: str) -> str:
    if predictor == "histmean":
        return (
            "CONTROL: forecast is the historical mean excess return, no margin data. "
            "Says how much of any result is the machinery rather than the signal."
        )
    if predictor == "md":
        return (
            "Margin debt. [DKP16] p.2 pre-declares this as the WEAKER predictor "
            "('its performance out of sample is weak'); a weak result here is confirmatory."
        )
    definition = (
        "free credit in margin accounts -- [DKP16]'s measure exactly, 2010-02+"
        if arm == "faithful"
        else "reconstructed COMBINED free credit -- a PROXY, not the paper's measure, 1997-01+"
    )
    return (
        f"Margin credit ({definition}), {mode} estimation, {strategy} sizing. "
        "Higher MC predicts LOWER next-month excess return ([DKP16] p.2, beta < 0)."
    )


MARGIN_CREDIT_FAMILY: list[MarginCreditSpec] = _build_family()


@dataclass
class MarginCreditConfig:
    cost_bps: float = MARGIN_CREDIT_COST_BPS
    short_borrow_bps_per_year: float = MARGIN_CREDIT_BORROW_BPS_PER_YEAR


@dataclass(frozen=True)
class CostArm:
    key: str
    description: str
    cost_bps: float
    short_borrow_bps_per_year: float


COST_ARMS: tuple[CostArm, ...] = (
    CostArm(
        key="cost_free",
        description="cost_bps=0, borrow=0 -- the GROSS signal, attribution only, never a verdict input",
        cost_bps=0.0,
        short_borrow_bps_per_year=0.0,
    ),
    CostArm(
        key="baseline",
        description=(
            "cost_bps=2.0 one-way on SPY notional traded (well above SPY's own quoted "
            "half-spread; identical to rebalancing_pressure_timing.py so the two families' "
            "numbers stay comparable), borrow=34bp/yr general collateral on any short "
            "notional the meanvar clip produces -- THE VERDICT ARM"
        ),
        cost_bps=MARGIN_CREDIT_COST_BPS,
        short_borrow_bps_per_year=MARGIN_CREDIT_BORROW_BPS_PER_YEAR,
    ),
    CostArm(
        key="stress",
        description="cost_bps=10.0 one-way, same borrow -- a deliberate UNSOURCED stress",
        cost_bps=10.0,
        short_borrow_bps_per_year=MARGIN_CREDIT_BORROW_BPS_PER_YEAR,
    ),
)
BASELINE_COST_ARM = "baseline"


def build_weights(panel: MarginCreditPanel, spec: MarginCreditSpec) -> pd.Series:
    """w_t: the weight in SPY held over month t+1.

    longonly ([DKP16] p.28): "The investment weight is 1 in S&P 500, when the
    prediction is positive and 0 otherwise."
    meanvar  ([DKP16] Eq. 9): (1/gamma) * r_hat / sigma_hat^2, clipped to
    [-0.5, 1.5], gamma = 3."""
    forecasts = build_forecasts(panel, arm=spec.arm, predictor=spec.predictor, mode=spec.mode)
    if spec.strategy == "longonly":
        weights = (forecasts > 0).astype(float)
        return weights.where(forecasts.notna())
    variance = trailing_variance(panel)
    raw = (1.0 / RISK_AVERSION_GAMMA) * forecasts / variance
    return raw.clip(WEIGHT_CLIP_LOW, WEIGHT_CLIP_HIGH).where(
        forecasts.notna() & variance.notna() & (variance > 0)
    )


@dataclass
class MarginCreditBacktestResult:
    spec_id: str
    status: str
    strategy_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    overlay_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    benchmark_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    weights: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    total_cost: float = 0.0
    total_borrow_cost: float = 0.0
    total_turnover: float = 0.0
    n_switches: int = 0
    first_month: str | None = None
    last_month: str | None = None


def run_margin_credit_backtest(
    panel: MarginCreditPanel, spec: MarginCreditSpec, config: MarginCreditConfig
) -> MarginCreditBacktestResult:
    """One spec's monthly replay.

    THE TIMING CONTRACT: the weight formed at the end of month t earns month
    t+1's excess return, which the panel already carries on row t. There is no
    path by which month t+1's return can influence the weight that earned it.

    Both streams are produced here rather than in two passes so they are
    guaranteed to share one weight path, one cost charge and one month index:
        strategy = w       * excess - costs
        overlay  = (w - 1) * excess - costs
    The w=1 benchmark never trades, so the SAME cost is charged to both -- the
    overlay is the strategy minus a costless buy-and-hold, which is exactly
    what the incremental bet costs in reality."""
    weights = build_weights(panel, spec)
    excess = panel.frame["excess_simple"].astype(float)

    cost_rate = config.cost_bps / 1e4
    borrow_monthly = config.short_borrow_bps_per_year / 1e4 / MONTHS_PER_YEAR

    strategy: dict[str, float] = {}
    overlay: dict[str, float] = {}
    benchmark: dict[str, float] = {}
    held: dict[str, float] = {}
    previous = 0.0
    total_cost = 0.0
    total_borrow = 0.0
    total_turnover = 0.0
    n_switches = 0

    for month in panel.frame.index:
        w = weights.get(month, np.nan)
        r = excess.get(month, np.nan)
        if not np.isfinite(w) or not np.isfinite(r):
            continue
        turnover = abs(w - previous)
        cost = cost_rate * turnover
        borrow = borrow_monthly * max(0.0, -w)
        strategy[month] = w * r - cost - borrow
        overlay[month] = (w - 1.0) * r - cost - borrow
        benchmark[month] = r
        held[month] = w
        total_cost += cost
        total_borrow += borrow
        total_turnover += turnover
        if turnover > 0.0:
            n_switches += 1
        previous = w

    if not strategy:
        return MarginCreditBacktestResult(spec_id=spec.spec_id, status="no_realized_months")

    strategy_series = pd.Series(strategy).sort_index()
    return MarginCreditBacktestResult(
        spec_id=spec.spec_id,
        status="ok",
        strategy_returns=strategy_series,
        overlay_returns=pd.Series(overlay).sort_index(),
        benchmark_returns=pd.Series(benchmark).sort_index(),
        weights=pd.Series(held).sort_index(),
        total_cost=total_cost,
        total_borrow_cost=total_borrow,
        total_turnover=total_turnover,
        n_switches=n_switches,
        first_month=str(strategy_series.index[0]),
        last_month=str(strategy_series.index[-1]),
    )


# ---------------------------------------------------------------------------
# confound diagnostics (pre-registration F6, F8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarginCreditConfound:
    spec_id: str
    mean_weight: float
    fraction_long: float
    fraction_flat: float
    n_switches: int
    annual_turnover: float
    strategy_sharpe: float
    buy_and_hold_sharpe: float
    overlay_beta_on_market: float
    overlay_alpha_annualized: float
    predictive_beta: float | None
    predictive_beta_t_nw: float | None
    predictive_r2: float | None
    one_sd_effect_pp_per_month: float | None
    bootstrap_p_value: float | None


def compute_confound_diagnostics(
    panel: MarginCreditPanel, spec: MarginCreditSpec, replay: MarginCreditBacktestResult
) -> MarginCreditConfound:
    overlay = replay.overlay_returns
    bench = replay.benchmark_returns
    beta, alpha = _ols_beta_alpha(overlay, bench)
    weights = replay.weights
    n_years = max(len(overlay) / MONTHS_PER_YEAR, 1e-9)

    predictive_beta = predictive_t = predictive_r2 = one_sd = None
    if spec.predictor != "histmean":
        signal = build_standardized_signal(
            panel, arm=spec.arm, predictor=spec.predictor, mode=spec.mode
        )
        aligned = pd.concat(
            [signal.rename("x"), panel.frame["excess_log"].rename("y")], axis=1, join="inner"
        ).dropna()
        if len(aligned) >= 24:
            x = aligned["x"].to_numpy(dtype=float)
            y = aligned["y"].to_numpy(dtype=float)
            design = np.column_stack([np.ones(len(x)), x])
            coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
            resid = y - design @ coeffs
            predictive_beta = float(coeffs[1])
            # HAC standard error on the slope, Newey-West with 12 lags.
            xtx_inv = np.linalg.pinv(design.T @ design)
            s = (design * resid[:, None]).T @ (design * resid[:, None])
            for lag in range(1, min(12, len(x) - 1) + 1):
                weight = 1.0 - lag / 13.0
                a = (design[lag:] * resid[lag:, None]).T @ (
                    design[:-lag] * resid[:-lag, None]
                )
                s = s + weight * (a + a.T)
            cov = xtx_inv @ s @ xtx_inv
            se = float(np.sqrt(max(cov[1, 1], 0.0)))
            predictive_t = predictive_beta / se if se > 0 else float("nan")
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            predictive_r2 = float(1.0 - np.sum(resid**2) / ss_tot) if ss_tot > 0 else None
            # The signal is already standardized, so beta IS the 1-s.d. effect.
            one_sd = predictive_beta * 100.0

    return MarginCreditConfound(
        spec_id=spec.spec_id,
        mean_weight=float(weights.mean()) if len(weights) else 0.0,
        fraction_long=float((weights > 0).mean()) if len(weights) else 0.0,
        fraction_flat=float((weights == 0).mean()) if len(weights) else 0.0,
        n_switches=replay.n_switches,
        annual_turnover=float(replay.total_turnover / n_years),
        strategy_sharpe=sharpe_ratio(replay.strategy_returns, periods_per_year=MONTHS_PER_YEAR),
        buy_and_hold_sharpe=sharpe_ratio(bench, periods_per_year=MONTHS_PER_YEAR),
        overlay_beta_on_market=beta,
        overlay_alpha_annualized=alpha * MONTHS_PER_YEAR,
        predictive_beta=predictive_beta,
        predictive_beta_t_nw=predictive_t,
        predictive_r2=predictive_r2,
        one_sd_effect_pp_per_month=one_sd,
        bootstrap_p_value=block_bootstrap_sharpe_pvalue(
            overlay, block_length=BOOTSTRAP_BLOCK_MONTHS
        ),
    )


# ---------------------------------------------------------------------------
# screening
# ---------------------------------------------------------------------------


def policy_d_denominators(n_local: int = MARGIN_CREDIT_N_TRIALS) -> list[int]:
    """The N values a Policy D report must cover, ascending and deduplicated:
    dsr_n_trials(n_local) plus the pooled rungs from dsr_policy_n.json
    (n_mechanisms, n_effective, n_raw).

    Same derivation and same artifact as
    rebalancing_pressure_timing.policy_d_denominators. The lowest tier is
    dsr_n_trials(n_local), NOT n_local itself, because that is the denominator
    the screen actually deflates at."""
    # The pooled rungs come from dsr_policy_n.json, the project's explicit
    # DENOMINATOR LADDER, not from global_effective_n.json's provenance fields.
    # Until 2026-09-06 this returned {n_local, 481, 857}, where 481 was
    # `n_specs_clustered` ("how many specs happened to carry a usable return
    # series") and 857 was that run's raw population count -- two bookkeeping
    # numbers on a MEASUREMENT artifact that were never chosen as denominators.
    # See dsr_policy_n.py for the four rungs and what each one is measured from.
    #
    # dsr_n_trials() is still applied to n_local first, so the family's own grid
    # remains the floor and this ladder can only ever GROW the denominator.
    from app.services.research_lab.dsr_policy_n import dsr_policy_denominators

    return dsr_policy_denominators(dsr_n_trials(int(n_local)))


def dsr_across_denominators(
    sharpe_annualized: float,
    returns: pd.Series,
    sigma_sr_annualized: float | None,
    denominators: list[int],
) -> dict[int, float | None]:
    """DSR at each N. None means the machinery could not produce one there
    (below deflated_sharpe.MIN_TRIALS_FOR_DSR, or a degenerate series) and is
    treated downstream as NOT clearing the bar."""
    return {
        int(n): compute_deflated_sharpe(
            sharpe_annualized,
            returns,
            int(n),
            sigma_sr_annualized,
            periods_per_year=MONTHS_PER_YEAR,
        ).dsr
        for n in denominators
    }


@dataclass
class MarginCreditScreeningResult:
    """One spec's full Policy D record.

    THE VERDICT FIELDS ARE THE OVERLAY ONES. sharpe_annualized, dsr_by_n,
    preservation and deflated_sharpe all describe the OVERLAY stream, per the
    pre-registration's section 6. The strategy stream's Sharpe is carried
    alongside in `strategy_sharpe` and in the confound record for comparison
    with [DKP16]'s own 0.92, and is never the verdict input."""

    spec_id: str
    predictor: str
    arm: str
    mode: str
    strategy: str
    citation: str
    hypothesis: str
    is_control: bool
    cost_arm: str
    n_trading_days: int  # MONTHS -- named for cross_sectional_persistence's contract
    first_month: str | None
    last_month: str | None
    sharpe_annualized: float  # OVERLAY
    strategy_sharpe: float
    buy_and_hold_sharpe: float
    dsr_by_n: dict[int, float | None]
    preservation: dict[str, float | int | bool | None]
    net_cumulative_overlay_return: float
    total_cost_drag: float
    total_borrow_drag: float
    total_turnover: float
    annual_turnover: float
    n_switches: int
    deflated_sharpe: object
    confound: MarginCreditConfound


def screen_margin_credit(
    panel: MarginCreditPanel,
    specs: list[MarginCreditSpec],
    config: MarginCreditConfig,
    *,
    denominators: list[int] | None = None,
    cost_arm: str = BASELINE_COST_ARM,
) -> list[MarginCreditScreeningResult]:
    """One Sharpe per spec, DSR-corrected at every pre-declared denominator.

    n_trials is fixed at len(specs) -- the family's literal pre-declared size --
    raised to the project-wide effectively-independent count by dsr_n_trials
    whenever that is larger, and NEVER shrunk to however many specs survived the
    data floors. Same rule as every other family here.

    sigma_sr is the ddof=1 standard deviation of every sibling spec's OVERLAY
    Sharpe from this same pass."""
    denominators = denominators if denominators is not None else policy_d_denominators(len(specs))
    n_local = dsr_n_trials(len(specs)) if specs else 0

    replays: dict[str, MarginCreditBacktestResult] = {}
    for spec in specs:
        replay = run_margin_credit_backtest(panel, spec, config)
        if replay.status != "ok":
            logger.info("margin_credit spec %s not replayed: %s", spec.spec_id, replay.status)
            continue
        if len(replay.overlay_returns) < MIN_REPLAY_MONTHS:
            logger.info(
                "margin_credit spec %s dropped: only %d realized months (floor %d)",
                spec.spec_id,
                len(replay.overlay_returns),
                MIN_REPLAY_MONTHS,
            )
            continue
        replays[spec.spec_id] = replay

    sharpes = {
        sid: sharpe_ratio(r.overlay_returns, periods_per_year=MONTHS_PER_YEAR)
        for sid, r in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.spec_id: s for s in specs}
    results: list[MarginCreditScreeningResult] = []
    for spec_id, replay in replays.items():
        spec = spec_by_id[spec_id]
        overlay = replay.overlay_returns
        sharpe = sharpes[spec_id]
        dsr_by_n = dsr_across_denominators(sharpe, overlay, sigma_sr, denominators)
        deflated_local = compute_deflated_sharpe(
            sharpe, overlay, n_local, sigma_sr, periods_per_year=MONTHS_PER_YEAR
        )
        preservation = compute_preservation_metrics(
            overlay, dsr=dsr_by_n.get(n_local), periods_per_year=MONTHS_PER_YEAR
        ).as_dict()
        confound = compute_confound_diagnostics(panel, spec, replay)
        results.append(
            MarginCreditScreeningResult(
                spec_id=spec_id,
                predictor=spec.predictor,
                arm=spec.arm,
                mode=spec.mode,
                strategy=spec.strategy,
                citation=spec.citation,
                hypothesis=spec.hypothesis,
                is_control=spec.is_control,
                cost_arm=cost_arm,
                n_trading_days=len(overlay),
                first_month=replay.first_month,
                last_month=replay.last_month,
                sharpe_annualized=sharpe,
                strategy_sharpe=confound.strategy_sharpe,
                buy_and_hold_sharpe=confound.buy_and_hold_sharpe,
                dsr_by_n=dsr_by_n,
                preservation=preservation,
                net_cumulative_overlay_return=float(overlay.sum()),
                total_cost_drag=replay.total_cost,
                total_borrow_drag=replay.total_borrow_cost,
                total_turnover=replay.total_turnover,
                annual_turnover=confound.annual_turnover,
                n_switches=replay.n_switches,
                deflated_sharpe=deflated_local,
                confound=confound,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeamDiagnostics:
    """Pre-registration F7: the 2010-01 -> 2010-02 definitional seam, measured
    rather than asserted."""

    last_combined_month: str
    first_split_month: str
    debit_pct_change: float
    combined_free_credit_pct_change: float
    cash_reported_pct_change: float


def compute_seam_diagnostics(panel: MarginCreditPanel) -> SeamDiagnostics:
    finra = panel.finra
    prev = _shift_month(SPLIT_FIRST_MONTH, -1)
    before = finra.loc[prev]
    after = finra.loc[SPLIT_FIRST_MONTH]
    return SeamDiagnostics(
        last_combined_month=prev,
        first_split_month=SPLIT_FIRST_MONTH,
        debit_pct_change=float(after["debit_margin"] / before["debit_margin"] - 1.0),
        combined_free_credit_pct_change=float(after["mc_proxy"] / before["mc_proxy"] - 1.0),
        cash_reported_pct_change=float(
            after["free_credit_cash_reported"] / before["free_credit_cash_reported"] - 1.0
        ),
    )


@dataclass
class MarginCreditScreeningSummary:
    n_trials: int = MARGIN_CREDIT_N_TRIALS
    denominators: list[int] = field(default_factory=list)
    results_by_cost_arm: dict[str, list[MarginCreditScreeningResult]] = field(default_factory=dict)
    trend_diagnostics: list[TrendDiagnostics] = field(default_factory=list)
    seam: SeamDiagnostics | None = None
    sigma_sr_by_cost_arm: dict[str, float | None] = field(default_factory=dict)
    panel_first_month: str | None = None
    panel_last_month: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def baseline_results(self) -> list[MarginCreditScreeningResult]:
        return self.results_by_cost_arm.get(BASELINE_COST_ARM, [])

    def verdict(self, threshold: float = VALIDATED_EDGE_BAR) -> tuple[str, str | None]:
        """Policy D's two-tier verdict, read off the BASELINE cost arm's best
        spec by OVERLAY DSR at n_local -- exactly the rule the pre-registration
        fixed (sections 6 and 10) before any number existed."""
        results = self.baseline_results
        if not results:
            return "definite_negative", None
        n_local = dsr_n_trials(self.n_trials)
        best = max(
            results,
            key=lambda r: (r.dsr_by_n.get(n_local) if r.dsr_by_n.get(n_local) is not None else -1.0),
        )
        return (
            policy_d_verdict(dsr_by_n=best.dsr_by_n, threshold=threshold, n_local=n_local),
            best.spec_id,
        )


def build_margin_credit_disclosure(summary: MarginCreditScreeningSummary) -> list[str]:
    """Plain-language caveats that must travel with any number from this
    family."""
    lines = [
        f"SOURCE: {MARGIN_CREDIT_CITATION}",
        (
            "THE PEER-REVIEWED TEXT WAS NOT OBTAINED. This build implements the 2016 WORKING "
            "PAPER. The 2020 Review of Finance version is retitled and may differ in details "
            "(added macro outcome variables, renamed terminology, revised specifications) that "
            "could not be verified. Disagreement with the published article is possible and is "
            "NOT ruled out."
        ),
        (
            "THE PAPER'S EXACT MARGIN-CREDIT SERIES COULD NOT BE REPRODUCED FROM FREE DATA. "
            "FINRA's free file reports free credit in MARGIN accounts only from 2010-02; through "
            "2010-01 cash and margin free credit were combined into a single amount (FINRA's own "
            "footnote). The `faithful` arm is definitionally correct but starts 2010-02; the "
            "`proxy` arm has history back to 1997-01 but pools cash-account balances belonging to "
            "investors who are not levered, which is NOT the paper's mechanism."
        ),
        (
            "NONE OF THE PAPER'S OWN SAMPLE IS REPRODUCED. [DKP16] runs 1984-01..2014-12; the "
            "`faithful` arm contains ZERO of it and the `proxy` arm only its last 18 years. "
            "Disagreement with the paper's reported numbers is expected by construction and is "
            "NOT evidence against the paper."
        ),
        (
            "THE VERDICT IS READ OFF THE OVERLAY STREAM (w - 1) * excess, not the strategy "
            "stream. A long-only timing strategy is long equities most of the time, so its raw "
            "Sharpe largely measures the equity risk premium -- available for free by doing "
            "nothing -- rather than the signal."
        ),
        (
            f"n_trials = {MARGIN_CREDIT_N_TRIALS} ({len(PREDICTORS)} predictors x "
            f"{len(DEFINITION_ARMS)} definition arms x {len(ESTIMATION_MODES)} estimation modes x "
            f"{len(STRATEGIES)} strategies), fixed in the pre-registration before any return was "
            "computed, and raised to the project-wide effectively-independent count by "
            "dsr_n_trials whenever that is larger. It does NOT cover the choice to read this "
            "particular paper."
        ),
        (
            f"THE `faithful` ARM IS THIN BY CONSTRUCTION: margin data starts 2010-02 and the "
            f"burn-in is a fixed {BURN_IN_MONTHS} months, so a weak result there is "
            "UNINFORMATIVE about the paper rather than evidence against it. The `proxy` arm "
            "carries the statistical weight."
        ),
        (
            "MONTHLY OBSERVATIONS, periods_per_year = 12. The signal changes at most once a "
            "month; marking it daily would inflate the PSR/DSR observation count ~21x without "
            "adding one independent draw."
        ),
        (
            "H = 1 ONLY. The paper's quarterly/semi-annual/annual horizons and its larger "
            "annual-horizon R-squared are NOT tested here, and no claim is made about them."
        ),
    ]
    if summary.seam is not None:
        s = summary.seam
        lines.append(
            f"SEAM MEASURED (F7): across {s.last_combined_month} -> {s.first_split_month}, "
            f"margin debt moved {s.debit_pct_change:+.2%} and the reconstructed combined free "
            f"credit moved {s.combined_free_credit_pct_change:+.2%} -- both ordinary "
            f"month-on-month moves, so the FINRA population change at that date is immaterial "
            f"at this resolution. (The as-reported cash column moved "
            f"{s.cash_reported_pct_change:+.2%}, which is the definitional split itself and is "
            f"exactly why the raw column must not be used as one continuous series.)"
        )
    for warning in summary.warnings:
        lines.append(f"WARNING: {warning}")
    return lines


def run_margin_credit_screening(
    *,
    panel: MarginCreditPanel | None = None,
    specs: list[MarginCreditSpec] | None = None,
) -> MarginCreditScreeningSummary:
    """The family's ONE production entry point. Runs every cost arm."""
    panel = panel if panel is not None else build_margin_credit_panel()
    specs = specs if specs is not None else MARGIN_CREDIT_FAMILY
    denominators = policy_d_denominators(len(specs))

    summary = MarginCreditScreeningSummary(
        n_trials=len(specs),
        denominators=denominators,
        panel_first_month=str(panel.frame.index[0]),
        panel_last_month=str(panel.frame.index[-1]),
        seam=compute_seam_diagnostics(panel),
    )
    for arm in DEFINITION_ARMS:
        summary.trend_diagnostics.extend(compute_trend_diagnostics(panel, arm))

    for cost_arm in COST_ARMS:
        config = MarginCreditConfig(
            cost_bps=cost_arm.cost_bps,
            short_borrow_bps_per_year=cost_arm.short_borrow_bps_per_year,
        )
        results = screen_margin_credit(
            panel, specs, config, denominators=denominators, cost_arm=cost_arm.key
        )
        summary.results_by_cost_arm[cost_arm.key] = results
        sharpes = [r.sharpe_annualized for r in results]
        summary.sigma_sr_by_cost_arm[cost_arm.key] = (
            float(np.std(sharpes, ddof=1)) if len(sharpes) >= 2 else None
        )

    screened = len(summary.baseline_results)
    if screened < len(specs):
        summary.warnings.append(
            f"only {screened} of {len(specs)} pre-declared specs cleared the "
            f"{MIN_REPLAY_MONTHS}-month replay floor; n_trials stays at {len(specs)} regardless"
        )
    return summary
