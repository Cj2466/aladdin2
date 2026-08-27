"""Probe a broad crypto candidate list -- including coins that DIED -- and
measure the diagnostics the universe rules will key on."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_897780eb-d4b-1/backend")

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)

CANDIDATES = [
    # majors / long-lived
    "BTC-USD", "ETH-USD", "XRP-USD", "BNB-USD", "ADA-USD", "SOL-USD", "DOGE-USD",
    "DOT-USD", "AVAX-USD", "LINK-USD", "LTC-USD", "BCH-USD", "XLM-USD", "TRX-USD",
    "ATOM-USD", "ETC-USD", "XMR-USD", "ALGO-USD", "VET-USD", "FIL-USD", "ICP-USD",
    "HBAR-USD", "EOS-USD", "AAVE-USD", "MKR-USD", "CRV-USD", "SNX-USD", "COMP-USD",
    "YFI-USD", "SUSHI-USD", "ZEC-USD", "DASH-USD", "NEO-USD", "THETA-USD",
    "EGLD-USD", "XTZ-USD", "FTM-USD", "NEAR-USD", "APE-USD", "SAND-USD", "MANA-USD",
    "AXS-USD", "GRT-USD", "ENJ-USD", "CHZ-USD", "BAT-USD", "ZIL-USD", "QNT-USD",
    "KSM-USD", "WAVES-USD", "UNI7083-USD", "CAKE-USD", "RUNE-USD", "KAVA-USD",
    "HNT-USD", "AR-USD", "FLOW-USD", "GALA-USD", "LRC-USD", "ZRX-USD", "KNC-USD",
    "RVN-USD", "DCR-USD", "QTUM-USD", "ONT-USD", "ICX-USD", "IOTA-USD",
    # coins that DIED or were renamed -- the survivorship-bias fix
    "LUNA1-USD", "UST-USD", "FTT-USD", "MATIC-USD", "RNDR-USD", "CEL-USD",
    "ANC-USD", "SRM-USD", "OMG-USD", "REN-USD", "WAXP-USD", "AMP-USD",
    # known-bad (probe to confirm exclusion evidence)
    "SHIB-USD", "UNI-USD", "TON11419-USD", "USDT-USD", "USDC-USD", "DAI-USD",
]

p = YFinanceProvider()
END = date(2026, 8, 27)
frames, missing = p.get_daily_ohlcv(CANDIDATES, date(2015, 1, 1), END)
close = frames["close"]
volume = frames["volume"]
print(f"missing entirely: {missing}\n")

rows = []
last_row = close.index[-1]
for t in CANDIDATES:
    if t not in close.columns:
        rows.append({"ticker": t, "n": 0, "note": "no column"})
        continue
    s = close[t].dropna()
    if s.empty:
        rows.append({"ticker": t, "n": 0, "note": "empty"})
        continue
    v = volume[t].reindex(s.index) if t in volume.columns else pd.Series(np.nan, index=s.index)
    dv = (s * v).dropna()
    chg = s.pct_change(fill_method=None).dropna()
    stale = float((chg == 0.0).mean()) if len(chg) else np.nan
    # last 365 days of the sample
    recent = dv[dv.index >= (close.index[-1] - pd.Timedelta(days=365))]
    alive = bool(close[t].notna().iloc[-1])
    rows.append({
        "ticker": t,
        "n": len(s),
        "start": s.index[0].date(),
        "end": s.index[-1].date(),
        "alive": alive,
        "med_dv_all": float(dv.median()) if len(dv) else np.nan,
        "med_dv_1y": float(recent.median()) if len(recent) else np.nan,
        "stale%": round(stale * 100, 1),
        "minpx": float(s.min()),
        "cv": round(float(s.std() / s.mean()), 2) if s.mean() else np.nan,
    })

df = pd.DataFrame(rows).sort_values("med_dv_all", ascending=False, na_position="last")
df["med_dv_all"] = df["med_dv_all"].map(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")
df["med_dv_1y"] = df["med_dv_1y"].map(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")
print(df.to_string(index=False))

print("\n=== common-history start for the top-N-by-median-dollar-volume alive-or-dead sets ===")
ranked = [r["ticker"] for r in rows if r.get("n", 0) > 200]
for n in (10, 15, 20, 25, 30):
    sub = ranked[:n]
    have = [t for t in sub if t in close.columns]
    common = close[have].dropna(how="any")
    print(f"  top {n}: common history {common.index[0].date() if len(common) else None} .. "
          f"{common.index[-1].date() if len(common) else None} ({len(common)} rows)")
