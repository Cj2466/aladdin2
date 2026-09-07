"""IDIOSYNCRATIC TSMOM on the 31-instrument CME-SPAN futures panel.

Builds a real, tradeable strategy return series, charges it a cited cost
model, and scores it with the project's DSR N-ladder and preservation_score.
The pre-registration committed BEFORE this script produced any number is
data/research_runs/tsmom_idiosyncratic_signal_PREREGISTRATION.txt.

WHAT IS REUSED VERBATIM (nothing in app/services is modified by this work):
  app/services/research_lab/tsmom_signal.py            MOP Eq.(1) / Eq.(5)
  app/services/research_lab/tsmom_regime_definition.py pre-registered regime
  app/services/research_lab/dsr_policy_n.py            the {n_local,37,362,1031} ladder
  app/services/research_lab/deflated_sharpe.py         PSR / SR0 / DSR
  app/services/research_lab/preservation_score.py      mandatory secondary check
  app/services/research_lab/metrics.py                 sharpe_ratio

THE WALK-FORWARD FACTOR ESTIMATION IS THE SAME PROCEDURE, NOT A NEW ONE.
`_fit_factors_from_prior` below is residualize_pit()'s per-boundary body from
run_tsmom_factor_decomposition_2026_09_07.py, lifted unchanged in every
statistical respect: strictly-prior mean/std, correlation matrix of the
standardized prior block, eigh + descending sort, top-k eigenvectors, OLS of
the standardized prior on [1, factor scores]. Same BURN_IN_DAYS=504, same
REFIT_EVERY_DAYS=21, same k=6. The only thing this file adds is the step BACK
INTO RETURN UNITS, because a z-score residual is not a tradeable P&L and the
prior task never needed one. That conversion is exact and is asserted below.

THE PORTFOLIO IDENTITY THIS FILE RESTS ON
-----------------------------------------
At a refit boundary let m, s be the strictly-prior per-instrument mean and
standard deviation, L (n x k) the top-k eigenvectors of the prior correlation
matrix, and B (k x n) the fitted OLS betas of the standardized returns on the
factor scores.

  factor score of factor j:      f_j = sum_i (L[i,j] / s_i) * r_i
  TSMOM weight of instrument i:  w_i = sign_i * (0.40 / sigma_i) / S
  the leg's exposure to f_j:     E_j = sum_i w_i * s_i * B[j,i]
  hedge weights:                 h_i = - sum_j E_j * L[i,j] / s_i
  idiosyncratic return:          sum_i (w_i + h_i) * r_i
                                   == (leg return) - sum_j E_j * f_j

The hedge is therefore a real portfolio of the same 31 instruments, and the
idiosyncratic return is literally "the TSMOM position's return minus the hedge
portfolio's return". The two routes are computed independently below and
asserted equal, so a sign or index error cannot pass silently.

DELIBERATELY NOT DEMEANED: f_j is built from raw r_i, not (r_i - m_i). The
demeaned version would be an equivalent variance hedge but would carry a
phantom cash leg (a deterministic constant with no instrument holding behind
it). A fully-invested futures portfolio is the tradeable object, so the
deterministic mean offset stays inside the hedge P&L where it belongs.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}")

from app.services.research_lab.deflated_sharpe import (  # noqa: E402
    compute_deflated_sharpe,
    compute_return_stats,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.dsr_policy_n import dsr_policy_denominators  # noqa: E402
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio  # noqa: E402
from app.services.research_lab.preservation_score import (  # noqa: E402
    compute_preservation_metrics,
)
from app.services.research_lab.tsmom_regime_definition import (  # noqa: E402
    classify_extreme_market_quarters,
)
from app.services.research_lab.tsmom_signal import (  # noqa: E402
    MOP_VOLATILITY_TARGET,
    ex_ante_volatility,
    trailing_return,
    tsmom_sign,
)

# --------------------------------------------------------------------------
# Where the real chained futures data lives (gitignored, produced by
# chain_cme_span_continuous.py in the futures-span-full-pull worktree).
# Same resolution order as run_tsmom_factor_decomposition_2026_09_07.py.
# --------------------------------------------------------------------------
_REPO_ROOT = _BACKEND.parent
_WT = ("futures-span-full-pull", "backend", "data", "futures_daily", "cme_span", "continuous")
_CONTINUOUS_CANDIDATES = [
    _BACKEND / "data" / "futures_daily" / "cme_span" / "continuous",
    _REPO_ROOT / ".claude" / "worktrees" / Path(*_WT),
    _REPO_ROOT.parent.parent.parent / ".claude" / "worktrees" / Path(*_WT),
]

# The main checkout holds the untracked price store (SPY, for the regime rule).
_MAIN_BACKEND = _REPO_ROOT.parent.parent.parent / "backend"
_SPY_CANDIDATES = [
    _BACKEND / "data" / "price_store" / "v1" / "SPY.csv.gz",
    _MAIN_BACKEND / "data" / "price_store" / "v1" / "SPY.csv.gz",
]

# --- constants carried over unchanged from the prior merged work -----------
BURN_IN_DAYS = 504  # run_tsmom_factor_decomposition_2026_09_07.py J1
REFIT_EVERY_DAYS = 21  # ditto
K_FACTORS = 6  # RMT-significant count measured in b8880c8; NOT searched here

# --- the pre-registered grid (tsmom_idiosyncratic_signal_PREREGISTRATION.txt)
GRID_LOOKBACK_BLOCKS = (1, 3, 12)
GRID_CONSTRUCTION = ("hedged", "unhedged")
HEADLINE_LOOKBACK = 12
HEADLINE_CONSTRUCTION = "hedged"

# --- the cited cost anchor -------------------------------------------------
# Hurst, Ooi & Pedersen (2013), "Demystifying Managed Futures", Journal of
# Investment Management 11(3), 42-58, Section 5, p.55:
#   "the annual transaction costs of a Managed Futures strategy are typically
#    about 1-4% for a sophisticated trader"
# and, same page, their diversified TSMOM strategy is "run at a 10%
# annualized volatility". Footnote 7: proprietary estimates for a manager with
# about USD 1 billion under management.
HOP_COST_BAND_LOW = 0.01
HOP_COST_BAND_MID = 0.025
HOP_COST_BAND_HIGH = 0.04
HOP_REFERENCE_VOLATILITY = 0.10
HOP_CITATION = (
    "Hurst, B., Ooi, Y. H. & Pedersen, L. H., 'Demystifying Managed Futures', "
    "Journal of Investment Management 11(3), 2013, pp. 42-58, Section 5 p.55 "
    "('the annual transaction costs of a Managed Futures strategy are typically about "
    "1-4% for a sophisticated trader') and footnote 7 (proprietary estimates, "
    "~USD 1bn AUM); reference strategy 'run at a 10% annualized volatility' (p.55)."
)

#: CL settled at -37.63 on 2020-04-20. The ratio convention then reports
#: -305.97% and -126.60% on the two following rows -- artifacts, not P&L.
#: Disclosed and handled identically in da504d2 / b8880c8.
CL_CORRUPTED_DATES = ("2020-04-20", "2020-04-21")

OUT_TXT = _BACKEND / "data" / "research_runs" / "tsmom_idiosyncratic_signal_2026-09-08.txt"
OUT_JSON = _BACKEND / "data" / "research_runs" / "tsmom_idiosyncratic_signal_2026-09-08.json"


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def continuous_dir() -> Path:
    for c in _CONTINUOUS_CANDIDATES:
        if c.exists():
            return c
    raise SystemExit(f"chained futures CSVs not found; looked in {_CONTINUOUS_CANDIDATES}")


def load_return_panel() -> pd.DataFrame:
    """Byte-identical logic to measure_futures_breadth_2026_09_07.py's loader."""
    series: dict[str, pd.Series] = {}
    for path in sorted(continuous_dir().glob("*.csv")):
        frame = pd.read_csv(path)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        series[path.stem] = pd.Series(
            frame["chained_daily_return"].to_numpy(dtype=float),
            index=pd.DatetimeIndex(frame["trade_date"]),
            name=path.stem,
        )
    return pd.DataFrame(series).sort_index().dropna(how="all")


