import sys, time, warnings
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
sys.path.insert(0, "$SP".replace("$SP", "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"))
import numpy as np
import pandas as pd
from scipy.stats import linregress, ttest_1samp
from statsmodels.tsa.stattools import adfuller
from fracdiff_lib import get_weights_ffd, frac_diff_ffd

warnings.filterwarnings("ignore")

prices = pd.read_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prices_3y.pkl")
tickers = list(prices.columns)

FIT_WINDOW = 90  # matches momentum.DEFAULT_FIT_WINDOW_DAYS
THRESHOLD = 1e-4
D_GRID = np.round(np.arange(0.0, 1.05, 0.1), 2)

def min_d_search(log_price: np.ndarray):
    """Lopez de Prado's own method: smallest d in D_GRID such that the FFD
    series passes ADF (p<=0.05) for stationarity."""
    for d in D_GRID:
        fd = frac_diff_ffd(log_price, d, THRESHOLD)
        fd = fd[~np.isnan(fd)]
        if len(fd) < 30:
            continue
        try:
            stat, pvalue, *_ = adfuller(fd, autolag="aic")
        except Exception:
            continue
        if pvalue <= 0.05:
            return d, pvalue, fd
    return None, None, None

raw_pass = 0     # existing fit_momentum_window (OLS log_price ~ t) baseline
simple_ret_pass = 0   # d=1 baseline (plain daily returns' mean, one-sample t-test)
fracdiff_pass = 0     # frac-diff at minimum-d, one-sample t-test on its mean
n_ok = 0
n_no_d_found = 0
d_values = []

t0 = time.time()
for ticker in tickers:
    series = prices[ticker].dropna()
    if len(series) < 750:
        continue
    log_price = np.log(series.to_numpy())

    # --- existing baseline: raw OLS-on-time over trailing 90 days ---
    window_raw = log_price[-FIT_WINDOW:]
    t_idx = np.arange(FIT_WINDOW, dtype=float)
    slope, intercept, r, p_raw, se = linregress(t_idx, window_raw)
    if p_raw <= 0.05:
        raw_pass += 1

    # --- d=1 baseline: plain returns' mean over trailing 90 days ---
    simple_ret = np.diff(log_price)[-FIT_WINDOW:]
    _, p_simple = ttest_1samp(simple_ret, 0.0)
    if p_simple <= 0.05:
        simple_ret_pass += 1

    # --- frac-diff at minimum d found via ADF search on the FULL series ---
    # (Full ~750-990 day series used only to CHOOSE d -- a slowly-varying
    # per-ticker hyperparameter, not a per-day OOS statistic; see plan text
    # for the walk-forward-safe design: d is chosen from the PRE-OOS
    # calibration slice only, not the live series, in the real design.)
    d_star, adf_p, fd_full = min_d_search(log_price)
    n_ok += 1
    if d_star is None:
        n_no_d_found += 1
        continue
    d_values.append(d_star)
    fd_window = fd_full[-FIT_WINDOW:]
    if len(fd_window) < FIT_WINDOW:
        continue
    _, p_fd = ttest_1samp(fd_window, 0.0)
    if p_fd <= 0.05:
        fracdiff_pass += 1

elapsed = time.time() - t0
print(f"Processed {n_ok} tickers in {elapsed:.1f}s ({elapsed/max(n_ok,1)*1000:.0f}ms/ticker)")
print(f"No stationary d found in [0,1] grid: {n_no_d_found}/{n_ok}")
print(f"\nPass rates at p<=0.05 over trailing {FIT_WINDOW}-day window:")
print(f"  EXISTING (raw log_price ~ t OLS):      {raw_pass}/{n_ok} ({100*raw_pass/n_ok:.1f}%)  <- ground-truth baseline was ~85-86% at 503-universe scale")
print(f"  d=1 (plain daily-return mean t-test):  {simple_ret_pass}/{n_ok} ({100*simple_ret_pass/n_ok:.1f}%)")
print(f"  frac-diff at minimum d (t-test on fd): {fracdiff_pass}/{n_ok} ({100*fracdiff_pass/n_ok:.1f}%)")

d_arr = np.array(d_values)
print(f"\nMinimum-d distribution (n={len(d_arr)}): mean={d_arr.mean():.2f} median={np.median(d_arr):.2f} "
      f"min={d_arr.min():.2f} max={d_arr.max():.2f}")
print("Histogram:", {float(d): int((d_arr==d).sum()) for d in sorted(set(d_arr))})
