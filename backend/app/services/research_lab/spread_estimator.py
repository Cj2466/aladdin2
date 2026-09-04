from dataclasses import dataclass

import pandas as pd
from bidask import edge_rolling

# Ardia, Guidotti & Kroencke, "Efficient Estimation of Bid-Ask Spreads from
# Open, High, Low, and Close Prices," Journal of Financial Economics 2024
# (doi.org/10.1016/j.jfineco.2024.103916). A GMM-style estimator of the
# effective bid-ask spread from daily OHLC alone -- no tick/quote data
# needed. Uses the `bidask` package (MIT license, github.com/eguidotti/
# bidask) directly rather than re-implementing the formula: it's the
# paper's own maintained reference implementation, not a third-party
# guess at their method.
#
# SUPERSEDES an earlier hand-rolled Corwin & Schultz (2012) implementation,
# built first and then discarded after direct validation exposed it as the
# wrong tool for this project's universe: on synthetic OHLC with a KNOWN
# injected spread, Corwin-Schultz recovered a true 10bps spread as -12.8bps
# and a true 50bps spread as 20.5bps -- a large, sign-flipping downward
# bias at exactly the LOW-spread regime this project's S&P 500/600 universe
# lives in. This estimator, tested identically on the same synthetic data,
# recovered 10bps as 4.7bps and 50bps as 48.0bps -- close to exact at every
# true-spread level tested (10/50/100/300/500bps). The CS bias is
# well-documented in the literature (it's why Abdi-Ranaldo 2017 and then
# this estimator were developed as successors); it wasn't a bug in that
# implementation, the formula itself is known-weak exactly where this
# project needs it strong.
#
# Built in response to this project's own repeated finding (Phase A/B
# intraday pattern mining, 420/420 patterns tried, zero with positive
# pooled Sharpe after cost): every backtest in this codebase currently
# assumes a FLAT cost in basis points, identical across every ticker and
# every day. This gives a per-ticker, per-day-varying cost proxy instead.
#
# WIRED (2026-08-28) into the cross-sectional harness as an OPT-IN
# alternative cost model, never a silent replacement: CrossSectionalConfig.
# cost_model="edge_spread" charges each formation's per-ticker traded
# notional at that ticker's own trailing EDGE half-spread (via
# build_edge_half_spread_frame below, carried on CrossSectionalData.
# half_spread), falling back to the flat config.cost_bps for any
# ticker/date with no usable estimate. The default cost_model="flat_bps"
# is byte-for-byte the old behavior — exactly the additive-alternative
# discipline the dual price basis followed (see cross_sectional.py).

DEFAULT_WINDOW_DAYS = 21  # ~1 trading month

