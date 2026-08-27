"""Controlled before/after: the S&P 600 IVOL family replayed against the SAME
saved production fetch, three ways --
  A  no fix              (what production does today)
  B  time axis only      (restrict_share_counts_to_price_lifecycle)
  C  time axis + band    (the wiring being proposed)
so the A/B ablation shows which check moves what.
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.research_lab.cross_sectional import (  # noqa: E402
    CrossSectionalData,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_ivol import (  # noqa: E402
    build_point_in_time_market_cap,
    implausible_market_cap_mask,
    restrict_share_counts_to_price_lifecycle,
)
from app.services.research_lab.cross_sectional_small_mid_cap import (  # noqa: E402
    IVOL_N_TRIALS,
    SMALL_CAP_IVOL_FAMILY,
    default_small_cap_config,
)
from app.services.research_lab.small_cap_membership_history import was_member  # noqa: E402

HERE = Path(__file__).parent
with (HERE / "sc600_fetch.pkl").open("rb") as fh:
    D = pickle.load(fh)

close = D["close"]
START = D["start"]
mcap_close = D["mcap_close"]
mcap_close = (
    pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    if mcap_close.empty
    else mcap_close.reindex(index=close.index, columns=close.columns)
)
splits, shares = D["splits"], D["shares"]

SC600_MIN = 1.0e7
SC600_MAX = 1.5e11


def market_cap(mode: str):
    sh = shares
    if mode in ("B", "C"):
        sh, dropped = restrict_share_counts_to_price_lifecycle(sh, close)
    mc, no_shares = build_point_in_time_market_cap(mcap_close, sh, splits)
    n_mask = 0
    if mode == "C":
        m = implausible_market_cap_mask(mc, minimum_usd=SC600_MIN, maximum_usd=SC600_MAX)
        n_mask = int(m.to_numpy().sum())
        mc = mc.mask(m)
    return mc, no_shares, n_mask


out = {}
for mode in ("A", "B", "C"):
    mc, no_shares, n_mask = market_cap(mode)
    cfg = default_small_cap_config(START)
    data = CrossSectionalData(close=close, market_cap=mc)
    res = screen_cross_sectional_universe(
        data, SMALL_CAP_IVOL_FAMILY, cfg, membership_fn=was_member,
        n_trials_override=IVOL_N_TRIALS,
    )
    out[mode] = res
    print(f"--- mode {mode}: {len(res)} specs, no_shares={len(no_shares)}, masked_cells={n_mask}",
          flush=True)
    for r in res:
        print(f"    {r.pattern_id:34s} sharpe={r.sharpe_annualized:+.4f} dsr={r.deflated_sharpe.dsr:.4f} "
              f"vw_legs={r.n_value_weighted_legs} fallbacks={r.n_value_weight_fallbacks}", flush=True)

with (HERE / "replay.pkl").open("wb") as fh:
    pickle.dump(
        {m: [(r.pattern_id, r.sharpe_annualized, r.deflated_sharpe.dsr, r.deflated_sharpe.sigma_sr_annualized,
              r.deflated_sharpe.n_trials, r.n_value_weighted_legs,
              r.n_value_weight_fallbacks) for r in res] for m, res in out.items()},
        fh,
    )
print("saved replay.pkl")
