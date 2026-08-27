"""INDEPENDENT regression harness (written by the verifier, not the builder).
Runs on both the pre-fix and post-fix trees with NO import of the builder's
own fixture module. Dumps EVERY float on EVERY screening result."""
import json, sys, math
import numpy as np
import pandas as pd
from dataclasses import fields, is_dataclass

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig, CrossSectionalData, fixed_universe_membership,
    screen_cross_sectional_universe,
)

SEED = 777001          # deliberately NOT the builder's seed
N_T, N_ROWS = 60, 1900

def panel(names):
    n = len(names)
    rng = np.random.default_rng(SEED)
    idx = pd.bdate_range("2015-01-02", periods=N_ROWS)
    drift = rng.normal(0.00015, 0.00035, n); vol = rng.uniform(0.007, 0.032, n)
    mkt = rng.normal(0, 1, (N_ROWS, 1)); beta = rng.uniform(0.3, 1.5, n)
    lr = drift + vol * (0.55 * mkt * beta + 0.85 * rng.normal(0, 1, (N_ROWS, n)))
    close = pd.DataFrame(100*np.exp(np.cumsum(lr, 0)), index=idx, columns=names)
    wedge = np.exp(np.cumsum(np.tile(rng.uniform(0, 1.3e-4, n), (N_ROWS, 1)), 0))
    px = close / wedge
    open_ = pd.DataFrame((close*(1+rng.normal(0,0.0021,(N_ROWS,n)))).to_numpy(), index=idx, columns=names)
    volume = pd.DataFrame(rng.lognormal(13.8, 0.55, (N_ROWS, n)), index=idx, columns=names)
    steps = np.repeat(np.cumprod(1+rng.normal(-0.0021,0.011,(N_ROWS//63+1,n)),0),63,0)[:N_ROWS]
    shares = pd.DataFrame(1.1e9*steps, index=idx, columns=names)
    r = close.pct_change(fill_method=None)
    tv = r.rolling(63, min_periods=21).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        lwb = (1.0/tv).replace([np.inf,-np.inf], np.nan)
    return CrossSectionalData(close=close, open=open_, volume=volume,
        market_cap=shares*px, price_only_close=px, leg_weight_basis=lwb,
        shares_outstanding=shares)

def families():
    from app.services.research_lab import (cross_sectional_bonds as B,
        cross_sectional_buyback as BB, cross_sectional_commodities as C,
        cross_sectional_fx as FX, cross_sectional_ivol as IV,
        cross_sectional_patterns as P, cross_sectional_patterns_d2 as D2,
        cross_sectional_patterns_round_d as RD)
    T = [f"T{i:02d}" for i in range(N_T)]
    rng = np.random.default_rng(SEED+5)
    months = pd.date_range("2014-01-31", periods=150, freq="ME")
    rd_ = pd.DataFrame(rng.normal(0,0.016,(len(months),N_T)), index=months, columns=T)
    fxc = CrossSectionalConfig(cost_bps=FX.FX_SPREAD_BPS_ONE_WAY,
        financing_bps_per_year=FX.FX_FINANCING_BPS_PER_YEAR,
        min_names_per_leg=FX.FX_MIN_NAMES_PER_LEG)
    return {
      "bonds": (list(B.BONDS_FAMILY), B.default_bonds_config(), list(B.BONDS_UNIVERSE)),
      "buyback": (list(BB.BUYBACK_FAMILY), BB.default_buyback_config(), T),
      "commodities": (C.build_commodities_family(), C.default_commodities_config(), T),
      "fx": (FX.build_fx_family(rd_), fxc, T),
      "ivol": (list(IV.ROUND_D1_FAMILY), CrossSectionalConfig(), T),
      "round_c": (list(P.ROUND_C_FAMILY), CrossSectionalConfig(), T),
      "d2": (list(D2.D2_FAMILY), CrossSectionalConfig(), T),
      "round_d": (list(RD.ROUND_D_LPS_INTRADAY_FAMILY), CrossSectionalConfig(), T),
    }

def floats_of(obj, prefix=""):
    """Recursively harvest every float/int field — nothing hand-picked."""
    out = {}
    if is_dataclass(obj):
        for f in fields(obj):
            v = getattr(obj, f.name)
            out.update(floats_of(v, f"{prefix}{f.name}."))
    elif isinstance(obj, (float, int)) and not isinstance(obj, bool):
        out[prefix[:-1]] = float(obj)
    elif obj is None:
        out[prefix[:-1]] = None
    return out

def main():
    all_out = {}
    nspec = 0
    for name, (specs, cfg, tick) in families().items():
        res = screen_cross_sectional_universe(panel(tick), specs, cfg, fixed_universe_membership(tick))
        fam = {}
        for r in res:
            fam[r.pattern_id] = floats_of(r)
            nspec += 1
        all_out[name] = fam
    nfloat = sum(len(v) for f in all_out.values() for v in f.values())
    print(f"FAMILIES={len(all_out)} SPECS={nspec} FLOATS={nfloat}", file=sys.stderr)
    for k, v in all_out.items():
        print(f"  {k}: {len(v)} specs", file=sys.stderr)
    json.dump(all_out, open(sys.argv[1], "w"), indent=0, sort_keys=True, default=str)

main()