# KNOWN LIMITATION -- SEVERITY UPDATED 2026-08-30 after a dedicated
# investigation into a large-cap cost-inflation report from two same-night
# strategy builds (eigenportfolio-statarb, jump-drift). The 2026-08-28 note
# below (~2x bias at 10bps, synthetic-only) badly understated this in the
# real-data regime this project actually screens (mega/large-cap S&P names,
# true half-spreads on the order of ~0.3-1.5bps). Independently reproduced
# at production settings (window=63): PG/JNJ/KO/VZ median HALF-spread
# 11.8/14.1/13.5/15.8bps against tick-floor true half-spreads of roughly
# 0.3-1.5bps -- a ~10-40x overstatement, not ~2x. SPY itself (true full
# spread ~0.26bps, live-verified) gets a rolling-63 median FULL-spread
# estimate of ~24bps. This is NOT an implementation bug -- verified
# line-by-line against the paper's own reference `bidask` package and its
# Eq. (11)-(13); units, the half-spread division by 2, and auto_adjust
# handling are all correct. It is the source paper's OWN disclosed
# limitation for this exact regime (Ardia/Guidotti/Kroencke, pp. 24-26 of
# the working paper, SSRN 3892335): "the spreads for mid and large caps
# have become too small to be reliably estimated from a monthly sample of
# daily data" (post-2005), with intraday price data named as the paper's
# own recommended remedy over more daily-bar history or a wider window --
# widening the window here trades away liquidity-regime responsiveness
# without closing this gap, since the dominant failure mode is a real-data
# violation of the estimator's model (documented positive-skewed overnight
# gap dynamics reading as a spurious positive transitory component), not
# just short-sample GMM noise. A secondary, smaller amplifier: this module
# calls `edge_rolling` with the package default `sign=False`, which FOLDS
# negative squared-spread estimates to positive via abs() rather than the
# paper's own canonical truncation-to-zero (Eq. 14); recomputing with
# truncation reduces but does not close the gap (e.g. JNJ 14.1 -> 5.3bps).
#
# PRACTICAL CONSEQUENCE: do not read this module's output as an accurate
# cost LEVEL for a single liquid large-cap ticker, at any window length.
# It remains far more trustworthy (a) for ranking tickers by relative
# cost, and (b) as a level estimate for wider-spread/less-liquid names
# above roughly 30-50bps true spread, where the earlier 2026-08-28 note's
# few-percent recovery numbers do hold. Any existing run persisted under
# cost_model="edge_spread" that concluded a strategy was uneconomic on a
# mega/large-cap-heavy universe should be read as a PESSIMISTIC bound, not
# a realistic cost estimate -- since cost only ever pushes net Sharpe
# down, no prior "positive edge" conclusion is invalidated by this, but a
# prior "uneconomic under edge_spread costs" conclusion on such a universe
# is not sound as stated and may be worth re-examining under a more
# realistic cost assumption (e.g. a lower calibrated flat rate, or EDGE
# used as a ranker scaling a calibrated base rate, or an intraday-based
# estimate) before being treated as a closed negative.
#
# THE REMEDY IS NOW IMPLEMENTED, 2026-09-05: the second of those three
# options -- EDGE as a ranker scaling an externally calibrated base rate --
# is build_calibrated_half_spread_frame() below. It is ADDITIVE. Everything
# above this line still describes build_edge_half_spread_frame(), which is
# unchanged to the byte so every persisted run under cost_model=
# "edge_spread" stays exactly reproducible; read that builder's output as a
# PESSIMISTIC BOUND and the calibrated builder's as the realistic estimate.
# No family's default was switched by that commit: swapping the frame a live
# forward registration trades on changes its accumulating track record
# without changing its config fingerprint, which is precisely the silent
# drift live_registration_dependencies.json exists to make visible, and is
# the repo owner's call to make rather than a side effect of a cost fix.


def estimate_effective_spread(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> pd.Series | None:
    """Rolling effective-spread estimate, as a fraction of price (0.01 =
    1%, i.e. ~100bps). All four series must share one ascending
    DatetimeIndex. Returns None if there isn't enough history for even one
    full window -- edge_rolling would otherwise return an all-NaN Series,
    which is a worse signal to callers than an explicit None (same
    convention as classify_regime's insufficient-history skip)."""
    if not (
        open_.index.equals(high.index)
        and open_.index.equals(low.index)
        and open_.index.equals(close.index)
    ):
        raise ValueError("open, high, low, close must share the same index")
    if len(open_) < window_days:
        return None

    frame = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})
    return edge_rolling(frame, window=window_days)


# The rolling window used when the estimate feeds a COST MODEL (the
# cross-sectional harness's cost_model="edge_spread", and the intraday
# re-audit's per-ticker cost derivation) rather than a point-in-time
# liquidity *ranking*. One quarter, not DEFAULT_WINDOW_DAYS=21, because of
# the KNOWN LIMITATION documented above: at 21 days a true 10bps spread
# recovers as ~21bps — a ~2x UPWARD bias exactly in the tight-spread
# large-cap regime this project's S&P universe lives in — and that bias is
# short-sample GMM noise, which widening the window directly reduces. A
# cost model biased 2x high at the tight end would rebuild, in miniature,
# the very flat-cost pessimism this option exists to correct. 63 trading
# days mirrors the "one quarter" judgment call this codebase already uses
# for a smoothing horizon (cross_sectional_patterns.TURNOVER_
# NORMALIZATION_WINDOW), trading some responsiveness to genuine liquidity
# regime shifts for materially less small-sample bias; disclosed judgment
# call, not an independently calibrated constant. Pinned by the synthetic
# recovery test in tests/test_edge_cost_model.py at THIS window, not just
# the module default.
COST_MODEL_WINDOW_DAYS = 63


