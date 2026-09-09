"""Market intraday momentum on SPY — Gao, Han, Li & Zhou.

THE CLAIM. The first half-hour return of the trading day, measured from the
PREVIOUS day's close, predicts the sign of the last half-hour return on the same
day, on the S&P 500 ETF.

SOURCE, OBTAINED AND READ — with its provenance limit stated up front.
=====================================================================
Lei Gao (Iowa State), Yufeng Han, Sophia Zhengzi Li and Guofu Zhou (Washington
University in St. Louis), "Intraday Momentum: The First Half-Hour Return
Predicts the Last Half-Hour Return", SSRN id 2440866, **First Draft March 2014,
Current Version October 2014**. Fetched 2026-09-09 from a third-party mirror
(https://www.smallake.kr/wp-content/uploads/2015/01/SSRN-id2440866.pdf) because
SSRN itself returns HTTP 403 to automated retrieval, and its text extracted with
`pdftotext -layout`.

This is the WORKING-PAPER DRAFT, not the published version — "Market intraday
momentum", *Journal of Financial Economics* 129(2) (2018), 394-414. The author
affiliations differ (Han: Colorado Denver here vs UNC Charlotte published; Li:
Michigan State here vs Rutgers published), which is what identifies it as an
earlier draft. **Every number cited below is from the October 2014 draft.
Whether the published 2018 article reports the same figures is UNVERIFIED** —
ScienceDirect is paywalled. The draft's sample (Feb 1993 - Dec 2013) matches the
published abstract's, and its OOS R2 for r1 of 1.69% corroborates the
independently-fetched Monash replication (Limkriangkrai, Chai & Zheng,
*Pacific-Basin Finance Journal* 80 (2023), 102086, Table 2 Panel A: SPY
1996-2013 R2_OS = 0.017), so the draft is not obviously superseded — but it is a
draft and is labelled as one everywhere.

Definitions and rules are transcribed from the draft, never from memory:

  Eq. (1), draft section 2 -- 13 half-hour returns per day, 9:30am-4:00pm ET:
      r_{j,t} = p_{j,t}/p_{j-1,t} - 1,  j = 1..13
  with, verbatim, "p_{0,t} is the previous trading day's price at the 13th
  half-hour (4:00 pm) ... so that the first half-hour return captures the impact
  of information since the previous trading day's closing time."

  Eq. (4), draft section 4.1 -- the timing rule:
      eta(r1) = r13 if r1 > 0 ; -r13 if r1 <= 0
  (note the tie convention: r1 <= 0 is SHORT, not flat), with "the position
  (long or short) is closed at the market close each trading day."

  Eq. (5) -- the two-signal rule:
      eta(r1, r12) = r13 if r1>0 & r12>0 ; -r13 if r1<=0 & r12<=0 ; 0 otherwise

  Table 5 Panel A (SPY, Feb 1993 - Dec 2013, GROSS of costs), the effect sizes
  this family's power block is calibrated against:
      r1        : Avg Ret 6.67%*** (t=4.36), Std 6.19%, SRatio 1.08, Success 54.37%
      r12       : Avg Ret 1.77%   (t=1.16), Std 6.20%, SRatio 0.29, Success 50.93%
      r1 and r12: Avg Ret 4.39%*** (t=3.96), Std 4.49%, SRatio 0.98, Success 77.05%
      Always Long (benchmark): -1.11%, 6.21%, SRatio -0.18, Success 50.42%
  Draft footnote 4: "we still annualize the returns by multiplying a factor of
  252 because we only trade once per day."

  Table 3 (out-of-sample R2): r1 alone 1.69%, r12 alone 0.92%, both 2.53%.

THE ENTIRE SAMPLE HERE IS OUT-OF-SAMPLE RELATIVE TO THE PAPER.
==============================================================
The paper's sample ends 2013-12-31. This project's free Alpaca minute-bar
history starts 2016-01-04. There is ZERO OVERLAP. This module cannot replicate
the paper and does not try to: it is a pure out-of-sample test of a claim
published in 2018 on data ending in 2013, run on 2016-2026 after eight years of
publicity. A negative here is entirely consistent with the paper having been
right about 1993-2013.

WHY THIS FAMILY EXISTS AT ALL, given it is a single instrument.
==============================================================
data/research_runs/criteria_audit_2026-09-09/ measured that at this project's
sample lengths a true annualized Sharpe of 0.5 cannot be certified in a working
lifetime, and that only HIGH-Sharpe claims are testable at all. This paper's
claim is one of the few with (a) a reported Sharpe above 1, (b) free data, and
(c) one genuinely non-overlapping bet per trading day. It is a cheap test of
whether a high-Sharpe published claim survives the post-publication period and
realistic costs. It is NOT a route to the project's breadth goal.

PRE-REGISTRATION. data/research_runs/intraday_momentum_spy_2026-09-09/
PREREGISTRATION.md (committed 1532641, before any backtest) and
ADDENDUM_01_DATA_AND_COST.md (committed dd07220, after the data audit but before
any strategy return). The addendum records that the pre-registered EDGE-based
cost procedure FAILED its own sanity check -- it returned a 12.59 bp one-way
half-spread for SPY, 91x the widest half-spread a one-cent tick permits on a
$362 median close -- and was replaced, before any result existed, by a fixed
1.0 bp one-way verdict arm. That failure is disclosed rather than repaired
silently, because a cost model that decides the verdict by an artefact is the
"manufacture a false negative" failure the scoping memo warned about in advance.

COST REALISM IS NOT A SIDE DISCLOSURE (CLAUDE.md section 4). DSR, preservation
and the verdict are all computed on the NET baseline daily series. The cost_free
arm exists only to attribute how much the costs ate.

THE ARITHMETIC THAT MATTERS MOST NEEDS NO RESULT. This strategy opens and closes
a position every trading day for a 30-minute hold: 504 crossings a year against
a source-claimed GROSS 6.67%/yr with a 6.19%/yr standard deviation. At the
verdict arm's 1.0 bp/side that is 5.04%/yr of cost, so even a perfect
1993-2013-strength replication would net a Sharpe of about 0.26. That is
arithmetic on the paper's own Table 5, written into the addendum before the
2016-2026 numbers existed.
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

FAMILY_KEY = "intraday_momentum_spy"

INTRADAY_MOMENTUM_CITATION = (
    "Gao, Han, Li & Zhou, 'Intraday Momentum: The First Half-Hour Return Predicts "
    "the Last Half-Hour Return', SSRN 2440866, October 2014 draft (published as "
    "'Market intraday momentum', Journal of Financial Economics 129(2), 2018, "
    "394-414 -- the published version's figures are UNVERIFIED, paywalled)"
)

# --- session geometry (Eq. 1) ----------------------------------------------
# 13 half-hour blocks from 09:30 to 16:00 ET. Block j covers bar-START times in
# [09:30 + 30*(j-1), 09:30 + 30*j). Alpaca bar timestamps are bar-START times
# (alpaca_provider.py: "a regular-session bar starts at or after 09:30 and
# strictly before 16:00 ET"), so block 13 is starts 15:30..15:59 and p_13 is
# the close of the 15:59 bar, i.e. the regular-hours closing print.
N_HALF_HOURS = 13
SESSION_OPEN = dt_time(9, 30)
BLOCK_MINUTES = 30
FULL_SESSION_MINUTES = 390

# --- pre-registered usability rules (PREREGISTRATION section 2b) ------------
# Declared BEFORE the data was examined. Not to be tuned.
MIN_SESSION_BARS = 380  # U3
MIN_LAST_BAR_START = dt_time(15, 55)  # U2
MAX_PREVIOUS_SESSION_GAP_DAYS = 5

# --- the grid (PREREGISTRATION section 3) ----------------------------------
PREDICTORS = ("r1", "r12", "r1_and_r12")
RULES = ("sign", "deadband10bp")
PLACEBO_PREDICTOR = "r2"
# A single a-priori threshold, NOT gridded, NOT tuned. Licensed by the draft's
# footnote 9 ("In practice, one may trade only on high volume or more
# profitable days to reduce total transaction costs") and its Table 6
# volatility terciles. The paper itself specifies no threshold, so this is a
# logged DEVIATION, not a construction the source endorses.
DEADBAND = 0.0010

# --- bars (PREREGISTRATION section 4 / ADDENDUM 01 section 4c) -------------
# One-way basis points. A traded day pays TWO crossings (enter at 15:30, exit
# at 16:00); a flat day pays zero. There is never netting across days, because
# the paper closes the position at every close.
CROSSINGS_PER_TRADED_DAY = 2

VALIDATED_EDGE_BAR = 0.95
SCREENING_FLOOR = 0.50

# The paper's OWN Table 5 Panel A Sharpe for the exact rule spec r1__sign
# implements. GROSS of costs, 1993-2013, and the best of the three signals it
# reports -- an upper bound on all three counts, stated as such. Deliberately
# NOT the scoping memo's derived 2.088, which is the maximal Sharpe of an
# OPTIMALLY-SCALED linear-forecast bet and therefore describes a different,
# richer strategy that this grid does not contain; a +/-1 sign rule discards
# magnitude information and must score lower.
PAPER_SIGN_RULE_SHARPE = 1.08
SCOPING_MEMO_OPTIMAL_SCALING_SHARPE = 2.088
PAPER_SAMPLE = "1993-02-01..2013-12-31"


class IntradayMomentumError(ValueError):
    """A data or configuration problem that must not be papered over."""


# ---------------------------------------------------------------------------
# bar aggregation
# ---------------------------------------------------------------------------


def _block_index(times: pd.Series) -> np.ndarray:
    """Which half-hour block (1..13) each bar-START time falls in."""
    minutes = times.dt.hour * 60 + times.dt.minute
    open_minutes = SESSION_OPEN.hour * 60 + SESSION_OPEN.minute
    return ((minutes - open_minutes) // BLOCK_MINUTES + 1).to_numpy()


@dataclass(frozen=True)
class SessionAudit:
    """Why each calendar date was kept or dropped. Every drop is counted and
    reported by reason; no session is dropped for a reason not pre-registered."""

    n_sessions: int
    n_usable: int
    dropped_incomplete_blocks: list[str]  # U1
    dropped_late_bar: list[str]  # U2
    dropped_too_few_bars: list[str]  # U3
    dropped_no_previous: list[str]  # first session / gap > 5 calendar days
    n_traded_days: int


def build_half_hour_panel(bars: pd.DataFrame) -> tuple[pd.DataFrame, SessionAudit]:
    """Collapse 1-minute SPY bars into one row per usable trading day carrying
    r1..r13, per Eq. (1) and the pre-registered usability rules.

    `bars` must be the AlpacaProvider shape: lowercase open/high/low/close/
    volume, tz-aware America/New_York DatetimeIndex of bar-START times,
    ascending, regular session only.

    Returns (frame indexed by session date with columns r1..r13, audit)."""
    if bars.empty:
        raise IntradayMomentumError("no bars supplied")
    if "close" not in bars.columns:
        raise IntradayMomentumError(f"bars missing 'close'; have {list(bars.columns)}")

    index = pd.DatetimeIndex(bars.index)
    dates = index.normalize()
    times = pd.Series(index, index=bars.index)
    blocks = _block_index(times)

    frame = pd.DataFrame(
        {"date": dates, "block": blocks, "close": bars["close"].to_numpy(float)},
        index=bars.index,
    )

    dropped_blocks: list[str] = []
    dropped_late: list[str] = []
    dropped_few: list[str] = []
    closes_by_date: dict[pd.Timestamp, np.ndarray] = {}

    n_sessions = 0
    for session_date, group in frame.groupby("date", sort=True):
        n_sessions += 1
        label = pd.Timestamp(session_date).strftime("%Y-%m-%d")
        # U3: total bar count floor.
        if len(group) < MIN_SESSION_BARS:
            dropped_few.append(label)
            continue
        # U2: the session must actually run to the close.
        last_start = pd.Timestamp(group.index[-1]).time()
        if last_start < MIN_LAST_BAR_START:
            dropped_late.append(label)
            continue
        # U1: at least one bar in every one of the 13 blocks. p_j is the close
        # of the LAST bar present in block j (last-price sampling; a missing
        # minute inside a block is not an error).
        block_last = group.groupby("block")["close"].last()
        if not all(j in block_last.index for j in range(1, N_HALF_HOURS + 1)):
            dropped_blocks.append(label)
            continue
        closes_by_date[pd.Timestamp(session_date)] = np.array(
            [float(block_last.loc[j]) for j in range(1, N_HALF_HOURS + 1)], dtype=float
        )

    usable_dates = sorted(closes_by_date)
    rows: dict[pd.Timestamp, dict[str, float]] = {}
    dropped_no_prev: list[str] = []
    for i, session_date in enumerate(usable_dates):
        label = session_date.strftime("%Y-%m-%d")
        if i == 0:
            dropped_no_prev.append(label)
            continue
        previous = usable_dates[i - 1]
        gap_days = (session_date.normalize() - previous.normalize()).days
        if gap_days > MAX_PREVIOUS_SESSION_GAP_DAYS:
            dropped_no_prev.append(label)
            continue
        p = closes_by_date[session_date]
        p_prev_close = closes_by_date[previous][N_HALF_HOURS - 1]
        # Eq. (1): p_0,t = p_13,t-1 -- the PREVIOUS trading day's 4:00pm price.
        row = {"r1": p[0] / p_prev_close - 1.0}
        for j in range(2, N_HALF_HOURS + 1):
            row[f"r{j}"] = p[j - 1] / p[j - 2] - 1.0
        rows[session_date] = row

    if not rows:
        raise IntradayMomentumError("no usable trading days survived the pre-registered rules")

    panel = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    audit = SessionAudit(
        n_sessions=n_sessions,
        n_usable=len(usable_dates),
        dropped_incomplete_blocks=dropped_blocks,
        dropped_late_bar=dropped_late,
        dropped_too_few_bars=dropped_few,
        dropped_no_previous=dropped_no_prev,
        n_traded_days=len(panel),
    )
    return panel, audit


# ---------------------------------------------------------------------------
# specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntradayMomentumSpec:
    spec_id: str
    predictor: str
    rule: str
    is_control: bool
    citation: str
    hypothesis: str


def build_family() -> list[IntradayMomentumSpec]:
    """The 8 pre-registered specs, in the pre-registered order. Controls are
    INCLUDED in the family and therefore in N_local -- the conservative choice,
    since a larger denominator can only make the gate stricter."""
    specs: list[IntradayMomentumSpec] = []
    for predictor in PREDICTORS:
        for rule in RULES:
            specs.append(
                IntradayMomentumSpec(
                    spec_id=f"{predictor}__{rule}",
                    predictor=predictor,
                    rule=rule,
                    is_control=False,
                    citation=INTRADAY_MOMENTUM_CITATION,
                    hypothesis=_hypothesis(predictor, rule, control=False),
                )
            )
    for rule in RULES:
        specs.append(
            IntradayMomentumSpec(
                spec_id=f"placebo_{PLACEBO_PREDICTOR}__{rule}",
                predictor=PLACEBO_PREDICTOR,
                rule=rule,
                is_control=True,
                citation="pre-registered control, not a claim of the source paper",
                hypothesis=_hypothesis(PLACEBO_PREDICTOR, rule, control=True),
            )
        )
    return specs


def _hypothesis(predictor: str, rule: str, *, control: bool) -> str:
    if control:
        return (
            "PLACEBO. r2 is the 10:00-10:30 half-hour return: same instrument, same "
            "scale, same intraday-noise structure and the same number of observations "
            "as r1, but no overnight-information content and no role in the paper's "
            "mechanism (overnight news -> informed/day-trader positioning -> unwind "
            "into the close). Should earn nothing. If it earns as much as r1, the r1 "
            "result is not attributable to the paper's mechanism."
        )
    base = {
        "r1": "Eq. (4) on r1, the paper's headline signal (Table 5 Panel A: SRatio 1.08)",
        "r12": "Eq. (4) on r12, the paper's second signal (Table 5 Panel A: SRatio 0.29)",
        "r1_and_r12": "Eq. (5), the paper's two-signal rule (Table 5 Panel A: SRatio 0.98)",
    }[predictor]
    if rule == "sign":
        return base + "; sign rule verbatim, including the r <= 0 => SHORT tie convention"
    return (
        base + f"; DEVIATION: flat when |signal| <= {DEADBAND:.4f} ({DEADBAND * 1e4:.0f}bp). "
        "The paper specifies no threshold; licensed only in direction by its footnote 9 "
        "and its Table 6 volatility terciles. Single a-priori value, not gridded."
    )


# ---------------------------------------------------------------------------
# cost arms
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostArm:
    key: str
    description: str
    one_way_bps: float


# ADDENDUM_01_DATA_AND_COST.md section 4c. The verdict arm was fixed there,
# before any strategy return existed, after the pre-registered EDGE procedure
# was declared failed in public.
COST_ARMS: tuple[CostArm, ...] = (
    CostArm(
        key="cost_free",
        description="0 bp -- the GROSS signal. Attribution only, NEVER a verdict input.",
        one_way_bps=0.0,
    ),
    CostArm(
        key="spy_tick",
        description=(
            "0.1381 bp -- half of SPY's one-cent minimum-tick quoted spread at the "
            "sample-median close of $362.04. The most optimistic defensible number. "
            "Informational."
        ),
        one_way_bps=0.1381,
    ),
    CostArm(
        key="baseline",
        description=(
            "1.0 bp one-way -- THE VERDICT ARM. 7.2x SPY's own quoted half-spread and "
            "4x the paper's entire round-trip spread charge, with the margin reserved "
            "for 15:30 entry impact and 16:00 closing-auction impact (which the paper "
            "assumed away and which Bogousslavsky & Muravyev 2023 measure at ~8.1bp "
            "mean absolute deviation). Honours the pre-registered 0.5bp floor, doubled. "
            "No commission (retail equity commissions went to zero in 2019) and no "
            "overnight borrow (the position is closed at every close)."
        ),
        one_way_bps=1.0,
    ),
    CostArm(
        key="conservative",
        description=(
            "5.0 bp one-way -- intraday_patterns.INTRADAY_COST_BPS, the project-wide "
            "cross-sectional default. Retained and reported, but NOT the verdict: the "
            "scoping memo flagged in advance that applying a broad-cross-section cost "
            "model unchanged to the most liquid ETF in the world would manufacture a "
            "false negative."
        ),
        one_way_bps=5.0,
    ),
)
BASELINE_COST_ARM = "baseline"


def cost_arm(key: str) -> CostArm:
    for arm in COST_ARMS:
        if arm.key == key:
            return arm
    raise IntradayMomentumError(f"unknown cost arm {key!r}; have {[a.key for a in COST_ARMS]}")


# ---------------------------------------------------------------------------
# the paper's OWN predictive regression, re-run out of sample (diagnostic)
# ---------------------------------------------------------------------------

# Draft Table 1 Panel A, whole sample (Feb 1993 - Dec 2013), Newey-West t in
# parentheses -- what the out-of-sample numbers below are compared against:
#   beta_r1  = 0.069*** (4.08), R2 = 1.6%
#   beta_r12 = 0.118*** (2.62), R2 = 1.1%
#   joint    : beta_r1 0.068 (4.14), beta_r12 0.114 (2.60), R2 = 2.6%
PAPER_TABLE1_PANEL_A = {
    "r1": {"beta": 0.069, "t": 4.08, "r2_pct": 1.6},
    "r12": {"beta": 0.118, "t": 2.62, "r2_pct": 1.1},
}
# Newey-West lag truncation. The draft cites Newey & West (1987) but does not
# state its lag choice, so this is DISCLOSED AS THIS PROJECT'S OWN: the standard
# floor(4*(T/100)^(2/9)) rule of thumb, computed from T rather than fixed.
NEWEY_WEST_RULE = "floor(4*(T/100)^(2/9))"


@dataclass(frozen=True)
class PredictiveRegression:
    """One column of the paper's Eq. (2), re-estimated on this out-of-sample
    window. A DIAGNOSTIC ONLY: it is not a spec, it is not in N_local, and it
    never enters the DSR or the verdict. It exists because 'the strategy did not
    clear a multiple-testing gate' and 'the predictive relationship the paper
    documented is not there' are different findings, and only the second one is
    answered by re-running the paper's own test."""

    predictor: str
    n_observations: int
    beta: float
    newey_west_t: float
    r_squared_pct: float
    newey_west_lags: int
    paper_beta: float | None
    paper_t: float | None
    paper_r_squared_pct: float | None


