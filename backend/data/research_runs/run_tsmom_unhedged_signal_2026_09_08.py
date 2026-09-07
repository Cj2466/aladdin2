"""PLAIN UNHEDGED MOP (2012) TSMOM on the 31-instrument CME-SPAN futures panel,
evaluated as its OWN family.

READ tsmom_unhedged_signal_PREREGISTRATION_AND_DISCLOSURE.txt FIRST. This is
NOT a blind pre-registration: the headline spec's numbers (gross +0.8176 /
net +0.6796) were already computed and committed on main as the hedged
candidate's control leg, and that visibility is the reason this family exists.
The verdict here is consequently read from ladder rung 2 (N=37) at minimum,
NOT from n_local.

WHAT IS REUSED VERBATIM (nothing in app/services is modified by this work):
  app/services/research_lab/tsmom_signal.py            MOP Eq.(1) / Eq.(5)
  app/services/research_lab/tsmom_regime_definition.py pre-registered regime
  app/services/research_lab/dsr_policy_n.py            the {n_local,37,362,1031} ladder
  app/services/research_lab/deflated_sharpe.py         PSR / SR0 / DSR
  app/services/research_lab/preservation_score.py      mandatory secondary check
  app/services/research_lab/metrics.py                 sharpe_ratio

The data loading, the MOP signal construction, the turnover accounting and the
cost calibration below are lifted from the merged
run_tsmom_idiosyncratic_signal_2026_09_08.py (main f0cd8e1) with the hedging
branch removed, so the three unhedged specs must REPRODUCE main's numbers
exactly. That reproduction is asserted at the end of main(), not assumed.
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

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}")

from app.services.research_lab.deflated_sharpe import (
    compute_return_stats,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.dsr_policy_n import dsr_policy_denominators
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.research_lab.preservation_score import compute_preservation_metrics
from app.services.research_lab.tsmom_regime_definition import (
    classify_extreme_market_quarters,
)
from app.services.research_lab.tsmom_signal import (
    MOP_VOLATILITY_TARGET,
    ex_ante_volatility,
    trailing_return,
)

_REPO_ROOT = _BACKEND.parent
_WT = ("futures-span-full-pull", "backend", "data", "futures_daily", "cme_span", "continuous")
_CONTINUOUS_CANDIDATES = [
    _BACKEND / "data" / "futures_daily" / "cme_span" / "continuous",
    _REPO_ROOT / ".claude" / "worktrees" / Path(*_WT),
    _REPO_ROOT.parent.parent.parent / ".claude" / "worktrees" / Path(*_WT),
]
_MAIN_BACKEND = _REPO_ROOT.parent.parent.parent / "backend"
_SPY_CANDIDATES = [
    _BACKEND / "data" / "price_store" / "v1" / "SPY.csv.gz",
    _MAIN_BACKEND / "data" / "price_store" / "v1" / "SPY.csv.gz",
]

BURN_IN_DAYS = 504
REFIT_EVERY_DAYS = 21
GRID_LOOKBACK_BLOCKS = (1, 3, 12)
HEADLINE_LOOKBACK = 12

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
CL_CORRUPTED_DATES = ("2020-04-20", "2020-04-21")

#: The verdict rung declared in the disclosure document. n_local is reported
#: but is NOT the lenient tier for this family, because the headline spec was
#: selected after its result was already visible on main.
VERDICT_MIN_RUNG = 37
DSR_BAR = 0.95

#: Reproduction targets: main's committed numbers for the three unhedged legs
#: (tsmom_idiosyncratic_signal_2026-09-08.json -> specs). Asserted, not assumed.
MAIN_UNHEDGED_REFERENCE = {
    1: {"gross": 0.7654327732732809, "net": 0.3592903247301155},
    3: {"gross": 0.15668639907140605, "net": -0.10441460878676209},
    12: {"gross": 0.8176013928172485, "net": 0.6796489540062862},
}
MAIN_SIGMA_SR_6SPEC = 0.3376871178763641

OUT_TXT = _BACKEND / "data" / "research_runs" / "tsmom_unhedged_signal_2026-09-08.txt"
OUT_JSON = _BACKEND / "data" / "research_runs" / "tsmom_unhedged_signal_2026-09-08.json"


def continuous_dir() -> Path:
    for c in _CONTINUOUS_CANDIDATES:
        if c.exists():
            return c
    raise SystemExit(f"chained futures CSVs not found; looked in {_CONTINUOUS_CANDIDATES}")


def load_return_panel() -> pd.DataFrame:
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
            return (
                pd.Series(
                    frame[close_col].to_numpy(dtype=float),
                    index=pd.DatetimeIndex(pd.to_datetime(frame[date_col])),
                )
                .sort_index()
                .dropna()
            )
    raise SystemExit(f"SPY price store not found; looked in {_SPY_CANDIDATES}")


@dataclass
class StrategyRun:
    lookback_days: int
    rebalance_every: int
    dates: pd.DatetimeIndex
    gross: pd.Series
    turnover_at_boundary: pd.Series
    net_turnover: float
    mean_gross_notional: float


def build_strategy(
    panel: pd.DataFrame, lookback_days: int, rebalance_every: int = REFIT_EVERY_DAYS
) -> StrategyRun:
    """MOP (2012) diversified TSMOM, unhedged. Identical to main's
    build_strategy() with construction='unhedged' (the hedge branch there is a
    no-op: exposure=0, hedge=0, so w_net == w and route A == leg return)."""
    values = panel.to_numpy()
    n_obs, n_inst = values.shape
    dates = panel.index

    # MOP Eq. (1), p.233 -- strictly causal.
    sigma = pd.DataFrame(
        {c: ex_ante_volatility(panel[c]) for c in panel.columns}, index=dates
    ).to_numpy()
    # MOP Eq. (5)'s sign(r_{t-12,t}).
    signs = pd.DataFrame(
        {c: np.sign(trailing_return(panel[c], lookback_days)) for c in panel.columns}
    ).to_numpy()

    gross = np.full(n_obs, np.nan)
    turnover = np.zeros(n_obs)
    prev_w = np.zeros(n_inst)
    net_to = 0.0
    gross_notional: list[float] = []

    start = BURN_IN_DAYS
    while start < n_obs:
        stop = min(start + rebalance_every, n_obs)
        sign_row = signs[start - 1]
        sigma_row = sigma[start - 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            raw_size = MOP_VOLATILITY_TARGET / sigma_row
        usable = np.isfinite(sign_row) & np.isfinite(raw_size) & (sigma_row > 0)
        s_t = int(usable.sum())
        if s_t == 0:
            start = stop
            continue

        # MOP p.236: equal-weighted 1/S_t across available instruments.
        w = np.zeros(n_inst)
        w[usable] = sign_row[usable] * raw_size[usable] / s_t

        turnover[start] = float(np.abs(w - prev_w).sum())
        net_to += turnover[start]
        prev_w = w
        gross_notional.append(float(np.abs(w).sum()))

        clean = np.nan_to_num(values[start:stop], nan=0.0)
        gross[start:stop] = clean @ w
        start = stop

    mask = np.isfinite(gross)
    return StrategyRun(
        lookback_days=lookback_days,
        rebalance_every=rebalance_every,
        dates=dates[mask],
        gross=pd.Series(gross[mask], index=dates[mask]),
        turnover_at_boundary=pd.Series(turnover[mask], index=dates[mask]),
        net_turnover=net_to,
        mean_gross_notional=float(np.mean(gross_notional)) if gross_notional else float("nan"),
    )


def years_of(index: pd.DatetimeIndex) -> float:
    return len(index) / TRADING_DAYS_PER_YEAR


def solve_cost_per_unit(reference: StrategyRun, anchor_pct: float) -> float:
    """Turnover-matched calibration -- the CORRECTED one from main. The
    reference book is rebalanced WEEKLY, matching Hurst et al. Section 3.1's
    Friday-close rebalance. Back-solving from the 21-day book's lower turnover
    was the mistake caught last time; retained only as a labelled
    over-punitive sensitivity."""
    vol = float(reference.gross.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    target_annual_cost = anchor_pct * (vol / HOP_REFERENCE_VOLATILITY)
    annual_turnover = reference.net_turnover / years_of(reference.dates)
    if annual_turnover <= 0:
        raise SystemExit("reference leg has zero turnover; cannot calibrate a cost")
    return target_annual_cost / annual_turnover


def net_of_cost(run: StrategyRun, cost_per_unit: float) -> pd.Series:
    return run.gross - cost_per_unit * run.turnover_at_boundary


def dsr_by_denominator(
    returns: pd.Series, sharpe_ann: float, sigma_sr: float | None, denominators: list[int]
) -> dict[int, float | None]:
    stats = compute_return_stats(returns)
    out: dict[int, float | None] = {}
    for n in denominators:
        if stats is None or sigma_sr is None or not np.isfinite(sigma_sr):
            out[n] = None
            continue
        sr0_daily = expected_max_sharpe_under_noise(sigma_sr / np.sqrt(TRADING_DAYS_PER_YEAR), n)
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


def strict_verdict(dsr_map: dict[int, float | None], bar: float = DSR_BAR) -> str:
    """THE STRICTER RULE declared in the disclosure document, Section 1(d).

    Verdict is read from rung >= 37, NOT from n_local, because the headline
    spec was selected after its result was already visible. n_local is still
    computed and reported, but cannot rescue this family.
        fails at 37              -> DEFINITE_NEGATIVE
        passes 37, fails 1031    -> UNRESOLVED
        passes at 1031           -> PASS
    """
    rungs = sorted(n for n in dsr_map if n >= VERDICT_MIN_RUNG)
    if not rungs:
        return "UNCOMPUTABLE"
    lenient, conservative = dsr_map[rungs[0]], dsr_map[rungs[-1]]
    if lenient is None:
        return "UNCOMPUTABLE"
    if lenient < bar:
        return "DEFINITE_NEGATIVE"
    if conservative is not None and conservative >= bar:
        return "PASS"
    return "UNRESOLVED"


def naive_verdict(dsr_map: dict[int, float | None], bar: float = DSR_BAR) -> str:
    """CLAUDE.md's DEFAULT two-tier rule read at n_local -- reported ONLY so the
    difference against strict_verdict() is auditable. NOT this family's verdict."""
    ns = sorted(dsr_map)
    if not ns or dsr_map[ns[0]] is None:
        return "UNCOMPUTABLE"
    if dsr_map[ns[0]] < bar:
        return "DEFINITE_NEGATIVE"
    if dsr_map[ns[-1]] is not None and dsr_map[ns[-1]] >= bar:
        return "PASS"
    return "UNRESOLVED"


