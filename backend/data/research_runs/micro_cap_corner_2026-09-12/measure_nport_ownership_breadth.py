#!/usr/bin/env python
"""Step 0 Day 2 measurement: fund-OWNERSHIP BREADTH of every equity CUSIP in SEC's
N-PORT bulk data, per quarter, 2019q4 -> 2026q2.

WHY. Coval-Stafford's fire-sale mechanism was untestable on S&P 500/600 because
the median stock there has 643 / 246 fund owners (paper: 47) -- see
coval_stafford_firesale_RESULTS.md. The forced-flow corner is where ownership is
sparse. This script measures, without any ticker mapping, how many CUSIPs have
few owners and how much fund money sits in them. NO strategy, NO return, NO DB row.

HOW. Streams FUND_REPORTED_HOLDING.tsv of each quarterly zip through the existing
NportBulkProvider.stream_member_lines (HTTP range requests; nothing stored beyond
the aggregate). For ASSET_CAT == "EC" rows with a real CUSIP, aggregates per
ISSUER_CUSIP: n_filings (distinct ACCESSION_NUMBER = fund-report owners),
value_usd (sum CURRENCY_VALUE). One csv.gz per quarter + summary.json.
"""
from __future__ import annotations

import csv
import gzip
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.market_data import nport_provider as npp

QUARTERS = [f"{y}q{q}" for y in range(2019, 2027) for q in range(1, 5)]
QUARTERS = [q for q in QUARTERS if "2019q4" <= q <= "2026q2"]
OUT = HERE / "nport_breadth"
OUT.mkdir(exist_ok=True)
CUSIP_NA = "999999999"


def one_quarter(provider, quarter: str) -> dict:
    t0 = time.time()
    lines = provider.stream_member_lines(quarter, npp.TABLE_FUND_REPORTED_HOLDING)
    header = next(lines).rstrip("\r").split("\t")
    idx = {h: i for i, h in enumerate(header)}
    i_acc, i_cusip, i_cat, i_val = idx["ACCESSION_NUMBER"], idx["ISSUER_CUSIP"], idx["ASSET_CAT"], idx["CURRENCY_VALUE"]
    owners: dict[str, set[str]] = defaultdict(set)
    value: dict[str, float] = defaultdict(float)
    n_rows = n_ec = 0
    for line in lines:
        n_rows += 1
        parts = line.rstrip("\r").split("\t")
        if len(parts) <= max(i_acc, i_cusip, i_cat, i_val):
            continue
        if parts[i_cat] != "EC":
            continue
        cusip = parts[i_cusip].strip()
        if not cusip or cusip == CUSIP_NA:
            continue
        n_ec += 1
        owners[cusip].add(parts[i_acc])
        try:
            value[cusip] += float(parts[i_val])
        except ValueError:
            pass
    path = OUT / f"{quarter}_breadth.csv.gz"
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cusip", "n_filings", "value_usd"])
        for c in sorted(owners):
            w.writerow([c, len(owners[c]), f"{value[c]:.2f}"])
    counts = sorted(len(s) for s in owners.values())
    def pct(p: float) -> int:
        return counts[min(len(counts) - 1, int(p * len(counts)))] if counts else 0
    rec = {
        "quarter": quarter, "rows_streamed": n_rows, "ec_rows": n_ec, "cusips": len(counts),
        "owners_p10": pct(0.10), "owners_p25": pct(0.25), "owners_p50": pct(0.50), "owners_p75": pct(0.75), "owners_p90": pct(0.90),
        "cusips_le_47_owners": sum(1 for c in counts if c <= 47),
        "cusips_le_20_owners": sum(1 for c in counts if c <= 20),
        "cusips_ge_5_le_47_owners": sum(1 for c in counts if 5 <= c <= 47),
        "seconds": round(time.time() - t0, 1),
    }
    print(json.dumps(rec), flush=True)
    return rec


def main() -> int:
    provider = npp.NportProvider(cache_dir=None)
    summary_path = OUT / "summary.json"
    done = {r["quarter"]: r for r in json.loads(summary_path.read_text())} if summary_path.exists() else {}
    for q in QUARTERS:
        if q in done:
            continue
        try:
            done[q] = one_quarter(provider, q)
        except Exception as exc:  # noqa: BLE001 - record and continue; nothing is invented
            done[q] = {"quarter": q, "error": f"{type(exc).__name__}: {exc}"}
            print(json.dumps(done[q]), flush=True)
        summary_path.write_text(json.dumps([done[k] for k in sorted(done)], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