def predictive_regression(panel: pd.DataFrame, predictor: str) -> PredictiveRegression:
    """Eq. (2): r13_t = alpha + beta * predictor_t + eps_t, with Newey-West
    (1987) HAC standard errors, exactly the specification the draft's Table 1
    reports. Uses statsmodels' HAC covariance; no standard-error formula is
    retyped here."""
    import statsmodels.api as sm

    y = panel["r13"].astype(float)
    x = sm.add_constant(panel[predictor].astype(float))
    n = len(y)
    lags = int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))
    fit = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    reference = PAPER_TABLE1_PANEL_A.get(predictor, {})
    return PredictiveRegression(
        predictor=predictor,
        n_observations=n,
        beta=float(fit.params[predictor]),
        newey_west_t=float(fit.tvalues[predictor]),
        r_squared_pct=float(fit.rsquared * 100.0),
        newey_west_lags=lags,
        paper_beta=reference.get("beta"),
        paper_t=reference.get("t"),
        paper_r_squared_pct=reference.get("r2_pct"),
    )


def directional_hit_rate(panel: pd.DataFrame, predictor: str) -> tuple[float, int]:
    """Fraction of days on which sign(predictor) equals sign(r13), and the day
    count. The paper's 'success rate' for eta(r1) is 54.37% against a 50.42%
    Always-Long benchmark (Table 5 Panel A). Gross by construction -- no cost
    enters a sign comparison."""
    signal = panel[predictor].astype(float)
    r13 = panel["r13"].astype(float)
    # Eq. (4)'s tie convention: signal <= 0 is a SHORT call.
    called_up = signal > 0
    correct = np.where(called_up, r13 > 0, r13 <= 0)
    return float(np.mean(correct)), int(len(correct))


