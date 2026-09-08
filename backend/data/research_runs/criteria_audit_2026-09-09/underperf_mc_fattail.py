# Robustness of the underperformance-rule MC to fat tails: Student-t(df=4) daily returns, same rule.
import numpy as np
rng=np.random.default_rng(1); LOOK=60; THR=-0.5; PPY=252
def p_flag(S,H,n=20000,vol=0.01,df=4):
    mu=S/np.sqrt(PPY)*vol
    z=rng.standard_t(df,size=(n,H))*np.sqrt((df-2)/df)  # unit variance
    r=mu+vol*z
    cs=np.cumsum(r,1); cs2=np.cumsum(r*r,1); fl=np.zeros(n,bool)
    for end in range(LOOK,H+1):
        s=cs[:,end-1]-(cs[:,end-LOOK-1] if end-LOOK-1>=0 else 0); s2=cs2[:,end-1]-(cs2[:,end-LOOK-1] if end-LOOK-1>=0 else 0)
        m=s/LOOK; v=(s2-LOOK*m**2)/(LOOK-1); fl|=(m/np.sqrt(v)*np.sqrt(PPY)<=THR)
    return fl.mean()
print("t(4) returns: true_SR  H=126  H=252")
for S in [0.5,1.0,2.0]: print(f"{S:5.1f}  {p_flag(S,126):.3f}  {p_flag(S,252):.3f}")
# also: what threshold would give a 5% false-kill rate over 252 days for a TRUE SR=0.5 strategy?
def p_flag_thr(S,H,thr,n=20000,vol=0.01):
    mu=S/np.sqrt(PPY)*vol; r=rng.normal(mu,vol,(n,H)); cs=np.cumsum(r,1); cs2=np.cumsum(r*r,1); fl=np.zeros(n,bool)
    for end in range(LOOK,H+1):
        s=cs[:,end-1]-(cs[:,end-LOOK-1] if end-LOOK-1>=0 else 0); s2=cs2[:,end-1]-(cs2[:,end-LOOK-1] if end-LOOK-1>=0 else 0)
        m=s/LOOK; v=(s2-LOOK*m**2)/(LOOK-1); fl|=(m/np.sqrt(v)*np.sqrt(PPY)<=thr)
    return fl.mean()
print("normal, true SR=0.5, H=252: P(flag) at threshold", {t: round(p_flag_thr(0.5,252,t),3) for t in [-0.5,-1.0,-2.0,-3.0,-4.0]})
print("normal, true SR=0.0, H=252: P(flag) at threshold", {t: round(p_flag_thr(0.0,252,t),3) for t in [-0.5,-1.0,-2.0,-3.0,-4.0]})
