import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
close = pickle.load(open(f"{OUT}/close.pkl", "rb"))["close"]
splits = pickle.load(open(f"{OUT}/splits.pkl", "rb"))["splits"]
shares = pickle.load(open(f"{OUT}/shares.pkl", "rb"))["shares"]

print("=" * 78)
print("1. THE ~2015-10 FLOOR, across the whole real universe")
print("=" * 78)
firsts = pd.Series({t: s.index[0] for t, s in shares.items() if not s.empty})
print(f"tickers with any share history: {len(firsts)} / {len(close.columns)}")
print(f"earliest first-obs: {firsts.min().date()}   latest first-obs: {firsts.max().date()}")
print("first-obs quantiles:", {q: str(firsts.quantile(q).date()) for q in (0.01, 0.05, 0.5, 0.95, 0.99)})
print("first-obs by year:", dict(firsts.groupby(firsts.dt.year).size()))
n_pre = int((firsts < pd.Timestamp("2015-10-01")).sum())
print(f"tickers whose series starts BEFORE 2015-10-01: {n_pre}")

print()
print("=" * 78)
print("2. STEPWISE / UNEVEN DENSITY: observations per year, pooled")
print("=" * 78)
all_dates = pd.DatetimeIndex(np.concatenate([s.index.to_numpy() for s in shares.values() if not s.empty]))
per_year = pd.Series(all_dates).dt.year.value_counts().sort_index()
print("pooled obs per year:", dict(per_year))
print("median obs/ticker/year:")
for yr in range(2015, 2027):
    counts = [int(((s.index.year == yr)).sum()) for s in shares.values() if not s.empty]
    print(f"   {yr}: median={np.median(counts):.0f}  mean={np.mean(counts):.1f}  zero-rows tickers={sum(1 for c in counts if c == 0)}")

print()
print("=" * 78)
print("3. GAP DISTRIBUTION -> what staleness cap costs")
print("=" * 78)
gaps = []
for s in shares.values():
    if len(s) < 2:
        continue
    gaps.append(np.diff(s.index.to_numpy()) / np.timedelta64(1, "D"))
gaps = np.concatenate(gaps)
print(f"n gaps={len(gaps)}  median={np.median(gaps):.0f}d  p90={np.percentile(gaps,90):.0f}d  "
      f"p99={np.percentile(gaps,99):.0f}d  max={gaps.max():.0f}d")
for cap in (130, 200, 300, 400, 500, 730):
    print(f"   gaps exceeding {cap}d: {(gaps > cap).sum()} ({100*(gaps>cap).mean():.2f}%)")

print()
print("=" * 78)
print("4. TERMINAL STALENESS: series that die before the panel ends")
print("=" * 78)
panel_end = close.index[-1]
lasts = pd.Series({t: s.index[-1] for t, s in shares.items() if not s.empty})
dead = (panel_end - lasts).dt.days
print(f"days from last obs to panel end: median={dead.median():.0f}  p90={dead.quantile(0.9):.0f}  max={dead.max():.0f}")
for cap in (200, 400, 730):
    print(f"   tickers whose last obs is >{cap}d before panel end: {(dead > cap).sum()}")
