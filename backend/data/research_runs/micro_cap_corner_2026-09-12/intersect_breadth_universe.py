#!/usr/bin/env python
"""Step 0 Day 2: how many US-LISTED names sit in the sparse-ownership corner?

Joins three free sources, per quarter:
  * nport_breadth/<q>_breadth.csv.gz  (fund owners per equity CUSIP, this folder)
  * SEC fails-to-deliver archives (CUSIP -> symbol, dated) read from the MAIN
    checkout's data/form13f_raw (gitignored, per-worktree; path passed explicitly)
  * Alpaca /v2/assets symbols (active + inactive, listed exchanges, plain tickers)
    from alpaca_universe_probe.json's counts are NOT enough -- the symbol lists are
    re-fetched here so the join is on actual symbols.
Counts, per quarter, CUSIPs with 5..47 fund owners (the Coval-Stafford breadth
regime) that map to a listed Alpaca symbol. NO strategy, NO return, NO DB row.
"""
from __future__ import annotations

import csv
import glob
import gzip
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
FTD_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/form13f_raw")
LISTED = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}
PLAIN = re.compile(r"^[A-Z]{1,5}$")


def ftd_map(ftd_dir: Path) -> dict[str, set[str]]:
    m: dict[str, set[str]] = {}
    for f in sorted(glob.glob(str(ftd_dir / "cnsfails*.zip"))):
        with zipfile.ZipFile(f) as z:
            for name in z.namelist():
                for line in z.read(name).decode("latin-1").splitlines()[1:]:
                    p = line.split("|")
                    if len(p) >= 3 and p[1] and p[2]:
                        m.setdefault(p[1], set()).add(p[2])
    return m


def alpaca_symbols() -> tuple[set[str], set[str]]:
    h = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"]}
    base = os.environ.get("ALPACA_TRADING_BASE_URL", "https://paper-api.alpaca.markets")
    out = {}
    for st in ("active", "inactive"):
        r = requests.get(f"{base}/v2/assets", params={"status": st, "asset_class": "us_equity"}, headers=h, timeout=120)
        r.raise_for_status()
        out[st] = {x["symbol"] for x in r.json() if x["exchange"] in LISTED and PLAIN.match(x["symbol"])}
    return out["active"], out["inactive"]


def main() -> int:
    fm = ftd_map(FTD_DIR)
    active, inactive = alpaca_symbols()
    listed = active | inactive
    rows = []
    for path in sorted(HERE.glob("nport_breadth/*_breadth.csv.gz")):
        q = path.name.split("_")[0]
        n_all = n_mapped = n_listed = n_sparse = n_sparse_listed = n_sparse_inactive = 0
        with gzip.open(path, "rt") as f:
            for r in csv.DictReader(f):
                n = int(r["n_filings"])
                n_all += 1
                syms = fm.get(r["cusip"])
                if syms:
                    n_mapped += 1
                    hit = syms & listed
                    if hit:
                        n_listed += 1
                if 5 <= n <= 47:
                    n_sparse += 1
                    if syms and (syms & listed):
                        n_sparse_listed += 1
                        if syms & inactive and not (syms & active):
                            n_sparse_inactive += 1
        rows.append({"quarter": q, "cusips": n_all, "cusips_mapped_by_ftd": n_mapped, "cusips_mapped_to_listed_alpaca": n_listed,
                     "sparse_5_47": n_sparse, "sparse_5_47_listed": n_sparse_listed, "sparse_5_47_listed_now_inactive": n_sparse_inactive})
        print(json.dumps(rows[-1]), flush=True)
    (HERE / "breadth_universe_intersection.json").write_text(json.dumps({"ftd_cusips": len(fm), "alpaca_listed_plain_active": len(active), "alpaca_listed_plain_inactive": len(inactive), "quarters": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
