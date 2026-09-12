"""M1 — is the Thai foreign-board (`-F.BK`) premium a tradable spread or a stale print?

Descriptive measurement ONLY. No strategy, no Sharpe, no DB write.

Symbol list: the review at
`.claude/worktrees/.../scratchpad/REVIEW_FOR_BRIEF.md` section 2.5 measured 15 Thai
symbol pairs (`probe_thai_foreign_board.py`, not present in this worktree at the
time this script was written). Rather than use the task brief's fallback list
verbatim (which does not exactly match the review's own text — it repeats BBL and
substitutes TCAP/KKP/INTUCH for names the review actually reports), this script
uses the 15 symbols the review's §2.5 table and prose actually name, since those
are the ones with an already-cited measurement to cross-check against:
BBL, KBANK, SCC, BAY, SCCC, BANPU, ADVANC, PTT, SCB, CPALL, AOT, TU, KTB, TISCO, EGCO.

For each symbol this script independently re-fetches `<SYM>.BK` and `<SYM>-F.BK`
from yfinance (period="max", auto_adjust=False) rather than reusing any cached
review output, and reports:
  (a) days in common between the two legs
  (b) fraction of common days where BOTH legs have volume > 0 ("two-sided days"),
      per calendar year and overall
  (c) premium = F_close / main_close - 1: mean/median/p10/p90 on ALL common days
      vs. on two-sided days only
  (d) after a two-sided day t, change in premium at t+1/t+5/t+20 trading days
      (premium[t+k] - premium[t]), restricted to pairs where t+k is ALSO a
      two-sided day; mean, median, and n pairs
  (e) THB depth proxy = F_volume * F_close on two-sided days: p25/median/p75,
      overall and for the last 3 years only
  (f) last-3-years-only versions of (b) and (c)
  (g) for BBL, KBANK, SCC only: autocorrelation (lag 1) of the premium computed
      over the sequence of two-sided days only (diagnostic, not a strategy)
"""
import json
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import yfinance as yf

SYMBOLS = [
    "BBL", "KBANK", "SCC", "BAY", "SCCC", "BANPU", "ADVANC", "PTT",
    "SCB", "CPALL", "AOT", "TU", "KTB", "TISCO", "EGCO",
]

OUT_DIR = "."
TODAY = datetime.now(UTC).date()
THREE_YEARS_AGO = pd.Timestamp(TODAY) - pd.DateOffset(years=3)


