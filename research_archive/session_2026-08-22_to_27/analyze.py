import json

with open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/alpaca_results.json") as f:
    results = json.load(f)

# My independently-researched real historical S&P 500 company name for each
# of the 143 tickers (the company that ACTUALLY held this ticker while an
# S&P 500 member, per general financial-history knowledge / point-in-time
# membership context), used to sanity-check against Alpaca's /v2/assets name.
EXPECTED_NAME = {
    "AABA": "Altaba / Yahoo!",
    "ABC": "AmerisourceBergen",
    "ABMD": "Abiomed",
    "ADS": "Alliance Data Systems",
    "AGN": "Allergan",
    "ALTR": "Altera",
    "ALXN": "Alexion Pharmaceuticals",
    "ANSS": "ANSYS",
    "ANTM": "Anthem",
    "ARG": "Airgas",
    "ARNC": "Arconic",
    "ATVI": "Activision Blizzard",
    "AVP": "Avon Products",
    "BCR": "C. R. Bard",
    "BHGE": "Baker Hughes a GE Company",
    "BK": "Bank of New York Mellon",
    "BLL": "Ball Corporation",
    "BRCM": "Broadcom Corporation (pre-Avago)",
    "BXLT": "Baxalta",
    "CA": "CA, Inc. (Computer Associates)",
    "CBS": "CBS Corporation",
    "CCE": "Coca-Cola Enterprises",
    "CDAY": "Ceridian HCM / Dayforce",
    "CELG": "Celgene",
    "CERN": "Cerner",
    "CFN": "CareFusion",
    "CHK": "Chesapeake Energy",
    "CMA": "Comerica",
    "CMCSK": "Comcast (Special Class A)",
    "COG": "Cabot Oil & Gas",
    "COV": "Covidien",
    "CPGX": "Columbia Pipeline Group",
    "CTL": "CenturyLink",
    "CTLT": "Catalent",
    "CTRA": "Coterra Energy",
    "CTXS": "Citrix Systems",
    "CVC": "Cablevision Systems",
    "CXO": "Concho Resources",
    "DAY": "Dayforce (formerly Ceridian)",
    "DFS": "Discover Financial Services",
    "DISCA": "Discovery Inc Class A",
    "DISCK": "Discovery Inc Class C",
    "DISH": "DISH Network",
    "DNB": "Dun & Bradstreet",
    "DNR": "Denbury Resources",
    "DO": "Diamond Offshore Drilling",
    "DRE": "Duke Realty",
    "DTV": "DIRECTV",
    "DWDP": "DowDuPont",
    "ENDP": "Endo International",
    "ESV": "Ensco / Valaris",
    "ETFC": "E*TRADE Financial",
    "FBHS": "Fortune Brands Home & Security",
    "FDO": "Family Dollar Stores",
    "FI": "Fiserv",
    "FL": "Foot Locker",
    "FLIR": "FLIR Systems",
    "FLT": "FLEETCOR Technologies / Corpay",
    "FRC": "First Republic Bank",
    "FTR": "Frontier Communications",
    "GAS": "AGL Resources",
    "GGP": "General Growth Properties",
    "GMCR": "Keurig Green Mountain",
    "GPS": "Gap Inc.",
    "HAR": "Harman International",
    "HBI": "Hanesbrands",
    "HCBK": "Hudson City Bancorp",
    "HCP": "HCP Inc / Healthpeak",
    "HES": "Hess Corporation",
    "HFC": "HollyFrontier / HF Sinclair",
    "HOLX": "Hologic",
    "HRS": "Harris Corporation",
    "HSP": "Hospira",
    "IPG": "Interpublic Group",
    "JEC": "Jacobs Engineering",
    "JNPR": "Juniper Networks",
    "JOY": "Joy Global",
    "JWN": "Nordstrom",
    "K": "Kellogg / Kellanova",
    "KORS": "Michael Kors / Capri Holdings",
    "KRFT": "Kraft Foods Group",
    "KSU": "Kansas City Southern",
    "LLL": "L3 Technologies",
    "LLTC": "Linear Technology",
    "LM": "Legg Mason",
    "LO": "Lorillard",
    "LVLT": "Level 3 Communications",
    "MJN": "Mead Johnson Nutrition",
    "MMC": "Marsh & McLennan",
    "MNK": "Mallinckrodt",
    "MON": "Monsanto",
    "MRO": "Marathon Oil",
    "MWV": "MeadWestvaco",
    "MXIM": "Maxim Integrated Products",
    "MYL": "Mylan",
    "NBL": "Noble Energy",
    "NLOK": "NortonLifeLock / Gen Digital",
    "NLSN": "Nielsen Holdings",
    "PBCT": "People's United Financial",
    "PCP": "Precision Castparts",
    "PDCO": "Patterson Companies",
    "PEAK": "Healthpeak Properties",
    "PETM": "PetSmart",
    "PKI": "PerkinElmer / Revvity",
    "PLL": "Pall Corporation",
    "PX": "Praxair",
    "PXD": "Pioneer Natural Resources",
    "QEP": "QEP Resources",
    "RAI": "Reynolds American",
    "RE": "Everest Re Group",
    "RHT": "Red Hat",
    "RTN": "Raytheon Company",
    "SATS": "EchoStar Corporation",
    "SEE": "Sealed Air",
    "SIAL": "Sigma-Aldrich",
    "SIVB": "SVB Financial Group / Silicon Valley Bank",
    "SNI": "Scripps Networks Interactive",
    "SRCL": "Stericycle",
    "STJ": "St. Jude Medical",
    "SWN": "Southwestern Energy",
    "SWY": "Safeway",
    "SYMC": "Symantec",
    "TEG": "Integrys Energy Group",
    "TGNA": "TEGNA",
    "TIF": "Tiffany & Co.",
    "TMK": "Torchmark / Globe Life",
    "TSS": "Total System Services",
    "TWC": "Time Warner Cable",
    "TWTR": "Twitter",
    "UTX": "United Technologies",
    "VAR": "Varian Medical Systems",
    "VIAB": "Viacom Inc (old)",
    "VIAC": "ViacomCBS",
    "WBA": "Walgreens Boots Alliance",
    "WCG": "WellCare Health Plans",
    "WFM": "Whole Foods Market",
    "WIN": "Windstream Holdings",
    "WLTW": "Willis Towers Watson",
    "WRK": "WestRock",
    "WYND": "Wyndham Worldwide",
    "XEC": "Cimarex Energy",
    "XL": "XL Group",
    "XLNX": "Xilinx",
}

