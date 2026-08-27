"""Deep post-run analysis of the Phase B screen results."""

import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

RESULTS = Path("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/screen_results")
results = pickle.loads((RESULTS / "final_results.pkl").read_bytes())

from app.services.research_lab.intraday_patterns import PHASE_B_TOTAL_TRIALS

print(f"included: {len(results)} of {PHASE_B_TOTAL_TRIALS} pre-declared trials")
by_tf = defaultdict(list)
for r in results:
    by_tf[r.timeframe].append(r)
for tf, rs in by_tf.items():
    sh = [r.sharpe_annualized for r in rs]
    print(f"  {tf}: {len(rs)} included, sharpe min={min(sh):.2f} median={np.median(sh):.2f} max={max(sh):.2f}, positives={sum(1 for s in sh if s > 0)}")

sh_all = [r.sharpe_annualized for r in results]
print(f"overall: positives {sum(1 for s in sh_all if s>0)}/{len(sh_all)}, sigma_SR={np.std(sh_all, ddof=1):.3f}")

best = results[0]
d = best.deflated_sharpe
print("\nBEST PATTERN (by pooled Sharpe):")
print(f"  {best.pattern_id} [{best.timeframe}] family={best.family}")
print(f"  sharpe={best.sharpe_annualized:.4f} dsr={d.dsr} psr_vs_zero={d.psr_vs_zero}")
print(f"  n_days={best.n_trading_days} n_trades={best.n_trades} hit={best.hit_rate}")
print(f"  fired {best.n_tickers_fired}/{best.n_tickers_in_basket} tickers")
print(f"  SR0(noise benchmark)={d.expected_max_sharpe_noise_annualized} sigma_SR={d.sigma_sr_annualized}")

print("\nTOP 12 BY DSR:")
for r in sorted(results, key=lambda r: (r.deflated_sharpe.dsr or 0), reverse=True)[:12]:
    d = r.deflated_sharpe
    print(f"  {r.pattern_id[:50]:50s} tf={r.timeframe:3s} sharpe={r.sharpe_annualized:+.3f} dsr={d.dsr:.3e} psr0={d.psr_vs_zero:.4f} trades={r.n_trades} hit={r.hit_rate:.3f}")

print("\nPER-FAMILY (mean sharpe, n, best):")
fam = defaultdict(list)
for r in results:
    fam[(r.family, r.timeframe)].append(r.sharpe_annualized)
for (f, tf), sh in sorted(fam.items(), key=lambda kv: -max(kv[1])):
    print(f"  {f[:40]:40s} {tf:3s} n={len(sh):3d} mean={np.mean(sh):+.2f} best={max(sh):+.2f}")

# Cost-drag signature: day-of-week long/short pair sums (a real directional
# edge would make pairs asymmetric; symmetric negative sums = pure cost).
print("\nDAY-OF-WEEK PAIR SUMS (cost-drag signature check):")
by_id = {r.pattern_id: r for r in results}
for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
    lo = by_id.get(f"day_of_week_{day}_long")
    sh = by_id.get(f"day_of_week_{day}_short")
    if lo and sh:
        print(f"  {day:10s} long={lo.sharpe_annualized:+.2f} short={sh.sharpe_annualized:+.2f} sum={lo.sharpe_annualized + sh.sharpe_annualized:+.2f}")
print("\nTIME-OF-DAY PAIR SUMS:")
for phase in ("open", "mid_morning", "midday", "power_hour", "close"):
    lo = by_id.get(f"time_of_day_{phase}_long")
    sh = by_id.get(f"time_of_day_{phase}_short")
    if lo and sh:
        print(f"  {phase:12s} long={lo.sharpe_annualized:+.2f} short={sh.sharpe_annualized:+.2f} sum={lo.sharpe_annualized + sh.sharpe_annualized:+.2f}")

# Anything clearing any meaningful bar?
print("\nDSR > 0.5:", [r.pattern_id for r in results if (r.deflated_sharpe.dsr or 0) > 0.5])
print("DSR > 0.05:", [r.pattern_id for r in results if (r.deflated_sharpe.dsr or 0) > 0.05])
print("PSR0 > 0.975 (uncorrected):", [(r.pattern_id, round(r.deflated_sharpe.psr_vs_zero, 4)) for r in results if (r.deflated_sharpe.psr_vs_zero or 0) > 0.975])
