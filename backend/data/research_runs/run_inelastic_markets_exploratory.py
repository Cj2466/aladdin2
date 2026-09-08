"""EXPLORATORY arms for the Inelastic-Markets family. NOT REGISTERED RESULTS.

Everything in this file was run AFTER the registered verdict was known and is
reported as exploratory only, never as a verdict. It exists because the
pre-registration (sections 6 and 10) requires three specific things to be
computed and disclosed rather than left unexamined:

  A. THE REVERSAL SIGN. The pre-registration fixed the POSITIVE (continuation)
     direction and put the negative direction out of the registered grid. The
     registered arm produced uniformly NEGATIVE overlay Sharpes, which means the
     opposite sign would have produced positive ones. That has to be shown and
     quantified rather than quietly omitted -- and then explained, because a
     post-hoc sign flip is exactly what pre-registration exists to prevent. The
     honest question it answers is: even GIVEN a searched sign, does the best
     arm clear the bar?

  B. FOOTNOTE 70's ALTERNATIVE INSTRUMENT. Under eq. (68) the n_pcs grid
     dimension is DEGENERATE -- Z is built from the eq. (67) residuals and the
     principal components never touch it, so pcs1 and pcs2 are byte-identical.
     [GK21] footnote 70 offers the alternative: "An equivalent way to proceed is
     to use z_t = sum_i S_{i,t-1} u_check_it, where u_check_it is the measure of
     idiosyncratic shock ... As we control for eta^{PC,e} below, the two
     procedures are similar." Under that construction n_pcs DOES bite, so it is
     run to check the null is not an artefact of the eq. (68) choice.

  C. THE PAPER'S OWN PERMANENCE CLAIM, tested directly on this project's data:
     regressing FUTURE quarterly returns on Z_t at horizons h = 1..4. [GK21]
     predicts these coefficients are ~0. This is the cleanest test of whether
     the null is the paper being right rather than the signal being broken.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe  # noqa: E402
from app.services.research_lab.inelastic_markets_timing import (  # noqa: E402
    INELASTIC_COST_BPS,
    INELASTIC_N_TRIALS,
    QUARTERS_PER_YEAR,
    AVAILABILITY_LAG_QUARTERS,
    _ols,
    apply_holding,
    build_dq_panel,
    build_giv,
    dsr_across_denominators,
    extract_pcs,
    giv_instrument,
    instrument_sectors,
    load_real_gdp_growth,
    load_z1_holdings,
    panel_residuals,
    policy_d_denominators,
    position_from_zscore,
    pseudo_equal_weights,
    quarterly_market_excess,
    recursive_giv,
    select_giv_sectors,
    spec_grid,
    standardize,
    verdict_from_dsr,
)
from app.services.research_lab.metrics import sharpe_ratio  # noqa: E402

OUT = Path(__file__).resolve().parent


def replay_signed(z, market_excess, std, rule, hold, cost_bps, sign):
    zs = standardize(z, std)
    w = position_from_zscore(sign * zs, rule)
    w = apply_holding(w, hold)
    w = w.shift(AVAILABILITY_LAG_QUARTERS)
    frame = pd.concat([w.rename("w"), market_excess.rename("r")], axis=1).dropna()
    if frame.empty:
        return None
    turnover = frame["w"].diff().abs().fillna(frame["w"].iloc[0])
    cost = turnover * (cost_bps / 1e4)
    return (frame["w"] - 1.0) * frame["r"] - cost


def giv_footnote70(dq, shares, gdp, n_pcs):
    """Footnote 70's alternative: residualise the eq.(67) residuals on the
    principal components before size-weighting, so n_pcs actually bites."""
    cols = instrument_sectors(list(dq.columns))
    sub = dq[cols]
    weights = pseudo_equal_weights(sub)
    dq_check = panel_residuals(sub, gdp, weights)
    pcs = extract_pcs(dq_check, weights, n_pcs)
    x = np.column_stack([np.ones(len(pcs)), pcs.to_numpy()])
    resid = {}
    for c in dq_check.columns:
        beta, *_ = np.linalg.lstsq(x, dq_check[c].to_numpy(), rcond=None)
        resid[c] = dq_check[c].to_numpy() - x @ beta
    u = pd.DataFrame(resid, index=dq_check.index)
    return giv_instrument(u, shares)


def recursive_footnote70(dq, shares, gdp, n_pcs, warmup=20):
    out = {}
    idx = dq.index
    for pos in range(warmup, len(idx)):
        upto = idx[: pos + 1]
        z = giv_footnote70(dq.loc[upto], shares.loc[upto], gdp, n_pcs)
        out[idx[pos]] = float(z.iloc[-1])
    return pd.Series(out).sort_index()


def main() -> None:
    wide = load_z1_holdings()
    gdp = load_real_gdp_growth()
    sectors = select_giv_sectors(wide)
    dq, shares = build_dq_panel(wide, sectors)
    market_excess = quarterly_market_excess()
    denominators = policy_d_denominators(INELASTIC_N_TRIALS)
    grid = spec_grid()
    report: dict[str, object] = {"NOT_REGISTERED": True, "denominators": denominators}

    z_std = {p: recursive_giv(dq, shares, gdp, p) for p in (1, 2)}

    # ---- A. reversal sign -------------------------------------------------
    rows = []
    for sign, label in ((1.0, "registered_positive"), (-1.0, "exploratory_reversal")):
        streams = {}
        for n_pcs, std, rule, hold in grid:
            sid = f"pcs{n_pcs}_{std}_{rule}_{hold}"
            s = replay_signed(
                z_std[n_pcs], market_excess, std, rule, hold, INELASTIC_COST_BPS, sign
            )
            if s is not None:
                streams[sid] = s
        sharpes = {k: sharpe_ratio(v, periods_per_year=QUARTERS_PER_YEAR) for k, v in streams.items()}
        sigma = float(np.std(list(sharpes.values()), ddof=1))
        # searching the sign doubles the real search: 48, not 24
        dens_signed = policy_d_denominators(INELASTIC_N_TRIALS * 2)
        best_id = max(sharpes, key=lambda k: sharpes[k])
        dsr_best = dsr_across_denominators(
            sharpes[best_id], streams[best_id], sigma, dens_signed
        )
        rows.append(
            {
                "arm": label,
                "best_spec": best_id,
                "best_overlay_sharpe": sharpes[best_id],
                "median_overlay_sharpe": float(np.median(list(sharpes.values()))),
                "dsr_if_sign_were_searched": dsr_best,
                "denominators_if_sign_searched": dens_signed,
                "verdict_even_with_searched_sign": verdict_from_dsr(dsr_best),
            }
        )
    report["A_sign_arms"] = rows

    # ---- B. footnote 70 alternative instrument ----------------------------
    z70 = {p: recursive_footnote70(dq, shares, gdp, p) for p in (1, 2)}
    report["B_footnote70_n_pcs_now_bites"] = float(
        (z70[1] - z70[2]).abs().max()
    )
    b_rows = []
    for sign, label in ((1.0, "registered_positive"), (-1.0, "reversal")):
        sharpes = {}
        streams = {}
        for n_pcs, std, rule, hold in grid:
            sid = f"pcs{n_pcs}_{std}_{rule}_{hold}"
            s = replay_signed(
                z70[n_pcs], market_excess, std, rule, hold, INELASTIC_COST_BPS, sign
            )
            if s is not None:
                streams[sid] = s
                sharpes[sid] = sharpe_ratio(s, periods_per_year=QUARTERS_PER_YEAR)
        sigma = float(np.std(list(sharpes.values()), ddof=1))
        best_id = max(sharpes, key=lambda k: sharpes[k])
        b_rows.append(
            {
                "arm": label,
                "best_spec": best_id,
                "best_overlay_sharpe": sharpes[best_id],
                "median_overlay_sharpe": float(np.median(list(sharpes.values()))),
                "dsr_best": dsr_across_denominators(
                    sharpes[best_id], streams[best_id], sigma, denominators
                ),
            }
        )
    report["B_footnote70_arms"] = b_rows

    # ---- C. the paper's permanence claim, tested directly -----------------
    z, _ = build_giv(dq, shares, gdp, 1)
    mkt = market_excess
    horizons = {}
    for h in range(0, 5):
        # future return over quarter t+h (h=0 is contemporaneous)
        fut = mkt.shift(-h)
        f = pd.concat([z.rename("z"), fut.rename("r")], axis=1).dropna()
        if len(f) < 20:
            continue
        beta = _ols(f["r"].to_numpy(), f[["z"]].to_numpy())
        yhat = np.column_stack([np.ones(len(f)), f[["z"]].to_numpy()]) @ beta
        resid = f["r"].to_numpy() - yhat
        n, k = len(f), 2
        se = float(
            np.sqrt(
                (resid**2).sum()
                / (n - k)
                * np.linalg.inv(
                    np.column_stack([np.ones(n), f[["z"]].to_numpy()]).T
                    @ np.column_stack([np.ones(n), f[["z"]].to_numpy()])
                )[1, 1]
            )
        )
        horizons[h] = {
            "n": n,
            "coefficient": float(beta[1]),
            "std_error": se,
            "t_stat": float(beta[1] / se) if se > 0 else float("nan"),
            "corr": float(f["z"].corr(f["r"])),
        }
    report["C_permanence_future_return_on_Z"] = {
        "note": (
            "h=0 is contemporaneous (the paper's own estimand). h>=1 are FUTURE "
            "quarter returns. [GK21] predicts h>=1 coefficients ~ 0."
        ),
        "horizons": horizons,
    }

    out = OUT / f"inelastic_markets_EXPLORATORY_{date.today().isoformat()}.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
