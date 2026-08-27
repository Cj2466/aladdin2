"""The REAL production entry point, with the fix wired, driven over the REAL
saved production fetch. This exercises run_small_cap_ivol_screening itself
(mask_recycled_ticker_prices, both cross-endpoint checks, the band, the
screening call) rather than a hand-assembled replay of its steps.
"""
import pickle
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

import app.services.research_lab.cross_sectional_small_mid_cap as module  # noqa: E402
from app.services.research_lab.cross_sectional_small_mid_cap import (  # noqa: E402
    run_small_cap_ivol_screening,
)

HERE = Path(__file__).parent
with (HERE / "sc600_fetch.pkl").open("rb") as fh:
    D = pickle.load(fh)


class SavedFetchProvider:
    """Serves the exact frames the real 2026-08-27 fetch returned."""

    def get_price_history(self, tickers, start, end):
        return D["close_raw"], D["missing_price"]

    def get_market_cap_basis(self, tickers, start, end):
        cols = [t for t in tickers if t in D["mcap_close"].columns]
        return D["mcap_close"][cols], D["splits"], []

    def get_shares_outstanding(self, tickers, start, end):
        got = {t: D["shares"][t] for t in tickers if t in D["shares"]}
        return got, [t for t in tickers if t not in D["shares"]]


(results, missing_price, recycled, truncated, no_shares, n_lifecycle, n_implausible) = (
    run_small_cap_ivol_screening(date(2020, 1, 1), date(2026, 8, 27), provider=SavedFetchProvider())
)

print(f"missing_price       : {len(missing_price)}")
print(f"recycled dropped    : {len(recycled)}")
print(f"truncated           : {len(truncated)}")
print(f"no share history    : {len(no_shares)} -> {no_shares}")
print(f"lifecycle refusals  : {n_lifecycle} share-count observations")
print(f"implausible cells   : {n_implausible}")
print(f"legs {sum(r.n_value_weighted_legs for r in results)}  "
      f"fallbacks {sum(r.n_value_weight_fallbacks for r in results)}")
print()
print(f"{'spec':34s} {'sharpe':>9s} {'DSR':>8s} {'sigma_sr':>9s} {'n_trials':>8s} {'cost%':>7s}")
for r in results:
    d = r.deflated_sharpe
    print(f"{r.pattern_id:34s} {r.sharpe_annualized:+9.4f} {d.dsr:8.4f} "
          f"{d.sigma_sr_annualized:9.4f} {d.n_trials:8d} {100*r.total_cost_drag:7.3f}")

with (HERE / "prod_rerun.pkl").open("wb") as fh:
    pickle.dump(
        {
            "rows": [(r.pattern_id, r.sharpe_annualized, r.deflated_sharpe.dsr,
                      r.deflated_sharpe.sigma_sr_annualized, r.n_value_weighted_legs,
                      r.n_value_weight_fallbacks) for r in results],
            "n_lifecycle": n_lifecycle,
            "n_implausible": n_implausible,
            "no_shares": no_shares,
            "recycled": recycled,
        },
        fh,
    )
print("\nsaved prod_rerun.pkl")
