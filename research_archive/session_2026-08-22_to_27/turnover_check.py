import sys
sys.path.insert(0, ".")
from app.services.research_lab.cross_sectional import _turnover

old_equal = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
# Same 4 members held across reformation, but the magnitude-weighting shifted
# (D's signal got moderately stronger)
new_mild_shift = {"A": 0.15, "B": 0.15, "C": 0.15, "D": 0.55}
# D's signal got MUCH stronger (bigger reformation-to-reformation magnitude change)
new_big_shift = {"A": 0.05, "B": 0.05, "C": 0.05, "D": 0.85}

print("unchanged membership, mild magnitude shift -> turnover:", _turnover(old_equal, new_mild_shift))
print("unchanged membership, big magnitude shift   -> turnover:", _turnover(old_equal, new_big_shift))
print("(old equal-weight convention would have charged exactly 0.0 for an unchanged member list either way)")
print("(intraday/low_frequency's flat position-based cost would likewise charge the SAME cost regardless of this shift's size)")
