import sys

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_ea27d8f0-500-1/backend")
from app.services.research_lab.sp500_membership_history import (  # noqa: E402
    _BASE_UNIVERSE,
    earliest_membership_date,
    vendored_events,
)

events = vendored_events()
base = set(_BASE_UNIVERSE)

first_removal = {}
for eff, added, removed in events:
    for t in removed:
        first_removal.setdefault(t, eff)

add_dates = {}
rem_dates = {}
for eff, added, removed in events:
    for t in added:
        add_dates.setdefault(t, []).append(eff)
    for t in removed:
        rem_dates.setdefault(t, []).append(eff)

# --- rule 1: the override layer says this "addition" is a symbol change ---
rule1 = []
for eff, added, removed in events:
    for s in added:
        em = earliest_membership_date(s)
        prior_removal = first_removal.get(s) is not None and first_removal[s] < eff
        if em is not None and em < eff and s not in base and not prior_removal:
            rule1.append((eff, s, em, removed))
print("RULE1 rename-successor additions:", len(rule1))
multi = [x for x in rule1 if len(x[3]) != 1]
print("  not paired 1-to-1 with exactly one removal:", len(multi))
for x in multi:
    print("   ", x)
print("  sample:", rule1[:5])

# --- rule 2: symbol round-trip ---
rt = []
for eff, added, removed in events:
    for r in removed:
        for s in added:
            common = set(add_dates.get(r, [])) & set(rem_dates.get(s, []))
            for d2 in common:
                if d2 > eff:
                    rt.append((eff, r, s, d2))
print("RULE2 symbol round-trips:", rt)

r1_removals = set()
for eff, s, em, removed in rule1:
    for r in removed:
        r1_removals.add((r, eff))
r2_removals = set()
for eff, r, s, d2 in rt:
    r2_removals.add((r, eff))
    r2_removals.add((s, d2))
all_rename = r1_removals | r2_removals
print("total removals flagged as rename artifacts:", len(all_rename))
total_removals = sum(len(r) for _, _, r in events)
print("total removals:", total_removals, "-> non-rename:", total_removals - len(all_rename))
print("flagged:", sorted((t, d.isoformat()) for t, d in all_rename))
