# The estimator sign-mode switch (owner-approved 2026-09-15)

Owner approved two items after the 2026-09-15 audit: switch the estimator mode in
the main code, and merge the two old research branches. This is the first.
**A correction to the premise is recorded first, because the owner approved it on
a stale reading that I supplied.**

## The premise had already shifted — my error in reporting it

I told the owner that switching would "move a live registration's track record,
0.5946 → 0.7456". That number is real, but it describes a switch **already made
on 2026-09-05**: `build_lazy_prices_half_spread_frame` has called
`build_calibrated_half_spread_frame` since then, and it is the single builder for
both that family's screening path and its live tick.

I read it as pending because `live_registration_dependencies.py`'s own docstring
still says so ("a fourth is live right now… lazy_prices_jaccard_full trades on
it"). That docstring is stale and a dated correction has been appended to it.

**Consequence: no live registration was affected by this change.** The four
consumers that actually moved are research families.

## What changed

Two lines in `spread_estimator.py`, both in the UNCALIBRATED entry points:

| function | before | after |
|---|---|---|
| `estimate_effective_spread` | `edge_rolling(frame, window=…)` → sign=False | `sign=CALIBRATED_SIGN_MODE` (True) |
| `build_edge_half_spread_frame` | `edge_rolling(ohlc, window=…)` → sign=False | `sign=CALIBRATED_SIGN_MODE` (True) |

Nothing else. `build_calibrated_half_spread_frame` already passed sign=True.

**Why this is safe to change without inventing an anchor:** `sign=False` folds
the estimator's noise into a positive number via `abs()` and can never return
zero. `sign=True` lets it go negative, and the existing
`return result.where(result > 0.0)` already NaNs those cells — which every caller
already treats as "no estimate" and falls back to the flat `cost_bps` for,
counted per formation in `FormationRecord.edge_flat_fallback_notional` and never
silent. So the downstream contract is untouched; only the fabrication is removed.
No level anchor is introduced, which is what made this different from the A2
question.

## Measured on one same-day baseline

159 tickers × 213 days, 2024-01-02 → 2026-09-11, built once and read by both arms.

| | cells charged | median | p90 |
|---|---|---|---|
| sign=False (before) | 24,009 / 33,867 (**70.9%**) | 50.57 bp | 183.66 bp |
| sign=True (after) | 15,188 / 33,867 (**44.8%**) | 51.83 bp | 195.04 bp |

- **On cells charged under BOTH modes the median change is +0.00 bp.** The switch
  does not move surviving estimates; it withdraws invented ones.
- **8,821 cells (26.0% of the frame) were being charged a median of 49.00 bp**
  (p25 27.31, p75 78.93) that the estimator had manufactured from volatility.
  On synthetic data with a TRUE spread of exactly zero, sign=False returns
  +2.65 / +7.27 / +20.43 bp at daily vol 50 / 150 / 400 bp while sign=True is
  centred on zero (`number_audit_2026-09-15/validate_edge.py`).

### Proof that the live registration is untouched

`build_calibrated_half_spread_frame` was run on the identical panel before and
after the edit. Stable hash **9504763528740016484** both times, identical
`CalibrationReport`. Proven, not assumed. Acknowledged in
`live_registration_dependencies.json` (2026-09-15 entry), sha256
`d50570d6…` → `3e2e04dc…`.

## Stated plainly, including the uncomfortable part

**This change makes four research families' backtests CHEAPER, and therefore
better-looking.** That direction deserves suspicion, so:

- the 49 bp it withdraws was invented, and that is measured, not argued;
- but the flat `cost_bps` those cells now fall back to is itself **optimistic**
  for a stock too illiquid for the estimator to measure — a pre-existing property
  of the harness's design, not introduced here, but it now applies to 26% of
  cells instead of ~0%;
- so **`ipo_lockup_expiration`, `jump_drift`, `eigenportfolio` and `patterns`
  now have STALE stored results.** None of their numbers may be quoted again
  until each is re-run against a same-day baseline. Logged, not done here.

The better fix for those four is not the flat fallback but a per-liquidity-bucket
sourced rate — the same open item A2 named, now with the SEC/Collver curve
available to build it from.
