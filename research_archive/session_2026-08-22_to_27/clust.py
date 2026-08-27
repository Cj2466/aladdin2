import json, warnings, sys
warnings.filterwarnings('ignore')
SP='/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/'
res=json.load(open(SP+'surv.json'))
sv=[x for x in res if x['status']=='survivor']
from collections import Counter
d=Counter(x['eff'] for x in sv)
print('survivor events', len(sv), 'distinct dates', len(d), 'max per date', max(d.values()))
print('per-year:', sorted(Counter(x['eff'][:4] for x in sv).items()))
# cluster within 5 business days
import datetime as dt
dates=sorted({dt.date.fromisoformat(k) for k in d})
clusters=[]; cur=[dates[0]]
for a,b in zip(dates, dates[1:]):
    if (b-a).days<=7: cur.append(b)
    else: clusters.append(cur); cur=[b]
clusters.append(cur)
print('n clusters (<=7d apart):', len(clusters))
sys.stdout.flush()
