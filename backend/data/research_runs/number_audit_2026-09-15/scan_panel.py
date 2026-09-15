"""Full integrity scan of the whole-market Alpaca panel (2026-09-15)."""
import gzip, os, math, sys, json
from collections import defaultdict

ROOT = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1"
TODAY = "2026-09-15"

counts = defaultdict(int)
bad = defaultdict(list)
total_rows = 0
files = sorted(f for f in os.listdir(ROOT) if f.endswith(".csv.gz"))
other = [f for f in os.listdir(ROOT) if not f.endswith(".csv.gz")]
first_date, last_date = "9999", "0000"
split_nonzero = 0
div_nonzero = 0
jump_no_split = defaultdict(int)

for fn in files:
    sym = fn[:-7]
    try:
        with gzip.open(os.path.join(ROOT, fn), "rt") as fh:
            hdr = fh.readline().rstrip("\n").split(",")
            idx = {c: i for i, c in enumerate(hdr)}
            seen = set()
            prev_date = ""
            prev_close = None
            n = 0
            for line in fh:
                p = line.rstrip("\n").split(",")
                if len(p) < 6:
                    counts["malformed_row"] += 1
                    continue
                d = p[idx["date"]]
                n += 1
                if d in seen:
                    counts["duplicate_date"] += 1
                    if len(bad["duplicate_date"]) < 5: bad["duplicate_date"].append(f"{sym} {d}")
                seen.add(d)
                if d < prev_date:
                    counts["out_of_order"] += 1
                    if len(bad["out_of_order"]) < 5: bad["out_of_order"].append(f"{sym} {d}")
                prev_date = d
                if d > TODAY:
                    counts["future_date"] += 1
                    if len(bad["future_date"]) < 5: bad["future_date"].append(f"{sym} {d}")
                if d < first_date: first_date = d
                if d > last_date: last_date = d
                try:
                    o, h, l, c = (float(p[idx[k]]) for k in ("open","high","low","close"))
                    v = float(p[idx["volume"]])
                except ValueError:
                    counts["unparseable_price"] += 1
                    continue
                if min(o,h,l,c) <= 0:
                    counts["nonpositive_price"] += 1
                    if len(bad["nonpositive_price"]) < 5: bad["nonpositive_price"].append(f"{sym} {d}")
                if h < l:
                    counts["high_lt_low"] += 1
                    if len(bad["high_lt_low"]) < 5: bad["high_lt_low"].append(f"{sym} {d}")
                if c > h or c < l or o > h or o < l:
                    counts["ohlc_inconsistent"] += 1
                    if len(bad["ohlc_inconsistent"]) < 5: bad["ohlc_inconsistent"].append(f"{sym} {d}")
                if v < 0:
                    counts["negative_volume"] += 1
                if "split" in idx:
                    try:
                        s = float(p[idx["split"]])
                        if s not in (0.0, 1.0): split_nonzero += 1
                    except ValueError: pass
                if "dividend" in idx:
                    try:
                        if float(p[idx["dividend"]]) != 0.0: div_nonzero += 1
                    except ValueError: pass
                # unadjusted-split detector: >45% single-day move with no split flag
                if prev_close and prev_close > 0 and c > 0:
                    r = c / prev_close
                    if (r > 1.8 or r < 0.556):
                        s = 0.0
                        if "split" in idx:
                            try: s = float(p[idx["split"]])
                            except ValueError: pass
                        if s in (0.0, 1.0):
                            jump_no_split[sym] += 1
                            counts["big_jump_no_split_flag"] += 1
                prev_close = c
            total_rows += n
            if n == 0:
                counts["empty_file"] += 1
                if len(bad["empty_file"]) < 5: bad["empty_file"].append(sym)
    except Exception as e:
        counts["read_error"] += 1
        if len(bad["read_error"]) < 5: bad["read_error"].append(f"{sym}: {e}")

print(f"symbol files      : {len(files)}")
print(f"non-csv entries   : {other}")
print(f"total data rows   : {total_rows:,}")
print(f"date range        : {first_date} -> {last_date}")
print(f"rows w/ split flag set   : {split_nonzero:,}")
print(f"rows w/ dividend nonzero : {div_nonzero:,}")
print("--- defects ---")
for k in sorted(counts):
    print(f"  {k:26s}: {counts[k]:,}")
    for ex in bad.get(k, [])[:3]:
        print(f"      e.g. {ex}")
top = sorted(jump_no_split.items(), key=lambda kv: -kv[1])[:10]
print("--- worst unadjusted-jump symbols ---")
for s, n in top:
    print(f"  {s}: {n} jumps >45% with no split flag")
