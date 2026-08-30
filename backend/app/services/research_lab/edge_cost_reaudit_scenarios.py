"""Cost-scenario construction for the 2026-08-30 corrected-cost re-audit of
the two edge_spread hard-exclusions (round_c, phase_a_intraday_expanded).

Every number and rule here implements — and only implements — the frozen
design in data/research_runs/edge_cost_reaudit_corrected_PREREGISTRATION.txt
(sha256 a17e993f647629236939d2af9886b9010f7d4a9a84609f3ea2bed843ae13c80b,
written before any scenario was run). Nothing in this module decides what to
run; it only builds the cost inputs the two existing screening mechanisms
already accept (CrossSectionalData.half_spread + CrossSectionalConfig.cost_bps
for round_c, screen_pattern_universe's cost_bps_by_ticker for phase_a), so
the re-audit reuses the harnesses byte-for-byte rather than growing a third
cost path.

Two pieces:

 * scale_half_spread_frame_to_median — the RC-edge-ranked scenario: the EDGE
   half-spread frame's LEVEL is untrustworthy for liquid large caps (the
   ~10-40x overstatement documented in spread_estimator.py's KNOWN
   LIMITATION block) but its RANKING is the part the same block says remains
   trustworthy. So the frame is multiplied by ONE scalar chosen so the
   pooled median charged cell equals an externally calibrated realistic
   half-spread (2.0bp one-way in the pre-registration, from Hagstromer JFE
   2021 Table 1 + Nasdaq 2024). No clipping, no per-ticker fitting — one
   mechanical scalar, so the scenario cannot be tuned spec by spec.

 * tiered_cost_bps_by_ticker — phase_a's per-ticker one-way costs: a flat
   rate per liquidity tier (the module's own pre-existing large-cap vs
   mid/small-cap split, not a new judgment), floored per ticker at its own
   tick floor (a $0.01 minimum tick means one-way half-spread >= 0.005 /
   price, i.e. 50 / price_in_dollars bps — exact arithmetic, not an
   estimate).
"""

from datetime import date

import pandas as pd

# One-way half-spread floor implied by the $0.01 minimum tick: full spread
# >= $0.01, so half-spread fraction >= 0.005 / price, which in bps is
# 10_000 * 0.005 / price = 50 / price. Exact for price > 0; sub-$1 names
# (which can tick finer than a cent) do not occur in either re-audited
# universe.
_TICK_FLOOR_BPS_NUMERATOR = 50.0


def tick_floor_half_spread_bps(price_dollars: float) -> float:
    """One-way half-spread lower bound in bps for a stock trading at
    `price_dollars` under the US $0.01 minimum tick. Raises on a
    non-positive price rather than returning a nonsense floor."""
    if not price_dollars > 0:
        raise ValueError(
            f"tick_floor_half_spread_bps needs a positive price, got {price_dollars!r}"
        )
    return _TICK_FLOOR_BPS_NUMERATOR / price_dollars


def tiered_cost_bps_by_ticker(
    tickers: list[str],
    large_cap_tier: list[str],
    mid_small_tier: list[str],
    large_cap_rate_bps: float,
    mid_small_rate_bps: float,
    median_close_by_ticker: dict[str, float],
) -> dict[str, float]:
    """Per-ticker one-way cost in bps: the ticker's tier rate, floored at
    its own tick floor (see tick_floor_half_spread_bps). Loud on any ticker
    in neither tier or missing a median close — a silent default here would
    let a symbology mismatch quietly re-price part of the universe, the
    exact failure mode screen_pattern_universe's own cost_bps_by_ticker
    contract polices."""
    large = set(large_cap_tier)
    mid_small = set(mid_small_tier)
    overlap = large & mid_small
    if overlap:
        raise ValueError(f"tiers overlap: {sorted(overlap)}")

    costs: dict[str, float] = {}
    for ticker in tickers:
        if ticker in large:
            rate = large_cap_rate_bps
        elif ticker in mid_small:
            rate = mid_small_rate_bps
        else:
            raise ValueError(
                f"ticker {ticker!r} is in neither tier — tier lists must cover the "
                "whole universe explicitly (see pre-registration section 3)."
            )
        median_close = median_close_by_ticker.get(ticker)
        if median_close is None or not median_close > 0:
            raise ValueError(
                f"ticker {ticker!r} has no usable median close ({median_close!r}) for "
                "its tick floor — supply a real price, not a silent unfloored rate."
            )
        costs[ticker] = max(rate, tick_floor_half_spread_bps(median_close))
    return costs


def scale_half_spread_frame_to_median(
    half_spread: pd.DataFrame,
    target_median_half_spread: float,
    formation_start: date,
) -> tuple[pd.DataFrame, float, float]:
    """Returns (scaled_frame, scale, observed_median) where
    scale = target_median_half_spread / observed_median and observed_median
    is the pooled median over ALL non-NaN cells of `half_spread` on dates
    >= formation_start (the region where formations can actually charge a
    cost — the warmup NaN band and pre-formation padding never do).

    Both target and the frame are unit-fractions of price (0.0002 = 2bp),
    matching CrossSectionalData.half_spread's own unit. One scalar for the
    whole frame — EDGE keeps only its relative (cross-sectional and
    through-time) structure, per the pre-registration. Raises if no usable
    cell exists or the median is non-positive, rather than silently scaling
    by inf/NaN."""
    if not target_median_half_spread > 0:
        raise ValueError(
            f"target_median_half_spread must be positive, got {target_median_half_spread!r}"
        )
    charged_region = half_spread.loc[half_spread.index >= pd.Timestamp(formation_start)]
    pooled = charged_region.to_numpy().ravel()
    pooled = pd.Series(pooled).dropna()
    if pooled.empty:
        raise ValueError(
            "scale_half_spread_frame_to_median: no non-NaN half-spread cells on or "
            f"after formation_start {formation_start.isoformat()} — nothing to calibrate."
        )
    observed_median = float(pooled.median())
    if not observed_median > 0:
        raise ValueError(
            f"pooled median half-spread is non-positive ({observed_median!r}) — the EDGE "
            "frame contract (result.where(result > 0)) should make this impossible; "
            "refusing to scale garbage."
        )
    scale = target_median_half_spread / observed_median
    return half_spread * scale, scale, observed_median
