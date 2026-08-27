import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
from app.services.research_lab.low_frequency_patterns import (
    build_hold_and_magnitude_from_events, _daily_hold_to_bar_magnitude, MAX_WEIGHT_MULTIPLE
)

print("MAX_WEIGHT_MULTIPLE =", MAX_WEIGHT_MULTIPLE)

# Edge 1: all-zero event_dir (no signals ever fire) -> hold all 0, magnitude all 1.0 (flat/no bet)
n = 10
event_dir = np.zeros(n, dtype=np.int8)
event_ratio = np.zeros(n, dtype=np.float64)  # deliberately NOT pre-clipped/defaulted by caller
hold, mag = build_hold_and_magnitude_from_events(event_dir, event_ratio, hold_days=3)
print("EDGE 1 (all-zero events): hold=", hold.tolist(), "mag=", mag.tolist())

# Edge 2: overlapping holds where the SECOND (later) event has a smaller magnitude than the first --
# does magnitude correctly follow "most-recent-event-wins" the same as direction, or can a hold window
# end up carrying a STALE (overridden) direction paired with the NEW event's magnitude or vice versa
# (a direction/magnitude mismatch bug)?
event_dir2 = np.array([1, 0, -1, 0, 0, 0, 0, 0, 0, 0], dtype=np.int8)
event_ratio2 = np.array([3.0, 0, 1.2, 0, 0, 0, 0, 0, 0, 0], dtype=np.float64)  # event0: dir=+1,ratio=3.0 (big); event2: dir=-1,ratio=1.2 (small)
hold2, mag2 = build_hold_and_magnitude_from_events(event_dir2, event_ratio2, hold_days=5)
print("EDGE 2 (overlapping holds, later event overrides earlier one):")
print("  hold=", hold2.tolist())
print("  mag =", mag2.tolist())
# event0 fires at i=0 -> sets days 1..5 to (dir=+1, ratio=3.0)
# event2 fires at i=2 -> sets days 3..7 to (dir=-1, ratio=1.2), OVERRIDING days 3,4,5 from event0
# Correct expectation: day1=+1/3.0, day2=+1/3.0, day3..7=-1/1.2 (direction AND magnitude both from event2)
expected_hold = [0,1,1,-1,-1,-1,-1,-1,0,0]
expected_mag  = [1,3.0,3.0,1.2,1.2,1.2,1.2,1.2,1,1]
print("  expected hold=", expected_hold)
print("  expected mag =", expected_mag)
print("  MATCH:", hold2.tolist()==expected_hold and mag2.tolist()==expected_mag)

# Edge 3: caller passes an out-of-band event_ratio (e.g. 999.0, NOT pre-clipped to MAX_WEIGHT_MULTIPLE=3.0)
# -- does build_hold_and_magnitude_from_events itself enforce the cap, or trust the caller blindly?
event_dir3 = np.array([1,0,0], dtype=np.int8)
event_ratio3 = np.array([999.0, 0, 0], dtype=np.float64)
hold3, mag3 = build_hold_and_magnitude_from_events(event_dir3, event_ratio3, hold_days=2)
print("EDGE 3 (unclipped 999x magnitude passed directly, cap NOT re-enforced here):")
print("  hold=", hold3.tolist(), "mag=", mag3.tolist(), " -- cap breached:", any(m > MAX_WEIGHT_MULTIPLE for m in mag3))

# Edge 4: NaN inside daily_magnitude Series fed to _daily_hold_to_bar_magnitude directly
# (not routed through one of the guarded _xxx_ratio builders -- exercising the raw utility fn's own contract)
daily_mag = pd.Series([1.0, float("nan"), 2.5], index=pd.to_datetime(["2024-01-01","2024-01-02","2024-01-03"]))
bar_dates = np.array(pd.to_datetime(["2024-01-01","2024-01-01","2024-01-02","2024-01-02","2024-01-03","2024-01-03"]))
result = _daily_hold_to_bar_magnitude(daily_mag, bar_dates)
print("EDGE 4 (NaN inside daily_magnitude fed to the raw utility directly):", result.tolist())
