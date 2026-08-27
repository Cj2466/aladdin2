import os
import json
import time
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv('/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/.env')
KEY = os.environ['ALPACA_API_KEY']
SECRET = os.environ['ALPACA_API_SECRET']
HEADERS = {'APCA-API-KEY-ID': KEY, 'APCA-API-SECRET-KEY': SECRET}

TICKERS = """AABA
ABC
ABMD
ADS
AGN
ALTR
ALXN
ANSS
ANTM
ARG
ARNC
ATVI
AVP
BCR
BHGE
BK
BLL
BRCM
BXLT
CA
CBS
CCE
CDAY
CELG
CERN
CFN
CHK
CMA
CMCSK
COG
COV
CPGX
CTL
CTLT
CTRA
CTXS
CVC
CXO
DAY
DFS
DISCA
DISCK
DISH
DNB
DNR
DO
DRE
DTV
DWDP
ENDP
ESV
ETFC
FBHS
FDO
FI
FL
FLIR
FLT
FRC
FTR
GAS
GGP
GMCR
GPS
HAR
HBI
HCBK
HCP
HES
HFC
HOLX
HRS
HSP
IPG
JEC
JNPR
JOY
JWN
K
KORS
KRFT
KSU
LLL
LLTC
LM
LO
LVLT
MJN
MMC
MNK
MON
MRO
MWV
MXIM
MYL
NBL
NLOK
NLSN
PBCT
PCP
PDCO
PEAK
PETM
PKI
PLL
PX
PXD
QEP
RAI
RE
RHT
RTN
SATS
SEE
SIAL
SIVB
SNI
SRCL
STJ
SWN
SWY
SYMC
TEG
TGNA
TIF
TMK
TSS
TWC
TWTR
UTX
VAR
VIAB
VIAC
WBA
WCG
WFM
WIN
WLTW
WRK
WYND
XEC
XL
XLNX""".split()

assert len(TICKERS) == 143, len(TICKERS)

BARS_URL = "https://data.alpaca.markets/v2/stocks/{sym}/bars"
ASSET_URL = "https://paper-api.alpaca.markets/v2/assets/{sym}"


def http_get_json(url, headers, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.getcode(), json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body.decode(errors="replace")}
            if e.code == 429 and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return e.code, parsed
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return -1, {"error": str(e)}


def get_all_bars(sym):
    all_bars = []
    page_token = None
    while True:
        url = (BARS_URL.format(sym=sym) +
               "?timeframe=1Day&start=2015-01-01T00:00:00Z&end=2026-08-26T00:00:00Z"
               "&limit=10000&feed=sip&adjustment=split")
        if page_token:
            url += f"&page_token={page_token}"
        code, data = http_get_json(url, HEADERS)
        if code != 200:
            return None, code, data
        bars = data.get("bars") or []
        all_bars.extend(bars)
        page_token = data.get("next_page_token")
        if not page_token:
            break
    return all_bars, 200, None


def get_asset(sym):
    url = ASSET_URL.format(sym=sym)
    code, data = http_get_json(url, HEADERS)
    return code, data


results = {}
for i, sym in enumerate(TICKERS):
    bars, code, err = get_all_bars(sym)
    acode, adata = get_asset(sym)
    results[sym] = {
        "bars_http_code": code,
        "bars_error": err,
        "bars": bars,
        "asset_http_code": acode,
        "asset": adata,
    }
    n = len(bars) if bars else 0
    first = bars[0]["t"] if bars else None
    last = bars[-1]["t"] if bars else None
    aname = adata.get("name") if isinstance(adata, dict) else None
    astatus = adata.get("status") if isinstance(adata, dict) else None
    print(f"[{i+1}/{len(TICKERS)}] {sym}: bars_code={code} n={n} first={first} last={last} | asset_code={acode} name={aname!r} status={astatus}")
    time.sleep(0.05)

with open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/alpaca_results.json", "w") as f:
    json.dump(results, f)

print("DONE")