resolved = []
unresolved = []
recycled_flags = []

def to_date(ts):
    return ts[:10] if ts else None

for sym, r in results.items():
    bars = r.get("bars") or []
    bars_code = r.get("bars_http_code")
    asset = r.get("asset") if isinstance(r.get("asset"), dict) else {}
    asset_code = r.get("asset_http_code")
    aname = asset.get("name")
    astatus = asset.get("status")

    has_bars = bool(bars) and bars_code == 200
    has_asset = asset_code == 200 and isinstance(asset, dict) and asset.get("symbol")

    if not has_bars and not has_asset:
        unresolved.append({"ticker": sym, "bars_code": bars_code, "asset_code": asset_code,
                            "asset_error": asset if not has_asset else None,
                            "bars_error": r.get("bars_error")})
        continue

    first_date = to_date(bars[0]["t"]) if bars else None
    last_date = to_date(bars[-1]["t"]) if bars else None
    n = len(bars)

    # discontinuity scan: >5x jump or <1/5 drop close-to-close, single day
    jumps = []
    for i in range(1, len(bars)):
        prev_c = bars[i-1]["c"]
        cur_c = bars[i]["c"]
        if prev_c and prev_c > 0:
            ratio = cur_c / prev_c
            if ratio >= 5.0 or ratio <= 0.2:
                jumps.append({
                    "date": to_date(bars[i]["t"]),
                    "prev_date": to_date(bars[i-1]["t"]),
                    "prev_close": prev_c,
                    "cur_close": cur_c,
                    "ratio": ratio,
                })

    resolved.append({
        "ticker": sym,
        "bars_n": n,
        "first_bar_date": first_date,
        "last_bar_date": last_date,
        "asset_name": aname,
        "asset_status": astatus,
        "expected_company": EXPECTED_NAME.get(sym),
        "price_jumps": jumps,
    })

    if jumps:
        recycled_flags.append({"ticker": sym, "jumps": jumps, "asset_name": aname,
                                "expected_company": EXPECTED_NAME.get(sym), "last_bar_date": last_date,
                                "first_bar_date": first_date, "bars_n": n})

print("=== SUMMARY ===")
print("total checked:", len(results))
print("resolved (bars or asset found):", len(resolved))
print("unresolved:", len(unresolved))
print("flagged for price discontinuity:", len(recycled_flags))
print()

print("=== UNRESOLVED ===")
for u in unresolved:
    print(u["ticker"], "bars_code=", u["bars_code"], "asset_code=", u["asset_code"], u.get("asset_error"))

print()
print("=== RESOLVED WITH NO BARS BUT ASSET FOUND (edge case) ===")
for r in resolved:
    if r["bars_n"] == 0:
        print(r["ticker"], r["asset_name"], r["asset_status"])

print()
print("=== PRICE DISCONTINUITY FLAGS ===")
for f in recycled_flags:
    print(f"{f['ticker']}: expected={f['expected_company']!r} alpaca_name={f['asset_name']!r} bars={f['first_bar_date']}..{f['last_bar_date']} n={f['bars_n']}")
    for j in f["jumps"]:
        print(f"    JUMP {j['prev_date']} (close={j['prev_close']}) -> {j['date']} (close={j['cur_close']}) ratio={j['ratio']:.3f}")

print()
print("=== NAME MISMATCH CANDIDATES (heuristic, needs manual review) ===")
for r in resolved:
    exp = (r["expected_company"] or "").lower()
    got = (r["asset_name"] or "").lower()
    if not got:
        continue
    # crude token overlap check
    exp_tokens = set(exp.replace(",", "").replace(".", "").split())
    got_tokens = set(got.replace(",", "").replace(".", "").split())
    stop = {"inc", "corp", "corporation", "company", "co", "the", "group", "inc.", "plc", "holdings", "companies", "&"}
    exp_tokens -= stop
    got_tokens -= stop
    overlap = exp_tokens & got_tokens
    if not overlap and exp_tokens and got_tokens:
        print(f"{r['ticker']}: expected={r['expected_company']!r} vs alpaca={r['asset_name']!r} (status={r['asset_status']}) last_bar={r['last_bar_date']}")

with open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/analysis_output.json", "w") as f:
    json.dump({"resolved": resolved, "unresolved": unresolved, "recycled_flags": recycled_flags}, f, indent=2)
