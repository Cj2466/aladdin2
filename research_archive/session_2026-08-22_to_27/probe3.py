import sys
from datetime import date
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_897780eb-d4b-1/backend")
import numpy as np, pandas as pd
from app.services.market_data.yfinance_provider import YFinanceProvider
pd.set_option("display.width", 220)

UNIVERSE = [
    "BTC-USD","ETH-USD","XRP-USD","BNB-USD","ADA-USD","SOL-USD","DOGE-USD","DOT-USD",
    "AVAX-USD","LINK-USD","LTC-USD","BCH-USD","XLM-USD","TRX-USD","ATOM-USD","ETC-USD",
    "XMR-USD","ALGO-USD","VET-USD","FIL-USD","ICP-USD","HBAR-USD","EOS-USD","AAVE-USD",
    "MKR-USD","CRV-USD","SNX-USD","YFI-USD","SUSHI-USD","ZEC-USD","DASH-USD","NEO-USD",
    "THETA-USD","EGLD-USD","XTZ-USD","NEAR-USD","SAND-USD","MANA-USD","AXS-USD","ENJ-USD",
    "CHZ-USD","BAT-USD","ZIL-USD","QNT-USD","KSM-USD","WAVES-USD","UNI7083-USD","CAKE-USD",
    "RUNE-USD","KAVA-USD","HNT-USD","AR-USD","FLOW-USD","LRC-USD","ZRX-USD","KNC-USD",
    "RVN-USD","DCR-USD","QTUM-USD","ONT-USD","ICX-USD","OMG-USD","REN-USD","WAXP-USD",
    "AMP-USD","SRM-USD","CEL-USD",
    # dead / renamed -- the survivorship fix
    "LUNA1-USD","MATIC-USD","RNDR-USD","FTM-USD","GALA-USD","FTT-USD",
]
print(f"universe size = {len(UNIVERSE)}")
p = YFinanceProvider()
frames, missing = p.get_daily_ohlcv(UNIVERSE, date(2017, 11, 1), date(2026, 8, 27))
close, volume = frames["close"], frames["volume"]
print("missing:", missing)
print("panel:", close.index[0].date(), "..", close.index[-1].date(), len(close), "rows,", close.shape[1], "cols")

# calendar completeness: crypto trades 365/yr -> index should have no gaps
full = pd.date_range(close.index[0], close.index[-1], freq="D")
print("missing calendar days in index:", len(full.difference(close.index)))

WIN, MINP, GATE = 90, 60, 25e6
trail = volume.rolling(WIN, min_periods=MINP).median().shift(1)
elig = (trail >= GATE) & close.notna()
counts = elig.sum(axis=1)
sub = counts[counts.index >= "2020-11-01"]
print(f"\neligible names on/after 2020-11-01: min={sub.min()} p10={int(sub.quantile(.1))} "
      f"median={int(sub.median())} max={sub.max()}")
for y in range(2020, 2027):
    s = counts[counts.index.year == y]
    if len(s): print(f"   {y}: min={s.min():3d} med={int(s.median()):3d} max={s.max():3d}")

RF = 0.2
legs = (sub * RF).astype(int).clip(lower=1)
print(f"\nquintile leg sizes (rank_fraction={RF}): min={legs.min()} median={int(legs.median())} max={legs.max()}")
print(f"formations with leg < 5 (harness default min_names_per_leg): "
      f"{(legs < 5).mean():.1%} of days")

# dead coins: are they eligible while alive, and gone after?
print("\n=== dead coins under the gate ===")
for t in ["LUNA1-USD","MATIC-USD","RNDR-USD","FTM-USD","GALA-USD","FTT-USD"]:
    e = elig[t]
    on = e[e]
    print(f"  {t}: eligible on {len(on)} days, {on.index[0].date() if len(on) else None} .. "
          f"{on.index[-1].date() if len(on) else None}; last priced {close[t].dropna().index[-1].date()}")

# where does 2020-11-01 sit, and is the 730d lookback warmed from pre-start data?
pos = int(np.flatnonzero(close.index.date >= date(2020,11,1))[0])
print(f"\nrow position of 2020-11-01 = {pos} (730d lookback needs >=730) -> warmed from pre-start data: {pos>=730}")
print(f"rows from 2020-11-01 to end = {len(close)-pos} (~{(len(close)-pos)/365:.2f} yrs)")
for h in (90,180):
    print(f"  hold {h}d -> ~{(len(close)-pos)//h} non-overlapping formations")
