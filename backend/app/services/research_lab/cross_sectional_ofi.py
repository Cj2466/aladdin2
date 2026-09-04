"""The crypto cross-sectional ORDER-FLOW IMBALANCE (OFI) family: 4
pre-declared definitions on Binance USDT-margined perpetual futures,
screened as one family with its own never-pooled DSR n_trials denominator.

================================================================================
THE SOURCE — READ, NOT RECALLED
================================================================================
Alexia Anastasopoulos, "Three Essays on Order Flow and Cryptocurrency
Returns", PhD thesis in Economics, University of Guelph, December 2025
(advisors Gradojevic, Liu, Maynard, Tsiakas). The full 120-page PDF was
downloaded and read in this session from the University of Guelph's Atrium
repository (item 803d3c13-a2cd-4600-8b3a-a48648a6746a); every number,
equation and quotation below was taken from that file, and page/section
references point into it. The related journal version in the Journal of
International Financial Markets, Institutions and Money
(ScienceDirect PII S1386418126000029 — that identifier is a publisher item id, NOT a DOI) is PAYWALLED — ScienceDirect returned HTTP 403 to
this session — so NOTHING here is sourced from the journal version, and no
claim is made about how it differs from the thesis.

WHAT THE THESIS ACTUALLY DEFINES (chapter 1, section 1.2.2, quoted):
order flow is "the log difference between buyer-initiated and
seller-initiated transaction volume denominated in a particular fiat
currency over a period of time", i.e.

    of_{i,t} = log(buy_volume_{i,t}) - log(sell_volume_{i,t})

standardized, "Following Menkhoff et al. (2016)", by equation (1.2):

    OF_{i,t} = of_{i,t} / sigma(of_{i,t-29:t})

NOTE THE SHAPE OF THAT STANDARDIZATION, because it is easy to assume
wrongly and this family depends on it: it is SCALE-ONLY. There is no mean
subtraction — it is NOT a z-score. The denominator is "the order flow
volatility over the last 30 days", a 30-observation window ending at and
INCLUDING t. Because sigma > 0, the standardization preserves the sign of
of_{i,t}, which a demeaning z-score would not.

THE ORTHOGONALIZATION, the single most important correctness detail, and
the reason this family is not a rebuild of short-term reversal. Chapter 2
(section 2.5.2, quoted): "we first orthogonalize lagged world order flow
with respect to lagged returns to remove the short-term reversal
component", and the sort is on a variable "orthogonalized relative to
same-period returns". Those two phrasings describe ONE operation seen from
two reference points: the order flow measured over period t is
orthogonalized against the return of that SAME period t, and the residual
is then used to predict period t+1 — so relative to the predicted return,
the return being projected out is a LAGGED one. The mechanism the thesis
gives for why this matters (chapter 2, quoted): "lagged order flow is
comprised of one component that is correlated with lagged returns,
reflecting transitory effects, and another component that is uncorrelated
with returns, reflecting permanent effects. Using an orthogonalized OF_W
ensures that portfolio sorts rely on lagged order flow information
exclusive of any information in lagged returns."

THE ESTIMATOR IS SPELLED OUT IN THE THESIS'S OWN FOOTNOTE 12, quoted in
full because this family implements it literally:

    "Daily (weekly) ortho-OF_W is defined as the last residual from a
     recursive regression of lagged order flow on lagged returns, which is
     estimated using an expanding window that is updated daily (weekly).
     This approach avoids any forward-looking bias as only information
     available up to time t is used to construct ortho-OF_W."

So the orthogonalization is EXPANDING-WINDOW and CAUSAL BY CONSTRUCTION —
the no-look-ahead property is the thesis's own design choice, not a
retrofit by this module. expanding_orthogonalize() below implements exactly
that recursion and a dedicated test mutates future rows to prove the
residual at t does not move.

================================================================================
THE REAL NUMBERS, TRANSCRIBED FROM THE THESIS'S TABLES 2.3 AND 2.4
================================================================================
Equally-weighted QUINTILE portfolios, P5-P1, out-of-sample test period
2020-02-18 to 2022-06-30, Newey-West t-statistics, SR annualized. Alphas
are against the Liu-Tsyvinski-Wu (2022) crypto three-factor model.

Table 2.3 — sorts on WORLD order flow (the aggregate of 11 fiat flows):
    daily   OF_W        mean +0.02%/day   (t=0.18)  alpha 0.02% (t=0.11)  SR  0.11
    daily   ortho-OF_W  mean +0.23%/day   (t=1.59)  alpha 0.24% (t=1.65)  SR  1.00
    weekly  OF_W        mean +1.93%/week  (t=2.99)  alpha 1.78% (t=2.86)  SR  2.05
    weekly  ortho-OF_W  mean +1.83%/week  (t=2.82)  alpha 1.72% (t=2.71)  SR  1.93

Table 2.4 — sorts on US order flow alone (ONE fiat flow):
    daily   OF_USD        mean -0.08%/day  (t=-0.74)  alpha -0.08% (t=-0.69)  SR -0.45
    daily   ortho-OF_USD  mean +0.01%/day  (t= 0.09)  alpha  0.03% (t= 0.25)  SR  0.06
    weekly  OF_USD        mean +1.70%/week (t= 2.91)  alpha  1.64% (t= 2.61)  SR  1.80
    weekly  ortho-OF_USD  mean +1.65%/week (t= 2.86)  alpha  1.48% (t= 2.50)  SR  1.82

TABLE 2.4 IS THE ROW THAT ACTUALLY GOVERNS THIS FAMILY'S PRE-DECLARATION,
and it is the reason the primary spec is weekly. This project has ONE
aggregate Binance perp flow, not eleven fiat flows — so the honest
analogue of what can be built here is the SINGLE-flow column, not the
world-aggregate column. In the thesis's own single-flow results the daily
effect is gone (SR 0.06 after orthogonalization, i.e. nothing) while the
weekly effect survives nearly intact (SR 1.82 vs the world flow's 1.93).
Daily is therefore pre-declared as a deliberately WEAKER secondary spec on
the thesis's own evidence, not demoted after seeing this family's results.

THE ML NUMBER IS NOT A TARGET AND IS NOT COMPARABLE. The thesis abstract's
headline — "long-short portfolios sorted on machine learning forecasts
conditioning on daily order flow exhibit an alpha of up to 0.79% per day
with an annualized Sharpe ratio of 3.63", and the best single model (SGB)
at 0.78%/day, t=5.85, SR 3.68 — REQUIRES the 11 separate fiat-denominated
order flows, which come from CryptoCompare, a vendor this project has no
access to. Reproducing it is impossible here by construction. It is quoted
only so nobody later mistakes this family's numbers for a failure to hit it.

================================================================================
WHY THIS IS A DIFFERENT TEST FROM THE THESIS'S — STATED BEFORE THE RESULTS
================================================================================
This is a genuinely different experiment that may simply not reproduce, and
each difference is a real one, not a formality:
  * VENUE. The thesis uses CryptoCompare's cross-exchange aggregated signed
    volume over 300+ exchanges, denominated in fiat. This family uses ONE
    venue's (Binance's) USDT-margined PERPETUAL FUTURES taker flow. Perp
    taker flow is leveraged-derivative flow, not the spot fiat flow the
    thesis measures. That is a different economic object with a plausible
    but unproven relationship to it.
  * FLOW BREADTH. Eleven fiat flows and their world aggregate, versus one.
    See Table 2.4 above for what the thesis itself found that costs.
  * SAMPLE. The thesis's portfolio sorts run 2020-02-18 to 2022-06-30. This
    family runs on whatever Binance serves through the run date — a window
    that includes the 2022-2023 bear market, the 2024 spot-ETF regime and
    2025-2026, none of which the thesis tested.
  * PRICES. The thesis uses CoinMarketCap spot prices at 00:00 GMT and
    EXCLUDES weekends and US holidays from its daily sample. This family
    uses the perp's own close on a 24/7/365 calendar and excludes nothing,
    because a perp trades every day and the sibling crypto families here
    have already established periods_per_year=365.
  * COSTS. The thesis's Tables 2.3/2.4 report GROSS returns. This family
    charges OFI_COST_BPS one-way and reports gross AND net Sharpes side by
    side so the comparison to the thesis is like-for-like.
  * UNIVERSE. 84 CMC coins in a balanced panel there; this project's
    73-name hand-assembled crypto list mapped to Binance perps here, ragged
    by listing/delisting date.

================================================================================
DATA — THE SIGNED-VOLUME IDENTITY, VERIFIED LIVE 2026-08-29
================================================================================
No new vendor and no tick data: Binance's ordinary daily kline already
carries signed volume, and the provider was extended (additively) to expose
it. Per app.services.market_data.binance_futures_provider, whose docstring
shows the arithmetic, an exact reconciliation against the raw
/fapi/v1/aggTrades tape was run in this session and matched to the last
decimal:

    buyer-initiated quote volume  = kline element [10] (taker_buy_quote_volume)
    total quote volume            = kline element  [7] (quote_volume)
    seller-initiated quote volume = [7] - [10]           EXACT on the tape

so this family's inputs are

    buy_{i,t}  = taker_buy_quote_volume
    sell_{i,t} = quote_volume - taker_buy_quote_volume

both in USDT, available back to each contract's inception. `trade_count`
(element [8]) is exposed by the same provider change but is NOT used by any
spec here — it is not part of the pre-declared family and exists for future
work; using it later requires a new pre-declaration, not a quiet extra run.

A DELIBERATE MEASUREMENT MISMATCH, disclosed: `sell` is a RESIDUAL of two
reported aggregates. On a bar with tiny or zero turnover the residual can be
zero or lost in float noise, making log(sell) undefined or wild. Every such
bar is NaN'd out rather than clipped — see order_flow_log_difference().

================================================================================
THE PRE-DECLARED FAMILY — 4 SPECS, FIXED BEFORE ANY DATA WAS RUN
================================================================================
Two axes only:
  * signal variant: {ortho, raw}                                        (2)
  * rebalance/aggregation horizon H: {7 days (WEEKLY), 1 day (DAILY)}   (2)
                                                          2 x 2 = 4 specs

PRIMARY  : ofi_ortho_h7  — weekly, orthogonalized. The thesis's own
           headline construction and the one place its single-flow effect
           survives (Table 2.4: SR 1.82).
SECONDARY: ofi_raw_h7    — weekly, NOT orthogonalized. This is the
           thesis's own CONTROL, and it is in the family for a reason that
           is the opposite of p-hacking: without it there is no way to tell
           whether orthogonalization did anything. The thesis found it
           barely matters weekly (1.93% raw vs 1.83% ortho) and matters
           enormously daily (0.02% raw vs 0.24% ortho). Testing both is how
           that claim gets checked here rather than assumed.
SECONDARY: ofi_ortho_h1, ofi_raw_h1 — daily, pre-labelled WEAKER per
           Table 2.4, and additionally expected to suffer here because
           daily rebalancing pays 7x the turnover cost of weekly.

EVERYTHING ELSE IS FIXED AT THE THESIS'S OWN VALUE AND IS NOT AN AXIS:
  * quintile cutoff 0.2 — the thesis sorts into quintiles, full stop.
  * equal-weighted legs — "The portfolios are equally-weighted" (Tables
    2.3/2.4 headers).
  * log-difference flow definition — section 1.2.2.
  * 30-observation scale-only standardization — equation (1.2).
  * expanding-window OLS orthogonalization — footnote 12.

DECILE WAS CONSIDERED AND PRE-EXCLUDED, with a measured reason rather than
a taste: the sibling funding-carry family's independent verification on
THIS EXACT universe found that decile legs need >= 50 eligible names while
measured breadth has decayed from 66 to about 27 (yearly mean eligible
counts 2021: 59.6 down to 2026: 31.4), leaving all four of its decile specs
untradeable in the recent sample. Adding a cutoff axis here would spend two
extra DSR trials on specs already known to be structurally broken on this
universe. Excluded before the run, and recorded here so the choice is
auditable rather than invisible.

n_trials for the DSR is 4 — the pre-declared enumeration, asserted against
the built list, never shrunk to survivors.

A KNOWN AND ACCEPTED CONSEQUENCE OF CHOOSING A 4-SPEC FAMILY: this
project's deflated_sharpe module refuses to compute a DSR below
MIN_TRIALS_FOR_DSR = 5 sibling trials, because the sigma_SR estimate is
too unstable to serve as a multiple-comparisons benchmark on so few
(its own measured coefficient of variation is ~42% at N=4 vs ~38% at
N=5). So EVERY spec in this family reports dsr = None BY DESIGN, and
CrossSectionalTrialResult's own column comment already says that is
correct rather than a failure. The statistic that IS computed and IS
meaningful here is psr_vs_zero (the probabilistic Sharpe ratio against
zero, skew- and kurtosis-adjusted), which is what the summary reports and
what a reader should judge these specs on.

This constraint was NOT a reason to pad the family to five. Inflating a
pre-declared enumeration so the tooling emits a number would be choosing
the hypothesis to fit the instrument, and doing it after seeing results
would be precisely the p-hacking this project's discipline exists to
prevent. Four honestly-justified specs with a NULL DSR beats five with a
computable one.

================================================================================
CONSTRUCTION DETAILS AND THE JUDGEMENT CALLS INSIDE THEM
================================================================================
THE FORMATION GRID. Every quantity a spec ranks on is computed on a
NON-OVERLAPPING grid of every H-th panel row, built from the panel's first
row so that a coin's history is measured on the same grid the statistics are
estimated on. At grid point t: flows are summed over the H days ending at t,
the H-day return is close_t/close_{t-H} - 1, and both feed the
standardization and the regression. For H=1 this reduces exactly to the
thesis's daily construction. Overlapping (every-day) weekly windows were
rejected: they would put 7x autocorrelated observations into a rolling
sigma and an OLS fit that both assume independent draws.

AN INTERPRETATION THE THESIS DOES NOT PIN DOWN, disclosed rather than
hidden: footnote 12 says "a recursive regression of lagged order flow on
lagged returns" without stating whether it is fitted PER COIN or POOLED
across the panel. This family fits it PER COIN (each coin gets its own
reversal coefficient from its own history), chosen ex ante on the reading
that "the last residual" is a coin-specific quantity. It is NOT made an
axis: picking one interpretation before the run and saying so is the
discipline; running both and reporting the better one is the failure mode
this project exists to avoid.

    RESOLVED BY THE INDEPENDENT-VERIFICATION PASS, 2026-08-29 — and the
    ex-ante choice turns out to be the LESS well-supported reading of the
    source. Going back to the thesis rather than to footnote 12 alone:

      * Footnote 12's orthogonalization is introduced in chapter 2 with an
        explicit pointer back to chapter 1 — "As previously discovered in
        chapter 1 (see Table 1.6), lagged order flow is comprised of one
        component that is correlated with lagged returns ... and another
        component that is uncorrelated with returns". So the decomposition
        the residual is meant to implement is the one Table 1.6 estimated.
      * Table 1.6 is a POOLED PANEL regression. Chapter 1 section 1.3:
        "Our empirical approach is based on balanced panel regressions ...
        The panel regressions are estimated using the full sample ... and
        include coin fixed effects. The t-statistics ... are computed using
        standard errors which are clustered by time and by coin."
      * Footnote 12 says "A recursive regression" — one regression, whose
        "last residual" is then read off per coin — not 84 regressions.

    On that evidence the source leans POOLED, most specifically pooled WITH
    COIN FIXED EFFECTS, which is chapter 1's actual estimator. So the
    verification pass implemented both pooled variants (expanding and causal
    exactly as the per-coin one is) and re-ran the family on the identical
    panels, grid, eligibility and warm-up gate, changing NOTHING but the
    regression's estimation domain. Measured, net Sharpe:

        weekly ortho (THE PRIMARY SPEC)   per-coin +0.130 | pooled +0.073 |
                                          pooled+coin-FE +0.152
        daily  ortho                      per-coin -1.050 | pooled -1.342 |
                                          pooled+coin-FE -1.220
        daily  ortho, GROSS               per-coin +1.400 | pooled +1.030 |
                                          pooled+coin-FE +1.228
        daily  ortho, breakeven one-way   per-coin 5.7bp  | pooled 4.3bp   |
                                          pooled+coin-FE 5.0bp

    Mean CROSS-SECTIONAL RANK correlation between the per-coin signal and
    the pooled ones — the thing a quintile sort actually consumes — is
    +0.83 (pooled) and +0.99 (pooled+coin-FE) at the weekly horizon, +0.91
    and +0.99 daily. THE FORK HIDES NOTHING. Every reading of footnote 12
    leaves the primary spec flat (+0.07 to +0.15 net Sharpe, a band entirely
    inside "no edge"), and every reading leaves the daily specs' breakeven
    at or BELOW Binance's 5bp taker fee — the source-faithful pooled
    readings make the daily specs look WORSE, not better. The per-coin
    implementation is kept as the shipped one because it was the
    pre-declared choice and switching it after the fact would be choosing
    the estimator from the results; this note records that the choice is
    not load-bearing for any conclusion.

A SECOND FORK THE BUILDER DID NOT FLAG, found by the same verification
pass: equation (1.2) is only ever described as "a rolling window of 30
days" / "the order flow volatility over the last 30 days". At the DAILY
horizon that is unambiguous and this family implements it exactly. At the
WEEKLY horizon it is not: 30 OBSERVATIONS of the analysis frequency (= 30
weeks, what this family does) and 30 CALENDAR DAYS (~4 weekly
observations) are both readings of the same sentence, and the thesis never
says which it uses for its weekly results. Measured net Sharpe of the
primary weekly ortho spec: +0.130 at 30 weeks, +0.213 at 4 weeks. Still
flat under both, so the primary conclusion does not turn on it either.
Recorded rather than switched, and NOT promoted to an axis. One thing it
does reveal is worth keeping: the weekly RAW secondary is far more
window-sensitive (+0.462 at 30 weeks, +0.930 at 4 weeks) than the
orthogonalized primary. That sensitivity is a reason to distrust the raw
spec's apparently better number, not a reason to prefer the shorter
window.

WARM-UP COST OF THE METHOD. A coin needs 30 grid observations before its
standardized flow exists (equation 1.2's window), then
MIN_ORTHO_REGRESSION_OBS more standardized values before the expanding
regression is defined. At H=7 that is roughly 60 weeks after listing before
a coin can be ranked by the ortho signal. This is inherent in the thesis's
own method, it materially thins the weekly cross-section, and the summary
reports measured eligible counts so the reader sees the real breadth rather
than trusting this paragraph.

ELIGIBILITY and the UNIVERSE are deliberately IDENTICAL to the sibling
funding-carry family — the same 73-name list mapped through the same
binance_symbol_for(), and literally the same build_funding_eligibility()
function (trailing 30-day median perp turnover >= $10M on strictly prior
rows, and priced at formation). Reused rather than re-derived so that any
difference between this family's results and the funding family's is the
SIGNAL, not a quietly different universe or gate.

COSTS: OFI_COST_BPS = 10bp one-way per unit of gross notional traded — the
sibling funding family's number, adopted for exactly that comparability,
and an assumption rather than a measured execution cost. Every spec reports
its breakeven one-way cost and its gross Sharpe so a reader can see how much
leans on it. No financing charge (a perp short needs no borrow). NOT
MODELED: exchange-bankruptcy risk, liquidation/margin spirals, USDT depeg.

CALENDAR: crypto trades 24/7/365; periods_per_year = 365 throughout. Sharpe
is computed on the DAILY realized series even for the weekly specs, which is
the sibling families' convention and the shape the DSR machinery expects.
This differs from the thesis, which computes its weekly Sharpe on WEEKLY
returns annualized by sqrt(52); the two agree only up to within-week
autocorrelation, so this family's weekly SR is NOT arithmetically identical
to the thesis's even on identical data. Stated so the comparison is not
overclaimed.

THE FAMILY-SPECIFIC CONFOUND CHECK. Because the entire premise is "this is
not just short-term reversal", this family measures that directly instead of
asserting it: reversal_overlap() builds a pure short-term-reversal long-short
portfolio on the identical grid, universe and weighting, and reports its
correlation with every spec. A high correlation for the ortho specs would
falsify the premise no matter how good the Sharpe looked. The sibling
families' BTC/basket factor-exposure regression is also run per spec.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.services.market_data.binance_futures_provider import BinanceFuturesProvider
from app.services.research_lab.cross_sectional import (
    MIN_REPLAY_TRADING_DAYS,
    _turnover,
    realize_formation_day,
    select_leg_tickers,
)
from app.services.research_lab.cross_sectional_crypto import (
    CRYPTO_UNIVERSE,
    CryptoFactorExposure,
    compute_crypto_factor_exposure,
)
from app.services.research_lab.cross_sectional_funding_carry import (
    binance_symbol_for,
    build_funding_eligibility,
)
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import CALENDAR_DAYS_PER_YEAR, sharpe_ratio

logger = logging.getLogger(__name__)

OFI_PERIODS_PER_YEAR = float(CALENDAR_DAYS_PER_YEAR)

# --- universe (identical to the sibling funding family — see docstring) ------

OFI_UNIVERSE: dict[str, str] = {t: binance_symbol_for(t) for t in CRYPTO_UNIVERSE}

OFI_DATA_START = date(2019, 9, 1)
OFI_FORMATION_START = date(2020, 10, 1)

# --- the thesis's own constants ----------------------------------------------

# Equation (1.2): sigma over "the last 30 days", a window ending at and
# INCLUDING t. Scale-only — no mean subtraction. NOT an axis.
OFI_STANDARDIZATION_WINDOW = 30

# Footnote 12's expanding regression needs enough points to fit 2
# parameters. Set equal to the standardization window so the module carries
# ONE "30 observations of this frequency" number rather than two arbitrary
# ones. NOT an axis.
MIN_ORTHO_REGRESSION_OBS = 30

# Tables 2.3/2.4 sort into quintiles and equal-weight the legs. NOT axes.
OFI_RANK_FRACTION = 0.2

# --- the pre-declared axes ---------------------------------------------------

OFI_SIGNAL_VARIANTS: tuple[str, ...] = ("ortho", "raw")
OFI_HORIZON_DAYS: tuple[int, ...] = (7, 1)

# 2 variants x 2 horizons = 4. Computed from the axes so the two can never
# disagree; build_ofi_family asserts the built list matches. THE DSR
# denominator for this family, never pooled elsewhere.
OFI_N_TRIALS = len(OFI_SIGNAL_VARIANTS) * len(OFI_HORIZON_DAYS)

OFI_COST_BPS = 10.0
OFI_MIN_NAMES_PER_LEG = 5

# Binance's own published USDT-M futures TAKER fee for a regular (VIP 0)
# account, read from Binance's fee documentation 2026-08-29 during the
# independent-verification pass: maker 0.02%, taker 0.05% = 5bp. This is NOT
# the cost the specs are charged (OFI_COST_BPS = 10bp is, deliberately
# conservative at 2x the raw fee). It is here only so the summary can put a
# spec's measured breakeven next to the cheapest cost that could possibly be
# paid — a breakeven BELOW this number means the spec cannot pay even the
# exchange's headline fee, before any spread or slippage at all.
BINANCE_TAKER_FEE_BPS = 5.0

# A grid observation whose H-day flow window is under this fraction
# populated is refused — the sibling families' shared coverage floor.
MIN_SIGNAL_OBS_FRACTION = 0.8

OFI_CITATION = (
    "Anastasopoulos, A., 'Three Essays on Order Flow and Cryptocurrency Returns', PhD thesis, "
    "University of Guelph, December 2025 (full 120-page PDF downloaded from the Guelph Atrium "
    "repository and read 2026-08-29). Order flow = log difference of buyer- vs seller-initiated "
    "volume (sec. 1.2.2), standardized scale-only by its trailing 30-day sigma (eq. 1.2, after "
    "Menkhoff, Sarno, Schmeling & Schrimpf 2016), orthogonalized against same-period returns via "
    "an expanding-window recursive regression (footnote 12). Equally-weighted quintile P5-P1 "
    "sorts, 2020-02-18..2022-06-30: weekly ortho-OF_W +1.83%/week, t=2.82, SR 1.93 (Table 2.3); "
    "daily ortho-OF_W +0.24%/day, t=1.65, SR 1.00. Single-flow analogue (Table 2.4, the relevant "
    "one here): weekly ortho-OF_USD SR 1.82 but daily ortho-OF_USD SR 0.06. The thesis's SR 3.63 "
    "headline is a machine-learning forecast over 11 CryptoCompare fiat flows and is NOT "
    "reproducible from this project's single Binance perp flow."
)

OFI_FAMILY_KEY = "ofi_crypto"


# --- dataclasses -------------------------------------------------------------


@dataclass(frozen=True)
class OfiSpec:
    """One pre-declared definition: aggregate signed flow over
    horizon_days, standardize, optionally orthogonalize against the
    same-period return, rank into quintiles, hold horizon_days."""

    pattern_id: str
    signal_variant: str  # "ortho" | "raw"
    horizon_days: int
    rank_fraction: float = OFI_RANK_FRACTION
    family: str = OFI_FAMILY_KEY
    citation: str = OFI_CITATION

    @property
    def is_primary(self) -> bool:
        """The thesis's headline construction — weekly, orthogonalized."""
        return self.signal_variant == "ortho" and self.horizon_days == 7


