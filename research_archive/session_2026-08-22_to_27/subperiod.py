from datetime import date
import numpy as np, pandas as pd
from app.services.research_lab.cross_sectional_crypto import (
    build_crypto_price_panel, build_eligibility, build_inverse_vol_basis,
    build_crypto_family, default_crypto_config, liquidity_membership,
    CRYPTO_FORMATION_START, CRYPTO_PERIODS_PER_YEAR, CRYPTO_MARKET_TICKER)
from app.services.research_lab.cross_sectional import (
    CrossSectionalData, run_cross_sectional_backtest)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.metrics import sharpe_ratio

close, volume, missing = build_crypto_price_panel(YFinanceProvider(), date(2026,8,25))
elig = build_eligibility(close, volume)
data = CrossSectionalData(close=close, leg_weight_basis=build_inverse_vol_basis(close))
cfg = default_crypto_config(); cfg.formation_start = CRYPTO_FORMATION_START
specs = {s.pattern_id: s for s in build_crypto_family()}
mfn = liquidity_membership(elig)

for pid in ["xc_btcbeta_l180_h180","xc_btcbeta_l180_h90","xc_lowvol_l90_h90"]:
    rep = run_cross_sectional_backtest(data, specs[pid], cfg, mfn)
    r = rep.daily_returns.dropna()
    print(f"\n=== {pid}  full SR={sharpe_ratio(r,periods_per_year=CRYPTO_PERIODS_PER_YEAR):+.3f}  n={len(r)}")
    # calendar-year decomposition
    for y, g in r.groupby(r.index.year):
        if len(g) > 30:
            print(f"   {y}: SR={sharpe_ratio(g,periods_per_year=CRYPTO_PERIODS_PER_YEAR):+7.3f}  "
                  f"cum={100*((1+g).prod()-1):+8.1f}%  n={len(g)}")
    # 2022 bear (crypto winter) removed
    ex = r[~((r.index>=pd.Timestamp('2021-11-01'))&(r.index<=pd.Timestamp('2022-12-31')))]
    print(f"   EX crypto-winter (2021-11..2022-12): SR={sharpe_ratio(ex,periods_per_year=CRYPTO_PERIODS_PER_YEAR):+.3f} n={len(ex)}")
    # first half / second half
    h = len(r)//2
    print(f"   H1 SR={sharpe_ratio(r.iloc[:h],periods_per_year=CRYPTO_PERIODS_PER_YEAR):+.3f}   "
          f"H2 SR={sharpe_ratio(r.iloc[h:],periods_per_year=CRYPTO_PERIODS_PER_YEAR):+.3f}")
