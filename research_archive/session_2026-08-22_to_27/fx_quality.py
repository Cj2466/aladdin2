import warnings; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np

P = ["EURUSD=X","USDJPY=X","EURJPY=X","GBPUSD=X","GBPJPY=X","AUDUSD=X","AUDJPY=X","USDCHF=X","USDSEK=X","USDBRL=X","USDCNY=X","USDHKD=X"]
d = yf.download(P, start="2003-01-01", end="2026-08-26", auto_adjust=False, progress=False, group_by="column")
C,H,L,O,V = d["Close"], d["High"], d["Low"], d["Open"], d["Volume"]

print("=== OHLC integrity ===")
for p in ["EURUSD=X","USDJPY=X","GBPJPY=X","USDBRL=X"]:
    sub = pd.concat([O[p],H[p],L[p],C[p]],axis=1).dropna()
    sub.columns=["o","h","l","c"]
    bad_hl = int((sub.h < sub.l).sum())
    bad_c  = int(((sub.c > sub.h+1e-12)|(sub.c < sub.l-1e-12)).sum())
    bad_o  = int(((sub.o > sub.h+1e-12)|(sub.o < sub.l-1e-12)).sum())
    zero_range = int((sub.h==sub.l).sum())
    print(f"{p}: n={len(sub)} H<L={bad_hl} C_outside={bad_c} O_outside={bad_o} H==L={zero_range} vol_allzero={bool((V[p].fillna(0)==0).all())}")

print("\n=== Triangular consistency: EURJPY vs EURUSD*USDJPY ===")
for cross,a,b in [("EURJPY=X","EURUSD=X","USDJPY=X"),("GBPJPY=X","GBPUSD=X","USDJPY=X"),("AUDJPY=X","AUDUSD=X","USDJPY=X")]:
    j = pd.concat([C[cross],C[a],C[b]],axis=1).dropna()
    j.columns=["x","a","b"]
    synth = j.a*j.b
    err = (j.x/synth - 1.0)
    print(f"{cross}: n={len(j)} median_abs_err={err.abs().median()*1e4:.2f}bp p95={err.abs().quantile(.95)*1e4:.1f}bp p99.5={err.abs().quantile(.995)*1e4:.1f}bp max={err.abs().max()*1e4:.0f}bp")

print("\n=== Gap locations (missing >20 bdays) ===")
for p in ["USDSEK=X","USDCNY=X","USDBRL=X","USDHKD=X","EURJPY=X"]:
    s=C[p].dropna(); idx=s.index
    gaps = pd.Series(idx).diff().dt.days
    big = [(str(idx[i-1].date()), str(idx[i].date()), int(gaps.iloc[i])) for i in range(1,len(idx)) if gaps.iloc[i]>30]
    print(f"{p}: {big[:6]}")

print("\n=== Stale/repeat runs (identical close) ===")
for p in ["EURUSD=X","USDCNY=X","USDHKD=X"]:
    s=C[p].dropna(); r=s.diff()
    run=(r!=0).cumsum(); mx=int(r[r==0].groupby(run).size().max()) if (r==0).any() else 0
    print(f"{p}: max_consecutive_identical={mx}")

print("\n=== Weekend/Monday contamination (Sat/Sun bars?) ===")
for p in ["EURUSD=X","USDJPY=X"]:
    s=C[p].dropna()
    print(p, s.index.dayofweek.value_counts().sort_index().to_dict())
