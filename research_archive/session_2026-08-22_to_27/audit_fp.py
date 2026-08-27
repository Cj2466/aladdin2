import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, shares, splits = d["close"], d["shares"], d["splits"]
mc = pd.read_pickle(f"{SP}/audit_mcap.pkl")
for t in ["COHR","NKTR","ENPH","TTD","SEDG","XRX","SMCI","ARES","ECHO","CVNA","DDOG"]:
    m = mc[t].dropna(); bad = m[(m<1e9)|(m>6e12)]
    sp = splits.get(t)
    px = close[t].dropna()
    print(f"\n{t}: cap range ${m.min()/1e9:.3f}B..${m.max()/1e9:.1f}B | {len(bad)} bad cells "
          f"{bad.index[0].date() if len(bad) else '-'}..{bad.index[-1].date() if len(bad) else '-'}")
    print(f"   splits: {dict(zip([str(i.date()) for i in sp.index],[round(float(v),4) for v in sp.values])) if sp is not None and len(sp) else 'none'}")
    if len(bad):
        dt = bad.index[len(bad)//2]
        print(f"   sample {dt.date()}: cap=${mc[t].loc[dt]/1e9:.4f}B  price={close[t].loc[dt]:.2f}  implied_shares={mc[t].loc[dt]/close[t].loc[dt]:,.0f}")
