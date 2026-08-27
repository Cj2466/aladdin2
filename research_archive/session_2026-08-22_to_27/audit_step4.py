import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.sp500_membership_history import was_member

SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, shares, splits = d["close"], d["shares"], d["splits"]
FORM_START = date(2015,1,7)              # D1 production formation_start
BUYBACK_START = date(2018,1,2)           # Buyback production formation_start
idx = close.index
days = np.array([ts.date() for ts in idx])
in_d1   = days >= FORM_START
in_bb   = days >= BUYBACK_START

# --- per-ticker eligibility (member AND finite close), on D1's own trading grid
elig_days = {}
for t in close.columns:
    finite = np.isfinite(close[t].to_numpy())
    mem = np.array([was_member(t, dd) for dd in days])
    elig_days[t] = mem & finite
pickle.dump({"elig": elig_days, "days": days}, open(f"{SP}/audit_elig.pkl","wb"))

# --- contamination detectors ------------------------------------------------
def share_jumps(t):
    """Unexplained (non-split) jumps in the RAW share series."""
    sh = shares.get(t)
    if sh is None or len(sh) < 2: return []
    sp = splits.get(t)
    ratios = {} if sp is None else {pd.Timestamp(i): float(v) for i,v in sp.items() if np.isfinite(v) and v>0}
    r = (sh / sh.shift(1)).dropna()
    out=[]
    for i,v in r.items():
        if not (v > 1.5 or v < 0.667): continue
        # explained by a split whose ex-date is within +/-200d and whose ratio matches?
        expl = any(abs(v/rr - 1.0) <= 0.15 and abs((pd.Timestamp(i)-ed).days) <= 200
                   for ed, rr in ratios.items())
        if not expl:
            out.append((pd.Timestamp(i), float(v)))
    return out

def price_jumps(t):
    px = close[t].dropna()
    if len(px) < 2: return []
    r = (px/px.shift(1)).dropna()
    return [(i, float(v)) for i,v in r.items() if v > 2.5 or v < 0.4]

rows=[]
for t in close.columns:
    sh = shares.get(t)
    px = close[t].dropna()
    e = elig_days[t]
    ed1 = e & in_d1; edb = e & in_bb
    sf = pd.Timestamp(sh.index[0]) if sh is not None and len(sh) else None
    sl = pd.Timestamp(sh.index[-1]) if sh is not None and len(sh) else None
    sj = share_jumps(t); pj = price_jumps(t)
    rows.append(dict(
        t=t,
        px_first=px.index[0] if len(px) else None, px_last=px.index[-1] if len(px) else None,
        sh_first=sf, sh_last=sl,
        shares_precede_price_days=(px.index[0]-sf).days if (len(px) and sf is not None) else np.nan,
        n_elig_d1=int(ed1.sum()), n_elig_bb=int(edb.sum()),
        elig_d1_first=days[ed1][0] if ed1.any() else None, elig_d1_last=days[ed1][-1] if ed1.any() else None,
        n_share_jumps=len(sj), n_price_jumps=len(pj),
        share_jumps=sj, price_jumps=pj,
    ))
df = pd.DataFrame(rows).set_index("t")
df.to_pickle(f"{SP}/audit_full.pkl")

print("=== D1 eligibility reality check ===")
print("priced tickers:", len(df))
print("ever eligible in D1 window (member & priced on >=1 day):", int((df.n_elig_d1>0).sum()))
print("ever eligible in Buyback window:", int((df.n_elig_bb>0).sum()))
print("NEVER eligible (priced but never a member while priced):", int((df.n_elig_d1==0).sum()))

susp = df[df.shares_precede_price_days > 60]
print(f"\n=== The {len(susp)} lifecycle-mismatch tickers: were they EVER eligible? ===")
print(f"{'tick':7} {'sh_precede_d':>12} {'n_elig_D1':>10} {'n_elig_BB':>10}  elig window")
for t,r in susp.sort_values("shares_precede_price_days", ascending=False).iterrows():
    w = f"{r.elig_d1_first}..{r.elig_d1_last}" if r.n_elig_d1 else "-"
    print(f"{t:7} {int(r.shares_precede_price_days):12} {r.n_elig_d1:10} {r.n_elig_bb:10}  {w}")
