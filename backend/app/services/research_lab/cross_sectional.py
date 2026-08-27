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

NON-EQUITY UNIVERSES. was_member is the right gate for an S&P 500 equity
cross-section and the WRONG gate for anything else: it answers False for
every ticker that is not an S&P 500 member, which is every bond ETF, every
FX pair, every commodity and crypto instrument. Because "not a member" and
"not an index-membership concept at all" are the same False, passing
membership_fn=None for a non-equity basket used to yield n_eligible == 0 on
every formation and a long series of exact 0.0 returns — a SILENT
fake-empty result, confirmed live on a real bond-ETF family (2026-08-26).
Two changes close that hole, and both must stay:
 * fixed_universe_membership() below is the explicit, named gate for an
   asset class with no point-in-time index-membership concept (see its
   docstring for why that is legitimate there and never on equities).
 * A run in which EVERY attempted formation saw zero eligible tickers is
   now its own status ("no_eligible_universe"), its own counted field
   (CrossSectionalBacktestResult.n_zero_eligible_formations), an ERROR log,
   and — at screening level, where the whole run is empty for that reason —
   a raised EmptyEligibleUniverseError. It can no longer be mistaken for
   "ran fine, found nothing interesting", which is exactly what it looked
   like before.

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

A SEPARATE gap, independent of the above, and only PARTLY closed: until
2026-08-26 no borrow cost or short-availability constraint was modeled
anywhere in this harness — every bottom-decile name was assumed freely
shortable at the flat DEFAULT_XS_COST_BPS. In live markets the names these
signals route to the short leg (steep decliners, negative capital-gains
overhang, i.e. the same distressed profile as the paragraph above) are
disproportionately likely to be hard-to-borrow or carry a real negative
rebate — a cost this backtest could not see. This DOES bias any positive
short-leg contribution to look more achievable live than it would be —
the one factor identified here that points the ordinary "optimistic"
direction, and it applies regardless of how the survivorship question
above resolves.

