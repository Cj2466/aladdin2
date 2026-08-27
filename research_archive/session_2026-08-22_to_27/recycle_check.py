import sys
import time
import warnings
from datetime import date, timedelta

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_82071471-600-1/backend")
import pandas as pd

from app.services.research_lab import small_cap_membership_history as scm

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
close = pd.read_pickle(f"{SCRATCH}/sp600_close.pkl")

# The harness's containment argument: recycled data can only reach a portfolio
# if it appears within `holding_days` of the ticker's index exit. Longest hold
# in this run is 252 trading days ~= 365 calendar days.
MAX_HOLD_CALENDAR_DAYS = 365

wholly_recycled, leaky, safe = [], [], []
for t in close.columns:
    spans = scm.get_membership_intervals(t)
    if not spans or spans[-1][1] is None:
        continue  # still a member; no exit to be recycled after
    exit_date = spans[-1][1]
    s = close[t].dropna()
    if s.empty:
        continue
    first, last = s.index[0].date(), s.index[-1].date()
    if first > exit_date:
        wholly_recycled.append((t, exit_date, first, (first - exit_date).days))
        continue
    # Data continues past the exit: is there a long gap after the exit, with
    # data resuming on the far side? That resumption is the recycled listing.
    after = s[s.index.date > exit_date]
    if after.empty:
        safe.append(t)
        continue
    gaps = after.index.to_series().diff().dt.days
    big = gaps[gaps > 30]
    if len(big):
        resume = big.index[0].date()
        (leaky if (resume - exit_date).days < MAX_HOLD_CALENDAR_DAYS else safe).append(
            (t, exit_date, resume, (resume - exit_date).days)
        )
    else:
        safe.append(t)

print(f"departed tickers with price data: {len(wholly_recycled) + len(leaky) + len(safe)}")
print(f"  WHOLLY recycled (all history postdates index exit): {len(wholly_recycled)}")
for r in sorted(wholly_recycled, key=lambda x: x[3])[:8]:
    print(f"     {r[0]}: exit {r[1]}, history starts {r[2]} (+{r[3]}d)")
print(f"  LEAKY (resumes after a >30d gap, WITHIN {MAX_HOLD_CALENDAR_DAYS}d of exit "
      f"-> can reach a 252-day hold): {len(leaky)}")
for r in sorted(leaky, key=lambda x: x[3])[:10]:
    print(f"     {r[0]}: exit {r[1]}, resumes {r[2]} (+{r[3]}d)")
print(f"  safe: {len(safe)}")

print("\n--- timing get_shares_outstanding (D1 needs it for every priced ticker) ---")
from app.services.market_data.yfinance_provider import YFinanceProvider

p = YFinanceProvider()
sample = list(close.columns[:10])
t0 = time.time()
shares, miss = p.get_shares_outstanding(sample, date(2018, 11, 1), date.today())
dt = time.time() - t0
print(f"  10 tickers in {dt:.1f}s -> {len(close.columns)} would take ~{dt / 10 * len(close.columns) / 60:.0f} min")
print(f"  resolved {len(shares)} of 10, missing {len(miss)}")