def main() -> None:
    panel_raw = load_return_panel()
    panel_masked = mask_cl_negative_price_dates(panel_raw)
    common = panel_masked.dropna(how="any")
    common_unmasked = panel_raw.dropna(how="any")

    runs = {
        lb: build_strategy(common, lb * REFIT_EVERY_DAYS) for lb in GRID_LOOKBACK_BLOCKS
    }

    # Cost calibration: bit-identical to main's -- the reference leg does not
    # depend on the spec grid, so c must match main's committed values.
    reference = build_strategy(common, 252, rebalance_every=5)
    reference_21d = runs[HEADLINE_LOOKBACK]
    cost_by_anchor = {
        a: solve_cost_per_unit(reference, a)
        for a in (HOP_COST_BAND_LOW, HOP_COST_BAND_MID, HOP_COST_BAND_HIGH)
    }
    cost_by_anchor_21d_ref = {
        a: solve_cost_per_unit(reference_21d, a)
        for a in (HOP_COST_BAND_LOW, HOP_COST_BAND_MID, HOP_COST_BAND_HIGH)
    }
    cost_mid = cost_by_anchor[HOP_COST_BAND_MID]

    net_mid = {lb: net_of_cost(r, cost_mid) for lb, r in runs.items()}
    sharpes_mid = {
        lb: float(sharpe_ratio(s, periods_per_year=TRADING_DAYS_PER_YEAR))
        for lb, s in net_mid.items()
    }
    gross_sharpes = {
        lb: float(sharpe_ratio(r.gross, periods_per_year=TRADING_DAYS_PER_YEAR))
        for lb, r in runs.items()
    }

    # --- REPRODUCTION ASSERTION against main's committed numbers ------------
    repro: dict[str, Any] = {}
    for lb, ref in MAIN_UNHEDGED_REFERENCE.items():
        dg = abs(gross_sharpes[lb] - ref["gross"])
        dn = abs(sharpes_mid[lb] - ref["net"])
        repro[f"lb{lb}"] = {
            "gross_here": gross_sharpes[lb],
            "gross_main": ref["gross"],
            "abs_diff_gross": dg,
            "net_here": sharpes_mid[lb],
            "net_main": ref["net"],
            "abs_diff_net": dn,
        }
        if dg > 1e-12 or dn > 1e-12:
            raise AssertionError(
                f"lb{lb} does NOT reproduce main: gross diff {dg:.3e}, net diff {dn:.3e}"
            )

    # --- sigma_SR: BOTH conventions, per the disclosure's declared judgment call
    sigma_sr_family = float(np.std(list(sharpes_mid.values()), ddof=1))  # 3 unhedged specs
    sigma_sr_main6 = MAIN_SIGMA_SR_6SPEC  # main's 6-spec value, for reproduction

    n_local_family = len(runs)  # 3
    denoms_family = dsr_policy_denominators(n_local_family)
    denoms_main6 = dsr_policy_denominators(6)

    headline_run = runs[HEADLINE_LOOKBACK]
    headline_net = net_mid[HEADLINE_LOOKBACK]
    headline_sr = sharpes_mid[HEADLINE_LOOKBACK]

    dsr_family = dsr_by_denominator(headline_net, headline_sr, sigma_sr_family, denoms_family)
    dsr_main6 = dsr_by_denominator(headline_net, headline_sr, sigma_sr_main6, denoms_main6)

    verdict_strict = strict_verdict(dsr_family)
    verdict_strict_main6 = strict_verdict(dsr_main6)
    verdict_naive = naive_verdict(dsr_family)

    preservation = compute_preservation_metrics(
        headline_net, dsr=dsr_family.get(n_local_family)
    ).as_dict()

    # --- regime split, pre-registered rule ----------------------------------
    regime = classify_extreme_market_quarters(load_spy_prices())
    day_labels = pd.Series(
        pd.PeriodIndex(headline_net.index, freq="Q").to_timestamp(how="end").normalize(),
        index=headline_net.index,
    )
    lookup = {k.normalize(): v for k, v in regime.labels.items()}
    day_regime = day_labels.map(lambda d: lookup.get(d, "unclassified"))

    regime_block: dict[str, Any] = {}
    for label in ("extreme", "normal"):
        subset_idx = day_regime[day_regime == label].index
        sub_sharpes = {
            lb: float(
                sharpe_ratio(
                    s.loc[s.index.intersection(subset_idx)],
                    periods_per_year=TRADING_DAYS_PER_YEAR,
                )
            )
            for lb, s in net_mid.items()
        }
        sub_sigma = float(np.std(list(sub_sharpes.values()), ddof=1))
        sub = headline_net.loc[headline_net.index.intersection(subset_idx)]
        sub_dsr = dsr_by_denominator(
            sub, sub_sharpes[HEADLINE_LOOKBACK], sub_sigma, denoms_family
        )
        regime_block[label] = {
            "n_days": len(sub),
            "sharpe_net_annualized": sub_sharpes[HEADLINE_LOOKBACK],
            "sigma_sr_annualized": sub_sigma,
            "dsr_by_n": {str(n): v for n, v in sub_dsr.items()},
            "verdict_strict_from_37": strict_verdict(sub_dsr),
            "verdict_naive_at_n_local": naive_verdict(sub_dsr),
        }

    unmasked_run = build_strategy(common_unmasked, HEADLINE_LOOKBACK * REFIT_EVERY_DAYS)
    unmasked_net = net_of_cost(unmasked_run, cost_mid)

    payload: dict[str, Any] = {
        "schema": "tsmom_unhedged_signal/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "preregistration_and_disclosure": (
            "data/research_runs/tsmom_unhedged_signal_PREREGISTRATION_AND_DISCLOSURE.txt"
        ),
        "LOOK_AHEAD_DISCLOSURE": {
            "is_blind_preregistration": False,
            "what_was_already_seen": (
                "The headline spec (12-block unhedged) scored gross +0.8176 / net +0.6796 in "
                "the merged prior task (main f0cd8e1), where it was built only as the "
                "factor-hedged candidate's control leg. Those numbers were committed and read "
                "before this family was proposed."
            ),
            "why_this_family_exists": (
                "Precisely BECAUSE that already-visible number looked good. The spec was "
                "selected after its result was known; this is a second-look confirmation, not "
                "a fresh test."
            ),
            "statistical_consequence": (
                "n_local encodes 'small honest self-contained search'. That assumption is FALSE "
                "here: the spec is a hand-picked maximum from a multi-day search over this same "
                "panel. n_local is reported for completeness but is NOT the lenient tier."
            ),
            "verdict_rung_declared_in_advance": VERDICT_MIN_RUNG,
            "reading_rule": (
                "Credible verdict read from N=37 at minimum; only survival at 362 or 1031 is "
                "suggestive of a real edge. Strictly harsher than CLAUDE.md's default rule."
            ),
            "broader_multiple_testing_note": (
                "This look adds 3 unhedged specs (plus the weekly calibration reference leg) as "
                "trials against the same futures panel; the project's 1031-trial pool grows "
                "accordingly. No rung value is edited by this family -- editing the denominator "
                "in the task that reports a result against it would be circular. Standing "
                "instruction unchanged: regenerate via run_dsr_policy_n.py --stage all once "
                "~100 more trials accumulate."
            ),
        },
        "INHERITED_FAILED_GATE": {
            "gate": "pre-declared effective-breadth floor for the TSMOM universe",
            "floor": 15,
            "measured_raw_universe": 10.0081,
            "status": "FAIL",
            "source": "main da504d2 / project_tsmom_breadth_gate_failed_2026-09-07",
            "note": (
                "This family trades the RAW panel and has NONE of the hedged family's "
                "residualization argument (which was itself ruled UNRESOLVED). A DSR pass would "
                "not clear this gate; it would leave two findings in conflict. Lowering the "
                "floor for this family is explicitly the move the pre-declaration exists to "
                "prevent and is NOT proposed."
            ),
        },
        "panel": {
            "source": str(continuous_dir()),
            "n_instruments": int(common.shape[1]),
            "instruments": list(common.columns),
            "raw_panel_first": str(panel_raw.index.min().date()),
            "raw_panel_last": str(panel_raw.index.max().date()),
            "common_window_first": str(common.index.min().date()),
            "common_window_last": str(common.index.max().date()),
            "common_window_n_obs": int(common.shape[0]),
            "cl_dates_masked": list(CL_CORRUPTED_DATES),
            "date_note": (
                "The task brief said 2013-01-02..2025-09-12; that is the RAW span. The COMMON "
                "window (dropna how=any across 31 instruments) starts 2017-07-10, and after the "
                "504-day burn-in the strategy series starts 2019-06-18 (1623 days, ~6.4 years). "
                "The shorter window is what the prior work actually used and what is reused."
            ),
        },
        "construction": {
            "burn_in_days": BURN_IN_DAYS,
            "refit_every_days": REFIT_EVERY_DAYS,
            "volatility_target": MOP_VOLATILITY_TARGET,
            "hedging": "NONE -- plain MOP diversified TSMOM",
            "n_local_family": n_local_family,
            "denominators_family": denoms_family,
            "denominators_main6": denoms_main6,
            "sigma_sr_family_3spec": sigma_sr_family,
            "sigma_sr_main_6spec": sigma_sr_main6,
            "sigma_sr_note": (
                "JUDGMENT CALL, declared in advance: as its own family the grid is 3 unhedged "
                "specs (sigma_SR over those 3); main used 6 specs. Both are reported. Neither "
                "is the verdict rung, which is why the ambiguity is left standing rather than "
                "resolved toward whichever is more favourable."
            ),
        },
        "mechanism_fidelity": {
            "MOP_faithful": True,
            "statement": (
                "This construction is MOP (2012) Eq.(1) ex-ante volatility and Eq.(5) "
                "sign(r_{t-12,t}) at the 40% volatility target with 1/S_t equal weighting "
                "(p.236). The hedged family's single biggest deviation -- subtracting estimated "
                "common-factor exposure and hedging it in factor-mimicking portfolios -- does "
                "NOT apply here. That is a genuine point in this family's favour."
            ),
            "inherited_deviations": [
                {
                    "deviation": "Calendar front-month roll rule, not MOP's own convention.",
                    "disclosed_in": "main da504d2",
                    "applies_here": True,
                },
                {
                    "deviation": (
                        "CL settled at -37.63 on 2020-04-20; the ratio return convention emits "
                        "artifacts on 2020-04-20/21, which are masked. Reported unmasked as a "
                        "sensitivity."
                    ),
                    "disclosed_in": "main b8880c8",
                    "applies_here": True,
                },
            ],
        },
        "cost_model": {
            "citation": HOP_CITATION,
            "anchors_annual_pct_of_nav_at_10pct_vol": {
                "low": HOP_COST_BAND_LOW,
                "mid": HOP_COST_BAND_MID,
                "high": HOP_COST_BAND_HIGH,
            },
            "cost_per_unit_notional_traded": {str(k): v for k, v in cost_by_anchor.items()},
            "reference_leg": (
                "252-day lookback, unhedged, rebalanced WEEKLY (turnover-matched to Hurst et "
                "al. Section 3.1's Friday-close weekly rebalance) -- the CORRECTED calibration"
            ),
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
        "reproduction_of_main": {
            "note": (
                "The three unhedged specs must reproduce main f0cd8e1's committed numbers "
                "exactly; asserted at 1e-12 in code, not assumed."
            ),
            "specs": repro,
        },
        "specs": {},
        "headline": {
            "lookback_blocks": HEADLINE_LOOKBACK,
            "construction": "unhedged",
            "cost_anchor": HOP_COST_BAND_MID,
            "n_days": len(headline_net),
            "first_day": str(headline_net.index.min().date()),
            "last_day": str(headline_net.index.max().date()),
            "sharpe_gross_annualized": gross_sharpes[HEADLINE_LOOKBACK],
            "sharpe_net_annualized": headline_sr,
            "dsr_by_n_family_sigma": {str(n): v for n, v in dsr_family.items()},
            "dsr_by_n_main6_sigma": {str(n): v for n, v in dsr_main6.items()},
            "VERDICT": verdict_strict,
            "verdict_basis": (
                f"strict reading, lenient tier = N={VERDICT_MIN_RUNG} (look-ahead adjusted)"
            ),
            "verdict_strict_main6_sigma": verdict_strict_main6,
            "verdict_if_naively_read_at_n_local": verdict_naive,
            "preservation": preservation,
        },
        "regime_conditional": {
            "rule": regime.rule_name,
            "module": "app/services/research_lab/tsmom_regime_definition.py",
            "note": (
                "MOP's crisis-alpha claim is explicitly conditional, so CLAUDE.md requires this "
                "split. The UNHEDGED leg is the construction that should show crisis alpha if "
                "it is real -- the hedged family removed it by design."
            ),
            "n_unclassified_days": int((day_regime == "unclassified").sum()),
            **regime_block,
        },
        "sensitivity": {
            "cl_unmasked": {
                "n_days": len(unmasked_net),
                "sharpe_net_annualized": float(
                    sharpe_ratio(unmasked_net, periods_per_year=TRADING_DAYS_PER_YEAR)
                ),
            },
            "cost_anchor_sweep": {},
            "overpunitive_21day_referenced": {},
        },
    }

    for lb, run in runs.items():
        payload["specs"][f"lb{lb}_unhedged"] = {
            "lookback_blocks": lb,
            "construction": "unhedged",
            "n_days": len(run.gross),
            "sharpe_gross_annualized": gross_sharpes[lb],
            "sharpe_net_annualized": sharpes_mid[lb],
            "vol_gross_annualized": float(
                run.gross.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
            ),
            "annual_turnover_netted": run.net_turnover / years_of(run.dates),
            "mean_gross_notional": run.mean_gross_notional,
            "annual_cost_pct_of_nav": cost_mid * run.net_turnover / years_of(run.dates),
        }

    for anchor, c in cost_by_anchor.items():
        sh = {
            lb: float(sharpe_ratio(net_of_cost(r, c), periods_per_year=TRADING_DAYS_PER_YEAR))
            for lb, r in runs.items()
        }
        sig = float(np.std(list(sh.values()), ddof=1))
        d = dsr_by_denominator(net_of_cost(headline_run, c), sh[HEADLINE_LOOKBACK], sig, denoms_family)
        payload["sensitivity"]["cost_anchor_sweep"][str(anchor)] = {
            "cost_per_unit_notional_traded": c,
            "sharpe_net_annualized": sh[HEADLINE_LOOKBACK],
            "dsr_by_n": {str(n): v for n, v in d.items()},
            "verdict_strict_from_37": strict_verdict(d),
            "verdict_naive_at_n_local": naive_verdict(d),
        }

    for anchor, c in cost_by_anchor_21d_ref.items():
        sh = {
            lb: float(sharpe_ratio(net_of_cost(r, c), periods_per_year=TRADING_DAYS_PER_YEAR))
            for lb, r in runs.items()
        }
        sig = float(np.std(list(sh.values()), ddof=1))
        d = dsr_by_denominator(net_of_cost(headline_run, c), sh[HEADLINE_LOOKBACK], sig, denoms_family)
        payload["sensitivity"]["overpunitive_21day_referenced"][str(anchor)] = {
            "cost_per_unit_notional_traded": c,
            "sharpe_net_annualized": sh[HEADLINE_LOOKBACK],
            "dsr_by_n": {str(n): v for n, v in d.items()},
            "verdict_strict_from_37": strict_verdict(d),
        }

    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    write_report(payload)
    print(json.dumps(payload["headline"], indent=2, default=str))
    print(f"\nwrote {OUT_JSON}\nwrote {OUT_TXT}")


