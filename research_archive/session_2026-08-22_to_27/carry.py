import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, io, requests
S={"USD":"IR3TIB01USM156N","EUR":"IR3TIB01EZM156N","JPY":"IR3TIB01JPM156N","GBP":"IR3TIB01GBM156N",
   "AUD":"IR3TIB01AUM156N","CAD":"IR3TIB01CAM156N","CHF":"IR3TIB01CHM156N","NZD":"IR3TIB01NZM156N",
   "SEK":"IR3TIB01SEM156N","NOK":"IR3TIB01NOM156N"}
out={}
for k,v in S.items():
    t=requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={v}",timeout=30).text
    df=pd.read_csv(io.StringIO(t)); df.columns=["date","val"]
    df["date"]=pd.to_datetime(df["date"]); df["val"]=pd.to_numeric(df["val"],errors="coerce")
    out[k]=df.set_index("date")["val"]
R=pd.DataFrame(out)
R=R.loc["2006-01-01":]
print("rate panel rows:",len(R)," last full row:",R.dropna().index[-1].date())
print("non-null counts:\n", R.notna().sum().to_dict())
D=R.sub(R["USD"],axis=0).drop(columns=["USD"]).dropna()
print("\ndifferential panel:",D.index[0].date(),"->",D.index[-1].date(),len(D),"months")
print("mean carry diff (%):", D.mean().round(2).to_dict())
print("cross-sec spread (max-min) mean:", round(float((D.max(axis=1)-D.min(axis=1)).mean()),2),"%")
# persistence: rank correlation of differential vs its own lag
for lag in [1,3,6,12]:
    c=[D.iloc[i].corr(D.iloc[i-lag],method="spearman") for i in range(lag,len(D))]
    print(f"rank-corr(diff_t, diff_t-{lag}m) = {np.nanmean(c):.3f}")
