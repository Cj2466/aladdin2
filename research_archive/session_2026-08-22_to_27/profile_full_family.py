"""Measure the REAL per-ticker cost of the full Phase B families on real
cached AAPL bars, and confirm every new family fires somewhere."""

import pickle
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.research_lab.intraday_patterns import (
    FIT_WINDOW_BARS_1MIN,
    FIT_WINDOW_BARS_15MIN,
    PATTERN_FAMILY_PHASE_B_1MIN,
    PHASE_B_ADDITIONS_15MIN,
    backtest_patterns_for_ticker,
)

CACHE = Path("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/bars_cache")

m15 = pickle.loads((CACHE / "AAPL_15Min.pkl").read_bytes())
m1 = pickle.loads((CACHE / "AAPL_1Min.pkl").read_bytes())

# 15Min: the NEW additions only (the base 212's cost is already known from
# the previous 43.7-min run's arithmetic; the additions carry the unknown
# EWM/rolling costs).
t0 = time.time()
stats15 = backtest_patterns_for_ticker(m15, PHASE_B_ADDITIONS_15MIN, FIT_WINDOW_BARS_15MIN)
dt15 = time.time() - t0
fired15 = Counter()
for spec in PHASE_B_ADDITIONS_15MIN:
    s = stats15.get(spec.pattern_id)
    if s is not None and s.fired:
        fired15[spec.family] += 1
print(f"15Min additions: {len(PHASE_B_ADDITIONS_15MIN)} patterns x {len(m15)} bars in {dt15:.0f}s "
      f"({dt15/len(PHASE_B_ADDITIONS_15MIN):.2f} s/pattern)")
print("fired by family (15Min additions):", dict(fired15))
families15 = {s.family for s in PHASE_B_ADDITIONS_15MIN}
print("families with zero fires (15Min):", families15 - set(fired15))

# 1Min: full subfamily on a 1/4 slice for timing, then fire-check on full.
slice1 = m1.iloc[:50000]
t0 = time.time()
stats1 = backtest_patterns_for_ticker(slice1, PATTERN_FAMILY_PHASE_B_1MIN, FIT_WINDOW_BARS_1MIN)
dt1 = time.time() - t0
per_step = dt1 / (len(PATTERN_FAMILY_PHASE_B_1MIN) * (len(slice1) - FIT_WINDOW_BARS_1MIN))
fired1 = Counter()
for spec in PATTERN_FAMILY_PHASE_B_1MIN:
    s = stats1.get(spec.pattern_id)
    if s is not None and s.fired:
        fired1[spec.family] += 1
print(f"1Min family: {len(PATTERN_FAMILY_PHASE_B_1MIN)} patterns x {len(slice1)} bars in {dt1:.0f}s "
      f"({per_step*1e6:.0f} us/step)")
print("fired by family (1Min, 50k-bar slice):", dict(fired1))
families1 = {s.family for s in PATTERN_FAMILY_PHASE_B_1MIN}
print("families with zero fires (1Min slice):", families1 - set(fired1))
