import warnings; warnings.filterwarnings("ignore")
import sys, numpy as np, pandas as pd, yfinance as yf
from app.services.research_lab.cross_sectional import (
    CrossSectionalData, CrossSectionalSpec, CrossSectionalConfig,
    run_cross_sectional_backtest, screen_cross_sectional_universe,
)

U = ["SHY","IEI","IEF","TLH","TLT","LQD","HYG","TIP"]
close = yf.download(U, start="2007-01-01", auto_adjust=True, progress=False)["Close"][U].dropna()
print("universe rows", len(close), close.index[0].date(), "->", close.index[-1].date())
data = CrossSectionalData(close=close)

def sig_carry(d: CrossSectionalData) -> pd.Series:
    """toy: 126d trailing total return (duration-carry proxy)"""
    w = d.close
    return w.iloc[-1] / w.iloc[0] - 1.0

specs = [
    CrossSectionalSpec(pattern_id=f"toy_h{h}", family="bond_toy", citation="smoke",
                       signal_fn=sig_carry, lookback_days=126, holding_days=h,
                       portfolio="long_short", rank_fraction=0.25)
    for h in (21, 63, 126)
]
cfg = CrossSectionalConfig(cost_bps=5.0, min_names_per_leg=2)
try:
    res = screen_cross_sectional_universe(data, specs, cfg, None)
    for r in res:
        print(f"  {r.pattern_id:10} sharpe={r.sharpe:+.3f} dsr_p={getattr(r,'dsr_p_value',None)} n_form={getattr(r,'n_formations',None)}")
    print("HARNESS RUNS ON BOND UNIVERSE: YES")
except Exception as e:
    import traceback; traceback.print_exc()
    print("HARNESS FAILED:", repr(e)[:300])
