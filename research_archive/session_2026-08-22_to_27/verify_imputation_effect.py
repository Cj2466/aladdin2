"""Independent verification: does impute_delisting_returns=True actually
change D2's results vs False, as the module docstring claims? Re-runs the
same window with imputation explicitly OFF and diffs Sharpes against the
production (imputation ON) run already completed."""
import sys, time
from datetime import date
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

from app.services.research_lab.cross_sectional import CrossSectionalConfig
from app.services.research_lab.cross_sectional_patterns_d2 import screen_d2_reversal_family
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

start = MEMBERSHIP_DATA_START
end = date.today()

cfg = CrossSectionalConfig(impute_delisting_returns=False)
t0 = time.time()
summary = screen_d2_reversal_family(start=start, end=end, provider=None, config=cfg)
print(f"done in {time.time()-t0:.1f}s")
for r in summary.results:
    print(f"{r.pattern_id:<40} sharpe={r.sharpe_annualized:.4f}  n_days={r.n_trading_days}")
