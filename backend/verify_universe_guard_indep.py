"""Does the sample-fingerprint guard fire ONLY on the thing it is for?

A false positive here would be an own-goal far worse than the risk it closes:
MembershipRefreshRunner ticks daily in production, and if a refresh tripped the
guard, BOTH registrations would stop accumulating forward days from the first
day the runner succeeded, silently, forever.
"""

from datetime import date, timedelta

from app.services.research_lab import cross_sectional_forward_registry as reg
from app.services.research_lab import sp500_membership_history as memb
from app.services.research_lab.cross_sectional_quality import build_quality_sample

fails = 0


def check(label, cond, detail=""):
    global fails
    fails += not cond
    print(f"{'PASS' if cond else '**FAIL**'}  {label}  {detail}")


def sample_now():
    return build_quality_sample(memb.MEMBERSHIP_DATA_START, memb.MEMBERSHIP_DATA_AS_OF)


def guard_fires() -> bool:
    s, n = sample_now()
    try:
        reg._assert_sample_is_the_registered_one(s, n)
        return False
    except reg.CrossSectionalUniverseDriftError:
        return True


print("baseline (vendored literals only, no extension applied)")
check("guard is silent", not guard_fires(), f"coverage_end={memb.membership_coverage_end()}")

print()
print("A. A LIVE MEMBERSHIP REFRESH -- the daily production case. Must NOT fire.")
for label, ext in (
    ("dated upstream events + advanced coverage_end", memb.MembershipExtension(
        coverage_end=memb.MEMBERSHIP_DATA_AS_OF + timedelta(days=60),
        events=(
            (memb.MEMBERSHIP_DATA_AS_OF + timedelta(days=10), ("NEWCO", "OTHERCO"), ("AAPL",)),
            (memb.MEMBERSHIP_DATA_AS_OF + timedelta(days=40), ("THIRDCO",), ("MSFT",)),
        ),
        sources=("verifier",))),
    ("undated live-source additions past coverage_end", memb.MembershipExtension(
        coverage_end=memb.MEMBERSHIP_DATA_AS_OF,
        events=((memb.MEMBERSHIP_DATA_AS_OF + timedelta(days=90), ("LATECO",), ()),),
        live_members=frozenset({"AAPL"}), live_as_of=date.today(), sources=("verifier",))),
    ("an earliest_overrides rename correction", memb.MembershipExtension(
        coverage_end=memb.MEMBERSHIP_DATA_AS_OF,
        earliest_overrides=(("AAPL", date(2015, 1, 8)),), sources=("verifier",))),
    ("all three at once", memb.MembershipExtension(
        coverage_end=memb.MEMBERSHIP_DATA_AS_OF + timedelta(days=60),
        events=((memb.MEMBERSHIP_DATA_AS_OF + timedelta(days=10), ("NEWCO",), ("AAPL",)),),
        earliest_overrides=(("MSFT", date(2015, 1, 8)),),
        live_members=frozenset({"NEWCO"}), live_as_of=date.today(), sources=("verifier",))),
):
    memb.apply_membership_extension(ext)
    try:
        s, n = sample_now()
        check(f"  refresh: {label}", not guard_fires(),
              f"coverage_end -> {memb.membership_coverage_end()}, union still {n}, sample {len(s)}")
    finally:
        memb.clear_membership_extension()

print()
print("B. A RE-VENDORING of the literals -- the residual the guard exists for. MUST fire.")
orig_as_of = memb.MEMBERSHIP_DATA_AS_OF
orig_events = memb._EVENTS
try:
    # Exactly what a re-vendoring does: move the coverage constant forward and
    # append the newly-vendored dated events inside the new window.
    new_as_of = orig_as_of + timedelta(days=120)
    memb.MEMBERSHIP_DATA_AS_OF = new_as_of
    memb._EVENTS = orig_events + ((orig_as_of + timedelta(days=30), ("REVENDORED",), ()),)
    memb._STATE = memb._build_state(None)
    reg.MEMBERSHIP_DATA_AS_OF = new_as_of  # the registry imported the name by value
    s, n = sample_now()
    fired = guard_fires()
    check("  re-vendored literals are caught", fired,
          f"union {n} (was 768), sample overlap with registered = "
          f"{len(set(s) & set(build_quality_sample(memb.MEMBERSHIP_DATA_START, orig_as_of)[0]))}/200")
finally:
    memb.MEMBERSHIP_DATA_AS_OF = orig_as_of
    memb._EVENTS = orig_events
    memb._STATE = memb._build_state(None)
    reg.MEMBERSHIP_DATA_AS_OF = orig_as_of

check("guard silent again after restore", not guard_fires(), "")

print()
print("=" * 70)
print(f"{'ALL CHECKS PASSED' if not fails else f'{fails} CHECK(S) FAILED'}")
print("=" * 70)
