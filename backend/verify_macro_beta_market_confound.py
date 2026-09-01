"""POST-HOC diagnostic for the macro-beta family. NOT pre-registered.

WHY THIS EXISTS
============================================================================
The pre-registered run returned "skill" for exactly three drivers —
copper_cper, china_fxi and credit_spread — and for both beta variants of
each. Those are precisely the three drivers whose daily moves co-move most
strongly with the US equity market. That coincidence is suspicious enough to
test rather than celebrate.

THE MECHANISM BEING TESTED. The pre-registration argued that the per-day
Spearman statistic is "automatically immune to the market-direction
confound" because Spearman is invariant to subtracting a constant from every
return on a day. That argument is CORRECT but NARROWER THAN IT SOUNDS: it
immunises against the market LEVEL shift, not against the market-BETA
channel, which is a different and more damaging confound:

    A stock's beta to copper is largely a proxy for its beta to the MARKET —
    high-beta cyclicals have high copper betas. On a day copper falls hard
    the market usually falls too, and high-market-beta names fall most.
    Orienting by sign(driver move) then lines those names up exactly where a
    positive rank correlation needs them. The statistic would come out
    positive even if copper carried no information about any individual
    stock beyond "this is a high-beta name."

This diagnostic re-runs the identical test with the market-beta channel
partialled out cross-sectionally.

WHAT MAKES RUNNING IT AFTER SEEING THE RESULT LEGITIMATE (corrected
2026-09-01 by independent verification; the earlier wording here claimed the
diagnostic "can only ever WEAKEN the pre-registered claim, never strengthen
it", which is FALSE — see the nine flips in section 6b of the results file):

    The diagnostic CAN create apparent new positives. This analysis declines
    to count any of them. Only the pre-registered positives are ever
    evaluated through it, and any new apparent positive would need its own
    fresh, separately pre-registered test before being trusted.

So the discipline is a rule about what is COUNTED, not a mathematical
property of the statistic. Stated that way it is honest; stated the old way
it was contradicted by this script's own output.

Market proxy: the equal-weighted cross-sectional mean return of the universe
itself. No extra fetch, and it is exactly the quantity the demeaning step
already implicitly references.
"""

import json
import logging
from datetime import date

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp

from app.db import SessionLocal
from app.services.macro_data.fred_provider import FredProvider
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.macro_beta import (
    BETA_VARIANT_FULL_SAMPLE,
    BETA_VARIANT_SHOCK_DAYS,
    BONFERRONI_ALPHA,
    MACRO_DRIVERS,
    OOS_FIT_WINDOW_DAYS,
    OOS_TEST_WINDOW_DAYS,
    _fit_betas_over_window,
    _ols_with_intercept,
    load_macro_beta_inputs,
    shock_day_mask,
)
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # never print the FRED key
log = logging.getLogger("confound")

OUT = "/tmp/macro_beta_confound.json"


def _residualize(target: np.ndarray, control: np.ndarray) -> np.ndarray:
    """Cross-sectional residual of `target` after regressing it on `control`
    with an intercept. Returns `target` centred if the control is degenerate."""
    fit = _ols_with_intercept(target, control)
    if fit is None:
        return target - target.mean()
    return (target - target.mean()) - fit.beta * (control - control.mean())