def write_report(p: dict[str, Any]) -> None:
    h = p["headline"]
    L = p["LOOK_AHEAD_DISCLOSURE"]
    g = p["INHERITED_FAILED_GATE"]
    lines: list[str] = []
    A = lines.append
    A("=" * 80)
    A("PLAIN UNHEDGED MOP (2012) TSMOM -- 31-INSTRUMENT CME FUTURES PANEL")
    A("Evaluated as its own family. Generated " + p["generated_at"])
    A("=" * 80)
    A("")
    A("!" * 80)
    A("SECTION 0 -- THIS IS NOT A BLIND PRE-REGISTRATION")
    A("!" * 80)
    A(L["what_was_already_seen"])
    A("")
    A("WHY THIS FAMILY EXISTS: " + L["why_this_family_exists"])
    A("")
    A("STATISTICAL CONSEQUENCE: " + L["statistical_consequence"])
    A("")
    A(f"VERDICT RUNG DECLARED IN ADVANCE: N >= {L['verdict_rung_declared_in_advance']}")
    A("READING RULE: " + L["reading_rule"])
    A("")
    A("BROADER MULTIPLE-TESTING ACCOUNTING: " + L["broader_multiple_testing_note"])
    A("")
    A("-" * 80)
    A("SECOND, INDEPENDENT STRIKE: A PRE-DECLARED GATE THIS FAMILY ALREADY FAILS")
    A("-" * 80)
    A(f"  {g['gate']}")
    A(f"  floor {g['floor']}   measured (raw universe) {g['measured_raw_universe']}   {g['status']}")
    A(f"  source: {g['source']}")
    A(f"  {g['note']}")
    A("")
    A("-" * 80)
    A("DATA")
    A("-" * 80)
    A(f"  instruments            {p['panel']['n_instruments']}")
    A(f"  raw panel span         {p['panel']['raw_panel_first']} .. {p['panel']['raw_panel_last']}")
    A(
        f"  common window          {p['panel']['common_window_first']} .. "
        f"{p['panel']['common_window_last']}  ({p['panel']['common_window_n_obs']} obs)"
    )
    A(f"  strategy series        {h['first_day']} .. {h['last_day']}  ({h['n_days']} days)")
    A(f"  NOTE: {p['panel']['date_note']}")
    A("")
    A("-" * 80)
    A("MECHANISM FIDELITY")
    A("-" * 80)
    A(f"  MOP-faithful: {p['mechanism_fidelity']['MOP_faithful']}")
    A(f"  {p['mechanism_fidelity']['statement']}")
    A("  Inherited deviations, re-cited because this family inherits them:")
    for d in p["mechanism_fidelity"]["inherited_deviations"]:
        A(f"    - {d['deviation']}  [{d['disclosed_in']}]")
    A("")
    A("-" * 80)
    A("REPRODUCTION OF MAIN (asserted at 1e-12, not assumed)")
    A("-" * 80)
    for k, v in p["reproduction_of_main"]["specs"].items():
        A(
            f"  {k:6s} gross {v['gross_here']:+.10f} vs main {v['gross_main']:+.10f} "
            f"(d={v['abs_diff_gross']:.2e})"
        )
        A(
            f"  {'':6s} net   {v['net_here']:+.10f} vs main {v['net_main']:+.10f} "
            f"(d={v['abs_diff_net']:.2e})"
        )
    A("")
    A("-" * 80)
    A("SPECS (cost anchor 2.5%/yr)")
    A("-" * 80)
    for k, v in p["specs"].items():
        A(
            f"  {k:16s} gross SR {v['sharpe_gross_annualized']:+.4f}  net SR "
            f"{v['sharpe_net_annualized']:+.4f}  vol {v['vol_gross_annualized']:.4f}  "
            f"turn/yr {v['annual_turnover_netted']:.2f}  cost/yr {v['annual_cost_pct_of_nav']:.4%}"
        )
    A("")
    A(f"  sigma_SR (3-spec, this family) {p['construction']['sigma_sr_family_3spec']:.10f}")
    A(f"  sigma_SR (6-spec, main's)      {p['construction']['sigma_sr_main_6spec']:.10f}")
    A(f"  {p['construction']['sigma_sr_note']}")
    A("")
    A("-" * 80)
    A("HEADLINE: 12-block unhedged, 2.5%/yr cost anchor")
    A("-" * 80)
    A(f"  gross Sharpe (annualized)  {h['sharpe_gross_annualized']:+.4f}")
    A(f"  net   Sharpe (annualized)  {h['sharpe_net_annualized']:+.4f}")
    A("")
    A("  DSR ACROSS THE FULL LADDER (bar 0.95):")
    A("    using this family's own 3-spec sigma_SR:")
    for n, v in h["dsr_by_n_family_sigma"].items():
        mark = "   <- reported, NOT the verdict rung (look-ahead)" if int(n) < VERDICT_MIN_RUNG else ""
        A(f"      N={n:>5s}  DSR {float(v):.6f}{mark}")
    A("    using main's 6-spec sigma_SR (reproduction cross-check):")
    for n, v in h["dsr_by_n_main6_sigma"].items():
        A(f"      N={n:>5s}  DSR {float(v):.6f}")
    A("")
    A(f"  VERDICT (strict, from N=37):            {h['VERDICT']}")
    A(f"  verdict on main's 6-spec sigma:         {h['verdict_strict_main6_sigma']}")
    A(f"  (naive n_local reading, NOT adopted):   {h['verdict_if_naively_read_at_n_local']}")
    A("")
    A("-" * 80)
    A("PRESERVATION SCORE (mandatory, no exceptions)")
    A("-" * 80)
    for k, v in h["preservation"].items():
        A(f"  {k:28s} {v}")
    A("")
    A("-" * 80)
    A("REGIME-CONDITIONAL SPLIT (pre-registered rule, d9b1f96)")
    A("-" * 80)
    A(f"  rule: {p['regime_conditional']['rule']}")
    A(f"  {p['regime_conditional']['note']}")
    A(f"  unclassified days: {p['regime_conditional']['n_unclassified_days']}")
    for label in ("extreme", "normal"):
        b = p["regime_conditional"][label]
        A(
            f"  {label:8s} n={b['n_days']:5d}  net SR {b['sharpe_net_annualized']:+.4f}  "
            f"verdict(strict) {b['verdict_strict_from_37']}"
        )
        A(f"           DSR: {b['dsr_by_n']}")
    A("")
    A("-" * 80)
    A("SENSITIVITIES")
    A("-" * 80)
    A("  cost anchor sweep (corrected weekly-referenced calibration):")
    for a, v in p["sensitivity"]["cost_anchor_sweep"].items():
        A(
            f"    anchor {float(a):.1%}  net SR {v['sharpe_net_annualized']:+.4f}  "
            f"verdict(strict) {v['verdict_strict_from_37']}   DSR@37 "
            f"{v['dsr_by_n']['37']}"
        )
    A("  over-punitive 21-day-referenced calibration (the mistake caught last time,")
    A("  retained only as a labelled sensitivity):")
    for a, v in p["sensitivity"]["overpunitive_21day_referenced"].items():
        A(
            f"    anchor {float(a):.1%}  net SR {v['sharpe_net_annualized']:+.4f}  "
            f"verdict(strict) {v['verdict_strict_from_37']}"
        )
    cu = p["sensitivity"]["cl_unmasked"]
    A(f"  CL unmasked: net SR {cu['sharpe_net_annualized']:+.4f} over {cu['n_days']} days")
    A("")
    A("=" * 80)
    A("NOT DONE (CLAUDE.md rule 6 -- recommend only): no registration, no tracker")
    A("entry, no live/forward-validation status change, no push, no merge.")
    A("=" * 80)
    OUT_TXT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
