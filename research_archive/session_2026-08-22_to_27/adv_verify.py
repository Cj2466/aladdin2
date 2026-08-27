import sys, time
from datetime import date
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")
from app.services.research_lab.cross_sectional import CrossSectionalConfig
from app.services.research_lab.cross_sectional_patterns_d2 import screen_d2_reversal_family, D2_FAMILY, D2_N_TRIALS
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START
start, end = MEMBERSHIP_DATA_START, date.today()
print("family size:", len(D2_FAMILY), "D2_N_TRIALS:", D2_N_TRIALS, flush=True)
for label, cfg in (("ON(default,config=None)", None), ("OFF(explicit)", CrossSectionalConfig(impute_delisting_returns=False))):
    t0=time.time()
    s = screen_d2_reversal_family(start=start, end=end, provider=None, config=cfg)
    print(f"--- {label}  {time.time()-t0:.1f}s  n_results={len(s.results)}  n_missing={len(s.missing_price_data)}", flush=True)
    for r in sorted(s.results, key=lambda r: r.pattern_id):
        d=r.deflated_sharpe
        print(f"  {r.pattern_id:<40} sharpe={r.sharpe_annualized:.4f} ndays={r.n_trading_days} nform={r.n_formations} ntrials={d.n_trials} dsr={d.dsr} psr0={None if d.psr_vs_zero is None else round(d.psr_vs_zero,4)} floor={d.dsr_floor_met}", flush=True)
    d=s.independent_window_disclosure
    print(f"  disclosure: replayed={d.n_trading_days_replayed} hold={d.holding_days} full={d.n_full_independent_windows} partial={d.partial_window_fraction:.4f}", flush=True)
