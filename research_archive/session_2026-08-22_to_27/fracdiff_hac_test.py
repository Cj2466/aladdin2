import sys, time, warnings
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
sys.path.insert(0, "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad")
import numpy as np
import pandas as pd
from scipy.stats import linregress
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from fracdiff_lib import frac_diff_ffd

warnings.filterwarnings("ignore")

prices = pd.read_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prices_3y.pkl")
tickers = list(prices.columns)

FIT_WINDOW = 90
THRESHOLD = 1e-4
D_GRID = np.round(np.arange(0.0, 1.05, 0.1), 2)
HAC_LAGS = 5  # ~1 trading week, standard rule-of-thumb floor for daily data

def min_d_search(log_price):
    for d in D_GRID:
        fd = frac_diff_ffd(log_price, d, THRESHOLD)
        fd = fd[~np.isnan(fd)]
        if len(fd) < 30:
            continue
        stat, pvalue, *_ = adfuller(fd, autolag="aic")
        if pvalue <= 0.05:
            return d, fd
    return None, None

raw_pass = 0
raw_hac_pass = 0     # NEW: existing OLS-on-time regression, but with HAC standard errors (no frac-diff)
fracdiff_naive_pass = 0
fracdiff_hac_pass = 0  # NEW: frac-diff + HAC-corrected mean test
n_ok = 0

# Track a few "obviously strong trend" tickers by raw slope magnitude to check signal isn't destroyed
strong_trend_results = []

t0 = time.time()
for ticker in tickers:
    series = prices[ticker].dropna()
    if len(series) < 750:
        continue
    log_price = np.log(series.to_numpy())
    window_raw = log_price[-FIT_WINDOW:]
    t_idx = np.arange(FIT_WINDOW, dtype=float)

    slope, intercept, r, p_raw, se = linregress(t_idx, window_raw)
    if p_raw <= 0.05:
        raw_pass += 1

    X = sm.add_constant(t_idx)
    ols_hac = sm.OLS(window_raw, X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    p_raw_hac = ols_hac.pvalues[1]
    if p_raw_hac <= 0.05:
        raw_hac_pass += 1

    n_ok += 1
    d_star, fd_full = min_d_search(log_price)
    if d_star is None:
        continue
    fd_window = fd_full[-FIT_WINDOW:]
    if len(fd_window) < FIT_WINDOW:
        continue

    # naive iid t-test on frac-diff'd mean
    from scipy.stats import ttest_1samp
    _, p_fd_naive = ttest_1samp(fd_window, 0.0)
    if p_fd_naive <= 0.05:
        fracdiff_naive_pass += 1

    # HAC-corrected mean test = OLS on a constant-only regressor with HAC SE
    const_only = np.ones_like(fd_window)
    ols_fd_hac = sm.OLS(fd_window, const_only).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    p_fd_hac = ols_fd_hac.pvalues[0]
    if p_fd_hac <= 0.05:
        fracdiff_hac_pass += 1

    if abs(slope) > 0.01:  # a genuinely strong raw price trend over 90 days
        strong_trend_results.append((ticker, slope, p_raw, p_raw_hac, d_star, p_fd_naive, p_fd_hac))

elapsed = time.time() - t0
print(f"Processed {n_ok} tickers in {elapsed:.1f}s")
print(f"\nPass rates at p<=0.05 over trailing {FIT_WINDOW}-day window (n={n_ok}):")
print(f"  EXISTING raw OLS-on-time (naive SE):        {raw_pass}/{n_ok} ({100*raw_pass/n_ok:.1f}%)")
print(f"  raw OLS-on-time + HAC SE (no frac-diff):    {raw_hac_pass}/{n_ok} ({100*raw_hac_pass/n_ok:.1f}%)")
print(f"  frac-diff(min d) + naive t-test:            {fracdiff_naive_pass}/{n_ok} ({100*fracdiff_naive_pass/n_ok:.1f}%)")
print(f"  frac-diff(min d) + HAC-corrected mean test: {fracdiff_hac_pass}/{n_ok} ({100*fracdiff_hac_pass/n_ok:.1f}%)")

print(f"\n{len(strong_trend_results)} tickers with a strong raw 90-day trend (|slope|>0.01/day):")
for t, slope, p_raw, p_raw_hac, d, p_naive, p_hac in strong_trend_results[:20]:
    print(f"  {t:6s} slope={slope:+.4f} p_raw={p_raw:.4f} p_raw_hac={p_raw_hac:.4f} d*={d:.1f} p_fd_naive={p_naive:.4f} p_fd_hac={p_hac:.4f}")
