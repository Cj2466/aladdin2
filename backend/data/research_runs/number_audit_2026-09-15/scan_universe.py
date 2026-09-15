"""What is actually IN the panel? Warrants/units/preferreds vs common stock."""
import gzip, os, re, json
from collections import defaultdict

ROOT = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1"
syms = sorted(f[:-7] for f in os.listdir(ROOT) if f.endswith(".csv.gz"))

def classify(s):
    if len(s) == 5 and s.endswith("W"):  return "warrant (5-letter -W)"
    if s.endswith("WW"):                 return "warrant (-WW)"
    if len(s) == 5 and s.endswith("U"):  return "unit (5-letter -U)"
    if len(s) == 5 and s.endswith("R"):  return "right (5-letter -R)"
    if len(s) == 5 and s[-1] in "PQ":    return "preferred-ish (5-letter -P/-Q)"
    if len(s) == 5:                      return "5-letter other"
    if len(s) <= 4:                      return "plain 1-4 letter"
    return "6+ letter"

buckets = defaultdict(list)
for s in syms:
    buckets[classify(s)].append(s)

print("=== universe composition ===")
tot = len(syms)
for k in sorted(buckets, key=lambda k: -len(buckets[k])):
    v = buckets[k]
    print(f"  {k:28s}: {len(v):6,d}  ({len(v)/tot*100:5.1f}%)   e.g. {', '.join(v[:4])}")

# re-run the jump detector ONLY on plain 1-4 letter tickers
plain = set(buckets["plain 1-4 letter"])
jumps = defaultdict(int)
rows = 0
for s in plain:
    with gzip.open(os.path.join(ROOT, s + ".csv.gz"), "rt") as fh:
        hdr = fh.readline().rstrip("\n").split(",")
        i = {c: k for k, c in enumerate(hdr)}
        prev = None
        for line in fh:
            p = line.rstrip("\n").split(",")
            if len(p) < 6: continue
            rows += 1
            try:
                c = float(p[i["close"]]); sp = float(p[i["split"]])
            except (ValueError, KeyError):
                continue
            if prev and prev > 0 and c > 0:
                r = c / prev
                if (r > 1.8 or r < 0.556) and sp in (0.0, 1.0):
                    jumps[s] += 1
            prev = c

print(f"\n=== plain 1-4 letter tickers only: {len(plain):,} symbols, {rows:,} rows ===")
print(f"  big jumps (>45%) with no split flag: {sum(jumps.values()):,} "
      f"across {len(jumps):,} symbols")
top = sorted(jumps.items(), key=lambda kv: -kv[1])[:12]
for s, n in top:
    print(f"    {s}: {n}")

cov = json.load(open(os.path.join(ROOT, "_coverage.json")))
print(f"\n=== _coverage.json ===\n  keys: {list(cov)[:10] if isinstance(cov, dict) else type(cov)}")
if isinstance(cov, dict):
    for k in list(cov)[:6]:
        v = cov[k]
        print(f"  {k}: {str(v)[:120]}")
