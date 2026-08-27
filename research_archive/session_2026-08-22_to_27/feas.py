"""Feasibility: CBOE implied correlation + realized correlation + overlap vs the
already-rejected vol-regime family's state variables."""
import io
import sys
from datetime import date

import httpx
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a6fc3015debbbe27e/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.risk.correlation import correlation_matrix
from app.services.risk.diversification import average_pairwise_correlation

BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/"


def fetch_cboe(sym: str) -> pd.Series:
    with httpx.Client(timeout=30.0, follow_redirects=True,
                      headers={"User-Agent": "aladdin2-research/1.0"}) as c:
        r = c.get(f"{BASE}{sym}_History.csv")
        r.raise_for_status()
        raw = r.text
    df = pd.read_csv(io.StringIO(raw))
    df.columns = [c.strip().upper() for c in df.columns]
    df["DATE"] = pd.to_datetime(df["DATE"], format="%m/%d/%Y")
    s = df.set_index("DATE")["CLOSE"].astype(float).sort_index()
    return s[s > 0]


cor1m = fetch_cboe("COR1M")
cor3m = fetch_cboe("COR3M")
print("=== CBOE IMPLIED CORRELATION, LIVE PULL ===")
for name, s in (("COR1M", cor1m), ("COR3M", cor3m)):
    print(f"{name}: n={len(s)}  {s.index[0].date()} -> {s.index[-1].date()}  "
          f"min={s.min():.2f} med={s.median():.2f} max={s.max():.2f}  last={s.iloc[-1]:.2f}")
print("corr(COR1M, COR3M) levels:", round(cor1m.align(cor3m, join="inner")[0].corr(cor3m.align(cor1m, join="inner")[0]), 4))

# --- realized correlation from sector ETFs ---------------------------------
SECTORS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
prov = YFinanceProvider()
px, missing = prov.get_price_history(list(SECTORS) + ["SPY", "^VIX", "^SKEW", "^MOVE", "^VVIX", "^OVX", "^GVZ", "^VXN"],
                                     date(2004, 1, 1), date(2026, 8, 27))
print("\nmissing:", missing)
print("sector px:", px.index[0].date(), "->", px.index[-1].date(), "n=", len(px))
for t in SECTORS:
    if t in px.columns:
        s = px[t].dropna()
        print(f"  {t}: {s.index[0].date()} n={len(s)}")

sec = px[list(SECTORS)].dropna(axis=0, how="any")
rets = sec.pct_change().dropna()
print("sector returns n=", len(rets), rets.index[0].date(), "->", rets.index[-1].date())


def realized_corr(returns: pd.DataFrame, window: int) -> pd.Series:
    out = {}
    vals = returns
    for i in range(window, len(vals) + 1):
        w = vals.iloc[i - window:i]
        out[vals.index[i - 1]] = average_pairwise_correlation(correlation_matrix(w))
    return pd.Series(out)


for w in (21, 63):
    rc = realized_corr(rets, w) * 100.0
    print(f"\nrealized_corr_{w}d(sector,%): n={len(rc)} min={rc.min():.1f} med={rc.median():.1f} max={rc.max():.1f}")
    imp = cor1m if w == 21 else cor3m
    j = pd.concat([imp.rename("imp"), rc.rename("rc")], axis=1).dropna()
    print(f"  overlap n={len(j)}  corr(implied, realized) LEVELS = {j['imp'].corr(j['rc']):.4f}")
    crp = (j["imp"] - j["rc"])
    print(f"  CRP: mean={crp.mean():+.2f} med={crp.median():+.2f} sd={crp.sd() if hasattr(crp,'sd') else crp.std():.2f} "
          f"min={crp.min():+.1f} max={crp.max():+.1f}  frac>0={(crp>0).mean():.3f}")

# --- THE OVERLAP CHECK vs already-rejected vol-regime state variables -------
print("\n=== OVERLAP vs REJECTED vol_regime_timing FAMILY ===")
import app.services.research_lab.vol_regime_timing as vrt

volc = px[["^VIX", "^SKEW", "^MOVE", "^VVIX", "^OVX", "^GVZ", "^VXN"]]
Z = vrt.VOL_REGIME_Z_WINDOW

rc21 = realized_corr(rets, 21) * 100.0
j = pd.concat([cor1m.rename("imp"), rc21.rename("rc")], axis=1).dropna()
crp_raw = (j["imp"] - j["rc"]).rename("crp")
crp_z = vrt.trailing_zscore(crp_raw, Z)

states = {}
for key, fn, _c, _h, _x in vrt._STATE_VARIABLES:
    states[key] = fn(volc, Z)

print(f"\n{'state':<14}{'corr(z(CRP), z(state)) LEVELS':>32}{'corr of daily CHANGES':>26}{'n':>8}")
for key, s in states.items():
    a = pd.concat([crp_z.rename("a"), s.rename("b")], axis=1).dropna()
    if len(a) < 50:
        print(f"{key:<14}{'n/a':>32}{'n/a':>26}{len(a):>8}")
        continue
    lv = a["a"].corr(a["b"])
    dch = a["a"].diff().corr(a["b"].diff())
    print(f"{key:<14}{lv:>32.4f}{dch:>26.4f}{len(a):>8}")

# also raw (un-z-scored) CRP vs raw VIX level
a = pd.concat([crp_raw.rename("a"), volc["^VIX"].rename("b")], axis=1).dropna()
print(f"\nRAW CRP vs RAW VIX level: corr={a['a'].corr(a['b']):.4f}  n={len(a)}")
a2 = pd.concat([j["imp"].rename("a"), volc["^VIX"].rename("b")], axis=1).dropna()
print(f"RAW COR1M vs RAW VIX level: corr={a2['a'].corr(a2['b']):.4f}  n={len(a2)}")
a3 = pd.concat([rc21.rename("a"), volc["^VIX"].rename("b")], axis=1).dropna()
print(f"RAW realized_corr21 vs RAW VIX: corr={a3['a'].corr(a3['b']):.4f}  n={len(a3)}")
