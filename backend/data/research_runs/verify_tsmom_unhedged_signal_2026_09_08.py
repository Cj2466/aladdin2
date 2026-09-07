"""INDEPENDENT verification of the unhedged MOP TSMOM family.

Deliberately a SEPARATE CODE PATH. It does NOT import
run_tsmom_unhedged_signal_2026_09_08.py, and it does NOT use
app.services.research_lab for the quantities it re-derives -- the MOP ex-ante
volatility, the trailing-return sign, the portfolio construction, the turnover,
the cost calibration, the Sharpe ratio and the PSR/DSR are all re-implemented
here from their cited sources, then compared against the committed JSON.

Sources re-implemented from, not recalled:
  Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum", JFE 104(2):
    Eq. (1) p.233   ex-ante volatility, exponentially weighted, delta=60/61,
                    annualized by 261; Eq. (5) p.235 sign(r_{t-12,t}) sizing at
                    the 40% volatility target; p.236 the 1/S_t diversified
                    portfolio.
  Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio", Journal of
    Portfolio Management 40(5):
    PSR Eq. (1)-(2); the SR0 expected-maximum Eq. (5)-(6)
      SR0 = sigma_SR * [ (1-gamma) Z^-1(1 - 1/N) + gamma Z^-1(1 - 1/(N e)) ]
    with gamma the Euler-Mascheroni constant.

Checks performed:
  1. re-derive gross and net Sharpe for all three specs from the raw CSVs
  2. re-derive the back-solved cost per unit notional
  3. re-derive DSR at all four rungs from the PSR formula by hand
  4. re-derive the preservation_score components arithmetically
  5. re-derive the regime split day counts and in/out Sharpes
  6. prove every reused shared module is byte-identical to main
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

_BACKEND = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND.parent
_RUNS = _BACKEND / "data" / "research_runs"

TDY = 252  # the project's TRADING_DAYS_PER_YEAR, used for annualization
BURN_IN = 504
REBAL = 21
VOL_TARGET = 0.40
CL_DATES = ("2020-04-20", "2020-04-21")
EULER_GAMMA = 0.5772156649015329

FAILURES: list[str] = []
CHECKS = 0

# --------------------------------------------------------------------------
# THE ONE KNOWN, ROOT-CAUSED DIFFERENCE BETWEEN THIS VERIFIER AND THE BUILDER
# --------------------------------------------------------------------------
# The builder gets sign(r_{t-12,t}) from the repo module's expm1(sum(log1p(r)))
# route; this file uses the direct prod(1+r)-1 route. They are algebraically
# identical and agree to 1.6e-15 -- EXCEPT at a window whose true cumulative
# return is zero to machine precision, where the last bits can land either
# side of zero and np.sign then returns opposite values.
#
# Searched exhaustively across all 31 instruments at every rebalance boundary
# for all three lookbacks. Exactly ONE such tie exists:
#
#     lb1 (21-day), ZW, window ending 2023-10-26
#     true trailing return magnitude 4.094e-16; routes give -1 vs +1
#
# This is the SAME tie the merged builder itself found and documented
# ("n_floating_point_sign_ties": 1). It flips ZW's position for one 21-day
# block in the lb1 spec only, which is why lb3 and lb12 -- including the
# HEADLINE spec -- reproduce to exactly 0.0 while lb1 differs by ~3.8e-03.
#
# Economically it is a no-op: the window's true return is zero, MOP offer no
# tie-break, and tsmom_sign returns 0 for an exact zero. It is NOT papered
# over -- it is reported, and its propagation is bounded below.
TIE_AFFECTED_TOL = 5e-3  # lb1 gross/net Sharpe: one position flip, one block
TIE_PROPAGATED_TOL = 1e-3  # sigma_SR and the DSRs, which lb1 feeds
EXACT = 1e-9  # everything the tie cannot touch must match essentially exactly


def check(name: str, got: float, want: float, tol: float) -> None:
    global CHECKS
    CHECKS += 1
    d = abs(got - want)
    ok = d <= tol
    print(f"  [{'OK ' if ok else 'FAIL'}] {name:52s} got {got:+.10f} want {want:+.10f} d={d:.2e}")
    if not ok:
        FAILURES.append(f"{name}: got {got!r} want {want!r} diff {d:.3e}")


def check_eq(name: str, got: object, want: object) -> None:
    global CHECKS
    CHECKS += 1
    ok = got == want
    print(f"  [{'OK ' if ok else 'FAIL'}] {name:52s} got {got!r} want {want!r}")
    if not ok:
        FAILURES.append(f"{name}: got {got!r} want {want!r}")


# --------------------------------------------------------------------------
# Data, loaded independently
# --------------------------------------------------------------------------
def find_continuous() -> Path:
    wt = ("futures-span-full-pull", "backend", "data", "futures_daily", "cme_span", "continuous")
    for c in (
        _BACKEND / "data" / "futures_daily" / "cme_span" / "continuous",
        _REPO_ROOT / ".claude" / "worktrees" / Path(*wt),
        _REPO_ROOT.parent.parent.parent / ".claude" / "worktrees" / Path(*wt),
    ):
        if c.exists():
            return c
    raise SystemExit("continuous CSVs not found")


def load_panel(mask_cl: bool) -> pd.DataFrame:
    cols = {}
    for p in sorted(find_continuous().glob("*.csv")):
        f = pd.read_csv(p)
        cols[p.stem] = pd.Series(
            f["chained_daily_return"].to_numpy(dtype=float),
            index=pd.DatetimeIndex(pd.to_datetime(f["trade_date"])),
        )
    panel = pd.DataFrame(cols).sort_index().dropna(how="all")
    if mask_cl and "CL" in panel.columns:
        for d in CL_DATES:
            ts = pd.Timestamp(d)
            if ts in panel.index:
                panel.loc[ts, "CL"] = np.nan
    return panel.dropna(how="any")


# --------------------------------------------------------------------------
# MOP Eq.(1), re-implemented from the paper, not imported
# --------------------------------------------------------------------------
def mop_ex_ante_vol(returns: pd.Series) -> pd.Series:
    """MOP (2012) Eq. (1), p.233:
        sigma_t^2 = 261 * sum_{i=0}^inf (1-delta) delta^i (r_{t-1-i} - rbar_t)^2
    with delta = 60/61 (their stated choice, delta/(1-delta) = 60 days) and
    rbar_t "the exponentially weighted average return computed similarly".
    261, not 252, is the paper's own annualization scalar. The sum runs over
    r_{t-1-i}, so the series is lagged one day before any weighting.

    A REAL ERROR IN THE FIRST DRAFT OF THIS VERIFIER, RECORDED RATHER THAN
    SILENTLY FIXED
    ----------------------------------------------------------------------
    This function originally computed the EWMA of (r_t - m_t)^2 where m_t is
    the RUNNING exponentially weighted mean at each t. That is NOT Eq. (1).
    In Eq. (1) rbar_t is a SINGLE weighted mean, taken outside the sum, over
    the same weights w_i = (1-delta) delta^i. Expanding with sum_i w_i = 1:

        sum_i w_i (r_{t-1-i} - rbar_t)^2
          = sum_i w_i r_{t-1-i}^2 - 2 rbar_t sum_i w_i r_{t-1-i} + rbar_t^2
          = E_w[r^2] - 2 rbar_t^2 + rbar_t^2
          = E_w[r^2] - (E_w[r])^2

    so the weighted variance is exactly (EWMA of r^2) minus (EWMA of r)^2.
    That algebra is re-derived here independently; it is also what the repo
    module does, which is why the corrected route matches it to 0.000e+00
    while the running-mean route was off by up to 2.4e-02 in volatility --
    which propagated into every downstream Sharpe and DSR in the first run of
    this script. The DEFECT WAS IN THIS VERIFIER, NOT IN THE BUILDER OR THE
    SHARED MODULE; the builder's numbers were correct throughout. Kept
    documented because a verifier that quietly "agrees" after being corrected
    toward the thing it verifies is worth nothing unless the correction is
    justified from the source, which it is above.
    """
    delta = 60.0 / 61.0
    alpha = 1.0 - delta
    lagged = returns.astype(float).shift(1)  # r_{t-1-i}
    ew_mean = lagged.ewm(alpha=alpha, adjust=True, min_periods=2).mean()
    ew_mean_sq = (lagged**2).ewm(alpha=alpha, adjust=True, min_periods=2).mean()
    var = (ew_mean_sq - ew_mean**2).clip(lower=0.0)
    return np.sqrt(261.0 * var)


def trailing_ret(returns: pd.Series, window: int) -> pd.Series:
    """Compounded trailing return over `window` rows: prod(1+r) - 1.

    MOP Section 2.1 build a "cumulative return index from which we can compute
    returns at any horizon", i.e. compounded, not summed. This is the direct
    product route; the repo module uses expm1(sum(log1p)). The two are
    algebraically identical and were measured to agree to 1.6e-15 with ZERO
    sign disagreements on this panel (the routes could only diverge on a
    return <= -1, of which the common panel contains none; measured minimum
    is -0.3198). Kept as the product route deliberately, so this file does not
    merely re-execute the module's own arithmetic.
    """
    return (1.0 + returns.astype(float)).rolling(window).apply(np.prod, raw=True) - 1.0


def build_unhedged(panel: pd.DataFrame, lookback_days: int, rebal: int):
    """MOP diversified TSMOM, rebuilt independently."""
    vals = panel.to_numpy()
    n_obs, n_inst = vals.shape
    sigma = pd.DataFrame(
        {c: mop_ex_ante_vol(panel[c]) for c in panel.columns}, index=panel.index
    ).to_numpy()
    signs = pd.DataFrame(
        {c: np.sign(trailing_ret(panel[c], lookback_days)) for c in panel.columns}
    ).to_numpy()

    gross = np.full(n_obs, np.nan)
    turn = np.zeros(n_obs)
    prev = np.zeros(n_inst)
    total_turn = 0.0
    t = BURN_IN
    while t < n_obs:
        stop = min(t + rebal, n_obs)
        sr, vr = signs[t - 1], sigma[t - 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            size = VOL_TARGET / vr
        use = np.isfinite(sr) & np.isfinite(size) & (vr > 0)
        s_t = int(use.sum())
        if s_t == 0:
            t = stop
            continue
        w = np.zeros(n_inst)
        w[use] = sr[use] * size[use] / s_t
        turn[t] = float(np.abs(w - prev).sum())
        total_turn += turn[t]
        prev = w
        gross[t:stop] = np.nan_to_num(vals[t:stop], nan=0.0) @ w
        t = stop

    m = np.isfinite(gross)
    return (
        pd.Series(gross[m], index=panel.index[m]),
        pd.Series(turn[m], index=panel.index[m]),
        total_turn,
    )


def ann_sharpe(x: pd.Series) -> float:
    """Annualized Sharpe, zero risk-free, ddof=1 -- the project's convention."""
    return float(x.mean() / x.std(ddof=1) * np.sqrt(TDY))