def build_edge_half_spread_frame(
    open_: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    window_days: int = COST_MODEL_WINDOW_DAYS,
) -> pd.DataFrame:
    """Wide (dates x tickers) frame of one-way HALF-spreads as a fraction
    of price (0.0005 = 5bps per unit of notional traded, one-way) — the
    per-ticker, per-day cost basis CrossSectionalData.half_spread carries
    for cost_model="edge_spread". Each column is that ticker's rolling
    EDGE full-spread estimate divided by 2: crossing from mid to bid or
    ask costs half the effective spread, which makes each cell directly
    comparable to the flat one-way config.cost_bps / 10_000 it replaces.

    All four input frames must share one index and one column set (the
    exact alignment YFinanceProvider.get_daily_ohlcv guarantees). The
    output is aligned to close likewise, so validate_cross_sectional_data
    accepts it unchanged.

    TRAILING BY CONSTRUCTION — the property that lets the harness read row
    i at formation i without look-ahead: edge_rolling is a pandas-style
    rolling window ENDING at each row, so the estimate on a formation date
    uses only that date's own and earlier OHLC rows (pinned by the
    truncation-invariance test in tests/test_edge_cost_model.py). The
    adjustment basis does not matter here: auto_adjust scales O/H/L/C by
    the same per-day factor, and the estimator reads only intraday log
    RATIOS, which that scaling leaves untouched.

    A cell is NaN wherever no usable estimate exists — not enough valid
    rows in the window yet, missing OHLC, or a degenerate/non-positive
    estimate (edge_rolling's unsigned output can be exactly 0.0 when its
    squared-spread estimate lands at zero; a zero trading cost is not a
    plausible real-world number, so it is treated as "no estimate" rather
    than "free"). NaN is deliberate: the consuming cost model falls back
    to the flat config.cost_bps for exactly those ticker/dates and COUNTS
    the fallback (FormationRecord.edge_flat_fallback_notional), instead of
    crashing or silently charging zero."""
    for name, frame in (("high", high), ("low", low), ("close", close)):
        if not frame.index.equals(open_.index) or not frame.columns.equals(open_.columns):
            raise ValueError(
                f"build_edge_half_spread_frame: {name} is not aligned with open "
                "(index/columns must match exactly — see get_daily_ohlcv, which guarantees this)."
            )
    half_by_ticker: dict[str, pd.Series] = {}
    for ticker in close.columns:
        ohlc = pd.DataFrame(
            {"open": open_[ticker], "high": high[ticker], "low": low[ticker], "close": close[ticker]}
        )
        half_by_ticker[ticker] = edge_rolling(ohlc, window=window_days) / 2.0
    result = pd.DataFrame(half_by_ticker, index=close.index).loc[:, close.columns]
    return result.where(result > 0.0)


