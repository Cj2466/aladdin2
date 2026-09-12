#!/usr/bin/env python
"""Re-check every number asserted in M2_RESULT.md against the committed artefacts.

Deliberately does NOT import m2_odd_lot_offers: it recomputes the bet population, the premium
quantiles and the dollar round-trip from m2_offers.csv with its own code, so a bug in the
measurement module cannot reproduce itself in the check (project rule, 2026-09-11: an
independent re-derivation must not share helpers).  It also re-hashes every source file quoted
in m2_SOURCES.md and confirms the two verbatim legal/literature quotations are present in the
committed extracts.

Run from this directory.  Exits non-zero on the first failed check.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILED: list[str] = []


def check(name: str, ok: bool) -> None:
    print(("PASS  " if ok else "FAIL  ") + name)
    if not ok:
        FAILED.append(name)


def pctl(xs: list[float], q: float) -> float:
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def main() -> int:
    summ = json.loads((HERE / "m2_output.json").read_text())["summary"]
    rows = list(csv.DictReader((HERE / "m2_offers.csv").open()))
    bets = [
        r
        for r in rows
        if r["listed_status"] == "listed"
        and r["odd_lot_priority"] == "yes"
        and r["tendered_class"] == "common_or_unspecified"
    ]
    prem = sorted(float(r["gross_premium"]) for r in bets if r["gross_premium"])
    stakes = [99 * float(r["doc_ref_price"]) for r in bets if r["gross_premium"]]
    gains = sorted(
        99 * float(r["doc_ref_price"]) * float(r["gross_premium"])
        for r in bets
        if r["gross_premium"]
    )

    check("census: 1,175 hit filings -> 348 offers, 176 CIKs",
          summ["hit_filings_retrieved"] == 1175 and summ["distinct_offers"] == 348
          and summ["distinct_ciks"] == 176 and len(rows) == 348)
    check("bet population: 103 bets, 79 distinct issuers",
          len(bets) == 103 and len({r["cik"] for r in bets}) == 79)
    check("bets per year 2019-2026 = 17,17,19,16,15,8,5,6",
          [summ["per_year"][y]["bets"] for y in
           ("2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026")]
          == [17, 17, 19, 16, 15, 8, 5, 6])
    check("clause verdicts partition the census: 257 grant + 7 deny + 84 mention = 348",
          summ["priority_yes"] == 257 and summ["priority_denied"] == 7
          and summ["priority_mentioned_only"] == 84
          and summ["priority_yes"] + summ["priority_denied"]
          + summ["priority_mentioned_only"] + summ["priority_absent"] == 348)
    check("listing split: 142 listed / 130 non-traded / 76 unknown = 348",
          summ["listed_count"] + summ["non_traded_count"] + summ["unknown_listing_count"] == 348
          and summ["non_traded_count"] == 130)
    check("premium quantiles: p10 -2.71, p25 +0.91, median +4.21, p75 +10.71, p90 +24.42 (N 78)",
          len(prem) == 78
          and [round(pctl(prem, q) * 100, 2) for q in (0.10, 0.25, 0.50, 0.75, 0.90)]
          == [-2.71, 0.91, 4.21, 10.71, 24.42])
    check("premium shape: 64 of 78 positive, mean +11.48%, min -39.52%, max +284.6%",
          sum(1 for x in prem if x > 0) == 64
          and round(statistics.mean(prem) * 100, 2) == 11.48
          and round(min(prem) * 100, 2) == -39.52 and round(max(prem) * 100, 1) == 284.6)
    check("48 of 78 premiums use a Dutch range midpoint",
          summ["premium_midpoint_flagged_n"] == 48)
    check("completion 98 of 103 bets (95.1%)", summ["bets_completed_yes"] == 98)
    check("holding period median 29d (p25 28, p75 38, N 57)",
          (summ["holding_days_median"], summ["holding_days_p25"],
           summ["holding_days_p75"], summ["holding_days_n"]) == (29.0, 28.0, 38.0, 57))
    check("99-share round trip: stake median $2,381.94, gross gain median $63.11",
          round(statistics.median(sorted(stakes)), 2) == 2381.94
          and round(statistics.median(gains), 2) == 63.11)
    check("99-share round trip: p25 $12.99, p75 $207.03, 14 of 78 lose after $2",
          round(pctl(gains, 0.25), 2) == 12.99 and round(pctl(gains, 0.75), 2) == 207.03
          and sum(1 for g in gains if g - 2 <= 0) == 14)
    check("free-feed cross-check: yfinance within 2% of the document print on 69 of 86",
          (summ["yf_vs_document_price_within_2pct"], summ["yf_vs_document_price_n"]) == (69, 86))
    check("7 split-off exchange offers among the bets",
          sum(1 for r in bets if r["offer_type"] == "split_off_exchange_offer") == 7)
    check("6 of the 7 explicit denials are dated 2024 or later",
          sum(1 for r in rows
              if r["odd_lot_priority"] == "no_explicitly_denied"
              and r["launch_date"] >= "2024") == 6)

    md = (HERE / "m2_SOURCES.md").read_text()
    named = re.findall(r"`([A-Za-z0-9_.\-]+\.(?:txt|html))`[^|]*\| `([0-9a-f]{64})`", md)
    check(f"m2_SOURCES.md names {len(named)} hashed files", len(named) >= 19)
    for fname, sha in named:
        path = HERE / "m2_sources" / fname
        if fname.endswith(".html"):
            check(f"{fname}: committed bytes hash to the recorded sha256",
                  path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == sha)
        else:
            hdr = re.search(r"SHA-256 \(raw document as fetched\): ([0-9a-f]{64})",
                            path.read_text() if path.exists() else "")
            check(f"{fname}: extract header carries the recorded sha256",
                  bool(hdr) and hdr.group(1) == sha)

    ecfr = (HERE / "m2_sources" / "ecfr_240.13e-4.txt").read_text()
    check("17 CFR 240.13e-4(f)(3)(i) carve-out is verbatim in the committed eCFR text",
          "shall not prohibit the issuer or affiliate making the issuer tender offer from: "
          "( i ) Accepting all securities tendered by persons who own, beneficially or of "
          "record, an aggregate of not more than a specified number which is less than one "
          "hundred shares of such security and who tender all their securities, before "
          "prorating securities tendered by others" in ecfr)
    check("the word 'odd' appears zero times in 240.13e-4 (why the review's search missed it)",
          len(re.findall(r"(?i)odd", ecfr)) == 0)

    kad = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", (
        HERE / "m2_sources" / "kadapakkam_zhang_yildirim_2021_scholarsmine.html"
    ).read_text(errors="replace")))
    check("Kadapakkam 2021 abstract quotes are verbatim in the committed page",
          "abnormal profits from tendering have disappeared" in kad
          and "no longer significant after adjustments for transaction costs" in kad)

    print()
    if FAILED:
        print(f"{len(FAILED)} CHECK(S) FAILED")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
