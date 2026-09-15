"""Step A2 — per-ticker trading cost on the whole-market panel (2026-09-15).

Design forced by the 2026-09-15 audit, and by what the tool can honestly do:

  * `build_calibrated_half_spread_frame`'s own step 3 pins the LEVEL to a
    published constant and keeps only EDGE's relative structure. Its source
    comment states the constant is "a UNIVERSE PROPERTY, NOT A CONSTANT OF
    NATURE... right for a US large-cap (S&P 500-like) cross-section. Pass an
    explicit target_median_half_spread for anything else."  No sourced anchor
    exists for micro-caps. So this run reproduces that function's steps
    1 (sign=True + truncate to zero), 2 (halve) and 4 (tick floor) and
    DELIBERATELY SKIPS step 3 rather than invent an anchor -- the exact
    mistake (an unsourced cost constant) that this whole audit began with.

  * Per ticker it reports THREE separate things, never mixed:
      1. TICK FLOOR   -- exact arithmetic, 0.005/price, no assumption at all.
                         A hard LOWER bound on the one-way half-spread.
      2. EDGE RAW     -- sign=True, negatives truncated to zero, halved.
                         Unanchored. Usable as a RANKING, not as a level.
      3. ANCHORED     -- EDGE scaled so the large-cap bucket's median equals
                         the sourced 2.0bp, applied ONLY within that bucket.
                         Blank elsewhere, because no anchor is sourced there.

  * Audit defects handled: D1 liveness read from the data, never
    `_coverage.json`; D2 unflagged-split days break the window; D3 common
    stock only, from `clean_universe.csv`.
"""
import csv, gzip, json, math, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from bidask import edge_rolling  # noqa: E402
from app.services.research_lab.spread_estimator import (  # noqa: E402
    CALIBRATED_SIGN_MODE, SP500_TARGET_MEDIAN_HALF_SPREAD,
)

STORE = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
UNIV = os.path.join(HERE, "..", "a2_universe_2026-09-15", "clean_universe.csv")

WINDOW = 63                      # COST_MODEL_WINDOW_DAYS: one quarter
EVAL_START = "2025-09-01"        # ~1y of evaluation, ending at the panel's last bar
MIN_EVAL_BARS = 120
TICK = 0.005                     # half of a $0.01 minimum increment
SPLIT_RATIOS = (2,3,4,5,6,7,8,10,12,15,20,25,30,40,50,60,75,100,150,200)


def is_round_split(ratio: float) -> bool:
    for k in SPLIT_RATIOS:
        if abs(ratio - k) / k < 0.04 or abs(ratio * k - 1.0) < 0.04:
            return True
    return False