def fetch(symbol: str) -> pd.DataFrame | None:
    try:
        df = yf.Ticker(symbol).history(period="max", auto_adjust=False)
    except Exception as e:  # noqa: BLE001 - report, don't hide fetch failures
        print(f"  fetch error {symbol}: {e}", file=sys.stderr)
        return None
    if df is None or df.empty:
        return None
    df = df[["Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def pct(arr, q):
    if len(arr) == 0:
        return None
    return float(np.percentile(arr, q))


def summarize_premium(prem: pd.Series) -> dict:
    if len(prem) == 0:
        return {"n": 0, "mean": None, "median": None, "p10": None, "p90": None}
    return {
        "n": len(prem),
        "mean": float(prem.mean()),
        "median": float(prem.median()),
        "p10": pct(prem.values, 10),
        "p90": pct(prem.values, 90),
    }


def measure_pair(symbol: str) -> dict:
    main = fetch(f"{symbol}.BK")
    fboard = fetch(f"{symbol}-F.BK")

    result = {"symbol": symbol, "main_exists": main is not None, "f_exists": fboard is not None}

    if main is None or fboard is None:
        result["note"] = "one or both legs missing; skipping pair measurement"
        return result

    joined = main.join(fboard, how="inner", lsuffix="_main", rsuffix="_f")
    joined = joined.sort_index()
    result["days_in_common"] = len(joined)
    if len(joined) == 0:
        result["note"] = "no overlapping dates"
        return result

    result["window_start"] = str(joined.index.min().date())
    result["window_end"] = str(joined.index.max().date())

    two_sided_mask = (joined["Volume_main"] > 0) & (joined["Volume_f"] > 0)
    joined["two_sided"] = two_sided_mask

    # (b) two-sided fraction overall and per year
    result["two_sided_fraction_overall"] = float(two_sided_mask.mean())
    by_year = joined.groupby(joined.index.year)["two_sided"].mean()
    result["two_sided_fraction_by_year"] = {int(y): float(v) for y, v in by_year.items()}

    # premium on all common days
    premium_all = joined["Close_f"] / joined["Close_main"] - 1.0
    joined["premium"] = premium_all
    result["premium_all_days"] = summarize_premium(premium_all)

    # premium on two-sided days only
    premium_2s = premium_all[two_sided_mask]
    result["premium_two_sided_days"] = summarize_premium(premium_2s)

    # (d) forward change in premium after a two-sided day, restricted to
    # t+k also being two-sided
    fwd = {}
    two_sided_idx = joined.index[two_sided_mask]
    prem_series = joined["premium"]
    for k in (1, 5, 20):
        shifted_prem = prem_series.shift(-k)
        shifted_two_sided = joined["two_sided"].shift(-k).fillna(False).astype(bool)
        valid = two_sided_mask & shifted_two_sided
        diffs = (shifted_prem - prem_series)[valid].dropna()
        fwd[str(k)] = {
            "n_pairs": len(diffs),
            "mean": float(diffs.mean()) if len(diffs) else None,
            "median": float(diffs.median()) if len(diffs) else None,
        }
    result["premium_change_after_two_sided_day"] = fwd

    # (e) THB depth proxy on two-sided days
    depth = (joined["Volume_f"] * joined["Close_f"])[two_sided_mask]
    result["depth_thb_two_sided_days"] = {
        "n": len(depth),
        "p25": pct(depth.values, 25),
        "median": pct(depth.values, 50),
        "p75": pct(depth.values, 75),
    }
    last3_mask = joined.index >= THREE_YEARS_AGO
    depth_3y = (joined["Volume_f"] * joined["Close_f"])[two_sided_mask & last3_mask]
    result["depth_thb_two_sided_days_last3y"] = {
        "n": len(depth_3y),
        "p25": pct(depth_3y.values, 25),
        "median": pct(depth_3y.values, 50),
        "p75": pct(depth_3y.values, 75),
    }

    # (f) last 3 years only: two-sided fraction + premium summaries
    joined_3y = joined[last3_mask]
    two_sided_3y_mask = joined_3y["two_sided"]
    result["last_3y"] = {
        "days_in_common": len(joined_3y),
        "two_sided_fraction": float(two_sided_3y_mask.mean()) if len(joined_3y) else None,
        "premium_all_days": summarize_premium(joined_3y["premium"]),
        "premium_two_sided_days": summarize_premium(joined_3y["premium"][two_sided_3y_mask]),
    }

    # (g) autocorrelation of premium across consecutive two-sided days (diagnostic only)
    if symbol in ("BBL", "KBANK", "SCC"):
        prem_2s_seq = joined.loc[two_sided_idx, "premium"].dropna()
        if len(prem_2s_seq) > 2:
            ac = prem_2s_seq.autocorr(lag=1)
            result["premium_autocorr_lag1_two_sided_seq"] = (
                float(ac) if ac is not None and not np.isnan(ac) else None
            )
        else:
            result["premium_autocorr_lag1_two_sided_seq"] = None

    return result


def main():
    all_results = []
    for sym in SYMBOLS:
        print(f"measuring {sym} ...", file=sys.stderr)
        all_results.append(measure_pair(sym))

    output = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "symbols_source": (
            "REVIEW_FOR_BRIEF.md section 2.5's own 15 named symbols "
            "(BBL, KBANK, SCC, BAY, SCCC, BANPU, ADVANC, PTT, SCB, CPALL, AOT, TU, "
            "KTB, TISCO, EGCO); the review's own probe script "
            "(probe_thai_foreign_board.py) was not present in this worktree, so "
            "each pair was independently re-fetched from yfinance rather than "
            "reused."
        ),
        "three_years_ago_cutoff": str(THREE_YEARS_AGO.date()),
        "results": all_results,
    }

    with open(f"{OUT_DIR}/m1_output.json", "w") as f:
        json.dump(output, f, indent=2)

    write_txt_table(output)


def fmt_pct(x):
    return "n/a" if x is None else f"{x*100:.3f}%"


def fmt_num(x):
    return "n/a" if x is None else f"{x:,.0f}"


def write_txt_table(output: dict):
    lines = []
    lines.append("M1 — Thai foreign-board (-F.BK) premium: tradable spread or stale print?")
    lines.append(f"measured_at_utc: {output['measured_at_utc']}")
    lines.append(f"3-year cutoff: {output['three_years_ago_cutoff']}")
    lines.append("")
    header = (
        f"{'symbol':<8}{'days':>7}{'2s_frac':>9}{'2s_frac_3y':>12}"
        f"{'mean_all':>11}{'mean_2s':>11}{'med_depth_THB':>16}{'med_depth_3y':>16}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for r in output["results"]:
        if not r.get("main_exists") or not r.get("f_exists") or r.get("days_in_common", 0) == 0:
            lines.append(f"{r['symbol']:<8}  MISSING LEG OR NO OVERLAP: {r.get('note','')}")
            continue
        lines.append(
            f"{r['symbol']:<8}"
            f"{r['days_in_common']:>7}"
            f"{r['two_sided_fraction_overall']*100:>8.2f}%"
            f"{(r['last_3y']['two_sided_fraction'] or 0)*100:>11.2f}%"
            f"{fmt_pct(r['premium_all_days']['mean']):>11}"
            f"{fmt_pct(r['premium_two_sided_days']['mean']):>11}"
            f"{fmt_num(r['depth_thb_two_sided_days']['median']):>16}"
            f"{fmt_num(r['depth_thb_two_sided_days_last3y']['median']):>16}"
        )
    lines.append("")
    lines.append("Forward premium change after a two-sided day (mean, n pairs):")
    for r in output["results"]:
        if "premium_change_after_two_sided_day" not in r:
            continue
        fwd = r["premium_change_after_two_sided_day"]
        parts = []
        for k in ("1", "5", "20"):
            m = fwd[k]["mean"]
            n = fwd[k]["n_pairs"]
            parts.append(f"t+{k}: mean={fmt_pct(m)} n={n}")
        lines.append(f"  {r['symbol']:<8}" + "  ".join(parts))
    lines.append("")
    lines.append("Autocorrelation of premium (lag 1, two-sided-day sequence) — diagnostic only:")
    for r in output["results"]:
        if "premium_autocorr_lag1_two_sided_seq" in r:
            ac = r["premium_autocorr_lag1_two_sided_seq"]
            lines.append(f"  {r['symbol']:<8} autocorr={ac}")

    with open(f"{OUT_DIR}/m1_output.txt", "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
