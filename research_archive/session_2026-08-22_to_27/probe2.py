"""Universe screen with CORRECT dollar-volume units (yfinance crypto Volume
is already USD notional)."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_897780eb-d4b-1/backend")

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)

CANDIDATES = [
    "BTC-USD", "ETH-USD", "XRP-USD", "BNB-USD", "ADA-USD", "SOL-USD", "DOGE-USD",
    "DOT-USD", "AVAX-USD", "LINK-USD", "LTC-USD", "BCH-USD", "XLM-USD", "TRX-USD",
    "ATOM-USD", "ETC-USD", "XMR-USD", "ALGO-USD", "VET-USD", "FIL-USD", "ICP-USD",
    "HBAR-USD", "EOS-USD", "AAVE-USD", "MKR-USD", "CRV-USD", "SNX-USD",
    "YFI-USD", "SUSHI-USD", "ZEC-USD", "DASH-USD", "NEO-USD", "THETA-USD",
    "EGLD-USD", "XTZ-USD", "FTM-USD", "NEAR-USD", "SAND-USD", "MANA-USD",
    "AXS-USD", "ENJ-USD", "CHZ-USD", "BAT-USD", "ZIL-USD", "QNT-USD",
    "KSM-USD", "WAVES-USD", "UNI7083-USD", "CAKE-USD", "RUNE-USD", "KAVA-USD",
    "HNT-USD", "AR-USD", "FLOW-USD", "GALA-USD", "LRC-USD", "ZRX-USD", "KNC-USD",
    "RVN-USD", "DCR-USD", "QTUM-USD", "ONT-USD", "ICX-USD",
    "LUNA1-USD", "FTT-USD", "MATIC-USD", "RNDR-USD", "CEL-USD", "SRM-USD",
    "OMG-USD", "REN-USD", "WAXP-USD", "AMP-USD",
    "SHIB-USD", "UNI-USD", "APE-USD", "COMP-USD", "GRT-USD", "ANC-USD",
    "USDT-USD", "USDC-USD", "DAI-USD", "UST-USD",
]

p = YFinanceProvider()
frames, missing = p.get_daily_ohlcv(CANDIDATES, date(2015, 1, 1), date(2026, 8, 27))
close, volume = frames["close"], frames["volume"]

rows = []
for t in CANDIDATES:
    s = close[t].dropna() if t in close.columns else pd.Series(dtype=float)
    if s.empty:
        rows.append({"ticker": t, "n": 0}); continue
    dv = volume[t].reindex(s.index).dropna()          # ALREADY USD
    chg = s.pct_change(fill_method=None).dropna()
    stale = float((chg == 0.0).mean()) if len(chg) else np.nan
    recent = dv[dv.index >= (close.index[-1] - pd.Timedelta(days=365))]
    rows.append({
        "ticker": t, "n": len(s), "start": s.index[0].date(), "end": s.index[-1].date(),
        "alive": bool(close[t].notna().iloc[-1]),
        "dv_all_M": round(float(dv.median()) / 1e6, 1) if len(dv) else np.nan,
        "dv_1y_M": round(float(recent.median()) / 1e6, 1) if len(recent) else np.nan,
        "stale%": round(stale * 100, 1),
    })

df = pd.DataFrame(rows).sort_values("dv_all_M", ascending=False, na_position="last")
print(df.to_string(index=False))

# How many names clear a $25M/day trailing gate at each month-end?
print("\n=== breadth over time at a $25M/day trailing-90d-median gate ===")
dvol = volume.reindex(columns=[c for c in close.columns])
trail = dvol.rolling(90, min_periods=60).median().shift(1)
priced = close.notna()
STABLE = {"USDT-USD", "USDC-USD", "DAI-USD", "UST-USD"}
BROKEN = {"SHIB-USD", "UNI-USD", "APE-USD", "COMP-USD", "GRT-USD", "ANC-USD"}
keep = [c for c in close.columns if c not in STABLE and c not in BROKEN]
gate = (trail[keep] >= 25e6) & priced[keep]
counts = gate.sum(axis=1)
for y in range(2019, 2027):
    sub = counts[counts.index.year == y]
    if len(sub):
        print(f"  {y}: min={sub.min():3d} median={int(sub.median()):3d} max={sub.max():3d}")
first_ok = counts[counts >= 12]
print(f"  first date with >=12 eligible: {first_ok.index[0].date() if len(first_ok) else None}")
first_ok15 = counts[counts >= 15]
print(f"  first date with >=15 eligible: {first_ok15.index[0].date() if len(first_ok15) else None}")
