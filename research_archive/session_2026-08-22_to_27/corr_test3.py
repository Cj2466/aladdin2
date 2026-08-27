"""Hardened null: joint iid bootstrap of the ACTUAL (a_t,b_t) return pairs.
Preserves each leg's fat tails and the unconditional correlation exactly;
destroys ALL time-variation in correlation. If real 'breakdown reversion'
sits inside this null's distribution, the effect is the rolling estimator
regressing to its own mean, not a real state reverting."""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
rng = np.random.default_rng(11)
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/"
rets = np.log(pd.read_pickle(SP+"px.pkl")).diff()
fisher = lambda r: np.arctanh(np.clip(r,-0.9999,0.9999))
W=HZ=63; NB=400

def lift(a_arr, b_arr):
    s=pd.Series(a_arr); t=pd.Series(b_arr)
    z=fisher(s.rolling(W).corr(t))
    bm=z.shift(W).expanding(252).mean(); bs=z.shift(W).expanding(252).std()
    m=pd.DataFrame({"zs":(z-bm)/bs,"fwd":z.shift(-HZ)-z}).dropna().iloc[::HZ]
    bd=m[m.zs<-1.5]
    return (bd.fwd.mean()-m.fwd.mean(), len(bd)) if len(bd)>=2 else (np.nan,len(bd))

print(f"{'pair':12s} {'real':>7s} {'n_bd':>5s} {'null_mu':>8s} {'null_sd':>8s} {'z':>6s} {'p':>7s}")
for a,b in [("XLE","USO"),("XOP","USO"),("GLD","TIP"),("GLD","IEF"),
            ("FXC","USO"),("FXC","XLE"),("GLD","SLV"),("HYG","LQD")]:
    d=rets[[a,b]].dropna(); A=d[a].values; B=d[b].values; n=len(A)
    real,nbd = lift(A,B)
    nulls=[]
    for _ in range(NB):
        i=rng.integers(0,n,n)              # joint iid bootstrap of pairs
        l,_=lift(A[i],B[i])
        if np.isfinite(l): nulls.append(l)
    nulls=np.array(nulls)
    z=(real-nulls.mean())/nulls.std()
    p=float((nulls>=real).mean())
    print(f"{a}/{b:7s} {real:+7.3f} {nbd:5d} {nulls.mean():+8.3f} {nulls.std():8.3f} "
          f"{z:+6.2f} {p:7.3f}")

print("\n=== Sanity: does the detector find a breakdown when one is REAL? ===")
print("    (sim: true corr 0.65 for 3000d, drops to 0.15 for 250d, back to 0.65)")
det=[]
for _ in range(200):
    seg=[]
    for rho,k in [(0.65,3000),(0.15,250),(0.65,1750)]:
        seg.append(rng.multivariate_normal([0,0],[[1,rho],[rho,1]],size=k))
    e=np.vstack(seg); l,nb=lift(e[:,0],e[:,1]); det.append(l)
det=np.array([x for x in det if np.isfinite(x)])
print(f"    lift with a REAL 250d breakdown embedded = {det.mean():+.3f} "
      f"(vs pure-noise null ~+0.22) -> real regimes DO show up as ~{det.mean()-0.22:+.3f} excess")
