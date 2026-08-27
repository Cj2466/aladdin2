import json

import httpx

env = {}
with open("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/.env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

KEY = env["ALPACA_API_KEY"]
SEC = env["ALPACA_API_SECRET"]
BASE = "https://paper-api.alpaca.markets/v2"
H = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC}

with httpx.Client(timeout=20) as c:
    for path in ("/account", "/clock", "/positions", "/orders?status=open"):
        r = c.get(BASE + path, headers=H)
        print("=== GET", path, "->", r.status_code)
        try:
            body = r.json()
        except Exception:
            print(r.text[:500])
            continue
        if isinstance(body, list):
            print("  list len:", len(body))
            if body:
                print(json.dumps(body[0], indent=2)[:2000])
        else:
            print(json.dumps(body, indent=2)[:2500])