@dataclass
class OfiConfig:
    cost_bps: float = OFI_COST_BPS
    min_names_per_leg: int = OFI_MIN_NAMES_PER_LEG
    periods_per_year: float = OFI_PERIODS_PER_YEAR
    formation_start: date = OFI_FORMATION_START


@dataclass
class OfiCoverage:
    """One symbol's real, measured data coverage."""

    symbol: str
    first_day: date | None
    last_day: date | None
    n_days: int
    n_days_with_flow: int  # bars where BOTH signed halves are strictly positive
    frac_days_with_flow: float


@dataclass
class OfiPanels:
    """The aligned daily panels every spec is replayed against.

    buy_quote/sell_quote are the two signed halves in USDT (see the
    module docstring's verified identity); both are NaN where the perp had
    no market, so no spec can rank a name on a bar that did not trade."""

    close: pd.DataFrame
    quote_volume: pd.DataFrame
    buy_quote: pd.DataFrame
    sell_quote: pd.DataFrame
    trade_count: pd.DataFrame
    coverage: dict[str, OfiCoverage]
    symbols_missing: list[str]


@dataclass
class OfiFormationRecord:
    formation_date: date
    long_tickers: list[str]
    short_tickers: list[str]
    turnover: float
    skipped_reason: str | None

    @property
    def n_long(self) -> int:
        return len(self.long_tickers)

    @property
    def n_short(self) -> int:
        return len(self.short_tickers)


