"""Lookback-vs-data-cleanliness confound diagnostic for the NSI buyback family.

METHOD (stated so it can be checked):
  The build's cleanliness metric is `uninformative_window_rate` = share of
  cells whose two window endpoints are the BIT-IDENTICAL filed count. That
  metric is not comparable across lookbacks by construction: identical
  endpoints require ONE filing to back both ends, i.e. endpoint age >= the
  window's calendar span. SHARES_MAX_STALENESS_DAYS = 400 < 504d window
  (~730 calendar days), so the 504 spec's 0.2% is close to mechanically
  guaranteed, whatever the true filing sparsity.

  The lookback-INVARIANT measure of the same defect is ENDPOINT AGE: for
  each (date, ticker) cell, the calendar age of the (reporting-lagged)
  filing whose count that cell carries forward. That is drawn from the same
  distribution regardless of which lookback reads it, so it can be MATCHED
  across specs.

  Diagnostic: re-run the l126 and l504 specs with an extra gate that refuses
  any name whose EITHER window endpoint is backed by a filing older than
  MAX_AGE days. Both specs then rank only names whose data quality is
  comparable, on the SAME formation dates. If l126's Sharpe converges toward
  l504's, the gap is cleanliness. If it does not, the gap is horizon.
"""
import pickle, sys, time
from datetime import date
from functools import partial

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")

