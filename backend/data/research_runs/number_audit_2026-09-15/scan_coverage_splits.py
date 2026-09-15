"""Two checks: (1) does _coverage.json match the delivered data? (2) are split flags usable?"""
import gzip, os, json, statistics
from collections import defaultdict

ROOT = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1"
cov = json.load(open(os.path.join(ROOT, "_coverage.json")))
syms = sorted(f[:-7] for f in os.listdir(ROOT) if f.endswith(".csv.gz"))

mismatch_start = mismatch_end = exact = 0
worst = []
split_rows = []          # (ratio_observed, split_flag)
flagged_jumps = unflagged_jumps = 0
unflagged_round = 0

for s in syms:
    with gzip.open(os.path.join(ROOT, s + ".csv.gz"), "rt") as fh:
        hdr = fh.readline().rstrip("\n").split(",")
        i = {c: k for k, c in enumerate(hdr)}
        first = last = None
        prev = None
        for line in fh:
            p = line.rstrip("\n").split(",")
            if len(p) < 6: continue
            d = p[i["date"]]
            if first is None: first = d
            last = d
            try:
                c = float(p[i["close"]]); sp = float(p[i["split"]])
            except (ValueError, KeyError):
                prev = None; continue
            if prev and prev > 0 and c > 0:
                r = c / prev
                if r > 1.8 or r < 0.556:
                    if sp not in (0.0, 1.0):
                        flagged_jumps += 1
                        split_rows.append((r, sp))
                    else:
                        unflagged_jumps += 1
                        # "round" ratio => likely an unflagged split
                        for k in (2,3,4,5,6,8,10,12,15,20,25,30,40,50,100):
                            if abs(r - k) / k < 0.03 or abs(r - 1.0/k) * k < 0.03:
                                unflagged_round += 1
                                break
            prev = c
    claim = cov.get(s)
    if not claim:
        continue
    cs, ce = claim[0][0], claim[0][-1]
    if cs == first and ce == last:
        exact += 1
    else:
        if cs != first: mismatch_start += 1
        if ce != last:
            mismatch_end += 1
            if len(worst) < 6:
                worst.append((s, ce, last))

n = len(syms)
print("=== _coverage.json vs delivered data ===")
print(f"  symbols                       : {n:,}")
print(f"  claim matches data exactly    : {exact:,}  ({exact/n*100:.1f}%)")
print(f"  claimed START differs from data: {mismatch_start:,}  ({mismatch_start/n*100:.1f}%)")
print(f"  claimed END   differs from data: {mismatch_end:,}  ({mismatch_end/n*100:.1f}%)")
print("  examples where the claim runs PAST the last real bar:")
for s, ce, last in worst:
    print(f"    {s}: claims through {ce}, last real bar {last}")

print("\n=== split flags ===")
print(f"  big jumps WITH a split flag   : {flagged_jumps:,}")
print(f"  big jumps WITHOUT a split flag: {unflagged_jumps:,}")
print(f"     ...of which a 'round' ratio: {unflagged_round:,}  (likely unflagged splits)")
if split_rows:
    # if the flag is the split factor, observed ratio should be ~ 1/flag
    err = [abs(r * sp - 1.0) for r, sp in split_rows if sp > 0]
    err.sort()
    print(f"  |observed_ratio x split_flag - 1| over {len(err)} flagged jumps:")
    print(f"     median {statistics.median(err):.3f}   p10 {err[len(err)//10]:.3f}   p90 {err[9*len(err)//10]:.3f}")
    close = sum(1 for e in err if e < 0.25)
    print(f"     within 25% of a clean reconciliation: {close}/{len(err)} ({close/len(err)*100:.0f}%)")