config.financing_bps_per_year now gives that cost somewhere to live (see
the financing bullet in CONVENTIONS below, and the field's own docstring),
but it DEFAULTS TO 0.0 and therefore closes nothing on its own: every
equity family screened before it existed (Round C, Round D, D1, D2) still
carries the full undisclosed short-borrow optimism described above,
byte-for-byte unchanged, because none of them sets it. The knob is a place
to put a real, sourced number — not a claim that one has been sourced.
Short-AVAILABILITY (can this name be borrowed at all, in what size) is
still not modeled at any price.

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
   is unusable at that formation (see _resolve_leg_weights). Two further
   modes were added 2026-08-27 for the FX family (cross_sectional_fx.py),
   whose literature reports neither magnitude- nor cap-weighted legs:
   "equal" (every member the same share — the plain convention of the G10
   carry/momentum literature, where a "basket" means an equally weighted
   one and there is no market cap to weight a currency by at all) and
   "inverse_vol" (weight by CrossSectionalData.leg_weight_basis, a generic
   positive per-ticker quantity — 1/trailing-vol for that family — through
   the identical normalize-then-cap machinery "value" uses, with the same
   whole-leg magnitude fallback when any member's basis is unusable). ALL
   FOUR schemes still leave each leg's weights summing to exactly 1.0, so
   the self-financing argument two sentences up holds unchanged for every
   one of them.
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
 * TWO cost components, deliberately never collapsed into one number.
   config.cost_bps is per unit of gross notional TRADED — it is paid once
   per formation and scales with TURNOVER, so trading more often costs
   more. config.financing_bps_per_year (added 2026-08-26, default 0.0) is
   per unit of gross notional HELD per year — borrow on a short leg, FX
   rollover/swap points, bond repo — so it accrues while a position sits
   and holding LONGER costs more. The two therefore push in OPPOSITE
   directions across the holding_days axis this whole round is a search
   over (fewer trade-cost hits but more financing accrual as holds
   lengthen), which is precisely why one blended "cost" number cannot
   represent both: any single per-trade figure that is right at
   holding_days=5 is wrong at holding_days=756, in a direction that
   depends on which component dominates. Every non-equity asset class a
   feasibility scout examined (bonds, FX) needs BOTH.
   Accrual convention: financing is charged on each realized day for the
   CALENDAR days actually elapsed since the previous realized close
   ((index[j] - index[j-1]).days / 365), so a Friday-to-Monday day carries
   three days of it and a full calendar year of holding costs exactly the
   full stated annual rate. Charging 1/365 per TRADING day instead would
   have made weekends free and undercharged a continuously-held book by
   ~31% (252/365) — the wrong direction for a cost, in a module whose
   other disclosures are all about not flattering results. Financing is
   reported SEPARATELY (CrossSectionalBacktestResult.total_financing_cost,
   CrossSectionalScreeningResult.total_financing_drag) and never folded
   into total_cost, which stays exactly the turnover charge it always was.
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

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.research_lab.sp500_membership_history import was_member

logger = logging.getLogger(__name__)

# One-way cost per unit of gross notional traded at a formation — mirrors
# momentum.py's DEFAULT_COST_BPS = 5.0 single-leg convention (itself half of
# pairs' two-leg 10bps), not independently recalibrated. A full long-short
# formation from flat trades gross notional 2.0 (buy 1.0 of longs, sell 1.0
# of shorts), so establishing the book costs ~10bps of equity, and each
# reformation costs 10bps times the fraction of the book actually replaced
# — far below the every-bar cost bleed the Round A/B post-mortem diagnosed,
# which is the entire economic thesis of this round.
DEFAULT_XS_COST_BPS = 5.0

# The SECOND, structurally different cost component (see the two-cost
# CONVENTIONS bullet): bps per YEAR per unit of gross notional HELD, not per
# trade — short-leg equity borrow, FX rollover/swap points, bond repo.
# Defaults to 0.0, and that default is load-bearing, not a placeholder
# guess: every equity family screened before this existed (Round C, Round D,
# D1, D2) must keep producing byte-identical numbers, and this project has
# no sourced borrow-rate data for those names to substitute in. A family
# that DOES know its financing rate (a bond or FX basket, whose carry is a
# published, observable number) sets config.financing_bps_per_year itself.
DEFAULT_FINANCING_BPS_PER_YEAR = 0.0

# 365, not 252: financing accrues on CALENDAR days — a book held over a
# weekend pays three days of borrow/repo/rollover, and a book held for one
# calendar year pays exactly one year of it. Paired with the calendar-day
# elapsed measurement in _replay_sleeve, this makes the total charge over a
# hold exactly rate * (calendar days actually held) / 365. See the
# CONVENTIONS bullet for why the trading-day alternative (1/365 per trading
# day, ~252/365 = 69% of the stated rate per year) was rejected as a
# systematic UNDERcharge of a real cost.
FINANCING_DAYS_PER_YEAR = 365.0

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

# The leg_weighting modes that read an EXTERNAL per-ticker frame and can
# therefore fail to resolve one, falling back to magnitude weighting for the
# whole leg (see _resolve_leg_weights). "magnitude" is itself the fallback
# and "equal" needs no data at all, so neither can ever fall back — which is
# why the fallback tally in screen_cross_sectional_universe is keyed on this
# tuple rather than on "not magnitude".
BASIS_WEIGHTED_MODES: tuple[str, ...] = ("value", "inverse_vol")


class EmptyEligibleUniverseError(RuntimeError):
    """Raised by screen_cross_sectional_universe when EVERY formation it
    attempted across the ENTIRE run saw zero eligible tickers — i.e. the
    membership gate rejected the whole universe on every date, so nothing
    was ever ranked, held, or realized.

    This is a configuration error, never a research finding, which is why
    it is an exception rather than an empty list. The caller supplied price
    data for a set of tickers and a membership_fn; if their intersection is
    empty on every single formation date, no possible signal definition
    could have produced a result, so the run answered nothing at all — it
    did not answer "no edge here". The distinction matters because those
    two used to be the same empty list (confirmed live on a bond-ETF family
    2026-08-26: 17 formations, n_eligible=0 on all of them, a 339-day
    series of exact 0.0 returns, and `[]` back from screening — visually
    identical to a family whose specs all fell below the data floors).

    Deliberately NOT raised for the other, genuinely legitimate ways a run
    can produce zero usable formations, which keep their existing quieter
    handling because they are real research outcomes about a real universe:
    a universe too small for config.min_names_per_leg, legs that would
    overlap at the requested rank_fraction, or too little history — all of
    which still report status "no_valid_formations"/"insufficient_history"
    and an empty screening list, exactly as before."""


def fixed_universe_membership(tickers: Iterable[str]) -> MembershipFn:
    """A MembershipFn treating every ticker in a FIXED basket as eligible on
    every date — the correct gate for an asset class that has no
    point-in-time index-membership concept at all.

    WHY THIS IS LEGITIMATE HERE, AND ONLY HERE. was_member exists because an
    S&P 500 cross-section has a real, moving, survivorship-relevant
    membership boundary: firms are added and deleted, deletions cluster on
    failure, and forming deciles from today's constituent list silently
    deletes the very names the short leg would have wanted (see this
    module's POINT-IN-TIME UNIVERSE section). A bond-ETF, FX, commodity or
    crypto basket has no such boundary to get wrong. AGG was not "added to
    an index of bond ETFs" on some date; EURUSD is not a constituent of
    anything. The universe is a hand-chosen list of instruments that are
    liquid TODAY, every one of them is continuously tradeable across the
    whole backtest window, and the survivorship machinery has nothing to
    correct — there is no delisting-clustered exit process, and no
    membership event whose date could be gotten wrong.

    What this helper does NOT do, and must never be used to pretend it does:
     * It is NOT a substitute for was_member on EQUITIES. Passing an equity
       list here reintroduces exactly the survivorship bias this module was
       built to eliminate — today's surviving members applied retroactively
       across a window they were not all members of — and the module
       docstring explains at length why that bias is worse for a
       cross-sectional long-short design than for anything built before it.
       If the tickers are single stocks, this is the wrong function.
     * It does not make a NON-equity universe automatically bias-free.
       Choosing today's liquid ETFs is still a choice made with hindsight:
       a fund that launched in 2019 has no 2015 history (it will simply
       never rank, the same "eligible but unpriceable" hole the equity path
       has), and a fund that CLOSED before today would never have made the
       hand-chosen list at all. That second one is a genuine, if much
       smaller, survivorship channel — small because ETF closures are rare
       among the large liquid instruments these baskets are built from and
       are announced/orderly rather than failure-clustered, but not zero.
       Disclose it; do not claim this helper eliminated it.

    Empty `tickers` is rejected loudly rather than returning an
    always-False function: an empty fixed universe would reproduce, exactly,
    the silent all-zero-eligible failure this helper exists to prevent.
    """
    members = frozenset(tickers)
    if not members:
        raise ValueError(
            "fixed_universe_membership() needs at least one ticker — an empty basket would make "
            "every ticker ineligible on every formation date, which is the exact silent fake-empty "
            "failure this helper exists to prevent (see EmptyEligibleUniverseError)."
        )

    def _is_member(ticker: str, _on: date) -> bool:
        return ticker in members

    return _is_member


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
    # A SECOND close-price series on a different adjustment basis: split-
    # adjusted but dividend-UNadjusted, aligned to close exactly like the
    # frames above. `close` itself is, and must remain, the dividend-adjusted
    # TOTAL-RETURN basis (auto_adjust=True) everywhere — every realized
    # return this harness computes comes off it, and swapping in an
    # unadjusted price would get the SIGN wrong on income-dominated
    # instruments, not merely the magnitude.
    #
    # This frame exists because a family may need to observe INCOME
    # separately from PRICE CHANGE, which neither basis alone can show. The
    # wedge between them over a window is the distribution actually paid:
    # (TR_t/TR_{t-L}) / (PX_t/PX_{t-L}) - 1 is an OBSERVED yield, not an
    # assumed one. Added 2026-08-27 for cross_sectional_bonds.py's curve
    # carry/roll-down mechanism, whose whole construction is a yield pickup
    # per unit of duration; supplied by YFinanceProvider.
    # get_total_and_price_return_closes, which returns both bases from one
    # download.
    #
    # It lives HERE, on CrossSectionalData, rather than being fetched inside
    # the consuming family, for the reason open/volume/market_cap do: the
    # per-formation history view below slices it to rows <= the formation
    # date alongside every other frame, so a signal reading it CANNOT see a
    # future distribution however buggy it is. A family holding its own
    # second price frame would have no such structural guarantee.
    #
    # Deliberately NOT reused as market_cap even though get_market_cap_basis
    # returns the same adjustment basis: that field means shares outstanding
    # x price and is read by the leg-WEIGHTING step, while this one is a
    # price read by SIGNALS. Same numbers, different jobs.
    price_only_close: pd.DataFrame | None = None
    # A GENERIC positive per-ticker quantity a leg may be weighted
    # proportionally to, aligned to close exactly like the frames above.
    # Read only by leg_weighting == "inverse_vol" (see _resolve_leg_weights),
    # which is the FX family's risk-parity weighting — that family fills
    # this with 1 / trailing realized volatility, computed point-in-time.
    #
    # Deliberately NOT folded into market_cap even though _apply_weight_cap
    # treats both identically (any positive scale, normalized then capped):
    # market_cap has a specific, load-bearing meaning documented above and
    # in cross_sectional_ivol.build_point_in_time_market_cap (shares
    # outstanding x a split-adjusted, dividend-UNadjusted close), and
    # smuggling a volatility reciprocal through a field named "market cap"
    # is exactly the kind of silent semantic drift the rest of this module
    # is written to prevent. A family that wants BOTH can carry both.
    leg_weight_basis: pd.DataFrame | None = None
    # SHARE COUNTS THEMSELVES — not shares x price — one column per ticker,
    # aligned to close exactly like the frames above: the point-in-time
    # split-adjusted count of shares outstanding, step-forward-filled from
    # real filing-dated observations. Added 2026-08-27 for
    # cross_sectional_buyback.py, whose whole signal is the TRAILING CHANGE
    # in this quantity (net share issuance: shrinking = buybacks, growing =
    # dilution).
    #
    # Deliberately NOT read off market_cap, even though market_cap is
    # literally this frame times a price and a family could in principle
    # divide it back out. Two reasons, both load-bearing. (1) A market cap
    # moves overwhelmingly because the PRICE moved; recovering the share
    # count from it would require dividing by exactly the same price basis
    # it was built with, and getting that basis wrong is precisely the class
    # of bug the "TWO INPUTS, ONE BASIS" note in build_point_in_time_market_
    # cap documents. (2) market_cap is read by the leg-WEIGHTING step and
    # this frame is read by SIGNALS — the same separation of jobs that keeps
    # price_only_close distinct from market_cap despite sharing an
    # adjustment basis.
    #
    # THE STEP FUNCTION IS THE DATA, not an artifact to be smoothed. Share
    # counts are published quarterly and change discretely; the frame a
    # family builds here must be a forward-filled STEP series, never an
    # interpolated one. Interpolating would manufacture intermediate values
    # that were never filed, never knowable point-in-time, and would turn a
    # signal about corporate actions into a signal about a smoothing kernel.
    # See cross_sectional_buyback.build_point_in_time_share_counts, which
    # also refuses to carry a count forward past a bounded staleness rather
    # than letting a dead series masquerade as current.
    shares_outstanding: pd.DataFrame | None = None
    # A PRECOMPUTED PER-TICKER FUNDAMENTAL QUANTITY the family's signal
    # ranks on directly — one column per ticker, aligned to close exactly
    # like the frames above. Added 2026-08-28 for cross_sectional_quality.py
    # (cash-based operating profitability and net operating assets, both
    # computed OUTSIDE the harness from SEC EDGAR XBRL filing-dated annual
    # observations and forward-filled as a step series from each value's
    # real FILING date, never its period end).
    #
    # Deliberately GENERIC (one field, not one per factor), following
    # leg_weight_basis's own precedent: the harness's job here is only to
    # slice this frame into the per-formation history view alongside every
    # other frame, which is what extends the structural look-ahead guarantee
    # to it — a signal reading it CANNOT see a row after the formation date.
    # What the harness canNOT guarantee is the point-in-time correctness of
    # the VALUES themselves (that a number only appears from its real public
    # filing date onward); that responsibility stays with the supplying
    # family's builder, exactly as it does for market_cap and
    # shares_outstanding, and is unit-tested there.
    #
    # THE STEP FUNCTION IS THE DATA, same rule as shares_outstanding above:
    # annual fundamentals change once a year at a filing; the frame must be
    # a forward-filled STEP series, never interpolated, and must refuse
    # (NaN) a value carried beyond a bounded staleness.
    fundamental_signal: pd.DataFrame | None = None


def validate_cross_sectional_data(data: CrossSectionalData) -> None:
    for name, frame in (
        ("open", data.open),
        ("volume", data.volume),
        ("market_cap", data.market_cap),
        ("price_only_close", data.price_only_close),
        ("leg_weight_basis", data.leg_weight_basis),
        ("shares_outstanding", data.shares_outstanding),
        ("fundamental_signal", data.fundamental_signal),
    ):
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
    # Declares that this spec's SIGNAL reads CrossSectionalData.
    # price_only_close (the split-adjusted, dividend-unadjusted basis).
    # Added 2026-08-27 for cross_sectional_bonds.py's carry mechanism, and
    # follows requires_open/requires_volume/requires_market_cap exactly:
    # False by default, so every spec predating it is unaffected, and
    # checked once up front in run_cross_sectional_backtest so a family that
    # forgot to supply the frame fails loudly on formation zero instead of
    # deep inside a signal function on some later formation.
    requires_price_only_close: bool = False
    # Declares that this spec's SIGNAL reads CrossSectionalData.
    # shares_outstanding (the point-in-time split-adjusted share-count step
    # series). Added 2026-08-27 for cross_sectional_buyback.py's net-share-
    # issuance signal, and follows requires_price_only_close exactly: False
    # by default, so every spec predating it is unaffected, and checked once
    # up front in run_cross_sectional_backtest so a family that forgot to
    # supply the frame fails loudly on formation zero rather than returning a
    # whole run of all-NaN signals that look like "no ticker qualified".
    requires_shares_outstanding: bool = False
    # Declares that this spec's SIGNAL reads CrossSectionalData.
    # fundamental_signal (the precomputed point-in-time fundamental step
    # series). Added 2026-08-28 for cross_sectional_quality.py, and follows
    # requires_shares_outstanding exactly: False by default so every spec
    # predating it is unaffected, and checked once up front in
    # run_cross_sectional_backtest so a family that forgot to supply the
    # frame fails loudly on formation zero rather than producing a run of
    # all-NaN signals indistinguishable from "no ticker qualified".
    requires_fundamental_signal: bool = False
    # "magnitude" (default, every family before Build D1): _leg_weights --
    # weight by each member's own distance from the leg's boundary. "value":
    # weight the ranked long/short legs by real point-in-time market cap
    # instead (see _resolve_leg_weights and cross_sectional_ivol.py's
    # citations for why -- the AHXZ/Bali-Cakici/Blitz-van Vliet
    # idiosyncratic-volatility literature is standardly reported
    # value-weighted, and an equal- or magnitude-weighted low-IVOL portfolio
    # is well documented to load heavily on illiquid micro-caps in a way
    # that misrepresents the anomaly's tradeable size). "equal" and
    # "inverse_vol" were added 2026-08-27 for cross_sectional_fx.py -- see
    # the module docstring's leg-weighting bullet and _resolve_leg_weights.
    # Defaulted to "magnitude" so every existing spec (Round C, Round D, D1,
    # D2) is byte-for-byte unaffected by this field's existence.
    leg_weighting: Literal["magnitude", "value", "equal", "inverse_vol"] = "magnitude"
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
    # The TIME-based cost component: bps per YEAR per unit of gross notional
    # HELD, accrued on calendar days elapsed (see the two-cost CONVENTIONS
    # bullet and FINANCING_DAYS_PER_YEAR). Structurally NOT cost_bps: that
    # one is charged per unit of notional TRADED, once per formation, and
    # scales with turnover; this one is charged for as long as the book is
    # held and scales with time. A hold twice as long pays twice this and
    # half as many of those.
    #
    # It lives on the CONFIG rather than the SPEC on purpose, following the
    # split this file already uses everywhere: a CrossSectionalSpec
    # describes a signal HYPOTHESIS (what to rank on, how long to hold, how
    # to weight), while CrossSectionalConfig describes the MARKET the
    # hypothesis is traded in (cost_bps, delisting treatment). Financing
    # rate is a property of the asset class and the broker, identical across
    # every spec in a family and independent of what any of them ranks on —
    # the same reason cost_bps has never been per-spec. A family whose specs
    # genuinely faced different financing rates would be a family mixing
    # asset classes, which needs separate screening runs anyway (their
    # sibling-Sharpe sigma_sr would not be comparable either).
    #
    # HOW TO SET IT, since the base is GROSS notional held (sum of |net
    # weights|), matching cost_bps' own gross-notional-traded base: a fully
    # formed long_short book carries gross 2.0 (1.0 long + 1.0 short), so a
    # rate of R bps/yr costs 2 * R bps/yr of equity. For an equity family
    # where only the SHORT leg pays borrow at B bps/yr, pass B / 2 — half
    # the book is short, so B/2 applied to gross 2.0 is exactly B on the
    # 1.0 short leg. For a bond or FX basket where BOTH legs finance (repo
    # both sides, rollover both sides), pass the per-unit rate directly.
    # 0.0 (the default) is an exact no-op: no financing term is computed or
    # subtracted at all, so every family that predates this field is
    # byte-for-byte unaffected -- see DEFAULT_FINANCING_BPS_PER_YEAR on why
    # that default is deliberate rather than an unfilled placeholder.
    financing_bps_per_year: float = DEFAULT_FINANCING_BPS_PER_YEAR
    # How many realized return observations a YEAR of this asset class's
    # data contains — the annualization factor for metrics.sharpe_ratio and
    # the de-annualization factor for deflated_sharpe.compute_deflated_
    # sharpe, both called by screen_cross_sectional_universe below.
    #
    # It lives on the CONFIG, beside cost_bps and financing_bps_per_year and
    # for the identical reason: a CrossSectionalSpec describes a signal
    # HYPOTHESIS, while a CrossSectionalConfig describes the MARKET that
    # hypothesis trades in. A year length is a property of the market's
    # CALENDAR, identical across every spec in a family and independent of
    # what any of them ranks on.
    #
    # 252 (metrics.TRADING_DAYS_PER_YEAR) is the exchange-traded default and
    # is load-bearing: every equity, bond, FX and commodity family screened
    # before this field existed must keep producing byte-identical numbers,
    # which a regression test over all eight of them pins exactly
    # (tests/test_periods_per_year_regression.py).
    #
    # A 24/7/365 market passes 365. This is NOT cosmetic: crypto genuinely
    # produces 365-366 rows a year (verified live 2026-08-27 — BTC-USD has
    # zero missing calendar days since 2018, against SPY's 250-253 sessions),
    # so annualizing it at 252 understates every Sharpe by sqrt(252/365) and,
    # worse, compute_deflated_sharpe would then divide the point estimate and
    # the sibling-noise benchmark by DIFFERENT year lengths than the one they
    # were built with. Note FINANCING_DAYS_PER_YEAR is a separate 365.0 and
    # is already correct for every asset class — financing accrues on
    # calendar days everywhere, which is a different question from how many
    # return OBSERVATIONS a year holds.
    periods_per_year: float = TRADING_DAYS_PER_YEAR


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
    # "no_eligible_universe" (added 2026-08-26) is a STRICT REFINEMENT of
    # "no_valid_formations", split out of it for the one cause that is a
    # configuration error rather than a research outcome: every formation
    # attempted saw zero eligible tickers, so the membership gate rejected
    # the entire universe on every date. The classic causes of
    # "no_valid_formations" (universe smaller than min_names_per_leg,
    # overlapping legs) all still report "no_valid_formations" exactly as
    # before -- they had eligible tickers and declined to form legs from
    # them, which is a real answer about a real universe. See
    # EmptyEligibleUniverseError for why the two must not look alike.
    status: Literal["ok", "insufficient_history", "no_valid_formations", "no_eligible_universe"]
    daily_returns: pd.Series  # net of costs, one observation per realized trading day
    formations: list[FormationRecord] = field(default_factory=list)
    total_cost: float = 0.0  # sum of all formation-turnover cost charges
    # Sum of all time-based financing/borrow/carry charges (see config.
    # financing_bps_per_year). Reported SEPARATELY from total_cost, never
    # added into it: the two scale with opposite things (turnover vs time),
    # so a single blended number would hide which one a given holding
    # period is actually paying. Exactly 0.0 whenever financing_bps_per_year
    # is 0.0, which is the default.
    total_financing_cost: float = 0.0
    # How many attempted formations saw an EMPTY eligible set. A first-class
    # counted field rather than only a status/log, on the same reasoning as
    # FormationRecord's value-weight fallback flags: a caller that ignores
    # `status` still has an unmissable number, and a PARTIALLY empty run
    # (some dates eligible, some not -- e.g. formations running off the
    # front of membership coverage) is visible here even though it does not
    # trip the all-empty status or the screening-level exception.
    n_zero_eligible_formations: int = 0


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
            for t, w_under in under.items():
                weights[t] += excess_to_redistribute * (w_under / under_total)
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
    leg_weighting: Literal["magnitude", "value", "equal", "inverse_vol"],
    market_cap: pd.Series | None,
    weight_basis: pd.Series | None = None,
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
    naked partial book).

    "equal" (added 2026-08-27 for the FX family) is the one mode that needs
    no data at all and therefore can never fall back: every member gets
    1/len(tickers). It is NOT routed through _apply_weight_cap because it
    has nothing to cap — a uniform leg's every weight is exactly one equal
    share, and MAX_WEIGHT_MULTIPLE (3.0) times an equal share is by
    definition unreachable.

    "inverse_vol" (same date, same family) is "value" with a different,
    explicitly generic source frame: it reads CrossSectionalData.
    leg_weight_basis instead of .market_cap and is otherwise byte-identical
    — same positivity/NaN usability gate, same _apply_weight_cap, same
    whole-leg fallback to _leg_weights with used_fallback=True. Sharing the
    code path rather than duplicating it is deliberate: the concentration
    cap and the no-partial-state fallback discipline are properties of
    basis weighting in general, not of market cap in particular."""
    if len(tickers) <= 1 or leg_weighting == "magnitude":
        # Size 0/1 reduces correctly under every scheme ({} / forced full
        # weight) and there is no "which weighting" question to ask about a
        # single name's own weight, so this is never a fallback.
        return _leg_weights(tickers, signal, higher_is_stronger=higher_is_stronger), False

    if leg_weighting == "equal":
        equal_share = 1.0 / len(tickers)
        return {t: equal_share for t in tickers}, False

    basis = market_cap if leg_weighting == "value" else weight_basis
    caps = None if basis is None else basis.reindex(tickers)
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


@dataclass(frozen=True)
class FormationOutcome:
    """Everything ONE formation date produces, as a single value.

    EXTRACTED, NOT INVENTED. Every field below was already a local variable
    inside _replay_sleeve's loop body; this dataclass and form_portfolio()
    below are a pure extraction of that body's first half, made callable
    from outside the batch replay loop. The reason is
    cross_sectional_forward.py: a forward-validation tick has to form the
    SAME book, from the SAME signal, with the SAME leg weighting, turnover
    and cost arithmetic, one real day at a time — and the one thing it must
    never do is grow a second implementation of that arithmetic that could
    quietly drift from the backtest whose result it is supposed to be
    validating. Exactly engine.py's step_one_day rationale ("not two
    implementations that could drift apart"), applied to the cross-sectional
    harness.

    realized_short_weights is deliberately separate from the ranked bottom
    leg: for portfolio == "long_universe_hedged" the side actually shorted
    each day is the equal-weighted WHOLE eligible universe, not a rank-cutoff
    leg (see _target_weights)."""

    record: FormationRecord
    long_weights: dict[str, float]
    realized_short_weights: dict[str, float]
    net_weights: dict[str, float]
    turnover_cost: float
    gross_notional_held: float


def form_portfolio(
    data: CrossSectionalData,
    spec: CrossSectionalSpec,
    config: CrossSectionalConfig,
    is_member: MembershipFn,
    position: int,
    prev_weights: dict[str, float],
) -> FormationOutcome:
    """Form one formation date's book: point-in-time eligibility, the
    history view, the signal, the ranked legs, their weights, the net
    target weights, turnover and its cost.

    `position` is the integer row of the formation date in data.close.
    `prev_weights` is the book being replaced (empty dict from flat), which
    is what turnover is measured against.

    LOOK-AHEAD IS STRUCTURAL, NOT ASSERTED. The history view handed to
    spec.signal_fn is data.close.iloc[row_start : position + 1] — rows
    strictly up to and including the formation date, columns restricted to
    that date's eligible tickers. A signal function CANNOT read a future row
    because the row is not in the frame it is given. That property is what
    makes this same function safe to call with position == len(index) - 1 in
    a live forward-validation tick, where "the last row" is literally today:
    there is no future data anywhere in the frame to leak."""
    index = data.close.index
    i = position
    formation_ts = index[i]
    formation_day: date = formation_ts.date()

    # Point-in-time eligibility: an index member on the formation date,
    # with a price at that date's close (a member with no price today
    # cannot be ranked or traded). This is THE survivorship-bias gate —
    # see module docstring.
    formation_close = data.close.iloc[i]
    eligible = [t for t in data.close.columns if is_member(t, formation_day) and np.isfinite(formation_close[t])]

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
            volume=(data.volume.iloc[row_start : i + 1].loc[:, eligible] if data.volume is not None else None),
            market_cap=(
                data.market_cap.iloc[row_start : i + 1].loc[:, eligible] if data.market_cap is not None else None
            ),
            price_only_close=(
                data.price_only_close.iloc[row_start : i + 1].loc[:, eligible]
                if data.price_only_close is not None
                else None
            ),
            leg_weight_basis=(
                data.leg_weight_basis.iloc[row_start : i + 1].loc[:, eligible]
                if data.leg_weight_basis is not None
                else None
            ),
            shares_outstanding=(
                data.shares_outstanding.iloc[row_start : i + 1].loc[:, eligible]
                if data.shares_outstanding is not None
                else None
            ),
            fundamental_signal=(
                data.fundamental_signal.iloc[row_start : i + 1].loc[:, eligible]
                if data.fundamental_signal is not None
                else None
            ),
        )
        signal = spec.signal_fn(view)
        top, bottom = select_leg_tickers(signal, spec.rank_fraction)
        n_ranked = int(signal.dropna().shape[0])
        n_leg = len(top)
        if n_leg < config.min_names_per_leg:
            skipped_reason = (
                f"only {n_ranked} ranked names -> leg of {n_leg} < min_names_per_leg={config.min_names_per_leg}"
            )
        elif 2 * n_leg > n_ranked:
            skipped_reason = f"legs would overlap ({n_ranked} ranked names for two legs of {n_leg})"
        else:
            # Leg weighting reads the FORMATION row directly from `data`
            # (not the view) — market cap needs only today's row, not a
            # lookback window, and this is the exact same row
            # `formation_close` above was already read from.
            market_cap_row = data.market_cap.iloc[i] if data.market_cap is not None else None
            basis_row = data.leg_weight_basis.iloc[i] if data.leg_weight_basis is not None else None

            long_tickers = top
            long_weights, long_fallback = _resolve_leg_weights(
                top,
                signal,
                higher_is_stronger=True,
                leg_weighting=spec.leg_weighting,
                market_cap=market_cap_row,
                weight_basis=basis_row,
            )
            if spec.portfolio == "long_short":
                short_tickers = bottom
                short_weights, short_fallback = _resolve_leg_weights(
                    bottom,
                    signal,
                    higher_is_stronger=False,
                    leg_weighting=spec.leg_weighting,
                    market_cap=market_cap_row,
                    weight_basis=basis_row,
                )
    else:
        skipped_reason = "no eligible tickers (point-in-time membership + price availability)"

    new_weights = _target_weights(long_weights, short_weights, spec.portfolio, eligible)
    turnover = _turnover(prev_weights, new_weights)
    cost = (config.cost_bps / 10_000.0) * turnover

    record = FormationRecord(
        date=formation_ts,
        n_eligible=len(eligible),
        long_tickers=long_tickers,
        short_tickers=(eligible if spec.portfolio == "long_universe_hedged" and long_tickers else short_tickers),
        turnover=turnover,
        skipped_reason=skipped_reason,
        long_leg_value_weight_fallback=long_fallback,
        short_leg_value_weight_fallback=short_fallback,
    )

    # For long_universe_hedged, the realized "short leg" is the equal-
    # weighted whole eligible universe (see _target_weights) — computed
    # once per formation rather than inside the per-day realization loop.
    realized_short_weights = (
        {t: 1.0 / len(eligible) for t in eligible}
        if spec.portfolio == "long_universe_hedged" and long_tickers
        else short_weights
    )

    # The base the time-based financing charge accrues on: this
    # formation's GROSS notional held, sum of |net weight| -- 2.0 for a
    # fully formed long_short book (1.0 long + 1.0 short), the same
    # gross-notional base config.cost_bps is charged on, and exactly 0.0
    # for a skipped formation (flat book pays no borrow, which is the
    # economically correct answer and follows _target_weights' existing
    # "a skipped formation is FLAT, never a naked partial book" rule).
    gross_notional_held = sum(abs(w) for w in new_weights.values())

    return FormationOutcome(
        record=record,
        long_weights=long_weights,
        realized_short_weights=realized_short_weights,
        net_weights=new_weights,
        turnover_cost=cost,
        gross_notional_held=gross_notional_held,
    )


def realize_formation_day(
    day_returns: pd.Series,
    long_weights: dict[str, float],
    realized_short_weights: dict[str, float],
) -> float:
    """One held day's GROSS (pre-cost, pre-financing) portfolio return:
    the long leg's weighted mean member return minus the short side's.

    The other half of _replay_sleeve's extracted loop body (see
    FormationOutcome). Trivially small on purpose — the substance lives in
    _leg_weighted_return, which already handles a name that stops printing
    mid-hold — but it is the single named place the long-minus-short
    convention is expressed, so the forward-validation tick realizes a day
    by calling THIS rather than by re-deriving the subtraction."""
    return _leg_weighted_return(day_returns, long_weights) - _leg_weighted_return(
        day_returns, realized_short_weights
    )


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
) -> tuple[list[FormationRecord], dict[pd.Timestamp, tuple[float, float, float]], bool]:
    """One independent formation/hold cycle: reforms every spec.holding_days
    trading days starting at start_position. This is this module's
    ORIGINAL (pre-overlap) single-stream algorithm, extracted verbatim so
    run_cross_sectional_backtest can run several of these staggered by
    spec.cohort_formation_days and blend them into one overlapping-cohort
    replay -- a single sleeve at start_position == first_formation
    reproduces every prior (Round C, Round D) behavior bit-for-bit, since
    that is exactly the loop those families already ran.

    Returns (this sleeve's own FormationRecords, {realized date:
    (net_return, turnover_cost_charged_on_that_date,
    financing_cost_charged_on_that_date)}, whether any formation in this
    sleeve actually formed). The (net, cost, financing) triple -- not just
    net -- is what lets the caller blend several sleeves' returns by simple
    average while still reporting honest, SEPARATE cost totals: mean(net_i)
    over active sleeves is exactly the equal-weighted blended net return,
    and mean(cost_i) / mean(financing_i) are that day's actual blended
    drags, all of which collapse to today's single value when only one
    sleeve is active (see run_cross_sectional_backtest)."""
    index = data.close.index
    n = len(index)

    # Per unit of gross notional per calendar day (see config.
    # financing_bps_per_year and FINANCING_DAYS_PER_YEAR). Exactly 0.0 by
    # default, and every use below is guarded on it being truthy, so the
    # financing term is not merely a zero addend but structurally never
    # computed or applied for any family that has not opted in.
    financing_per_notional_day = (
        config.financing_bps_per_year / 10_000.0
    ) / FINANCING_DAYS_PER_YEAR

    formations: list[FormationRecord] = []
    by_date: dict[pd.Timestamp, tuple[float, float, float]] = {}
    prev_weights: dict[str, float] = {}

    any_formed = False

    for i in range(start_position, n - 1, spec.holding_days):
        # The formation half of this loop body now lives in form_portfolio()
        # so a live forward-validation tick can form the identical book from
        # the identical arithmetic (see FormationOutcome). Behavior here is
        # unchanged — that function IS this code, moved.
        outcome = form_portfolio(data, spec, config, is_member, i, prev_weights)
        prev_weights = outcome.net_weights
        if outcome.record.skipped_reason is None:
            any_formed = True

        formations.append(outcome.record)

        long_weights = outcome.long_weights
        realized_short_weights = outcome.realized_short_weights
        cost = outcome.turnover_cost
        gross_notional_held = outcome.gross_notional_held

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
            gross = realize_formation_day(day, long_weights, realized_short_weights)
            # The formation's turnover cost lands on its first realization
            # day — the day the rebalance trades settle into the return
            # stream, mirroring engine.py charging |position change| on the
            # day the position changes.
            cost_today = cost if j == i + 1 else 0.0
            net = gross - cost_today
            # Time-based financing/borrow/carry (config.financing_bps_per_
            # year), accrued over the CALENDAR days actually elapsed since
            # the previous close -- three days across a weekend, one on an
            # ordinary day. Every calendar day between the formation close
            # (position established, day i) and the hold's last realized
            # day is charged exactly once and never twice: the first
            # realized day j == i+1 covers the formation-to-first-close gap,
            # and the next formation in this sleeve starts at the hold's own
            # last day, whose successor day belongs to that next hold. The
            # `if` is what keeps this a strict no-op at the 0.0 default --
            # `net` is not even re-bound, so no float operation touches it.
            financing_today = 0.0
            if financing_per_notional_day and gross_notional_held:
                calendar_days_held = float((index[j] - index[j - 1]).days)
                financing_today = (
                    financing_per_notional_day * gross_notional_held * calendar_days_held
                )
                net -= financing_today
            by_date[index[j]] = (net, cost_today, financing_today)

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
    prove the composed system respects them.

    THAT DEFAULT IS AN S&P 500 EQUITY GATE, not "everything is eligible".
    was_member answers False for every ticker that is not an S&P 500
    member, so leaving membership_fn=None for a bond/FX/commodity/crypto
    basket makes the ENTIRE universe ineligible on every formation date.
    That case is now detected and reported as status "no_eligible_universe"
    with an ERROR log and a counted n_zero_eligible_formations, instead of
    silently returning a long series of exact 0.0 returns under the same
    "no_valid_formations" status a legitimately-unformable equity universe
    gets. Non-equity callers should pass fixed_universe_membership(tickers)
    — see its docstring."""
    validate_cross_sectional_data(data)
    if spec.requires_open and data.open is None:
        raise ValueError(f"{spec.pattern_id} requires daily Open data (CrossSectionalData.open is None).")
    if spec.requires_volume and data.volume is None:
        raise ValueError(f"{spec.pattern_id} requires daily Volume data (CrossSectionalData.volume is None).")
    if spec.requires_market_cap and data.market_cap is None:
        raise ValueError(
            f"{spec.pattern_id} requires point-in-time market cap (CrossSectionalData.market_cap is None)."
        )
    if spec.requires_price_only_close and data.price_only_close is None:
        raise ValueError(
            f"{spec.pattern_id} requires the dividend-unadjusted price basis "
            "(CrossSectionalData.price_only_close is None)."
        )
    if spec.requires_shares_outstanding and data.shares_outstanding is None:
        raise ValueError(
            f"{spec.pattern_id} requires point-in-time share counts "
            "(CrossSectionalData.shares_outstanding is None)."
        )
    if spec.requires_fundamental_signal and data.fundamental_signal is None:
        raise ValueError(
            f"{spec.pattern_id} requires the point-in-time fundamental step series "
            "(CrossSectionalData.fundamental_signal is None)."
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
    if spec.leg_weighting == "inverse_vol" and data.leg_weight_basis is None:
        # Exact analogue of the "value"/market_cap check above, for the same
        # belt-and-suspenders reason: "inverse_vol" is a structural need of
        # the harness's own leg-forming step, so it is checked here whether
        # or not the spec also declared a requires_* flag. Without this the
        # basis would silently be None, every leg would take the
        # magnitude-weighting fallback, and the run would report itself as
        # inverse-vol weighted while being nothing of the kind.
        raise ValueError(
            f"{spec.pattern_id} has leg_weighting='inverse_vol' but "
            "CrossSectionalData.leg_weight_basis is None."
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
    per_date: dict[pd.Timestamp, list[tuple[float, float, float]]] = {}
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
    total_financing_cost = 0.0
    for realized_date in return_dates:
        pairs = per_date[realized_date]
        # Equal-weighted blend across whichever sleeves are concurrently
        # active on this date — mean of a single value when n_sleeves == 1
        # (or only one sleeve happens to be active yet/still), which is
        # exactly the un-blended original value: this is what makes the
        # n_sleeves == 1 path numerically identical to the pre-overlap
        # algorithm, not merely structurally similar. Financing blends the
        # same way and for the same reason (it is already a per-sleeve
        # per-day charge inside each sleeve's own net return).
        net_returns.append(float(np.mean([p[0] for p in pairs])))
        total_cost += float(np.mean([p[1] for p in pairs]))
        total_financing_cost += float(np.mean([p[2] for p in pairs]))

    daily = pd.Series(net_returns, index=pd.DatetimeIndex(return_dates), dtype=float)

    # THE LOUD FAILURE MODE (see EmptyEligibleUniverseError and the module
    # docstring's NON-EQUITY UNIVERSES section). Zero eligible tickers on
    # EVERY attempted formation is not a research outcome about a universe,
    # it is the membership gate having rejected the universe outright —
    # nothing was ever ranked and every "return" below is a structural 0.0,
    # not a measured flat day. It gets its own status, its own counted
    # field, and an ERROR log, so it can never again be read as the same
    # thing as a universe that was eligible but declined to form legs.
    n_zero_eligible = sum(1 for f in all_formations if f.n_eligible == 0)
    universe_never_eligible = bool(all_formations) and n_zero_eligible == len(all_formations)

    status: Literal["ok", "insufficient_history", "no_valid_formations", "no_eligible_universe"]
    if universe_never_eligible:
        status = "no_eligible_universe"
        logger.error(
            "%s: ZERO eligible tickers on ALL %d attempted formations (%s .. %s) — the membership "
            "gate rejected the entire universe of %d ticker(s), so nothing was ranked and the %d "
            "returned daily 'returns' are structural zeros, NOT a measured flat result. If this is "
            "a non-equity universe (bonds, FX, commodities, crypto), the cause is almost certainly "
            "membership_fn=None defaulting to the S&P 500 gate sp500_membership_history.was_member, "
            "which answers False for every non-member: pass "
            "cross_sectional.fixed_universe_membership(tickers) instead.",
            spec.pattern_id,
            len(all_formations),
            all_formations[0].date.date(),
            all_formations[-1].date.date(),
            len(data.close.columns),
            len(daily),
        )
    elif any_formed:
        status = "ok"
    else:
        status = "no_valid_formations"
        if n_zero_eligible:
            # Partially empty: some dates had an eligible cross-section and
            # some had none. Not the all-empty configuration error above, but
            # still worth a line rather than only a silent counter.
            logger.warning(
                "%s: no formation produced usable legs, and %d of %d attempted formations had zero "
                "eligible tickers.",
                spec.pattern_id,
                n_zero_eligible,
                len(all_formations),
            )

    return CrossSectionalBacktestResult(
        status=status,
        daily_returns=daily,
        formations=all_formations,
        total_cost=total_cost,
        total_financing_cost=total_financing_cost,
        n_zero_eligible_formations=n_zero_eligible,
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
    # The time-based financing/borrow/carry drag, reported as its OWN number
    # alongside total_cost_drag (the turnover charge) rather than summed
    # into it -- see the two-cost CONVENTIONS bullet. 0.0 for every family
    # that leaves config.financing_bps_per_year at its 0.0 default, which is
    # every equity family screened to date.
    total_financing_drag: float = 0.0


def screen_cross_sectional_universe(
    data: CrossSectionalData,
    specs: list[CrossSectionalSpec],
    config: CrossSectionalConfig,
    membership_fn: MembershipFn | None = None,
    n_trials_override: int | None = None,
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
    different pattern" as the sibling relation.

    Raises EmptyEligibleUniverseError when EVERY spec that got as far as
    attempting a formation came back with zero eligible tickers on all of
    them — the whole run saw no universe at all. That is the one
    zero-result cause that is a configuration error rather than a finding,
    and before this it returned the same bare `[]` as a family whose specs
    merely fell below the data floors (see that exception's docstring for
    the live bond-ETF case that motivated it). Every other route to an
    empty list — too little history, universe below min_names_per_leg,
    overlapping legs, replays under MIN_REPLAY_TRADING_DAYS — still returns
    `[]` quietly and unchanged, because those are real answers about a real
    universe.

    n_trials_override (added 2026-08-27 for cross_sectional_small_mid_cap.py)
    replaces len(specs) as the DSR denominator, and may ONLY ever be LARGER
    than it — enforced by assertion below, not merely documented, because a
    SMALLER value is precisely the "trial-count laundering" this project
    already identified and rejected once (see cross_sectional_patterns_
    round_d.py's module docstring, which walks through why post-hoc shrinking
    of n_trials produces a corrected-LOOKING Sharpe that is not actually
    corrected for the search that produced the hypothesis). There is no
    legitimate reason to pass a smaller number, so the parameter cannot
    express one.

    WHY A LARGER ONE IS SOMETIMES THE HONEST NUMBER, which is the whole
    reason this parameter exists: len(specs) is the right denominator when
    "which definition" is genuinely the only search dimension — the pooled
    framing above. It is NOT the whole search when the same, already-designed
    family is re-run on a DIFFERENT UNIVERSE, because the universe is then a
    second dimension that was also chosen. Re-running an N-definition family
    on a second universe makes the set of results that could have been
    reported N x 2, and the first universe's N results were already computed
    and seen. Passing 2N there is not conservatism, it is the arithmetic.
    See cross_sectional_small_mid_cap.py, which derives this in full for the
    two families it re-runs.

    Left None (the default), behavior is byte-for-byte what it always was:
    every family screened before this parameter existed is unaffected."""
    n_trials = len(specs)
    if n_trials_override is not None:
        if n_trials_override < n_trials:
            raise ValueError(
                f"n_trials_override={n_trials_override} is SMALLER than the {n_trials} specs actually "
                "screened. That is trial-count laundering — it would report a DSR corrected for fewer "
                "comparisons than were really made (see cross_sectional_patterns_round_d.py). This "
                "parameter exists only to ENLARGE the denominator for a search dimension outside the "
                "spec list, never to shrink it."
            )
        n_trials = n_trials_override

    replays: dict[str, CrossSectionalBacktestResult] = {}
    n_attempted_formations = 0  # specs that actually reached a formation date
    n_no_eligible_universe = 0  # ...of which, saw zero eligible tickers on every one
    for spec in specs:
        result = run_cross_sectional_backtest(data, spec, config, membership_fn)
        if result.formations:
            n_attempted_formations += 1
        if result.status == "no_eligible_universe":
            n_no_eligible_universe += 1
        if result.status != "ok":
            continue
        if len(result.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        replays[spec.pattern_id] = result

    # Run-wide loud failure (see EmptyEligibleUniverseError). Guarded on
    # n_attempted_formations so a family that never reached a single
    # formation — every spec short on history, or an empty spec list — keeps
    # its existing quiet empty-list behavior; this fires only when
    # formations really were attempted and every one of them was handed an
    # empty universe.
    if n_attempted_formations > 0 and n_no_eligible_universe == n_attempted_formations:
        raise EmptyEligibleUniverseError(
            f"Every one of the {n_no_eligible_universe} spec(s) that reached a formation date saw "
            f"ZERO eligible tickers on EVERY formation: none of the "
            f"{len(data.close.columns)} ticker(s) in the supplied price data was ever admitted by "
            "the membership gate. Nothing was ranked, held, or measured — this run answered "
            "nothing; it did not answer 'no edge here'. If this is a non-equity universe (bonds, "
            "FX, commodities, crypto), the cause is almost certainly membership_fn=None defaulting "
            "to the S&P 500 gate sp500_membership_history.was_member, which returns False for every "
            "non-member: pass fixed_universe_membership(tickers) instead. If it IS an equity "
            "universe, check that config.formation_start is at or after "
            "sp500_membership_history.MEMBERSHIP_DATA_START and that the tickers use this project's "
            "symbology (BRK-B, not BRK.B)."
        )

    # Every Sharpe here — the point estimates AND the sigma_sr built from
    # them — is annualized with the SAME config.periods_per_year, and
    # compute_deflated_sharpe below de-annualizes both with that same figure.
    # That consistency is the whole point: a mismatch between the two would
    # compare a point estimate on one year-length against a noise benchmark
    # on another (see CrossSectionalConfig.periods_per_year).
    sharpes = {
        pid: sharpe_ratio(res.daily_returns, periods_per_year=config.periods_per_year)
        for pid, res in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {spec.pattern_id: spec for spec in specs}
    results: list[CrossSectionalScreeningResult] = []
    for pattern_id, replay in replays.items():
        spec = spec_by_id[pattern_id]
        formed = [f for f in replay.formations if f.skipped_reason is None]
        skipped = [f for f in replay.formations if f.skipped_reason is not None]
        avg_leg = float(np.mean([len(f.long_tickers) for f in formed])) if formed else 0.0
        dsr = compute_deflated_sharpe(
            sharpes[pattern_id],
            replay.daily_returns,
            n_trials,
            sigma_sr,
            periods_per_year=config.periods_per_year,
        )

        # Basis-weighting fallback tally: only meaningful for a spec whose
        # weighting reads an external per-ticker frame and can therefore
        # FAIL to — "value" (market_cap) and, since 2026-08-27,
        # "inverse_vol" (leg_weight_basis). "magnitude" and "equal" specs
        # never set either FormationRecord flag (neither can fall back —
        # one IS the fallback, the other needs no data), so both stay 0.
        # The long leg is always attempted under basis weighting; the short
        # leg only for long_short (long_universe_hedged's hedge side is
        # never basis-weighted — see _target_weights).
        n_value_weighted_legs = 0
        n_value_weight_fallbacks = 0
        if spec.leg_weighting in BASIS_WEIGHTED_MODES:
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
                total_financing_drag=replay.total_financing_cost,
                deflated_sharpe=dsr,
                n_value_weighted_legs=n_value_weighted_legs,
                n_value_weight_fallbacks=n_value_weight_fallbacks,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results