# ===========================================================================
# THE CORRECTED COST BASIS (2026-09-05)
# ===========================================================================
# build_edge_half_spread_frame above is wrong as a cost LEVEL for liquid
# large caps by roughly 10-40x, for two separable reasons. This section
# fixes both, and neither fix is a formula written from memory: the first is
# the source paper's own documented option, the second is a re-use of this
# project's own already-pre-registered, already-independently-verified
# calibration (commit dd34094).
#
# DEFECT 1 -- THE abs() FOLD, an implementation deviation from the source.
# `bidask.edge_rolling`'s default is sign=False, which returns
# sqrt(|s^2|): a negative squared-spread estimate is FOLDED to a positive
# spread instead of being truncated. The package's own documentation
# (bidask.eguidotti.com, FAQ, retrieved 2026-09-05) states the trade-off
# directly: the absolute-value default is "generally a good option if you
# are interested in point estimates" but "may create a small-sample bias if
# the estimates are used for averaging or regression studies", whereas
# computing "signed estimates with the argument sign=True and reset negative
# values to zero" is what "reduce[s] this source of bias". It also warns
# that "keeping negative values is not recommended because more negative
# estimates are typically associated with larger spreads empirically" --
# hence truncation to zero, never retention of the negative value.
#
# A COST MODEL IS THE AVERAGING CASE, not the point-estimate case: every
# formation charges a rolling estimate for every traded ticker, and the
# realized charge is an average over thousands of such cells. So sign=True
# with truncation is the applicable choice here, and CALIBRATED_SIGN_MODE
# pins it. The 2026-08-30 investigation already measured the direction on
# real data (JNJ 14.1 -> 5.3bps); the synthetic tests in
# tests/test_calibrated_spread_cost.py measure it against a KNOWN true
# spread instead of against another estimate.
#
# DEFECT 2 -- THE LEVEL, which is the source paper's own disclosed
# limitation and cannot be fixed inside the estimator at all (Ardia/
# Guidotti/Kroencke, working paper pp. 24-26: post-2005 mid and large cap
# spreads "have become too small to be reliably estimated from a monthly
# sample of daily data"). What CAN be trusted is the RANKING. So the level
# is not estimated here: it is pinned by ONE pooled scalar to an externally
# published calibration, exactly the RC-edge-ranked scenario frozen in
# data/research_runs/edge_cost_reaudit_corrected_PREREGISTRATION.txt §3 and
# implemented in edge_cost_reaudit_scenarios.scale_half_spread_frame_to_
# median. One scalar for the whole frame, no clipping, no per-ticker
# fitting -- mechanically untunable.
#
# DEFECT 3, which was never a defect but is closed here anyway -- THE FLOOR.
# A US equity's quoted spread cannot be below one $0.01 tick, so the one-way
# half-spread cannot be below 0.005 / price. That is exact arithmetic, not
# an estimate (pre-registration §2 source S4, and
# edge_cost_reaudit_scenarios.tick_floor_half_spread_bps). Applying it per
# cell means a truncated-to-zero estimate becomes the tick floor rather than
# a NaN that falls back to the flat rate, which is both more accurate and
# strictly cheaper to reason about.

# sign=True, then truncate negatives to zero. See DEFECT 1.
CALIBRATED_SIGN_MODE = True

# One-way half-spread, as a fraction of price, that the pooled median
# charged cell is pinned to. 2.0bp = 0.0002.
#
# SOURCED, NOT CHOSEN. From edge_cost_reaudit_corrected_PREREGISTRATION.txt
# §2, whose two primary sources were fetched and read in full at the time
# and whose calibration was independently verified in dd34094:
#   (S1) Hagstromer, "Bias in the effective bid-ask spread", JFE 2021,
#        Table 1 (all S&P 500 constituents, Dec 7-11 2015, dollar-volume-
#        weighted FULL spreads in bps): micro-price effective mean 2.73,
#        median 2.53, p75 3.78, p95 6.99. => one-way half-spreads: median
#        stock ~1.3bp, p75 ~1.9bp, p95 ~3.5bp, in a low-volatility year.
#   (S2) Mackintosh (Nasdaq Chief Economist), "Sampling the S&P 500 to
#        Minimize Spreads", 2024-05-30: cap-weighted average QUOTED spreads
#        MSFT/AAPL ~1bp, 100-largest ~3.7bp, whole S&P 500 "just over
#        4.5 bps" => one-way ~0.5bp to ~2.3bp.
#   (S3) Mackintosh, "Have Spreads Changed Over Time?", 2021-10-14:
#        post-2018/2020 regimes run wider than 2015, order +50%
#        volatility-adjusted.
# An EQUAL-weighted S&P 500 cross-section (which is what a decile/quintile
# leg is) sits between S1's median and p75 -- ~3bp full, ~1.5bp one-way in
# 2015's tight regime -- and a 2015-2026 window that includes wider regimes
# and departed, less liquid members lands at ~2bp one-way.
#
# THIS NUMBER IS A UNIVERSE PROPERTY, NOT A CONSTANT OF NATURE. It is right
# for a US large-cap (S&P 500-like) cross-section. Pass an explicit
# target_median_half_spread for anything else; there is deliberately no
# lookup table, because a silently-wrong universe default is worse than an
# argument a caller has to think about.
SP500_TARGET_MEDIAN_HALF_SPREAD = 0.0002

# One-way half-spread floor implied by the US $0.01 minimum tick: full
# spread >= $0.01 => half-spread fraction >= 0.005 / price. Exact for
# price > 0. Duplicated from edge_cost_reaudit_scenarios' bps form
# (50 / price_in_dollars bps) in FRACTION units, which is the unit
# CrossSectionalData.half_spread actually carries.
MIN_TICK_DOLLARS = 0.01


