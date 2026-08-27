"""A/B: replay every real family spec through BOTH the refactored
cross_sectional.py and main's pre-refactor copy, on identical synthetic
panels, and require bit-identical daily returns, formations and cost totals."""

import importlib.util
import sys

import numpy as np
import pandas as pd

SCRATCH = (
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/cross_sectional_main.py"
)
_s = importlib.util.spec_from_file_location("cs_main", SCRATCH)
cs_main = importlib.util.module_from_spec(_s)
sys.modules["cs_main"] = cs_main
_s.loader.exec_module(cs_main)

import app.services.research_lab.cross_sectional as cs_new  # noqa: E402
from app.services.research_lab.cross_sectional_bonds import _build_bonds_family  # noqa: E402
from app.services.research_lab.cross_sectional_buyback import _build_buyback_family  # noqa: E402
from app.services.research_lab.cross_sectional_commodities import (  # noqa: E402
    build_commodities_family,
)
from app.services.research_lab.cross_sectional_crypto import (  # noqa: E402
    build_crypto_family,
    build_inverse_vol_basis,
    default_crypto_config,
)
from app.services.research_lab.cross_sectional_ivol import _build_round_d1_family  # noqa: E402
from app.services.research_lab.cross_sectional_patterns import _build_round_c_family  # noqa: E402
from app.services.research_lab.cross_sectional_patterns_d2 import _build_d2_family  # noqa: E402


def panel(n_rows, n_tickers, seed):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=pd.Timestamp("2026-08-20"), periods=n_rows, freq="D")
    return pd.DataFrame(
        {
            f"T{i:02d}": 100 * np.exp(np.cumsum(rng.normal(0.0004 * (i - n_tickers / 2) / n_tickers, 0.02, n_rows)))
            for i in range(n_tickers)
        },
        index=dates,
    )


families = [
    ("crypto", build_crypto_family(), default_crypto_config()),
    ("commodities", build_commodities_family(), None),
    ("bonds", _build_bonds_family(), None),
    ("round_c", _build_round_c_family(), None),
    ("ivol_d1", _build_round_d1_family(), None),
    ("d2", _build_d2_family(), None),
    ("buyback", _build_buyback_family(), None),
]


def key(r):
    return (
        r.status,
        r.total_cost,
        r.total_financing_cost,
        r.n_zero_eligible_formations,
        list(r.daily_returns.index),
        [float(v) for v in r.daily_returns.to_numpy()],
        [
            (
                f.date,
                tuple(f.long_tickers),
                tuple(f.short_tickers),
                f.turnover,
                f.skipped_reason,
                f.long_leg_value_weight_fallback,
                f.short_leg_value_weight_fallback,
                f.n_eligible,
            )
            for f in r.formations
        ],
    )


n_compared = 0
n_ok_status = 0
mismatches = []
for fam_name, specs, fam_config in families:
    max_lb = max(s.lookback_days for s in specs)
    n_rows = max_lb + 300
    close = panel(n_rows, 30, seed=abs(hash(fam_name)) % 10_000)
    tickers = list(close.columns)
    for s in specs:
        base = fam_config if fam_config is not None else cs_new.CrossSectionalConfig()

        def mk(mod, base=base, max_lb=max_lb, close=close):
            c = mod.CrossSectionalConfig(
                cost_bps=base.cost_bps,
                min_names_per_leg=min(base.min_names_per_leg, 3),
                financing_bps_per_year=base.financing_bps_per_year,
                periods_per_year=base.periods_per_year,
                impute_delisting_returns=base.impute_delisting_returns,
                imputed_delisting_return=base.imputed_delisting_return,
            )
            c.formation_start = close.index[max_lb].date()
            return c

        extras = {}
        if s.requires_open:
            extras["open"] = close * 0.999
        if s.requires_volume:
            extras["volume"] = pd.DataFrame(1e7, index=close.index, columns=close.columns)
        if s.requires_market_cap or s.leg_weighting == "value":
            extras["market_cap"] = close * 1e6
        if s.requires_price_only_close:
            extras["price_only_close"] = close * 0.98
        if s.requires_shares_outstanding:
            extras["shares_outstanding"] = pd.DataFrame(
                np.linspace(1e6, 9e5, len(close))[:, None].repeat(len(tickers), 1),
                index=close.index,
                columns=close.columns,
            )
        if s.leg_weighting == "inverse_vol":
            extras["leg_weight_basis"] = build_inverse_vol_basis(close)

        s_old = cs_main.CrossSectionalSpec(
            pattern_id=s.pattern_id,
            family=s.family,
            citation=s.citation,
            signal_fn=s.signal_fn,
            lookback_days=s.lookback_days,
            holding_days=s.holding_days,
            portfolio=s.portfolio,
            rank_fraction=s.rank_fraction,
            requires_open=s.requires_open,
            requires_volume=s.requires_volume,
            requires_market_cap=s.requires_market_cap,
            requires_price_only_close=s.requires_price_only_close,
            requires_shares_outstanding=s.requires_shares_outstanding,
            leg_weighting=s.leg_weighting,
            cohort_formation_days=s.cohort_formation_days,
        )
        try:
            r_new = cs_new.run_cross_sectional_backtest(
                cs_new.CrossSectionalData(close=close, **extras),
                s,
                mk(cs_new),
                cs_new.fixed_universe_membership(tickers),
            )
            r_old = cs_main.run_cross_sectional_backtest(
                cs_main.CrossSectionalData(close=close, **extras),
                s_old,
                mk(cs_main),
                cs_main.fixed_universe_membership(tickers),
            )
        except Exception as e:  # noqa: BLE001
            mismatches.append((fam_name, s.pattern_id, f"raised {type(e).__name__}: {e}"))
            continue
        n_compared += 1
        if r_new.status == "ok":
            n_ok_status += 1
        if key(r_new) != key(r_old):
            mismatches.append((fam_name, s.pattern_id, "OUTPUT DIFFERS"))

print(
    f"\nA/B compared {n_compared} real production specs across {len(families)} families "
    f"({n_ok_status} produced a full status='ok' replay)."
)
print("MISMATCHES:", len(mismatches))
for m in mismatches[:20]:
    print("  ", m)
