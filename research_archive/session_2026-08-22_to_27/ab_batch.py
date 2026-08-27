"""A/B: run a battery of cross-sectional backtests on deterministic synthetic
panels and dump every daily return / formation / cost total. Run in both trees;
compare the JSON byte-for-byte."""
import json
import sys

import numpy as np
import pandas as pd

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
    run_cross_sectional_backtest,
)

N_DAYS = 900
TICKERS = [f"T{i:02d}" for i in range(24)]


def make_panel(seed, ragged=True):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", periods=N_DAYS, freq="D")
    rets = rng.normal(0.0004, 0.02, size=(N_DAYS, len(TICKERS)))
    close = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=TICKERS)
    vol = pd.DataFrame(rng.lognormal(15, 1, size=close.shape), index=idx, columns=TICKERS)
    mcap = close * rng.lognormal(18, 0.5, size=(1, len(TICKERS)))
    if ragged:
        # births, deaths and transient holes -- exercises delisting / NaN paths
        close.iloc[:120, 3] = np.nan
        close.iloc[600:, 5] = np.nan          # permanent death mid-sample
        close.iloc[300:340, 7] = np.nan       # transient gap
        close.iloc[:400, 11] = np.nan
        close.iloc[850:, 13] = np.nan
        close.iloc[500, 2] = np.nan           # one-day hole
    basis = 1.0 / close.pct_change(fill_method=None).rolling(60, min_periods=20).std()
    return CrossSectionalData(close=close, open=close * 0.999, volume=vol,
                              market_cap=mcap, leg_weight_basis=basis)


def sig_mom(lb):
    def f(h):
        c = h.close
        return (c.iloc[-1] / c.iloc[0]) - 1.0
    return f


def sig_rev(lb):
    def f(h):
        c = h.close
        return -(c.iloc[-1] / c.iloc[max(0, len(c) - 6)] - 1.0)
    return f


def sig_vol(lb):
    def f(h):
        return -h.close.pct_change(fill_method=None).std()
    return f


SIGS = {"mom": sig_mom, "rev": sig_rev, "vol": sig_vol}

CASES = []
cid = 0
for signame in SIGS:
    for hold in (1, 3, 5, 21, 63, 180):
        for portfolio in ("long_short", "long_universe_hedged"):
            for weighting in ("magnitude", "value", "equal", "inverse_vol"):
                for cohort in (None, ):
                    cid += 1
                    CASES.append((cid, signame, 120, hold, portfolio, weighting, cohort))
# cohort / overlapping-sleeve cases and imputation cases
for hold, cohort in ((63, 21), (180, 60), (21, 7)):
    for signame in SIGS:
        cid += 1
        CASES.append((cid, signame, 120, hold, "long_short", "magnitude", cohort))


def run():
    out = {}
    for ragged in (True, False):
        data = make_panel(7, ragged=ragged)
        member = fixed_universe_membership(TICKERS)
        for (cid, signame, lb, hold, portfolio, weighting, cohort) in CASES:
            for impute in (False, True):
                for fin in (0.0, 400.0):
                    spec = CrossSectionalSpec(
                        pattern_id=f"p{cid}",
                        family="ab",
                        citation="ab",
                        signal_fn=SIGS[signame](lb),
                        lookback_days=lb,
                        holding_days=hold,
                        portfolio=portfolio,
                        rank_fraction=0.25,
                        leg_weighting=weighting,
                        cohort_formation_days=cohort,
                    )
                    cfg = CrossSectionalConfig(
                        cost_bps=30.0,
                        min_names_per_leg=3,
                        impute_delisting_returns=impute,
                        financing_bps_per_year=fin,
                        periods_per_year=365.0,
                    )
                    r = run_cross_sectional_backtest(data, spec, cfg, member)
                    key = f"{int(ragged)}|{cid}|{signame}|{hold}|{portfolio}|{weighting}|{cohort}|{impute}|{fin}"
                    out[key] = {
                        "status": r.status,
                        "n": int(r.daily_returns.shape[0]),
                        "rets": [repr(float(v)) for v in r.daily_returns.values],
                        "dates": [str(d.date()) for d in r.daily_returns.index],
                        "total_cost": repr(float(r.total_cost)),
                        "total_financing_cost": repr(float(r.total_financing_cost)),
                        "formations": [
                            {
                                "date": str(f.date.date()),
                                "n_eligible": f.n_eligible,
                                "long": list(f.long_tickers),
                                "short": list(f.short_tickers),
                                "turnover": repr(float(f.turnover)),
                                "skipped": f.skipped_reason,
                                "lfb": f.long_leg_value_weight_fallback,
                                "sfb": f.short_leg_value_weight_fallback,
                            }
                            for f in r.formations
                        ],
                    }
    return out


if __name__ == "__main__":
    json.dump(run(), open(sys.argv[1], "w"), sort_keys=True)
    print("cases:", len(CASES))
