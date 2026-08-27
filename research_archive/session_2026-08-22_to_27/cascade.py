import sys, warnings, pickle
sys.path.insert(0, '/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_16c9f152-b0d-1/backend')
warnings.filterwarnings('ignore')
import pandas as pd, numpy as np
from datetime import date, timedelta
from app.services.research_lab import sp500_membership_history as m

close = pickle.load(open('/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/removed_close.pkl','rb'))
close.index = pd.DatetimeIndex(close.index).tz_localize(None)
idx = close.index

ev = m.vendored_events()
removals = [(d, t) for d, a, r in ev for t in r]
print(f'[0] raw removal events                          : {len(removals)}')

# --- filter 1: documented rename artifacts -------------------------------
# 1 add + 1 remove on the date, and the ADDED ticker carries a hand-verified
# earliest-membership override strictly predating the event (the exact
# signature sp500_membership_history documents for its 23 confirmed renames).
OVR = m._EARLIEST_MEMBERSHIP_OVERRIDES
renames = set()
for d, a, r in ev:
    if len(a) == 1 and len(r) == 1:
        add = a[0]
        if add in OVR and date.fromisoformat(OVR[add]) < d:
            renames.add((d, r[0]))
print(f'[1] documented same-date rename artifacts removed: {len(renames)}  -> {len(removals)-len(renames)}')
for d,t in sorted(renames): print(f'      rename: {t} on {d}')
stage1 = [(d,t) for d,t in removals if (d,t) not in renames]

# --- filter 2: ticker resolves on yfinance at all ------------------------
stage2 = [(d,t) for d,t in stage1 if t in close.columns]
print(f'[2] ticker resolves on yfinance                  : {len(stage2)}')

# --- filter 3: non-recycled (real pre-event data inside membership) ------
PRE_WIN = 60; PRE_MIN = 40
stage3 = []
recycled = []
for d, t in stage2:
    pos = idx.searchsorted(pd.Timestamp(d))
    lo = max(0, pos - PRE_WIN)
    pre = close[t].iloc[lo:pos]
    n_pre = int(pre.notna().sum())
    # membership check: those pre-event days must fall inside a real interval
    if n_pre < PRE_MIN:
        recycled.append((d,t,n_pre)); continue
    if not m.was_member(t, (idx[pos-1]).date() if pos>0 else d):
        recycled.append((d,t,-1)); continue
    stage3.append((d,t))
print(f'[3] non-recycled (>={PRE_MIN}/{PRE_WIN} pre-event days, member) : {len(stage3)}')
print(f'      excluded as recycled/thin: {len(recycled)}')
for d,t,n in recycled[:25]: print(f'      {t:6} {d}  pre_days={n}')

# --- filter 4: quotable at entry = effective + 1 trading day -------------
stage4 = []
for d, t in stage3:
    pos = idx.searchsorted(pd.Timestamp(d))       # first trading day >= effective
    entry = pos + 1
    if entry >= len(idx): continue
    if not np.isfinite(close[t].iloc[entry]): continue
    stage4.append((d, t, entry))
print(f'[4] quotable at entry (eff + 1 trading day)      : {len(stage4)}')

# --- post-window survival, per hold ---------------------------------------
for H in (63,126,252):
    surv = sum(1 for d,t,e in stage4
               if e+H < len(idx) and np.isfinite(close[t].iloc[e+H]))
    print(f'      survive a full {H}-day post-window       : {surv}')

# --- independent clusters (>=7 days apart) -------------------------------
dates = sorted({d for d,t,e in stage4})
clusters=1; last=dates[0]
for d in dates[1:]:
    if (d-last).days >= 7: clusters+=1
    last=d
print(f'[5] distinct event DATES                         : {len(dates)}')
print(f'[6] independent clusters (>=7 days apart)        : {clusters}')
print(f'      first / last event date: {dates[0]} / {dates[-1]}')

pickle.dump(stage4, open('/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/usable.pkl','wb'))