# ---------------------------------------------------------------------------
# the replay
# ---------------------------------------------------------------------------


def build_positions(panel: pd.DataFrame, spec: IntradayMomentumSpec) -> pd.Series:
    """w_t in {-1, 0, +1}: the position held over the LAST half-hour of day t.

    THE TIMING CONTRACT. Every quantity entering w_t is measurable by 15:30 ET
    on day t: r1 is known at 10:00, r2 at 10:30, r12 at 15:30, and the previous
    day's close at 16:00 the day before. w_t then earns r13 (15:30 -> 16:00).
    There is no path by which r13 can influence the weight that earned it."""
    if spec.predictor == "r1_and_r12":
        a, b = panel["r1"], panel["r12"]
        if spec.rule == "sign":
            # Eq. (5): long only if BOTH > 0, short only if BOTH <= 0, else flat.
            long_leg = (a > 0) & (b > 0)
            short_leg = (a <= 0) & (b <= 0)
        else:
            long_leg = (a > DEADBAND) & (b > DEADBAND)
            short_leg = (a < -DEADBAND) & (b < -DEADBAND)
        return pd.Series(
            np.where(long_leg, 1.0, np.where(short_leg, -1.0, 0.0)), index=panel.index
        )

    signal = panel[spec.predictor]
    if spec.rule == "sign":
        # Eq. (4): r <= 0 is SHORT, not flat.
        return pd.Series(np.where(signal > 0, 1.0, -1.0), index=panel.index)
    return pd.Series(
        np.where(signal > DEADBAND, 1.0, np.where(signal < -DEADBAND, -1.0, 0.0)),
        index=panel.index,
    )


