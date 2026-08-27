import sys, datetime
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-1/backend")
from app.services.research_lab.cross_sectional_commodities import (
    run_commodities_screening, COMMODITIES_N_TRIALS, COMMODITIES_UNIVERSE,
)
s = run_commodities_screening(end=datetime.date(2026, 8, 26))
print("N_TRIALS_CONST", COMMODITIES_N_TRIALS, "universe", len(COMMODITIES_UNIVERSE))
print("panel", s.panel_start, s.panel_end, "rows", s.n_panel_rows)
print("scrubbed", s.n_bad_prints_scrubbed, s.bad_prints_by_ticker)
print("breadth", round(s.effective_breadth,3), "maxpair", s.max_pair, round(s.max_pair_correlation,4))
print("excluded", s.excluded_redundant, "legsize", s.leg_size, "warnings", s.warnings)
print("n_results", len(s.results))
rows=[]
for r in s.results:
    rows.append((r.pattern_id, r.sharpe_annualized, getattr(r,"deflated_sharpe_ratio",None),
                 getattr(r,"psr_zero",None), getattr(r,"n_formations",None), getattr(r,"n_trials",None)))
for t in sorted(rows, key=lambda x: -x[1]):
    print(f"{t[0]:42s} {t[1]:+.3f} {t[2]!s:>7.7s} {t[3]!s:>7.7s} nform={t[4]} ntr={t[5]}")
import statistics
sh=[r[1] for r in rows]
print("MEAN", round(statistics.mean(sh),4), "MEDIAN", round(statistics.median(sh),4), "POS", sum(1 for x in sh if x>0), "/", len(sh))
