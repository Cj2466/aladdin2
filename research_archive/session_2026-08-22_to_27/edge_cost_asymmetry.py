import sys
sys.path.insert(0, ".")
import pandas as pd
from app.services.research_lab.engine import step_one_day, WalkForwardState, WalkForwardConfig, StrategyFit
from app.services.research_lab.intraday_patterns import realize_pattern_return, apply_pattern_signal_rule

config = WalkForwardConfig(fit_window_days=5, entry_z=0.0, exit_z=0.0, cost_bps=10.0)
day_row = pd.Series({"ret": 0.01})
window = pd.DataFrame({"close": [1,2,3]})

def make_fit_fn(weight):
    return lambda w: StrategyFit(is_valid=True, z_score=1.0, fit_quality=None, params={"weight_magnitude": weight})

state0 = WalkForwardState(position=0, equity=1.0)

state_a, day_a, _ = step_one_day(window, day_row, make_fit_fn(1.0), realize_pattern_return, state0, config,
                                  decide_position_fn=apply_pattern_signal_rule, direction_labels=("long","short"))
state_b, day_b, _ = step_one_day(window, day_row, make_fit_fn(3.0), realize_pattern_return, state0, config,
                                  decide_position_fn=apply_pattern_signal_rule, direction_labels=("long","short"))

print("Scenario A (weight_magnitude=1.0): raw_return=%.6f cost=%.6f net_return=%.6f" % (day_a.raw_return, day_a.cost, day_a.net_return))
print("Scenario B (weight_magnitude=3.0): raw_return=%.6f cost=%.6f net_return=%.6f" % (day_b.raw_return, day_b.cost, day_b.net_return))
print("raw_return scaled 3x as expected:", abs(day_b.raw_return - 3*day_a.raw_return) < 1e-12)
print("cost IDENTICAL despite 3x bet size (the disclosed-in-low_frequency asymmetry):", abs(day_a.cost - day_b.cost) < 1e-12)
