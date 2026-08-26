"""Round C: a cross-sectional ranking / portfolio-formation backtest harness.

WHY THIS EXISTS (and why it is genuinely new capability rather than a
disguised reuse of engine.py): three prior honest pattern-mining rounds
(29 + 29 + 212 = 270 tested definitions, all single-ticker time-series,
see intraday_patterns.py) came back cleanly negative with a
cost-dominated-noise signature — symmetric losses on long/short pattern
pairs, both-direction momentum negative — consistent with too-frequent
trading eating the 10bps-per-round-trip cost assumption. The literature
review that motivated this round found that almost every robust,
well-replicated behavioral-finance anomaly (1) operates on multi-day-to-
multi-month holding periods, amortizing costs over far more return, and
(2) is CROSS-SECTIONAL: rank all stocks on a signal at a formation date,
go long the top decile and short the bottom decile, hold for a horizon,
reform. "One ticker's own history predicts that ticker's own next bar" —
the only shape engine.py/ou_pairs.py/momentum.py can express — is a
different (and, in 270 honest trials here, empirically empty) hypothesis
class. The ranking/formation step below is therefore new; what IS reused
is everything downstream that already works on a daily return series:
metrics.sharpe_ratio and deflated_sharpe.compute_deflated_sharpe, both
completely unmodified, exactly as intraday_patterns.py reused them.

POINT-IN-TIME UNIVERSE — the load-bearing correctness requirement of this
module. Survivorship bias is MORE severe for a cross-sectional decile
strategy than for the per-ticker screens built before it: a decile
portfolio formed from TODAY's index constituents silently excludes every
company that failed enough to leave the index, biasing the whole
strategy's return stream (especially the SHORT leg, which is precisely
where the failed names would have lived), not just which candidates got
surfaced. So eligibility here is decided per formation date by
sp500_membership_history.was_member — a ticker enters the ranked cross-
section on formation date d only if it was ACTUALLY an S&P 500 member on
d — never by ticker_universe.SCREENING_UNIVERSE (a snapshot of today)
applied retroactively. This is structural (the signal function is never
even shown an ineligible ticker's column), not a disclosed-after-the-fact
warning like build_membership_warnings — a deliberate strengthening for
the cross-sectional case, per the reasoning above.

What point-in-time membership CANNOT fix (carried over verbatim from
sp500_membership_history's KNOWN LIMITS, which every reader of results
from this module must internalize): ~48% of the members that left the
index in the trailing 5 years have NO yfinance price history at all.
Those tickers will be correctly ELIGIBLE at historical formation dates
here, but absent from the price data, so they simply never rank.

Direction of the residual bias, reasoned through rather than assumed:
for a LONG-ONLY benchmark the standard result is that this kind of gap
biases returns upward (the worst performers are silently dropped from
the sample average). This harness is long-short, and that intuition
does not automatically transfer. Most of these signals (52-week-high
nearness, capital-gains overhang) would plausibly rank a name in real
distress toward the BOTTOM decile — i.e. exactly a short candidate —
while it was still an index member and, in many real cases, still had
tradeable price history for much of its decline (index removal usually
lags the worst of the deterioration). Where the missing ~48% coincides
with that decline window, its absence denies the SHORT leg its best
opportunities, which understates the strategy's edge rather than
flattering it. The long_universe_hedged variant points the same way:
excluding chronic underperformers from the "hedge the whole eligible
universe" leg inflates that universe's average return, so shorting it
is a bigger headwind than the true population would be. Net: this
residual bias is probably NOT reliably "upward" for this long-short
design the way it would be for a long-only one — plausibly the
opposite, though not confidently signed either way without the real
data. That uncertainty, not a presumed direction, is the honest reason
it still needs a delisted-securities price vendor (Norgate, CRSP,
Sharadar) — already on the project's pending-paid-decisions list — to
actually close, not just disclose.

A SEPARATE, currently wholly undisclosed gap, independent of the above:
no borrow cost or short-availability constraint is modeled anywhere in
this harness — every bottom-decile name is assumed freely shortable at
the flat DEFAULT_XS_COST_BPS. In live markets the names these signals
route to the short leg (steep decliners, negative capital-gains
overhang, i.e. the same distressed profile as the paragraph above) are
disproportionately likely to be hard-to-borrow or carry a real negative
rebate — a cost this backtest cannot see. This DOES bias any positive
short-leg contribution to look more achievable live than it would be —
the one factor identified here that points the ordinary "optimistic"
direction, and it applies regardless of how the survivorship question
above resolves.

Recycled-ticker containment (the "silently wrong data" failure mode
sp500_membership_history documents — e.g. yfinance "FB" history restarts
2025-06-26 as a different company): a ticker's prices can only influence
this harness through (a) its signal at a formation date on which it was a
member, or (b) realization during a hold that began at such a formation.
Membership at formation gates (a) directly; (b) extends at most
holding_days past a formation, and every observed ticker recycling gap is
years, not months — so recycled data structurally cannot reach a
portfolio here. A removal DURING a hold keeps contributing until the hold
ends, which is correct (index removal is not a forced sale) and is
exactly the post-removal return window survivorship bias normally eats.

CONVENTIONS, each with its justification:
 * Formation at the close: the signal is computed from data up to and
   including formation date d's close, the position is assumed established
   at that same close, and returns realize from d+1 onward (close-to-
   close). This is the standard convention of the cited literature
   (George & Hwang 2004 and Grinblatt & Han 2005 both form at month-end
   using month-end prices) and is mildly optimistic about executing at the
   exact close print — disclosed, not hidden.
 * Magnitude-weighted legs, long-minus-short: daily portfolio return is the
   long leg's magnitude-weighted mean daily return minus the short leg's
   (see _leg_weights) — each ranked member's weight grows with its own
   distance from the leg's boundary (the marginal, just-barely-selected
   member), capped at MAX_WEIGHT_MULTIPLE times an equal share so one
   outlier can't dominate a leg. This is the SAME self-financing
   dollar-neutral assumption metrics.sharpe_ratio already documents as its
   reason for not subtracting a risk-free rate (each leg's weights still
   sum to exactly 1.0), so that function is reused unmodified without
   silently violating its contract. A leg's weights degrade to equal
   weight whenever there is no magnitude information to weight by (a leg
   of exactly one member, or every member tied) — this is a refinement of
   the equal-weight convention, not a departure from it at the boundary.
 * Leg weighting is pluggable per spec (CrossSectionalSpec.leg_weighting,
   dispatched by _resolve_leg_weights), not hard-wired to magnitude:
   "magnitude" (above) is every family's default and Round C's only mode;
   "value" — added for Build D1's idiosyncratic-volatility family, see
   cross_sectional_ivol.py's citations — weights a leg's members by real
   point-in-time market cap instead, through the SAME normalize-then-cap-
   at-MAX_WEIGHT_MULTIPLE machinery (_apply_weight_cap), falling back to
   magnitude weighting for the whole leg whenever any member's market cap
   is unusable at that formation (see _resolve_leg_weights). Both schemes
   still leave each leg's weights summing to exactly 1.0, so the
   self-financing argument two sentences up holds unchanged either way.
 * "Long-only" variants are implemented as long-top-decile MINUS the
   equal-weighted eligible universe ("long_universe_hedged"), not as a raw
   unhedged long: a raw long-only S&P-constituent decile's Sharpe is
   mostly the market's own Sharpe, which would (1) break
   metrics.sharpe_ratio's self-financing assumption above and (2) make
   sibling-Sharpe comparisons in the DSR's sigma_sr meaningless across a
   family mixing hedged and unhedged streams. Hedging with the universe
   isolates the cross-sectional selection effect, which is the hypothesis
   actually under test. The universe-hedge side itself stays
   equal-weighted always — there is no rank cutoff for "the whole eligible
   universe" to weight members' distance from.
 * Leg weights are treated as re-set every day within a hold at zero cost
   (each day's leg return is that day's magnitude-weighted mean member
   return, renormalized over any names still trading) — the same
   zero-cost-rebalancing convention an equal-weighted portfolio already
   assumes, just with the weights no longer forced uniform. The disclosed
   cost driver is formation-date turnover, priced exactly like engine.py's
   |position change| convention: cost_bps per unit of gross notional
   traded, one-way (see DEFAULT_XS_COST_BPS) — turnover is measured on
   these same magnitude-weighted net targets, so a reformation that only
   reshuffles weights among unchanged leg members (no membership change)
   still correctly costs something, unlike the old equal-weight version
   where an unchanged membership list always cost exactly zero.
 * A ticker whose price disappears mid-hold (delisting, acquisition) drops
   out of its leg's mean from that day by DEFAULT — economically,
   liquidation at the last available price with proceeds redistributed
   across the remaining names, the standard fallback absent true delisting
   returns (see the survivorship disclosure above for why the true returns
   are unavailable). config.impute_delisting_returns is an opt-in
   alternative to this default, generic on the harness (not special-cased
   to any one family): when a ticker's price permanently stops appearing
   anywhere later in the loaded frame — distinct from a transient data gap
   that later recovers, see _compute_delisting_positions — the day it
   disappears is charged a fixed imputed loss
   (config.imputed_delisting_return, defaulting to
   DEFAULT_IMPUTED_DELISTING_RETURN) instead of being silently dropped.
   Built for Build D2's long-horizon reversal family, whose LONG leg is
   disproportionately the population most likely to delist mid-hold (past
   losers) — dropping it flatters exactly that family the most — but left
   off by default (config.impute_delisting_returns=False) so every family
   screened before this option existed (Round C, Round D) is byte-for-byte
   unaffected unless it deliberately opts in.
 * Formation cadence defaults to holding_days (non-overlapping holds — the
   whole portfolio reforms every holding_days trading days). Overlapping
   Jegadeesh-Titman-style cohorts are an opt-in alternative via
   spec.cohort_formation_days (a stagger shorter than holding_days): the
   harness then runs holding_days // cohort_formation_days independent,
   staggered "sleeves" (see _replay_sleeve), each an ordinary non-
   overlapping replay in its own right, and blends whichever sleeves are
   concurrently active on a given day by simple equal-weighted average of
   their own net daily returns — the standard construction for smoothing
   an overlapping-cohort return stream without changing the expected
   return of any one sleeve. Left unset (None), cadence == holding_days,
   which collapses to exactly ONE sleeve starting at the same position the
   pre-overlap algorithm always used — so every existing spec (Round C,
   Round D — none of which set this field) is byte-for-byte unaffected.
   Built for Build D2, whose ~11.6-year usable point-in-time history gives
   only 3-4 truly independent non-overlapping 756-day windows; overlapping
   quarterly cohorts trade formation-date noise for a smoother, larger
   daily-observation count WITHOUT manufacturing additional independent
   long-run observations — that distinction must stay disclosed wherever
   this option is used (see cross_sectional_patterns_d2.py's own
   independent-window disclosure), not treated as if it were free
   statistical power.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import was_member

# One-way cost per unit of gross notional traded at a formation — mirrors
# momentum.py's DEFAULT_COST_BPS = 5.0 single-leg convention (itself half of
# pairs' two-leg 10bps), not independently recalibrated. A full long-short
# formation from flat trades gross notional 2.0 (buy 1.0 of longs, sell 1.0
# of shorts), so establishing the book costs ~10bps of equity, and each
# reformation costs 10bps times the fraction of the book actually replaced
# — far below the every-bar cost bleed the Round A/B post-mortem diagnosed,
# which is the entire economic thesis of this round.
DEFAULT_XS_COST_BPS = 5.0

# A leg with fewer names than this is a stock pick, not a decile portfolio —
# its "cross-sectional" return would be dominated by idiosyncratic single-
# name noise. 5 mirrors deflated_sharpe.MIN_TRIALS_FOR_DSR's
# smallest-sample-that-isn't-dominated-by-2-3-draws reasoning (verified
# there by simulation); an engineering judgment call at the same honesty
# register, not an independently calibrated constant.
DEFAULT_MIN_NAMES_PER_LEG = 5

# Same floor as momentum.py's MIN_OUT_OF_SAMPLE_TRADING_DAYS (itself
# mirroring ou_pairs.py) — below this many realized daily returns, a Sharpe
# is too thin to mean anything and the spec is dropped from screening
# results entirely rather than surfaced with misleading precision.
MIN_REPLAY_TRADING_DAYS = 60

# Cap on how much more than an equal share any single leg member can carry
# after magnitude-weighting (see _leg_weights) — same "engineering judgment
# call, disclosed not calibrated" register as MIN_NAMES_PER_LEG above.
# Without a cap, one extreme outlier in a rank_fraction-selected leg could
# dominate that leg's whole realized return, turning a diversified decile
# bet into a near-single-name bet by accident — exactly the kind of
# concentration a decile *portfolio* (this module's whole premise, see
# DEFAULT_MIN_NAMES_PER_LEG above) exists to avoid.
MAX_WEIGHT_MULTIPLE = 3.0

# Shumway, "The Delisting Bias in CRSP Data" (Journal of Finance, 1997):
# CRSP's own delisting-return field is disproportionately MISSING exactly
# for the worst outcomes (bankruptcy, liquidation), and imputing a fixed
# -30% for a missing NYSE/AMEX delisting return removes most of the
# resulting upward bias. Shumway & Warther, "The Delisting Bias in CRSP's
# Nasdaq Data and Its Implications for the Size Effect" (Journal of
# Finance, 1999) extends the same diagnosis to Nasdaq with a larger -55%
# (Nasdaq delistings skew more toward outright failure/liquidation than
# NYSE/AMEX's larger share of mergers and voluntary exchange moves).
SHUMWAY_NYSE_AMEX_DELISTING_RETURN = -0.30
SHUMWAY_NASDAQ_DELISTING_RETURN = -0.55

# This harness has no per-ticker listing-exchange field anywhere (see
# CrossSectionalData's docstring on what free data this project has), so
# Shumway's two figures cannot be applied by exchange. DEFAULT_IMPUTED_
# DELISTING_RETURN is their plain unweighted average, used DELIBERATELY
# instead of a composition-weighted blend: any specific weighting (e.g.
# "S&P 500 constituents skew N% NYSE") would fabricate an exchange split
# this project has no data to support, which is worse than the honest,
# disclosed approximation of splitting the difference. config.
# imputed_delisting_return exists precisely so a caller who DOES have (or
# is willing to assume) a better-justified figure for their own family can
# override this default rather than being stuck with it.
DEFAULT_IMPUTED_DELISTING_RETURN = (
    SHUMWAY_NYSE_AMEX_DELISTING_RETURN + SHUMWAY_NASDAQ_DELISTING_RETURN
) / 2.0

MembershipFn = Callable[[str, date], bool]


@dataclass(frozen=True)
class CrossSectionalData:
    """Wide (dates x tickers) daily frames, all sharing close's exact index
    and columns (YFinanceProvider.get_daily_ohlcv guarantees the alignment;
    validate_cross_sectional_data re-checks it for hand-built data). open/
    volume are optional because only some signal families need them — the
    Lou/Polk/Skouras decomposition needs open, the Grinblatt/Han turnover
    proxy needs volume — and requiring all three everywhere would force
    every close-only test and caller to fabricate columns it never reads."""

    close: pd.DataFrame
    open: pd.DataFrame | None = None
    volume: pd.DataFrame | None = None
    # Point-in-time market cap (shares outstanding x close, forward-filled
    # from real per-ticker share-count history only -- never a future
    # count), one column per ticker aligned to close exactly like open/
    # volume. Added for Build D1 (cross_sectional_ivol.py's value-weighted
    # idiosyncratic-volatility family) but lives here, not in that file,
    # because it is consumed by run_cross_sectional_backtest's leg-weighting
    # step below -- the same reason open/volume live here rather than in
    # cross_sectional_patterns.py despite existing only for its signals.
    market_cap: pd.DataFrame | None = None


def validate_cross_sectional_data(data: CrossSectionalData) -> None:
    for name, frame in (("open", data.open), ("volume", data.volume), ("market_cap", data.market_cap)):
        if frame is None:
            continue
        if not frame.index.equals(data.close.index) or not frame.columns.equals(data.close.columns):
            raise ValueError(
                f"CrossSectionalData.{name} is not aligned with close "
                f"(index/columns must match exactly — see get_daily_ohlcv, which guarantees this)."
            )


# Receives a HISTORY VIEW: rows strictly up to and including the formation
# date, columns restricted to that formation date's eligible (point-in-time
# member) tickers. Returns one signal value per ticker; NaN means "this
# ticker has no valid signal today" (insufficient history, missing data)
# and excludes it from the ranking. The view construction in
# run_cross_sectional_backtest is what makes look-ahead structurally
# impossible — a signal function CANNOT read a future row, however buggy,
# because the row is not in the frame it is handed (the same structural
# guarantee engine.py's run_walk_forward makes by slicing the fit window
# before the day row, proven there by test_research_lab's look-ahead test
# and here by test_cross_sectional's).
SignalFn = Callable[[CrossSectionalData], pd.Series]


@dataclass(frozen=True)
class CrossSectionalSpec:
    pattern_id: str
    family: str
    citation: str
    signal_fn: SignalFn
    lookback_days: int  # trading rows of history the signal needs before its first formation
    holding_days: int  # trading days each formation is held; also the formation cadence (non-overlapping holds — see module docstring)
    portfolio: Literal["long_short", "long_universe_hedged"]
    rank_fraction: float  # 0.1 = deciles, 0.2 = quintiles
    requires_open: bool = False
    requires_volume: bool = False
    requires_market_cap: bool = False
    # "magnitude" (default, every family before Build D1): _leg_weights --
    # weight by each member's own distance from the leg's boundary. "value":
    # weight the ranked long/short legs by real point-in-time market cap
    # instead (see _resolve_leg_weights and cross_sectional_ivol.py's
    # citations for why -- the AHXZ/Bali-Cakici/Blitz-van Vliet
    # idiosyncratic-volatility literature is standardly reported
    # value-weighted, and an equal- or magnitude-weighted low-IVOL portfolio
    # is well documented to load heavily on illiquid micro-caps in a way
    # that misrepresents the anomaly's tradeable size). Defaulted to
    # "magnitude" so every existing spec (Round C) is byte-for-byte
    # unaffected by this field's existence.
    leg_weighting: Literal["magnitude", "value"] = "magnitude"
    # None (default): formation cadence == holding_days, the harness's
    # original non-overlapping schedule -- every existing spec (Round C,
    # Round D) leaves this unset and is byte-for-byte unaffected. Set to a
    # positive stagger STRICTLY LESS than holding_days to form OVERLAPPING
    # Jegadeesh-Titman-style cohorts instead (see run_cross_sectional_
    # backtest / _replay_sleeve): holding_days // cohort_formation_days
    # independent staggered sleeves are replayed and blended by simple
    # equal-weighted average on any day multiple are concurrently active.
    # Built for Build D2's long-horizon reversal family -- see that
    # family's own module docstring for why its short usable history needs
    # this for statistical power, and why it does NOT increase the number
    # of independent long-run observations regardless.
    cohort_formation_days: int | None = None


@dataclass
class CrossSectionalConfig:
    cost_bps: float = DEFAULT_XS_COST_BPS
    min_names_per_leg: int = DEFAULT_MIN_NAMES_PER_LEG
    # Earliest calendar date a formation may occur on. The production entry
    # point sets this to the requested screening start so that price
    # history fetched EARLIER (purely to warm up long lookbacks) never
    # itself hosts a formation — and, critically, so no formation can land
    # before MEMBERSHIP_DATA_START, where was_member would silently answer
    # False for everyone (see sp500_membership_history.was_member's own
    # docstring on "no" vs "unknown").
    formation_start: date | None = None
    # False (default): a ticker whose price disappears mid-hold silently
    # drops out of its leg's mean (see the module docstring's delisting
    # bullet) -- every family screened before this option existed keeps
    # this exact behavior unless it deliberately sets True. True: apply
    # imputed_delisting_return once, on the day a held ticker's price
    # permanently stops appearing anywhere later in the loaded data (a real
    # delisting, distinct from a transient gap that later recovers -- see
    # _compute_delisting_positions), instead of dropping it.
    impute_delisting_returns: bool = False
    # The fixed one-time loss charged when impute_delisting_returns fires.
    # Defaults to DEFAULT_IMPUTED_DELISTING_RETURN (Shumway 1997 / Shumway
    # & Warther 1999 -- see that constant). Ignored entirely when
    # impute_delisting_returns is False.
    imputed_delisting_return: float = DEFAULT_IMPUTED_DELISTING_RETURN


@dataclass
class FormationRecord:
    """One formation date's full audit trail — what was eligible, what was
    held, what it cost. Kept per-formation (not just aggregated) because
    the point-in-time-correctness tests assert directly against these
    (e.g. TWTR must appear in no formation dated after its real 2022-11-01
    index removal), and because a surprising screening result should be
    auditable down to exactly which names drove it."""

    date: pd.Timestamp
    n_eligible: int
    long_tickers: list[str] = field(default_factory=list)
    short_tickers: list[str] = field(default_factory=list)
    turnover: float = 0.0  # sum of |weight change| across tickers, gross one-way notional traded
    skipped_reason: str | None = None
    # Only ever True when spec.leg_weighting == "value" AND that leg's real
    # point-in-time market cap was unusable for at least one member (missing
    # share-count history, or a non-positive/NaN resolved value) at this
    # formation, forcing a fall-back to the magnitude-weighted scheme for
    # that leg alone -- see _resolve_leg_weights. Always False for a
    # magnitude-weighted spec (never applicable) and for a leg that was
    # never formed (skipped_reason is not None) or has no rank-cutoff short
    # leg (long_universe_hedged's hedge side is never value-weighted, see
    # _target_weights). screen_cross_sectional_universe aggregates these
    # into CrossSectionalScreeningResult so "how often did the fallback
    # fire" is a first-class, always-reported number, not a log line that
    # could go unread.
    long_leg_value_weight_fallback: bool = False
    short_leg_value_weight_fallback: bool = False


@dataclass
class CrossSectionalBacktestResult:
    status: Literal["ok", "insufficient_history", "no_valid_formations"]
    daily_returns: pd.Series  # net of costs, one observation per realized trading day
    formations: list[FormationRecord] = field(default_factory=list)
    total_cost: float = 0.0  # sum of all formation-turnover cost charges


def select_leg_tickers(signal: pd.Series, rank_fraction: float) -> tuple[list[str], list[str]]:
    """Ranks a cross-sectional signal and returns (top, bottom) leg ticker
    lists, each of size max(1, floor(n * rank_fraction)). Deterministic
    under ties: the signal is pre-sorted by ticker so the stable value sort
    breaks ties alphabetically — a re-run on identical data always forms
    the identical portfolio (screening results must be reproducible to be
    auditable). NaNs are dropped before ranking (a NaN signal means "no
    valid signal", per the SignalFn contract). The caller is responsible
    for rejecting cross-sections too small for the two legs to be disjoint
    (2 * leg size > n) — this function only ranks."""
    clean = signal.dropna()
    clean = clean[np.isfinite(clean)]
    n = len(clean)
    if n == 0:
        return [], []
    n_leg = max(1, int(n * rank_fraction))
    ordered = clean.sort_index().sort_values(ascending=False, kind="mergesort")
    top = list(ordered.index[:n_leg])
    bottom = list(ordered.index[-n_leg:])
    return top, bottom


# A member's raw (pre-normalization) weight floors at this fraction of the
# leg's own largest excess — keeps the boundary (weakest, just-barely-
# selected) member from carrying literally zero weight in a leg with one
# very extreme outlier, without diluting genuine differentiation the way
# giving every member a full equal-share floor would (verified: a full
# equal-share floor mathematically caps every member's post-normalization
# weight below MAX_WEIGHT_MULTIPLE * equal_share for any leg size and any
# multiple > 1, making the cap below unreachable dead code — this smaller,
# excess-relative floor is what lets one genuinely dominant signal
# actually reach and trigger the cap).
MIN_RELATIVE_WEIGHT_FRACTION = 0.1


def _apply_weight_cap(raw: dict[str, float]) -> dict[str, float]:
    """Normalizes non-negative raw weights (any positive scale — signal
    excess for magnitude weighting, dollar market cap for value weighting)
    to sum to 1.0, then caps each member at MAX_WEIGHT_MULTIPLE times an
    equal share: excess above the cap is redistributed proportionally among
    the members never yet capped, iterated to convergence.

    A member is added to a PERMANENT `capped` set the first time it is
    clamped, and is excluded from every later redistribution round even
    though its value now reads exactly `cap` (`<=cap` would be true of it
    forever after). This is the fix for a real bug found by this project's
    own independent-verify pass (2026-08-26): an earlier version re-derived
    "under" fresh each pass as `w <= cap`, which is also true of a member
    THIS SAME PASS just clamped to `cap` — so that member re-entered the
    next pass's redistribution pool and could be pushed back over cap by
    it. Stress-tested at the time: ~23% of 2,000 randomized fat-tailed leg
    compositions ended with a member up to 36 percentage points over cap,
    one repro needing 64 passes against a 12-iteration budget. Once
    "capped" is permanent, each pass adds at least one NEW member to that
    set or terminates, so the loop provably converges within len(weights)
    passes and no capped member can ever be pushed over cap again.

    Factored out of _leg_weights so the identical concentration limit
    applies under EITHER weighting philosophy _resolve_leg_weights can
    choose between, rather than the cap being reimplemented (and liable to
    drift) per scheme — see MAX_WEIGHT_MULTIPLE's own docstring for why a
    leg needs this cap at all. Caller contract: `raw` is non-empty with a
    strictly positive sum; both call sites below guarantee this before
    calling (a zero/degenerate raw is handled by the caller's own
    equal-weight fallback, never reaches here)."""
    total = sum(raw.values())
    weights = {t: w / total for t, w in raw.items()}
    equal_share = 1.0 / len(weights)
    cap = MAX_WEIGHT_MULTIPLE * equal_share
    capped: set[str] = set()
    for _ in range(len(weights)):
        over = {t: w for t, w in weights.items() if t not in capped and w > cap}
        if not over:
            break
        excess_to_redistribute = sum(w - cap for w in over.values())
        for t in over:
            weights[t] = cap
            capped.add(t)
        under = {t: w for t, w in weights.items() if t not in capped}
        under_total = sum(under.values())
        if under_total > 0.0:
            for t in under:
                weights[t] += excess_to_redistribute * (under[t] / under_total)
    return weights


def _leg_weights(tickers: list[str], signal: pd.Series, *, higher_is_stronger: bool) -> dict[str, float]:
    """Magnitude-weights one leg's members proportionally to their own
    distance from the leg's weakest (boundary) member — raw weight is
    excess, floored at MIN_RELATIVE_WEIGHT_FRACTION of the leg's largest
    excess so the boundary member keeps a small nonzero share — then capped
    via _apply_weight_cap (normalize to 1.0, cap at MAX_WEIGHT_MULTIPLE
    times an equal share, redistribute the excess).

    higher_is_stronger=True for the long leg (the largest signal value is
    the most extreme, most-weighted member); False for the short leg (the
    smallest signal value is most extreme). A leg of size 1 always returns
    {ticker: 1.0} regardless of signal — weighting only has meaning across
    >=2 members, and this must reduce to this module's old equal-weight
    behavior in that degenerate (and, per DEFAULT_MIN_NAMES_PER_LEG,
    already-guarded-against-in-practice) case. A leg whose members are
    exactly tied (spread == 0, e.g. a constant test signal) also falls
    back to equal weight — there is no information to weight by."""
    if not tickers:
        return {}
    if len(tickers) == 1:
        return {tickers[0]: 1.0}

    values = signal.reindex(tickers)
    boundary = values.min() if higher_is_stronger else values.max()
    excess = (values - boundary) if higher_is_stronger else (boundary - values)
    excess = excess.clip(lower=0.0)
    spread = float(excess.max())
    equal_share = 1.0 / len(tickers)
    if spread <= 0.0 or not np.isfinite(spread):
        return {t: equal_share for t in tickers}

    floor = spread * MIN_RELATIVE_WEIGHT_FRACTION
    raw = {t: max(float(excess[t]), floor) for t in tickers}
    return _apply_weight_cap(raw)


def _resolve_leg_weights(
    tickers: list[str],
    signal: pd.Series,
    *,
    higher_is_stronger: bool,
    leg_weighting: Literal["magnitude", "value"],
    market_cap: pd.Series | None,
) -> tuple[dict[str, float], bool]:
    """Dispatches one leg's weighting to _leg_weights (magnitude, the only
    scheme before Build D1) or, when leg_weighting == "value", to real
    point-in-time market-cap weighting — Build D1's whole point (see
    cross_sectional_ivol.py's citations: the idiosyncratic-volatility
    literature is standardly reported value-weighted, not equal- or
    magnitude-weighted). Returns (weights, used_fallback).

    market_cap is `data.market_cap.iloc[formation_row]` reindexed by the
    caller — i.e. the SAME formation-date row `formation_close` was read
    from, so it carries no more look-ahead risk than any other
    formation-date read in this module; the point-in-time-safety work
    (forward-fill from real share-count history only, never a future
    count) already happened once, before the backtest, in
    cross_sectional_ivol.py's build_point_in_time_market_cap.

    A leg of size 0 or 1 is routed straight to _leg_weights regardless of
    leg_weighting: _leg_weights already reduces correctly at both sizes
    (empty dict / forced full weight), and there is no "value vs magnitude"
    question to ask about a single name's own weight. This never counts as
    a fallback — there was nothing to fall back FROM.

    For a genuine (>=2 member) leg under "value" weighting: falls back to
    _leg_weights — the ORIGINAL, already-battle-tested scheme, per the
    build instructions this module was written against, not a fresh
    equal-weight — whenever ANY member's market cap is missing (no
    share-count history ever resolved for that ticker) or non-positive
    (NaN slipped through, or a data error). Mixing a value-weighted subset
    with an arbitrarily-weighted remainder would not be a coherent value
    weighting, so the fallback applies to the WHOLE leg, not just the
    offending member — the same "no partial state" discipline
    _target_weights already uses for a skipped formation (flat, never a
    naked partial book)."""
    if leg_weighting != "value" or len(tickers) <= 1:
        return _leg_weights(tickers, signal, higher_is_stronger=higher_is_stronger), False

    caps = None if market_cap is None else market_cap.reindex(tickers)
    usable = caps is not None and bool(caps.notna().all()) and bool((caps > 0.0).all())
    if not usable:
        return _leg_weights(tickers, signal, higher_is_stronger=higher_is_stronger), True

    raw = {t: float(caps[t]) for t in tickers}
    return _apply_weight_cap(raw), False


def _target_weights(
    long_weights: dict[str, float], short_weights: dict[str, float], portfolio: str, eligible: list[str]
) -> dict[str, float]:
    """Net per-ticker weights for one formation: each leg's own
    magnitude-weighted shares (see _leg_weights), signed +/- and summed —
    long_short nets a long leg against a short leg; long_universe_hedged
    nets a long leg against an equal-weighted short of the WHOLE eligible
    universe (no rank cutoff exists for "the whole universe", so that side
    is never magnitude-weighted). Net (not per-leg) weights are what
    turnover must be measured on — a name staying long across a
    reformation trades nothing, whatever leg bookkeeping says."""
    weights: dict[str, float] = {}
    for t, w in long_weights.items():
        weights[t] = weights.get(t, 0.0) + w
    # A hedged portfolio shorts the universe only when it actually formed a
    # long leg — a skipped formation is FLAT, never a naked universe short.
    if portfolio == "long_universe_hedged":
        if long_weights:
            w_short = 1.0 / len(eligible)
            for t in eligible:
                weights[t] = weights.get(t, 0.0) - w_short
    else:
        for t, w in short_weights.items():
            weights[t] = weights.get(t, 0.0) - w
    return weights


def _turnover(old: dict[str, float], new: dict[str, float]) -> float:
    tickers = set(old) | set(new)
    return float(sum(abs(new.get(t, 0.0) - old.get(t, 0.0)) for t in tickers))


def _leg_weighted_return(day_returns: pd.Series, leg_weights: dict[str, float]) -> float:
    """Magnitude-weighted mean of the leg's member returns that day,
    skipping names with no return (delisted mid-hold) and renormalizing
    the survivors' weights back to sum to 1.0 — the weighted analogue of
    the old liquidate-at-last-price convention, which this formula exactly
    reduces to at equal weights. A leg whose every name is missing
    contributes 0.0 — cash, not a fabricated number."""
    if not leg_weights:
        return 0.0
    vals = day_returns.reindex(list(leg_weights.keys()))
    survivors = vals.dropna()
    if survivors.empty:
        return 0.0
    total_weight = sum(leg_weights[t] for t in survivors.index)
    if total_weight <= 0.0:
        return 0.0
    return float(sum(leg_weights[t] * survivors[t] for t in survivors.index) / total_weight)


def _compute_delisting_positions(close: pd.DataFrame) -> dict[str, int]:
    """For each ticker, the integer row position of its first PERMANENTLY
    missing day: the position immediately after its last valid price
    anywhere in the ENTIRE loaded `close` frame -- i.e. it has no valid
    price again from there through the frame's very last row. This is the
    operational definition of "delisted" config.impute_delisting_returns
    uses, and it is deliberately global (computed once over the whole
    frame, not per-hold): a ticker whose gap later CLOSES -- a valid price
    reappears anywhere later in the frame, whether a same-week halt, a
    data-provider hiccup, or (per this module's own recycled-ticker
    disclosure) a years-later ticker reuse -- is NOT included here. That is
    a data gap, not a delisting, by construction: the whole point of
    "permanently" is that a transient gap must fall back to the ordinary
    drop-and-renormalize convention, never the imputed loss.

    A ticker still valid on the frame's very last row is also not
    included: the loaded data simply ENDING is not evidence the ticker
    stopped trading, only that this run's data collection did. A ticker
    with no valid price ANYWHERE in the frame is likewise excluded -- there
    is no "last valid price" to delist FROM, and (structurally, see
    run_cross_sectional_backtest's eligibility gate) such a ticker could
    never have been held in the first place, since formation eligibility
    already requires a finite price that same day."""
    n = len(close.index)
    positions: dict[str, int] = {}
    notna = close.notna().to_numpy()
    for col_idx, ticker in enumerate(close.columns):
        valid = np.flatnonzero(notna[:, col_idx])
        if valid.size == 0:
            continue
        last_valid = int(valid[-1])
        if last_valid < n - 1:
            positions[ticker] = last_valid + 1
    return positions


def _replay_sleeve(
    data: CrossSectionalData,
    spec: CrossSectionalSpec,
    config: CrossSectionalConfig,
    is_member: MembershipFn,
    daily_returns_all: pd.DataFrame,
    delisting_by_position: dict[int, list[str]],
    start_position: int,
) -> tuple[list[FormationRecord], dict[pd.Timestamp, tuple[float, float]], bool]:
    """One independent formation/hold cycle: reforms every spec.holding_days
    trading days starting at start_position. This is this module's
    ORIGINAL (pre-overlap) single-stream algorithm, extracted verbatim so
    run_cross_sectional_backtest can run several of these staggered by
    spec.cohort_formation_days and blend them into one overlapping-cohort
    replay -- a single sleeve at start_position == first_formation
    reproduces every prior (Round C, Round D) behavior bit-for-bit, since
    that is exactly the loop those families already ran.

    Returns (this sleeve's own FormationRecords, {realized date:
    (net_return, cost_charged_on_that_date)}, whether any formation in this
    sleeve actually formed). The (net, cost) pair -- not just net -- is
    what lets the caller blend several sleeves' returns by simple average
    while still reporting an honest total_cost: mean(net_i) over active
    sleeves is exactly the equal-weighted blended net return, and
    mean(cost_i) is that day's actual blended cost drag, both of which
    collapse to today's single value when only one sleeve is active (see
    run_cross_sectional_backtest)."""
    index = data.close.index
    n = len(index)

    formations: list[FormationRecord] = []
    by_date: dict[pd.Timestamp, tuple[float, float]] = {}
    prev_weights: dict[str, float] = {}

    any_formed = False

    for i in range(start_position, n - 1, spec.holding_days):
        formation_ts = index[i]
        formation_day: date = formation_ts.date()

        # Point-in-time eligibility: an index member on the formation date,
        # with a price at that date's close (a member with no price today
        # cannot be ranked or traded). This is THE survivorship-bias gate —
        # see module docstring.
        formation_close = data.close.iloc[i]
        eligible = [
            t for t in data.close.columns if is_member(t, formation_day) and np.isfinite(formation_close[t])
        ]

        long_tickers: list[str] = []
        short_tickers: list[str] = []
        long_weights: dict[str, float] = {}
        short_weights: dict[str, float] = {}
        long_fallback = False
        short_fallback = False
        skipped_reason: str | None = None

        if eligible:
            # The history view: rows <= formation date, columns = eligible
            # only. Structural look-ahead impossibility — see SignalFn.
            # Rows are capped at the spec's own declared lookback_days —
            # the exact history the spec's contract says its signal reads —
            # rather than all history since inception: behaviorally
            # identical for any signal honoring its declaration, and it
            # caps the per-formation frame copy at lookback x universe
            # (~10MB at 567 rows x ~700 tickers) instead of growing with
            # every year of replay.
            row_start = max(0, i + 1 - spec.lookback_days)
            view = CrossSectionalData(
                close=data.close.iloc[row_start : i + 1].loc[:, eligible],
                open=data.open.iloc[row_start : i + 1].loc[:, eligible] if data.open is not None else None,
                volume=(
                    data.volume.iloc[row_start : i + 1].loc[:, eligible] if data.volume is not None else None
                ),
                market_cap=(
                    data.market_cap.iloc[row_start : i + 1].loc[:, eligible]
                    if data.market_cap is not None
                    else None
                ),
            )
            signal = spec.signal_fn(view)
            top, bottom = select_leg_tickers(signal, spec.rank_fraction)
            n_ranked = int(signal.dropna().shape[0])
            n_leg = len(top)
            if n_leg < config.min_names_per_leg:
                skipped_reason = (
                    f"only {n_ranked} ranked names -> leg of {n_leg} < min_names_per_leg="
                    f"{config.min_names_per_leg}"
                )
            elif 2 * n_leg > n_ranked:
                skipped_reason = f"legs would overlap ({n_ranked} ranked names for two legs of {n_leg})"
            else:
                # Leg weighting reads the FORMATION row directly from `data`
                # (not the view) — market cap needs only today's row, not a
                # lookback window, and this is the exact same row
                # `formation_close` above was already read from.
                market_cap_row = data.market_cap.iloc[i] if data.market_cap is not None else None

                long_tickers = top
                long_weights, long_fallback = _resolve_leg_weights(
                    top,
                    signal,
                    higher_is_stronger=True,
                    leg_weighting=spec.leg_weighting,
                    market_cap=market_cap_row,
                )
                if spec.portfolio == "long_short":
                    short_tickers = bottom
                    short_weights, short_fallback = _resolve_leg_weights(
                        bottom,
                        signal,
                        higher_is_stronger=False,
                        leg_weighting=spec.leg_weighting,
                        market_cap=market_cap_row,
                    )
        else:
            skipped_reason = "no eligible tickers (point-in-time membership + price availability)"

        new_weights = _target_weights(long_weights, short_weights, spec.portfolio, eligible)
        turnover = _turnover(prev_weights, new_weights)
        cost = (config.cost_bps / 10_000.0) * turnover
        prev_weights = new_weights
        if skipped_reason is None:
            any_formed = True

        formations.append(
            FormationRecord(
                date=formation_ts,
                n_eligible=len(eligible),
                long_tickers=long_tickers,
                short_tickers=(eligible if spec.portfolio == "long_universe_hedged" and long_tickers else short_tickers),
                turnover=turnover,
                skipped_reason=skipped_reason,
                long_leg_value_weight_fallback=long_fallback,
                short_leg_value_weight_fallback=short_fallback,
            )
        )

        # For long_universe_hedged, the realized "short leg" is the equal-
        # weighted whole eligible universe (see _target_weights) — computed
        # once per formation rather than inside the per-day loop below.
        realized_short_weights = (
            {t: 1.0 / len(eligible) for t in eligible}
            if spec.portfolio == "long_universe_hedged" and long_tickers
            else short_weights
        )

        hold_end = min(i + spec.holding_days, n - 1)
        for j in range(i + 1, hold_end + 1):
            day = daily_returns_all.iloc[j]
            # Opt-in Shumway-style imputed delisting loss (see
            # config.impute_delisting_returns): only ever fires on the
            # exact transition day precomputed by _compute_delisting_
            # positions, and only touches tickers actually flagged that
            # day -- everything else about `day` is untouched, so this is a
            # strict no-op whenever delisting_by_position is empty (the
            # default, impute_delisting_returns=False).
            delisting_today = delisting_by_position.get(j)
            if delisting_today:
                day = day.copy()
                for t in delisting_today:
                    if t in day.index:
                        day[t] = config.imputed_delisting_return
            long_ret = _leg_weighted_return(day, long_weights)
            short_ret = _leg_weighted_return(day, realized_short_weights)
            gross = long_ret - short_ret
            # The formation's turnover cost lands on its first realization
            # day — the day the rebalance trades settle into the return
            # stream, mirroring engine.py charging |position change| on the
            # day the position changes.
            cost_today = cost if j == i + 1 else 0.0
            net = gross - cost_today
            by_date[index[j]] = (net, cost_today)

    return formations, by_date, any_formed


def run_cross_sectional_backtest(
    data: CrossSectionalData,
    spec: CrossSectionalSpec,
    config: CrossSectionalConfig,
    membership_fn: MembershipFn | None = None,
) -> CrossSectionalBacktestResult:
    """One spec's full walk-forward replay: at each formation date (every
    holding_days trading days by default, or every spec.cohort_formation_
    days if set — see the module docstring's overlapping-cohorts bullet —
    starting once lookback_days of history exist and config.formation_start
    is reached), rank the point-in-time-eligible cross-section, form the
    legs, realize close-to-close returns until the next formation. See the
    module docstring for every convention used here and its justification.

    membership_fn defaults to sp500_membership_history.was_member — the
    production point-in-time gate. Tests inject their own to isolate
    mechanics from the vendored membership data, EXCEPT the point-in-time-
    correctness tests, which deliberately run the real was_member against
    real historical index events (TWTR's removal, PLTR's addition) to
    prove the composed system respects them."""
    validate_cross_sectional_data(data)
    if spec.requires_open and data.open is None:
        raise ValueError(f"{spec.pattern_id} requires daily Open data (CrossSectionalData.open is None).")
    if spec.requires_volume and data.volume is None:
        raise ValueError(f"{spec.pattern_id} requires daily Volume data (CrossSectionalData.volume is None).")
    if spec.requires_market_cap and data.market_cap is None:
        raise ValueError(
            f"{spec.pattern_id} requires point-in-time market cap (CrossSectionalData.market_cap is None)."
        )
    if spec.leg_weighting == "value" and data.market_cap is None:
        # Belt-and-suspenders on top of the declared-requirement check above
        # (same relationship requires_open/requires_volume have to their own
        # signals): "value" weighting is a structural need of the harness's
        # OWN leg-forming step below, not just something a signal function
        # might read, so this is checked independently of whether a spec
        # remembered to also set requires_market_cap=True.
        raise ValueError(
            f"{spec.pattern_id} has leg_weighting='value' but CrossSectionalData.market_cap is None."
        )

    is_member = membership_fn if membership_fn is not None else was_member
    index = data.close.index
    n = len(index)

    # fill_method=None: a mid-series NaN yields a NaN return (the ticker
    # drops out of its leg that day) rather than pandas' legacy forward-
    # fill, which would fabricate a 0% return for a halted/delisted name.
    daily_returns_all = data.close.pct_change(fill_method=None)

    first_formation = spec.lookback_days
    if config.formation_start is not None:
        eligible_positions = np.flatnonzero(index.date >= config.formation_start)  # type: ignore[attr-defined]
        if len(eligible_positions) == 0:
            return CrossSectionalBacktestResult(
                status="insufficient_history", daily_returns=pd.Series(dtype=float)
            )
        first_formation = max(first_formation, int(eligible_positions[0]))

    # Need at least one realization day after the first formation.
    if first_formation >= n - 1:
        return CrossSectionalBacktestResult(status="insufficient_history", daily_returns=pd.Series(dtype=float))

    # Overlapping-cohort cadence (see module docstring and CrossSectionalSpec.
    # cohort_formation_days). None or == holding_days both collapse to
    # n_sleeves == 1 starting at first_formation — i.e. literally the
    # original single-stream loop — so every spec that has never set this
    # field replays byte-for-byte identically to before this option existed.
    cadence = spec.cohort_formation_days if spec.cohort_formation_days is not None else spec.holding_days
    if cadence <= 0 or cadence > spec.holding_days:
        raise ValueError(
            f"{spec.pattern_id}: cohort_formation_days ({spec.cohort_formation_days}) must be a positive "
            f"stagger no larger than holding_days ({spec.holding_days}) — that is what makes it a cadence "
            "for OVERLAPPING cohorts; leave it unset for the plain non-overlapping schedule instead."
        )
    n_sleeves = max(1, spec.holding_days // cadence)

    # Opt-in Shumway-style delisting-return imputation (see module docstring
    # and config.impute_delisting_returns). Computed once, globally, over the
    # whole loaded frame — not per sleeve — both because the underlying
    # price data a ticker permanently disappears from is shared by every
    # sleeve, and because computing it once is strictly cheaper. Stays an
    # empty dict (hence a strict no-op inside _replay_sleeve) whenever the
    # option is off, which is the default.
    delisting_by_position: dict[int, list[str]] = {}
    if config.impute_delisting_returns:
        for ticker, position in _compute_delisting_positions(data.close).items():
            delisting_by_position.setdefault(position, []).append(ticker)

    all_formations: list[FormationRecord] = []
    per_date: dict[pd.Timestamp, list[tuple[float, float]]] = {}
    any_formed = False
    for k in range(n_sleeves):
        start_position = first_formation + k * cadence
        if start_position >= n - 1:
            continue
        formations_k, by_date_k, formed_k = _replay_sleeve(
            data, spec, config, is_member, daily_returns_all, delisting_by_position, start_position
        )
        all_formations.extend(formations_k)
        any_formed = any_formed or formed_k
        for realized_date, pair in by_date_k.items():
            per_date.setdefault(realized_date, []).append(pair)

    all_formations.sort(key=lambda f: f.date)
    return_dates = sorted(per_date.keys())
    net_returns: list[float] = []
    total_cost = 0.0
    for realized_date in return_dates:
        pairs = per_date[realized_date]
        # Equal-weighted blend across whichever sleeves are concurrently
        # active on this date — mean of a single value when n_sleeves == 1
        # (or only one sleeve happens to be active yet/still), which is
        # exactly the un-blended original value: this is what makes the
        # n_sleeves == 1 path numerically identical to the pre-overlap
        # algorithm, not merely structurally similar.
        net_returns.append(float(np.mean([p[0] for p in pairs])))
        total_cost += float(np.mean([p[1] for p in pairs]))

    daily = pd.Series(net_returns, index=pd.DatetimeIndex(return_dates), dtype=float)
    status: Literal["ok", "insufficient_history", "no_valid_formations"] = (
        "ok" if any_formed else "no_valid_formations"
    )
    return CrossSectionalBacktestResult(
        status=status, daily_returns=daily, formations=all_formations, total_cost=total_cost
    )


@dataclass
class CrossSectionalScreeningResult:
    pattern_id: str
    family: str
    citation: str
    n_formations: int
    n_skipped_formations: int
    avg_names_per_leg: float
    n_trading_days: int  # length of the realized daily-return series
    sharpe_annualized: float
    total_cost_drag: float
    deflated_sharpe: DeflatedSharpeResult
    # Both 0 for every magnitude-weighted spec (Round C and earlier — there
    # is no value-weighting fallback to ever fire). For a leg_weighting ==
    # "value" spec, these are the first-class, always-reported answer to
    # "how often did the market-cap fallback fire" the build instructions
    # required — a count, not a log line that could go unread. See
    # FormationRecord.long_leg_value_weight_fallback /
    # short_leg_value_weight_fallback, which these are aggregated from.
    n_value_weighted_legs: int = 0
    n_value_weight_fallbacks: int = 0


def screen_cross_sectional_universe(
    data: CrossSectionalData,
    specs: list[CrossSectionalSpec],
    config: CrossSectionalConfig,
    membership_fn: MembershipFn | None = None,
) -> list[CrossSectionalScreeningResult]:
    """One Sharpe per spec across the whole cross-section, DSR-corrected
    for the family's pre-declared size. Trial counting follows
    intraday_patterns.screen_pattern_universe's pooled framing exactly,
    and for the same documented reason: each spec IS already a single
    portfolio across the whole universe (there is no per-ticker result to
    cherry-pick, so no silently-uncorrected "which ticker" search
    dimension exists), leaving "which pattern definition" as the one
    search dimension — so n_trials is fixed at len(specs), the family's
    literal pre-declared size, never shrunk to however many specs survived
    the data floors (which would be gameable by defining specs expected to
    fail). sigma_sr is the ddof=1 std of every sibling spec's own Sharpe
    from this same screening pass — the direct analogue of
    screen_pattern_universe's sibling convention, with "same family,
    different pattern" as the sibling relation."""
    n_trials = len(specs)

    replays: dict[str, CrossSectionalBacktestResult] = {}
    for spec in specs:
        result = run_cross_sectional_backtest(data, spec, config, membership_fn)
        if result.status != "ok":
            continue
        if len(result.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        replays[spec.pattern_id] = result

    sharpes = {pid: sharpe_ratio(res.daily_returns) for pid, res in replays.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {spec.pattern_id: spec for spec in specs}
    results: list[CrossSectionalScreeningResult] = []
    for pattern_id, replay in replays.items():
        spec = spec_by_id[pattern_id]
        formed = [f for f in replay.formations if f.skipped_reason is None]
        skipped = [f for f in replay.formations if f.skipped_reason is not None]
        avg_leg = float(np.mean([len(f.long_tickers) for f in formed])) if formed else 0.0
        dsr = compute_deflated_sharpe(sharpes[pattern_id], replay.daily_returns, n_trials, sigma_sr)

        # Value-weighting fallback tally: only meaningful for a "value" spec
        # (magnitude specs never set either FormationRecord flag, so both
        # stay 0). The long leg is always attempted under "value" weighting;
        # the short leg only for long_short (long_universe_hedged's hedge
        # side is never value-weighted — see _target_weights).
        n_value_weighted_legs = 0
        n_value_weight_fallbacks = 0
        if spec.leg_weighting == "value":
            for f in formed:
                n_value_weighted_legs += 1
                if f.long_leg_value_weight_fallback:
                    n_value_weight_fallbacks += 1
                if spec.portfolio == "long_short":
                    n_value_weighted_legs += 1
                    if f.short_leg_value_weight_fallback:
                        n_value_weight_fallbacks += 1

        results.append(
            CrossSectionalScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                n_formations=len(formed),
                n_skipped_formations=len(skipped),
                avg_names_per_leg=avg_leg,
                n_trading_days=len(replay.daily_returns),
                sharpe_annualized=sharpes[pattern_id],
                total_cost_drag=replay.total_cost,
                deflated_sharpe=dsr,
                n_value_weighted_legs=n_value_weighted_legs,
                n_value_weight_fallbacks=n_value_weight_fallbacks,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results
