"""Corwin-Schultz (2012) high-low effective-spread estimator + dollar volume,
S&P 600 vs S&P 500, on real yfinance daily bars."""
import sys, warnings, random
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_82071471-600-1/backend")
import numpy as np, pandas as pd, yfinance as yf
from app.services.research_lab.sp500_membership_history import get_universe_as_of

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"


def corwin_schultz(h, l):
    """Two-day high-low spread estimator, per-day series as a fraction of price."""
    h = h.astype(float)
    l = l.astype(float)
    ok = (h > 0) & (l > 0)
    h = h.where(ok)
    l = l.where(ok)
    beta = (np.log(h / l) ** 2) + (np.log(h.shift(1) / l.shift(1)) ** 2)
    h2 = pd.concat([h, h.shift(1)], axis=1).max(axis=1)
    l2 = pd.concat([l, l.shift(1)], axis=1).min(axis=1)
    gamma = np.log(h2 / l2) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return s.clip(lower=0)  # Corwin-Schultz's own convention: negative estimates -> 0


sp600 = [t.strip().replace(".", "-") for t in pd.read_html(f"{SCRATCH}/sp600.html")[0]["Symbol"].astype(str)]
sp500 = get_universe_as_of(pd.Timestamp("2026-06-30").date())
random.seed(7)
s600 = random.sample(sp600, 120)
s500 = random.sample(sp500, 120)


def measure(tickers, label):
    df = yf.download(
        tickers, start="2024-01-01", end="2026-08-26", auto_adjust=False,
        progress=False, group_by="column", threads=True,
    )
    hi, lo, cl, vo = df["High"], df["Low"], df["Close"], df["Volume"]
    spreads, dvols = [], []
    for t in hi.columns:
        h = hi[t].dropna()
        if len(h) < 200:
            continue
        s = corwin_schultz(hi[t], lo[t]).dropna()
        if len(s) < 200:
            continue
        spreads.append(float(s.median()))
        dvols.append(float((cl[t] * vo[t]).median()))
    print(
        f"{label}: n={len(spreads)}  median CS spread = {np.median(spreads) * 10000:.1f} bps"
        f"  mean = {np.mean(spreads) * 10000:.1f} bps  median daily $vol = ${np.median(dvols) / 1e6:.1f}M"
    )
    return np.median(spreads), np.median(dvols)


s6, v6 = measure(s600, "S&P 600")
s5, v5 = measure(s500, "S&P 500")
print(f"\nRATIO spread 600/500 = {s6 / s5:.2f}x     RATIO $vol 500/600 = {v5 / v6:.1f}x thinner")