from app.services.research_lab.cross_sectional import (
    CrossSectionalData,
    CrossSectionalSpec,
    run_cross_sectional_backtest,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe
from app.services.research_lab.cross_sectional_buyback import (
    BUYBACK_FAMILY,
    BUYBACK_CITATION,
    BUYBACK_FORMATION_START,
    BUYBACK_RANK_FRACTION,
    SHARES_REPORTING_LAG_DAYS,
    build_point_in_time_share_counts,
    default_buyback_config,
    signal_net_share_issuance,
)

D = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/lens_conf/"
with open(D + "data.pkl", "rb") as fh:
    blob = pickle.load(fh)

close = blob["close"]
shares = blob["shares"]
splits = blob["splits"]
start = BUYBACK_FORMATION_START
t0 = time.time()

shares_frame, unusable = build_point_in_time_share_counts(close, shares, splits)
print(f"panel {shares_frame.shape}, unusable {len(unusable)}  t={time.time()-t0:.0f}s", flush=True)

# ---- AGE FRAME: calendar age of the lagged filing backing each cell -------
idx_vals = shares_frame.index.to_numpy()
age = pd.DataFrame(np.nan, index=shares_frame.index, columns=shares_frame.columns)
for tkr in shares_frame.columns:
    raw = shares.get(tkr)
    col = shares_frame[tkr]
    if raw is None or raw.empty or col.isna().all():
        continue
    usable_raw = raw[np.isfinite(raw) & (raw > 0.0)]
    if usable_raw.empty:
        continue
    visible = (
        pd.DatetimeIndex(pd.DatetimeIndex(usable_raw.index) + pd.Timedelta(days=SHARES_REPORTING_LAG_DAYS))
        .unique().sort_values()
    )
    pos = np.searchsorted(visible.to_numpy(), idx_vals, side="right") - 1
    valid = (pos >= 0) & col.notna().to_numpy()
    a = np.full(len(idx_vals), np.nan)
    a[valid] = (idx_vals[valid] - visible.to_numpy()[pos[valid]]) / np.timedelta64(1, "D")
    age[tkr] = a
print(f"age frame built t={time.time()-t0:.0f}s", flush=True)
age.to_pickle(D + "age.pkl")
shares_frame.to_pickle(D + "panel.pkl")

# ---- DESCRIPTIVE: realized span vs nominal span, per lookback -------------
replay_rows = shares_frame.index.date >= start
print("\n=== ENDPOINT AGE (calendar days), populated cells in the replayed sample ===")
a_replay = age.loc[replay_rows]
flat = a_replay.to_numpy().ravel()
flat = flat[np.isfinite(flat)]
print("  n cells %d  median %.0f  p75 %.0f  p90 %.0f  p95 %.0f  p99 %.0f  max %.0f"
      % (len(flat), *[np.percentile(flat, q) for q in (50, 75, 90, 95, 99, 100)]))
for yr in range(2018, 2027):
    m = np.array([d.year == yr for d in a_replay.index.date])
    f = a_replay.to_numpy()[m].ravel(); f = f[np.isfinite(f)]
    if len(f):
        print(f"    {yr}: median {np.median(f):5.0f}  p90 {np.percentile(f,90):5.0f}  "
              f"share>45d {100*np.mean(f>45):5.1f}%  share>90d {100*np.mean(f>90):5.1f}%")

print("\n=== REALIZED MEASUREMENT SPAN vs NOMINAL, per lookback ===")
for lb in (126, 252, 504):
    nominal_cal = lb * 365.0 / 252.0
    a_last = age
    a_first = age.shift(lb)
    d_last = pd.Series(shares_frame.index, index=shares_frame.index)
    span = (
        (d_last.values.astype("datetime64[D]").astype(float)[:, None] - a_last.to_numpy())
        - (d_last.shift(lb).values.astype("datetime64[D]").astype(float)[:, None] - a_first.to_numpy())
    )
    span = pd.DataFrame(span, index=shares_frame.index, columns=shares_frame.columns)
    both = shares_frame.notna() & shares_frame.shift(lb).notna()
    ident = both & (shares_frame == shares_frame.shift(lb))
    s = span.where(both & ~ident).loc[replay_rows].to_numpy().ravel()
    s = s[np.isfinite(s)]
    rel = s / nominal_cal
    print(f"  l{lb}: nominal {nominal_cal:.0f} cal days | realized median {np.median(s):.0f} "
          f"p10 {np.percentile(s,10):.0f} p90 {np.percentile(s,90):.0f} | "
          f"rel-span median {np.median(rel):.2f} p10 {np.percentile(rel,10):.2f} "
          f"p90 {np.percentile(rel,90):.2f} | share within +/-10% of nominal {100*np.mean(np.abs(rel-1)<=0.10):.1f}%")
    u = both.loc[replay_rows].to_numpy().sum()
    i = ident.loc[replay_rows].to_numpy().sum()
    print(f"        uninformative (identical endpoints) {100*i/u:.2f}%   [reproduces the build's metric]")

# ---- THE GATED SIGNAL -----------------------------------------------------
AGE = age


def signal_age_gated(history, *, lookback_days, max_age, winsorize_quantile=None):
    base = signal_net_share_issuance(
        history, lookback_days=lookback_days, winsorize_quantile=winsorize_quantile
    )
    sh = history.shares_outstanding
    w = sh.iloc[-(lookback_days + 1):]
    if len(w) < lookback_days + 1:
        return base
    cols = list(sh.columns)
    a0 = AGE.loc[w.index[0], cols]
    a1 = AGE.loc[w.index[-1], cols]
    ok = (a0 <= max_age) & (a1 <= max_age)
    ok = ok.reindex(base.index).fillna(False).astype(bool)
    return base.where(ok)


def make_spec(pid, lookback, holding, portfolio, max_age=None):
    fn = (
        partial(signal_net_share_issuance, lookback_days=lookback)
        if max_age is None
        else partial(signal_age_gated, lookback_days=lookback, max_age=max_age)
    )
    return CrossSectionalSpec(
        pattern_id=pid, family="net_share_issuance", citation=BUYBACK_CITATION,
        signal_fn=fn, lookback_days=lookback + 1, holding_days=holding,
        portfolio=portfolio, rank_fraction=BUYBACK_RANK_FRACTION,
        requires_shares_outstanding=True,
    )


data = CrossSectionalData(close=close, shares_outstanding=shares_frame)
config = default_buyback_config()
config.formation_start = start


def run(spec):
    r = run_cross_sectional_backtest(data, spec, config)
    formed = [f for f in r.formations if f.skipped_reason is None]
    legs = float(np.mean([len(f.long_tickers) for f in formed])) if formed else 0.0
    ranked = float(np.mean([f.n_ranked for f in formed])) if formed and hasattr(formed[0], "n_ranked") else float("nan")
    return dict(
        pid=spec.pattern_id, status=r.status, sharpe=sharpe_ratio(r.daily_returns),
        n_form=len(formed), n_skip=len(r.formations) - len(formed), leg=legs,
        ranked=ranked, ret=r.daily_returns,
    )


print("\n=== BASELINE (reproduce the production run) ===", flush=True)
baseline = {}
for spec in BUYBACK_FAMILY:
    out = run(spec)
    baseline[out["pid"]] = out
    print(f"  {out['pid']:26s} sharpe {out['sharpe']:+.3f}  formations {out['n_form']:3d} "
          f"skipped {out['n_skip']:2d}  leg {out['leg']:.1f}", flush=True)

sharpes = {k: v["sharpe"] for k, v in baseline.items()}
sigma_sr = float(np.std(list(sharpes.values()), ddof=1))
print(f"  sigma_sr (ddof=1 across 14) = {sigma_sr:.4f}")
best = baseline["nsi_l504_ls_h126"]
dsr = compute_deflated_sharpe(best["sharpe"], best["ret"], 14, sigma_sr)
print(f"  nsi_l504_ls_h126 DSR = {dsr.dsr:.4f}  SR0 = {dsr.expected_max_sharpe_noise_annualized:.4f} "
      f"n_obs = {dsr.n_observations}  PSR0 = {dsr.psr_vs_zero:.4f}")

print("\n=== MATCHED-CLEANLINESS DIAGNOSTIC ===", flush=True)
rows = []
for max_age in (120, 60, 45, 30):
    for lb in (126, 252, 504):
        for portfolio, tag in (("long_short", "ls"),):
            for hold in (126, 252):
                pid = f"nsi_l{lb}_{tag}_h{hold}_age{max_age}"
                out = run(make_spec(pid, lb, hold, portfolio, max_age=max_age))
                rows.append((max_age, lb, hold, out))
                base_pid = f"nsi_l{lb}_{tag}_h{hold}"
                print(f"  age<={max_age:3d} l{lb:3d} h{hold:3d}: sharpe {out['sharpe']:+.3f} "
                      f"(ungated {baseline[base_pid]['sharpe']:+.3f})  formations {out['n_form']:2d} "
                      f"skipped {out['n_skip']:2d}  leg {out['leg']:.1f}", flush=True)

with open(D + "results.pkl", "wb") as fh:
    pickle.dump({"baseline": {k: {kk: vv for kk, vv in v.items()} for k, v in baseline.items()},
                 "gated": rows, "sigma_sr": sigma_sr}, fh)
print(f"\nDONE t={time.time()-t0:.0f}s", flush=True)
