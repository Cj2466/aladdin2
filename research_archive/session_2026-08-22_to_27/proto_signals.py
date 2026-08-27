"""Prototype the three bond mechanisms on real data, to validate the math
and the leg composition BEFORE writing the production module."""
from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

LADDER = ["SHY", "IEI", "IEF", "TLH", "TLT"]
CREDIT = ["TIP", "LQD", "HYG"]
ALL = LADDER + CREDIT

raw = yf.download(ALL, start=date(2007, 1, 1), end=date(2026, 8, 27),
                  auto_adjust=False, progress=False)
adj = yf.download(ALL, start=date(2007, 1, 1), end=date(2026, 8, 27),
                  auto_adjust=True, progress=False)
tr = adj["Close"][ALL].dropna(how="any")
px = raw["Close"][ALL].reindex(tr.index)

print("common window:", tr.index[0].date(), "->", tr.index[-1].date(), len(tr), "rows")


def empirical_duration_beta(tr_window: pd.DataFrame) -> pd.Series:
    """beta of each ETF's daily total return on the equal-weighted Treasury
    ladder 'level' factor. Duration RATIOS are what every mechanism needs,
    and beta_i/beta_j is exactly that, so no external duration constant is
    needed anywhere."""
    r = tr_window.pct_change().dropna(how="all")
    ladder_cols = [c for c in LADDER if c in r.columns]
    f = r[ladder_cols].mean(axis=1)
    var_f = f.var(ddof=1)
    return r.apply(lambda col: col.cov(f) / var_f)


def income_yield(tr_w: pd.DataFrame, px_w: pd.DataFrame, L: int) -> pd.Series:
    """Annualized trailing distribution yield: the wedge between the
    dividend-adjusted (total return) series and the split-only-adjusted
    (price return) series over the window."""
    tr_growth = tr_w.iloc[-1] / tr_w.iloc[0]
    px_growth = px_w.iloc[-1] / px_w.iloc[0]
    income_growth = tr_growth / px_growth
    return income_growth ** (252.0 / L) - 1.0


# --- spot check the pieces at a few historical dates ----------------------
for asof in ["2010-06-30", "2015-06-30", "2019-06-28", "2022-06-30", "2023-10-31", "2026-08-26"]:
    ts = tr.index[tr.index <= asof][-1]
    i = tr.index.get_loc(ts)
    L = 252
    w_tr = tr.iloc[i - L + 1: i + 1]
    w_px = px.iloc[i - L + 1: i + 1]
    b = empirical_duration_beta(w_tr)
    y = income_yield(w_tr, w_px, L)
    print(f"\n=== {ts.date()} ===")
    print("  beta (empirical duration, ladder-relative):")
    print("   ", {t: round(float(b[t]), 2) for t in ALL})
    print("  trailing 252d annualized distribution yield:")
    print("   ", {t: f"{float(y[t]):.2%}" for t in ALL})
    # M1: carry per unit duration over the ladder only
    y_front = y["SHY"]
    m1 = pd.Series({t: (y[t] - y_front) / b[t] for t in LADDER})
    print("  M1 carry-per-duration (ladder only):", {t: round(float(m1[t]), 4) for t in LADDER})

print()
print("=" * 78)
print("M1 sanity: does the signal actually ROTATE, or is it a static long-TLT bet?")
print("=" * 78)
picks = {}
for i in range(252, len(tr), 126):
    L = 252
    w_tr = tr.iloc[i - L + 1: i + 1]
    w_px = px.iloc[i - L + 1: i + 1]
    b = empirical_duration_beta(w_tr)
    y = income_yield(w_tr, w_px, L)
    m1 = pd.Series({t: (y[t] - y["SHY"]) / b[t] for t in LADDER}).sort_values(ascending=False)
    top2 = tuple(sorted(m1.index[:2]))
    picks[top2] = picks.get(top2, 0) + 1
print("  long-leg (top-2) composition frequency across formations:")
for k, v in sorted(picks.items(), key=lambda kv: -kv[1]):
    print(f"    {k}: {v}")

print()
print("=" * 78)
print("M2 butterfly: residual of cumulative return on duration-beta (ladder)")
print("=" * 78)
picks2 = {}
for i in range(252, len(tr), 126):
    L = 252
    w = tr.iloc[i - L + 1: i + 1]
    b = empirical_duration_beta(w)[LADDER]
    c = w[LADDER].iloc[-1] / w[LADDER].iloc[0] - 1.0
    A = np.column_stack([np.ones(len(LADDER)), b.to_numpy()])
    coef, *_ = np.linalg.lstsq(A, c.to_numpy(), rcond=None)
    resid = c.to_numpy() - A @ coef
    s = pd.Series(-resid, index=LADDER).sort_values(ascending=False)
    top2 = tuple(sorted(s.index[:2]))
    picks2[top2] = picks2.get(top2, 0) + 1
    if i == 252:
        print("  OLS orthogonality check at first formation:")
        print(f"    sum(resid)      = {resid.sum():.3e}  (must be ~0)")
        print(f"    sum(beta*resid) = {float((b.to_numpy()*resid).sum()):.3e}  (must be ~0)")
print("  long-leg (top-2) composition frequency:")
for k, v in sorted(picks2.items(), key=lambda kv: -kv[1]):
    print(f"    {k}: {v}")

print()
print("=" * 78)
print("M3 duration-hedged credit excess: where do the 8 names actually rank?")
print("=" * 78)
picks3, short3 = {}, {}
for i in range(252, len(tr), 126):
    L = 252
    w = tr.iloc[i - L + 1: i + 1]
    r = w.pct_change().dropna(how="all")
    f = r[LADDER].mean(axis=1)
    var_f = f.var(ddof=1)
    b = r.apply(lambda col: col.cov(f) / var_f)
    hedged = (r - np.outer(f, b)).sum()   # cumulative duration-hedged excess
    s = (-hedged).sort_values(ascending=False)
    picks3[tuple(sorted(s.index[:2]))] = picks3.get(tuple(sorted(s.index[:2])), 0) + 1
    short3[tuple(sorted(s.index[-2:]))] = short3.get(tuple(sorted(s.index[-2:])), 0) + 1
print("  long-leg (top-2, most spread-widened) frequency:")
for k, v in sorted(picks3.items(), key=lambda kv: -kv[1])[:8]:
    print(f"    {k}: {v}")
print("  short-leg (bottom-2, richest) frequency:")
for k, v in sorted(short3.items(), key=lambda kv: -kv[1])[:8]:
    print(f"    {k}: {v}")
