import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, mcap_close, shares, splits = d["close"], d["mcap_close"], d["shares"], d["splits"]
mcap_close = mcap_close.reindex(index=close.index, columns=close.columns)

for t in ["BNY","AIV","COL","PARA","CNX"]:
    sh = shares[t]; px = close[t].dropna(); mpx = mcap_close[t].dropna()
    sp = splits.get(t)
    print(f"\n===== {t} =====")
    print(f"  adj price  {px.index[0].date()}..{px.index[-1].date()}  n={len(px)}  first={px.iloc[0]:.4g} last={px.iloc[-1]:.4g}")
    print(f"  mcap price {mpx.index[0].date()}..{mpx.index[-1].date()} n={len(mpx)} first={mpx.iloc[0]:.4g} last={mpx.iloc[-1]:.4g}")
    print(f"  shares     {pd.Timestamp(sh.index[0]).date()}..{pd.Timestamp(sh.index[-1]).date()} n={len(sh)}  min={sh.min():.4g} max={sh.max():.4g}")
    print(f"  splits: {dict(zip([str(i.date()) for i in sp.index], [round(float(v),5) for v in sp.values])) if sp is not None and len(sp) else 'none'}")
    yr = sh.groupby(sh.index.year).agg(["first","last","count"])
    print("  shares by year:"); print("    " + yr.to_string().replace("\n","\n    "))
