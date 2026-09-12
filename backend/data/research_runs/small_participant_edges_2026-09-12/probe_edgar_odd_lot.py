#!/usr/bin/env python
"""Probe 4: does the ODD-LOT PROVISION still exist in US issuer tender offers, and how often?

EDGAR full-text search (free, covers 2001-present) counted by year for the exact phrase
"odd lot" restricted to issuer self-tender forms SC TO-I, and for the phrase in any form.
Measures existence and bet count; it does NOT measure profitability.
"""
import json, time, urllib.request

UA = "aladdin2-research (autoa0792@gmail.com)"
BASE = "https://efts.sec.gov/LATEST/search-index?q=%s&forms=%s&dateRange=custom&startdt=%s&enddt=%s"

def q(phrase, forms, start, end):
    url = ("https://efts.sec.gov/LATEST/search-index?q=" + urllib.parse.quote(f'"{phrase}"') +
           f"&forms={urllib.parse.quote(forms)}&startdt={start}&enddt={end}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    return d

import urllib.parse
for forms in ["SC TO-I", "SC TO-T"]:
    print(f"=== phrase 'odd lot' in {forms} ===")
    for y in range(2011, 2027):
        try:
            d = q("odd lot", forms, f"{y}-01-01", f"{y}-12-31")
            tot = d.get("hits", {}).get("total", {}).get("value")
            print(f"  {y}: filings hit = {tot}")
        except Exception as e:
            print(f"  {y}: ERROR {e!r}")
        time.sleep(0.4)

print("\n=== control: total SC TO-I filings per year (any text) ===")
for y in range(2011, 2027):
    try:
        d = q("the", "SC TO-I", f"{y}-01-01", f"{y}-12-31")
        print(f"  {y}: {d.get('hits',{}).get('total',{}).get('value')}")
    except Exception as e:
        print(f"  {y}: ERROR {e!r}")
    time.sleep(0.4)

# --- appended: distinct issuers behind the 'odd lot' SC TO-I filings, 2023-2026 ---
def unique_ciks(year):
    seen, names = {}, {}
    frm = 0
    while frm < 100:
        url = ("https://efts.sec.gov/LATEST/search-index?q=" + urllib.parse.quote('"odd lot"') +
               f"&forms={urllib.parse.quote('SC TO-I')}&startdt={year}-01-01&enddt={year}-12-31&from={frm}")
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
        except Exception as e:
            print(f"   {year} from={frm} ERROR {e!r}"); break
        hits = d.get("hits", {}).get("hits", [])
        if not hits: break
        for h in hits:
            s = h.get("_source", {})
            for c, n in zip(s.get("ciks", []), s.get("display_names", []) or s.get("ciks", [])):
                seen[c] = n
        frm += len(hits)
        time.sleep(0.3)
    return seen

print("\n=== distinct entities named on 'odd lot' SC TO-I filings (first 100 hits per year) ===")
for y in [2023, 2024, 2025, 2026]:
    s = unique_ciks(y)
    print(f"  {y}: {len(s)} distinct CIKs in the first 100 hits")
    for c, n in list(s.items())[:12]:
        print(f"      {c} {n}")