@dataclass(frozen=True)
class CalibrationReport:
    """Everything needed to re-derive a calibrated frame without re-running
    it -- the same reason preservation_score returns its inputs alongside
    its score. A calibrated cost basis with no record of WHICH scalar was
    applied, to how many cells, is not auditable."""

    window_days: int
    target_median_half_spread: float
    observed_median_half_spread: float
    scale: float
    n_cells_total: int
    n_cells_estimated: int  # a finite, strictly positive EDGE estimate
    n_cells_truncated_to_zero: int  # negative s^2, truncated per Eq. (14)
    n_cells_no_estimate: int  # NaN: not enough window, or missing OHLC
    n_cells_raised_to_tick_floor: int
    realized_median_half_spread: float

    def summary(self) -> str:
        return (
            f"calibrated EDGE half-spread frame: window={self.window_days}d, "
            f"pooled median {self.observed_median_half_spread * 10_000:.2f}bp scaled by "
            f"{self.scale:.4f} to target {self.target_median_half_spread * 10_000:.2f}bp "
            f"(realized {self.realized_median_half_spread * 10_000:.2f}bp after the tick floor); "
            f"{self.n_cells_estimated}/{self.n_cells_total} cells estimated, "
            f"{self.n_cells_truncated_to_zero} truncated to zero, "
            f"{self.n_cells_no_estimate} with no estimate, "
            f"{self.n_cells_raised_to_tick_floor} raised to the tick floor"
        )


