import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a6fc3015debbbe27e/backend")
from datetime import date

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_correlation_risk_premium import (
    SECTOR_ETF_UNIVERSE,
    _run_pit_crosscheck,
)

prov = YFinanceProvider()
closes, missing = prov.get_price_history(list(SECTOR_ETF_UNIVERSE), date(2014, 1, 1), date(2026, 8, 27))
print("sector missing:", missing, "rows:", len(closes), flush=True)
r = _run_pit_crosscheck(prov, closes, date(2014, 1, 1), date(2026, 8, 27))
print("\n=== POINT-IN-TIME S&P 500 CROSS-CHECK ===")
print("status:", r.status)
print("n_dates:", r.n_dates, r.start, "->", r.end)
print("level corr (sector proxy vs true PIT constituent corr):", r.level_correlation)
print("change corr:", r.change_correlation)
print("mean sector corr %:", r.mean_sector_correlation, " mean PIT constituent corr %:", r.mean_pit_correlation)
print("mean names per cross-section:", r.mean_names)
for n in r.notes:
    print(" note:", n)