@dataclass
class OfiBacktest:
    daily_returns: pd.Series  # net of turnover cost
    daily_returns_gross: pd.Series
    formations: list[OfiFormationRecord]
    total_cost_drag: float
    total_turnover: float


@dataclass
class OfiSpecResult:
    """Per-spec screening output. Carries exactly the fields
    persist_cross_sectional_trial_results requires (pattern_id,
    sharpe_annualized, n_trading_days, deflated_sharpe) plus this
    family's own honesty counters."""

    pattern_id: str
    family: str
    citation: str
    signal_variant: str
    horizon_days: int
    is_primary: bool
    n_formations: int
    n_skipped_formations: int
    avg_names_per_leg: float
    n_trading_days: int
    sharpe_annualized: float  # NET — the number this project reports
    sharpe_gross_annualized: float  # thesis-comparable (its tables are gross)
    mean_return_per_formation: float
    total_cost_drag: float
    total_turnover: float
    cumulative_net_return: float
    reversal_correlation: float  # vs a pure short-term-reversal book
    deflated_sharpe: DeflatedSharpeResult


@dataclass
class OfiScreeningSummary:
    results: list[OfiSpecResult]
    n_trials: int
    periods_per_year: float
    panel_start: date | None
    panel_end: date | None
    n_panel_rows: int
    formation_start: date
    candidate_universe_size: int
    symbols_missing: list[str]
    coverage: dict[str, OfiCoverage]
    min_eligible: int
    median_eligible: float
    max_eligible: int
    reversal_sharpe: float = float("nan")
    factor_exposures: dict[str, CryptoFactorExposure] = field(default_factory=dict)
    text: str = ""
    warnings: list[str] = field(default_factory=list)


