"""The Inelastic-Markets family: a ONE-INSTRUMENT (SPY vs cash) QUARTERLY
market-timing overlay built from Gabaix & Koijen's granular aggregate
equity-flow shock, screened as exactly 24 PRE-DECLARED specs.

PRE-REGISTRATION: data/research_runs/gabaix_koijen_inelastic_PREREGISTRATION.txt,
committed as a1b1df9 BEFORE this module or any backtest existed. Every
construction constant below is fixed there; this module implements that
document and does not extend it.

============================================================================
THE SOURCE, READ DIRECTLY
============================================================================
[GK21] Gabaix, Xavier & Ralph S. J. Koijen, "In Search of the Origins of
Financial Fluctuations: The Inelastic Markets Hypothesis", NBER Working Paper
28967, June 2021. Read from the NBER PDF; extracted text committed at
data/research_runs/gabaix_koijen_src/w28967_nber_2021.txt.

[GK22] The longer (123pp) Cowles Foundation revision, extracted text at
data/research_runs/gabaix_koijen_src/cowles_revision_2022.txt. Its headline
numbers are IDENTICAL to [GK21]'s (M = 7.1 / 5.3, "around M = 5", robustness
"ranging from 3.5 to 8"), so the revision corrected none of them.

NO PUBLISHED JOURNAL VERSION WAS LOCATED. Gabaix's own publications page
returned HTTP 403 to automated fetch and could not be read, so "no published
successor exists" is NOT claimed -- only that none was found. Disclosed
wherever this family's results are reported.

============================================================================
WHAT THIS FAMILY IS ACTUALLY TESTING -- AND WHY THE PAPER PREDICTS IT FAILS
============================================================================
THIS IS THE MOST IMPORTANT COMMENT IN THE FILE. [GK21] is a theory of price
FORMATION, not of return PREDICTABILITY. Its estimand is CONTEMPORANEOUS and
its price impact is PERMANENT, and both are the authors' own statements:

  * eq. (32) is same-quarter:  dp_t = M * Z_t + e_t. Nothing is forecast.

  * The horizon regression eq. (38) has left-hand side p_{t+h} - p_{t-1} --
    a window that ALREADY CONTAINS the contemporaneous quarter. [GK21] S4.2
    verbatim: "We find that the cumulative impact is fairly stable over time.
    This is intuitive as sharp reversals would imply a strong negative
    autocorrelation in returns, which is not something that we observe for the
    aggregate stock market at a quarterly frequency."
    M_h flat in h IS the statement that E[p_{t+h} - p_t | Z_t] ~ 0 for h >= 1.

  * [GK21] S4.2 verbatim on the other direction: "Size-weighted sector-
    specific demand shocks are also not correlated with returns at t-1."

  * [GK22] states the tradability implication outright, verbatim: "a one-time,
    non mean-reverting inflow permanently changes prices ... even if it
    contains no information whatsoever. ... The typical empirical strategy to
    look for reversals as signs of flows (rather than information) moving
    prices does not work in this case. By the same logic, we can see large
    changes in prices but small changes in long-horizon expected returns."

So the registered hypothesis here is NOT [GK21]'s claim -- it is an adjacent
claim [GK21] predicts to be FALSE. A NULL RESULT CONFIRMS THE PAPER. It is
recorded as a definite negative FOR TRADABILITY and explicitly NOT as evidence
against the inelastic markets hypothesis, which this project cannot falsify
and is not trying to.

A SECOND, INDEPENDENT BLOCKER: PUBLICATION LAG, MEASURED NOT ASSUMED. The Fed's
own release page on 2026-09-08 reads verbatim "Release Date: June 11, 2026
2026:Q1 Release". 2026:Q1 ends 2026-03-31, so the lag is 72 DAYS -- ~79% of the
way into the following quarter. Z_t is therefore NOT available at the start of
t+1, and the first quarter tradable on it is t+2. AVAILABILITY_LAG_QUARTERS = 2
is that fact, and it makes eq. (32)'s contemporaneous relationship untradable
by construction, independently of everything above.

============================================================================
THE CONSTRUCTION, EQUATION BY EQUATION
============================================================================
Holdings growth, [GK21] S4.1 verbatim ("Suppose that we have a time series of
changes in investors' equity holdings, dq_it = (Q_it - Q_i,t-1)/Q_i,t-1"):

    dq_it = (Q_it - Q_i,t-1) / Q_i,t-1                                   (28)

Q is the Z.1 LM (level, MARKET VALUE, NSA) holding of corporate equities. Being
a market-value level, dq mixes the sector's trading with the market's own
return -- which is exactly what [GK21] intends: eq. (28)'s -zeta*dp_t term IS
that valuation effect, and it is common across sectors so the GIV contrast
differences it away. [GK21] footnote 42 verbatim: "we can implement the GIV
procedure using dq_it, which does not require knowledge of holdings in other
assets than equities."

Shares and the two averages, eq. (27):

    S_i,t-1 = Q_i,t-1 / sum_j Q_j,t-1          (sums to 1)
    dq_Et   = (1/N) sum_i dq_it                 equal-weighted
    dq_St   = sum_i S_i,t-1 dq_it               size-weighted

The granular instrument, uniform-loadings case, eq. (31):

    Z_t = dq_St - dq_Et

General case with non-uniform loadings, eqs. (34)-(35): cross-sectionally
demean, dq_check_it = dq_it - dq_Et; extract r principal components; and take
Z_t as the size-weighted sum of the FACTOR-RESIDUALISED shocks (this module's
`_giv_from_panel`). r in {1, 2} is a grid dimension -- exactly the two columns
of [GK21] Table 2.

The multiplier regression, eq. (35):

    dp_t = M * Z_t + beta' * eta_t + e_t

with real GDP growth and a time trend also in the control set per eq. (37) and
[GK21] footnote 47 ("We include a time trend as some sectors grew faster in the
nineties").

NO-LOOK-AHEAD IN THE PCA (pre-registration gate G3). The PCA that residualises
dq enters Z's construction, so a full-sample PCA would leak the future into
every historical position. Every TRADABLE spec recomputes the PCA and every
standardization moment RECURSIVELY, on data through the decision date only.
The full-sample PCA is used ONLY for the G2 multiplier replication, which is
not a trading result and is labelled in-sample.

============================================================================
WHY THE VERDICT READS OFF THE OVERLAY STREAM, NOT THE STRATEGY STREAM
============================================================================
Unchanged from margin_credit_timing.py, and for the same reason: a long-only
equity timer is long equities most of the time, so a DSR on the strategy stream
would largely be measuring the EQUITY RISK PREMIUM -- free by doing nothing --
and reporting it as a signal. Both streams are always computed and reported:

    strategy_{t+1} = w_t       * (R_SPY - RF)_{t+1} - costs
    overlay_{t+1}  = (w_t - 1) * (R_SPY - RF)_{t+1} - costs   THE VERDICT

QUARTERLY, NOT MONTHLY. periods_per_year = 4 everywhere. The signal changes at
most once a quarter; marking the same quarterly bet monthly would multiply the
observation count feeding PSR/DSR by 3 without adding one independent draw.
This is the conservative choice and makes the bar harder to clear.

What IS reused unmodified, imported rather than re-implemented:
metrics.sharpe_ratio, deflated_sharpe.compute_deflated_sharpe,
preservation_score.compute_preservation_metrics,
global_effective_n.dsr_n_trials, dsr_policy_n.dsr_policy_denominators, and
margin_credit_timing's own load_monthly_spy_returns / load_monthly_risk_free.
"""

