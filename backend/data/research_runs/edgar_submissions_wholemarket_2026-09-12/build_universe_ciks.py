"""Step A4.1 — resolve the whole-market price-panel universe to SEC CIKs.

    ./venv/bin/python data/research_runs/edgar_submissions_wholemarket_2026-09-12/build_universe_ciks.py

Input: backend/data/research_runs/whole_market_panel_2026-09-12/universe.csv
(committed on main, 14,737 rows / 14,509 distinct symbols; column
`in_sec_company_tickers` marks the ~7,266 rows Step A1.1 already found present
in SEC's company_tickers.json). This script does NOT trust that column's
boolean as the resolution itself — it re-fetches company_tickers.json fresh
today (SEC's mapping is not static; a re-fetch is the only way to cite a live
CIK rather than an assumption) and resolves every DISTINCT symbol in the
whole universe (not only the pre-marked ones) so a symbol SEC added since
2026-09-12's morning fetch is not silently missed.

Writes:
  - company_tickers_2026-09-12.json   (raw SEC response, verbatim)
  - company_tickers_2026-09-12.sha256 (hash of the exact bytes fetched)
  - universe_ciks.csv                 (symbol, cik, entity_name — resolved only)
  - universe_cik_resolution_report.json (counts: resolved / unresolved / distinct CIKs)

Rate/etiquette: a single GET, SEC's declared user-agent convention (same
token cross_sectional_pead.py uses), no loop.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.services.research_lab.cross_sectional_pead import (
    PEAD_SEC_USER_AGENT,
    SEC_COMPANY_TICKERS_URL,
)

HERE = Path(__file__).resolve().parent
UNIVERSE_CSV = _BACKEND / "data" / "research_runs" / "whole_market_panel_2026-09-12" / "universe.csv"
RAW_JSON = HERE / "company_tickers_2026-09-12.json"
RAW_HASH = HERE / "company_tickers_2026-09-12.sha256"
OUT_CSV = HERE / "universe_ciks.csv"
OUT_REPORT = HERE / "universe_cik_resolution_report.json"


def fetch_company_tickers() -> bytes:
    request = urllib.request.Request(SEC_COMPANY_TICKERS_URL, headers={"User-Agent": PEAD_SEC_USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> int:
    raw_bytes = fetch_company_tickers()
    RAW_JSON.write_bytes(raw_bytes)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    RAW_HASH.write_text(f"{digest}  company_tickers_2026-09-12.json\n")
    print(f"fetched {SEC_COMPANY_TICKERS_URL} -> {len(raw_bytes):,} bytes, sha256={digest}")

    raw = json.loads(raw_bytes)
    # {ticker: (cik, entity_name)} -- last row wins on a duplicate ticker,
    # matching load_cik_map's own dict-comprehension semantics exactly (it is
    # not re-derived here; this is the same {row["ticker"]: cik_str} shape
    # SEC serves, just carrying entity_name through too).
    ticker_to_cik: dict[str, tuple[int, str]] = {}
    for row in raw.values():
        ticker_to_cik[row["ticker"]] = (int(row["cik_str"]), str(row.get("title") or ""))
    print(f"company_tickers.json: {len(ticker_to_cik)} distinct tickers mapped")

    with UNIVERSE_CSV.open() as f:
        universe_rows = list(csv.DictReader(f))
    distinct_symbols = sorted({r["symbol"] for r in universe_rows})
    print(f"universe.csv: {len(universe_rows)} rows, {len(distinct_symbols)} distinct symbols")

    resolved: list[tuple[str, int, str]] = []
    unresolved: list[str] = []
    for sym in distinct_symbols:
        hit = ticker_to_cik.get(sym)
        if hit is None:
            unresolved.append(sym)
        else:
            cik, name = hit
            resolved.append((sym, cik, name))

    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "cik", "entity_name"])
        for sym, cik, name in resolved:
            w.writerow([sym, cik, name])

    distinct_ciks = sorted({cik for _sym, cik, _name in resolved})
    marked_true = sorted({r["symbol"] for r in universe_rows if r["in_sec_company_tickers"] == "True"})
    marked_true_but_unresolved = sorted(set(marked_true) - {s for s, _c, _n in resolved})
    resolved_but_marked_false = sorted({s for s, _c, _n in resolved} - set(marked_true))

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_url": SEC_COMPANY_TICKERS_URL,
        "source_sha256": digest,
        "source_bytes": len(raw_bytes),
        "universe_csv": str(UNIVERSE_CSV.relative_to(_BACKEND)),
        "n_universe_rows": len(universe_rows),
        "n_distinct_symbols": len(distinct_symbols),
        "n_resolved_symbols": len(resolved),
        "n_unresolved_symbols": len(unresolved),
        "n_distinct_ciks": len(distinct_ciks),
        "n_marked_true_in_universe_csv": len(marked_true),
        "n_marked_true_but_unresolved_today": len(marked_true_but_unresolved),
        "n_resolved_today_but_marked_false": len(resolved_but_marked_false),
        "marked_true_but_unresolved_today_sample": marked_true_but_unresolved[:50],
        "resolved_today_but_marked_false_sample": resolved_but_marked_false[:50],
        "unresolved_symbols_sample": unresolved[:50],
    }
    OUT_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(f"resolved {len(resolved)} symbols, {len(unresolved)} unresolved")
    print(f"distinct CIKs: {len(distinct_ciks)} (share classes / dual tickers collapse)")
    print(f"universe.csv marked {len(marked_true)} True; of those {len(marked_true_but_unresolved)} "
          f"failed to resolve against today's fresh fetch")
    print(f"{len(resolved_but_marked_false)} symbols resolved today that universe.csv had marked False "
          "(company_tickers.json drifted, or the 2026-09-12 fetch used a different snapshot)")
    print(f"written {OUT_CSV.relative_to(_BACKEND)}")
    print(f"written {OUT_REPORT.relative_to(_BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
