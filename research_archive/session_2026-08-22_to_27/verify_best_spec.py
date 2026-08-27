"""Independent verification of the production run's best spec: is
cmd_momentum_l126_h126_inverse_vol's +0.91 Sharpe (a) commodity-market
beta in disguise, (b) a couple of extreme days, or (c) an actual
cross-sectional spread? Also re-verify the H=63-survives-costs claim from
the realized numbers."""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-1/backend")
import numpy as np
import pandas as pd
from datetime import date
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import run_cross_sectional_backtest, fixed_universe_membership, CrossSectionalData
from app.services.research_lab.cross_sectional_commodities import (
    COMMODITIES_UNIVERSE, build_commodities_family, build_commodities_price_panel,
    build_inverse_vol_basis, default_commodities_config,
)
from app.services.research_lab.metrics import sharpe_ratio

provider = YFinanceProvider()
panel, flags, missing = build_commodities_price_panel(provider, end=date.today())
basis = build_inverse_vol_basis(panel)
data = CrossSectionalData(close=panel, leg_weight_basis=basis)
membership = fixed_universe_membership(COMMODITIES_UNIVERSE)
config = default_commodities_config()
specs = {s.pattern_id: s for s in build_commodities_family()}

for pid in ("cmd_momentum_l126_h126_inverse_vol", "cmd_momentum_l126_h63_inverse_vol"):
    res = run_cross_sectional_backtest(data, specs[pid], config, membership)
    r = res.daily_returns
    market = panel.pct_change(fill_method=None).mean(axis=1).reindex(r.index)
    joined = pd.concat([r.rename("s"), market.rename("m")], axis=1).dropna()
    beta = joined["s"].cov(joined["m"]) / joined["m"].var(ddof=1)
    resid = joined["s"] - beta * joined["m"]
    t_alpha = resid.mean() / (resid.std(ddof=1) / np.sqrt(len(resid)))
    print(f"\n{pid}")
    print(f"  sharpe {sharpe_ratio(r):+.3f} | ann vol {r.std(ddof=1)*np.sqrt(252):.1%} | n={len(r)}")
    print(f"  market(EW basket) sharpe {sharpe_ratio(joined['m']):+.3f}")
    print(f"  beta to EW basket {beta:+.3f} | neutralized sharpe {sharpe_ratio(resid):+.3f} | alpha t {t_alpha:+.2f}")
    total = r.sum()
    top5 = r.nlargest(5).sum()
    bot5 = r.nsmallest(5).sum()
    print(f"  cumulative(sum) {total:+.2%}; top-5 days {top5:+.2%}, bottom-5 {bot5:+.2%}")
    ex = r.drop(r.abs().nlargest(5).index)
    print(f"  sharpe excluding 5 largest |days|: {sharpe_ratio(ex):+.3f}")
    print(f"  skew {r.skew():+.2f} kurt {r.kurt():+.2f}")
    # year-by-year: does one year carry it?
    yearly = r.groupby(r.index.year).apply(lambda x: float(x.sum()))
    print("  yearly sums:", {int(y): f"{v:+.1%}" for y, v in yearly.items()})
    # formation audit: does the long leg just park in one ticker?
    from collections import Counter
    longs, shorts = Counter(), Counter()
    formed = [f for f in res.formations if f.skipped_reason is None]
    for f in formed:
        longs.update(f.long_tickers); shorts.update(f.short_tickers)
    print(f"  {len(formed)} formations; long-leg counts {dict(longs.most_common())}")
    print(f"  short-leg counts {dict(shorts.most_common())}")
