"""INDEPENDENT verification of the Inelastic-Markets family (candidate #16).

THE POINT OF THIS FILE IS THAT IT DOES NOT IMPORT inelastic_markets_timing.
Every number it checks is re-derived here from the raw committed CSVs with a
separately-written implementation. If this file imported the family module it
would only prove the module is self-consistent, which is not verification.

It re-derives, from scratch:
  V1  the 16-sector partition against Z.1's own "All sectors" total (gate G1)
  V2  the GIV instrument Z_t, via an INDEPENDENT implementation of [GK21]
      Appendix B.2 steps 1-4 (inverse-variance capped weights; the eq. (67)
      WLS panel regression written here with explicit dummy construction;
      eq. (68) size-weighting)
  V3  the multiplier M of eq. (69) (gate G2)
  V4  one spec's overlay return stream and Sharpe, end to end, including the
      two-quarter availability lag
  V5  the permanence result: contemporaneous vs future-horizon regressions
  V6  the no-look-ahead property, tested behaviourally -- corrupting FUTURE
      Z.1 data must not change any past position

Run:  python3 data/research_runs/verify_inelastic_markets.py
Exit code 0 = every check passed.
"""

from __future__ import annotations

import csv
import gzip
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
DATA = BACKEND / "data"
Z1 = DATA / "z1_financial_accounts" / "z1_corporate_equities_holdings.csv.gz"
GDP_CSV = DATA / "z1_financial_accounts" / "real_gdp_bea_nipa_t10106_a191rx.csv"

HOLDERS = [
    "LM153064105.Q", "LM263064105.Q", "LM103064103.Q", "LM213064103.Q",
    "LM223064145.Q", "LM313064105.Q", "LM343064105.Q", "LM513064105.Q",
    "LM543064105.Q", "LM553064103.Q", "LM563064100.Q", "LM573064105.Q",
    "LM623064103.Q", "LM653064100.Q", "LM663064105.Q", "LM703064105.Q",
]
TOTAL = "LM893064105.Q"
CORPORATE = "LM103064103.Q"
START = pd.Period("1993Q1", "Q")

failures: list[str] = []
notes: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")
    if not ok:
        failures.append(f"{name}: {detail}")


# --------------------------------------------------------------------------
# load raw, independently
# --------------------------------------------------------------------------
with gzip.open(Z1, "rt") as fh:
    raw = list(csv.DictReader(fh))
frame = pd.DataFrame(raw)
frame["value"] = frame["value"].astype(float)
frame["q"] = pd.PeriodIndex(pd.to_datetime(frame["period"]), freq="Q")
wide = frame.pivot_table(index="q", columns="series_name", values="value").sort_index()

gdp_raw = pd.read_csv(GDP_CSV)
gdp_idx = pd.PeriodIndex(gdp_raw["period"].str.replace("-Q", "Q", regex=False), freq="Q")
gdp_level = pd.Series(gdp_raw["real_gdp_chained_millions"].astype(float).to_numpy(), index=gdp_idx)
gdp_growth = np.log(gdp_level).diff().dropna()

# --------------------------------------------------------------------------
# V1 -- partition integrity, gate G1
# --------------------------------------------------------------------------
sub = wide.loc[pd.Period("1997Q1", "Q") : pd.Period("2026Q1", "Q")]
summed = sub[HOLDERS].sum(axis=1)
rel = ((summed - sub[TOTAL]) / sub[TOTAL]).abs().dropna()
check(
    "V1 sector partition reconstructs Z.1's own total",
    float(rel.median()) <= 0.02,
    f"median |rel discrepancy| = {rel.median():.6f}, max = {rel.max():.6f} (threshold 0.02)",
)

# --------------------------------------------------------------------------
# V2 -- rebuild the GIV independently
# --------------------------------------------------------------------------
# sector admission: strictly positive from START-1 onward
window = wide.loc[START - 1 :, HOLDERS]
admitted = [c for c in HOLDERS if bool((window[c] > 0).all())]
check(
    "V2a sector admission reproduces 12 sectors",
    len(admitted) == 12,
    f"{len(admitted)} admitted; excluded {[c for c in HOLDERS if c not in admitted]}",
)