if __name__ == "__main__":
    end = date(2026, 8, 31)
    db = SessionLocal()
    try:
        inputs = load_macro_beta_inputs(
            db, YFinanceProvider(), FredProvider(), list(SCREENING_UNIVERSE),
            end=end, trading_days_needed=700,
        )
    finally:
        db.close()

    returns = inputs.ticker_returns
    # Equal-weighted market return: the cross-sectional mean each day.
    market = returns.mean(axis=1)

    rows = []
    for driver in MACRO_DRIVERS:
        moves = inputs.driver_moves[driver.driver_id]
        common = returns.index.intersection(moves.index).sort_values()
        required = OOS_FIT_WINDOW_DAYS + OOS_TEST_WINDOW_DAYS
        fit_index = common[-required:-OOS_TEST_WINDOW_DAYS]
        test_index = common[-OOS_TEST_WINDOW_DAYS:]

        fitted = _fit_betas_over_window(returns, moves, fit_index)
        # Market betas over the SAME fit window, same estimator.
        market_betas: dict[str, float] = {}
        for ticker in returns.columns:
            aligned = pd.concat(
                {"r": returns[ticker].loc[fit_index], "m": market.loc[fit_index]},
                axis=1, join="inner",
            ).dropna()
            if len(aligned) < 60:
                continue
            fit = _ols_with_intercept(
                aligned["r"].to_numpy(float), aligned["m"].to_numpy(float)
            )
            if fit is not None:
                market_betas[ticker] = fit.beta

        test_moves = moves.loc[test_index]
        shock_days = test_index[shock_day_mask(test_moves).to_numpy()]

        for variant in (BETA_VARIANT_FULL_SAMPLE, BETA_VARIANT_SHOCK_DAYS):
            betas = {
                t: (r.beta_full_sample if variant == BETA_VARIANT_FULL_SAMPLE
                    else r.beta_shock_days)
                for t, r in fitted.items()
            }
            betas = {
                t: b for t, b in betas.items()
                if b is not None and np.isfinite(b) and t in market_betas
            }
            beta_series = pd.Series(betas)
            market_series = pd.Series({t: market_betas[t] for t in beta_series.index})

            # How much of the driver beta IS the market beta, cross-sectionally?
            beta_vs_market_corr = float(
                np.corrcoef(beta_series.to_numpy(), market_series.to_numpy())[0, 1]
            )

            raw_rhos, partial_rhos = [], []
            for day in shock_days:
                day_returns = returns.loc[day, list(beta_series.index)].dropna()
                if len(day_returns) < 100:
                    continue
                move = float(test_moves.loc[day])
                if move == 0.0:
                    continue
                oriented = (day_returns * np.sign(move)).to_numpy(float)
                b = beta_series.loc[day_returns.index].to_numpy(float)
                mb = market_series.loc[day_returns.index].to_numpy(float)

                rho = spearmanr(b, oriented).statistic
                if np.isfinite(rho):
                    raw_rhos.append(float(rho))

                # Partial out the market-beta channel from BOTH sides.
                p_rho = spearmanr(_residualize(b, mb), _residualize(oriented, mb)).statistic
                if np.isfinite(p_rho):
                    partial_rhos.append(float(p_rho))

            def _test(values, label):
                if len(values) < 2:
                    return None, None, None
                arr = np.asarray(values)
                if arr.std(ddof=1) == 0:
                    return float(arr.mean()), None, None
                r = ttest_1samp(arr, 0.0, alternative="greater")
                return float(arr.mean()), float(r.statistic), float(r.pvalue)

            raw_mean, raw_t, raw_p = _test(raw_rhos, "raw")
            par_mean, par_t, par_p = _test(partial_rhos, "partial")

            row = {
                "driver": driver.driver_id,
                "variant": variant,
                "n_days": len(raw_rhos),
                "beta_vs_market_beta_corr": beta_vs_market_corr,
                "raw_mean_rho": raw_mean,
                "raw_p": raw_p,
                "partial_mean_rho": par_mean,
                "partial_p": par_p,
                "raw_passes": raw_p is not None and raw_mean > 0 and raw_p < BONFERRONI_ALPHA,
                "partial_passes": (
                    par_p is not None and par_mean > 0 and par_p < BONFERRONI_ALPHA
                ),
            }
            rows.append(row)
            log.info(
                "%-20s %-12s corr(beta,mktbeta)=%+.3f | raw rho=%+.4f p=%.2e pass=%-5s | "
                "PARTIAL rho=%+.4f p=%.2e pass=%s",
                row["driver"], row["variant"], row["beta_vs_market_beta_corr"],
                row["raw_mean_rho"], row["raw_p"], row["raw_passes"],
                row["partial_mean_rho"], row["partial_p"], row["partial_passes"],
            )

    with open(OUT, "w") as fh:
        json.dump(rows, fh, indent=2)
    log.info("wrote %s", OUT)

    raw_pass = sum(1 for r in rows if r["raw_passes"])
    par_pass = sum(1 for r in rows if r["partial_passes"])
    log.info("SUMMARY: %d/26 pass raw, %d/26 survive the market-beta control", raw_pass, par_pass)
