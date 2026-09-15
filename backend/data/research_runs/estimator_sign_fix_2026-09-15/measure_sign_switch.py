"""Same-day baseline for the sign-mode switch (2026-09-15).

Two questions, answered on ONE data build (the project's rule that a cost arm is
only meaningful next to a baseline built on the same inputs it saw):

  Q1 Does the edit change what the LIVE lazy_prices registration computes?
     It calls build_calibrated_half_spread_frame, which already passes
     sign=CALIBRATED_SIGN_MODE explicitly, so it should be byte-identical.
     Proven here rather than asserted.

  Q2 What does it change for the four research families still on
     build_edge_half_spread_frame (ipo_lockup_expiration, jump_drift,
     eigenportfolio, patterns)?

`sign=False` folds the estimator's noise into a positive number via abs();
`sign=True` lets it go negative, and the existing `.where(result > 0.0)` then
NaNs those cells -- which the harness ALREADY handles by falling back to the
flat cost_bps and counting the fallback per formation (never silent). So the
downstream contract does not change; only the fabrication is removed.
"""
import gzip, os, sys, csv
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/"
                   "estimator-sign-fix-2026-09-15/backend")
from bidask import edge_rolling                                   # noqa: E402
from app.services.research_lab.spread_estimator import (          # noqa: E402
    build_edge_half_spread_frame, build_calibrated_half_spread_frame,
    COST_MODEL_WINDOW_DAYS,
)

STORE = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1"
UNIV = ("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/research_runs/"
        "a2_universe_2026-09-15/clean_universe.csv")
START = "2024-01-01"


def panel(symbols):
    frames = {}
    for s in symbols:
        rows = []
        with gzip.open(os.path.join(STORE, s + ".csv.gz"), "rt") as fh:
            for r in csv.DictReader(fh):
                if r["date"] < START:
                    continue
                try:
                    rows.append((r["date"], float(r["open"]), float(r["high"]),
                                 float(r["low"]), float(r["close"])))
                except ValueError:
                    continue
        if len(rows) > COST_MODEL_WINDOW_DAYS + 40:
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])
            df["date"] = pd.to_datetime(df["date"])
            frames[s] = df.set_index("date")
    idx = None
    for f in frames.values():
        idx = f.index if idx is None else idx.intersection(f.index)
    out = {}
    for col in ("open", "high", "low", "close"):
        out[col] = pd.DataFrame({s: f.loc[idx, col] for s, f in frames.items()}, index=idx)
    return out


def main():
    rows = [r for r in csv.DictReader(open(UNIV))
            if r["instrument"] == "common" and r["last_bar"] >= "2026-09-01"
            and int(r["rows"]) > 1500]
    rows.sort(key=lambda r: r["symbol"])
    sample = [r["symbol"] for r in rows][:160]
    p = panel(sample)
    print(f"panel: {p['close'].shape[1]} tickers x {p['close'].shape[0]} days "
          f"({p['close'].index[0].date()} -> {p['close'].index[-1].date()})")

    # ---- Q2: the raw (uncalibrated) frame, both modes, same data ----
    def raw(sign):
        cols = {}
        for t in p["close"].columns:
            ohlc = pd.DataFrame({k: p[k][t] for k in ("open", "high", "low", "close")})
            cols[t] = edge_rolling(ohlc, window=COST_MODEL_WINDOW_DAYS, sign=sign) / 2.0
        fr = pd.DataFrame(cols, index=p["close"].index)
        return fr.where(fr > 0.0)

    before, after = raw(False), raw(True)
    live = build_edge_half_spread_frame(p["open"], p["high"], p["low"], p["close"])
    same_as_before = bool(np.allclose(live.to_numpy(dtype=float),
                                      before.to_numpy(dtype=float), equal_nan=True))
    same_as_after = bool(np.allclose(live.to_numpy(dtype=float),
                                     after.to_numpy(dtype=float), equal_nan=True))
    print(f"\nmodule's build_edge_half_spread_frame == sign=False arm: {same_as_before}")
    print(f"module's build_edge_half_spread_frame == sign=True  arm: {same_as_after}")

    tot = before.size
    for name, fr in (("sign=False (current)", before), ("sign=True (proposed)", after)):
        v = pd.Series(fr.to_numpy(dtype=float).ravel()).dropna()
        print(f"  {name:22s}: {len(v):7,d}/{tot:,} cells charged ({len(v)/tot*100:5.1f}%)  "
              f"median {v.median()*1e4:7.2f} bp  p90 {v.quantile(0.9)*1e4:7.2f} bp")
    dropped = int((before.notna() & after.isna()).to_numpy().sum())
    print(f"  cells that become NaN (-> flat cost_bps fallback): {dropped:,} "
          f"({dropped/tot*100:.1f}% of all cells)")
    both = before.notna() & after.notna()
    d = (after.where(both) - before.where(both))
    dv = pd.Series(d.to_numpy(dtype=float).ravel()).dropna()
    print(f"  on cells charged under BOTH: median change {dv.median()*1e4:+.2f} bp")
    gone = before.where(before.notna() & after.isna())
    gv = pd.Series(gone.to_numpy(dtype=float).ravel()).dropna()
    print(f"  the WITHDRAWN cells were being charged: median {gv.median()*1e4:7.2f} bp, "
          f"p25 {gv.quantile(0.25)*1e4:6.2f}, p75 {gv.quantile(0.75)*1e4:7.2f}")
    print(f"     -> they now fall back to the flat cost_bps instead")

    # ---- Q1: the calibrated frame, which the live registration uses ----
    cal, rep = build_calibrated_half_spread_frame(p["open"], p["high"], p["low"], p["close"])
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrated_frame_hash.txt")
    h = pd.util.hash_pandas_object(cal.round(12).fillna(-1).stack(), index=True).sum()
    with open(out, "w") as fh:
        fh.write(f"{h}\n{cal.shape}\n")
    print(f"\nQ1: calibrated frame shape {cal.shape}, stable hash {h}")
    print(f"    (written to calibrated_frame_hash.txt; re-run after the edit and compare)")
    print(f"    calibration report: {rep}")


if __name__ == "__main__":
    main()
