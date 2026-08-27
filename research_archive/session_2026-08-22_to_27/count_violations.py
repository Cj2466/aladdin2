import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")
import random
from app.services.research_lab.cross_sectional import _apply_weight_cap, MAX_WEIGHT_MULTIPLE

random.seed(42)
n_trials = 2000
n_violations = 0
worst_excess = 0.0
for trial in range(n_trials):
    n = random.randint(2, 12)
    tickers = [f"T{i}" for i in range(n)]
    raw = {t: random.choice([
        random.uniform(1, 10),
        random.uniform(1000, 1_000_000),
        random.uniform(0.0001, 0.01),
    ]) for t in tickers}
    weights = _apply_weight_cap(raw)
    equal_share = 1.0 / n
    cap = MAX_WEIGHT_MULTIPLE * equal_share
    trial_viol = max((w - cap for w in weights.values()), default=0.0)
    if trial_viol > 1e-9:
        n_violations += 1
        worst_excess = max(worst_excess, trial_viol)

print(f"{n_violations}/{n_trials} random legs ended with a cap violation")
print(f"worst excess over cap seen: {worst_excess:.6f}")