def build_calibrated_half_spread_frame(
    open_: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    *,
    window_days: int = COST_MODEL_WINDOW_DAYS,
    target_median_half_spread: float = SP500_TARGET_MEDIAN_HALF_SPREAD,
    calibration_start: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, CalibrationReport]:
    """The corrected per-ticker, per-day one-way HALF-spread frame for
    cost_model="edge_spread" -- same units, same shape, same alignment
    contract, and the same trailing/no-look-ahead property as
    build_edge_half_spread_frame, so it is a drop-in replacement for that
    function's output wherever a caller decides to use it.

    Four steps, in this order, each justified in the section header above:

      1. EDGE at `window_days` with sign=True, then NEGATIVE ESTIMATES
         TRUNCATED TO ZERO (the source package's own recommended treatment
         for averaging use, not the abs() fold its default performs).
      2. Halved -- crossing from mid to bid or ask costs half the effective
         spread, identical to build_edge_half_spread_frame.
      3. Scaled by ONE pooled scalar so the pooled median of the cells that
         carry a positive estimate equals `target_median_half_spread`. EDGE
         keeps only its relative structure; the LEVEL comes from published
         spread statistics (see SP500_TARGET_MEDIAN_HALF_SPREAD).
      4. Floored per cell at that ticker's own tick floor,
         0.005 / close_price. Exact arithmetic.

    THREE KINDS OF CELL, AND THE DIFFERENT ANSWER EACH GETS. The distinction
    is load-bearing and was found on real data, not reasoned out in advance:
    on the S&P 500 2015-2026 panel, 40% of cells truncate to zero, so how
    they are priced moves the realized median by roughly a factor of two.

      * A POSITIVE ESTIMATE. Scaled. This is the informative case.
      * TRUNCATED TO ZERO -- the estimator RAN and returned a squared spread
        at or below zero. That is a statement about the estimator's
        precision at this window length, not a claim that the stock is free
        to trade: no US equity's spread is zero. So the cell is charged the
        CALIBRATED TARGET, i.e. the universe's own published central level,
        which is exactly the rule the rest of this function follows whenever
        EDGE has no usable relative information. Charging the tick floor
        instead (~0.3bp for a $150 stock) would price 40% of the book at
        almost nothing on the strength of a small-sample artifact.
      * NO ESTIMATE AT ALL -- NaN, because the window has not filled or the
        OHLC row is missing. Left NaN, so the harness falls back to the flat
        config.cost_bps for that ticker/date AND COUNTS IT
        (FormationRecord.edge_flat_fallback_notional). That accounting is
        the thing that stops a spread-priced run degenerating quietly into a
        flat-priced one, and filling these cells here would destroy it.

    WHY THE CALIBRATION MEDIAN IS TAKEN OVER POSITIVE CELLS ONLY. Including
    the truncated zeros would drag the pooled median down and so scale every
    other cell UP -- charging more, but for the wrong reason. All three
    counts are reported rather than hidden.

    `calibration_start` restricts the pooled median to rows on or after it,
    matching scale_half_spread_frame_to_median's formation_start argument:
    the warmup NaN band and any pre-formation padding never charge a cost
    and should not set the level either. Defaults to the whole frame.

    Returns (frame, report). The report is not optional decoration -- a
    calibrated cost basis whose scalar is not recorded cannot be audited.
    """
    for name, frame in (("high", high), ("low", low), ("close", close)):
        if not frame.index.equals(open_.index) or not frame.columns.equals(open_.columns):
            raise ValueError(
                f"build_calibrated_half_spread_frame: {name} is not aligned with open "
                "(index/columns must match exactly — see get_daily_ohlcv, which guarantees this)."
            )
    if not target_median_half_spread > 0:
        raise ValueError(
            f"target_median_half_spread must be positive, got {target_median_half_spread!r}"
        )

    signed_half: dict[str, pd.Series] = {}
    for ticker in close.columns:
        ohlc = pd.DataFrame(
            {"open": open_[ticker], "high": high[ticker], "low": low[ticker], "close": close[ticker]}
        )
        signed = edge_rolling(ohlc, window=window_days, sign=CALIBRATED_SIGN_MODE)
        signed_half[ticker] = signed / 2.0
    raw = pd.DataFrame(signed_half, index=close.index).loc[:, close.columns]

    n_cells_total = int(raw.size)
    n_cells_no_estimate = int(raw.isna().to_numpy().sum())
    # Step 1's truncation. `<= 0` and not `< 0`: an exactly-zero estimate is
    # the same statement ("no measurable spread") and gets the same
    # treatment, so the two cannot be told apart downstream anyway.
    truncated_mask = raw.le(0.0) & raw.notna()
    n_cells_truncated_to_zero = int(truncated_mask.to_numpy().sum())
    positive = raw.where(raw > 0.0)
    n_cells_estimated = n_cells_total - n_cells_no_estimate - n_cells_truncated_to_zero

    calibration_region = positive
    if calibration_start is not None:
        calibration_region = positive.loc[positive.index >= pd.Timestamp(calibration_start)]
    pooled = pd.Series(calibration_region.to_numpy().ravel()).dropna()
    if pooled.empty:
        raise ValueError(
            "build_calibrated_half_spread_frame: no positive EDGE half-spread cell in the "
            "calibration region — there is nothing to pin the level to. Widen the window, "
            "supply more history, or pass an explicit calibration_start."
        )
    observed_median = float(pooled.median())
    if not observed_median > 0:
        raise ValueError(
            f"pooled median half-spread is non-positive ({observed_median!r}) despite being "
            "taken over strictly positive cells — refusing to scale garbage."
        )
    scale = target_median_half_spread / observed_median

    # Positive cells scale; truncated cells take the calibrated target; NaN
    # stays NaN so the harness's counted flat fallback still fires. See the
    # docstring's "THREE KINDS OF CELL".
    scaled = (positive * scale).where(~truncated_mask, other=target_median_half_spread)

    # Step 4. A non-positive or missing close cannot produce a floor, so it
    # leaves that cell to the scaled value (or NaN); it never silently
    # becomes free.
    floor = (MIN_TICK_DOLLARS / 2.0) / close.where(close > 0.0)
    raise_mask = scaled.notna() & floor.notna() & (floor > scaled)
    floored = scaled.where(~raise_mask, floor)
    n_cells_raised_to_tick_floor = int(raise_mask.to_numpy().sum())

    realized = pd.Series(floored.to_numpy().ravel()).dropna()
    report = CalibrationReport(
        window_days=window_days,
        target_median_half_spread=target_median_half_spread,
        observed_median_half_spread=observed_median,
        scale=scale,
        n_cells_total=n_cells_total,
        n_cells_estimated=n_cells_estimated,
        n_cells_truncated_to_zero=n_cells_truncated_to_zero,
        n_cells_no_estimate=n_cells_no_estimate,
        n_cells_raised_to_tick_floor=n_cells_raised_to_tick_floor,
        realized_median_half_spread=float(realized.median()) if not realized.empty else float("nan"),
    )
    return floored, report
