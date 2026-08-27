import sys, time
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from statsmodels.tsa.stattools import acf

from app.services.research_lab.ou_pairs import run_pairs_backtest, DEFAULT_ENTRY_Z, DEFAULT_EXIT_Z, DEFAULT_COST_BPS, DEFAULT_FIT_WINDOW_DAYS as OU_FIT
from app.services.research_lab.momentum import run_momentum_backtest, DEFAULT_FIT_WINDOW_DAYS as MOM_FIT
from app.services.research_lab.engine import WalkForwardConfig

end = date.today()
start = end - timedelta(days=365 * 5 + 60)
tickers = ["AAPL", "MSFT", "KO", "PEP", "XOM", "CVX"]
raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
close = raw["Close"].dropna(axis=0, how="any")
print("Fetched", close.shape)

def prices_fn(req_tickers, s, e):
    sub = close[req_tickers]
    sub = sub[(sub.index.date >= s) & (sub.index.date <= e)]
    return sub, []

def effective_n(returns: np.ndarray, max_lag=30):
    n = len(returns)
    rho = acf(returns, nlags=max_lag, fft=True)[1:]  # exclude lag 0
    # Standard effective-sample-size formula for the mean estimator's variance inflation
    denom = 1.0 + 2.0 * sum((1 - k/n) * rho[k-1] for k in range(1, max_lag+1))
    return n / denom, rho

print("\n=== OU Pairs: KO/PEP ===")
cfg = WalkForwardConfig(fit_window_days=OU_FIT, entry_z=DEFAULT_ENTRY_Z, exit_z=DEFAULT_EXIT_Z, cost_bps=DEFAULT_COST_BPS)
result = run_pairs_backtest("KO", "PEP", 5, prices_fn, cfg)
print("status:", result.status, "n_out_of_sample_days:", result.n_out_of_sample_days)
if result.status == "ok":
    net_returns = np.array([d.net_return for d in result.day_results])
    n_eff, rho = effective_n(net_returns)
    print(f"Raw N={len(net_returns)}, lag-1 ACF={rho[0]:.4f}, lag-2={rho[1]:.4f}, lag-5={rho[4]:.4f}")
    print(f"Effective N (accounting for autocorrelation) = {n_eff:.1f}  (discount factor = {n_eff/len(net_returns):.3f})")

print("\n=== OU Pairs: XOM/CVX ===")
result2 = run_pairs_backtest("XOM", "CVX", 5, prices_fn, cfg)
print("status:", result2.status, "n_out_of_sample_days:", result2.n_out_of_sample_days)
if result2.status == "ok":
    net_returns2 = np.array([d.net_return for d in result2.day_results])
    n_eff2, rho2 = effective_n(net_returns2)
    print(f"Raw N={len(net_returns2)}, lag-1 ACF={rho2[0]:.4f}, lag-2={rho2[1]:.4f}, lag-5={rho2[4]:.4f}")
    print(f"Effective N = {n_eff2:.1f}  (discount factor = {n_eff2/len(net_returns2):.3f})")

print("\n=== Momentum: AAPL ===")
cfg_m = WalkForwardConfig(fit_window_days=MOM_FIT, entry_z=DEFAULT_ENTRY_Z, exit_z=DEFAULT_EXIT_Z, cost_bps=DEFAULT_COST_BPS)
result3 = run_momentum_backtest("AAPL", 5, prices_fn, cfg_m)
print("status:", result3.status, "n_out_of_sample_days:", result3.n_out_of_sample_days)
if result3.status == "ok":
    net_returns3 = np.array([d.net_return for d in result3.day_results])
    n_eff3, rho3 = effective_n(net_returns3)
    print(f"Raw N={len(net_returns3)}, lag-1 ACF={rho3[0]:.4f}, lag-2={rho3[1]:.4f}, lag-5={rho3[4]:.4f}")
    print(f"Effective N = {n_eff3:.1f}  (discount factor = {n_eff3/len(net_returns3):.3f})")

print("\n=== Momentum: MSFT ===")
result4 = run_momentum_backtest("MSFT", 5, prices_fn, cfg_m)
print("status:", result4.status, "n_out_of_sample_days:", result4.n_out_of_sample_days)
if result4.status == "ok":
    net_returns4 = np.array([d.net_return for d in result4.day_results])
    n_eff4, rho4 = effective_n(net_returns4)
    print(f"Raw N={len(net_returns4)}, lag-1 ACF={rho4[0]:.4f}, lag-2={rho4[1]:.4f}, lag-5={rho4[4]:.4f}")
    print(f"Effective N = {n_eff4:.1f}  (discount factor = {n_eff4/len(net_returns4):.3f})")