@dataclass
class IntradayMomentumReplay:
    spec_id: str
    status: str
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    gross_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    positions: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    total_cost: float = 0.0
    n_traded_days: int = 0
    n_flat_days: int = 0
    n_long_days: int = 0
    n_short_days: int = 0
    success_rate: float | None = None
    first_day: str | None = None
    last_day: str | None = None


def replay_spec(
    panel: pd.DataFrame, spec: IntradayMomentumSpec, one_way_bps: float
) -> IntradayMomentumReplay:
    """One spec's daily replay. `.daily_returns` is the NET return of the
    last-half-hour position for each trading day -- one non-overlapping
    observation per day, so periods_per_year is 252 (the paper's own footnote 4
    annualizes the same way: "we still annualize the returns by multiplying a
    factor of 252 because we only trade once per day")."""
    if one_way_bps < 0:
        raise IntradayMomentumError(f"one_way_bps must be non-negative, got {one_way_bps}")
    required = {"r13", spec.predictor} if spec.predictor != "r1_and_r12" else {"r13", "r1", "r12"}
    missing = required - set(panel.columns)
    if missing:
        raise IntradayMomentumError(f"panel missing columns {sorted(missing)}")

    positions = build_positions(panel, spec)
    r13 = panel["r13"].astype(float)
    gross = positions * r13
    # A traded day pays CROSSINGS_PER_TRADED_DAY one-way crossings; a flat day
    # pays nothing. No netting across days -- the position is closed at every
    # close, so tomorrow's entry is a fresh crossing whatever today's sign was.
    cost_per_traded_day = CROSSINGS_PER_TRADED_DAY * one_way_bps / 1e4
    costs = positions.abs() * cost_per_traded_day
    net = gross - costs

    valid = net.notna()
    net, gross, positions, costs = net[valid], gross[valid], positions[valid], costs[valid]
    if net.empty:
        return IntradayMomentumReplay(spec_id=spec.spec_id, status="no_realized_days")

    traded = positions != 0.0
    return IntradayMomentumReplay(
        spec_id=spec.spec_id,
        status="ok",
        daily_returns=net,
        gross_returns=gross,
        positions=positions,
        total_cost=float(costs.sum()),
        n_traded_days=int(traded.sum()),
        n_flat_days=int((~traded).sum()),
        n_long_days=int((positions > 0).sum()),
        n_short_days=int((positions < 0).sum()),
        # The paper's "success rate ... the percentage of trading days of
        # positive returns", measured on days actually in the market.
        success_rate=float((net[traded] > 0).mean()) if traded.any() else None,
        first_day=net.index[0].strftime("%Y-%m-%d"),
        last_day=net.index[-1].strftime("%Y-%m-%d"),
    )


