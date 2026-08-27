"""Dump a byte-exact numeric fingerprint of the cross-sectional harness.

Run BEFORE and AFTER the financing/loud-failure change; the two hex digests
must match exactly for every scenario, proving zero behavior change for any
family that does not opt in.
"""
import hashlib
import struct
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.research_lab.cross_sectional import (  # noqa: E402
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)

ALWAYS = lambda _t, _d: True


def _close(returns_by_ticker, start, n):
    index = pd.bdate_range(start, periods=n)
    return pd.DataFrame(
        {t: 100.0 * np.cumprod(np.full(n, 1.0 + r)) for t, r in returns_by_ticker.items()},
        index=index,
    )


def _last_close(view):
    return view.close.iloc[-1]


def _spec(**kw):
    d = dict(
        pattern_id="s",
        family="f",
        citation="c",
        signal_fn=_last_close,
        lookback_days=10,
        holding_days=5,
        portfolio="long_short",
        rank_fraction=0.5,
    )
    d.update(kw)
    return CrossSectionalSpec(**d)


def _digest_result(h, res):
    h.update(res.status.encode())
    for v in res.daily_returns.to_numpy(dtype=float):
        h.update(struct.pack("<d", v))
    for ts in res.daily_returns.index:
        h.update(str(ts).encode())
    h.update(struct.pack("<d", res.total_cost))
    for f in res.formations:
        h.update(str(f.date).encode())
        h.update(struct.pack("<i", f.n_eligible))
        h.update(",".join(f.long_tickers).encode())
        h.update(",".join(f.short_tickers).encode())
        h.update(struct.pack("<d", f.turnover))
        h.update((f.skipped_reason or "").encode())
        h.update(struct.pack("<??", f.long_leg_value_weight_fallback, f.short_leg_value_weight_fallback))


scenarios = {}

# 1. plain long/short
close = _close({"A": 0.01, "B": -0.01}, "2024-01-01", 40)
scenarios["long_short"] = (CrossSectionalData(close=close), _spec(), CrossSectionalConfig(min_names_per_leg=1))

# 2. long_universe_hedged
close2 = _close({"A": 0.04, "B": 0.02, "C": 0.0, "D": -0.02}, "2024-01-01", 60)
scenarios["hedged"] = (
    CrossSectionalData(close=close2),
    _spec(portfolio="long_universe_hedged", rank_fraction=0.25),
    CrossSectionalConfig(min_names_per_leg=1),
)

# 3. delisting imputation on
close3 = _close({"A": 0.02, "B": 0.01, "C": -0.01, "D": -0.02}, "2024-01-01", 40)
close3.loc[close3.index[15]:, "A"] = np.nan
scenarios["delisting_imputed"] = (
    CrossSectionalData(close=close3),
    _spec(rank_fraction=0.5, holding_days=10),
    CrossSectionalConfig(min_names_per_leg=1, impute_delisting_returns=True),
)

# 4. overlapping cohorts
rng = np.random.default_rng(5)
index4 = pd.bdate_range("2023-01-02", periods=300)
close4 = pd.DataFrame(
    {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.012, len(index4))) for t in "ABCDEFGH"},
    index=index4,
)
scenarios["overlapping_cohorts"] = (
    CrossSectionalData(close=close4),
    _spec(signal_fn=lambda v: v.close.iloc[-20:].mean(), lookback_days=20, holding_days=24,
          cohort_formation_days=6, rank_fraction=0.25),
    CrossSectionalConfig(min_names_per_leg=1),
)

# 5. value weighting
mcap = close4 * 1_000_000.0
scenarios["value_weighted"] = (
    CrossSectionalData(close=close4, market_cap=mcap),
    _spec(signal_fn=lambda v: v.close.iloc[-20:].mean(), lookback_days=20, holding_days=10,
          rank_fraction=0.25, leg_weighting="value", requires_market_cap=True),
    CrossSectionalConfig(min_names_per_leg=1),
)

# 6. skipped formations (min_names_per_leg too high)
scenarios["all_skipped"] = (
    CrossSectionalData(close=close), _spec(), CrossSectionalConfig(min_names_per_leg=5)
)

out = []
for name, (data, spec, config) in scenarios.items():
    h = hashlib.sha256()
    res = run_cross_sectional_backtest(data, spec, config, ALWAYS)
    _digest_result(h, res)
    out.append(f"{name}: {h.hexdigest()}")

# 7. full screening pass digest
h = hashlib.sha256()
specs = [
    _spec(pattern_id="alpha", signal_fn=lambda v: v.close.iloc[-20:].mean(), lookback_days=20,
          holding_days=5, rank_fraction=0.25),
    _spec(pattern_id="beta", signal_fn=lambda v: v.close.iloc[-5:].mean(), lookback_days=20,
          holding_days=21, rank_fraction=0.25),
    _spec(pattern_id="gamma", lookback_days=5000),
]
results = screen_cross_sectional_universe(
    CrossSectionalData(close=close4), specs, CrossSectionalConfig(min_names_per_leg=1), ALWAYS
)
for r in results:
    h.update(r.pattern_id.encode())
    h.update(struct.pack("<iiddd", r.n_formations, r.n_skipped_formations, r.avg_names_per_leg,
                         r.sharpe_annualized, r.total_cost_drag))
    h.update(struct.pack("<dd", r.deflated_sharpe.sharpe_net_annualized, r.deflated_sharpe.dsr or -99.0))
    h.update(struct.pack("<ii", r.n_value_weighted_legs, r.n_value_weight_fallbacks))
out.append(f"screening_pass: {h.hexdigest()}")

print("\n".join(out))
