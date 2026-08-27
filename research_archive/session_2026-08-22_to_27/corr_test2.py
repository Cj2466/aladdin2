"""TEST A: is a 'correlation breakdown' a real state, or estimation noise?
   Null = two GBMs with CONSTANT true correlation, same detector.
   TEST B: does conditioning a spread trade on breakdown add anything?"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
rng = np.random.default_rng(7)
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/"
px = pd.read_pickle(SP+"px.pkl")
rets = np.log(px).diff()
fisher = lambda r: np.arctanh(np.clip(r,-0.9999,0.9999))

print("=== USO ROLL DECAY (kills any USO log-spread pair trade?) ===")
for t in ["USO","XLE","XOP","BNO"]:
    s = px[t].dropna(); print(f"  {t}: {s.iloc[0]:.2f} -> {s.iloc[-1]:.2f}  "
                              f"total {100*(s.iloc[-1]/s.iloc[0]-1):+.1f}%")

W, HZ = 63, 63     # corr window, forward horizon
def breakdown_stats(ra, rb, label):
    d = pd.DataFrame({"a":ra,"b":rb}).dropna()
    roll = d["a"].rolling(W).corr(d["b"])
    z = fisher(roll)
    # ex-ante standardisation: expanding mean/sd of z using ONLY past data,
    # lagged one window so the current window never feeds its own baseline
    base_m = z.shift(W).expanding(252).mean()
    base_s = z.shift(W).expanding(252).std()
    zs = (z - base_m) / base_s
    fwd = z.shift(-HZ) - z                      # forward CHANGE in corr
    m = pd.DataFrame({"zs":zs,"fwd":fwd}).dropna()
    m = m.iloc[::HZ]                            # non-overlapping
    bd = m[m.zs < -1.5]
    print(f"  {label:22s} n_blk={len(m):4d} n_bd={len(bd):3d}  "
          f"E[dz|breakdown]={bd.fwd.mean():+.3f}  E[dz|all]={m.fwd.mean():+.3f}  "
          f"lift={bd.fwd.mean()-m.fwd.mean():+.3f}")
    return bd.fwd.mean()-m.fwd.mean(), len(bd)

print(f"\n=== TEST A: forward {HZ}d change in Fisher-z after a breakdown (zs<-1.5)")
print("    REAL DATA ---")
real = {}
for a,b in [("XLE","USO"),("XOP","USO"),("GLD","TIP"),("FXC","USO"),("GLD","SLV")]:
    d = rets[[a,b]].dropna()
    real[(a,b)] = breakdown_stats(d[a], d[b], f"{a}/{b}")

print("    NULL: CONSTANT true corr, pure estimation noise ---")
n = 5000
for rho, lab in [(0.63,"sim rho=0.63 (XLE/USO)"), (0.26,"sim rho=0.26 (GLD/TIP)"),
                 (0.80,"sim rho=0.80 (GLD/SLV)")]:
    lifts=[]
    for _ in range(30):
        e = rng.multivariate_normal([0,0],[[1,rho],[rho,1]],size=n)
        s = pd.Series(e[:,0]); t = pd.Series(e[:,1])
        roll = s.rolling(W).corr(t); z=fisher(roll)
        bm=z.shift(W).expanding(252).mean(); bs=z.shift(W).expanding(252).std()
        zs=(z-bm)/bs; fwd=z.shift(-HZ)-z
        m=pd.DataFrame({"zs":zs,"fwd":fwd}).dropna().iloc[::HZ]
        bd=m[m.zs<-1.5]
        if len(bd): lifts.append(bd.fwd.mean()-m.fwd.mean())
    print(f"  {lab:22s} mean lift over 30 sims = {np.mean(lifts):+.3f} "
          f"(sd {np.std(lifts):.3f})  <- pure noise reverts this much")

print("\n=== TEST A2: after a breakdown, does corr RECOVER or STAY LOW at 252d? ===")
for a,b in [("XLE","USO"),("FXC","USO"),("HYG","LQD"),("GLD","TIP")]:
    d = rets[[a,b]].dropna()
    roll = d[a].rolling(W).corr(d[b]); z=fisher(roll)
    bm=z.shift(W).expanding(252).mean(); bs=z.shift(W).expanding(252).std()
    zs=(z-bm)/bs
    ev = zs[zs<-1.5].index
    ev = [e for e in ev if e < z.index[-260]]
    if not ev: print(f"  {a}/{b}: no events"); continue
    # keep only events >=252d apart (independent episodes)
    keep=[ev[0]]
    for e in ev[1:]:
        if (e-keep[-1]).days>365: keep.append(e)
    rec=[float(z.loc[z.index[z.index.get_loc(e)+252]]-bm.loc[e]) for e in keep]
    print(f"  {a}/{b:6s} {len(keep):2d} indep episodes; z_252d_later - prior_mean: "
          f"mean {np.mean(rec):+.3f}, {sum(r>0 for r in rec)}/{len(rec)} recovered above prior mean")

print("\n=== TEST B: does breakdown-conditioning add to a plain spread trade? ===")
print("    (XLE/USO, 252d OLS hedge on log px, spread z, hold 21d, 10bps/leg)")
for a,b in [("XLE","USO"),("XOP","USO"),("GLD","SLV")]:
    d = px[[a,b]].dropna(); la,lb = np.log(d[a]), np.log(d[b])
    r = rets[[a,b]].dropna()
    roll = r[a].rolling(W).corr(r[b]); z=fisher(roll)
    bm=z.shift(W).expanding(252).mean(); bs=z.shift(W).expanding(252).std(); zs=(z-bm)/bs
    out={"all":[], "bd":[], "normal":[]}
    idx=d.index
    for i in range(252, len(d)-21, 21):
        w=slice(i-252,i)
        h=np.polyfit(la.iloc[w], lb.iloc[w], 1)[0]
        sp = lb.iloc[w] - h*la.iloc[w]
        if sp.std()==0: continue
        zsp = (lb.iloc[i]-h*la.iloc[i]-sp.mean())/sp.std()
        if abs(zsp)<1.0: continue
        pos = -np.sign(zsp)                       # fade the spread
        fwd = ((lb.iloc[i+21]-lb.iloc[i]) - h*(la.iloc[i+21]-la.iloc[i]))/(1+abs(h))
        pnl = pos*fwd - 2*0.0010*(1+abs(h))/(1+abs(h))   # 10bps each leg, round trip
        out["all"].append(pnl)
        cz = zs.get(idx[i], np.nan)
        (out["bd"] if cz<-1.0 else out["normal"]).append(pnl)
    for k,v in out.items():
        v=np.array(v)
        if len(v)<5: print(f"  {a}/{b} {k}: n={len(v)} too few"); continue
        sr = v.mean()/v.std()*np.sqrt(252/21) if v.std()>0 else np.nan
        print(f"  {a}/{b:5s} {k:7s} n={len(v):4d} mean={v.mean()*100:+.3f}%  Sharpe={sr:+.2f}")