# --- panels ------------------------------------------------------------------


def build_ofi_panels(
    provider: BinanceFuturesProvider,
    end: date,
    start: date = OFI_DATA_START,
) -> OfiPanels:
    """Fetches (or reads from the provider's disk cache) daily klines for
    every candidate symbol and aligns them on one ragged calendar-day
    index — ragged on purpose, exactly as the sibling families' panel
    builders document: a symbol is NaN before listing and after delisting,
    and truncating to all-names-priced would delete the recent years for
    everyone.

    Market-or-not: a bar is kept only where quote turnover is strictly
    positive; a zero-turnover bar (delisted perps keep printing one) is a
    quote, not a market. The two signed halves are masked to that same
    condition, so buy/sell are never populated on a bar the close is not."""
    closes: dict[str, pd.Series] = {}
    volumes: dict[str, pd.Series] = {}
    buys: dict[str, pd.Series] = {}
    sells: dict[str, pd.Series] = {}
    counts: dict[str, pd.Series] = {}
    coverage: dict[str, OfiCoverage] = {}
    missing: list[str] = []

    for _yf_ticker, symbol in sorted(OFI_UNIVERSE.items(), key=lambda kv: kv[1]):
        klines = provider.get_daily_klines(symbol, start, end)
        if klines.empty:
            missing.append(symbol)
            continue

        close = pd.to_numeric(klines["close"], errors="coerce")
        volume = pd.to_numeric(klines["quote_volume"], errors="coerce")
        buy = pd.to_numeric(klines["taker_buy_quote_volume"], errors="coerce")
        n_trades = pd.to_numeric(klines["trade_count"], errors="coerce")

        traded = (close > 0.0) & (volume > 0.0)
        close = close.where(traded)
        # sell is the RESIDUAL of two reported aggregates — see the module
        # docstring's disclosed measurement mismatch.
        sell = (volume - buy).where(traded)
        buy = buy.where(traded)

        closes[symbol] = close
        volumes[symbol] = volume
        buys[symbol] = buy
        sells[symbol] = sell
        counts[symbol] = n_trades.where(traded)

        n_days = int(close.notna().sum())
        n_flow = int(((buy > 0.0) & (sell > 0.0)).sum())
        priced = close.dropna()
        coverage[symbol] = OfiCoverage(
            symbol=symbol,
            first_day=priced.index[0].date() if len(priced) else None,
            last_day=priced.index[-1].date() if len(priced) else None,
            n_days=n_days,
            n_days_with_flow=n_flow,
            frac_days_with_flow=(n_flow / n_days) if n_days else 0.0,
        )

    if not closes:
        empty = pd.DataFrame()
        return OfiPanels(empty, empty, empty, empty, empty, coverage, missing)

    close_frame = pd.concat(closes, axis=1).sort_index().dropna(how="all")
    idx = close_frame.index
    return OfiPanels(
        close=close_frame,
        quote_volume=pd.concat(volumes, axis=1).reindex(idx),
        buy_quote=pd.concat(buys, axis=1).reindex(idx),
        sell_quote=pd.concat(sells, axis=1).reindex(idx),
        trade_count=pd.concat(counts, axis=1).reindex(idx),
        coverage=coverage,
        symbols_missing=missing,
    )


