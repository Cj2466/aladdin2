import pandas as pd, numpy as np
SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
close = pd.read_pickle(f"{SCRATCH}/close.pkl")
FAMILY = ["^VIX","^SKEW","^MOVE","^VIX3M","^OVX","^VVIX","^GVZ","^VIX6M"]
vol = close[FAMILY]

defs = {"move_vix":("^MOVE","^VIX"),"ovx_vix":("^OVX","^VIX"),"gvz_vix":("^GVZ","^VIX"),
        "vix3m_vix":("^VIX3M","^VIX"),"vix6m_vix":("^VIX6M","^VIX"),
        "vix6m_vix3m":("^VIX6M","^VIX3M"),"vvix_vix":("^VVIX","^VIX"),"skew":("^SKEW",None)}

print("=== first date each signal's 252d z-score is available (each on its OWN full history) ===")
firsts = {}
for sid,(num,den) in defs.items():
    lvl = np.log(vol[num]/vol[den]) if den else np.log(vol[num])
    lvl = lvl.dropna()
    z = (lvl - lvl.rolling(252).mean())/lvl.rolling(252).std(ddof=1)
    z = z.dropna()
    firsts[sid] = z.index[0]
    print(f"  {sid:14s} level starts {lvl.index[0].date()}  z starts {z.index[0].date()}  n_z={len(z)}")

common = max(firsts.values())
print(f"\n=== COMMON FIRST FORMATION DATE (all 8 z available) = {common.date()} ===")
binding = [k for k,v in firsts.items() if v==common]
print("  bound by:", binding)

# tradeable sample
traded = close[["SPY","IEF"]].dropna()
sample = traded[traded.index >= common]
print(f"  tradeable sample: {sample.index[0].date()} -> {sample.index[-1].date()}  n_days={len(sample)}  ~{len(sample)/252:.1f} yrs")

for h in (21,42,63):
    print(f"    hold={h:3d} -> {len(sample)//h} non-overlapping formations")

print("\n=== does the traded sample contain real stress regimes? SPY worst 21d windows ===")
spy = sample["SPY"]; r = spy.pct_change()
roll = r.rolling(21).sum().dropna().sort_values()
for d,v in roll.head(6).items(): print(f"   {d.date()}  21d SPY {v:+.1%}")
print("\n=== BENCHMARKS over the tradeable sample (raw, zero-rf, matching metrics.sharpe_ratio) ===")
for t in ["SPY","IEF"]:
    x = sample[t].pct_change().dropna()
    print(f"   {t} buy&hold Sharpe = {x.mean()/x.std(ddof=1)*np.sqrt(252):+.3f}   ann.ret={x.mean()*252:+.2%}")
