"""A2, final step: what does the MEASURED per-ticker cost do to the Set-2 book?

The Set-2 lockbox charged a flat 20/P bps per month, built from the unsourced
DEFAULT_XS_COST_BPS = 5.0 one-way. A2 now has a measured cross-section. This
computes what the same book costs at the measured rates, for an equal-weighted
long-short portfolio drawn from the common-stock universe -- which is what OSAP
builds (210 of 242 predictors equal-weighted).

Reported as a RANGE, not a point, because the audit showed EDGE is informative
for illiquid names and returns its volatility noise floor for liquid ones. The
two ends are therefore:
  LOW  = tick floor (exact arithmetic, 0.005/price; a hard lower bound)
  HIGH = EDGE truncated-and-floored (informative where spreads are wide,
         noise-inflated where they are tight -> an upper bound)
"""
import json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, "..", "postpub_lockbox_2026-09-12")

df = pd.read_csv(os.path.join(HERE, "a2_per_ticker_cost.csv"))
df = df.dropna(subset=["tick_floor_half_bp", "edge_floored_half_bp"])
print(f"tickers with a measured cost: {len(df):,}")

# --- the book's own arithmetic, recovered from the committed result ---
# RESULT_SET2_OSAP.md: standard haircut = 20/P bps per month; P-clean post-pub
# pooled mean 0.4202 %/month at that haircut, Sharpe 0.5991.
MEAN_AT_STD = 0.4202          # %/month, net of the 20/P haircut
SR_AT_STD = 0.5991
STD_HAIRCUT_BP_PER_MONTH = 20.0   # for a P=1 (monthly) predictor
sd_monthly = (MEAN_AT_STD / (SR_AT_STD / np.sqrt(12.0)))
gross_mean = MEAN_AT_STD + STD_HAIRCUT_BP_PER_MONTH / 100.0
print(f"\nrecovered from the committed result:")
print(f"  monthly sd            : {sd_monthly:.4f} %")
print(f"  gross monthly mean    : {gross_mean:.4f} %   (net {MEAN_AT_STD:.4f} + 20bp haircut)")
print(f"  check: gross Sharpe   : {gross_mean/sd_monthly*np.sqrt(12):.4f}   "
      f"(committed table says 0.785)")

# --- measured cost of ONE full long-short reformation ---
# 4 legs traded per full replacement (close long, close short, open long, open
# short), each charged its one-way HALF-spread -- same convention the protocol used.
def book_cost_bp(col, weights=None):
    v = df[col].to_numpy(dtype=float)
    if weights is None:
        return 4.0 * float(np.median(v))
    return 4.0 * float(np.average(v, weights=weights))

low = book_cost_bp("tick_floor_half_bp")
high = book_cost_bp("edge_floored_half_bp")
print(f"\n=== measured cost of one full long-short reformation (bp) ===")
print(f"  protocol's assumption (4 x 5bp)        : {20.0:8.1f}")
print(f"  LOW  (tick floor, exact lower bound)   : {low:8.1f}   = {low/20:.2f}x the assumption")
print(f"  HIGH (EDGE floored, upper bound)       : {high:8.1f}   = {high/20:.2f}x the assumption")

# dollar-volume-weighted: what a size-aware implementation would pay
w = df["median_dollar_volume"].clip(lower=1).to_numpy()
print(f"  HIGH, dollar-volume weighted           : {book_cost_bp('edge_floored_half_bp', w):8.1f}"
      f"   (i.e. if you only traded where the money is)")

# --- what that does to the book, by rebalance frequency ---
print(f"\n=== book Sharpe at the measured cost, by rebalance cadence ===")
print(f"{'P (months)':>11s} {'assumed 20/P':>13s} {'LOW':>9s} {'HIGH':>9s} "
      f"{'SR @assumed':>12s} {'SR @LOW':>9s} {'SR @HIGH':>9s}")
rows = []
for P in (1, 3, 6, 12, 36):
    c_assumed = 20.0 / P / 100.0
    c_low = low / P / 100.0
    c_high = high / P / 100.0
    sr = lambda c: (gross_mean - c) / sd_monthly * np.sqrt(12.0)
    rows.append({"P": P, "assumed_bp_per_month": 20.0 / P,
                 "low_bp_per_month": low / P, "high_bp_per_month": high / P,
                 "sr_assumed": sr(c_assumed), "sr_low": sr(c_low), "sr_high": sr(c_high)})
    print(f"{P:11d} {20.0/P:13.1f} {low/P:9.1f} {high/P:9.1f} "
          f"{sr(c_assumed):12.3f} {sr(c_low):9.3f} {sr(c_high):9.3f}")

print("\n  (pass line was Sharpe >= 0.50)")

# --- break-even: how much cost can the book carry? ---
be_bp_per_month = gross_mean * 100.0                      # cost that zeroes the mean
be_50 = (gross_mean - 0.50 / np.sqrt(12.0) * sd_monthly) * 100.0
print(f"\n=== break-even cost ===")
print(f"  cost per month that takes the book to Sharpe 0.00 : {be_bp_per_month:.1f} bp")
print(f"  cost per month that takes the book to Sharpe 0.50 : {be_50:.1f} bp")
print(f"  -> a MONTHLY book survives the 0.50 line only if one reformation costs")
print(f"     under {be_50:.1f} bp; measured range is {low:.0f}-{high:.0f} bp.")
print(f"  -> an ANNUAL book (P=12) pays {low/12:.1f}-{high/12:.1f} bp/month, "
      f"comfortably under {be_50:.1f}.")

json.dump({
    "tickers": int(len(df)),
    "one_reformation_bp": {"assumed": 20.0, "low_tick_floor": round(low, 2),
                           "high_edge_floored": round(high, 2)},
    "recovered_monthly_sd_pct": round(float(sd_monthly), 5),
    "recovered_gross_monthly_mean_pct": round(float(gross_mean), 5),
    "breakeven_bp_per_month_to_sharpe_0": round(float(be_bp_per_month), 2),
    "breakeven_bp_per_month_to_sharpe_050": round(float(be_50), 2),
    "by_cadence": rows,
}, open(os.path.join(HERE, "a2_book_cost_implication.json"), "w"), indent=1, default=float)
print("\nwrote a2_book_cost_implication.json")
