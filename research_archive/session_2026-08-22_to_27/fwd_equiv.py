"""Adversarial live-simulation equivalence check.

For each config: replay the BATCH sleeve over the FULL panel starting at row s,
then simulate the forward ticker DAY BY DAY where on day k the ticker is handed
ONLY rows 0..k (exactly what a live tick can see) and the membership/eligibility
gate is RECOMPUTED from that truncated panel each day. If the two series match
bit-for-bit, the tick both (a) reproduces the backtest's arithmetic and (b)
cannot be using any data from after the day it is standing on.
"""
import numpy as np
import pandas as pd

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    _replay_sleeve,
)
from app.services.research_lab.cross_sectional_forward import (
    CrossSectionalForwardState,
    advance_forward_validation,
)

N_DAYS = 700
TICKERS = [f"T{i:02d}" for i in range(20)]


def make_panel(seed):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
    rets = rng.normal(0.0003, 0.03, size=(N_DAYS, len(TICKERS)))
    close = pd.DataFrame(50 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=TICKERS)
    close.iloc[:80, 2] = np.nan
    close.iloc[450:, 4] = np.nan       # dies mid-sample
    close.iloc[300:315, 6] = np.nan    # transient hole
    close.iloc[600, 9] = np.nan
    vol = pd.DataFrame(rng.lognormal(14, 1.2, size=close.shape), index=idx, columns=TICKERS)
    return close, vol


def slice_data(close, vol, upto):
    c = close.iloc[: upto + 1]
    v = vol.iloc[: upto + 1]
    basis = 1.0 / c.pct_change(fill_method=None).rolling(90, min_periods=30).std()
    return CrossSectionalData(close=c, volume=v, leg_weight_basis=basis)


def liquidity_membership(close, vol):
    """Same SHAPE as the crypto gate: trailing rolling stats, .shift(1)ed."""
    dv = (close * vol).rolling(90, min_periods=30).median().shift(1)
    stale = (close.pct_change(fill_method=None) == 0.0).rolling(90, min_periods=30).mean().shift(1)
    ok = (dv >= 1e6) & (stale <= 0.5)
    by_date = {d.date(): set(ok.columns[ok.loc[d].fillna(False).values]) for d in ok.index}

    def is_member(t, on):
        return t in by_date.get(on, set())

    return is_member


def sig(h):
    c = h.close
    return (c.iloc[-1] / c.iloc[0]) - 1.0


def main():
    close, vol = make_panel(11)
    full = slice_data(close, vol, len(close) - 1)
    n = len(close)
    problems = []
    checked = 0
    for hold in (1, 2, 5, 21, 60, 180):
        for portfolio in ("long_short", "long_universe_hedged"):
            for weighting in ("magnitude", "equal", "inverse_vol"):
                for fin in (0.0, 400.0):
                    spec = CrossSectionalSpec(
                        pattern_id="f", family="f", citation="f", signal_fn=sig,
                        lookback_days=180, holding_days=hold, portfolio=portfolio,
                        rank_fraction=0.25, leg_weighting=weighting,
                    )
                    cfg = CrossSectionalConfig(
                        cost_bps=30.0, min_names_per_leg=3,
                        financing_bps_per_year=fin, periods_per_year=365.0,
                    )
                    s = 300  # first formation row
                    # --- BATCH reference: full panel, full-panel membership -----
                    member_full = liquidity_membership(close, vol)
                    daily_all = close.pct_change(fill_method=None)
                    _f, by_date, _ = _replay_sleeve(full, spec, cfg, member_full, daily_all, {}, s)
                    batch = {d.date(): v[0] for d, v in by_date.items()}

                    # --- LIVE simulation: day k sees only rows 0..k -------------
                    state = CrossSectionalForwardState()
                    last = None
                    fwd = {}
                    for k in range(s, n):
                        d_k = slice_data(close, vol, k)
                        member_k = liquidity_membership(close.iloc[: k + 1], vol.iloc[: k + 1])
                        state, results = advance_forward_validation(
                            d_k, spec, cfg, member_k, state, last
                        )
                        assert len(results) == 1, (k, len(results))
                        r = results[0]
                        assert r.date == close.index[k]
                        last = r.date.date()
                        if r.realized:
                            fwd[last] = r.net_return
                    checked += 1
                    tag = f"hold={hold} {portfolio} {weighting} fin={fin}"
                    if set(batch) != set(fwd):
                        problems.append(f"{tag}: DATE SET differs "
                                        f"batch={len(batch)} fwd={len(fwd)} "
                                        f"missing={sorted(set(batch) - set(fwd))[:3]} "
                                        f"extra={sorted(set(fwd) - set(batch))[:3]}")
                        continue
                    bad = [d for d in batch if batch[d] != fwd[d]]
                    if bad:
                        d0 = sorted(bad)[0]
                        problems.append(f"{tag}: {len(bad)}/{len(batch)} days differ; "
                                        f"first {d0} batch={batch[d0]!r} fwd={fwd[d0]!r}")
                    # equity must equal compounded net returns, no gap/double count
                    eq = 1.0
                    for d in sorted(fwd):
                        eq *= 1.0 + fwd[d]
                    if abs(eq - state.equity) > 1e-12 * max(1.0, abs(eq)):
                        problems.append(f"{tag}: equity {state.equity!r} != compounded {eq!r}")
    print("configs checked:", checked)
    print("PROBLEMS:", len(problems))
    for p in problems:
        print("  -", p)


if __name__ == "__main__":
    main()
