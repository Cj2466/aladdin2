import os, json, time, urllib.request, urllib.error, sys
from dotenv import load_dotenv

load_dotenv('/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/.env')
KEY = os.environ['ALPACA_API_KEY']
SECRET = os.environ['ALPACA_API_SECRET']
HEADERS = {'APCA-API-KEY-ID': KEY, 'APCA-API-SECRET-KEY': SECRET}

BARS_URL = "https://data.alpaca.markets/v2/stocks/{sym}/bars"
ASSET_URL = "https://paper-api.alpaca.markets/v2/assets/{sym}"

def http_get_json(url, headers, retries=4):
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
                time.sleep(2 * (attempt + 1)); continue
            return e.code, parsed
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1)); continue
            return -1, {"error": str(e)}

def get_all_bars(sym, end="2026-08-25T00:00:00Z"):
    all_bars = []
    page_token = None
    while True:
        url = (BARS_URL.format(sym=sym) +
               f"?timeframe=1Day&start=2015-01-01T00:00:00Z&end={end}"
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
    return http_get_json(ASSET_URL.format(sym=sym), HEADERS)

def flatline_scan(bars):
    """Detect flatline (volume==0, price constant) stretches and where real
    volume resumes -- the signature the build report used for recycling."""
    events = []
    prev_vol_zero = False
    for i in range(1, len(bars)):
        v = bars[i].get('v', 0)
        pv = bars[i-1].get('v', 0)
        c = bars[i].get('c'); pc = bars[i-1].get('c')
        if pc and c:
            ratio = c / pc
            if ratio > 5 or ratio < 0.2:
                events.append(("JUMP", bars[i-1]['t'], bars[i]['t'], pc, c, ratio))
        if v == 0 and pv > 0:
            events.append(("FLATLINE_START", bars[i]['t'], None, pc, c, None))
        if v > 0 and pv == 0:
            events.append(("VOLUME_RESUME", bars[i]['t'], None, pc, c, None))
    return events

def summarize(sym, tag=""):
    bars, code, err = get_all_bars(sym)
    acode, adata = get_asset(sym)
    if code != 200:
        print(f"{tag}{sym}: BARS_HTTP_ERROR code={code} err={err}")
        return
    n = len(bars) if bars else 0
    if n == 0:
        aname = adata.get('name') if isinstance(adata, dict) else None
        astatus = adata.get('status') if isinstance(adata, dict) else None
        print(f"{tag}{sym}: ZERO BARS. asset_code={acode} name={aname!r} status={astatus}")
        return
    first = bars[0]['t'][:10]
    last = bars[-1]['t'][:10]
    aname = adata.get('name') if isinstance(adata, dict) else None
    astatus = adata.get('status') if isinstance(adata, dict) else None
    aclass = adata.get('class') if isinstance(adata, dict) else None
    tradable = adata.get('tradable') if isinstance(adata, dict) else None
    events = flatline_scan(bars)
    ev_str = "; ".join(f"{e[0]}@{e[1][:10]}" + (f"->{e[2][:10]} {e[3]}->{e[4]} x{e[5]:.2f}" if e[0]=="JUMP" else f" c={e[3]}->{e[4]}") for e in events[:12])
    print(f"{tag}{sym}: n={n} first={first} last={last} | asset name={aname!r} status={astatus} class={aclass} tradable={tradable} | events=[{ev_str}]")
    return {"sym": sym, "n": n, "first": first, "last": last, "asset_name": aname,
            "asset_status": astatus, "events": events, "bars": bars}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "clean"

    CLEAN_SPOTCHECK = ["DISCA","DISCK","TWTR","XLNX","SIVB","FRC","ABC","BRCM","PCP",
                        "GMCR","CPGX","BXLT","TWC","CELG","JNPR"]

    RECYCLE_HUNT = ["RTN","ESV","CXO","QEP","DNR","LVLT","JOY","BCR","HAR","CVC",
                     "GGP","WFM","SNI","STJ","MYL","CTL","TSS","WCG","COG","XEC"]

    targets = CLEAN_SPOTCHECK if mode == "clean" else RECYCLE_HUNT
    results = {}
    for t in targets:
        r = summarize(t, tag="[CLEAN] " if mode=="clean" else "[HUNT] ")
        if r:
            results[t] = r
        time.sleep(0.1)

    outpath = f"/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/my_verify_{mode}.json"
    with open(outpath, "w") as f:
        json.dump(results, f, default=str)
    print("DONE", mode)