hold = wide.loc[START - 1 :, admitted].astype(float)
dq_all = hold.pct_change().loc[START:]
lag = hold.shift(1)
shares_all = lag.div(lag.sum(axis=1), axis=0).loc[START:]
dq_all = dq_all.dropna(how="any")
shares_all = shares_all.loc[dq_all.index]
check(
    "V2b dq panel is finite and 133 x 12",
    dq_all.shape == (133, 12) and np.isfinite(dq_all.to_numpy()).all(),
    f"shape {dq_all.shape}, all finite {np.isfinite(dq_all.to_numpy()).all()}",
)

instrument_cols = [c for c in admitted if c != CORPORATE]
check(
    "V2c corporate sector excluded from instrument (B.2 step 1)",
    len(instrument_cols) == 11 and CORPORATE not in instrument_cols,
    f"{len(instrument_cols)} instrument sectors",
)


def independent_pseudo_equal(panel: pd.DataFrame) -> pd.Series:
    """B.2 step 1, written independently: inverse-variance, capped at 1.5/N."""
    sig = panel.std(ddof=1)
    w0 = (1.0 / sig**2)
    w0 = w0 / w0.sum()
    n = len(w0)
    cap = 1.5 / n
    if w0.max() <= cap:
        return w0
    # solve for xi by bisection so the capped weights sum to 1
    lo, hi = 1.0, 1e9
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if np.minimum(mid * w0, cap).sum() < 1.0:
            lo = mid
        else:
            hi = mid
    out = np.minimum(hi * w0, cap)
    return out / out.sum()


def independent_panel_resid(panel: pd.DataFrame, y: pd.Series, wts: pd.Series) -> pd.DataFrame:
    """eq. (67), written independently: sector FE + time FE + sector-specific
    GDP loading + sector-specific trend, WLS with weights `wts`."""
    secs, pers = list(panel.columns), list(panel.index)
    n, t = len(secs), len(pers)
    yy = y.reindex(pers).to_numpy()
    tr = np.arange(t, dtype=float)
    X, Y, W = [], [], []
    for si, sc in enumerate(secs):
        for ti in range(t):
            sd = np.zeros(n); sd[si] = 1.0
            td = np.zeros(t - 1)
            if ti > 0:
                td[ti - 1] = 1.0
            sg = np.zeros(n); sg[si] = yy[ti]
            st = np.zeros(n); st[si] = tr[ti]
            X.append(np.concatenate([sd, td, sg, st]))
            Y.append(panel.iat[ti, si])
            W.append(wts[sc])
    X = np.asarray(X); Y = np.asarray(Y); sw = np.sqrt(np.asarray(W))
    b, *_ = np.linalg.lstsq(X * sw[:, None], Y * sw, rcond=None)
    r = Y - X @ b
    return pd.DataFrame(r.reshape(n, t).T, index=pers, columns=secs)


panel = dq_all[instrument_cols]
wts = independent_pseudo_equal(panel)
check(
    "V2d pseudo-equal weights sum to 1 and respect the 1.5/N cap",
    abs(float(wts.sum()) - 1.0) < 1e-9 and float(wts.max()) <= 1.5 / len(wts) + 1e-12,
    f"sum={wts.sum():.10f} max={wts.max():.6f} cap={1.5/len(wts):.6f}",
)

dq_check = independent_panel_resid(panel, gdp_growth, wts)
s_inst = shares_all[instrument_cols]
s_inst = s_inst.div(s_inst.sum(axis=1), axis=0)
Z_ind = (dq_check * s_inst).sum(axis=1)

# compare against the committed run's own reported numbers by recomputing the
# multiplier below; also assert the residuals are weighted-mean-zero per quarter
wmean = (dq_check * wts).sum(axis=1)
check(
    "V2e eq.(67) time fixed effect makes residuals weighted-mean-zero each quarter",
    float(wmean.abs().max()) < 1e-8,
    f"max |weighted cross-sectional mean| = {wmean.abs().max():.3e}",
)

# --------------------------------------------------------------------------
# V3 -- the multiplier, gate G2
# --------------------------------------------------------------------------
# The price store is shared committed DATA, not family logic, so loading it here
# does not compromise independence -- every transformation below is re-written.
sys.path.insert(0, str(BACKEND))
from datetime import date

from app.services.market_data.yfinance_provider import YFinanceProvider

