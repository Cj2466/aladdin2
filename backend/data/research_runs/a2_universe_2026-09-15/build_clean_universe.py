"""A2 pre-pass 1: build a TRUTHFUL universe table for the whole-market panel.

Fixes two audit defects before A2 runs:
  D1  `_coverage.json` records the REQUESTED window, not the delivered one
      (only 28.8% match; 1,821 symbols claim bars through 2026-09-11 when their
      last real bar is years earlier). Here the delivered window is read from
      the files themselves, one row at a time.
  D3  the panel is not all common stock. Classified from the vendor's own
      `name` text plus SEC company-ticker presence plus listing venue -- NOT
      from the ticker-pattern heuristic used in the audit, which had known
      false positives (EWW, GWW, POWW).

Writes `clean_universe.csv` (one row per symbol) and `clean_universe_summary.json`.
Reads only; never mutates the price store.
"""
import csv, gzip, json, os, re
from collections import Counter, defaultdict

STORE = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1"
UNIVERSE = ("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/research_runs/"
            "whole_market_panel_2026-09-12/universe.csv")
HERE = os.path.dirname(os.path.abspath(__file__))

# Name patterns, most specific first. A symbol takes the FIRST match.
RULES = [
    ("warrant",   r"\bwarrants?\b|\bwts?\b"),
    ("right",     r"\brights?\b"),
    ("unit",      r"\bunits?\b"),
    ("preferred", r"preferred|\bpfd\b|depositary\s+shares?"),
    ("etp",       r"\betf\b|\betn\b|\betp\b|ishares|spdr|invesco|vanguard|proshares|direxion|"
                  r"wisdomtree|\bxtrackers\b|globalx|global\s+x|first\s+trust|vaneck|"
                  r"\bfund\b|\btrust\b(?!\s*co)|\bportfolio\b|\bindex\b|\bshares\b\s*$"),
    ("debt",      r"\bnotes?\b|\bbonds?\b|debenture|\bsenior\b"),
]


def classify(name: str) -> str:
    n = (name or "").lower()
    for label, pat in RULES:
        if re.search(pat, n):
            return label
    return "common"


def delivered_window(path):
    """(first_date, last_date, rows) read from the file itself."""
    first = last = None
    n = 0
    with gzip.open(path, "rt") as fh:
        fh.readline()
        for line in fh:
            d = line.split(",", 1)[0]
            if not d:
                continue
            if first is None:
                first = d
            last = d
            n += 1
    return first, last, n


def main():
    meta = {r["symbol"]: r for r in csv.DictReader(open(UNIVERSE))}
    claimed = json.load(open(os.path.join(STORE, "_coverage.json")))
    files = sorted(f for f in os.listdir(STORE) if f.endswith(".csv.gz"))

    rows = []
    for fn in files:
        sym = fn[:-7]
        first, last, n = delivered_window(os.path.join(STORE, fn))
        m = meta.get(sym, {})
        cl = claimed.get(sym)
        rows.append({
            "symbol": sym,
            "instrument": classify(m.get("name", "")),
            "name": (m.get("name") or "")[:80],
            "exchange": m.get("exchange", ""),
            "vendor_status": m.get("status", ""),
            "in_sec_company_tickers": m.get("in_sec_company_tickers", ""),
            "first_bar": first or "",
            "last_bar": last or "",
            "rows": n,
            "claimed_first": cl[0][0] if cl else "",
            "claimed_last": cl[0][-1] if cl else "",
            "coverage_claim_overstates_end": str(bool(cl and last and cl[0][-1] > last)),
            "in_universe_csv": str(sym in meta),
        })

    out = os.path.join(HERE, "clean_universe.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    inst = Counter(r["instrument"] for r in rows)
    # cross-check the classifier against SEC company-ticker presence:
    # an operating company files with the SEC; an ETP usually does not.
    cross = defaultdict(Counter)
    for r in rows:
        cross[r["instrument"]][r["in_sec_company_tickers"]] += 1

    overstate = sum(1 for r in rows if r["coverage_claim_overstates_end"] == "True")
    missing_meta = sum(1 for r in rows if r["in_universe_csv"] == "False")

    summary = {
        "symbols": len(rows),
        "instrument_counts": dict(inst),
        "instrument_vs_sec_company_tickers": {k: dict(v) for k, v in cross.items()},
        "coverage_json_overstates_end": overstate,
        "symbols_missing_from_universe_csv": missing_meta,
        "common_stock_symbols": inst["common"],
        "common_stock_rows": sum(r["rows"] for r in rows if r["instrument"] == "common"),
        "all_rows": sum(r["rows"] for r in rows),
    }
    json.dump(summary, open(os.path.join(HERE, "clean_universe_summary.json"), "w"), indent=1)

    print(f"symbols: {len(rows):,}   rows: {summary['all_rows']:,}")
    print("\n=== instrument mix (vendor name text) ===")
    for k, v in inst.most_common():
        print(f"  {k:10s}: {v:6,d}  ({v/len(rows)*100:5.1f}%)")
    print("\n=== classifier cross-check vs SEC company-ticker presence ===")
    print("  (an operating company files with the SEC; an ETP normally does not)")
    for k in sorted(cross):
        t = cross[k].get("True", 0); f = cross[k].get("False", 0)
        tot = t + f
        print(f"  {k:10s}: in SEC {t:5,d} / not {f:5,d}   -> {t/tot*100:5.1f}% file with SEC")
    print(f"\ncommon stock: {inst['common']:,} symbols, "
          f"{summary['common_stock_rows']:,} rows "
          f"({summary['common_stock_rows']/summary['all_rows']*100:.1f}% of the panel)")
    print(f"_coverage.json overstates the end date for {overstate:,} symbols")
    print(f"symbols with no row in universe.csv: {missing_meta:,}")


if __name__ == "__main__":
    main()
