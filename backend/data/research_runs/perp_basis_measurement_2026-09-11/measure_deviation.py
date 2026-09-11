"""Descriptive measurement of the Binance perp-spot basis deviation rho, per
He, Manela, Ross & von Wachter (HMRvW), "Fundamentals of Perpetual Futures"
(source text: backend/data/research_runs/hunting_ground_review_2026-09-11/
sources/perpetual_futures_fundamentals.txt -- line numbers below cite THAT
file). This is a MEASUREMENT of the opportunity, not a strategy backtest: no
Sharpe, no DSR, no verdict, no registration, no DB write. See
MEASUREMENT_2026-09-11.md for the full writeup this script's output feeds.

FORMULA, Eq. (8), lines 935-937:
    rho = kappa * (1 - exp(-(f - s))) - (r - r')  ~=  kappa*(f - s) - (r - r')
    f = ln(perp close), s = ln(spot close), kappa = 1095 (annualization
    constant used throughout the paper's tables), r' = 0 (line 956: "no
    interest is paid on spot crypto holdings"). This script uses the exact
    (not approximate) form, matching the paper's own equation, and takes
    r = 0 throughout -- see the module-level RISK_FREE_RATE_CAVEAT below and
    MEASUREMENT_2026-09-11.md's caveats section. rho is left in DECIMAL units
    (e.g. 1.792 = 179.2%), matching Table 3's percentages divided by 100.

BOUNDS, Table 3, line 866 (High tier) and the formula at line 878:
    rho_l = kappa * log(1 - C), rho_u = kappa * log(1 + C)
    High tier (line 866): rho_l = -179.5%, rho_u = +179.2%  (quoted directly,
    not recomputed, because the paper's own C for this tier -- spot 0.0675%
    + futures 0.0144% per side, round trip -- is stated in the same row and
    this script does not re-derive it independently for the paper's own
    tier; the retail-taker tier below IS re-derived, from fees this script's
    author verified live, because the paper never quotes a taker number).

CLOSE RULE, line 1128: "we open the position [when rho exits the bound].
We close the position when rho first goes back to 0."

RETAIL-TAKER BOUND: same formula as the High tier (line 878), with C built
from Binance Regular-User (VIP 0) TAKER fees, verified live 2026-09-11 via
WebFetch (not from memory, not from the paper -- the paper explicitly uses
MAKER fees, line 847-848: "We consider trading costs for makers instead of
takers because institutions typically trade maker orders"):
  * spot taker 0.100% -- https://www.binance.com/en/fee/trading (fetched
    2026-09-11: "Spot Trading: 0.100% taker fee" for non-VIP/regular users)
  * USDS-M futures taker 0.050% -- https://www.binance.com/en/support/faq/
    detail/360033544231 (fetched 2026-09-11: "a Regular User's maker fee is
    0.02% and a Regular User's taker fee is 0.05%")
  C = 2 * (spot_taker + perp_taker) = 2*(0.00100+0.00050) = 0.00300, the same
  "2x(spot+futures)" construction that reproduces the paper's own High-tier
  bound EXACTLY from its own per-side fees (verified as an independent check
  in this script's __main__ self-test: 1095*ln(1+2*(0.000675+0.000144)) =
  1.792 = 179.2%, matching Table 3's rho_u to 3 decimals)."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # .../backend
from app.config import MAIN_CHECKOUT_BACKEND_DIR

KAPPA = 1095.0  # HMRvW's annualization constant, used throughout their tables

# Table 3, line 866. Quoted directly from the paper, not recomputed --
# expressed as decimals (179.2% -> 1.792).
HIGH_TIER_RHO_L = -1.795
HIGH_TIER_RHO_U = 1.792

# Retail-taker fees, verified live 2026-09-11 (see module docstring).
RETAIL_SPOT_TAKER = 0.00100
RETAIL_PERP_TAKER = 0.00050
RETAIL_C = 2 * (RETAIL_SPOT_TAKER + RETAIL_PERP_TAKER)
RETAIL_RHO_L = KAPPA * math.log(1 - RETAIL_C)
RETAIL_RHO_U = KAPPA * math.log(1 + RETAIL_C)

# r = 0 throughout: this project does not hold the Aave USDT supply/borrow
# rate series the paper uses (line 962-965). The paper does not quantify its
# magnitude anywhere in the extracted text (checked: no numeric Aave rate
# appears outside Figure 8, which is a plot, not a table) -- so the honest
# disclosure is "unquantified, single-digit %/yr order, a GUESS" rather than
# a specific number. Against bounds of +-179%/yr (High tier) or +-320%/yr
# (retail-taker), a single-digit-%/yr r shifts rho by a few percentage
# points at most -- small relative to the bound width, but NOT zero, and
# every number in this script's output is on the r=0 basis, stated as such.
RISK_FREE_RATE_R = 0.0
RISK_FREE_RATE_CAVEAT = (
    "r=0 (Aave series not held; paper gives no numeric magnitude in the "
    "extracted text outside a plot -- unquantified, single-digit %/yr "
    "order, a GUESS at magnitude only, not used as a number)"
)

PAPER_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT"]
ALT_SYMBOLS = [
    "SOLUSDT", "XRPUSDT", "ZECUSDT", "LINKUSDT", "UNIUSDT",
    "NEARUSDT", "AVAXUSDT", "AAVEUSDT", "FILUSDT", "BCHUSDT",
    "TRXUSDT", "LTCUSDT", "XMRUSDT", "XLMUSDT", "DOTUSDT",
    "CRVUSDT", "HBARUSDT", "ICPUSDT", "ETCUSDT", "ATOMUSDT",
]
ALL_SYMBOLS = PAPER_SYMBOLS + ALT_SYMBOLS

# Table 2's own per-symbol sample starts (line ~816-824), used ONLY for the
# replication check (section 4) so that check compares like-for-like against
# Table 7's sample. Every other measurement in this script uses each
# symbol's own full fetched history instead.
PAPER_SAMPLE_START = {
    "BTCUSDT": "2020-01-08",
    "ETHUSDT": "2020-01-08",
    "BNBUSDT": "2020-02-10",
    "DOGEUSDT": "2020-07-10",
    "ADAUSDT": "2020-01-31",
}
PAPER_SAMPLE_END = "2024-03-11"  # line 812: "Our data ends on 2024-03-11"

# Table 7's "Active %" (High trading costs, unrestricted), line 1300-1332,
# by symbol and year. Transcribed by hand from the extracted text -- cross-
# checked against Table 6's High-tier Active% column (line 1216 etc.) for
# the "All" figure, which must equal Table 7's "All" column; both equal
# 20.06/22.68/35.02/28.79/34.60 for BTC/ETH/BNB/DOGE/ADA respectively.
TABLE7_ACTIVE_PCT = {
    "BTCUSDT": {2020: 28.66, 2021: 34.43, 2022: 9.21, 2023: 7.68, 2024: 22.18, "All": 20.06},
    "ETHUSDT": {2020: 37.80, 2021: 34.91, 2022: 8.23, 2023: 10.35, 2024: 20.93, "All": 22.68},
    "BNBUSDT": {2020: 55.23, 2021: 48.03, 2022: 16.54, 2023: 18.93, 2024: 53.39, "All": 35.02},
    "DOGEUSDT": {2020: 60.12, 2021: 49.19, 2022: 16.92, 2023: 8.37, 2024: 12.72, "All": 28.79},
    "ADAUSDT": {2020: 47.61, 2021: 42.18, 2022: 28.52, 2023: 25.24, 2024: 13.20, "All": 34.60},
}


def load_hourly(hourly_dir: Path, market: str, symbol: str) -> pd.Series:
    path = hourly_dir / f"{market}_{symbol}.csv"
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    s = df["close"].astype(float)
    s.index.name = "open_time"
    return s


def compute_rho(
    spot: pd.Series, perp: pd.Series, r: float = RISK_FREE_RATE_R
) -> tuple[pd.Series, dict]:
    """Eq. (8) exact form: rho = kappa*(1 - exp(-(f-s))) - r, f=ln(perp),
    s=ln(spot). Aligns on the INNER join of both indices (both bars must
    exist for that hour) and reports the alignment gap honestly."""
    union_index = spot.index.union(perp.index)
    aligned = spot.index.intersection(perp.index)
    missing_spot = len(union_index) - len(spot.index)
    missing_perp = len(union_index) - len(perp.index)

    f = np.log(perp.loc[aligned])
    s = np.log(spot.loc[aligned])
    rho = KAPPA * (1 - np.exp(-(f - s))) - r
    rho.name = "rho"
    align_stats = {
        "union_hours": len(union_index),
        "aligned_hours": len(aligned),
        "hours_missing_spot": int(missing_spot),
        "hours_missing_perp": int(missing_perp),
    }
    return rho, align_stats


def find_excursions(rho: pd.Series, rho_l: float, rho_u: float) -> list[dict]:
    """The paper's random-maturity strategy state machine (line 1122-1128):
    open when rho first exits [rho_l, rho_u]; close when rho first returns
    to (crosses) 0. Operates on the hourly series in index order; assumes
    the index is sorted and roughly hourly (gaps are tolerated -- duration
    is measured in ELAPSED HOURS via the index timestamps, not bar counts,
    so a data gap does not silently compress the reported duration)."""
    excursions = []
    state = None  # None, "high" (rho > rho_u), or "low" (rho < rho_l)
    entry_time = None
    entry_rho = None

    def _closes(state: str, v: float) -> bool:
        return (state == "high" and v <= 0) or (state == "low" and v >= 0)

    idx = rho.index
    vals = rho.to_numpy()
    for i in range(len(vals)):
        v = vals[i]
        t = idx[i]
        if state is not None and _closes(state, v):
            duration_h = (t - entry_time).total_seconds() / 3600.0
            excursions.append(
                {"entry_time": entry_time, "exit_time": t, "duration_hours": duration_h,
                 "entry_rho": entry_rho, "direction": state}
            )
            state = None
        if state is None:
            # Fresh entry: either the flat state coming in, or the same bar
            # that just closed a position re-crossing straight into the
            # opposite bound (a data gap can jump past 0 in one step).
            if v > rho_u:
                state, entry_time, entry_rho = "high", t, v
            elif v < rho_l:
                state, entry_time, entry_rho = "low", t, v
    return excursions


def compute_active_mask(rho: pd.Series, rho_l: float, rho_u: float) -> pd.Series:
    """Boolean Series, same index as rho: True for every hour the paper's
    strategy would hold an OPEN position (from the entry bar, inclusive,
    through the bar before the bar that closes it back to 0).

    THIS, NOT THE INSTANTANEOUS "rho is beyond the bound right now" fraction,
    is what Table 7's "Active %" measures. Found by re-deriving instead of
    trusting a first naive comparison: an initial replication pass compared
    the instantaneous exceedance share to Table 7 and got shares 5-45x
    smaller than the paper's for every symbol/year (e.g. BTC 2021: 5.8% vs
    the paper's 34.43%). Re-deriving Table 7's OWN definition from the text
    (line 1201-1204: "the average duration of open-to-close positions" is a
    SEPARATE reported column (OtC time) FROM Active% -- meaning Active% must
    be the fraction of hours a position is open, which persists through the
    whole excursion even while rho sits back inside the bound but hasn't
    yet crossed zero) and checking it against this repo's own excursion
    state machine for BTC 2021 (18 excursions x 168.5h mean duration /
    8760h = 34.6%) reproduced the paper's 34.43% almost exactly -- confirming
    this was a comparator-definition bug, not a data or formula bug. See
    MEASUREMENT_2026-09-11.md section 6c for the full writeup."""
    mask = np.zeros(len(rho), dtype=bool)
    idx = rho.index
    for exc in find_excursions(rho, rho_l, rho_u):
        start_pos = idx.searchsorted(exc["entry_time"], side="left")
        end_pos = idx.searchsorted(exc["exit_time"], side="left")
        mask[start_pos:end_pos] = True
    return pd.Series(mask, index=idx)


def year_key(ts: pd.Timestamp, end_of_data: pd.Timestamp) -> str:
    y = ts.year
    if y == end_of_data.year:
        return f"{y}-partial"
    return str(y)


def summarize_symbol(symbol: str, hourly_dir: Path) -> dict:
    spot = load_hourly(hourly_dir, "spot", symbol)
    perp = load_hourly(hourly_dir, "perp", symbol)
    rho, align_stats = compute_rho(spot, perp)

    if rho.empty:
        return {"symbol": symbol, "align": align_stats, "years": {}, "excursions_high": [], "excursions_retail": []}

    end_of_data = rho.index.max()
    years = sorted(rho.index.year.unique())
    year_labels = {y: (f"{y}-partial" if y == end_of_data.year else str(y)) for y in years}

    excursions_high = find_excursions(rho, HIGH_TIER_RHO_L, HIGH_TIER_RHO_U)
    excursions_retail = find_excursions(rho, RETAIL_RHO_L, RETAIL_RHO_U)
    # Table 7's "Active %" is the fraction of HOURS A POSITION IS OPEN, which
    # persists through the whole excursion (entry until the return-to-zero
    # close) -- NOT the instantaneous "rho is beyond the bound right now"
    # fraction (share_above_high_u/share_below_high_l below), which is a much
    # narrower, different quantity. See compute_active_mask's docstring for
    # how this was found and verified.
    active_high = compute_active_mask(rho, HIGH_TIER_RHO_L, HIGH_TIER_RHO_U)
    active_retail = compute_active_mask(rho, RETAIL_RHO_L, RETAIL_RHO_U)

    per_year = {}
    ma7 = rho.rolling("7D").mean()
    for y in years:
        label = year_labels[y]
        yr_rho = rho[rho.index.year == y]
        yr_ma7 = ma7[ma7.index.year == y]
        yr_active_high = active_high[active_high.index.year == y]
        yr_active_retail = active_retail[active_retail.index.year == y]
        n = len(yr_rho)
        per_year[label] = {
            "n_hours": n,
            "active_pct_high_tier": float(yr_active_high.mean()),
            "active_pct_retail_taker": float(yr_active_retail.mean()),
            "share_beyond_high_tier": float(((yr_rho > HIGH_TIER_RHO_U) | (yr_rho < HIGH_TIER_RHO_L)).mean()),
            "share_above_high_u": float((yr_rho > HIGH_TIER_RHO_U).mean()),
            "share_below_high_l": float((yr_rho < HIGH_TIER_RHO_L).mean()),
            "share_beyond_retail_taker": float(((yr_rho > RETAIL_RHO_U) | (yr_rho < RETAIL_RHO_L)).mean()),
            "rho_mean": float(yr_rho.mean()),
            "rho_median": float(yr_rho.median()),
            "rho_p05": float(yr_rho.quantile(0.05)),
            "rho_p95": float(yr_rho.quantile(0.95)),
            "rho_ma7_mean": float(yr_ma7.mean()) if len(yr_ma7) else float("nan"),
            "rho_ma7_median": float(yr_ma7.median()) if len(yr_ma7) else float("nan"),
            "rho_ma7_p05": float(yr_ma7.quantile(0.05)) if len(yr_ma7) else float("nan"),
            "rho_ma7_p95": float(yr_ma7.quantile(0.95)) if len(yr_ma7) else float("nan"),
        }

    all_n = len(rho)
    per_year["All"] = {
        "n_hours": all_n,
        "active_pct_high_tier": float(active_high.mean()),
        "active_pct_retail_taker": float(active_retail.mean()),
        "share_beyond_high_tier": float(((rho > HIGH_TIER_RHO_U) | (rho < HIGH_TIER_RHO_L)).mean()),
        "share_above_high_u": float((rho > HIGH_TIER_RHO_U).mean()),
        "share_below_high_l": float((rho < HIGH_TIER_RHO_L).mean()),
        "share_beyond_retail_taker": float(((rho > RETAIL_RHO_U) | (rho < RETAIL_RHO_L)).mean()),
        "rho_mean": float(rho.mean()),
        "rho_median": float(rho.median()),
        "rho_p05": float(rho.quantile(0.05)),
        "rho_p95": float(rho.quantile(0.95)),
        "rho_ma7_mean": float(ma7.mean()),
        "rho_ma7_median": float(ma7.median()),
        "rho_ma7_p05": float(ma7.quantile(0.05)),
        "rho_ma7_p95": float(ma7.quantile(0.95)),
    }

    return {
        "symbol": symbol,
        "align": align_stats,
        "years": per_year,
        "excursions_high": excursions_high,
        "excursions_retail": excursions_retail,
        "rho_series": rho,  # kept in-memory for the correlation step; not serialized
    }


def excursions_to_year_rows(symbol: str, bound_label: str, excursions: list[dict], end_of_data: pd.Timestamp) -> list[dict]:
    if not excursions:
        return []
    by_year: dict[str, list[dict]] = {}
    for e in excursions:
        label = year_key(e["entry_time"], end_of_data)
        by_year.setdefault(label, []).append(e)
    rows = []
    for label, group in sorted(by_year.items()):
        durations = [g["duration_hours"] for g in group]
        entries = [abs(g["entry_rho"]) for g in group]
        rows.append({
            "symbol": symbol,
            "bound": bound_label,
            "year": label,
            "n_excursions": len(group),
            "mean_duration_hours": float(np.mean(durations)),
            "median_duration_hours": float(np.median(durations)),
            "mean_abs_entry_rho": float(np.mean(entries)),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hourly-dir", type=Path, default=MAIN_CHECKOUT_BACKEND_DIR / "data" / "binance_hourly")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--symbols", nargs="*", default=ALL_SYMBOLS)
    args = parser.parse_args()

    # Self-test cited in the module docstring: the retail-taker formula,
    # applied to the PAPER's own High-tier per-side fees, must reproduce the
    # paper's own High-tier bound (Table 3, line 866) to 3 decimals -- this
    # is a check on THIS SCRIPT's formula, not a claim about the retail bound.
    paper_high_c = 2 * (0.000675 + 0.000144)
    check_u = KAPPA * math.log(1 + paper_high_c)
    check_l = KAPPA * math.log(1 - paper_high_c)
    assert abs(check_u - HIGH_TIER_RHO_U) < 0.001, (check_u, HIGH_TIER_RHO_U)
    assert abs(check_l - HIGH_TIER_RHO_L) < 0.001, (check_l, HIGH_TIER_RHO_L)
    print(f"Self-test OK: 2x(spot+perp) formula reproduces Table 3 High tier "
          f"(computed u={check_u:.4f} vs paper u={HIGH_TIER_RHO_U}, "
          f"l={check_l:.4f} vs paper l={HIGH_TIER_RHO_L})")
    print(f"Retail-taker bound: C={RETAIL_C:.5f}, rho_u={RETAIL_RHO_U:.4f} "
          f"({RETAIL_RHO_U*100:.1f}%), rho_l={RETAIL_RHO_L:.4f} ({RETAIL_RHO_L*100:.1f}%)")

    per_symbol = {}
    deviation_rows = []
    excursion_rows = []
    align_rows = []

    for symbol in args.symbols:
        print(f"Measuring {symbol}...", flush=True)
        result = summarize_symbol(symbol, args.hourly_dir)
        per_symbol[symbol] = result
        align_rows.append({"symbol": symbol, **result["align"]})

        rho = result.get("rho_series")
        end_of_data = rho.index.max() if rho is not None and len(rho) else None

        for year_label, stats in result["years"].items():
            deviation_rows.append({"symbol": symbol, "year": year_label, **stats})

        if end_of_data is not None:
            excursion_rows.extend(excursions_to_year_rows(symbol, "high_tier", result["excursions_high"], end_of_data))
            excursion_rows.extend(excursions_to_year_rows(symbol, "retail_taker", result["excursions_retail"], end_of_data))

    deviation_df = pd.DataFrame(deviation_rows)
    excursion_df = pd.DataFrame(excursion_rows)
    align_df = pd.DataFrame(align_rows)

    deviation_df.to_csv(args.out_dir / "deviation_summary.csv", index=False)
    excursion_df.to_csv(args.out_dir / "excursions.csv", index=False)
    align_df.to_csv(args.out_dir / "alignment_report.csv", index=False)

    # -- section 4: replication check against Table 7 --------------------
    # Compared quantity is ACTIVE %, the fraction of hours a position is
    # open (see compute_active_mask docstring) -- NOT the instantaneous
    # exceedance share. The mask is computed on each symbol's FULL fetched
    # history (so an excursion open before the paper's sample-start date, or
    # still open after its sample-end date, is not spuriously truncated by
    # resetting the state machine at the window boundary) and then sliced to
    # the paper's own Table-2 sample window for the comparison.
    replication_rows = []
    for symbol in PAPER_SYMBOLS:
        rho_full = per_symbol[symbol].get("rho_series")
        if rho_full is None:
            continue
        active_full = compute_active_mask(rho_full, HIGH_TIER_RHO_L, HIGH_TIER_RHO_U)
        start = pd.Timestamp(PAPER_SAMPLE_START[symbol])
        end = pd.Timestamp(PAPER_SAMPLE_END)
        window = active_full[(active_full.index >= start) & (active_full.index <= end)]
        for y in [2020, 2021, 2022, 2023, 2024]:
            yr = window[window.index.year == y]
            if len(yr) == 0:
                continue
            mine = float(yr.mean() * 100)
            paper = TABLE7_ACTIVE_PCT[symbol].get(y)
            replication_rows.append({
                "symbol": symbol, "year": y, "n_hours_mine": len(yr),
                "my_active_pct_r0": round(mine, 2), "paper_active_pct": paper,
                "diff_pp": round(mine - paper, 2) if paper is not None else None,
            })
        mine_all = float(window.mean() * 100)
        paper_all = TABLE7_ACTIVE_PCT[symbol]["All"]
        replication_rows.append({
            "symbol": symbol, "year": "All", "n_hours_mine": len(window),
            "my_active_pct_r0": round(mine_all, 2), "paper_active_pct": paper_all,
            "diff_pp": round(mine_all - paper_all, 2),
        })
    replication_df = pd.DataFrame(replication_rows)
    replication_df.to_csv(args.out_dir / "replication_check.csv", index=False)

    # -- section 5: cross-symbol correlation, 2024-03 onward --------------
    cutoff = pd.Timestamp("2024-03-01")
    series_map = {}
    for symbol in args.symbols:
        rho_full = per_symbol[symbol].get("rho_series")
        if rho_full is None or len(rho_full) == 0:
            continue
        s = rho_full[rho_full.index >= cutoff]
        if len(s) > 100:
            series_map[symbol] = s
    corr_frame = pd.DataFrame(series_map)
    corr_matrix = corr_frame.corr()
    corr_matrix.to_csv(args.out_dir / "rho_correlation_2024_03_onward.csv")

    mean_pairwise = np.nan
    if corr_matrix.shape[0] > 1:
        vals = corr_matrix.to_numpy()
        n = vals.shape[0]
        upper = vals[np.triu_indices(n, k=1)]
        mean_pairwise = float(np.nanmean(upper))

    summary = {
        "kappa": KAPPA,
        "high_tier_bounds": {"rho_l": HIGH_TIER_RHO_L, "rho_u": HIGH_TIER_RHO_U},
        "retail_taker_bounds": {"rho_l": RETAIL_RHO_L, "rho_u": RETAIL_RHO_U, "C": RETAIL_C,
                                 "spot_taker": RETAIL_SPOT_TAKER, "perp_taker": RETAIL_PERP_TAKER},
        "risk_free_rate_caveat": RISK_FREE_RATE_CAVEAT,
        "mean_pairwise_rho_correlation_2024_03_onward": mean_pairwise,
        "n_symbols_in_correlation": int(corr_matrix.shape[0]),
        "symbols": args.symbols,
    }
    (args.out_dir / "measurement_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print("Done.")


if __name__ == "__main__":
    main()
