from datetime import date
from app.services.research_lab.cross_sectional_index_removal import (
    run_index_removal_screening, MEMBERSHIP_DATA_START)
s = run_index_removal_screening(MEMBERSHIP_DATA_START, date(2026,6,30))
sm = s.sample
print("entered",sm.n_entered,"clusters",sm.n_independent_clusters,"candidates",sm.n_candidate_removals,"renamedrop",sm.n_rename_artifacts_dropped)
print("rejected", sm.rejected_by_reason)
print("nresults", len(s.results))
for r in s.results:
    print(f"h={r.holding_days:3d} {r.leg_weighting:11s} sharpe={r.sharpe_annualized:+.4f} dsr={r.deflated_sharpe.dsr:.4f} ntrials={r.deflated_sharpe.n_trials} inv={r.invested_fraction:.4f} fallback={r.n_weight_fallback_days} delisted={r.n_events_delisted_mid_hold} nev={r.n_events_entered}")
