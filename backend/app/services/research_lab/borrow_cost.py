"""SHORT-BORROW COST — a cited, conservative, FREE approximation, in place
of the 0.0 every equity family currently charges.

WHAT IS BEING REPLACED, AND WHY IT IS NOT MERELY MISSING
========================================================
Every US SINGLE-STOCK equity family in this project runs with
CrossSectionalConfig.financing_bps_per_year = 0.0, its default — verified by
grep, not assumed: QUALITY_, BUYBACK_, BEST_IDEAS_ and
SHORT_INTEREST_FINANCING_BPS_PER_YEAR are each literally 0.0, and
lazy_prices, pead, jump_drift, residual_momentum, asset_growth and
quality_neutral all pass the config default through unchanged. The
non-single-stock families are the exception and already charge something
sourced-or-declared: bonds 20, commodities 40, fx 25, eigenportfolio 50,
correlation_risk_premium 100.

The zero is documented in several pre-registrations as "this project's
standing DISCLOSED optimism about short borrow, NOT an estimate"
(short_interest_PREREGISTRATION §4). The disclosure is honest; the number is
still zero, and zero is not a conservative assumption, it is the least
conservative one available. It bites hardest exactly where it matters most —
short_interest's long_short specs short the MOST heavily shorted names in the
index, which is where borrow is expensive, and charge them nothing.

WHAT THIS MODULE IS NOT
=======================
It is NOT a securities-lending rate feed. A real per-name, per-day borrow
rate needs a paid source (S&P Global/IHS Markit Securities Finance, S3
Partners, EquiLend/DataLend), and none of them has a free tier that carries
historical rates. That gap is OPEN and is recorded as such in
data/research_runs/PENDING_PAID_DATA_DECISIONS.md. Nothing here should be
read as closing it.

What it IS: a two-rate schedule whose every number is a directly-verified
figure from a peer-reviewed paper, with the conservative (higher-cost) value
chosen wherever the sources disagree.

THE SOURCES, ALL FETCHED AND READ IN FULL 2026-09-05
====================================================
PAGE NUMBERS, AND WHAT THEY REFER TO. Every page number below was read off
the fetched PDF's own printed folio, not inferred. For (B1) that folio IS the
journal's (the copy is the JFE typeset article, running head "G. D'Avolio /
Journal of Financial Economics 66 (2002) 271-306"). For (B2) and (B3) the
copies are the authors' posted MANUSCRIPTS, so their page numbers are the
manuscript's own and will NOT match the published article's — cite them as
such rather than as journal pages. Two page numbers in an earlier draft of
this module were wrong by one to two pages and were corrected against the
folios before this shipped; the quoted TEXT is what identifies each claim.
(B1) D'Avolio, Gene, "The Market for Borrowing Stock", Journal of Financial
     Economics 66(2-3), 2002, pp. 271-306. Full text read from the author's
     posted copy. Sample: April 2000 - September 2001, one large financial
     institution's loan book.
       p.273, verbatim: "Ninety-one percent of the stocks lent out in the
       sample cost less than 1% per annum to borrow. These 'general
       collateral' stocks have a value-weighted mean fee of 17 basis points.
       S&P 500 constituents, provided in excess supply by indexing lenders,
       are almost always general collateral."
       p.273, verbatim: "Only 9% of stocks (about 206 stocks per day) have
       loan fees above 1% per annum. These 'specials' (stocks with high
       lending fees) have a mean fee of 4.3% per annum."
       Table 3, p.286: value-weighted mean FEE — All 0.24%/yr, GC 0.17%/yr
       (91.3% of stocks on loan), Special 4.30%/yr (8.7%), negative-rebate
       22.37%/yr (0.3%). Equal-weighted: 0.60 / 0.20 / 4.72 / 18.86.
       (The p.286 prose says the value-weighted specials mean is 4.69% while
       Table 3 on the same page says 4.30%. The table is used and the
       discrepancy is recorded rather than resolved by assertion.)

(B2) Engelberg, Reed & Ringgenberg, "Short-Selling Risk", Journal of Finance
     73(2), 2018, pp. 755-786. Full text read from a co-author's posted copy.
     Markit data, 4,500 US equities, July 2006 - December 2011.
       p.11, verbatim: "The median loan fee is only 11 basis points per
       annum; however, it is well known that loan fees exhibit considerable
       skewness, as indicated by the mean of 85 basis points and the 99th
       percentile of 1,479 basis points."
       p.19, verbatim, and the single most useful large-cap-specific figure
       found anywhere: "The 99th percentile of loan fees in the Micro sample
       is 1,119 bps; however, the 99th percentile of loan fees in the Large
       stock sample is only 236 bps. Similarly, the 90th percentile is 189
       bps for Micro stocks and only 20 bps for the Large stocks."
       "Large" is defined p.18 as market cap >= the 50th percentile of NYSE
       breakpoints.

(B3) Beneish, Lee & Nichols, "In Short Supply: Short-Sellers and Stock
     Returns", Journal of Accounting and Economics 60(1), 2015, pp. 33-57.
     Full text read from the authors' posted copy. Markit DXL, July 2004 -
     December 2013.
       p.15, verbatim: "Stocks with DCBS equal to 1 are clearly easy to
       borrow: their fees average less than 34 basis points per year. For
       DCBS equal to 2, the average (median) loan fee rises to 145 (122)
       basis points... The average loan fee for DCBS equal to 3 is over 270
       basis points, and quickly rises as DCBS increases: by the time DCBS
       equal to 7, the average loan fee exceeds 1000 basis points and for
       DCBS equal to 10, the average loan fee exceeds 4800 basis points."
       p.4: DCBS >= 3 is "Special"; 14.3% of firm-months are Special.

WHY THESE NUMBERS AND NOT OTHERS
================================
GC baseline = 34 bps/yr. Four independent, directly-verified estimates of the
easy-to-borrow band exist and they cluster tightly: D'Avolio 17 (VW) / 20
(EW), ERR 11 (median, all stocks) and 20 (90th percentile, LARGE stocks
specifically), BLN "less than 34" (DCBS=1). The rule this module follows
where sources disagree is TAKE THE HIGHEST, so 34 is used. It is the
conservative envelope over all four, and it is the only one of the four that
is quoted as a bound rather than a central tendency.

Hard-to-borrow = 430 bps/yr. D'Avolio Table 3's value-weighted mean fee for
specials, 4.30%/yr. Chosen over BLN's DCBS=3 ">270 bps" (lower) and set
against ERR's finding that even the 99th percentile of LARGE-stock fees is
only 236 bps — i.e. 430 is well above the 99th percentile of the large-cap
universe every equity family here actually trades. It is deliberately
conservative for that universe, not a best estimate of it.

STALENESS, STATED NOT BURIED. B1's sample is 2000-2001, B3's 2004-2013,
B2's 2006-2011. The most recent of them ends fifteen years before this code
runs. Securities lending has since been electronified and, on the industry
side, spreads have compressed; a 2026 GC rate is more likely BELOW 34bps than
above it. That direction is fine for a conservative charge and wrong for a
realistic one, and it is another reason the paid-feed gap stays open.

THE PROXY, AND ITS AUTHORS' OWN WARNING AGAINST IT
==================================================
We have FINRA short interest and no borrow rates, so short interest is the
only hard-to-borrow proxy available. Both primary sources say it is a POOR
one, and the disclosure is load-bearing rather than a hedge:

  D'Avolio p.285, on his Fig. 1 of mean fee by short-interest decile,
  verbatim: "While deciles 9 and 10 are the most expensive to borrow, the
  figure illustrates the potential difficulty with interpreting short
  interest in isolation and the limited use of this measure as a proxy for
  short-sale constraints."

  Beneish/Lee/Nichols p.5, verbatim: "consistent with D'Avolio (2002) we
  document a nonlinear (U-shaped) relation between SIR and a stock's
  'special' status — i.e., both extremely high SIR firms and extremely low
  SIR firms have a greater probability of being on special." And p.17:
  "even in the highest SIR decile, less than 30 percent of the stocks are
  special."

Two consequences are built into the schedule below rather than noted and
ignored:

  1. BOTH TAILS are charged the hard-to-borrow rate, not just the high one.
     The U-shape is the verified finding; charging only the high tail would
     encode the intuition instead of the evidence, and would undercharge the
     low-SIR names that BLN says are on special because LENDABLE SUPPLY is
     lowest there ("Lendable supply is also lowest among low SIR firms").
  2. The schedule OVERCHARGES by construction. BLN's "less than 30 percent"
     means charging a whole decile the specials rate prices roughly 70% of it
     too high. That is the intended direction: this replaces 0.0, and an
     approximation that errs cheap would be no better than the zero it
     replaces.

HOW IT IS WIRED (or rather, how it ISN'T yet)
=============================================
CrossSectionalConfig.financing_bps_per_year is a SCALAR on the config,
charged per unit of GROSS notional HELD per calendar year. Its own docstring
already gives the conversion: "For an equity family where only the SHORT leg
pays borrow at B bps/yr, pass B / 2 — half the book is short, so B/2 applied
to gross 2.0 is exactly B on the 1.0 short leg."
financing_bps_for_long_short_book() below is that arithmetic, once, so no
family has to rederive it.

NO FAMILY'S DEFAULT IS CHANGED BY THIS MODULE. financing_bps_per_year is part
of the config snapshot every live forward registration is fingerprinted on;
changing the default would park all four live registrations in "spec_drift"
on the next tick. Adoption is per-family and is the repo owner's call.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# --- the cited rates ---------------------------------------------------------

# Beneish/Lee/Nichols (2015) p.15, DCBS=1: "their fees average less than 34
# basis points per year". The conservative envelope over D'Avolio's 17 (VW)
# and 20 (EW), and ERR's 11 (median) and 20 (LARGE-stock 90th percentile).
GENERAL_COLLATERAL_BPS_PER_YEAR = 34.0

# D'Avolio (2002) Table 3, value-weighted mean fee for "specials"
# (FEE > 1%/yr): 4.30% per annum. Above BLN's DCBS=3 ">270 bps" and well
# above ERR's LARGE-stock 99th percentile of 236 bps.
HARD_TO_BORROW_BPS_PER_YEAR = 430.0

# Deciles 9 and 10 in D'Avolio's Fig. 1 are "the most expensive to borrow";
# BLN document the same pattern and add that the LOWEST SIR deciles carry a
# relatively high proportion of specials too (a U-shape driven by lendable
# supply, not demand). Both tails are therefore priced as hard to borrow.
# 0.10 = ONE decile per tail, so the top and bottom deciles together (20% of
# the cross-section) pay the specials rate and the middle 80% pays GC. The
# decile is D'Avolio's own unit of analysis in Fig. 1, not a chosen
# granularity.
HARD_TO_BORROW_TAIL_FRACTION = 0.10

CITATIONS = (
    "D'Avolio, 'The Market for Borrowing Stock', JFE 66(2-3), 2002, pp. 271-306, "
    "Table 3 p.286 (GC value-weighted mean 0.17%/yr; specials 4.30%/yr) and p.273 "
    "('S&P 500 constituents ... are almost always general collateral')",
    "Engelberg, Reed & Ringgenberg, 'Short-Selling Risk', Journal of Finance 73(2), "
    "2018, pp. 755-786, p.11 (median 11bp, mean 85bp) and p.19 (LARGE-stock 90th "
    "percentile 20bp, 99th percentile 236bp)",
    "Beneish, Lee & Nichols, 'In Short Supply', JAE 60(1), 2015, pp. 33-57, p.15 "
    "(DCBS=1 fees average <34bp/yr) and p.5 (U-shaped SIR/specialness relation)",
)

# The one number in this module that is NOT sourced, named so it cannot be
# mistaken for one that is. A real per-name borrow rate needs a paid feed;
# see the module docstring and data/research_runs/PENDING_PAID_DATA_DECISIONS.md.
UNSOURCED_ASSUMPTIONS = (
    "That the 2000-2013 sample periods of B1/B2/B3 still bound 2015-2026 borrow "
    "rates. Untested; the likely direction (electronification, spread compression) "
    "makes the GC rate an OVERstatement, which is the safe direction for a cost.",
)


@dataclass(frozen=True)
class BorrowSchedule:
    """A two-rate schedule plus the tail rule that assigns names to them."""

    general_collateral_bps: float = GENERAL_COLLATERAL_BPS_PER_YEAR
    hard_to_borrow_bps: float = HARD_TO_BORROW_BPS_PER_YEAR
    tail_fraction: float = HARD_TO_BORROW_TAIL_FRACTION

    def __post_init__(self) -> None:
        if self.general_collateral_bps < 0 or self.hard_to_borrow_bps < 0:
            raise ValueError("borrow rates must be non-negative")
        if self.hard_to_borrow_bps < self.general_collateral_bps:
            raise ValueError(
                f"hard_to_borrow_bps ({self.hard_to_borrow_bps}) is below "
                f"general_collateral_bps ({self.general_collateral_bps}) — the schedule's "
                "whole point is that the tails cost MORE."
            )
        if not 0.0 <= self.tail_fraction < 0.5:
            raise ValueError(
                f"tail_fraction must be in [0, 0.5), got {self.tail_fraction} — each tail is "
                "one side of a cross-section and two of them cannot exceed the whole."
            )

    def rate_for_percentiles(self, percentiles: pd.Series) -> pd.Series:
        """Annualized borrow rate in bps for each name, given its
        cross-sectional short-interest PERCENTILE in [0, 1] (1 = most
        heavily shorted).

        Both tails get the hard-to-borrow rate — see the module docstring's
        U-shape discussion; this is the evidence, not the intuition.

        A NaN percentile (no short-interest observation for that name on
        that date) gets the GENERAL COLLATERAL rate, not the hard-to-borrow
        one. That is the one place this module is deliberately NOT maximally
        conservative, and the justification is specific rather than general:
        D'Avolio p.273 states that "S&P 500 constituents, provided in excess
        supply by indexing lenders, are almost always general collateral",
        and every equity universe in this project is S&P 500 / S&P 600
        large- and mid-cap. On a micro-cap or international universe that
        sentence does not apply and this default would be wrong — pass an
        explicit schedule, or do not use this module."""
        if percentiles.empty:
            return pd.Series(dtype=float)
        values = percentiles.to_numpy(dtype=float)
        finite = values[~np.isnan(values)]
        if finite.size and (finite.min() < 0.0 or finite.max() > 1.0):
            raise ValueError(
                f"percentiles must lie in [0, 1]; got [{finite.min()}, {finite.max()}]"
            )
        lo = self.tail_fraction
        hi = 1.0 - self.tail_fraction
        is_tail = (values <= lo) | (values >= hi)
        rates = np.where(is_tail, self.hard_to_borrow_bps, self.general_collateral_bps)
        rates = np.where(np.isnan(values), self.general_collateral_bps, rates)
        return pd.Series(rates, index=percentiles.index, dtype=float)

    def book_borrow_bps_per_year(self, short_leg_percentiles: pd.Series) -> float:
        """The equal-weighted average borrow rate, in bps/yr, of a SHORT LEG
        whose members have the given short-interest percentiles. This is the
        `B` in financing_bps_for_long_short_book(B).

        Equal-weighted because every cross-sectional family here builds
        equal-weighted legs by default (see cross_sectional.py); a
        value-weighted book would need its own weights and should compute
        the average itself rather than call this."""
        if short_leg_percentiles.empty:
            raise ValueError("an empty short leg has no borrow rate; do not call this with one")
        return float(self.rate_for_percentiles(short_leg_percentiles).mean())

    def worst_case_bps_per_year(self) -> float:
        """Every short-leg name hard to borrow. The bound to quote when a
        family cannot compute percentiles at all — an explicit worst case is
        an honest answer where 0.0 is not."""
        return self.hard_to_borrow_bps


DEFAULT_SCHEDULE = BorrowSchedule()


def financing_bps_for_long_short_book(short_leg_borrow_bps_per_year: float) -> float:
    """CrossSectionalConfig.financing_bps_per_year for a fully-formed
    long_short book whose SHORT leg alone pays borrow at the given rate.

    The config field charges per unit of GROSS notional held, and a formed
    long_short book carries gross 2.0 (1.0 long + 1.0 short), so half the
    stated rate applied to gross 2.0 is exactly the stated rate on the 1.0
    short leg. This is cross_sectional.py's own documented conversion, moved
    here so no family rederives it.

    NOT valid for a long_universe_hedged book, whose short leg is a broad
    index-like basket rather than a ranked leg — that leg is genuinely
    cheap (D'Avolio: index constituents are almost always general
    collateral) and should be charged the GC rate directly."""
    if short_leg_borrow_bps_per_year < 0:
        raise ValueError("a borrow rate cannot be negative")
    return short_leg_borrow_bps_per_year / 2.0


def cross_sectional_percentiles(values: pd.Series) -> pd.Series:
    """Rank a formation's short-interest values into [0, 1] percentiles.

    Ties get the average rank (pandas' default), and NaNs stay NaN so
    rate_for_percentiles can apply its documented GC default to them rather
    than silently ranking a missing observation as median."""
    finite = values.dropna()
    if finite.empty:
        return pd.Series(np.nan, index=values.index, dtype=float)
    if len(finite) == 1:
        # A one-name cross-section has no tails to speak of; calling it
        # median is the only non-arbitrary answer.
        ranked = pd.Series(0.5, index=finite.index, dtype=float)
    else:
        ranked = finite.rank(method="average", pct=True)
    return ranked.reindex(values.index)
