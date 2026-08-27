import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import date, timedelta

from app.services.research_lab.ou_pairs import run_pairs_backtest, DEFAULT_ENTRY_Z, DEFAULT_EXIT_Z, DEFAULT_COST_BPS, DEFAULT_FIT_WINDOW_DAYS as OU_FIT
from app.services.research_lab.momentum import run_momentum_backtest, DEFAULT_FIT_WINDOW_DAYS as MOM_FIT
from app.services.research_lab.engine import WalkForwardConfig
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

end = date.today()
start = end - timedelta(days=365 * 5 + 60)
tickers = ["AAPL", "MSFT", "KO", "PEP"]
raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
close = raw["Close"].dropna(axis=0, how="any")

def prices_fn(req_tickers, s, e):
    sub = close[req_tickers]
    return sub[(sub.index.date >= s) & (sub.index.date <= e)], []

def sharpe_ann(returns):
    std = returns.std(ddof=1)
    if std == 0:
        return 0.0
    return returns.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR)

def moving_block_bootstrap_sharpe(returns: np.ndarray, block_len: int, n_boot: int = 2000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(returns)
    n_blocks_needed = int(np.ceil(n / block_len))
    max_start = n - block_len
    boot_sharpes = []
    for _ in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks_needed)
        sample = np.concatenate([returns[s:s+block_len] for s in starts])[:n]
        boot_sharpes.append(sharpe_ann(pd.Series(sample)))
    return np.array(boot_sharpes)

def analyze(name, result, block_len_override=None):
    print(f"\n=== {name} ===")
    if result.status != "ok":
        print("status:", result.status); return
    net = np.array([d.net_return for d in result.day_results])
    n = len(net)
    trades = result.trades
    holding = [t.holding_days for t in trades if not t.still_open]
    sr_point = sharpe_ann(pd.Series(net))
    print(f"n_days={n}, n_trades={len(trades)}, median_holding_days={np.median(holding) if holding else None}, sharpe_ann={sr_point:.3f}")

    # naive analytic SE (assumes iid daily returns), Lo (2002)/Mertens-style
    se_naive_annualized = np.sqrt((1 + sr_point**2/2) / n) * np.sqrt(TRADING_DAYS_PER_YEAR)

    block_len = block_len_override or max(5, int(np.median(holding)) if holding else 5)
    boot = moving_block_bootstrap_sharpe(net, block_len)
    se_boot = boot.std(ddof=1)
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    print(f"block_len used = {block_len} days")
    print(f"naive analytic SE(Sharpe_annualized) [assumes iid days] = {se_naive_annualized:.3f}")
    print(f"block-bootstrap SE(Sharpe_annualized) [block={block_len}d]   = {se_boot:.3f}")
    print(f"block-bootstrap 95% CI = [{ci_lo:.3f}, {ci_hi:.3f}]  (naive-iid 95% CI = [{sr_point-1.96*se_naive_annualized:.3f}, {sr_point+1.96*se_naive_annualized:.3f}])")
    print(f"SE inflation factor (block-boot / naive) = {se_boot/se_naive_annualized:.2f}x")

cfg = WalkForwardConfig(fit_window_days=OU_FIT, entry_z=DEFAULT_ENTRY_Z, exit_z=DEFAULT_EXIT_Z, cost_bps=DEFAULT_COST_BPS)
analyze("OU Pairs KO/PEP", run_pairs_backtest("KO", "PEP", 5, prices_fn, cfg))

cfg_m = WalkForwardConfig(fit_window_days=MOM_FIT, entry_z=DEFAULT_ENTRY_Z, exit_z=DEFAULT_EXIT_Z, cost_bps=DEFAULT_COST_BPS)
analyze("Momentum AAPL", run_momentum_backtest("AAPL", 5, prices_fn, cfg_m))
analyze("Momentum MSFT", run_momentum_backtest("MSFT", 5, prices_fn, cfg_m))
