"""Fast end-to-end smoke test of the disposition family on the CACHED panel,
so bugs surface before the real production run is launched."""
import sys
import time
import warnings
from datetime import date

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_82071471-600-1/backend")
import pandas as pd

from app.services.research_lab.cross_sectional import CrossSectionalData
from app.services.research_lab import cross_sectional_small_mid_cap as sc
from app.services.research_lab.cross_sectional import screen_cross_sectional_universe
from app.services.research_lab.small_cap_membership_history import was_member

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
frames = {n: pd.read_pickle(f"{SCRATCH}/sp600_{n}.pkl") for n in ("open", "close", "volume")}
print("panel:", frames["close"].shape)

frames, recycled, truncated = sc.mask_recycled_ticker_prices(frames)
print(f"recycled dropped: {len(recycled)} -> {recycled[:8]}")
print(f"truncated: {len(truncated)}")
print("panel after mask:", frames["close"].shape)

config = sc.default_small_cap_config(date(2020, 1, 1))
data = CrossSectionalData(close=frames["close"], open=frames["open"], volume=frames["volume"])
t0 = time.time()
results = screen_cross_sectional_universe(
    data, sc.SMALL_CAP_DISPOSITION_FAMILY, config,
    membership_fn=was_member, n_trials_override=sc.DISPOSITION_N_TRIALS,
)
print(f"screened in {time.time() - t0:.0f}s -> {len(results)} results")
for r in results:
    d = r.deflated_sharpe
    print(f"  {r.pattern_id:38s} SR={r.sharpe_annualized:+.3f} DSR={d.deflated_sharpe_ratio:.3f} "
          f"n_form={r.n_formations} leg={r.avg_names_per_leg:.0f} days={r.n_trading_days} "
          f"cost={r.total_cost_drag:.4f} n_trials={d.n_trials}")
