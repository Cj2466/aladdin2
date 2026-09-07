"""PRE-REGISTERED regime definition for the TSMOM candidate family.

THIS MODULE IS A COMMITMENT DEVICE, NOT AN ANALYSIS.
====================================================================
It is committed BEFORE any TSMOM return series exists in this project, so
that the git timestamp on this file is itself evidence that the in-regime /
out-of-regime split was fixed before anyone could see which split flattered
the result. Nothing in this module may be re-tuned after TSMOM returns are
computed. Every threshold below is a named module-level constant with its
source cited; there is no fitted, swept, or caller-supplied parameter
anywhere in the classification path.

WHY A REGIME DEFINITION IS REQUIRED HERE AT ALL
====================================================================
CLAUDE.md rule 4 mandates regime-conditional testing "only when the source
literature's claim is explicitly conditional (e.g. trend-following's claimed
'crisis alpha')". TSMOM is exactly that case: the source paper makes the
conditional claim in its own abstract.

SOURCE
====================================================================
Moskowitz, T. J., Ooi, Y. H. & Pedersen, L. H., "Time series momentum",
Journal of Financial Economics 104(2), 2012, pp. 228-250.
Text below quoted VERBATIM from the authors' own hosted copy
(w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf), extracted
and read in full on 2026-09-07 -- not recalled from memory, per CLAUDE.md's
never-implement-a-published-formula-from-memory rule.

  Abstract, p.228:
    "A diversified portfolio of time series momentum strategies across all
    asset classes delivers substantial abnormal returns with little
    exposure to standard asset pricing factors and performs best during
    extreme markets."

  Introduction, p.229:
    "The abnormal returns to time series momentum also do not appear to be
    compensation for crash risk or tail events. Rather, the return to time
    series momentum tends to be largest when the stock market's returns are
    most extreme -- performing best when the market experiences large up
    and down moves. Hence, time series momentum may be a hedge for extreme
    events[.]"

  Section 4.3 "Performance over time and in extreme markets", p.238:
    "More generally, Fig. 4 plots the TSMOM returns against the S&P 500
    returns. The returns to TSMOM are largest during the biggest up and
    down market movements. To test the statistical significance of this
    finding, the first row of Panel C of Table 3 reports coefficients from
    a regression of TSMOM returns on the market index return and squared
    market index return. While the beta on the market itself is
    insignificant, the coefficient on the market return squared is
    significantly positive, indicating that TSMOM delivers its highest
    profits during the most extreme market episodes. TSMOM, therefore, has
    payoffs similar to an option straddle on the market."

THE HONEST CITATION PROBLEM, STATED PLAINLY
====================================================================
**MOP 2012 does NOT operationalize "extreme markets" as a binary regime.**
This was checked directly in the paper's text rather than assumed. Their
actual significance test (Table 3, Panel C, first row) is a CONTINUOUS
convexity regression of quarterly TSMOM returns on the market return and
the SQUARED market return -- coefficient on the squared term 1.99 with
t-statistic 3.88. There is no drawdown threshold, no volatility percentile,
and no crisis dummy anywhere in that test.

So this project cannot copy a binary rule from MOP, because MOP does not
have one. What follows is therefore a DERIVED rule: constructed to match
the shape of MOP's actual finding as closely as a binary split can, using
MOP's own tail-fraction convention, with every deviation named below. This
is the "standard defensible alternative because the source's own definition
cannot be pinned down as a binary rule" case, stated honestly rather than
dressed up as a direct quotation.

Three design choices follow from the quotes above, and each is forced by
the source rather than chosen for convenience:

1. TWO-SIDED, ON MAGNITUDE -- not a one-sided crisis/crash rule.
   MOP say "largest during the biggest up AND down market movements" and
   their significant term is the SQUARED market return, which is symmetric
   by construction. A one-sided "crisis alpha" drawdown rule would test a
   DIFFERENT claim from the one the source paper actually makes. The
   primary rule below therefore classifies on |market return|.

2. THE 20% TAIL FRACTION comes from MOP's own extremes convention.
   MOP p.240 uses "the top 20% most extreme realizations of the TED spread"
   and, for the sentiment measures, "the top and bottom extremes (20%) of
   these variables". 20% is thus MOP's own choice of what "extreme" means
   when they do binarize a variable -- it is not a number picked here.

3. THE S&P 500 IS MOP'S OWN CHOICE OF INDEX for this specific claim.
   Section 4.3's Fig. 4 -- the figure that displays the extreme-markets
   result -- plots TSMOM against "the S&P 500 returns". (Table 3's
   regressions use MSCI World; this project has no clean MSCI World series,
   and Fig. 4's S&P 500 is both the closer match to the specific claim
   being tested and the series this project has clean, long access to.)
   Deviation logged: proxied by SPY, a total-return ETF, read on its raw
   close (price return, dividends excluded) so it tracks the S&P 500 PRICE
   index that Fig. 4 uses rather than a total-return variant.

A NULL RESULT IN THE SOURCE THAT MUST NOT BE QUIETLY REPRODUCED
====================================================================
The obvious "crisis regime" instinct is a volatility percentile. MOP
TESTED THAT AND FOUND NOTHING. Section 4.4, p.240:

    "the VIX index to capture the level of market volatility and the most
    extreme market volatility environments, which also seem to correspond
    with illiquid episodes. There is no significant relationship between
    TSMOM profitability and market volatility either."

Table 3 Panel C reports VIX t-stat 0.92 and VIX-top-20% t-stat -0.10; the
TED-spread top-20% term is -0.29; every sentiment extreme is insignificant.
Choosing a VIX/realized-vol percentile as the PRIMARY regime would
therefore be reproducing the one operationalization the source paper
explicitly reports as null, while ignoring the one it reports as
significant. That is why the primary rule keys on the magnitude of the
market's REALIZED RETURN, not on its volatility.

CONTEMPORANEOUS BY DESIGN -- THIS IS NOT A TRADEABLE SIGNAL
====================================================================
MOP's claim is contemporaneous: TSMOM earns its largest profits IN THE SAME
quarter in which the market makes its biggest move. Their regression is
contemporaneous, not predictive. The primary rule below is therefore also
contemporaneous: quarter q's label depends on quarter q's own realized
return, and is knowable only at the END of quarter q.

**This means the primary rule MUST NOT be used as a filter, an overlay, or
a timing rule.** It is legitimate only for the purpose it is pre-registered
for: partitioning ALREADY-REALIZED TSMOM returns into two buckets to
compute a separate DSR in each. Using it to decide a position would be
lookahead. A guard is provided (`assert_not_used_as_a_timing_signal`) and
the secondary drawdown rule, which IS pointwise-causal, is offered for any
purpose that genuinely needs a same-day-knowable state.

NO LOOKAHEAD IN THE THRESHOLD ITSELF
====================================================================
Separate from the contemporaneity point above, the 20% CUTOFF is computed
on an EXPANDING window of strictly-prior quarters only. Quarter q is
compared against the 80th percentile of |return| over quarters strictly
before q. The full-sample percentile is never used, because a full-sample
cutoff would leak the future into every early label. A burn-in of
MIN_PRIOR_QUARTERS quarters is required before any label is emitted at all;
quarters before that are labelled UNCLASSIFIED and are excluded from both
buckets rather than being silently dumped into the out-of-regime bucket.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# PRE-DECLARED CONSTANTS. Fixed on 2026-09-07, before any TSMOM return
# series existed in this project. Changing any of these after TSMOM returns
# have been computed invalidates the pre-registration.
# --------------------------------------------------------------------------

#: Tail fraction defining "extreme". MOP 2012 p.240's own convention: "the
#: top 20% most extreme realizations". Not tuned here.
MOP_EXTREME_TAIL_FRACTION = 0.20

#: Minimum number of strictly-prior non-overlapping quarters required before
#: an expanding-window percentile is considered meaningful enough to emit a
#: label. 40 quarters = 10 years. Chosen so the 80th percentile is estimated
#: from at least 8 observations in its own tail; declared before use, not
#: swept.
MIN_PRIOR_QUARTERS = 40

#: Secondary (NON-MOP) rule's drawdown threshold. The 20% peak-to-trough
#: figure is the conventional bear-market definition used by the
#: trend-following/"crisis alpha" industry literature this rule exists to
#: represent -- it is NOT from MOP 2012, which contains no such rule.
SECONDARY_DRAWDOWN_THRESHOLD = 0.20

#: Which rule is the pre-registered primary. Recorded as a constant so the
#: choice is a committed fact in code, not a sentence in a report.
PRIMARY_RULE = "mop_extreme_absolute_quarterly_market_return"

#: The index series the primary rule is defined on, and why.
PRIMARY_RULE_INDEX = "S&P 500 (proxied by SPY raw close, price return)"

_UNCLASSIFIED = "unclassified"
_IN_REGIME = "extreme"
_OUT_OF_REGIME = "normal"


@dataclass(frozen=True)
class RegimeClassification:
    """The full, auditable output of a regime rule.

    `labels` is the only field a downstream DSR split may consume. The
    remaining fields exist so a reviewer can re-derive every label by hand
    from primitives, per CLAUDE.md's independent-verification rule.
    """

    #: Index: period end date. Values: one of _IN_REGIME / _OUT_OF_REGIME /
    #: _UNCLASSIFIED.
    labels: pd.Series
    #: The realized period return that was classified.
    period_returns: pd.Series
    #: The expanding-window cutoff each period was compared against. NaN
    #: while inside the burn-in.
    thresholds: pd.Series
    #: How many strictly-prior periods fed each period's threshold.
    n_prior: pd.Series
    rule_name: str

    @property
    def n_in_regime(self) -> int:
        return int((self.labels == _IN_REGIME).sum())

    @property
    def n_out_of_regime(self) -> int:
        return int((self.labels == _OUT_OF_REGIME).sum())

    @property
    def n_unclassified(self) -> int:
        return int((self.labels == _UNCLASSIFIED).sum())

    def in_regime_periods(self) -> list[pd.Timestamp]:
        return list(self.labels.index[self.labels == _IN_REGIME])


def quarterly_price_returns(prices: pd.Series) -> pd.Series:
    """Non-overlapping calendar-quarter simple returns from a daily price
    series.

    Non-overlapping quarters, rather than a rolling window, because MOP's
    own extreme-markets test (Table 3, Panel C) is run on "quarterly
    non-overlapping returns" -- their Section 4.2 states the quarterly rows
    "uses quarterly non-overlapping returns (to account for any
    non-synchronous trading effects across markets)". Overlapping windows
    would also make the tail-fraction count meaningless by autocorrelating
    adjacent labels.

    The return of a quarter is measured from the last observed price of the
    PREVIOUS quarter to the last observed price of that quarter, so no
    within-quarter gap or holiday shifts the boundary.
    """
    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be a pd.Series indexed by date")
    clean = prices.dropna()
    if not isinstance(clean.index, pd.DatetimeIndex):
        clean = clean.copy()
        clean.index = pd.to_datetime(clean.index)
    clean = clean.sort_index()
    if len(clean) < 2:
        return pd.Series(dtype=float)
    quarter_end_prices = clean.resample("QE").last().dropna()
    return quarter_end_prices.pct_change().dropna()


def classify_extreme_market_quarters(
    prices: pd.Series,
    tail_fraction: float = MOP_EXTREME_TAIL_FRACTION,
    min_prior_quarters: int = MIN_PRIOR_QUARTERS,
) -> RegimeClassification:
    """PRIMARY, PRE-REGISTERED RULE.

    A quarter is IN-REGIME ("extreme") when the absolute value of the broad
    market's realized simple return for that quarter is at or above the
    (1 - tail_fraction) quantile of absolute quarterly returns over all
    STRICTLY PRIOR quarters.

    Two-sided on magnitude, per MOP 2012 Section 4.3 ("largest during the
    biggest up and down market movements") and the symmetric squared-return
    term that is their actual significant test statistic (Table 3 Panel C,
    coefficient 1.99, t = 3.88).

    The defaults are the pre-declared module constants; the parameters exist
    only so the unit tests can exercise degenerate cases. Production callers
    must not pass them.
    """
    returns = quarterly_price_returns(prices)
    if returns.empty:
        empty = pd.Series(dtype=object)
        return RegimeClassification(
            labels=empty,
            period_returns=pd.Series(dtype=float),
            thresholds=pd.Series(dtype=float),
            n_prior=pd.Series(dtype=int),
            rule_name=PRIMARY_RULE,
        )

    magnitudes = returns.abs()
    labels: list[str] = []
    thresholds: list[float] = []
    n_prior: list[int] = []

    for position in range(len(returns)):
        prior = magnitudes.iloc[:position]  # strictly prior -- no lookahead
        n_prior.append(len(prior))
        if len(prior) < min_prior_quarters:
            labels.append(_UNCLASSIFIED)
            thresholds.append(float("nan"))
            continue
        cutoff = float(np.quantile(prior.to_numpy(), 1.0 - tail_fraction))
        thresholds.append(cutoff)
        labels.append(
            _IN_REGIME if float(magnitudes.iloc[position]) >= cutoff else _OUT_OF_REGIME
        )

    return RegimeClassification(
        labels=pd.Series(labels, index=returns.index, dtype=object),
        period_returns=returns,
        thresholds=pd.Series(thresholds, index=returns.index, dtype=float),
        n_prior=pd.Series(n_prior, index=returns.index, dtype=int),
        rule_name=PRIMARY_RULE,
    )


def trailing_drawdown(prices: pd.Series) -> pd.Series:
    """Pointwise drawdown from the trailing running maximum, using only
    prices up to and including each date. Causal by construction: the
    running max is an expanding max, never a full-sample max.

    Returned as a non-negative fraction (0.20 == 20% below the trailing
    peak).
    """
    clean = prices.dropna()
    if not isinstance(clean.index, pd.DatetimeIndex):
        clean = clean.copy()
        clean.index = pd.to_datetime(clean.index)
    clean = clean.sort_index()
    running_peak = clean.cummax()
    return (1.0 - clean / running_peak).astype(float)


def classify_drawdown_regime(
    prices: pd.Series,
    threshold: float = SECONDARY_DRAWDOWN_THRESHOLD,
) -> RegimeClassification:
    """SECONDARY, EXPLICITLY NON-MOP RULE -- recorded for completeness, not
    pre-registered as the primary test of MOP's claim.

    A date is IN-REGIME when the broad market sits at or below `threshold`
    beneath its trailing running peak.

    This is the one-sided "crisis alpha" framing that CLAUDE.md rule 4 names
    as the motivating example. It is deliberately NOT the primary rule,
    because MOP 2012's actual claim is two-sided (large up moves count as
    extreme too) and their significant statistic is symmetric. Reporting a
    drawdown-conditional result AS IF it were MOP's claim would be a
    mechanism-fidelity failure.

    Unlike the primary rule this one IS pointwise-causal -- a given day's
    label is knowable that day -- so it is the appropriate choice if some
    later purpose genuinely needs a same-day-knowable state. It carries no
    burn-in and emits no UNCLASSIFIED labels.
    """
    drawdown = trailing_drawdown(prices)

    # Compare at the PRICE level rather than on the differenced drawdown.
    # Forming (1 - price/peak) and testing it against 0.20 misses an exact
    # 20% drawdown: 1 - 80/100 evaluates to 0.19999999999999996 in IEEE-754
    # double precision, so a textbook-exact boundary case falls on the wrong
    # side. price <= peak * (1 - threshold) is exact for the same case
    # (80 <= 80.0). Ties are near-measure-zero on real data, but a rule that
    # is silently wrong exactly AT its own stated threshold is the kind of
    # defect this project's verification rule exists to catch.
    prices_sorted = prices.dropna().sort_index()
    if not isinstance(prices_sorted.index, pd.DatetimeIndex):
        prices_sorted.index = pd.to_datetime(prices_sorted.index)
    trigger_level = prices_sorted.cummax() * (1.0 - threshold)
    labels = pd.Series(
        np.where(
            prices_sorted.to_numpy() <= trigger_level.to_numpy(),
            _IN_REGIME,
            _OUT_OF_REGIME,
        ),
        index=prices_sorted.index,
        dtype=object,
    )
    return RegimeClassification(
        labels=labels,
        period_returns=drawdown,
        thresholds=pd.Series(threshold, index=drawdown.index, dtype=float),
        n_prior=pd.Series(0, index=drawdown.index, dtype=int),
        rule_name="secondary_non_mop_trailing_drawdown",
    )


def assert_not_used_as_a_timing_signal(purpose: str) -> None:
    """Guard rail with teeth, per the module docstring's contemporaneity
    warning.

    The primary rule labels a quarter using that quarter's own realized
    return, so consuming it to size or gate a position is lookahead. Call
    this at any site that consumes `classify_extreme_market_quarters`,
    naming the purpose; it raises for the purposes that would be lookahead.
    """
    forbidden = ("timing", "overlay", "filter", "position", "sizing", "gate")
    lowered = purpose.lower()
    for word in forbidden:
        if word in lowered:
            raise ValueError(
                f"classify_extreme_market_quarters() is CONTEMPORANEOUS (a quarter's "
                f"label uses that quarter's own realized return) and must not be used "
                f"for {word!r}. It is pre-registered solely for partitioning "
                f"already-realized returns into in-regime / out-of-regime buckets for "
                f"a split DSR. Use classify_drawdown_regime() if you need a "
                f"pointwise-causal state."
            )