def mask_cl_negative_price_dates(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    for d in CL_CORRUPTED_DATES:
        ts = pd.Timestamp(d)
        if "CL" in out.columns and ts in out.index:
            out.loc[ts, "CL"] = np.nan
    return out


def load_spy_prices() -> pd.Series:
    for c in _SPY_CANDIDATES:
        if c.exists():
            frame = pd.read_csv(c)
            date_col = "date" if "date" in frame.columns else frame.columns[0]
            close_col = next(x for x in ("close", "Close", "adj_close") if x in frame.columns)
            s = pd.Series(
                frame[close_col].to_numpy(dtype=float),
                index=pd.DatetimeIndex(pd.to_datetime(frame[date_col])),
            ).sort_index()
            return s.dropna()
    raise SystemExit(f"SPY price store not found; looked in {_SPY_CANDIDATES}")


# --------------------------------------------------------------------------
# The walk-forward factor fit -- residualize_pit()'s body, unchanged
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FactorFit:
    mean: np.ndarray  # (n,)
    std: np.ndarray  # (n,)
    loadings: np.ndarray  # (n, k)
    betas: np.ndarray  # (k, n)
    intercept: np.ndarray  # (n,)


def _fit_factors_from_prior(prior: np.ndarray, k: int) -> FactorFit | None:
    mean = prior.mean(axis=0)
    std = prior.std(axis=0, ddof=1)
    if np.any(std <= 0) or not np.all(np.isfinite(std)):
        return None
    z_prior = (prior - mean) / std
    corr_prior = np.corrcoef(z_prior, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(corr_prior)
    order = np.argsort(eigvals)[::-1]
    loadings = eigvecs[:, order][:, :k]
    factors_prior = z_prior @ loadings
    design_prior = np.column_stack([np.ones(len(z_prior)), factors_prior])
    coef, *_ = np.linalg.lstsq(design_prior, z_prior, rcond=None)
    return FactorFit(mean=mean, std=std, loadings=loadings, betas=coef[1:], intercept=coef[0])


# --------------------------------------------------------------------------
# Signal construction
# --------------------------------------------------------------------------
def block_returns(values: np.ndarray, block: int) -> np.ndarray:
    """Compounded return of each non-overlapping `block`-row window, anchored
    at row 0. BURN_IN_DAYS (504) is 24 * REFIT_EVERY_DAYS (21), so every refit
    boundary falls exactly on a block edge and no window straddles one."""
    n_blocks = values.shape[0] // block
    out = np.empty((n_blocks, values.shape[1]))
    for b in range(n_blocks):
        chunk = values[b * block : (b + 1) * block]
        out[b] = np.prod(1.0 + chunk, axis=0) - 1.0
    return out


@dataclass
class StrategyRun:
    lookback_days: int
    rebalance_every: int
    construction: str
    dates: pd.DatetimeIndex
    gross: pd.Series
    turnover_at_boundary: pd.Series  # one-way L1 weight change, netted
    leg_turnover: float  # total one-way turnover of the TSMOM leg alone
    hedge_turnover: float  # total one-way turnover of the hedge leg alone
    net_turnover: float  # total one-way turnover of the netted book
    mean_gross_notional: float


def build_strategy(
    panel: pd.DataFrame,
    lookback_days: int,
    construction: str,
    k: int = K_FACTORS,
    rebalance_every: int = REFIT_EVERY_DAYS,
) -> StrategyRun:
    values = panel.to_numpy()
    n_obs, n_inst = values.shape
    dates = panel.index

    # MOP Eq. (1), p.233 -- strictly causal, computed once on the full daily
    # series. sigma_t depends only on rows before t, so evaluating it at a
    # boundary introduces no lookahead.
    sigma = pd.DataFrame(
        {c: ex_ante_volatility(panel[c]) for c in panel.columns}, index=dates
    ).to_numpy()

    # MOP Eq. (5)'s sign(r_{t-12,t}), via tsmom_signal.trailing_return's
    # compounded trailing window (MOP Section 2.1's cumulative return index),
    # measured in DAYS so the rebalance frequency and the lookback horizon are
    # independent. For rebalance_every=21 and lookback_days=21*b this is
    # arithmetically identical to compounding b non-overlapping 21-day blocks,
    # which the regression assertion in main() checks.
    signs = pd.DataFrame(
        {c: np.sign(trailing_return(panel[c], lookback_days)) for c in panel.columns}
    ).to_numpy()

    gross = np.full(n_obs, np.nan)
    turnover = np.zeros(n_obs)
    prev_w = np.zeros(n_inst)
    prev_leg = np.zeros(n_inst)
    prev_hedge = np.zeros(n_inst)
    leg_to = hedge_to = net_to = 0.0
    gross_notional: list[float] = []

    start = BURN_IN_DAYS
    while start < n_obs:
        stop = min(start + rebalance_every, n_obs)
        fit = _fit_factors_from_prior(values[:start], k)
        if fit is None:
            start = stop
            continue

        sign_row = signs[start - 1]  # last value knowable strictly before `start`
        sigma_row = sigma[start - 1]  # last value knowable strictly before `start`
        with np.errstate(divide="ignore", invalid="ignore"):
            raw_size = MOP_VOLATILITY_TARGET / sigma_row
        usable = np.isfinite(sign_row) & np.isfinite(raw_size) & (sigma_row > 0)
        s_t = int(usable.sum())
        if s_t == 0:
            start = stop
            continue

        # MOP p.236's diversified portfolio: equal-weighted 1/S_t across the
        # S_t instruments actually available at t.
        w = np.zeros(n_inst)
        w[usable] = sign_row[usable] * raw_size[usable] / s_t

        if construction == "hedged":
            exposure = fit.betas @ (w * fit.std)  # (k,)
            hedge = -(fit.loadings @ exposure) / fit.std  # (n,)
        else:
            exposure = np.zeros(k)
            hedge = np.zeros(n_inst)

        w_net = w + hedge

        # --- costs are charged on the boundary day, on the L1 change of the
        # netted instrument-space book. Netting is physically correct: the
        # hedge is a combination of the SAME 31 instruments, so an offsetting
        # hedge leg is not separately executed. Leg-wise turnover is also
        # accumulated and reported as the conservative (no-netting) variant.
        turnover[start] = float(np.abs(w_net - prev_w).sum())
        net_to += turnover[start]
        leg_to += float(np.abs(w - prev_leg).sum())
        hedge_to += float(np.abs(hedge - prev_hedge).sum())
        prev_w, prev_leg, prev_hedge = w_net, w, hedge
        gross_notional.append(float(np.abs(w_net).sum()))

        block_vals = values[start:stop]
        clean = np.nan_to_num(block_vals, nan=0.0)  # an absent instrument is not traded
        leg_ret = clean @ w
        if construction == "hedged":
            # Route A: the netted book.
            route_a = clean @ w_net
            # Route B: leg return MINUS the hedge portfolio's return, built
            # from the factor-mimicking portfolios exactly as the docstring
            # defines them. Independent arithmetic, same answer, or abort.
            fmp = clean @ (fit.loadings / fit.std[:, None])  # (rows, k)
            route_b = leg_ret - fmp @ exposure
            delta = float(np.abs(route_a - route_b).max())
            if delta > 1e-10:
                raise AssertionError(f"hedge routes disagree by {delta:.3e} at row {start}")
            gross[start:stop] = route_a
        else:
            gross[start:stop] = leg_ret

        start = stop

    mask = np.isfinite(gross)
    return StrategyRun(
        lookback_days=lookback_days,
        rebalance_every=rebalance_every,
        construction=construction,
        dates=dates[mask],
        gross=pd.Series(gross[mask], index=dates[mask]),
        turnover_at_boundary=pd.Series(turnover[mask], index=dates[mask]),
        leg_turnover=leg_to,
        hedge_turnover=hedge_to,
        net_turnover=net_to,
        mean_gross_notional=float(np.mean(gross_notional)) if gross_notional else float("nan"),
    )


# --------------------------------------------------------------------------
# Costs
# --------------------------------------------------------------------------
def years_of(index: pd.DatetimeIndex) -> float:
    return len(index) / TRADING_DAYS_PER_YEAR


def solve_cost_per_unit(reference: StrategyRun, anchor_pct: float) -> float:
    """Back-solve the one-way cost per unit of notional traded so that the
    reference book pays the cited annual cost, after rescaling the anchor from
    Hurst et al.'s 10%-vol reference book to this leg's own realized
    volatility (cost is linear in gross exposure, hence in the vol target).

    THE REFERENCE BOOK MUST BE TURNOVER-MATCHED TO THE CITATION, and getting
    this wrong is not a footnote. Hurst et al. state (Section 3.1) that "the
    portfolio is rebalanced weekly at the closing price each Friday". Their
    1-4%/yr is therefore the cost of a WEEKLY book. Back-solving c from a
    21-day book's much lower turnover to hit the same annual dollar cost
    inflates c by roughly the turnover ratio -- measured at ~4x here -- and
    that inflation is large enough to flip a net Sharpe on its own. The
    reference passed in is consequently the weekly-rebalanced unhedged leg;
    the 21-day-referenced calibration is retained only as a labelled
    (over-punitive) sensitivity."""
    vol = float(reference.gross.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    target_annual_cost = anchor_pct * (vol / HOP_REFERENCE_VOLATILITY)
    annual_turnover = reference.net_turnover / years_of(reference.dates)
    if annual_turnover <= 0:
        raise SystemExit("reference leg has zero turnover; cannot calibrate a cost")
    return target_annual_cost / annual_turnover


def net_of_cost(run: StrategyRun, cost_per_unit: float) -> pd.Series:
    return run.gross - cost_per_unit * run.turnover_at_boundary


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
def dsr_by_denominator(
    returns: pd.Series, sharpe_ann: float, sigma_sr: float | None, denominators: list[int]
) -> dict[int, float | None]:
    stats = compute_return_stats(returns)
    out: dict[int, float | None] = {}
    for n in denominators:
        if stats is None or sigma_sr is None or not np.isfinite(sigma_sr):
            out[n] = None
            continue
        sr0_daily = expected_max_sharpe_under_noise(
            sigma_sr / np.sqrt(TRADING_DAYS_PER_YEAR), n
        )
        if sr0_daily is None:
            out[n] = None
            continue
        out[n] = probabilistic_sharpe_ratio(
            sharpe_ann / np.sqrt(TRADING_DAYS_PER_YEAR),
            sr0_daily,
            stats.n,
            stats.skewness,
            stats.kurtosis,
        )
    return out


def two_tier_verdict(dsr_map: dict[int, float | None], bar: float = 0.95) -> str:
    ns = sorted(dsr_map)
    if not ns:
        return "UNCOMPUTABLE"
    lenient, conservative = dsr_map[ns[0]], dsr_map[ns[-1]]
    if lenient is None:
        return "UNCOMPUTABLE"
    if lenient < bar:
        return "DEFINITE_NEGATIVE"
    if conservative is not None and conservative >= bar:
        return "PASS"
    return "UNRESOLVED"


def main() -> None:
    panel_raw = load_return_panel()
    panel_masked = mask_cl_negative_price_dates(panel_raw)
    common = panel_masked.dropna(how="any")
    common_unmasked = panel_raw.dropna(how="any")

    # Regression check: the day-measured trailing sign must reproduce the
    # non-overlapping-block sign at every rebalance boundary, or the switch
    # from block-indexed to day-indexed lookbacks changed the signal.
    # Disagreements are tolerated ONLY where the trailing return is a
    # floating-point tie: the two routes compound differently (product of
    # 1+r vs expm1 of summed log1p), so a window whose true cumulative return
    # is zero can land either side of zero in the last bits. One such tie was
    # found and inspected (ZW, 21-day window ending 2023-10-26: the two routes
    # give +2.22e-16 and -4.09e-16). MOP offer no tie-break and tsmom_sign
    # returns 0 for an exact zero, so a tie is economically a no-position.
    # Any disagreement at a MATERIAL trailing return is a real bug and aborts.
    _TIE_TOLERANCE = 1e-12
    _vals = common.to_numpy()
    _blocks = pd.DataFrame(block_returns(_vals, REFIT_EVERY_DAYS), columns=common.columns)
    n_ties = 0
    for lb in GRID_LOOKBACK_BLOCKS:
        block_ret = _blocks.rolling(lb).apply(lambda w: np.prod(1 + w) - 1, raw=True).to_numpy()
        by_block = pd.DataFrame(
            {c: tsmom_sign(_blocks[c], lb) for c in _blocks.columns}
        ).to_numpy()
        day_ret = pd.DataFrame(
            {c: trailing_return(common[c], lb * REFIT_EVERY_DAYS) for c in common.columns}
        ).to_numpy()
        by_day = np.sign(day_ret)
        for start in range(BURN_IN_DAYS, len(common), REFIT_EVERY_DAYS):
            bi = start // REFIT_EVERY_DAYS - 1
            a_, b_ = by_block[bi], by_day[start - 1]
            bad = np.nan_to_num(a_, nan=9) != np.nan_to_num(b_, nan=9)
            if not bad.any():
                continue
            magnitudes = np.maximum(np.abs(block_ret[bi][bad]), np.abs(day_ret[start - 1][bad]))
            if np.nanmax(magnitudes) > _TIE_TOLERANCE:
                raise AssertionError(
                    f"block/day lookback signs disagree MATERIALLY at row {start}, lb={lb}: "
                    f"max |trailing return| among disagreements = {np.nanmax(magnitudes):.3e}"
                )
            n_ties += int(bad.sum())

    runs: dict[tuple[int, str], StrategyRun] = {}
    for lb in GRID_LOOKBACK_BLOCKS:
        for construction in GRID_CONSTRUCTION:
            runs[(lb, construction)] = build_strategy(
                common, lb * REFIT_EVERY_DAYS, construction
            )

    # Cost calibration reference: unhedged, 252-day lookback, rebalanced
    # WEEKLY -- turnover-matched to Hurst et al.'s own weekly book.
    reference = build_strategy(common, 252, "unhedged", rebalance_every=5)
    reference_21d = runs[(HEADLINE_LOOKBACK, "unhedged")]
    cost_by_anchor = {
        a: solve_cost_per_unit(reference, a)
        for a in (HOP_COST_BAND_LOW, HOP_COST_BAND_MID, HOP_COST_BAND_HIGH)
    }
    cost_by_anchor_21d_ref = {
        a: solve_cost_per_unit(reference_21d, a)
        for a in (HOP_COST_BAND_LOW, HOP_COST_BAND_MID, HOP_COST_BAND_HIGH)
    }
    cost_mid = cost_by_anchor[HOP_COST_BAND_MID]

    net_mid = {key: net_of_cost(run, cost_mid) for key, run in runs.items()}
    sharpes_mid = {
        key: float(sharpe_ratio(s, periods_per_year=TRADING_DAYS_PER_YEAR))
        for key, s in net_mid.items()
    }
    sigma_sr = float(np.std(list(sharpes_mid.values()), ddof=1))

    n_local = len(runs)
    denominators = dsr_policy_denominators(n_local)

    headline_key = (HEADLINE_LOOKBACK, HEADLINE_CONSTRUCTION)
    headline_net = net_mid[headline_key]
    headline_run = runs[headline_key]
    headline_dsr = dsr_by_denominator(
        headline_net, sharpes_mid[headline_key], sigma_sr, denominators
    )
    headline_verdict = two_tier_verdict(headline_dsr)

    preservation = compute_preservation_metrics(
        headline_net, dsr=headline_dsr.get(n_local)
    ).as_dict()

    # --- regime split, using the pre-registered rule ------------------------
    regime = classify_extreme_market_quarters(load_spy_prices())
    quarter_label = regime.labels
    day_labels = pd.Series(
        pd.PeriodIndex(headline_net.index, freq="Q").to_timestamp(how="end").normalize(),
        index=headline_net.index,
    )
    lookup = {k.normalize(): v for k, v in quarter_label.items()}
    day_regime = day_labels.map(lambda d: lookup.get(d, "unclassified"))

    regime_block: dict[str, Any] = {}
    for label in ("extreme", "normal"):
        subset_idx = day_regime[day_regime == label].index
        sub_sharpes = {
            key: float(sharpe_ratio(s.loc[s.index.intersection(subset_idx)],
                                    periods_per_year=TRADING_DAYS_PER_YEAR))
            for key, s in net_mid.items()
        }
        sub_sigma = float(np.std(list(sub_sharpes.values()), ddof=1))
        sub = headline_net.loc[headline_net.index.intersection(subset_idx)]
        sub_dsr = dsr_by_denominator(sub, sub_sharpes[headline_key], sub_sigma, denominators)
        regime_block[label] = {
            "n_days": int(len(sub)),
            "sharpe_net_annualized": sub_sharpes[headline_key],
            "sigma_sr_annualized": sub_sigma,
            "dsr_by_n": {str(n): v for n, v in sub_dsr.items()},
            "verdict": two_tier_verdict(sub_dsr),
        }

    # --- sensitivity: the unmasked CL panel --------------------------------
    unmasked_run = build_strategy(
        common_unmasked, HEADLINE_LOOKBACK * REFIT_EVERY_DAYS, HEADLINE_CONSTRUCTION
    )
    unmasked_net = net_of_cost(unmasked_run, cost_mid)

    payload: dict[str, Any] = {
        "schema": "tsmom_idiosyncratic_signal/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "preregistration": "data/research_runs/tsmom_idiosyncratic_signal_PREREGISTRATION.txt",
        "panel": {
            "source": str(continuous_dir()),
            "n_instruments": int(common.shape[1]),
            "instruments": list(common.columns),
            "common_window_first": str(common.index.min().date()),
            "common_window_last": str(common.index.max().date()),
            "common_window_n_obs": int(common.shape[0]),
            "cl_dates_masked": list(CL_CORRUPTED_DATES),
        },
        "construction": {
            "burn_in_days": BURN_IN_DAYS,
            "refit_every_days": REFIT_EVERY_DAYS,
            "k_factors": K_FACTORS,
            "volatility_target": MOP_VOLATILITY_TARGET,
            "n_local": n_local,
            "denominators": denominators,
            "sigma_sr_annualized": sigma_sr,
            "n_floating_point_sign_ties": n_ties,
        },
        "cost_model": {
            "citation": HOP_CITATION,
            "anchors_annual_pct_of_nav_at_10pct_vol": {
                "low": HOP_COST_BAND_LOW,
                "mid": HOP_COST_BAND_MID,
                "high": HOP_COST_BAND_HIGH,
            },
            "cost_per_unit_notional_traded": {str(k): v for k, v in cost_by_anchor.items()},
            "reference_leg": "252-day lookback, unhedged, rebalanced WEEKLY (turnover-matched "
            "to Hurst et al. Section 3.1's Friday-close weekly rebalance)",
            "reference_leg_gross_vol": float(
                reference.gross.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
            ),
            "reference_leg_annual_turnover": reference.net_turnover / years_of(reference.dates),
            "turnover_ratio_weekly_over_21day": (
                (reference.net_turnover / years_of(reference.dates))
                / (reference_21d.net_turnover / years_of(reference_21d.dates))
            ),
            "OVERPUNITIVE_21day_referenced_cost_per_unit": {
                str(k): v for k, v in cost_by_anchor_21d_ref.items()
            },
        },
        "specs": {},
        "headline": {
            "lookback_blocks": HEADLINE_LOOKBACK,
            "construction": HEADLINE_CONSTRUCTION,
            "cost_anchor": HOP_COST_BAND_MID,
            "n_days": int(len(headline_net)),
            "first_day": str(headline_net.index.min().date()),
            "last_day": str(headline_net.index.max().date()),
            "sharpe_gross_annualized": float(
                sharpe_ratio(headline_run.gross, periods_per_year=TRADING_DAYS_PER_YEAR)
            ),
            "sharpe_net_annualized": sharpes_mid[headline_key],
            "dsr_by_n": {str(n): v for n, v in headline_dsr.items()},
            "verdict": headline_verdict,
            "preservation": preservation,
        },
        "regime_conditional": {
            "rule": regime.rule_name,
            "module": "app/services/research_lab/tsmom_regime_definition.py",
            "n_unclassified_days": int((day_regime == "unclassified").sum()),
            **regime_block,
        },
        "sensitivity": {
            "cl_unmasked": {
                "n_days": int(len(unmasked_net)),
                "sharpe_net_annualized": float(
                    sharpe_ratio(unmasked_net, periods_per_year=TRADING_DAYS_PER_YEAR)
                ),
            },
            "cost_anchor_sweep": {},
        },
    }

    for key, run in runs.items():
        lb, construction = key
        gross_sr = float(sharpe_ratio(run.gross, periods_per_year=TRADING_DAYS_PER_YEAR))
        payload["specs"][f"lb{lb}_{construction}"] = {
            "lookback_blocks": lb,
            "construction": construction,
            "n_days": int(len(run.gross)),
            "sharpe_gross_annualized": gross_sr,
            "sharpe_net_annualized": sharpes_mid[key],
            "vol_gross_annualized": float(
                run.gross.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
            ),
            "annual_turnover_netted": run.net_turnover / years_of(run.dates),
            "annual_turnover_tsmom_leg": run.leg_turnover / years_of(run.dates),
            "annual_turnover_hedge_leg": run.hedge_turnover / years_of(run.dates),
            "mean_gross_notional": run.mean_gross_notional,
            "annual_cost_pct_of_nav": cost_mid * run.net_turnover / years_of(run.dates),
        }

    for anchor, c in cost_by_anchor.items():
        s = net_of_cost(headline_run, c)
        sh = {k2: float(sharpe_ratio(net_of_cost(r, c), periods_per_year=TRADING_DAYS_PER_YEAR))
              for k2, r in runs.items()}
        sig = float(np.std(list(sh.values()), ddof=1))
        d = dsr_by_denominator(s, sh[headline_key], sig, denominators)
        payload["sensitivity"]["cost_anchor_sweep"][str(anchor)] = {
            "cost_per_unit_notional_traded": c,
            "sharpe_net_annualized": sh[headline_key],
            "dsr_by_n": {str(n): v for n, v in d.items()},
            "verdict": two_tier_verdict(d),
        }

    # The 1.27x gross-up the factor-decomposition report flagged: measured,
    # and shown to be Sharpe-neutral because P&L and cost scale together.
    vol_hedged = float(runs[headline_key].gross.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    vol_raw = float(reference_21d.gross.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    lev = vol_raw / vol_hedged if vol_hedged > 0 else float("nan")
    levered_net = lev * runs[headline_key].gross - cost_mid * lev * runs[headline_key].turnover_at_boundary
    payload["gross_up"] = {
        "vol_raw_tsmom": vol_raw,
        "vol_idiosyncratic_tsmom": vol_hedged,
        "leverage_to_restore_raw_risk": lev,
        "sharpe_net_at_1x": sharpes_mid[headline_key],
        "sharpe_net_at_restored_leverage": float(
            sharpe_ratio(levered_net, periods_per_year=TRADING_DAYS_PER_YEAR)
        ),
        "note": (
            "Identical by construction: both P&L and cost are linear in gross exposure, so a "
            "uniform gross-up cannot change the net Sharpe. The 1.27x figure is a risk-target "
            "restatement, not a cost that the DSR verdict turns on. What DOES cost the "
            "hedged construction is the hedge leg's own turnover, reported per spec."
        ),
    }

    # The over-punitive 21-day-referenced calibration, kept visible so the
    # calibration choice is auditable rather than buried.
    for anchor, c in cost_by_anchor_21d_ref.items():
        s = net_of_cost(headline_run, c)
        sh = {k2: float(sharpe_ratio(net_of_cost(r, c), periods_per_year=TRADING_DAYS_PER_YEAR))
              for k2, r in runs.items()}
        sig = float(np.std(list(sh.values()), ddof=1))
        d = dsr_by_denominator(s, sh[headline_key], sig, denominators)
        payload["sensitivity"].setdefault("overpunitive_21day_referenced", {})[str(anchor)] = {
            "cost_per_unit_notional_traded": c,
            "sharpe_net_annualized": sh[headline_key],
            "dsr_by_n": {str(n): v for n, v in d.items()},
            "verdict": two_tier_verdict(d),
        }

    # Did the hedge actually neutralize the factor exposure? Regress the
    # hedged and unhedged strategy returns on the 6 factor-mimicking
    # portfolios estimated at the FINAL refit (an out-of-sample-ish check that
    # is independent of the internal route-A/route-B assertion).
    fit_last = _fit_factors_from_prior(common.to_numpy()[: len(common) - REFIT_EVERY_DAYS], K_FACTORS)
    if fit_last is not None:
        clean_all = np.nan_to_num(common.to_numpy(), nan=0.0)
        fmp_all = pd.DataFrame(
            clean_all @ (fit_last.loadings / fit_last.std[:, None]), index=common.index
        )
        neutrality: dict[str, Any] = {}
        for label, key2 in (("hedged", headline_key), ("unhedged", (HEADLINE_LOOKBACK, "unhedged"))):
            y = runs[key2].gross
            x = fmp_all.loc[y.index].to_numpy()
            design = np.column_stack([np.ones(len(x)), x])
            beta, *_ = np.linalg.lstsq(design, y.to_numpy(), rcond=None)
            fitted = design @ beta
            ss_res = float(((y.to_numpy() - fitted) ** 2).sum())
            ss_tot = float(((y.to_numpy() - y.mean()) ** 2).sum())
            neutrality[label] = {
                "r_squared_on_6_factor_mimicking_portfolios": 1.0 - ss_res / ss_tot,
                "abs_betas": [abs(float(b)) for b in beta[1:]],
            }
        payload["factor_neutrality_check"] = neutrality

    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps(payload["headline"], indent=2, default=str))
    print("\nspecs:")
    for k2, v in payload["specs"].items():
        print(
            f"  {k2:18s} gross SR {v['sharpe_gross_annualized']:+.4f}  net SR "
            f"{v['sharpe_net_annualized']:+.4f}  vol {v['vol_gross_annualized']:.4f}  "
            f"turn/yr net {v['annual_turnover_netted']:.2f} (leg {v['annual_turnover_tsmom_leg']:.2f}"
            f" hedge {v['annual_turnover_hedge_leg']:.2f})  cost/yr {v['annual_cost_pct_of_nav']:.4%}"
        )
    print("\nregime:", json.dumps(regime_block, indent=2, default=str))
    print("\ngross_up:", json.dumps(payload["gross_up"], indent=2, default=str))
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