# ---------------------------------------------------------------------------
# screening
# ---------------------------------------------------------------------------


def policy_d_denominators(n_local: int | None = None) -> list[int]:
    """{dsr_n_trials(n_local)} plus the pooled rungs from dsr_policy_n.json.
    Same derivation and same artifact as margin_credit_timing. The default
    is the family's own pre-declared grid size (len(build_family()) = 8), so
    the ladder call-site test (tests/test_dsr_policy_n.py) can call it with
    no arguments like every other family's."""
    from app.services.research_lab.dsr_policy_n import dsr_policy_denominators

    if n_local is None:
        n_local = len(build_family())
    return dsr_policy_denominators(dsr_n_trials(int(n_local)))


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
            periods_per_year=TRADING_DAYS_PER_YEAR,
        ).dsr
        for n in denominators
    }


@dataclass
class IntradayMomentumResult:
    spec_id: str
    predictor: str
    rule: str
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
    success_rate: float | None
    n_traded_days: int
    n_flat_days: int
    n_long_days: int
    n_short_days: int
    total_cost_drag: float
    breakeven_one_way_bps: float | None
    dsr_by_n: dict[int, float | None]
    preservation: dict[str, float | int | bool | None]
    deflated_sharpe: object


def breakeven_one_way_bps(replay: IntradayMomentumReplay) -> float | None:
    """The one-way cost at which this spec's mean NET daily return hits zero.

    mean(gross) - mean(|w|) * CROSSINGS * bps/1e4 = 0. Reported because the
    paper reports no break-even (its section 4.2 gives only a 3.78%/yr total-cost
    bound, which is not one), so this number is labelled as this project's own."""
    traded_fraction = float(replay.positions.abs().mean())
    if traded_fraction <= 0:
        return None
    mean_gross = float(replay.gross_returns.mean())
    return mean_gross / (traded_fraction * CROSSINGS_PER_TRADED_DAY) * 1e4


