"""REPRODUCIBILITY SCRIPT for
data/research_runs/short_interest_reproducibility_2026-09-04.txt — the
si_ratio_hedged_h21 reproducibility investigation (2026-09-04).

Every number quoted in that report comes from one of the subcommands below.
Run from backend/ with PYTHONPATH=. and the venv's python.

  finra       byte-diff cached FINRA cycle files against a fresh live fetch
              (candidate a)
  cikmap      diff SEC's cached vs a freshly-fetched company_tickers.json,
              restricted to this family's point-in-time universe
              (candidate b, part 1)
  cikmap-ab   run_short_interest_screening under the old map vs a fresh map,
              everything else held fixed (candidate b, part 2)
  secframes   diff all 36 cached SEC XBRL share-count frames against a fresh
              fetch, restricted to this family's resolvable CIKs
              (candidate c)
  splitcheck  the APH/MNST forensic trail: cumulative_split_factor against
              each ticker's own stored split column vs. a fresh single-
              ticker yfinance query (candidate d)
  snapshot    fetch and save the full-universe OHLCV snapshot used for the
              price_frames reproducibility proof
  replay      load the saved snapshot twice and run
              run_short_interest_screening(price_frames=...) both times,
              asserting the results are bit-identical

This script writes nothing to any git-tracked path; all fetched artifacts
land under a --scratch directory (default /tmp/si_repro_scratch) or the
project's normal gitignored price/FINRA/SEC caches under backend/data/.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.price_store import cumulative_split_factor
from app.services.market_data.yfinance_provider import (
    YFinanceProvider,
    load_ohlcv_snapshot,
    save_ohlcv_snapshot,
)
from app.services.research_lab.cross_sectional_short_interest import (
    SHORT_INTEREST_FORMATION_START,
    SHORT_INTEREST_PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    run_short_interest_screening,
)
from app.services.research_lab.sp500_membership_history import get_universe_over

REGISTRATION_START = SHORT_INTEREST_FORMATION_START
REGISTRATION_END = date(2026, 9, 1)
USER_AGENT = {"User-Agent": "aladdin2-research/1.0 (autoa0792@gmail.com)"}


def cmd_finra(args: argparse.Namespace) -> None:
    import hashlib

    finra_dir = Path("data/finra_short_interest")
    for stamp in args.stamps:
        cached = finra_dir / f"shrt{stamp}.csv"
        url = f"https://cdn.finra.org/equity/otcmarket/biweekly/shrt{stamp}.csv"
        resp = requests.get(url, headers=USER_AGENT, timeout=60)
        fresh_md5 = hashlib.md5(resp.content).hexdigest()
        cached_md5 = hashlib.md5(cached.read_bytes()).hexdigest() if cached.exists() else None
        match = "MATCH" if fresh_md5 == cached_md5 else "DIFFERS (or no cached copy)"
        print(f"shrt{stamp}.csv  cached={cached_md5}  fresh={fresh_md5}  {match}")


def cmd_cikmap(args: argparse.Namespace) -> None:
    old = EdgarXbrlProvider().get_ticker_cik_map()
    fresh = EdgarXbrlProvider(cache_dir=args.scratch / "fresh_edgar", max_cache_age_days=0).get_ticker_cik_map()
    only_old = set(old) - set(fresh)
    only_fresh = set(fresh) - set(old)
    changed = {t for t in (set(old) & set(fresh)) if old[t] != fresh[t]}
    print(f"old map size={len(old)}  fresh map size={len(fresh)}")
    print(f"only in old (dropped): {len(only_old)}  sample={sorted(only_old)[:10]}")
    print(f"only in fresh (added): {len(only_fresh)}  sample={sorted(only_fresh)[:10]}")
    print(f"changed CIK for same ticker: {sorted(changed)}")


def cmd_cikmap_ab(args: argparse.Namespace) -> None:
    for label, edgar in (
        ("old map", EdgarXbrlProvider()),
        ("fresh map", EdgarXbrlProvider(cache_dir=args.scratch / "fresh_edgar", max_cache_age_days=0)),
    ):
        summary = run_short_interest_screening(start=REGISTRATION_START, end=REGISTRATION_END, edgar=edgar)
        row = next(r for r in summary.results if r.pattern_id == "si_ratio_hedged_h21")
        print(
            f"[{label}] tickers_without_cik={len(summary.shares.tickers_without_cik)} "
            f"n_cells_common={summary.panel.n_cells_common} "
            f"si_ratio_hedged_h21 sharpe={row.sharpe_annualized!r} dsr={row.deflated_sharpe.dsr!r}"
        )


def cmd_secframes(args: argparse.Namespace) -> None:
    universe = get_universe_over(REGISTRATION_START, REGISTRATION_END)
    cik_map = EdgarXbrlProvider().get_ticker_cik_map()
    rev = {v: k for k, v in cik_map.items()}
    ciks = {cik_map[t] for t in universe if t in cik_map}
    print(f"universe size={len(universe)}  resolvable CIKs={len(ciks)}")

    any_diff = []
    for year in range(2017, 2027):
        for quarter in range(1, 5):
            if (year, quarter) < (2017, 4) or (year, quarter) > (2026, 3):
                continue
            cached_path = Path(f"data/sec_shares_outstanding/CY{year}Q{quarter}I.json")
            if not cached_path.exists():
                continue
            old = json.loads(cached_path.read_text())
            url = (
                "https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/"
                f"shares/CY{year}Q{quarter}I.json"
            )
            resp = requests.get(url, headers=USER_AGENT, timeout=60)
            new = resp.json()
            old_by_key = {(r["cik"], r["end"]): r["val"] for r in old["data"] if r["cik"] in ciks}
            new_by_key = {(r["cik"], r["end"]): r for r in new["data"] if r["cik"] in ciks}
            only_new = sorted(set(new_by_key) - set(old_by_key))
            only_old = sorted(set(old_by_key) - set(new_by_key))
            changed = [k for k in (set(old_by_key) & set(new_by_key)) if old_by_key[k] != new_by_key[k]["val"]]
            if only_new or only_old or changed:
                any_diff.append((year, quarter, only_old, only_new, changed))
                print(f"CY{year}Q{quarter}: only_old={len(only_old)} only_new={len(only_new)} changed={len(changed)}")
                for k in only_new:
                    row = new_by_key[k]
                    print(f"    NEW: {row['cik']} {rev.get(row['cik'])} {row['entityName']} {row['end']} {row['val']}")
    if not any_diff:
        print("all checked quarters matched exactly.")


def cmd_splitcheck(args: argparse.Namespace) -> None:
    import yfinance as yf

    for ticker in args.tickers:
        t = yf.Ticker(ticker)
        h = t.history(start="2017-12-13", end="2026-09-02", auto_adjust=False, actions=True)
        close_2017 = h.loc["2017-12-13", "Close"] if "2017-12-13" in h.index.strftime("%Y-%m-%d") else None
        splits = h.loc[h["Stock Splits"] != 0, "Stock Splits"]
        info = t.get_info()
        print(f"=== {ticker} ===")
        print(f"  fresh Close(2017-12-13, auto_adjust=False) = {close_2017}")
        print(f"  splits visible in .history() actions table: {dict(splits)}")
        print(f"  get_info() lastSplitFactor={info.get('lastSplitFactor')} lastSplitDate={info.get('lastSplitDate')}")

        store_path = Path(f"data/price_store/v1/{ticker}.csv.gz")
        if store_path.exists():
            with gzip.open(store_path, "rt") as f:
                frame = pd.read_csv(f, index_col=0, parse_dates=True)
            factor = cumulative_split_factor(frame["split"], frame.index)
            t0 = pd.Timestamp("2017-12-13")
            if t0 in factor.index:
                print(f"  cumulative_split_factor(stored split column) at 2017-12-13 = {factor.loc[t0]}")
                print(f"  stored close at 2017-12-13 = {frame.loc[t0, 'close']}")
                if close_2017 is not None:
                    print(f"  cross-check: fresh_close x factor = {close_2017 * factor.loc[t0]}")


def cmd_snapshot(args: argparse.Namespace) -> None:
    padded_start = REGISTRATION_START - timedelta(days=SHORT_INTEREST_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    universe = get_universe_over(REGISTRATION_START, REGISTRATION_END)
    provider = YFinanceProvider()
    frames, missing = provider.get_daily_ohlcv(sorted(universe), padded_start, REGISTRATION_END)
    print(f"universe={len(universe)} resolved_fields={list(frames)} missing={len(missing)}")
    save_ohlcv_snapshot(frames, args.snapshot_dir)
    print(f"saved snapshot to {args.snapshot_dir}")


def cmd_replay(args: argparse.Namespace) -> None:
    rows = []
    for i in range(2):
        frames = load_ohlcv_snapshot(args.snapshot_dir)
        if frames is None:
            raise SystemExit(f"no snapshot at {args.snapshot_dir}; run `snapshot` first")
        summary = run_short_interest_screening(
            start=REGISTRATION_START, end=REGISTRATION_END, price_frames=frames
        )
        row = {r.pattern_id: (r.sharpe_annualized, r.deflated_sharpe.dsr) for r in summary.results}
        rows.append(row)
        si = row["si_ratio_hedged_h21"]
        print(f"RUN {i}: si_ratio_hedged_h21 sharpe={si[0]!r} dsr={si[1]!r}")
    identical = rows[0] == rows[1]
    print(f"BIT-IDENTICAL ACROSS TWO INDEPENDENT REPLAYS: {identical}")
    if not identical:
        raise SystemExit("reproducibility check FAILED — the two replays disagree")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scratch", type=Path, default=Path("/tmp/si_repro_scratch"))
    parser.add_argument(
        "--snapshot-dir", type=Path, default=Path("/tmp/si_repro_scratch/snapshot_2018-01-12_2026-09-01")
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("finra")
    p.add_argument("--stamps", nargs="+", default=["20180112", "20260731", "20260814"])
    p.set_defaults(func=cmd_finra)

    p = sub.add_parser("cikmap")
    p.set_defaults(func=cmd_cikmap)

    p = sub.add_parser("cikmap-ab")
    p.set_defaults(func=cmd_cikmap_ab)

    p = sub.add_parser("secframes")
    p.set_defaults(func=cmd_secframes)

    p = sub.add_parser("splitcheck")
    p.add_argument("--tickers", nargs="+", default=["APH", "MNST"])
    p.set_defaults(func=cmd_splitcheck)

    p = sub.add_parser("snapshot")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("replay")
    p.set_defaults(func=cmd_replay)

    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()
