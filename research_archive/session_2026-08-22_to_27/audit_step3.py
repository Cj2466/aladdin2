import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
pd.set_option("display.width", 200)
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, shares, splits = d["close"], d["shares"], d["splits"]

for t in ["STI","PARA","NE","TE","DOW","SBNY"]:
    sh = shares[t]; px = close[t].dropna()
    print(f"\n===== {t} : {len(px)} price rows {px.index[0].date()}..{px.index[-1].date()} | {len(sh)} share obs =====")
    print("  price head:", [f"{i.date()}:{v:.2f}" for i,v in px.head(3).items()])
    print("  shares (yearly first obs):")
    yr = sh.groupby(sh.index.year).agg(["first","last","count"])
    print(yr.to_string().replace("\n","\n    "))
    # biggest non-split jumps in the share series
    r = (sh / sh.shift(1)).dropna()
    big = r[(r > 1.5) | (r < 0.667)]
    sp = splits.get(t)
    print(f"  splits in window: {dict(zip([str(i.date()) for i in sp.index], sp.values)) if sp is not None and len(sp) else 'none'}")
    print(f"  share-count jumps >1.5x or <0.667x: {len(big)}")
    for i,v in big.items():
        print(f"      {i.date()}  x{v:.4f}   ({sh.shift(1)[i]:.4g} -> {sh[i]:.4g})")
