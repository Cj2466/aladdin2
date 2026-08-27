"""Phase A live verification: fetch real hourly OHLCV bars for a pilot
universe and run the real pattern screening pass, honestly reporting the
results. Not part of the shipped codebase — a one-off verification script."""
import sys
import time

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.intraday_patterns import PATTERN_FAMILY, screen_pattern_universe
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

# 30 liquid large-caps, a subset of the existing SCREENING_UNIVERSE, spread
# across sectors -- not a separate universe list, per the plan's instruction.
PILOT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "JPM", "BAC", "XOM", "CVX",
    "JNJ", "PG", "KO", "PEP", "WMT", "HD", "DIS", "NFLX", "ADBE", "CRM",
    "INTC", "CSCO", "V", "MA", "UNH", "PFE", "ABBV", "T", "VZ", "GE",
]
missing_from_universe = [t for t in PILOT_TICKERS if t not in SCREENING_UNIVERSE]
print("tickers not in SCREENING_UNIVERSE (should be empty):", missing_from_universe)

provider = YFinanceProvider()
t0 = time.time()
bars_by_ticker, missing = provider.get_intraday_bars(PILOT_TICKERS, interval="60m")
t1 = time.time()
print(f"fetch took {t1-t0:.1f}s, resolved {len(bars_by_ticker)}/{len(PILOT_TICKERS)}, missing={missing}")
for ticker, bars in list(bars_by_ticker.items())[:3]:
    print(ticker, bars.shape, bars.index.min(), bars.index.max())

print(f"\npattern family size: {len(PATTERN_FAMILY)}")

t2 = time.time()
results = screen_pattern_universe(bars_by_ticker)
t3 = time.time()
print(f"screening took {t3-t2:.1f}s, {len(results)}/{len(PATTERN_FAMILY)} patterns produced a measurable result\n")

print(f"{'pattern_id':<45} {'family':<25} {'sharpe':>8} {'hit%':>6} {'ntrd':>5} {'nday':>5} {'ntick':>6} {'psr0':>7} {'dsr':>7}")
for r in results:
    dsr = r.deflated_sharpe
    hit = f"{r.hit_rate*100:.0f}" if r.hit_rate is not None else "n/a"
    psr0 = f"{dsr.psr_vs_zero:.3f}" if dsr.psr_vs_zero is not None else "n/a"
    dsr_val = f"{dsr.dsr:.3f}" if dsr.dsr is not None else "n/a"
    print(f"{r.pattern_id:<45} {r.family:<25} {r.sharpe_annualized:>8.3f} {hit:>6} {r.n_trades:>5} {r.n_trading_days:>5} {r.n_tickers_in_basket:>6} {psr0:>7} {dsr_val:>7}")

print("\n--- honest gate check ---")
best = results[0] if results else None
if best is not None:
    print(f"best pattern: {best.pattern_id} sharpe={best.sharpe_annualized:.3f} dsr={best.deflated_sharpe.dsr} dsr_floor_met={best.deflated_sharpe.dsr_floor_met}")
    print(best.deflated_sharpe.interpretation)
cleared = [r for r in results if r.deflated_sharpe.dsr is not None and r.deflated_sharpe.dsr > 0.5]
print(f"\npatterns with DSR > 0.5 (i.e. more likely than not a real edge net of the 29-pattern search): {len(cleared)}")
for r in cleared:
    print(" ", r.pattern_id, r.deflated_sharpe.dsr)