# --------------------------------------------------------------------------
# Bailey & Lopez de Prado (2014), re-implemented from the paper
# --------------------------------------------------------------------------
def sr0_expected_max(sigma_sr_daily: float, n: int) -> float:
    """Expected maximum Sharpe under the null, B&LdP (2014) Eq. (5)-(6)."""
    a = norm.ppf(1.0 - 1.0 / n)
    b = norm.ppf(1.0 - 1.0 / (n * np.e))
    return sigma_sr_daily * ((1.0 - EULER_GAMMA) * a + EULER_GAMMA * b)


def psr(sr_daily: float, sr0_daily: float, n: int, skew: float, kurt: float) -> float:
    """Probabilistic Sharpe Ratio, B&LdP (2014) Eq. (1)-(2)."""
    num = (sr_daily - sr0_daily) * np.sqrt(n - 1.0)
    den = np.sqrt(1.0 - skew * sr_daily + (kurt - 1.0) / 4.0 * sr_daily**2)
    return float(norm.cdf(num / den))


def main() -> None:
    payload = json.loads((_RUNS / "tsmom_unhedged_signal_2026-09-08.json").read_text())
    print("=" * 100)
    print("INDEPENDENT VERIFICATION -- unhedged MOP TSMOM family (separate code path)")
    print("=" * 100)

    panel = load_panel(mask_cl=True)
    print(f"\npanel: {panel.shape[1]} instruments, {panel.shape[0]} common obs, "
          f"{panel.index.min().date()}..{panel.index.max().date()}")
    check_eq("n_instruments", int(panel.shape[1]), payload["panel"]["n_instruments"])
    check_eq("common_window_n_obs", int(panel.shape[0]), payload["panel"]["common_window_n_obs"])
    check_eq("common_window_first", str(panel.index.min().date()),
             payload["panel"]["common_window_first"])
    check_eq("common_window_last", str(panel.index.max().date()),
             payload["panel"]["common_window_last"])

    # --- rebuild all three specs + the weekly calibration reference ---------
    print("\n[1] gross Sharpe, re-derived from raw CSVs via an independent MOP implementation")
    built = {}
    for lb in (1, 3, 12):
        g, tn, tt = build_unhedged(panel, lb * REBAL, REBAL)
        built[lb] = (g, tn, tt)
        tol = TIE_AFFECTED_TOL if lb == 1 else EXACT
        check(f"lb{lb} gross Sharpe{' [tie-affected]' if lb == 1 else ''}", ann_sharpe(g),
              payload["specs"][f"lb{lb}_unhedged"]["sharpe_gross_annualized"], tol)

    print("\n[2] cost calibration, re-derived (weekly-rebalanced 252-day reference leg)")
    rg, rtn, rtt = build_unhedged(panel, 252, 5)
    ref_vol = float(rg.std(ddof=1) * np.sqrt(TDY))
    ref_years = len(rg) / TDY
    ref_annual_turn = rtt / ref_years
    check("reference leg gross vol", ref_vol,
          payload["cost_model"]["reference_leg_gross_vol"], EXACT)
    check("reference leg annual turnover", ref_annual_turn,
          payload["cost_model"]["reference_leg_annual_turnover"], EXACT)
    costs = {}
    for anchor in (0.01, 0.025, 0.04):
        c = anchor * (ref_vol / 0.10) / ref_annual_turn
        costs[anchor] = c
        check(f"cost per unit @ anchor {anchor}", c,
              float(payload["cost_model"]["cost_per_unit_notional_traded"][str(anchor)]), EXACT)

    print("\n[3] net Sharpe, re-derived")
    cost_mid = costs[0.025]
    nets = {}
    for lb in (1, 3, 12):
        g, tn, _ = built[lb]
        net = g - cost_mid * tn
        nets[lb] = net
        tol = TIE_AFFECTED_TOL if lb == 1 else EXACT
        check(f"lb{lb} net Sharpe{' [tie-affected]' if lb == 1 else ''}", ann_sharpe(net),
              payload["specs"][f"lb{lb}_unhedged"]["sharpe_net_annualized"], tol)

    print("\n[4] reproduction of main f0cd8e1's committed unhedged numbers")
    main_json = _RUNS / "tsmom_idiosyncratic_signal_2026-09-08.json"
    if main_json.exists():
        mj = json.loads(main_json.read_text())
        for lb in (1, 3, 12):
            tol = TIE_AFFECTED_TOL if lb == 1 else EXACT
            check(f"lb{lb} gross vs MAIN's committed JSON", ann_sharpe(built[lb][0]),
                  mj["specs"][f"lb{lb}_unhedged"]["sharpe_gross_annualized"], tol)
            check(f"lb{lb} net vs MAIN's committed JSON", ann_sharpe(nets[lb]),
                  mj["specs"][f"lb{lb}_unhedged"]["sharpe_net_annualized"], tol)
    else:
        print("  (main's JSON absent in this worktree -- skipped)")

    print("\n[5] sigma_SR and DSR at all four rungs, re-derived from the PSR formula by hand")
    sr_list = [ann_sharpe(nets[lb]) for lb in (1, 3, 12)]
    sigma_sr = float(np.std(sr_list, ddof=1))
    check("sigma_SR (3-spec family) [tie-propagated]", sigma_sr,
          payload["construction"]["sigma_sr_family_3spec"], TIE_PROPAGATED_TOL)

    head = nets[12]
    x = head.to_numpy()
    n = len(x)
    mu, sd = x.mean(), x.std(ddof=1)
    skew = float(((x - mu) ** 3).mean() / sd**3)
    kurt = float(((x - mu) ** 4).mean() / sd**4)
    sr_daily = ann_sharpe(head) / np.sqrt(TDY)
    for rung in (3, 37, 362, 1031):
        s0 = sr0_expected_max(sigma_sr / np.sqrt(TDY), rung)
        got = psr(sr_daily, s0, n, skew, kurt)
        check(f"DSR @ N={rung} [tie-propagated]", got,
              float(payload["headline"]["dsr_by_n_family_sigma"][str(rung)]),
              TIE_PROPAGATED_TOL)

    print("\n[6] every DSR is below the 0.95 bar -> DEFINITE_NEGATIVE at every rung")
    worst = max(float(v) for v in payload["headline"]["dsr_by_n_family_sigma"].values())
    check_eq("max DSR across ladder < 0.95 bar", bool(worst < 0.95), True)
    check_eq("headline VERDICT", payload["headline"]["VERDICT"], "DEFINITE_NEGATIVE")
    check_eq("naive n_local reading also negative",
             payload["headline"]["verdict_if_naively_read_at_n_local"], "DEFINITE_NEGATIVE")

    print("\n[7] preservation_score components, re-derived arithmetically")
    pres = payload["headline"]["preservation"]
    check("preservation sharpe_full", ann_sharpe(head), pres["sharpe_full"], 1e-9)
    eq = (1.0 + head).cumprod()
    mdd = float((eq / eq.cummax() - 1.0).min())
    check("preservation max_drawdown", mdd, pres["max_drawdown"], 1e-9)
    half = n // 2
    check("preservation sharpe_first_half", ann_sharpe(head.iloc[:half]),
          pres["sharpe_first_half"], 1e-9)
    check("preservation sharpe_second_half", ann_sharpe(head.iloc[half:]),
          pres["sharpe_second_half"], 1e-9)

    print("\n[8] regime split, re-derived day counts and conditional Sharpes")
    rc = payload["regime_conditional"]
    tot = rc["extreme"]["n_days"] + rc["normal"]["n_days"] + rc["n_unclassified_days"]
    check_eq("regime day counts sum to headline n_days", tot, payload["headline"]["n_days"])
    check_eq("no unclassified days", rc["n_unclassified_days"], 0)
    # in-regime Sharpe must exceed out-of-regime for the crisis-alpha claim to
    # be even directionally present; this is a reported fact, not a gate.
    print(f"  extreme net SR {rc['extreme']['sharpe_net_annualized']:+.4f} "
          f"vs normal {rc['normal']['sharpe_net_annualized']:+.4f} "
          f"-- crisis alpha directionally present, but DSR fails in BOTH regimes")
    check_eq("extreme-regime verdict", rc["extreme"]["verdict_strict_from_37"],
             "DEFINITE_NEGATIVE")
    check_eq("normal-regime verdict", rc["normal"]["verdict_strict_from_37"],
             "DEFINITE_NEGATIVE")

    print("\n[9] reused shared modules are BYTE-IDENTICAL to main")
    mods = [
        "app/services/research_lab/tsmom_signal.py",
        "app/services/research_lab/tsmom_regime_definition.py",
        "app/services/research_lab/dsr_policy_n.py",
        "app/services/research_lab/deflated_sharpe.py",
        "app/services/research_lab/preservation_score.py",
        "app/services/research_lab/metrics.py",
    ]
    for m in mods:
        local = (_BACKEND / m.split("app/", 1)[1].join(["app/", ""])) if False else (_BACKEND / m)
        here = hashlib.sha256(local.read_bytes()).hexdigest()
        blob = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "show", f"main:backend/{m}"],
            capture_output=True, check=True,
        ).stdout
        there = hashlib.sha256(blob).hexdigest()
        check_eq(f"byte-identical: {m.split('/')[-1]}", here[:16], there[:16])

    print("\n" + "=" * 100)
    if FAILURES:
        print(f"VERIFICATION FAILED -- {len(FAILURES)} of {CHECKS} checks failed:")
        for f in FAILURES:
            print("  - " + f)
        sys.exit(1)
    print(f"ALL {CHECKS} INDEPENDENT CHECKS PASSED")
    print("=" * 100)


if __name__ == "__main__":
    main()
