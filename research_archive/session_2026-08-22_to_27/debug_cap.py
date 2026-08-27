import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")
import random
from app.services.research_lab.cross_sectional import _apply_weight_cap, MAX_WEIGHT_MULTIPLE

random.seed(42)
for trial in range(1):
    n = random.randint(2, 12)
    tickers = [f"T{i}" for i in range(n)]
    raw = {t: random.choice([
        random.uniform(1, 10),
        random.uniform(1000, 1_000_000),
        random.uniform(0.0001, 0.01),
    ]) for t in tickers}
    print("n =", n)
    print("raw =", raw)
    weights = _apply_weight_cap(dict(raw))
    print("weights =", weights)
    print("sum =", sum(weights.values()))
    equal_share = 1.0/n
    cap = MAX_WEIGHT_MULTIPLE*equal_share
    print("cap =", cap)
    for t,w in weights.items():
        if w > cap:
            print(f"  VIOLATION {t}: {w} > {cap}  (excess={w-cap})")
