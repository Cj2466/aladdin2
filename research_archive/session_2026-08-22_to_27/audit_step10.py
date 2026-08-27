import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np
from datetime import date
from app.services.research_lab.cross_sectional import CrossSectionalData, select_leg_tickers
from app.services.research_lab.cross_sectional_buyback import signal_net_share_issuance, BUYBACK_RANK_FRACTION
from app.services.research_lab.sp500_membership_history import was_member
SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
frame = pd.read_pickle(f"{SP}/audit_bb_shares.pkl"); close = pd.read_pickle(f"{SP}/audit_bb_close.pkl")

SUSPECT = ["BNY","PARA","COL","ECHO","SOLS","STI","DOW","IR","FOX","FOXA","AIV"]
# Replay each spec's real formation grid and report where the suspects land.
for lookback, holding in [(126,126),(252,252),(504,126),(504,252)]:
    idx = close.index
    days = np.array([ts.date() for ts in idx])
    start_pos = int(np.flatnonzero(days >= date(2018,1,2))[0])
    start_pos = max(start_pos, lookback+1-1)
    print(f"\n===== lookback {lookback}, holding {holding} =====")
    for i in range(start_pos, len(idx)-1, holding):
        fday = days[i]
        fc = close.iloc[i]
        elig = [t for t in close.columns if was_member(t, fday) and np.isfinite(fc[t])]
        if not elig: continue
        view = CrossSectionalData(close=close.iloc[max(0,i-lookback):i+1].loc[:,elig],
                                  shares_outstanding=frame.iloc[max(0,i-lookback):i+1].loc[:,elig])
        sig = signal_net_share_issuance(view, lookback_days=lookback)
        top, bot = select_leg_tickers(sig, BUYBACK_RANK_FRACTION)
        hits = [(t, "SHORT" if t in bot else "LONG") for t in SUSPECT if t in top or t in bot]
        if hits:
            ranked = sig.dropna()
            det = []
            for t,leg in hits:
                pct = float((ranked < ranked[t]).mean())
                det.append(f"{t}({leg},sig={ranked[t]:+.3f},pctile={pct:.3f})")
            print(f"  {fday}  n_ranked={len(ranked)} leg={len(top)}  " + " ".join(det))
