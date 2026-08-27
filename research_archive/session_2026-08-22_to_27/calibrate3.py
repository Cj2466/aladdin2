import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.research_lab.cross_sectional import select_leg_tickers  # noqa: E402
from app.services.research_lab.cross_sectional_buyback import (  # noqa: E402
    BUYBACK_RANK_FRACTION,
    build_point_in_time_share_counts,
)

OUT = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
close = pickle.load(open(f"{OUT}/close.pkl", "rb"))["close"]
splits = pickle.load(open(f"{OUT}/splits.pkl", "rb"))["splits"]
shares = pickle.load(open(f"{OUT}/shares.pkl", "rb"))["shares"]

corrected, _ = build_point_in_time_share_counts(close, shares, splits)
uncorrected, _ = build_point_in_time_share_counts(close, shares, {})  # no split ratios at all

print("=" * 78)
print("E. rankable names at the declared formation start, per lookback")
print("=" * 78)
for lb in (126, 252, 504):
    w = lb + 1
    first = corrected.shift(lb)
    ok = corrected.notna() & first.notna() & (corrected > 0) & (first > 0)
    cov = corrected.notna().rolling(w).sum() >= int(w * 0.8)
    n = (ok & cov).sum(axis=1)
    at = n.loc[n.index >= "2018-01-02"]
    print(f"   lookback={lb}: rankable at {at.index[0].date()} = {int(at.iloc[0])}   "
          f"min over 2018-01-02..end = {int(at.min())} on {at.idxmin().date()}")

print()
print("=" * 78)
print("F. THE GE / ANET SPLIT-CONTAMINATION REGRESSION, on real data")
print("=" * 78)


def issuance_signal(frame, asof, lookback):
    window = frame.loc[:asof].iloc[-(lookback + 1):]
    f, l = window.iloc[0], window.iloc[-1]
    n_obs = window.notna().sum()
    usable = np.isfinite(f) & np.isfinite(l) & (f > 0) & (l > 0) & (
        n_obs >= int((lookback + 1) * 0.8)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        s = -np.log(l / f)
    s = pd.Series(s, index=frame.columns, dtype=float)
    return s.where(usable & np.isfinite(s))


for asof in ("2022-01-14", "2022-03-15", "2022-06-15"):
    for lookback in (252,):
        bad = issuance_signal(uncorrected, asof, lookback)
        good = issuance_signal(corrected, asof, lookback)
        bt, bb = select_leg_tickers(bad, BUYBACK_RANK_FRACTION)
        gt, gb = select_leg_tickers(good, BUYBACK_RANK_FRACTION)
        print(f"\n--- as-of {asof}, lookback {lookback}d, n_ranked bad={bad.notna().sum()} good={good.notna().sum()} ---")
        for t in ("GE", "ANET"):
            def where(tk, top, bottom, sig):
                r = "LONG(top decile)" if tk in top else ("SHORT(bottom decile)" if tk in bottom else "unranked/middle")
                v = sig.get(tk, np.nan)
                rank = int(sig.rank(ascending=False)[tk]) if np.isfinite(v) else -1
                return f"{r} signal={v:+.4f} rank={rank}/{int(sig.notna().sum())}"
            print(f"   {t:5s} UNCORRECTED: {where(t, bt, bb, bad)}")
            print(f"   {t:5s} CORRECTED  : {where(t, gt, gb, good)}")

print()
print("=" * 78)
print("G. how many names change decile because of the split correction (whole replay)")
print("=" * 78)
dates = pd.date_range("2018-01-02", close.index[-1], freq="126D")
tot_moved = 0
tot_names = 0
for d in dates:
    d = close.index[close.index.searchsorted(d)] if d <= close.index[-1] else None
    if d is None:
        continue
    bad = issuance_signal(uncorrected, d, 252)
    good = issuance_signal(corrected, d, 252)
    bt, bb = select_leg_tickers(bad, BUYBACK_RANK_FRACTION)
    gt, gb = select_leg_tickers(good, BUYBACK_RANK_FRACTION)
    moved = (set(bt) ^ set(gt)) | (set(bb) ^ set(gb))
    tot_moved += len(moved)
    tot_names += len(bt) + len(bb)
    if moved:
        print(f"   {d.date()}: {len(moved)} leg-membership differences (legs of {len(bt)}); e.g. {sorted(moved)[:8]}")
print(f"   TOTAL leg-slot differences across {len(dates)} formations: {tot_moved} of {tot_names} slots")
