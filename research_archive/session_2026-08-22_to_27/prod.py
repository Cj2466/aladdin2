import sys; sys.path.insert(0,'/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_82071471-600-1/backend')
from datetime import date
from app.services.research_lab.cross_sectional_small_mid_cap import run_small_cap_disposition_screening, run_small_cap_ivol_screening
r1 = run_small_cap_disposition_screening(date(2020,1,1), date(2026,8,26))
res, missing, recycled, trunc = r1
print("=== DISPOSITION === missing",len(missing),"recycled",len(recycled),"trunc",len(trunc))
for r in sorted(res, key=lambda r: -r.sharpe_annualized):
    d=r.deflated_sharpe
    print(f"{r.pattern_id:42s} sharpe={r.sharpe_annualized:+.3f} dsr={d.dsr:.3f} psr={d.psr_vs_zero:.2f} n_trials={d.n_trials} forms={r.n_formations} leg={r.avg_names_per_leg:.0f} costdrag={r.total_cost_drag:.4f}")
res2, mp, rc, tr, nosh = run_small_cap_ivol_screening(date(2020,1,1), date(2026,8,26))
print("=== IVOL === missing",len(mp),"recycled",len(rc),"trunc",len(tr),"noshares",len(nosh))
vw=sum(r.n_value_weighted_legs for r in res2); fb=sum(r.n_value_weight_fallbacks for r in res2)
print(f"VW legs={vw} fallback legs={fb} total={vw+fb} pct_fallback={100*fb/(vw+fb):.1f}%")
for r in sorted(res2, key=lambda r: -r.sharpe_annualized):
    d=r.deflated_sharpe
    print(f"{r.pattern_id:42s} sharpe={r.sharpe_annualized:+.3f} dsr={d.dsr:.3f} psr={d.psr_vs_zero:.2f} n_trials={d.n_trials} forms={r.n_formations} leg={r.avg_names_per_leg:.0f}")