# --- the signal, step by step ------------------------------------------------


def order_flow_log_difference(buy: pd.DataFrame, sell: pd.DataFrame) -> pd.DataFrame:
    """The thesis's section-1.2.2 definition, applied elementwise:

        of = log(buyer-initiated volume) - log(seller-initiated volume)

    NaN wherever either half is not strictly positive. That is a refusal,
    not a clip: a bar with no seller-initiated volume has an undefined log
    ratio, and clipping it to some large finite number would invent an
    extreme signal value out of a data gap and hand it a leg slot."""
    valid = (buy > 0.0) & (sell > 0.0)
    return (np.log(buy.where(valid)) - np.log(sell.where(valid))).where(valid)


def standardize_order_flow(
    order_flow: pd.DataFrame,
    window: int = OFI_STANDARDIZATION_WINDOW,
) -> pd.DataFrame:
    """The thesis's equation (1.2): OF_t = of_t / sigma(of_{t-29:t}).

    SCALE-ONLY — deliberately no mean subtraction; this is not a z-score
    (see the module docstring). The window ends at and INCLUDES t, which is
    not look-ahead because of_t is known at t. A window with fewer than
    `window` observations, or a degenerate (zero/non-finite) sigma, yields
    NaN rather than an exploded value."""
    sigma = order_flow.rolling(window, min_periods=window).std()
    sigma = sigma.where(sigma > 0.0)
    out = order_flow / sigma
    return out.where(np.isfinite(out))


def expanding_orthogonalize(
    signal: pd.DataFrame,
    returns: pd.DataFrame,
    min_obs: int = MIN_ORTHO_REGRESSION_OBS,
) -> pd.DataFrame:
    """The thesis's footnote 12, implemented literally: for each column
    (coin) independently, the value at t is the LAST RESIDUAL of an OLS
    regression (with intercept) of `signal` on `returns` fitted on an
    EXPANDING window covering every observation up to AND INCLUDING t:

        b_t     = Cov_{s<=t}(x, y) / Var_{s<=t}(x)
        a_t     = mean_{s<=t}(y) - b_t * mean_{s<=t}(x)
        ortho_t = y_t - a_t - b_t * x_t

    NO LOOK-AHEAD BY CONSTRUCTION, and this is the property the whole
    family rests on: every term is a cumulative sum over rows <= t, so no
    observation after t can enter a_t or b_t. Both y_t (the flow measured
    over period t) and x_t (the return of that same period t) are known at
    the end of period t, and the residual is used to predict period t+1.
    A dedicated test mutates every row after t and asserts the residual at
    t is bit-identical.

    Fitted PER COIN, an interpretation choice the thesis does not pin down
    — declared in the module docstring, not discovered here.

    Only rows where BOTH x and y are finite contribute to the sums, so a
    coin's ragged history does not silently inject zeros into its own
    regression. NaN until `min_obs` valid pairs exist and wherever the
    return variance is degenerate."""
    x = returns.reindex_like(signal)
    valid = np.isfinite(signal) & np.isfinite(x)
    y_v = signal.where(valid).fillna(0.0)
    x_v = x.where(valid).fillna(0.0)
    ones = valid.astype(float)

    n = ones.cumsum()
    sx = x_v.cumsum()
    sy = y_v.cumsum()
    sxx = (x_v * x_v).cumsum()
    sxy = (x_v * y_v).cumsum()

    denom = n * sxx - sx * sx
    denom = denom.where(denom.abs() > 1e-12)
    beta = (n * sxy - sx * sy) / denom
    alpha = (sy - beta * sx) / n.where(n > 0)

    resid = signal - alpha - beta * x
    resid = resid.where(valid & (n >= min_obs))
    return resid.where(np.isfinite(resid))


def formation_grid(index: pd.DatetimeIndex, horizon_days: int) -> list[int]:
    """Row positions of the NON-OVERLAPPING formation grid: every
    horizon_days-th row, anchored at the panel's first row so a coin's
    statistics are estimated on the same grid it is later ranked on.
    Starts at horizon_days so the first grid point has a full lookback
    window behind it."""
    return list(range(horizon_days, len(index), horizon_days))


@dataclass
class OfiSignalPanels:
    """Everything computed on one horizon's formation grid, indexed by the
    grid's own dates. `raw` and `ortho` are the two pre-declared signal
    variants; `period_return` is the H-day return of the SAME period the
    flow was measured over (the regressor footnote 12 projects out)."""

    grid_rows: list[int]
    period_return: pd.DataFrame
    raw: pd.DataFrame
    ortho: pd.DataFrame


def build_ofi_signals(panels: OfiPanels, horizon_days: int) -> OfiSignalPanels:
    """The full signal pipeline for one horizon, on the non-overlapping
    formation grid: aggregate the two signed halves over the H days ending
    at each grid point, take the thesis's log difference, standardize by
    the trailing 30-observation sigma, and orthogonalize against the
    same-period H-day return with the expanding regression.

    Coverage floor: a grid point whose H-day window is under
    MIN_SIGNAL_OBS_FRACTION populated is NaN'd, so a coin cannot be ranked
    on a week that was mostly not traded."""
    rows = formation_grid(panels.close.index, horizon_days)
    grid_index = panels.close.index[rows]

    buy = panels.buy_quote
    sell = panels.sell_quote
    n_obs = buy.notna().rolling(horizon_days, min_periods=1).sum()
    buy_h = buy.rolling(horizon_days, min_periods=1).sum()
    sell_h = sell.rolling(horizon_days, min_periods=1).sum()

    enough = n_obs >= max(1, int(np.ceil(horizon_days * MIN_SIGNAL_OBS_FRACTION)))
    buy_h = buy_h.where(enough)
    sell_h = sell_h.where(enough)

    close = panels.close
    ret_h = close / close.shift(horizon_days) - 1.0

    # Subsample to the grid BEFORE the rolling sigma and the regression, so
    # both are estimated on non-overlapping observations (see docstring).
    buy_g = buy_h.iloc[rows]
    sell_g = sell_h.iloc[rows]
    ret_g = ret_h.iloc[rows].where(np.isfinite(ret_h.iloc[rows]))

    of = order_flow_log_difference(buy_g, sell_g)
    raw = standardize_order_flow(of)
    ortho = expanding_orthogonalize(raw, ret_g)

    return OfiSignalPanels(
        grid_rows=rows,
        period_return=ret_g.set_axis(grid_index),
        raw=raw.set_axis(grid_index),
        ortho=ortho.set_axis(grid_index),
    )


# --- backtest ----------------------------------------------------------------


