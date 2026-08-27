import sys
sys.path.insert(0, ".")
import math
import numpy as np
from app.services.research_lab.intraday_patterns import (
    _signal_weight_magnitude, PatternSpec, PatternSignal, MAX_WEIGHT_MULTIPLE
)

def spec(strength_scale=None, strength_is_margin=False):
    return PatternSpec(pattern_id="t", family="t", citation="t", fire_fn=lambda w: None,
                        strength_scale=strength_scale, strength_is_margin=strength_is_margin)

print("MAX_WEIGHT_MULTIPLE =", MAX_WEIGHT_MULTIPLE)

# Edge 1: NaN strength (e.g. an upstream computation glitch) -- does the cap actually catch it?
s = spec(strength_scale=0.004)
w = _signal_weight_magnitude(PatternSignal(direction="long", strength=float("nan")), s)
print("EDGE 1 (NaN strength, raw style):", w, "is_nan:", math.isnan(w) if isinstance(w,float) else "?")

# Edge 2: negative strength (raw style) -- can weight go negative/dodge the intended [0,MAX] band silently?
w2 = _signal_weight_magnitude(PatternSignal(direction="long", strength=-5.0), s)
print("EDGE 2 (negative strength, raw style, scale=0.004):", w2)

# Edge 3: negative strength_scale (not just zero) -- guard says <=0 so should still flatten
s3 = spec(strength_scale=-20.0, strength_is_margin=True)
w3 = _signal_weight_magnitude(PatternSignal(direction="short", strength=500.0), s3)
print("EDGE 3 (negative strength_scale=-20, huge strength):", w3)

# Edge 4: margin style with strength very negative (deep below its own boundary -- should never
# structurally happen since fire_fn gates on crossing, but what does the function itself do if
# called with an out-of-contract negative margin?)
s4 = spec(strength_scale=20.0, strength_is_margin=True)
w4 = _signal_weight_magnitude(PatternSignal(direction="short", strength=-100.0), s4)
print("EDGE 4 (margin style, strength=-100 < -scale, i.e. magnitude negative):", w4)

# Edge 5: extreme outlier beyond float overflow territory
s5 = spec(strength_scale=0.004)
w5 = _signal_weight_magnitude(PatternSignal(direction="long", strength=1e308), s5)
print("EDGE 5 (strength=1e308, scale=0.004 -> ratio overflow):", w5)

# Edge 6: strength_scale is a tiny positive denormal float (near-zero but not caught by <=0 guard)
s6 = spec(strength_scale=1e-310)
w6 = _signal_weight_magnitude(PatternSignal(direction="long", strength=1e-300), s6)
print("EDGE 6 (strength_scale=1e-310 denormal, strength=1e-300):", w6)

# Edge 7: NaN strength_scale itself (defensive -- should the <=0 check even catch NaN?)
s7 = spec(strength_scale=float("nan"))
w7 = _signal_weight_magnitude(PatternSignal(direction="long", strength=5.0), s7)
print("EDGE 7 (strength_scale=NaN):", w7, "nan<=0 is:", float("nan") <= 0)
