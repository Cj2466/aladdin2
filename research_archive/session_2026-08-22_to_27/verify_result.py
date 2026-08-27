"""Two verification passes on the production result:
 (1) why does curve_carry skip formations when the others never do?
 (2) does curve_carry's positive Sharpe survive removing its rate beta, or
     is it just the term premium in disguise?
"""
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_9fd00b72-30a-6/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.cross_sectional import (  # noqa: E402
    CrossSectionalData,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_bonds import (  # noqa: E402
    BONDS_FAMILY,
    BONDS_UNIVERSE,
    TREASURY_LADDER,
    default_bonds_config,
    rate_factor,
)
from app.services.research_lab.metrics import sharpe_ratio  # noqa: E402

provider = YFinanceProvider()
tr, px, _ = provider.get_total_and_price_return_closes(list(BONDS_UNIVERSE), date(2006, 1, 1), date(2026, 8, 27))
common = tr.dropna(axis=0, how="any")
start = common.index[252].date()
config = default_bonds_config()
config.formation_start = start
data = CrossSectionalData(close=tr, price_only_close=px)
membership = fixed_universe_membership(BONDS_UNIVERSE)
spec_by_id = {s.pattern_id: s for s in BONDS_FAMILY}

print("=" * 96)
print("(1) WHY curve_carry SKIPS FORMATIONS")
print("=" * 96)
for pid in ("bonds_curve_carry_l63_h126", "bonds_curve_carry_l252_h63"):
    replay = run_cross_sectional_backtest(data, spec_by_id[pid], config, membership)
    skipped = [f for f in replay.formations if f.skipped_reason is not None]
    print(f"\n  {pid}: {len(skipped)} skipped of {len(replay.formations)}")
    reasons = {}
    for f in skipped:
        reasons[f.skipped_reason] = reasons.get(f.skipped_reason, 0) + 1
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    x{n}: {reason}")
    print(f"    skipped formation dates: {[f.date.date().isoformat() for f in skipped][:12]}")

print()
print("=" * 96)
print("(2) IS curve_carry's EDGE REAL ALPHA, OR JUST THE TERM PREMIUM?")
print("=" * 96)
returns_all = tr.pct_change(fill_method=None)
factor = rate_factor(returns_all)

print(f"\n{'pattern_id':<30}{'Sharpe':>9}{'rateBeta':>10}{'alpha/yr':>10}{'t(alpha)':>10}{'residSharpe':>13}")
print("-" * 82)
for pid in sorted(spec_by_id):
    replay = run_cross_sectional_backtest(data, spec_by_id[pid], config, membership)
    if replay.status != "ok":
        continue
    s = replay.daily_returns
    f = factor.reindex(s.index)
    joined = pd.concat([s.rename("r"), f.rename("f")], axis=1).dropna()
    beta = joined["r"].cov(joined["f"]) / joined["f"].var(ddof=1)
    resid = joined["r"] - beta * joined["f"]
    alpha_daily = resid.mean()
    se = resid.std(ddof=1) / np.sqrt(len(resid))
    t_alpha = alpha_daily / se
    print(
        f"{pid:<30}{sharpe_ratio(s):>+9.3f}{beta:>+10.3f}{alpha_daily*252:>+10.3%}"
        f"{t_alpha:>+10.2f}{sharpe_ratio(resid):>+13.3f}"
    )

print()
print("=" * 96)
print("(3) WHAT THE RATE FACTOR ITSELF DID OVER THE SAME WINDOW")
print("=" * 96)
f_win = factor.loc[factor.index.date >= start].dropna()
print(f"  rate factor (equal-weighted Treasury ladder) Sharpe over the replay window: "
      f"{sharpe_ratio(f_win):+.3f}")
print(f"  cumulative: {f_win.sum():+.2%} over {len(f_win)/252:.1f} years")
print("  -> a book with a large positive rate beta inherits this, edge or no edge.")