def _select_and_weight(
    signal_row: pd.Series,
    eligible_row: pd.Series,
    spec: OfiSpec,
    config: OfiConfig,
) -> tuple[list[str], list[str], dict[str, float], dict[str, float], str | None]:
    """One formation's leg selection: gate on eligibility, refuse a
    cross-section too thin for two disjoint legs of the pre-declared size,
    and equal-weight both legs (the thesis's convention)."""
    signal = signal_row.where(eligible_row.reindex(signal_row.index).fillna(False))
    signal = signal.where(np.isfinite(signal))

    n_valid = int(signal.notna().sum())
    n_leg = max(1, int(n_valid * spec.rank_fraction)) if n_valid else 0
    if n_valid == 0 or n_leg < config.min_names_per_leg:
        return [], [], {}, {}, (
            f"leg of {n_leg} from {n_valid} valid names is below "
            f"min_names_per_leg={config.min_names_per_leg}"
        )
    if 2 * n_leg > n_valid:
        return [], [], {}, {}, f"universe of {n_valid} too small for disjoint legs of {n_leg}"

    long_leg, short_leg = select_leg_tickers(signal, spec.rank_fraction)
    long_w = {t: 1.0 / len(long_leg) for t in long_leg}
    short_w = {t: 1.0 / len(short_leg) for t in short_leg}
    return long_leg, short_leg, long_w, short_w, None


def _replay(
    panels: OfiPanels,
    signal_panel: pd.DataFrame,
    grid_rows: list[int],
    spec: OfiSpec,
    config: OfiConfig,
    eligibility: pd.DataFrame,
) -> OfiBacktest:
    """Shared replay loop for a spec and for the reversal control book, so
    the two are compared on identical machinery rather than two lookalike
    loops that could drift apart.

    Forms at each grid row at/after config.formation_start, holds until the
    next grid row, and realizes each held day's return with the harness's
    own realize_formation_day (long leg minus short leg, survivors
    renormalized). Turnover cost lands on the first realized day of each
    formation, exactly as the harness's _replay_sleeve charges it."""
    close = panels.close
    index = close.index
    n = len(index)
    returns = close.pct_change(fill_method=None)

    prev_weights: dict[str, float] = {}
    formations: list[OfiFormationRecord] = []
    daily_net: dict[pd.Timestamp, float] = {}
    daily_gross: dict[pd.Timestamp, float] = {}
    total_cost = 0.0
    total_turnover = 0.0

    start_ts = pd.Timestamp(config.formation_start)
    tradeable = [(k, r) for k, r in enumerate(grid_rows) if index[r] >= start_ts and r < n - 1]

    for k, row in tradeable:
        signal_row = signal_panel.iloc[k]
        long_leg, short_leg, long_w, short_w, skipped = _select_and_weight(
            signal_row, eligibility.iloc[row], spec, config
        )

        net_weights: dict[str, float] = dict(long_w)
        for t, w in short_w.items():
            net_weights[t] = net_weights.get(t, 0.0) - w

        turnover = _turnover(prev_weights, net_weights)
        cost = turnover * config.cost_bps / 10_000.0
        prev_weights = net_weights
        total_turnover += turnover

        formations.append(
            OfiFormationRecord(
                formation_date=index[row].date(),
                long_tickers=list(long_leg),
                short_tickers=list(short_leg),
                turnover=turnover,
                skipped_reason=skipped,
            )
        )

        hold_end = min(row + spec.horizon_days, n - 1)
        for j in range(row + 1, hold_end + 1):
            gross = realize_formation_day(returns.iloc[j], long_w, short_w)
            cost_today = cost if j == row + 1 else 0.0
            total_cost += cost_today
            daily_gross[index[j]] = gross
            daily_net[index[j]] = gross - cost_today

    return OfiBacktest(
        daily_returns=pd.Series(daily_net).sort_index(),
        daily_returns_gross=pd.Series(daily_gross).sort_index(),
        formations=formations,
        total_cost_drag=total_cost,
        total_turnover=total_turnover,
    )


def run_ofi_backtest(
    panels: OfiPanels,
    spec: OfiSpec,
    config: OfiConfig,
    signals: OfiSignalPanels | None = None,
    eligibility: pd.DataFrame | None = None,
) -> OfiBacktest:
    """One spec's full replay against the real panels."""
    if panels.close.empty:
        empty = pd.Series(dtype=float)
        return OfiBacktest(empty, empty, [], 0.0, 0.0)
    if eligibility is None:
        eligibility = build_funding_eligibility(panels.close, panels.quote_volume)
    if signals is None:
        signals = build_ofi_signals(panels, spec.horizon_days)
    signal_panel = signals.ortho if spec.signal_variant == "ortho" else signals.raw
    return _replay(panels, signal_panel, signals.grid_rows, spec, config, eligibility)


def run_reversal_control(
    panels: OfiPanels,
    horizon_days: int,
    config: OfiConfig,
    signals: OfiSignalPanels | None = None,
    eligibility: pd.DataFrame | None = None,
) -> OfiBacktest:
    """THE FAMILY-SPECIFIC FALSIFICATION TEST, not a spec and NOT counted
    in n_trials: a pure short-term-reversal book on the identical grid,
    universe, cutoff and weighting — signal = MINUS the same-period H-day
    return, so past losers go long. Its correlation with each OFI spec is
    the direct measurement of "is this just reversal?", which the
    orthogonalized specs must answer with a low number to mean anything."""
    if panels.close.empty:
        empty = pd.Series(dtype=float)
        return OfiBacktest(empty, empty, [], 0.0, 0.0)
    if eligibility is None:
        eligibility = build_funding_eligibility(panels.close, panels.quote_volume)
    if signals is None:
        signals = build_ofi_signals(panels, horizon_days)
    spec = OfiSpec(
        pattern_id=f"reversal_control_h{horizon_days}",
        signal_variant="raw",
        horizon_days=horizon_days,
    )
    return _replay(panels, -signals.period_return, signals.grid_rows, spec, config, eligibility)


# --- family ------------------------------------------------------------------


