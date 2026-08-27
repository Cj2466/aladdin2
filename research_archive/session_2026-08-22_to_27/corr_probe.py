"""Correlation-breakdown feasibility probe. Real data, no assumptions."""
import warnings, numpy as np, pandas as pd, yfinance as yf
warnings.filterwarnings("ignore")

TICKERS = ["GLD","TIP","IEF","TLT","USO","XLE","XOP","FXC","FXA","FXE","FXY",
           "EWJ","SPY","SLV","DBC","BNO","LQD","HYG","SHY"]

raw = yf.download(TICKERS, start="2004-01-01", end="2026-08-26",
                  auto_adjust=True, progress=False, threads=True)
px = raw["Close"].dropna(how="all")
print("=== COVERAGE (first valid date, n obs) ===")
for t in TICKERS:
    if t in px.columns:
        s = px[t].dropna()
        print(f"{t:5s} {str(s.index[0].date()):12s} {str(s.index[-1].date()):12s} n={len(s)}")
px.to_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/px.pkl")

rets = np.log(px).diff()

PAIRS = [("GLD","TIP"), ("GLD","IEF"), ("XLE","USO"), ("XOP","USO"),
         ("FXC","USO"), ("FXC","XLE"), ("FXY","EWJ"), ("GLD","SLV"),
         ("GLD","SPY"), ("HYG","LQD")]

def fisher(r): return np.arctanh(np.clip(r, -0.9999, 0.9999))

print("\n=== FULL-SAMPLE + STABILITY (daily log returns) ===")
print(f"{'pair':14s} {'n':>6s} {'full_r':>7s} {'r_sd63':>7s} {'r_min':>7s} {'r_max':>7s} "
      f"{'signflip%':>9s} {'yr_r_sd':>7s}")
summary = {}
for a,b in PAIRS:
    d = rets[[a,b]].dropna()
    if len(d) < 500:
        print(f"{a}/{b}: too short ({len(d)})"); continue
    full = d[a].corr(d[b])
    roll = d[a].rolling(63).corr(d[b]).dropna()
    yr = d.groupby(d.index.year).apply(lambda g: g[a].corr(g[b]) if len(g)>50 else np.nan).dropna()
    flip = float((np.sign(roll) != np.sign(full)).mean())
    print(f"{a}/{b:8s} {len(d):6d} {full:7.3f} {roll.std():7.3f} {roll.min():7.3f} "
          f"{roll.max():7.3f} {flip*100:8.1f}% {yr.std():7.3f}")
    summary[(a,b)] = dict(n=len(d), full=full, roll=roll, yr=yr, d=d)

print("\n=== YEARLY CORRELATIONS ===")
for (a,b),v in summary.items():
    print(f"{a}/{b:8s} " + " ".join(f"{y}:{r:+.2f}" for y,r in v["yr"].items()))

print("\n=== DOES ROLLING CORRELATION ITSELF MEAN-REVERT? (Fisher-z, AR1 on")
print("    NON-OVERLAPPING 63d blocks -> half-life in 63d blocks) ===")
print(f"{'pair':14s} {'nblk':>5s} {'AR1':>7s} {'HL_days':>8s} {'z_sd':>6s}")
for (a,b),v in summary.items():
    z = fisher(v["roll"]).iloc[::63]           # non-overlapping
    z = z.dropna()
    if len(z) < 20: continue
    x, y = z.values[:-1], z.values[1:]
    beta = np.polyfit(x, y, 1)[0]
    hl = np.log(0.5)/np.log(abs(beta))*63 if 0 < beta < 1 else np.nan
    print(f"{a}/{b:8s} {len(z):5d} {beta:7.3f} {hl:8.1f} {z.std():6.3f}")
