"""PRE-DECLARED diagnostic grid, fixed BEFORE seeing any result.
H1 credit->equity : 4 outcomes x 4 horizons = 16
H2 commodity->sector: 3 pairs x 3 lookbacks x 2 horizons = 18
H3 dollar->sector  : 2 spreads x 3 lookbacks x 2 horizons = 12
TOTAL N_DIAG = 46.  Bonferroni alpha = .05/46 = .00109
"""
import pandas as pd, numpy as np, statsmodels.api as sm
P = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/close.pkl"
c = pd.read_pickle(P).sort_index()
r = np.log(c).diff()
N_DIAG = 46; ALPHA = 0.05/N_DIAG
res=[]
def nw(y,x,lag,tag):
    df=pd.concat([y.rename("y"),x.rename("x")],axis=1).dropna()
    if len(df)<400: return
    m=sm.OLS(df.y,sm.add_constant(df.x)).fit(cov_type="HAC",cov_kwds={"maxlags":lag})
    res.append(dict(test=tag,n=len(df),beta=m.params["x"],t=m.tvalues["x"],
                    p=m.pvalues["x"],r2=m.rsquared))

# ---------- credit factor: duration-hedged HY excess return ----------
d=pd.concat([r.HYG,r.IEF],axis=1).dropna()
beta=d.HYG.rolling(252).cov(d.IEF)/d.IEF.rolling(252).var()
cx=(d.HYG-beta.shift(1)*d.IEF).dropna()          # daily credit excess return
SEC=["XLE","XLB","XLI","XLK","XLF","XLU","XLP","XLV","XLY"]
sec=r[SEC]
disp=sec.std(axis=1)                              # cross-sectional dispersion
spy=r.SPY

for H in [5,10,21,63]:
    cred21=cx.rolling(21).sum()                   # trailing credit excess (mom)
    f_ret =spy.shift(-H).rolling(H).sum()         # fwd SPY return
    f_disp=disp.shift(-H).rolling(H).mean()       # fwd mean dispersion
    f_vol =spy.shift(-H).rolling(H).std()         # fwd SPY realized vol
    lvl=np.log(c.SPY); f_dd=(lvl.shift(-H).rolling(H).min()-lvl)  # fwd drawdown
    nw(f_ret ,cred21,H,f"H1 cred21->fwd{H}d SPYret")
    nw(f_disp,cred21,H,f"H1 cred21->fwd{H}d disp")
    nw(f_vol ,cred21,H,f"H1 cred21->fwd{H}d vol")
    nw(f_dd  ,cred21,H,f"H1 cred21->fwd{H}d maxDD")

# ---------- H2 commodity -> sector ----------
for cm,eq in [("DBC","XLE"),("DBB","XLB"),("DBA","XLP")]:
    for L in [21,63,126]:
        mom=r[cm].rolling(L).sum()
        for H in [21,63]:
            nw(r[eq].shift(-H).rolling(H).sum(),mom,H,f"H2 {cm}{L}->fwd{H}d {eq}")
# ---------- H3 dollar -> sector spread ----------
for name,sp in [("XLE-XLP",r.XLE-r.XLP),("XLB-XLU",r.XLB-r.XLU)]:
    for L in [21,63,126]:
        mom=r.UUP.rolling(L).sum()
        for H in [21,63]:
            nw(sp.shift(-H).rolling(H).sum(),mom,H,f"H3 UUP{L}->fwd{H}d {name}")

o=pd.DataFrame(res).sort_values("p")
pd.set_option("display.width",200)
print(o.to_string(index=False,float_format=lambda v:f"{v:9.4f}"))
print(f"\nN_DIAG={N_DIAG} Bonferroni alpha={ALPHA:.5f}")
print("survivors:", (o.p<ALPHA).sum())
print(o[o.p<ALPHA].test.tolist())
