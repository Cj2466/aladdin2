import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np, yfinance as yf
from datetime import date
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, shares = d["close"], d["shares"]

print("=== identity check (live yfinance .info) ===")
for t in ["BNY","BK","COL","PARA","ECHO","SOLS","STI"]:
    try:
        info = yf.Ticker(t).info
        print(f"  {t:6} name={info.get('longName')!r:55} shares={info.get('sharesOutstanding')} mcap={info.get('marketCap')}")
    except Exception as e:
        print(f"  {t:6} ERROR {e}")

print("\n=== is BK also in the D1 universe? ===")
print("  BK in universe:", "BK" in d["universe"], "| BK priced:", "BK" in close.columns)
print("  BNY in universe:", "BNY" in d["universe"])

print("\n=== BNY share series around the 2021 jump (the fake-dilution risk for Buyback) ===")
sh = shares["BNY"]
w = sh[(sh.index >= "2020-06-01") & (sh.index <= "2022-06-01")]
print(w.to_string())
