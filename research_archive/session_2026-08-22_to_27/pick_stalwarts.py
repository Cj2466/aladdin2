import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")
from app.services.research_lab.sp500_membership_history import get_universe_over, was_member  # noqa: E402

u = get_universe_over(date(2018, 1, 2), date(2025, 6, 30))
probe = [date(2018, 1, 2), date(2020, 6, 1), date(2022, 6, 1), date(2025, 6, 2)]
stalwarts = [t for t in u if all(was_member(t, d) for d in probe)]
print(len(stalwarts))
print(stalwarts[:70])
