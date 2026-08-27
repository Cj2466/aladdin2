"""Catch-up path: N rows realized in ONE tick must equal N rows realized one
tick at a time (no gap, no double count), including across the 90-row cap.
Plus: check_underperformance's no-arg behavior."""
import inspect

import numpy as np
import pandas as pd

from app.services.research_lab import metrics
from app.services.forward_validation_service import check_underperformance
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
)
from app.services.research_lab.cross_sectional_forward import (
    MAX_CATCHUP_ROWS_PER_TICK,
    CrossSectionalForwardState,
    advance_forward_validation,
)

T = [f"T{i:02d}" for i in range(16)]
rng = np.random.default_rng(3)
N = 600
idx = pd.date_range("2021-01-01", periods=N, freq="D")
close = pd.DataFrame(
    40 * np.exp(np.cumsum(rng.normal(0.0002, 0.025, size=(N, len(T))), axis=0)),
    index=idx, columns=T,
)
close.iloc[400:, 3] = np.nan
basis = 1.0 / close.pct_change(fill_method=None).rolling(60, min_periods=20).std()
data = CrossSectionalData(close=close, leg_weight_basis=basis)
member = fixed_universe_membership(T)


def sig(h):
    return (h.close.iloc[-1] / h.close.iloc[0]) - 1.0


bad = 0
for hold in (1, 7, 30, 120):
    spec = CrossSectionalSpec(pattern_id="c", family="c", citation="c", signal_fn=sig,
                              lookback_days=120, holding_days=hold, portfolio="long_short",
                              rank_fraction=0.25, leg_weighting="inverse_vol")
    cfg = CrossSectionalConfig(cost_bps=30.0, min_names_per_leg=3,
                               financing_bps_per_year=400.0, periods_per_year=365.0)
    # one at a time
    s1, last1, days1 = CrossSectionalForwardState(), None, []
    for k in range(200, N):
        s1, res = advance_forward_validation(data.__class__(close=close.iloc[:k + 1],
                                                            leg_weight_basis=basis.iloc[:k + 1]),
                                             spec, cfg, member, s1, last1)
        days1 += res
        last1 = res[-1].date.date()
    # first tick, then ONE big catch-up over the remaining 399 rows (> 90 cap,
    # so it takes several ticks -- exactly the outage scenario)
    s2, last2, days2 = CrossSectionalForwardState(), None, []
    s2, res = advance_forward_validation(
        data.__class__(close=close.iloc[:201], leg_weight_basis=basis.iloc[:201]),
        spec, cfg, member, s2, last2)
    days2 += res
    last2 = res[-1].date.date()
    while True:
        s2, res = advance_forward_validation(data, spec, cfg, member, s2, last2)
        if not res:
            break
        assert len(res) <= MAX_CATCHUP_ROWS_PER_TICK
        days2 += res
        last2 = res[-1].date.date()
    if len(days1) != len(days2):
        print("LEN MISMATCH", hold, len(days1), len(days2)); bad += 1; continue
    for a, b in zip(days1, days2):
        if (a.date, a.realized, a.reformed, repr(a.net_return), repr(a.equity),
                repr(a.turnover_cost), repr(a.financing_cost)) != (
                b.date, b.realized, b.reformed, repr(b.net_return), repr(b.equity),
                repr(b.turnover_cost), repr(b.financing_cost)):
            print("DAY MISMATCH", hold, a.date, a, b); bad += 1; break
    eq = 1.0
    for d in days1:
        if d.realized:
            eq *= 1.0 + d.net_return
    if abs(eq - s1.equity) > 1e-12:
        print("EQUITY DRIFT", hold, eq, s1.equity); bad += 1
    n_real = sum(1 for d in days1 if d.realized)
    n_charged = sum(1 for d in days1 if d.turnover_cost)
    print(f"hold={hold:4d} days={len(days1)} realized={n_real} formations={s1.n_formations} "
          f"turnover-charged days={n_charged} equity={s1.equity:.6f}")

print("catch-up problems:", bad)
print("sharpe default ppy:", inspect.signature(metrics.sharpe_ratio).parameters["periods_per_year"].default,
      "== TRADING_DAYS_PER_YEAR", metrics.TRADING_DAYS_PER_YEAR)
p = inspect.signature(check_underperformance).parameters["periods_per_year"]
print("check_underperformance kw-only:", p.kind.name, "default:", p.default)
mism = 0
for seed in range(200):
    r = np.random.default_rng(seed)
    dr = [{"net_return": float(x)} for x in r.normal(0, 0.01, size=r.integers(0, 200))]
    if check_underperformance(dr) != check_underperformance(dr, periods_per_year=metrics.TRADING_DAYS_PER_YEAR):
        mism += 1
print("no-arg vs explicit-252 mismatches over 200 random series:", mism)
