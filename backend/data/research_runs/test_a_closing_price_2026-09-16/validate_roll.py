"""Validate the Roll (1984) estimator on synthetic data with a KNOWN spread,
BEFORE using it on real data (CLAUDE.md: never trust a published formula until it
reproduces a known answer on simulated data).

Source, read directly: Roll, "A Simple Implicit Measure of the Effective Bid-Ask
Spread in an Efficient Market", Journal of Finance 39(4) 1984, pp. 1127-1139.
  Abstract: "Spread = 2 sqrt(-cov) where 'cov' is the first-order serial
  covariance of price changes."
  Equation (2), applied to RETURNS: "s_jt = 200 sqrt(-c_jt) ... (The constant 200
  instead of 2.0 converts the units to percent)."
  Minimum sample: "one month (21 trading days) for calculations with daily returns".

Roll's own warning, same paper p.1134, is what this validation is checking for:
daily-derived estimates averaged 0.298% while weekly-derived averaged 1.74% on the
same stocks -- a 5.8x gap he attributes to "inefficiency-induced positive
dependence" in daily returns, with the daily mean covariance NEGATIVE (estimator
undefined) in six years out of twenty.
"""
import math
import numpy as np

rng = np.random.default_rng(20260916)


def roll_spread_from_returns(r):
    """Roll eq.(2) in fraction-of-price units: s = 2*sqrt(-cov(r_t, r_{t-1})).
    Returns None where the covariance is non-negative (estimator undefined)."""
    if len(r) < 21:                      # Roll's own minimum
        return None
    c = float(np.cov(r[1:], r[:-1], ddof=1)[0, 1])
    return 2.0 * math.sqrt(-c) if c < 0 else None


def simulate(true_spread_bp, n_days=250, trades_per_day=200, daily_vol_bp=200.0,
             drift_persistence=0.0):
    """Efficient log price is a random walk; each observed CLOSE is a trade at
    bid or ask. drift_persistence>0 adds positive autocorrelation to the
    efficient price -- the contamination Roll blames for the daily/weekly gap."""
    S = true_spread_bp / 1e4
    sig = (daily_vol_bp / 1e4) / math.sqrt(trades_per_day)
    n = n_days * trades_per_day
    e = rng.normal(0.0, sig, n)
    if drift_persistence:                # AR(1) in the efficient increments
        for i in range(1, n):
            e[i] += drift_persistence * e[i - 1]
    m = np.cumsum(e)
    q = rng.choice([-1.0, 1.0], n)
    p = np.exp(m + (S / 2.0) * q)
    closes = p.reshape(n_days, trades_per_day)[:, -1]
    return closes


def run(label, **kw):
    out = {}
    for true_bp in (0.0, 5.0, 30.0, 100.0, 300.0):
        d_est, w_est, d_undef = [], [], 0
        for _ in range(40):
            c = simulate(true_bp, **kw)
            rd = np.diff(np.log(c))
            s = roll_spread_from_returns(rd)
            if s is None: d_undef += 1
            else: d_est.append(s * 1e4)
            cw = c[::5]                               # weekly closes
            rw = np.diff(np.log(cw))
            sw = roll_spread_from_returns(rw)
            if sw is not None: w_est.append(sw * 1e4)
        out[true_bp] = (np.mean(d_est) if d_est else float('nan'),
                        d_undef / 40 * 100,
                        np.mean(w_est) if w_est else float('nan'))
    print(f"\n=== {label} ===")
    print(f"{'true full spread':>17s} {'Roll daily':>12s} {'undefined':>11s} {'Roll weekly':>13s}")
    for k, (d, u, w) in out.items():
        print(f"{k:14.1f} bp {d:11.2f} {u:10.0f}% {w:12.2f}")
    return out


print("Roll (1984) eq.(2) validated against a KNOWN injected spread")
run("clean random walk (the model Roll assumes holds exactly)")
run("with positive autocorrelation in the efficient price (Roll's own suspected contaminant)",
    drift_persistence=0.15)
run("low volatility", daily_vol_bp=80.0)
run("high volatility", daily_vol_bp=400.0)


# ---------------------------------------------------------------------------
# Does a LONGER sample bring the noise floor down far enough to run the test?
# Our panel holds up to 2,688 daily bars per ticker (2016-01 -> 2026-09).
# The question the test must answer is whether Q1 reads ~0 or ~92-124 bp, so the
# noise floor at true-spread-zero must be well below 92 bp to be usable.
# ---------------------------------------------------------------------------
print("\n\n" + "=" * 74)
print("NOISE FLOOR vs SAMPLE LENGTH, at a TRUE spread of exactly ZERO")
print("(the test needs this well under 92 bp -- the SEC micro-cap figure -- to work)")
print(f"{'daily bars':>11s} {'low vol':>20s} {'normal vol':>20s} {'high vol':>20s}")
for n_days in (250, 500, 1000, 2000, 2688):
    row = []
    for vol in (80.0, 200.0, 400.0):
        est, undef = [], 0
        for _ in range(40):
            c = simulate(0.0, n_days=n_days, daily_vol_bp=vol)
            s = roll_spread_from_returns(np.diff(np.log(c)))
            if s is None: undef += 1
            else: est.append(s * 1e4)
        row.append((np.mean(est) if est else float('nan'), undef / 40 * 100))
    print(f"{n_days:11d} " + " ".join(f"{m:12.1f}bp ({u:3.0f}%)" for m, u in row))
print("  (the % is the share of tickers where the estimator is UNDEFINED)")