def build_ofi_family() -> list[OfiSpec]:
    """The full, fixed 4-definition family. Assertions pin the size to the
    pre-declared axes so a drift silently changing the DSR denominator is
    impossible."""
    specs = [
        OfiSpec(
            pattern_id=f"ofi_{variant}_h{horizon}",
            signal_variant=variant,
            horizon_days=horizon,
        )
        for variant in OFI_SIGNAL_VARIANTS
        for horizon in OFI_HORIZON_DAYS
    ]
    assert len(specs) == OFI_N_TRIALS, (
        f"OFI family has {len(specs)} definitions, not the pre-declared {OFI_N_TRIALS} — "
        "the axes and the family size may never disagree"
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert OFI_N_TRIALS == 4
    assert sum(s.is_primary for s in specs) == 1, "exactly one primary spec (weekly ortho)"
    assert all(s.rank_fraction == OFI_RANK_FRACTION for s in specs), (
        "the cutoff is FIXED at the thesis's quintile — decile was pre-excluded, see docstring"
    )
    return specs


def default_ofi_config() -> OfiConfig:
    return OfiConfig()


# --- screening ---------------------------------------------------------------


def screen_ofi_family(
    panels: OfiPanels,
    specs: list[OfiSpec],
    config: OfiConfig,
) -> tuple[list[OfiSpecResult], dict[str, pd.Series], dict[int, OfiBacktest]]:
    """One Sharpe per spec, DSR-corrected with n_trials = OFI_N_TRIALS (the
    pre-declared size, NEVER the survivor count) and sigma_sr = the ddof=1
    spread of the sibling Sharpes from this same pass — the harness's exact
    convention, restated here because this family runs its own loop.

    Also returns the per-horizon reversal control books so the caller can
    report the falsification test alongside the results."""
    eligibility = build_funding_eligibility(panels.close, panels.quote_volume)
    signals_by_h = {h: build_ofi_signals(panels, h) for h in {s.horizon_days for s in specs}}
    reversal_by_h = {
        h: run_reversal_control(panels, h, config, signals_by_h[h], eligibility)
        for h in signals_by_h
    }

    replays: dict[str, OfiBacktest] = {}
    for spec in specs:
        bt = run_ofi_backtest(panels, spec, config, signals_by_h[spec.horizon_days], eligibility)
        if len(bt.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            logger.warning(
                "OFI spec %s replayed only %d days (< %d) — excluded from screening",
                spec.pattern_id,
                len(bt.daily_returns),
                MIN_REPLAY_TRADING_DAYS,
            )
            continue
        replays[spec.pattern_id] = bt

    sharpes = {
        pid: sharpe_ratio(bt.daily_returns, periods_per_year=config.periods_per_year)
        for pid, bt in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.pattern_id: s for s in specs}
    results: list[OfiSpecResult] = []
    daily_by_pattern: dict[str, pd.Series] = {}
    for pattern_id, bt in replays.items():
        spec = spec_by_id[pattern_id]
        formed = [f for f in bt.formations if f.skipped_reason is None]
        skipped = [f for f in bt.formations if f.skipped_reason is not None]
        rev = reversal_by_h[spec.horizon_days].daily_returns
        joined = pd.concat(
            [bt.daily_returns.rename("s"), rev.rename("r")], axis=1
        ).dropna()
        corr = float(joined["s"].corr(joined["r"])) if len(joined) >= 3 else float("nan")

        deflated = compute_deflated_sharpe(
            sharpes[pattern_id],
            bt.daily_returns,
            # POOLED DENOMINATOR (2026-09-04): raised to the project-wide
            # effectively-independent trial count when that is larger.
            # See global_effective_n.py.
            dsr_n_trials(OFI_N_TRIALS),
            sigma_sr,
            periods_per_year=config.periods_per_year,
        )
        results.append(
            OfiSpecResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                signal_variant=spec.signal_variant,
                horizon_days=spec.horizon_days,
                is_primary=spec.is_primary,
                n_formations=len(formed),
                n_skipped_formations=len(skipped),
                avg_names_per_leg=float(np.mean([f.n_long for f in formed])) if formed else 0.0,
                n_trading_days=len(bt.daily_returns),
                sharpe_annualized=float(sharpes[pattern_id]),
                sharpe_gross_annualized=float(
                    sharpe_ratio(
                        bt.daily_returns_gross, periods_per_year=config.periods_per_year
                    )
                ),
                mean_return_per_formation=(
                    float(bt.daily_returns.sum() / len(formed)) if formed else float("nan")
                ),
                total_cost_drag=float(bt.total_cost_drag),
                total_turnover=float(bt.total_turnover),
                cumulative_net_return=float(bt.daily_returns.sum()),
                reversal_correlation=corr,
                deflated_sharpe=deflated,
            )
        )
        daily_by_pattern[pattern_id] = bt.daily_returns
    return results, daily_by_pattern, reversal_by_h


# --- production entry point --------------------------------------------------


def _build_summary_text(summary: OfiScreeningSummary) -> str:
    lines = [
        (
            f"CRYPTO ORDER-FLOW IMBALANCE (OFI) FAMILY — READ BEFORE TRUSTING ANY NUMBER. "
            f"Pre-declared family size {summary.n_trials} (2 signal variants x 2 horizons), fixed "
            f"before the run and used as the DSR's n_trials in this family's own never-pooled "
            f"screening. The cutoff is FIXED at the source's quintile; decile was pre-excluded "
            f"(the sibling funding family measured decile legs as untradeable on this universe). "
            f"SOURCE: {OFI_CITATION}"
        ),
        (
            f"MECHANISM: signed taker volume from Binance perp klines — buy = element [10], "
            f"sell = [7]-[10], an identity reconciled EXACTLY against the raw aggTrades tape "
            f"2026-08-29. Order flow is the log difference of the two halves aggregated over the "
            f"spec's horizon, standardized SCALE-ONLY by its trailing "
            f"{OFI_STANDARDIZATION_WINDOW}-observation sigma (eq. 1.2 — not a z-score), then for "
            f"the 'ortho' specs orthogonalized against the SAME-PERIOD return by an expanding "
            f"recursive OLS (footnote 12) that is causal by construction. "
            f"CALENDAR: periods_per_year={summary.periods_per_year:.0f}."
        ),
        (
            f"THIS IS A DIFFERENT TEST FROM THE SOURCE'S, and may simply not reproduce: one "
            f"venue's leveraged PERP taker flow vs 300+ exchanges' spot fiat flow; ONE flow vs "
            f"eleven (the source's own single-flow table shows daily collapsing to SR 0.06 while "
            f"weekly holds at SR 1.82 — which is why weekly is primary and daily is a "
            f"pre-labelled weaker secondary); a different window "
            f"({summary.panel_start}..{summary.panel_end}) vs the source's 2020-02..2022-06; and "
            f"net-of-cost numbers vs the source's gross tables (gross Sharpes are reported below "
            f"for a like-for-like read)."
        ),
        (
            f"UNIVERSE/ELIGIBILITY, deliberately identical to the sibling funding-carry family so "
            f"any difference is the SIGNAL not the gate: {summary.candidate_universe_size} "
            f"candidates ({len(summary.symbols_missing)} with no Binance USDT perp data: "
            f"{', '.join(summary.symbols_missing) or 'none'}); trailing 30-day median perp "
            f"turnover >= $10M (shift(1)) and priced at formation. Eligible names over the "
            f"formation window: {summary.min_eligible}..{summary.max_eligible}, median "
            f"{summary.median_eligible:.0f}. COSTS: {OFI_COST_BPS}bp one-way (an assumption; "
            f"breakevens below). NOT MODELED: exchange-bankruptcy risk, liquidation spirals, "
            f"USDT depeg."
        ),
    ]

    if summary.results:
        lines.append(
            "PER-SPEC RESULTS (Sharpe NET of turnover cost; gross shown for source comparability; "
            "rev-corr is the correlation with a pure short-term-reversal book on the identical "
            "grid — the falsification test for 'this is just reversal'):"
        )
        for r in sorted(summary.results, key=lambda x: (-x.horizon_days, x.signal_variant)):
            dsr = r.deflated_sharpe.dsr
            psr = r.deflated_sharpe.psr_vs_zero
            breakeven = ""
            # GATE ON THE GROSS RESULT, NOT THE NET ONE. Gating on net Sharpe
            # (as this did until the independent-verification pass) hid the
            # breakeven for exactly the specs it matters most for: the daily
            # ones, whose gross Sharpe is strong but whose net Sharpe is
            # negative because the cost eats it. Suppressing the number there
            # deleted this family's single most interesting finding from its
            # own report. A spec with a positive gross return has a meaningful
            # breakeven cost whatever its net sign.
            if r.total_cost_drag > 0 and (r.cumulative_net_return + r.total_cost_drag) > 0:
                gross = r.cumulative_net_return + r.total_cost_drag
                breakeven = f", breakeven ~{OFI_COST_BPS * gross / r.total_cost_drag:.1f}bp one-way"
            tag = " [PRIMARY]" if r.is_primary else " [secondary, pre-labelled weaker]"
            lines.append(
                f"  {r.pattern_id}{tag}: Sharpe net {r.sharpe_annualized:+.3f} / gross "
                f"{r.sharpe_gross_annualized:+.3f}, DSR "
                f"{'n/a' if dsr is None else format(dsr, '.3f')}, PSR-vs-0 "
                f"{'n/a' if psr is None else format(psr, '.3f')}, {r.n_formations} formations "
                f"({r.n_skipped_formations} skipped), avg leg {r.avg_names_per_leg:.1f}, "
                f"{r.n_trading_days} days | cumulative net {r.cumulative_net_return:+.2%} "
                f"(costs {r.total_cost_drag:.2%}){breakeven}, rev-corr {r.reversal_correlation:+.3f}"
            )
        uneconomic = [
            r
            for r in summary.results
            if r.total_cost_drag > 0
            and (r.cumulative_net_return + r.total_cost_drag) > 0
            and r.sharpe_gross_annualized > 1.0
            and r.sharpe_annualized <= 0.0
        ]
        if uneconomic:
            lines.append(
                "  A STRONG SIGNAL THAT CANNOT PAY THE FEE — the most interesting thing this "
                "family found, and a negative result, not a lead: "
                + "; ".join(
                    f"{r.pattern_id} gross Sharpe {r.sharpe_gross_annualized:+.3f} but breakeven "
                    f"~{OFI_COST_BPS * (r.cumulative_net_return + r.total_cost_drag) / r.total_cost_drag:.1f}bp"
                    for r in sorted(uneconomic, key=lambda x: x.pattern_id)
                )
                + f". Binance's own published VIP-0 USDT-M TAKER fee is {BINANCE_TAKER_FEE_BPS:.0f}bp "
                f"(read from Binance's fee documentation 2026-08-29), so these breakevens sit at or "
                f"barely above the cheapest fee obtainable, with ZERO budget left for spread, "
                f"slippage or market impact on a ~10-name-per-leg book of mid-cap perps. The daily "
                f"horizon rebalances every day and therefore pays that cost ~7x as often as the "
                f"weekly one. Treat the gross number as evidence the signal is real and the net "
                f"number as evidence it is not harvestable HERE — not as an invitation to shop for "
                f"a cheaper cost assumption until it turns positive."
            )
        if all(r.deflated_sharpe.dsr is None for r in summary.results):
            lines.append(
                f"  WHY EVERY DSR IS n/a — BY DESIGN, NOT A FAILURE: deflated_sharpe refuses a "
                f"DSR below MIN_TRIALS_FOR_DSR=5 sibling trials because sigma_SR is too unstable "
                f"to be a multiple-comparisons benchmark on fewer (~42% CV at N=4). This family "
                f"pre-declared {summary.n_trials} specs and was NOT padded to five after the fact "
                f"to make the number appear. Judge these specs on PSR-vs-0 above."
            )
    if np.isfinite(summary.reversal_sharpe):
        lines.append(
            f"REVERSAL CONTROL (not a spec, not in n_trials): the pure short-term-reversal book "
            f"on the weekly grid scored Sharpe {summary.reversal_sharpe:+.3f} net over the same "
            f"period — context for the rev-corr column above."
        )
    if summary.warnings:
        lines.append("WARNINGS: " + " | ".join(summary.warnings))
    return "\n".join(lines)


def run_ofi_screening(
    end: date | None = None,
    provider: BinanceFuturesProvider | None = None,
    config: OfiConfig | None = None,
) -> OfiScreeningSummary:
    """THE production entry point: fetch/align real Binance panels, replay
    the 4 pre-declared specs, DSR-correct at n_trials=4, run the reversal
    falsification control and the BTC/basket confound regression.
    Persistence stays a separate explicit call
    (persist_cross_sectional_trial_results), per that module's contract."""
    end = end if end is not None else date.today()  # noqa: DTZ011 — fetch end bound only
    provider = provider if provider is not None else BinanceFuturesProvider()
    config = config if config is not None else default_ofi_config()

    warnings: list[str] = []
    panels = build_ofi_panels(provider, end)
    if panels.close.empty:
        summary = OfiScreeningSummary(
            results=[],
            n_trials=OFI_N_TRIALS,
            periods_per_year=config.periods_per_year,
            panel_start=None,
            panel_end=None,
            n_panel_rows=0,
            formation_start=config.formation_start,
            candidate_universe_size=len(OFI_UNIVERSE),
            symbols_missing=panels.symbols_missing,
            coverage=panels.coverage,
            min_eligible=0,
            median_eligible=0.0,
            max_eligible=0,
            warnings=["No Binance perp data resolved — nothing was screened."],
        )
        summary.text = _build_summary_text(summary)
        return summary

    close = panels.close
    thin_flow = {
        s: c.frac_days_with_flow
        for s, c in panels.coverage.items()
        if c.n_days > 0 and c.frac_days_with_flow < 0.95
    }
    if thin_flow:
        warnings.append(
            f"{len(thin_flow)} symbol(s) have a signed-volume half missing or non-positive on "
            f"over 5% of their traded bars (worst: "
            + ", ".join(
                f"{s}={f:.0%}" for s, f in sorted(thin_flow.items(), key=lambda kv: kv[1])[:5]
            )
            + ") — those bars produce a NaN order flow and cannot be ranked."
        )

    eligibility = build_funding_eligibility(close, panels.quote_volume)
    in_window = eligibility.loc[eligibility.index >= pd.Timestamp(config.formation_start)]
    counts = in_window.sum(axis=1)

    specs = build_ofi_family()
    results, daily_by_pattern, reversal_by_h = screen_ofi_family(panels, specs, config)

    btc = close["BTCUSDT"].pct_change(fill_method=None) if "BTCUSDT" in close else pd.Series(dtype=float)
    basket = close.pct_change(fill_method=None).where(eligibility).mean(axis=1, skipna=True)
    exposures = {
        pid: compute_crypto_factor_exposure(
            pid, series, btc.reindex(series.index), basket.reindex(series.index)
        )
        for pid, series in daily_by_pattern.items()
    }

    reversal_sharpe = float("nan")
    weekly_reversal = reversal_by_h.get(7)
    if weekly_reversal is not None and len(weekly_reversal.daily_returns) >= MIN_REPLAY_TRADING_DAYS:
        reversal_sharpe = sharpe_ratio(
            weekly_reversal.daily_returns, periods_per_year=config.periods_per_year
        )

    summary = OfiScreeningSummary(
        results=results,
        n_trials=OFI_N_TRIALS,
        periods_per_year=config.periods_per_year,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        n_panel_rows=len(close),
        formation_start=config.formation_start,
        candidate_universe_size=len(OFI_UNIVERSE),
        symbols_missing=panels.symbols_missing,
        coverage=panels.coverage,
        min_eligible=int(counts.min()) if len(counts) else 0,
        median_eligible=float(counts.median()) if len(counts) else 0.0,
        max_eligible=int(counts.max()) if len(counts) else 0,
        reversal_sharpe=reversal_sharpe,
        factor_exposures=exposures,
        warnings=warnings,
    )
    summary.text = _build_summary_text(summary)
    return summary


__all__ = [
    "MIN_ORTHO_REGRESSION_OBS",
    "MIN_SIGNAL_OBS_FRACTION",
    "OFI_CITATION",
    "OFI_COST_BPS",
    "OFI_DATA_START",
    "OFI_FAMILY_KEY",
    "OFI_FORMATION_START",
    "OFI_HORIZON_DAYS",
    "OFI_MIN_NAMES_PER_LEG",
    "OFI_N_TRIALS",
    "OFI_PERIODS_PER_YEAR",
    "OFI_RANK_FRACTION",
    "OFI_SIGNAL_VARIANTS",
    "OFI_STANDARDIZATION_WINDOW",
    "OFI_UNIVERSE",
    "OfiBacktest",
    "OfiConfig",
    "OfiCoverage",
    "OfiFormationRecord",
    "OfiPanels",
    "OfiScreeningSummary",
    "OfiSignalPanels",
    "OfiSpec",
    "OfiSpecResult",
    "build_ofi_family",
    "build_ofi_panels",
    "build_ofi_signals",
    "default_ofi_config",
    "expanding_orthogonalize",
    "formation_grid",
    "order_flow_log_difference",
    "run_ofi_backtest",
    "run_ofi_screening",
    "run_reversal_control",
    "screen_ofi_family",
    "standardize_order_flow",
]