def load(sym):
    rows = []
    with gzip.open(os.path.join(STORE, sym + ".csv.gz"), "rt") as fh:
        rd = csv.DictReader(fh)
        for r in rd:
            try:
                rows.append((r["date"], float(r["open"]), float(r["high"]),
                             float(r["low"]), float(r["close"]), float(r["volume"]),
                             float(r.get("split") or 0.0)))
            except (ValueError, TypeError):
                continue
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "split"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def main():
    univ = [r for r in csv.DictReader(open(UNIV)) if r["instrument"] == "common"]
    print(f"common-stock symbols in universe: {len(univ):,}")

    out = []
    skipped = {"too_few_bars": 0, "dead_before_window": 0, "no_estimate": 0, "read_fail": 0}
    for i, u in enumerate(univ):
        sym = u["symbol"]
        if (i + 1) % 1000 == 0:
            print(f"  ...{i+1:,}/{len(univ):,}", flush=True)
        try:
            df = load(sym)
        except Exception:
            skipped["read_fail"] += 1
            continue
        if df is None or df.empty:
            skipped["read_fail"] += 1
            continue
        if str(df.index[-1].date()) < EVAL_START:
            skipped["dead_before_window"] += 1
            continue

        # D2: a big move with no split flag and a round ratio is a suspected
        # unflagged split. Break the series there so no estimation window
        # straddles it.
        c = df["close"].to_numpy()
        sp = df["split"].to_numpy()
        ratio = np.divide(c[1:], c[:-1], out=np.ones(len(c) - 1), where=c[:-1] > 0)
        suspect = np.zeros(len(df), dtype=bool)
        for k, r in enumerate(ratio):
            if (r > 1.8 or r < 0.556) and sp[k + 1] in (0.0, 1.0) and is_round_split(r):
                suspect[k + 1] = True
        n_suspect = int(suspect.sum())

        ohlc = df[["open", "high", "low", "close"]].copy()
        if n_suspect:
            # NaN the suspect bar: edge_rolling's window then yields NaN across it.
            ohlc.loc[suspect, :] = np.nan

        try:
            signed = edge_rolling(ohlc, window=WINDOW, sign=CALIBRATED_SIGN_MODE)
        except Exception:
            skipped["no_estimate"] += 1
            continue
        half = signed / 2.0                       # step 2
        # Step 1's truncation, done CORRECTLY: a non-positive estimate means
        # "no measurable spread at this window", which is the number ZERO, not
        # a missing observation. Dropping those cells and taking the median of
        # what is left selects the upper half of a noisy, zero-centred
        # estimator and biases every ticker upward. Only genuinely absent
        # estimates (short history, masked split bars) stay NaN.
        half = half.mask(half.notna() & (half <= 0.0), 0.0)

        ev = df.loc[df.index >= EVAL_START]
        if len(ev) < MIN_EVAL_BARS:
            skipped["too_few_bars"] += 1
            continue
        h_ev = half.reindex(ev.index)

        px = float(ev["close"].median())
        dv = float((ev["close"] * ev["volume"]).median())
        tick_floor = TICK / px if px > 0 else float("nan")
        n_cells = int(h_ev.notna().sum())
        n_pos = int((h_ev > 0).sum())
        edge_trunc = float(h_ev.median()) if n_cells else float("nan")
        pos_only = h_ev.where(h_ev > 0.0)
        edge_pos_only = float(pos_only.median()) if n_pos else float("nan")
        floored = h_ev.fillna(0.0).clip(lower=tick_floor)
        edge_floored = float(floored.median()) if n_cells else float("nan")

        out.append({
            "symbol": sym,
            "exchange": u["exchange"],
            "in_sec_company_tickers": u["in_sec_company_tickers"],
            "last_bar": u["last_bar"],
            "eval_bars": len(ev),
            "median_close": round(px, 4),
            "median_dollar_volume": round(dv, 1),
            "tick_floor_half_bp": round(tick_floor * 1e4, 3),
            "edge_raw_half_bp": round(edge_trunc * 1e4, 3) if n_cells else float("nan"),
            "edge_pos_only_half_bp": round(edge_pos_only * 1e4, 3) if n_pos else float("nan"),
            "edge_floored_half_bp": round(edge_floored * 1e4, 3) if n_cells else float("nan"),
            "edge_cells_positive": n_pos,
            "edge_cells_total": int(len(h_ev)),
            "suspected_unflagged_splits": n_suspect,
        })

    df = pd.DataFrame(out)
    df.to_csv(os.path.join(HERE, "a2_raw_rows.csv"), index=False)
    print(f"\nrows produced: {len(df):,}   skipped: {skipped}")

    # liquidity buckets by median dollar volume
    df["liquidity_bucket"] = pd.qcut(
        df["median_dollar_volume"], 5,
        labels=["Q1 least liquid", "Q2", "Q3", "Q4", "Q5 most liquid"])

    # Anchor ONLY the most-liquid bucket, where the sourced constant applies.
    big = df[df["liquidity_bucket"] == "Q5 most liquid"]
    big_edge = pd.to_numeric(big["edge_raw_half_bp"], errors="coerce").dropna()
    scale = (SP500_TARGET_MEDIAN_HALF_SPREAD * 1e4) / big_edge.median() if len(big_edge) else float("nan")
    df["anchored_half_bp"] = float("nan")
    mask = df["liquidity_bucket"] == "Q5 most liquid"
    df.loc[mask, "anchored_half_bp"] = (
        pd.to_numeric(df.loc[mask, "edge_raw_half_bp"], errors="coerce") * scale).round(3)

    df.to_csv(os.path.join(HERE, "a2_per_ticker_cost.csv"), index=False)

    print(f"\nanchor scale applied to Q5 only: {scale:.4f} "
          f"(pins Q5 median to the sourced {SP500_TARGET_MEDIAN_HALF_SPREAD*1e4:.1f} bp)")
    print("\n=== per liquidity bucket (one-way HALF-spread, bp) ===")
    print(f"{'bucket':16s} {'n':>6s} {'med $vol':>14s} {'med price':>10s} "
          f"{'tick floor':>11s} {'EDGE trunc':>10s} {'EDGE pos-only':>12s} {'w/ floor':>11s} {'cells>0':>10s}")
    for b in df["liquidity_bucket"].cat.categories:
        s = df[df["liquidity_bucket"] == b]
        e = pd.to_numeric(s["edge_raw_half_bp"], errors="coerce")
        meas = float((s["edge_cells_positive"] / s["edge_cells_total"]).mean()) * 100
        ep = pd.to_numeric(s["edge_pos_only_half_bp"], errors="coerce")
        ef = pd.to_numeric(s["edge_floored_half_bp"], errors="coerce")
        print(f"{b:16s} {len(s):6,d} {s['median_dollar_volume'].median():14,.0f} "
              f"{s['median_close'].median():10.2f} {s['tick_floor_half_bp'].median():11.2f} "
              f"{e.median():10.2f} {ep.median():12.2f} {ef.median():11.2f} {meas:9.1f}%")

    summary = {
        "generated": "2026-09-15",
        "universe": "common stock only (clean_universe.csv), alive at/after " + EVAL_START,
        "window_days": WINDOW, "eval_start": EVAL_START,
        "rows": int(len(df)), "skipped": skipped,
        "anchor_source": "SP500_TARGET_MEDIAN_HALF_SPREAD = 2.0bp one-way, applied ONLY to Q5",
        "anchor_scale_Q5": None if math.isnan(scale) else round(float(scale), 6),
        "tickers_with_suspected_unflagged_splits": int((df["suspected_unflagged_splits"] > 0).sum()),
        "total_suspected_unflagged_split_bars": int(df["suspected_unflagged_splits"].sum()),
    }
    json.dump(summary, open(os.path.join(HERE, "a2_summary.json"), "w"), indent=1)
    print("\nwrote a2_per_ticker_cost.csv + a2_summary.json")


if __name__ == "__main__":
    main()