close, missing = YFinanceProvider().get_price_history(["^GSPC"], date(1990, 1, 1), date.today())
gspc = close["^GSPC"].astype(float).dropna()
mkt_log = np.log(gspc.groupby(gspc.index.to_period("Q")).last()).diff().dropna()


def ols_with_se(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    D = np.column_stack([np.ones(len(X)), X])
    b, *_ = np.linalg.lstsq(D, y, rcond=None)
    r = y - D @ b
    dof = len(y) - D.shape[1]
    cov = (r @ r) / dof * np.linalg.inv(D.T @ D)
    return b, np.sqrt(np.diag(cov))


def independent_pcs(resid: pd.DataFrame, wts: pd.Series, k: int) -> pd.DataFrame:
    """B.2 step 3: PCs of E~^{1/2} dq_check."""
    M = resid.mul(np.sqrt(wts.reindex(resid.columns)), axis=1).to_numpy()
    M = M - M.mean(axis=0, keepdims=True)
    _, _, vt = np.linalg.svd(M, full_matrices=False)
    kk = min(k, vt.shape[0])
    return pd.DataFrame(M @ vt[:kk].T, index=resid.index, columns=[f"pc{i+1}" for i in range(kk)])


mult = {}
for k in (1, 2):
    pcs = independent_pcs(dq_check, wts, k)
    f = pd.concat(
        [Z_ind.rename("z"), mkt_log.rename("dp"), gdp_growth.rename("gdp"), pcs], axis=1
    ).dropna()
    idx = pd.PeriodIndex(f.index, freq="Q")
    f = f[(idx >= pd.Period("1993Q1", "Q")) & (idx <= pd.Period("2018Q4", "Q"))]
    b, se = ols_with_se(f["dp"].to_numpy(), f[["z", "gdp"] + list(pcs.columns)].to_numpy())
    mult[k] = {"M": float(b[1]), "se": float(se[1]), "n": len(f)}

check(
    "V3a multiplier regression uses exactly 104 quarters ([GK21] Table 2's own n)",
    all(v["n"] == 104 for v in mult.values()),
    f"n = {[v['n'] for v in mult.values()]}",
)
check(
    "V3b independently re-derived M matches the committed run (2.526 / 2.754) to 0.02",
    abs(mult[1]["M"] - 2.526) < 0.02 and abs(mult[2]["M"] - 2.754) < 0.02,
    f"M(1pc) = {mult[1]['M']:.4f} (se {mult[1]['se']:.3f}), "
    f"M(2pc) = {mult[2]['M']:.4f} (se {mult[2]['se']:.3f})",
)
check(
    "V3c gate G2 genuinely FAILS -- neither M is inside the paper's [3.5, 8.0]",
    not (3.5 <= mult[1]["M"] <= 8.0) and not (3.5 <= mult[2]["M"] <= 8.0),
    f"M = {mult[1]['M']:.3f} / {mult[2]['M']:.3f} vs paper 7.08 / 5.28",
)

# --------------------------------------------------------------------------
# V4 -- one spec's overlay stream, end to end
# --------------------------------------------------------------------------
from app.services.research_lab.margin_credit_timing import (
    load_monthly_risk_free,
    load_monthly_spy_returns,
)

spy = load_monthly_spy_returns()
rf = load_monthly_risk_free()
spy.index = pd.PeriodIndex(pd.to_datetime(spy.index), freq="M")
rf.index = pd.PeriodIndex(pd.to_datetime(rf.index), freq="M")
common = spy.index.intersection(rf.index)
ex_m = spy.loc[common] - rf.loc[common]
g = ex_m.groupby(ex_m.index.asfreq("Q"))
mkt_ex = g.apply(lambda s: float(np.prod(1.0 + s.to_numpy()) - 1.0))[g.size() == 3]
mkt_ex.index = pd.PeriodIndex(mkt_ex.index, freq="Q")
mkt_ex = mkt_ex.sort_index()

# recursive Z, independently: refit weights + eq.(67) each quarter
rec = {}
for pos in range(20, len(dq_all.index)):
    upto = dq_all.index[: pos + 1]
    p_ = dq_all.loc[upto, instrument_cols]
    w_ = independent_pseudo_equal(p_)
    r_ = independent_panel_resid(p_, gdp_growth, w_)
    s_ = shares_all.loc[upto, instrument_cols]
    s_ = s_.div(s_.sum(axis=1), axis=0)
    rec[dq_all.index[pos]] = float((r_ * s_).sum(axis=1).iloc[-1])
Zrec = pd.Series(rec).sort_index()

# spec pcs1_rolling40_binary_1q, the registered best
mean = Zrec.rolling(40, min_periods=20).mean()
std = Zrec.rolling(40, min_periods=20).std(ddof=1)
z = (Zrec - mean) / std.replace(0.0, np.nan)
w = (z > 0).astype(float).where(z.notna())
w = w.shift(2)  # the two-quarter availability lag
fr = pd.concat([w.rename("w"), mkt_ex.rename("r")], axis=1).dropna()
turn = fr["w"].diff().abs().fillna(fr["w"].iloc[0])
overlay = (fr["w"] - 1.0) * fr["r"] - turn * (2.0 / 1e4)
sr = float(overlay.mean() / overlay.std(ddof=1) * np.sqrt(4.0))
check(
    "V4 independently re-derived overlay Sharpe for pcs1_rolling40_binary_1q "
    "matches the committed -0.0759",
    abs(sr - (-0.0759)) < 0.01,
    f"re-derived {sr:.4f} over {len(overlay)} quarters "
    f"({overlay.index[0]}..{overlay.index[-1]})",
)
check(
    "V4b the overlay Sharpe is negative, i.e. the timer LOSES to buy-and-hold",
    sr < 0,
    f"overlay Sharpe {sr:.4f}",
)

# --------------------------------------------------------------------------
# V5 -- permanence: contemporaneous vs future horizons
# --------------------------------------------------------------------------
tstats = {}
for h in range(5):
    f = pd.concat([Z_ind.rename("z"), mkt_ex.shift(-h).rename("r")], axis=1).dropna()
    b, se = ols_with_se(f["r"].to_numpy(), f[["z"]].to_numpy())
    tstats[h] = float(b[1] / se[1])
check(
    "V5a the contemporaneous relationship is strong (|t| > 8) -- the signal is REAL",
    abs(tstats[0]) > 8.0,
    f"h=0 t-stat = {tstats[0]:.2f}",
)
check(
    "V5b NO future horizon is significant (|t| < 2 for h=1..4) -- no forecasting content",
    all(abs(tstats[h]) < 2.0 for h in (1, 2, 3, 4)),
    "t-stats h=1..4: " + ", ".join(f"{tstats[h]:.2f}" for h in (1, 2, 3, 4)),
)
notes.append(
    "V5 is the substantive finding: the GIV explains contemporaneous quarterly "
    f"market returns with t={tstats[0]:.1f} and predicts future ones with "
    f"|t|<={max(abs(tstats[h]) for h in (1,2,3,4)):.2f}. The trading null is [GK21] "
    "being right, not a broken construction."
)

# --------------------------------------------------------------------------
# V6 -- no-look-ahead, tested behaviourally
# --------------------------------------------------------------------------
cut = dq_all.index[80]
corrupted = dq_all.copy()
corrupted.loc[corrupted.index > cut] *= -3.0  # violently corrupt the FUTURE only
rec_c = {}
for pos in range(20, 81):
    upto = corrupted.index[: pos + 1]
    p_ = corrupted.loc[upto, instrument_cols]
    w_ = independent_pseudo_equal(p_)
    r_ = independent_panel_resid(p_, gdp_growth, w_)
    s_ = shares_all.loc[upto, instrument_cols]
    s_ = s_.div(s_.sum(axis=1), axis=0)
    rec_c[corrupted.index[pos]] = float((r_ * s_).sum(axis=1).iloc[-1])
Zc = pd.Series(rec_c).sort_index()
overlap = Zrec.index.intersection(Zc.index)
delta = float((Zrec.loc[overlap] - Zc.loc[overlap]).abs().max())
check(
    "V6 corrupting FUTURE Z.1 data leaves every past recursive Z unchanged",
    delta < 1e-12,
    f"max |change| in past Z after corrupting all data after {cut} = {delta:.3e}",
)

# --------------------------------------------------------------------------
print()
for n in notes:
    print("NOTE: " + n)
print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for f_ in failures:
        print("  - " + f_)
    sys.exit(1)
print("ALL INDEPENDENT VERIFICATION CHECKS PASSED")

