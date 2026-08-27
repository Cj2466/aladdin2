import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")
from datetime import date, timedelta
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START, get_universe_over
from app.services.market_data.yfinance_provider import YFinanceProvider
provider = YFinanceProvider()
universe = get_universe_over(MEMBERSHIP_DATA_START, date.today())
padded_start = MEMBERSHIP_DATA_START - timedelta(days=850)
frames, missing = provider.get_daily_ohlcv(universe, padded_start, date.today())
print(len(universe), "universe size")
print(len(missing), "missing")
missing_sorted = sorted(missing)
for t in missing_sorted:
    print(t)
with open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/my_missing_repro.txt", "w") as f:
    f.write("\n".join(missing_sorted))
