#!/usr/bin/env python
"""Does SEC's free Financial Statement Data Set carry the accounting inputs the
buildable OSAP predictors need, and for how many filers?

Downloads one or more quarterly ZIPs (https://www.sec.gov/files/dera/data/
financial-statement-data-sets/<q>.zip), streams num.txt, and counts DISTINCT
CIKs reporting each tag as a consolidated fact (empty `segments` and `coreg`).
Writes fsds_coverage_<q>.json. Downloads to a temp dir and deletes them: one
quarter is ~100-125 MB zipped, ~490 MB for num.txt alone.

Run: measure_fsds_coverage.py 2016q1 2024q1
"""
from __future__ import annotations

import collections
import csv
import json
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = "aladdin2 research autoa0792@gmail.com"
URL = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/{q}.zip"

# Compustat field -> candidate us-gaap tags, in the order a builder would try them.
TAG_LADDERS: dict[str, list[str]] = {
    "at": ["Assets"],
    "ceq": ["StockholdersEquity"],
    "act": ["AssetsCurrent"],
    "lct": ["LiabilitiesCurrent"],
    "che": ["CashAndCashEquivalentsAtCarryingValue"],
    "invt": ["InventoryNet"],
    "ni": ["NetIncomeLoss"],
    "oiadp": ["OperatingIncomeLoss"],
    "gp_direct": ["GrossProfit"],
    "sale": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
             "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet", "SalesRevenueServicesNet"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfServices"],
    "oancf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "fincf": ["NetCashProvidedByUsedInFinancingActivities", "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations"],
    "ivncf": ["NetCashProvidedByUsedInInvestingActivities", "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations"],
    "sstk": ["ProceedsFromIssuanceOfCommonStock"],
    "prstkc": ["PaymentsForRepurchaseOfCommonStock"],
    "dv": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "dltis": ["ProceedsFromIssuanceOfLongTermDebt"],
    "dltr": ["RepaymentsOfLongTermDebt"],
    "txt": ["IncomeTaxExpenseBenefit"],
    "txdi": ["DeferredIncomeTaxExpenseBenefit"],
    "txfed": ["CurrentFederalTaxExpenseBenefit"],
    "txfo": ["CurrentForeignTaxExpenseBenefit"],
    "shrout": ["CommonStockSharesOutstanding", "CommonStockSharesIssued", "WeightedAverageNumberOfSharesOutstandingBasic",
               "EntityCommonStockSharesOutstanding"],
    "ib": ["IncomeLossFromContinuingOperations",
           "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest"],
}
ALL_TAGS = {t for ladder in TAG_LADDERS.values() for t in ladder}


def measure(quarter: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / f"{quarter}.zip"
        req = urllib.request.Request(URL.format(q=quarter), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=600) as r, open(zpath, "wb") as out:
            out.write(r.read())
        with zipfile.ZipFile(zpath) as z:
            z.extract("sub.txt", tmp)
            z.extract("num.txt", tmp)
        adsh_to_cik = {}
        forms = collections.Counter()
        with open(Path(tmp) / "sub.txt", encoding="latin-1", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                adsh_to_cik[row["adsh"]] = row["cik"]
                forms[row["form"]] += 1
        ciks_by_tag: dict[str, set[str]] = collections.defaultdict(set)
        all_ciks: set[str] = set()
        with open(Path(tmp) / "num.txt", encoding="latin-1", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader)
            idx = {h: i for i, h in enumerate(header)}
            for row in reader:
                if len(row) <= idx["value"]:
                    continue
                cik = adsh_to_cik.get(row[idx["adsh"]])
                if cik:
                    all_ciks.add(cik)
                tag = row[idx["tag"]]
                if tag in ALL_TAGS and cik and row[idx["value"]] and not row[idx["segments"]] and not row[idx["coreg"]]:
                    ciks_by_tag[tag].add(cik)
    n = len(all_ciks)
    per_tag = {t: len(s) for t, s in ciks_by_tag.items()}
    per_field = {}
    for field, ladder in TAG_LADDERS.items():
        union = set().union(*[ciks_by_tag[t] for t in ladder]) if ladder else set()
        per_field[field] = {"ladder_union_ciks": len(union), "ladder_union_pct": round(100 * len(union) / n, 1),
                            "per_tag": {t: per_tag.get(t, 0) for t in ladder}}
    return {"quarter": quarter, "ciks_with_any_fact": n, "filings": sum(forms.values()),
            "forms_top": dict(forms.most_common(6)), "per_field": per_field}


def main() -> int:
    quarters = sys.argv[1:] or ["2016q1", "2024q1"]
    out = [measure(q) for q in quarters]
    (HERE / "fsds_coverage.json").write_text(json.dumps(out, indent=1))
    for rec in out:
        print(f"=== {rec['quarter']}: {rec['ciks_with_any_fact']} CIKs, {rec['filings']} filings")
        for field, v in sorted(rec["per_field"].items(), key=lambda kv: -kv[1]["ladder_union_pct"]):
            print(f"  {field:10s} {v['ladder_union_pct']:5.1f}%  {v['per_tag']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
