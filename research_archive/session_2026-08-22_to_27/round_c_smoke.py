"""Round C SMOKE TEST — pipeline correctness only, NOT a research result.

A handful of tickers over ~3 years, real yfinance daily OHLCV, real
point-in-time membership. Proves the composed pipeline (fetch -> PIT
eligibility -> ranking -> formation -> holding-period realization -> DSR)
executes end-to-end on live data and produces sane-shaped output. Any
Sharpe printed here is meaningless (12 tickers is not a cross-section);
the production run is queued for when compute frees up.
"""
import sys
import time
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_patterns import ROUND_C_FAMILY
from app.services.research_lab.sp500_membership_history import was_member

# 11 stalwart members + ENPH, a REAL index departure (removed 2025-09-22,
# still trading) — a live-data check that a mid-replay removal exits the
# eligible set on the true date.
TICKERS = ["AAPL", "MSFT", "JPM", "KO", "PG", "XOM", "WMT", "HD", "CAT", "MMM", "NVDA", "ENPH"]
START = date(2023, 6, 1)
END = date(2026, 8, 25)
PADDED_START = date(2021, 2, 1)  # warm-up for the 567-row CGO lookback

t0 = time.time()
provider = YFinanceProvider()
frames, missing = provider.get_daily_ohlcv(TICKERS, PADDED_START, END)
t_fetch = time.time() - t0
print(f"fetch: {t_fetch:.1f}s, missing={missing}")
close = frames["close"]
print(f"close frame: {close.shape[0]} rows x {close.shape[1]} tickers, "
      f"{close.index[0].date()} .. {close.index[-1].date()}")
print(f"open NaN frac: {frames['open'].isna().mean().mean():.4f}, "
      f"volume NaN frac: {frames['volume'].isna().mean().mean():.4f}")

data = CrossSectionalData(close=close, open=frames["open"], volume=frames["volume"])
config = CrossSectionalConfig(min_names_per_leg=1, formation_start=START)

t1 = time.time()
results = screen_cross_sectional_universe(data, ROUND_C_FAMILY, config)
t_screen = time.time() - t1
print(f"\nscreen: {t_screen:.1f}s for {len(ROUND_C_FAMILY)} specs -> {len(results)} scored results")

print(f"\n{'pattern_id':38s} {'form':>4s} {'skip':>4s} {'days':>5s} {'sharpe':>7s} "
      f"{'cost':>7s} {'DSR':>6s} {'ntrl':>4s}")
for r in results:
    dsr = f"{r.deflated_sharpe.dsr:.3f}" if r.deflated_sharpe.dsr is not None else "  n/a"
    print(f"{r.pattern_id:38s} {r.n_formations:4d} {r.n_skipped_formations:4d} "
          f"{r.n_trading_days:5d} {r.sharpe_annualized:7.2f} {r.total_cost_drag:7.4f} "
          f"{dsr:>6s} {r.deflated_sharpe.n_trials:4d}")

# --- ENPH point-in-time check on LIVE data ------------------------------
ENPH_REMOVAL = date(2025, 9, 22)
assert was_member("ENPH", date(2025, 9, 19)) and not was_member("ENPH", ENPH_REMOVAL)
spec = next(s for s in ROUND_C_FAMILY if s.pattern_id == "gh52_ls_decile_h21")
replay = run_cross_sectional_backtest(data, spec, config)
pre = [f for f in replay.formations if f.date.date() < ENPH_REMOVAL]
post = [f for f in replay.formations if f.date.date() >= ENPH_REMOVAL]
assert post, "replay must extend past ENPH's removal"
assert all(f.n_eligible == 12 for f in pre if f.date.date() >= date(2023, 6, 2)), \
    "expected all 12 tickers eligible pre-removal"
assert all(f.n_eligible == 11 for f in post), "ENPH must drop from eligibility on 2026-05-07"
assert all("ENPH" not in f.long_tickers and "ENPH" not in f.short_tickers for f in post)
print(f"\nENPH PIT check on live data: {len(pre)} formations with 12 eligible before "
      f"{ENPH_REMOVAL}, {len(post)} with 11 after — ENPH never held post-removal. OK")
print(f"\ntotal smoke runtime: {time.time() - t0:.1f}s")
print("SMOKE TEST: pipeline executed end-to-end; numbers above are shape checks, not results.")
