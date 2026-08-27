import pandas as pd, numpy as np
SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
close = pd.read_pickle(f"{SCRATCH}/close.pkl")

FAMILY = ["^VIX","^SKEW","^MOVE","^VIX3M","^OVX","^VVIX","^GVZ","^VIX6M"]
sub = close[FAMILY].dropna()
print("=== COMMON HISTORY (8-index set, VXD/VIX9D/VIX1D excluded) ===")
print("first common date:", sub.index[0].date(), " last:", sub.index[-1].date(), " n=", len(sub))
# which ticker binds?
for t in FAMILY:
    print(f"   {t:8s} first={close[t].dropna().index[0].date()}")
print()
print("=== if ^VXD were included ===")
s2 = close[FAMILY+["^VXD"]].dropna(); print("  start:", s2.index[0].date(), "n=", len(s2))
print("=== if ^VIX9D were included (amendment 1 counterfactual) ===")
s3 = close[FAMILY+["^VIX9D"]].dropna(); print("  start:", s3.index[0].date(), "n=", len(s3))
print("=== if ^VIX1D were included ===")
s4 = close[FAMILY+["^VIX1D"]].dropna(); print("  start:", s4.index[0].date(), "n=", len(s4))
print()

print("=== CROSS-INDEX CORRELATION OF DAILY LOG CHANGES (scout claimed 0.34-0.42 for MOVE/OVX/GVZ vs VIX) ===")
dlog = np.log(sub).diff().dropna()
c = dlog.corr()
print(c.round(3).to_string())
print()
print("vs ^VIX specifically:")
for t in FAMILY:
    if t != "^VIX":
        print(f"   corr(d ln {t:8s}, d ln ^VIX) = {c.loc[t,'^VIX']:+.3f}")
print()

print("=== IS MOVE/VIX JUST RELABELED REALIZED VOL? (scout claimed corr = -0.40) ===")
spy = close["SPY"].dropna()
rv21 = np.log(spy).diff().rolling(21).std() * np.sqrt(252) * 100
ratio = np.log(sub["^MOVE"] / sub["^VIX"])
j = pd.concat([ratio.rename("logMV"), rv21.rename("rv")], axis=1).dropna()
print(f"  corr(log(MOVE/VIX), SPY 21d realized vol) = {j['logMV'].corr(j['rv']):+.3f}   n={len(j)}")
print(f"  corr(VIX level,     SPY 21d realized vol) = {sub['^VIX'].reindex(j.index).corr(j['rv']):+.3f}")
print()
print("=== SIGNAL RATIO SANITY (levels of each ratio over common sample) ===")
for name, num, den in [("MOVE/VIX","^MOVE","^VIX"),("OVX/VIX","^OVX","^VIX"),("GVZ/VIX","^GVZ","^VIX"),
                        ("VIX3M/VIX","^VIX3M","^VIX"),("VIX6M/VIX","^VIX6M","^VIX"),
                        ("VIX6M/VIX3M","^VIX6M","^VIX3M"),("VVIX/VIX","^VVIX","^VIX")]:
    r = sub[num]/sub[den]
    print(f"  {name:12s} min={r.min():7.3f} med={r.median():7.3f} max={r.max():8.3f}")
r = sub["^SKEW"]; print(f"  {'SKEW':12s} min={r.min():7.3f} med={r.median():7.3f} max={r.max():8.3f}")
print()
print("=== PAIRWISE CORR OF THE 8 z-SIGNALS THEMSELVES (252d z of log level) ===")
sig = {}
sig["move_vix"]    = np.log(sub["^MOVE"]/sub["^VIX"])
sig["ovx_vix"]     = np.log(sub["^OVX"]/sub["^VIX"])
sig["gvz_vix"]     = np.log(sub["^GVZ"]/sub["^VIX"])
sig["vix3m_vix"]   = np.log(sub["^VIX3M"]/sub["^VIX"])
sig["vix6m_vix"]   = np.log(sub["^VIX6M"]/sub["^VIX"])
sig["vix6m_vix3m"] = np.log(sub["^VIX6M"]/sub["^VIX3M"])
sig["vvix_vix"]    = np.log(sub["^VVIX"]/sub["^VIX"])
sig["skew"]        = np.log(sub["^SKEW"])
S = pd.DataFrame(sig)
Z = (S - S.rolling(252).mean()) / S.rolling(252).std(ddof=1)
print(Z.dropna().corr().round(2).to_string())