def screen_intraday_momentum(
    panel: pd.DataFrame,
    specs: list[IntradayMomentumSpec],
    *,
    cost_arm_key: str = BASELINE_COST_ARM,
    denominators: list[int] | None = None,
) -> list[IntradayMomentumResult]:
    """One Sharpe per spec, DSR-corrected at every pre-declared denominator.

    n_trials is fixed at len(specs) -- the family's literal pre-declared size,
    controls included -- raised by dsr_n_trials if that is larger, and NEVER
    shrunk to however many specs happened to survive. sigma_sr is the ddof=1
    standard deviation of every sibling spec's Sharpe from this same pass."""
    arm = cost_arm(cost_arm_key)
    denominators = denominators if denominators is not None else policy_d_denominators(len(specs))
    n_local = dsr_n_trials(len(specs)) if specs else 0

    replays: dict[str, IntradayMomentumReplay] = {}
    for spec in specs:
        replay = replay_spec(panel, spec, arm.one_way_bps)
        if replay.status != "ok":
            logger.info("intraday_momentum spec %s not replayed: %s", spec.spec_id, replay.status)
            continue
        replays[spec.spec_id] = replay

    sharpes = {
        sid: sharpe_ratio(r.daily_returns, periods_per_year=TRADING_DAYS_PER_YEAR)
        for sid, r in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.spec_id: s for s in specs}
    results: list[IntradayMomentumResult] = []
    for spec_id, replay in replays.items():
        spec = spec_by_id[spec_id]
        net = replay.daily_returns
        sharpe = sharpes[spec_id]
        dsr_by_n = dsr_across_denominators(sharpe, net, sigma_sr, denominators)
        deflated_local = compute_deflated_sharpe(
            sharpe, net, n_local, sigma_sr, periods_per_year=TRADING_DAYS_PER_YEAR
        )
        # preservation_score is a STANDARD SECONDARY CHECK WITH NO EXCEPTIONS
        # (CLAUDE.md section 4). Computed for every spec, including controls.
        preservation = compute_preservation_metrics(
            net, dsr=dsr_by_n.get(n_local), periods_per_year=TRADING_DAYS_PER_YEAR
        ).as_dict()
        results.append(
            IntradayMomentumResult(
                spec_id=spec_id,
                predictor=spec.predictor,
                rule=spec.rule,
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
                    replay.gross_returns, periods_per_year=TRADING_DAYS_PER_YEAR
                ),
                annualized_return=float(net.mean() * TRADING_DAYS_PER_YEAR),
                annualized_volatility=float(net.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)),
                success_rate=replay.success_rate,
                n_traded_days=replay.n_traded_days,
                n_flat_days=replay.n_flat_days,
                n_long_days=replay.n_long_days,
                n_short_days=replay.n_short_days,
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
class IntradayMomentumSummary:
    audit: SessionAudit
    panel: pd.DataFrame
    n_local: int
    denominators: list[int]
    sigma_sr_annualized: float | None
    results_by_arm: dict[str, list[IntradayMomentumResult]]

    def baseline_results(self) -> list[IntradayMomentumResult]:
        return self.results_by_arm[BASELINE_COST_ARM]

    def best_candidate(self) -> IntradayMomentumResult | None:
        """Best NON-CONTROL spec on the verdict arm."""
        live = [r for r in self.baseline_results() if not r.is_control]
        return max(live, key=lambda r: r.sharpe_annualized) if live else None

    def best_placebo(self) -> IntradayMomentumResult | None:
        controls = [r for r in self.baseline_results() if r.is_control]
        return max(controls, key=lambda r: r.sharpe_annualized) if controls else None

    def placebo_override_triggered(self) -> bool:
        """PREREGISTRATION section 6 rule 4: if the best placebo's net Sharpe is
        >= the best candidate's, the family is a negative on ATTRIBUTION grounds
        regardless of DSR."""
        best, placebo = self.best_candidate(), self.best_placebo()
        if best is None or placebo is None:
            return False
        return placebo.sharpe_annualized >= best.sharpe_annualized

    def verdict(self, threshold: float = VALIDATED_EDGE_BAR) -> tuple[str, str]:
        best = self.best_candidate()
        if best is None:
            return "no_candidate", "no non-control spec replayed"
        rungs = sorted(best.dsr_by_n)
        n_local = rungs[0]
        local_dsr = best.dsr_by_n.get(n_local)
        if local_dsr is None or local_dsr < threshold:
            return (
                "fails_at_n_local",
                (
                    f"{best.spec_id}: DSR at n_local={n_local} is {local_dsr} < {threshold}. "
                    "Whether this reads DEFINITE_NEGATIVE or UNDERPOWERED is decided by "
                    "the scorecard's power block, not here."
                ),
            )
        failing = [n for n in rungs if (best.dsr_by_n.get(n) or 0.0) < threshold]
        if failing:
            return (
                "unresolved",
                f"{best.spec_id}: clears {threshold} at n_local={n_local} but fails at {failing}",
            )
        return "passes_all_rungs", f"{best.spec_id}: clears {threshold} at every rung {rungs}"


def run_intraday_momentum_screening(bars: pd.DataFrame) -> IntradayMomentumSummary:
    """The whole family, every cost arm. Returns a summary; persistence is a
    SEPARATE call (cross_sectional_persistence.persist_cross_sectional_trial_results),
    never a hidden side effect here -- the convention that module's docstring sets."""
    panel, audit = build_half_hour_panel(bars)
    specs = build_family()
    denominators = policy_d_denominators(len(specs))
    results_by_arm = {
        arm.key: screen_intraday_momentum(
            panel, specs, cost_arm_key=arm.key, denominators=denominators
        )
        for arm in COST_ARMS
    }
    baseline = results_by_arm[BASELINE_COST_ARM]
    sigma_sr = (
        float(np.std([r.sharpe_annualized for r in baseline], ddof=1))
        if len(baseline) >= 2
        else None
    )
    return IntradayMomentumSummary(
        audit=audit,
        panel=panel,
        n_local=dsr_n_trials(len(specs)),
        denominators=denominators,
        sigma_sr_annualized=sigma_sr,
        results_by_arm=results_by_arm,
    )