from __future__ import annotations

import csv
import gzip
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe
from app.services.research_lab.dsr_policy_n import dsr_policy_denominators
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.margin_credit_timing import (
    load_monthly_risk_free,
    load_monthly_spy_returns,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.preservation_score import compute_preservation_metrics

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
Z1_CSV = _DATA_DIR / "z1_financial_accounts" / "z1_corporate_equities_holdings.csv.gz"

QUARTERS_PER_YEAR = 4.0

# --- the sector partition (pre-registration D2), PINNED ---------------------
# 16 mutually exclusive holder sectors of US corporate equities. Aggregates
# (36/38/52/58/59/69/79/80/81/84/89), the 70-subset 76, and every indirect-
# holding memorandum item are DELIBERATELY excluded -- including an aggregate
# alongside its own components would double-count and corrupt the S_i weights.
HOLDER_SERIES: dict[str, str] = {
    "LM153064105.Q": "Households and nonprofit organizations",
    "LM263064105.Q": "Rest of the world",
    "LM103064103.Q": "Nonfinancial corporate business",
    "LM213064103.Q": "State and local governments",
    "LM223064145.Q": "State and local govt employee DB pension funds",
    "LM313064105.Q": "Federal government",
    "LM343064105.Q": "Federal government pension funds",
    "LM513064105.Q": "Property-casualty insurance companies",
    "LM543064105.Q": "Life insurance companies",
    "LM553064103.Q": "Closed-end funds",
    "LM563064100.Q": "Exchange-traded funds",
    "LM573064105.Q": "Private pension funds, including 403(b) plans",
    "LM623064103.Q": "Hedge funds",
    "LM653064100.Q": "Mutual funds",
    "LM663064105.Q": "Security brokers and dealers",
    "LM703064105.Q": "Private depository institutions",
}
TOTAL_SERIES = "LM893064105.Q"  # "All sectors; corporate equities; asset"

# The GIV panel begins at [GK21]'s own sample start. Sector admission is
# evaluated once, here, by select_giv_sectors -- see its docstring.
GIV_PANEL_START = "1993Q1"

# --- gates (pre-registration section 7) ------------------------------------
G1_MAX_MEDIAN_ABS_DISCREPANCY = 0.02  # 2.0%
G2_MULTIPLIER_RANGE = (3.5, 8.0)  # [GK21] S4.2's own disclosed robustness range
GK_PAPER_SAMPLE = ("1993Q1", "2018Q4")
GK_TABLE2_MULTIPLIERS = {1: 7.08, 2: 5.28}  # [GK21] Table 2, 1 and 2 PCs

# --- the availability rule (pre-registration section 3) --------------------
# Z.1 2026:Q1 released 2026-06-11 = 72 days after quarter end, ~79% into the
# following quarter. So Z_t is NOT usable in t+1; the first fully-tradable
# quarter is t+2.
AVAILABILITY_LAG_QUARTERS = 2
Z1_PUBLICATION_LAG_DAYS = 72

# --- costs (pre-registration section 9) ------------------------------------
INELASTIC_COST_BPS = 2.0

# --- grid (pre-registration section 8) -------------------------------------
N_PCS_ARMS: tuple[int, ...] = (1, 2)
STANDARDIZATION_ARMS: tuple[str, ...] = ("expanding", "rolling40")
POSITION_RULES: tuple[str, ...] = ("binary", "linear_clip", "tertile")
HOLDING_ARMS: tuple[str, ...] = ("1q", "2q")

INELASTIC_N_TRIALS = (
    len(N_PCS_ARMS) * len(STANDARDIZATION_ARMS) * len(POSITION_RULES) * len(HOLDING_ARMS)
)  # 24

ROLLING_WINDOW_QUARTERS = 40
MIN_WARMUP_QUARTERS = 20
REGISTERED_SIGN = 1.0  # POSITIVE/continuation, pre-registered, NOT searched

VALIDATED_EDGE_BAR = 0.95


# ===========================================================================
# data loading
# ===========================================================================
def load_z1_holdings(path: Path | None = None) -> pd.DataFrame:
    """Quarterly Z.1 corporate-equity holdings, wide (index=quarter period,
    columns=series name), in millions of USD.

    Reads the committed extract of the Fed's own FRB_Z1_xml.zip. Values are
    NSA market-value levels (LM prefix); no seasonal adjustment is applied
    because [GK21] eq. (27) needs market-value holdings, not a smoothed
    series."""
    path = path or Z1_CSV
    rows: list[dict[str, str]] = []
    with gzip.open(path, "rt") as fh:
        rows = list(csv.DictReader(fh))
    frame = pd.DataFrame(rows)
    frame["value"] = frame["value"].astype(float)
    frame["quarter"] = pd.PeriodIndex(pd.to_datetime(frame["period"]), freq="Q")
    wide = frame.pivot_table(index="quarter", columns="series_name", values="value")
    return wide.sort_index()


def load_real_gdp_growth(path: Path | None = None) -> pd.Series:
    """Quarterly log growth of REAL GDP, chained dollars.

    [GK21] Section 2.1 names its control verbatim: "quarterly data on real GDP
    growth from the St. Louis Federal Reserve Bank FRED database, series
    GDPC1". FRED's own endpoints (fredgraph.csv and api.stlouisfed.org) are
    unreachable from this environment -- the graph endpoint times out and no
    FRED API key is configured in this project -- so the SAME underlying
    series was sourced from its primary publisher instead: BEA NIPA Table
    1.1.6 ("Real Gross Domestic Product, Chained Dollars"), line 1, series
    A191RX, quarterly. FRED's GDPC1 IS that BEA series republished, so this is
    a sourcing-route substitution, NOT a proxy for a different quantity.
    Retrieved via the DBnomics mirror of BEA, dataset last revised
    2026-08-26."""
    path = path or (_DATA_DIR / "z1_financial_accounts" / "real_gdp_bea_nipa_t10106_a191rx.csv")
    frame = pd.read_csv(path)
    idx = pd.PeriodIndex(frame["period"].str.replace("-Q", "Q", regex=False), freq="Q")
    level = pd.Series(frame["real_gdp_chained_millions"].astype(float).to_numpy(), index=idx)
    return np.log(level).diff().dropna().rename("real_gdp_growth")


def market_price_return_quarterly(ticker: str = "^GSPC") -> pd.Series:
    """Quarterly log PRICE return of the aggregate market, for the G2
    replication only.

    [GK21] eq. (32)'s dp_t is a change in the aggregate stock market's log
    PRICE, so a price index is the right left-hand side here, and ^GSPC is
    used because it covers the paper's full 1993-2018 sample (SPY's committed
    store begins later). DISCLOSED DEVIATION: [GK21] Section 2.1 uses CRSP's
    value-weighted index; CRSP is a paid database this project does not have.
    The S&P 500 is a large-cap subset of CRSP's universe, so the replicated
    multiplier is expected to be CLOSE TO but not identical to Table 2's."""
    from datetime import date

    from app.services.market_data.yfinance_provider import YFinanceProvider

    close, missing = YFinanceProvider().get_price_history([ticker], date(1990, 1, 1), date.today())
    if missing or ticker not in close.columns:
        raise ValueError(f"{ticker} is absent from the price store; cannot run the G2 replication")
    series = close[ticker].astype(float).dropna()
    quarterly_close = series.groupby(series.index.to_period("Q")).last()
    return np.log(quarterly_close).diff().dropna().rename("market_log_price_return")


def check_partition_integrity(wide: pd.DataFrame) -> dict[str, float | int | bool]:
    """GATE G1. The 16 holder series must actually partition the market.

    Compares their sum against LM893064105 ("All sectors"). A failure means
    the size weights S_i are built on the wrong universe, and the
    pre-registration forbids patching it by hunting for a better-fitting
    sector list -- that would be fitting the universe to the answer."""
    cols = [c for c in HOLDER_SERIES if c in wide.columns]
    missing = sorted(set(HOLDER_SERIES) - set(cols))
    sub = wide.loc["1997Q1":"2026Q1"]
    summed = sub[cols].sum(axis=1, min_count=len(cols))
    total = sub[TOTAL_SERIES]
    rel = ((summed - total) / total).abs().dropna()
    median_abs = float(rel.median()) if len(rel) else float("nan")
    return {
        "n_series_found": len(cols),
        "n_series_missing": len(missing),
        "missing": missing,
        "n_quarters_compared": int(len(rel)),
        "median_abs_rel_discrepancy": median_abs,
        "max_abs_rel_discrepancy": float(rel.max()) if len(rel) else float("nan"),
        "threshold": G1_MAX_MEDIAN_ABS_DISCREPANCY,
        "passed": bool(len(missing) == 0 and median_abs <= G1_MAX_MEDIAN_ABS_DISCREPANCY),
    }


# ===========================================================================
# the GIV construction -- [GK21] eqs. (27), (28), (31), (34)
# ===========================================================================
def select_giv_sectors(wide: pd.DataFrame, start: str = GIV_PANEL_START) -> list[str]:
    """Which of the 16 holder sectors can enter the GIV panel from `start`.

    WHY THIS EXISTS -- a real property of Z.1, found by running gate G1 and
    then hitting an SVD failure, not anticipated when the grid was written.
    Several Z.1 holder sectors are reported as EXACTLY ZERO (not missing) for
    long stretches, because the Fed only began breaking them out later. A
    growth rate dq_it = (Q_it - Q_i,t-1)/Q_i,t-1 is UNDEFINED on a zero base:
    0 -> positive is +inf and 0 -> 0 is 0/0. Feeding those into the panel
    produces inf/NaN and the PCA's SVD does not converge.

    THE RULE, and it is deliberately mechanical so it cannot be steered by the
    answer: a sector is admitted iff its holdings are STRICTLY POSITIVE in
    every quarter from `start` onward. Nothing about returns, Sharpes or the
    multiplier enters this decision, and the rule is applied once at the
    paper's own sample start rather than re-tuned per spec.

    On the committed 2026-06 vintage from 1993Q1 this admits 13 of 16 and
    excludes exactly three:
      LM623064103 Hedge funds              -- reported 0 for 250 of 303
        quarters; never becomes durably positive. Note [GK21] Section 2.2
        observes the FoF "household sector ... includes various institutional
        investors such as hedge funds", so hedge-fund holdings are not lost,
        they sit inside sector 15.
      LM313064105 Federal government       -- first durably positive 2008Q3.
      LM663064105 Security brokers/dealers -- this is a NET series and goes
        negative; [GK21] Section 2.2 notes dealers "hold only a small fraction
        of the US equity market", so little is lost.

    The excluded sectors' economic weight is reported as `coverage_share` by
    giv_panel_coverage(), NOT assumed to be negligible."""
    cols = [c for c in HOLDER_SERIES if c in wide.columns]
    # from start MINUS ONE quarter: dq at `start` divides by the level at
    # start-1, so that base must be positive too. (ETFs are first positive in
    # exactly 1993Q1, whose 1992Q4 base is 0 -> +inf, which is what caught this.)
    window = wide.loc[pd.Period(start, "Q") - 1 :, cols]
    return [c for c in cols if bool((window[c] > 0).all())]


def giv_panel_coverage(wide: pd.DataFrame, sectors: list[str]) -> dict[str, float]:
    """What fraction of the total US corporate-equity market the admitted GIV
    panel actually covers, so the exclusions in select_giv_sectors are
    quantified rather than waved through."""
    sub = wide.loc[pd.Period(GIV_PANEL_START, "Q") :]
    share = sub[sectors].sum(axis=1) / sub[TOTAL_SERIES]
    return {
        "n_sectors": len(sectors),
        "coverage_share_median": float(share.median()),
        "coverage_share_min": float(share.min()),
        "coverage_share_last": float(share.iloc[-1]),
    }


def build_dq_panel(
    wide: pd.DataFrame, sectors: list[str] | None = None, start: str = GIV_PANEL_START
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (dq, shares): dq_it per eq. (28) and the LAGGED size shares
    S_i,t-1 per eq. (27), aligned on the same index.

    Restricted to sectors admitted by select_giv_sectors, and to quarters at
    or after `start`, so every dq is defined on a strictly positive base."""
    cols = sectors if sectors is not None else select_giv_sectors(wide, start)
    holdings = wide[cols].astype(float)
    dq = holdings.pct_change()
    lagged = holdings.shift(1)
    shares = lagged.div(lagged.sum(axis=1), axis=0)
    begin = pd.Period(start, "Q")
    dq, shares = dq.loc[begin:], shares.loc[begin:]
    common = dq.dropna(how="any").index.intersection(shares.dropna(how="any").index)
    dq, shares = dq.loc[common], shares.loc[common]
    if not np.isfinite(dq.to_numpy()).all():
        raise ValueError("non-finite dq survived sector selection -- refusing to build a GIV")
    return dq, shares


# --- the GIV core, [GK21] APPENDIX B.2 STEPS 1-5 ---------------------------
# CORRECTION LOG (found during implementation, BEFORE any strategy return
# existed). A first implementation was built from the MAIN TEXT's eqs. (34)-(35)
# alone and was materially WRONG: it cross-sectionally demeaned dq and then
# residualised Z on the principal components. Appendix B.2 gives the actual
# algorithm and it differs in four ways that all matter:
#   (i)   the "equal-weight" leg is not equal-weighted at all but INVERSE-
#         VARIANCE ("pseudo-equal") weights, winsorised at 1.5/N;
#   (ii)  THE CORPORATE SECTOR IS EXCLUDED from the instrument -- B.2 step 1
#         verbatim: "We exclude the corporate sector in constructing the
#         instrument." (It is the SUPPLY side, whose own elasticity zeta_C is
#         estimated separately in eq. 71.);
#   (iii) dq_check is the residual of a WEIGHTED PANEL REGRESSION with sector
#         fixed effects, TIME fixed effects, sector-specific GDP loadings and
#         sector-specific time trends -- eq. (67) -- not a simple demeaning;
#   (iv)  the principal components are CONTROLS in the final regression eq.
#         (69), and are NOT used to residualise Z, which is built directly
#         from the eq. (67) residuals via eq. (68).
# The symptom that prompted the re-read: the n_pcs=1 and n_pcs=2 multipliers
# came out nearly identical (1.796 vs 1.846), which cannot happen if the PCs
# genuinely enter Z's construction. This is CLAUDE.md's "never implement a
# published formula from memory" rule doing its job.

CORPORATE_SECTOR_SERIES = "LM103064103.Q"  # Nonfinancial corporate business
PSEUDO_EQUAL_CAP_MULTIPLE = 1.5  # B.2 step 1: cap at 1.5/N


def pseudo_equal_weights(dq: pd.DataFrame) -> pd.Series:
    """[GK21] Appendix B.2 STEP 1: inverse-variance "pseudo-equal" weights,
    winsorised so no sector exceeds 1.5/N, renormalised to sum to 1.

    B.2 step 1 verbatim: "we start from E~_i = sigma_i^-2 / sum_k sigma_k^-2,
    where sigma_i = sigma(dq_it), and define E~_i = min{xi E~_i, 1.5/N} where
    xi >= 1 is tuned so that sum_i E~_i = 1. ... This winsorizes the
    quasi-equal weights to be at most 50% higher than strict equal weights."

    Footnote 69 gives the reason verbatim: "The primary objective of inverse
    variance weighing is to downplay the importance of very volatile sectors
    that may distort the estimation of the common factors."

    xi is solved by bisection rather than assumed; the cap is a water-filling
    problem with no closed form."""
    sigma = dq.std(ddof=1)
    inv_var = 1.0 / sigma.pow(2)
    base = inv_var / inv_var.sum()
    n = len(base)
    cap = PSEUDO_EQUAL_CAP_MULTIPLE / n
    if float(base.max()) <= cap:
        return base
    lo, hi = 1.0, 1e9
    for _ in range(200):
        mid = (lo + hi) / 2.0
        total = float(np.minimum(mid * base, cap).sum())
        if total < 1.0:
            lo = mid
        else:
            hi = mid
    weights = np.minimum(hi * base, cap)
    return pd.Series(weights / weights.sum(), index=base.index)


def panel_residuals(dq: pd.DataFrame, gdp_growth: pd.Series, weights: pd.Series) -> pd.DataFrame:
    """[GK21] Appendix B.2 STEP 2 / eq. (67):

        dq_it = alpha_i + eta_t + lambda_i * y_t + gamma_i * t + dq_check_it

    estimated by WLS "using E~ as regression weights", with dq_check the
    residuals. y_t is quarterly real GDP growth; the sector-specific trend is
    there because, B.2 step 2 verbatim, "some sectors grew substantially
    faster in, for instance, the nineties than in the subsequent period."

    Note eta_t (a TIME fixed effect) is what makes dq_check cross-sectionally
    (weighted-)mean-zero each quarter -- the role the main text's simple
    demeaning was standing in for."""
    sectors = list(dq.columns)
    periods = list(dq.index)
    n, t_n = len(sectors), len(periods)
    y = pd.Series(gdp_growth).reindex(periods)
    if y.isna().any():
        raise ValueError("real GDP growth does not cover the dq panel")
    trend = np.arange(t_n, dtype=float)

    rows, target, row_w = [], [], []
    for si, sec in enumerate(sectors):
        for ti, per in enumerate(periods):
            sector_d = np.zeros(n)
            sector_d[si] = 1.0
            time_d = np.zeros(t_n - 1)
            if ti > 0:
                time_d[ti - 1] = 1.0  # first period dropped: collinear with sector FE
            sec_gdp = np.zeros(n)
            sec_gdp[si] = float(y.iloc[ti])
            sec_trend = np.zeros(n)
            sec_trend[si] = trend[ti]
            rows.append(np.concatenate([sector_d, time_d, sec_gdp, sec_trend]))
            target.append(float(dq.iat[ti, si]))
            row_w.append(float(weights[sec]))

    design = np.asarray(rows)
    yv = np.asarray(target)
    sw = np.sqrt(np.asarray(row_w))
    beta, *_ = np.linalg.lstsq(design * sw[:, None], yv * sw, rcond=None)
    resid = yv - design @ beta
    return pd.DataFrame(
        resid.reshape(n, t_n).T, index=pd.Index(periods, name=dq.index.name), columns=sectors
    )


def extract_pcs(dq_check: pd.DataFrame, weights: pd.Series, n_pcs: int) -> pd.DataFrame:
    """[GK21] Appendix B.2 STEP 3: "We extract the principal components of
    E~_i^{1/2} dq_check_it and denote the estimated vector of principal
    components by eta^{PC,e}_t."""
    scaled = dq_check.mul(np.sqrt(weights.reindex(dq_check.columns)), axis=1)
    matrix = scaled.to_numpy()
    centred = matrix - matrix.mean(axis=0, keepdims=True)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    k = min(n_pcs, vt.shape[0])
    scores = centred @ vt[:k].T
    return pd.DataFrame(
        scores, index=dq_check.index, columns=[f"pc{i + 1}" for i in range(k)]
    )


def giv_instrument(dq_check: pd.DataFrame, shares: pd.DataFrame) -> pd.Series:
    """[GK21] Appendix B.2 STEP 4 / eq. (68):  Z_t = sum_i S_{i,t-1} dq_check_it

    Built directly from the eq. (67) residuals. The principal components do NOT
    enter here -- they are controls in eq. (69). Size shares are renormalised
    over the instrument's own sector set (the corporate sector having been
    excluded), so they still sum to 1."""
    cols = list(dq_check.columns)
    s = shares[cols]
    s = s.div(s.sum(axis=1), axis=0)
    return (dq_check * s).sum(axis=1).rename("giv")


def instrument_sectors(sectors: list[str]) -> list[str]:
    """The instrument's sector set: everything admitted, LESS the corporate
    sector, per Appendix B.2 step 1."""
    return [c for c in sectors if c != CORPORATE_SECTOR_SERIES]


def build_giv(
    dq: pd.DataFrame,
    shares: pd.DataFrame,
    gdp_growth: pd.Series,
    n_pcs: int,
) -> tuple[pd.Series, pd.DataFrame]:
    """Appendix B.2 steps 1-4 end to end. Returns (Z_t, eta^{PC,e})."""
    cols = instrument_sectors(list(dq.columns))
    sub = dq[cols]
    weights = pseudo_equal_weights(sub)
    dq_check = panel_residuals(sub, gdp_growth, weights)
    pcs = extract_pcs(dq_check, weights, n_pcs)
    return giv_instrument(dq_check, shares), pcs


def recursive_giv(
    dq: pd.DataFrame, shares: pd.DataFrame, gdp_growth: pd.Series, n_pcs: int
) -> pd.Series:
    """GATE G3. Z_t with EVERY estimated object -- the pseudo-equal weights,
    the eq. (67) panel regression and the PCA -- refit on data THROUGH t ONLY.

    This is the series every tradable spec uses. The full-sample `build_giv`
    is reserved for the in-sample G2 replication."""
    out: dict[object, float] = {}
    index = dq.index
    for pos in range(MIN_WARMUP_QUARTERS, len(index)):
        upto = index[: pos + 1]
        z, _ = build_giv(dq.loc[upto], shares.loc[upto], gdp_growth, n_pcs)
        out[index[pos]] = float(z.iloc[-1])
    return pd.Series(out).sort_index().rename("giv_recursive")


# ===========================================================================
# GATE G2 -- reproducing [GK21] Table 2
# ===========================================================================
def _ols(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Plain OLS with an intercept prepended. Returns the coefficient vector."""
    design = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    return beta


def estimate_multiplier(
    dq: pd.DataFrame,
    shares: pd.DataFrame,
    market_return: pd.Series,
    gdp_growth: pd.Series,
    n_pcs: int,
    sample: tuple[str, str] = GK_PAPER_SAMPLE,
) -> dict[str, object]:
    """GATE G2: estimate M in [GK21] Appendix B.2 STEP 5 / eq. (69):

        dp_t = alpha + M * Z_t + beta' * eta^e_t + e_t,
        with eta^e_t = (y_t, eta^{PC,e}_t)

    Note there is NO time trend in this regression -- the trend is absorbed
    sector-by-sector in eq. (67), and [GK21] Table 2 accordingly shows only
    GDP growth, eta1/eta2 and a constant alongside Z.

    IN-SAMPLE BY CONSTRUCTION and labelled as such: this reproduces a published
    coefficient, it is not a trading result, and it never feeds a strategy
    return."""
    lo, hi = sample
    z, pcs = build_giv(dq, shares, gdp_growth, n_pcs)
    frame = (
        pd.concat(
            [z.rename("z"), market_return.rename("dp"), gdp_growth.rename("gdp"), pcs], axis=1
        )
        .loc[lo:hi]
        .dropna()
    )
    if len(frame) < 20:
        return {"n_pcs": n_pcs, "n_obs": int(len(frame)), "multiplier": float("nan")}

    xcols = ["z", "gdp"] + list(pcs.columns)
    beta = _ols(frame["dp"].to_numpy(), frame[xcols].to_numpy())
    fitted = np.column_stack([np.ones(len(frame)), frame[xcols].to_numpy()]) @ beta
    resid = frame["dp"].to_numpy() - fitted
    ss_tot = float(((frame["dp"] - frame["dp"].mean()) ** 2).sum())
    multiplier = float(beta[1])
    return {
        "n_pcs": n_pcs,
        "n_obs": int(len(frame)),
        "multiplier": multiplier,
        "gdp_coefficient": float(beta[2]),
        "r_squared": float(1.0 - (resid**2).sum() / ss_tot) if ss_tot > 0 else float("nan"),
        "sample_first": str(frame.index[0]),
        "sample_last": str(frame.index[-1]),
        "paper_value": GK_TABLE2_MULTIPLIERS.get(n_pcs, float("nan")),
        "in_paper_robustness_range": bool(
            G2_MULTIPLIER_RANGE[0] <= multiplier <= G2_MULTIPLIER_RANGE[1]
        ),
    }


# ===========================================================================
# the tradable overlay
# ===========================================================================
def standardize(z: pd.Series, mode: str) -> pd.Series:
    """z-score of Z using ONLY backward-looking moments. Never a full-sample
    mean or standard deviation -- that would leak the future into every
    historical position."""
    if mode == "expanding":
        mean = z.expanding(min_periods=MIN_WARMUP_QUARTERS).mean()
        std = z.expanding(min_periods=MIN_WARMUP_QUARTERS).std(ddof=1)
    elif mode == "rolling40":
        mean = z.rolling(ROLLING_WINDOW_QUARTERS, min_periods=MIN_WARMUP_QUARTERS).mean()
        std = z.rolling(ROLLING_WINDOW_QUARTERS, min_periods=MIN_WARMUP_QUARTERS).std(ddof=1)
    else:
        raise ValueError(f"unknown standardization mode {mode!r}")
    return ((z - mean) / std.replace(0.0, np.nan)).rename("zscore")


def position_from_zscore(zscore: pd.Series, rule: str) -> pd.Series:
    """Map the standardized signal to a weight in [0, 1]. Long/flat only, so
    no short leg and no borrow cost is possible."""
    signed = REGISTERED_SIGN * zscore
    if rule == "binary":
        w = (signed > 0).astype(float)
    elif rule == "linear_clip":
        w = (0.5 + 0.5 * signed).clip(0.0, 1.0)
    elif rule == "tertile":
        # trailing tertile buckets -- backward-looking ranks only
        rank = signed.expanding(min_periods=MIN_WARMUP_QUARTERS).apply(
            lambda s: float((s.iloc[-1] > s.to_numpy()).mean()), raw=False
        )
        w = pd.Series(np.select([rank > 2 / 3, rank > 1 / 3], [1.0, 0.5], default=0.0), index=rank.index)
        w[rank.isna()] = np.nan
    else:
        raise ValueError(f"unknown position rule {rule!r}")
    return w.where(zscore.notna())


def apply_holding(w: pd.Series, holding: str) -> pd.Series:
    """'2q' holds each decision for two quarters (the signal may only change
    on alternate quarters); '1q' is the unconstrained quarterly decision."""
    if holding == "1q":
        return w
    if holding != "2q":
        raise ValueError(f"unknown holding arm {holding!r}")
    held = w.copy()
    valid = w.dropna()
    if valid.empty:
        return held
    keep = {p for i, p in enumerate(valid.index) if i % 2 == 0}
    held.loc[[p for p in valid.index if p not in keep]] = np.nan
    return held.ffill()


def quarterly_market_excess() -> pd.Series:
    """SPY quarterly TOTAL return in excess of the 1-month T-bill.

    Both legs come from margin_credit_timing's loaders -- IMPORTED, not
    re-implemented, so this family cannot silently disagree with the project's
    other SPY overlay about what SPY returned."""
    spy = load_monthly_spy_returns()
    rf = load_monthly_risk_free()
    spy.index = pd.PeriodIndex(pd.to_datetime(spy.index), freq="M")
    rf.index = pd.PeriodIndex(pd.to_datetime(rf.index), freq="M")
    common = spy.index.intersection(rf.index)
    excess_m = spy.loc[common] - rf.loc[common]
    grouped = excess_m.groupby(excess_m.index.asfreq("Q"))
    # compound within the quarter, and drop any partial quarter
    quarterly = grouped.apply(lambda s: float(np.prod(1.0 + s.to_numpy()) - 1.0))
    counts = grouped.size()
    quarterly = quarterly[counts == 3]
    quarterly.index = pd.PeriodIndex(quarterly.index, freq="Q")
    return quarterly.sort_index().rename("market_excess")


@dataclass
class SpecResult:
    spec_id: str
    n_pcs: int
    standardization: str
    position_rule: str
    holding: str
    cost_arm: str
    n_quarters: int
    first_quarter: str | None
    last_quarter: str | None
    sharpe_annualized: float  # OVERLAY -- the verdict stream
    strategy_sharpe: float
    buy_and_hold_sharpe: float
    dsr_by_n: dict[int, float | None] = field(default_factory=dict)
    preservation: dict[str, float | int | bool | None] = field(default_factory=dict)
    net_cumulative_overlay_return: float = 0.0
    total_cost_drag: float = 0.0
    total_turnover: float = 0.0
    mean_weight: float = 0.0
    n_switches: int = 0


def replay_spec(
    z_recursive: pd.Series,
    market_excess: pd.Series,
    standardization: str,
    position_rule: str,
    holding: str,
    cost_bps: float,
) -> dict[str, object]:
    """One spec's two return streams.

    THE TIMING CONTRACT, and the whole no-look-ahead story in three lines:
    z_recursive is indexed by the Z.1 quarter t it describes; it is shifted
    forward by AVAILABILITY_LAG_QUARTERS (=2) so the weight held through
    quarter t+2 depends only on information published before that quarter
    began.
    """
    zscore = standardize(z_recursive, standardization)
    weight = position_from_zscore(zscore, position_rule)
    weight = apply_holding(weight, holding)
    weight = weight.shift(AVAILABILITY_LAG_QUARTERS)

    frame = pd.concat([weight.rename("w"), market_excess.rename("r")], axis=1).dropna()
    if frame.empty:
        return {"empty": True}

    w = frame["w"]
    r = frame["r"]
    turnover = w.diff().abs().fillna(w.iloc[0])
    cost = turnover * (cost_bps / 1e4)

    strategy = w * r - cost
    overlay = (w - 1.0) * r - cost

    return {
        "empty": False,
        "weight": w,
        "market": r,
        "strategy": strategy,
        "overlay": overlay,
        "turnover": float(turnover.sum()),
        "cost_drag": float(cost.sum()),
        "n_switches": int((w.diff().fillna(0.0) != 0).sum()),
    }


def dsr_across_denominators(
    sharpe_annualized: float,
    returns: pd.Series,
    sigma_sr_annualized: float | None,
    denominators: list[int],
) -> dict[int, float | None]:
    """DSR at each N. None means the machinery could not produce one there and
    is treated downstream as NOT clearing the bar."""
    return {
        int(n): compute_deflated_sharpe(
            sharpe_annualized,
            returns,
            int(n),
            sigma_sr_annualized,
            periods_per_year=QUARTERS_PER_YEAR,
        ).dsr
        for n in denominators
    }


def policy_d_denominators(n_local: int = INELASTIC_N_TRIALS) -> list[int]:
    """dsr_n_trials(n_local) followed by the pooled rungs from
    dsr_policy_n.json -- identical to margin_credit_timing's convention, so
    this family's verdict is read on the same ladder as every other."""
    return dsr_policy_denominators(dsr_n_trials(int(n_local)))


def spec_grid() -> list[tuple[int, str, str, str]]:
    """The 24 pre-declared specs. CLOSED -- nothing may be added after results
    exist."""
    return [
        (n_pcs, std, rule, hold)
        for n_pcs in N_PCS_ARMS
        for std in STANDARDIZATION_ARMS
        for rule in POSITION_RULES
        for hold in HOLDING_ARMS
    ]


def verdict_from_dsr(dsr_by_n: dict[int, float | None], bar: float = VALIDATED_EDGE_BAR) -> str:
    """Two-tier verdict, CLAUDE.md's rule.

    fails even at the most lenient N        -> DEFINITE_NEGATIVE
    passes lenient, fails a stricter N      -> UNRESOLVED
    passes even at the most conservative N  -> PASS
    """
    if not dsr_by_n:
        return "DEFINITE_NEGATIVE"
    rungs = sorted(dsr_by_n)
    values = [dsr_by_n[n] for n in rungs]
    lenient = values[0]
    if lenient is None or lenient < bar:
        return "DEFINITE_NEGATIVE"
    if all(v is not None and v >= bar for v in values):
        return "PASS"
    return "UNRESOLVED"
