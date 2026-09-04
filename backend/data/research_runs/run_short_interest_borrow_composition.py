"""WHAT DOES short_interest ACTUALLY SHORT, AND WHAT DOES BORROWING IT COST?

MEASUREMENT ONLY. Nothing here writes a registration row, a config, a status
or a DB trial row. The output is two committed files and a number for the repo
owner to decide on, exactly as b492394 did for lazy_prices.

WHY THIS FAMILY, AND WHY IT IS NOT THE SAME QUESTION lazy_prices ANSWERED
========================================================================
borrow_cost.py names this family, by name, as where the standing 0.0 borrow
assumption "bites hardest":

    "It bites hardest exactly where it matters most -- short_interest's
     long_short specs short the MOST heavily shorted names in the index,
     which is where borrow is expensive, and charge them nothing."

and the family's own pre-registration says the same thing in its own words
(cross_sectional_short_interest.py, COSTS paragraph): "The long_universe_
hedged specs short a broad index-like basket, which is genuinely cheap to
borrow; the long_short specs short the MOST heavily shorted names in the
index, which is exactly the population where borrow is expensive."

Read those two sentences together and the headline of this run is already
visible in the source, before any data: THE SENTENCE IS ABOUT THE long_short
SPECS, AND THE REGISTERED SPEC IS NOT ONE OF THEM. si_ratio_hedged_h21 is a
long_universe_hedged spec. Its short side is the equal-weighted WHOLE
eligible universe (cross_sectional._target_weights: "nets a long leg against
an equal-weighted short of the WHOLE eligible universe"), not the top of the
short-interest ranking. So "bites hardest" is true of six specs this family
screened and did not register, and the live registration is a different
book from the one that sentence describes.

That is a real finding rather than a technicality, and it is exactly the
shape of mistake the lazy_prices measurement already caught once in the
other direction (a leg assumed cheap that the schedule charges 113bp/yr).
Both directions are measured below rather than argued.

THE THREE QUESTIONS, all answered with measurements
===================================================
  Q1  What share of each spec's REALIZED short side sits in borrow_cost's
      hard-to-borrow tails, against the 20% a book drawn independently of
      short interest holds by construction?
  Q2  What does borrow_cost's OWN schedule charge that side, and what
      scalar financing_bps_per_year does that imply for THIS book?
  Q3  What would paying it do to the registered spec's Sharpe and DSR?

THE ARITHMETIC FOR A HEDGED BOOK, WHICH IS NOT B/2
==================================================
borrow_cost.financing_bps_for_long_short_book(B) returns B/2, and its own
docstring says why that is wrong here:

    "NOT valid for a long_universe_hedged book, whose short leg is a broad
     index-like basket rather than a ranked leg"

B/2 is exact for a long_short book because gross notional is 2.0 (1.0 long +
1.0 short) so half the rate on gross 2.0 is the full rate on the 1.0 short
leg. A hedged book's gross is NOT 2.0: the long names are also members of
the universe being shorted, so their NET weight is (long weight - 1/N) and
the long and short sides partially cancel. cross_sectional.py computes the
financing base as sum(|net weight|), so this script computes, per formation,

    charge_bps  = sum over names with NET weight < 0 of |net_w| * rate(name)
    implied financing_bps_per_year = charge_bps / gross_notional_held

which is the scalar that makes the harness accrue exactly the borrow the
schedule says those short positions owe. For a long_short spec this reduces
to B/2 identically, and the run asserts that it does rather than assuming it.

Charging only NET-short names is the economically right answer, not a
convenience: a name the book is net long is not borrowed, and the hedged
book's long leg is the LOWEST-short-interest 5% -- i.e. it removes part of
the low tail from the short side, which pushes the measured tail share below
the 20% no-tilt baseline rather than above it. Measured, not asserted.

THE PERCENTILE IS ALWAYS TAKEN ON THE SHORT-INTEREST RATIO PANEL
================================================================
Including for the days_to_cover specs. borrow_cost's schedule is keyed on
"cross-sectional SHORT-INTEREST percentile" -- D'Avolio's Fig. 1 is short-
interest deciles and Beneish/Lee/Nichols' U-shape is in SIR -- so the
ranking variable a spec happens to sort on does not change which names are
expensive to borrow. Using each spec's own panel would silently redefine the
schedule for half the family.

DATA, BY THE FAMILY'S OWN FUNCTIONS, AND ITS HONEST LIMITS
==========================================================
The short-interest ratio panel is built by FinraShortInterestProvider,
SecSharesOutstandingProvider, build_point_in_time_share_count_frame and
build_short_interest_panels -- the family's own production path, the same
one run_short_interest_screening calls -- so its point-in-time contract
applies unchanged. The universe, formation cadence and eligibility come from
the harness itself via form_portfolio(), the exact function a live tick
calls, rather than from a re-derivation here.

REPRODUCIBILITY, STATED NOT ASSUMED. fa614ac diagnosed this family's
mid-split price freeze and section 8 of its module docstring records FOUR
different si_ratio_hedged_h21 Sharpes from four runs of the same code. This
script does what that section prescribes: ONE price fetch, held in memory,
handed to every arm as price_frames, so the before/after comparison is
exact regardless of what the absolute level reproduces to on another day.
The absolute numbers are compared against section 8's pinned reproducible
figure (+0.42004211 / DSR 0.77457982) and any gap is REPORTED, not silently
absorbed.

    ./venv/bin/python data/research_runs/run_short_interest_borrow_composition.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# resolves `app` to the MAIN worktree's backend/app. Without the two lines
# below, this runner silently measures main's code instead of this branch's --
# and for a module that exists in both, with NO error at all.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The measurement would have used another checkout's code."
    )

from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.finra_short_interest_provider import (
    FinraShortInterestProvider,
)
from app.services.market_data.sec_shares_outstanding_provider import (
    SecSharesOutstandingProvider,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.borrow_cost import (
    DEFAULT_SCHEDULE,
    GENERAL_COLLATERAL_BPS_PER_YEAR,
    HARD_TO_BORROW_BPS_PER_YEAR,
    cross_sectional_percentiles,
    financing_bps_for_long_short_book,
)
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    form_portfolio,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_forward_registry import (
    config_fingerprint,
    config_identity,
)
from app.services.research_lab.cross_sectional_short_interest import (
    SHARES_MAX_STALENESS_DAYS,
    SHORT_INTEREST_CYCLE_FETCH_START,
    SHORT_INTEREST_FORMATION_START,
    SHORT_INTEREST_N_TRIALS,
    SHORT_INTEREST_PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    build_point_in_time_share_count_frame,
    build_short_interest_family,
    build_short_interest_panels,
    default_short_interest_config,
    run_short_interest_screening,
)
from app.services.research_lab.deflated_sharpe import (
    MIN_TRIALS_FOR_DSR,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.preservation_score import (
    compute_preservation_metrics,
)
from app.services.research_lab.sp500_membership_history import (
    get_universe_over,
    was_member,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("si_borrow")

RUN_DATE = "2026-09-05"
START = SHORT_INTEREST_FORMATION_START  # 2018-01-12
END = date(2026, 9, 1)  # the registration window's end, per section 8
REGISTERED_SPEC_ID = "si_ratio_hedged_h21"

OUT_JSON = _BACKEND / "data" / "research_runs" / f"short_interest_borrow_composition_{RUN_DATE}.json"
OUT_TXT = _BACKEND / "data" / "research_runs" / f"short_interest_borrow_composition_{RUN_DATE}.txt"

# Section 8's pinned, independently-reproduced backward figure for the
# registered spec. Carried so this run can SHOW its gap against it rather than
# quietly presenting its own number as the family's.
SECTION_8_PINNED_SHARPE = 0.42004211
SECTION_8_PINNED_DSR = 0.77457982
# The registration's own documented figures (section 7), left as written.
REGISTRATION_DOCUMENTED_SHARPE = 0.4531
REGISTRATION_DOCUMENTED_DSR = 0.7962107673459036

# The no-tilt reference, computed from the schedule rather than hardcoded: a
# short side drawn independently of short interest holds one tail decile at
# each end, i.e. 2 * tail_fraction of its notional at the specials rate.
NO_TILT_TAIL_SHARE = 2.0 * DEFAULT_SCHEDULE.tail_fraction
NO_TILT_BPS = (
    NO_TILT_TAIL_SHARE * HARD_TO_BORROW_BPS_PER_YEAR
    + (1.0 - NO_TILT_TAIL_SHARE) * GENERAL_COLLATERAL_BPS_PER_YEAR
)

# The DSR denominators every figure is reported at, matching the convention
# lazy_prices' switch report used (family grid / clustered matrix / raw pooled
# distinct trials). Read from the committed pooled-N artifact where possible so
# this table cannot go stale against it.
LOCAL_N = SHORT_INTEREST_N_TRIALS  # 12


def _pooled_denominators() -> list[int]:
    cfg_path = _BACKEND / "app" / "services" / "research_lab" / "global_effective_n.json"
    out = [LOCAL_N]
    try:
        cfg = json.loads(cfg_path.read_text())
    except (OSError, ValueError):
        return out
    for key in ("n_specs_clustered", "raw_pooled_distinct_trials"):
        value = int(cfg.get(key, 0))
        if value > LOCAL_N and value not in out:
            out.append(value)
    return out


# ---------------------------------------------------------------------------
# COMPOSITION
# ---------------------------------------------------------------------------


def measure_spec_composition(
    data: CrossSectionalData,
    spec: Any,
    config: CrossSectionalConfig,
    ratio_frame: pd.DataFrame,
) -> dict[str, Any]:
    """One spec's realized short side, formation by formation.

    The formations come from form_portfolio() -- the harness's OWN formation
    function, the one a live tick calls -- replayed at the same positions
    run_cross_sectional_backtest walks. prev_weights is passed as {} because
    it feeds ONLY turnover (see form_portfolio), and nothing here reads
    turnover; net_weights and gross_notional_held do not depend on it."""
    index = data.close.index
    n = len(index)
    first_formation = spec.lookback_days
    eligible_positions = np.flatnonzero(index.date >= config.formation_start)  # type: ignore[attr-defined]
    if len(eligible_positions) == 0:
        raise SystemExit(f"{spec.pattern_id}: no position at or after {config.formation_start}")
    first_formation = max(first_formation, int(eligible_positions[0]))
    assert spec.cohort_formation_days is None, (
        f"{spec.pattern_id} sets cohort_formation_days; this walk assumes the single-sleeve "
        "cadence the short-interest family asserts for every one of its specs."
    )

    lo, hi = DEFAULT_SCHEDULE.tail_fraction, 1.0 - DEFAULT_SCHEDULE.tail_fraction
    per_formation: list[dict[str, Any]] = []
    for i in range(first_formation, n - 1, spec.holding_days):
        outcome = form_portfolio(data, spec, config, was_member, i, {})
        record = outcome.record
        row: dict[str, Any] = {
            "date": record.date.date().isoformat(),
            "n_eligible": record.n_eligible,
            "n_long": len(record.long_tickers),
            "skipped_reason": record.skipped_reason,
            "gross_notional_held": outcome.gross_notional_held,
        }
        if record.skipped_reason is not None or not outcome.net_weights:
            row["sir_covered"] = False
            per_formation.append(row)
            continue

        # THE FULL ELIGIBLE CROSS-SECTION this formation faced -- not the two
        # legs. Percentiles must be taken against everything the formation
        # could have ranked, or a long_short spec's short leg would be ranked
        # only against itself and its own long leg, which is not a
        # cross-sectional percentile at all and would report ~1.0 tail share
        # for any leg whatsoever.
        #
        # Reproduced from form_portfolio's own eligibility line (member on the
        # formation date AND a finite close on it) and then CHECKED against
        # the FormationRecord's own n_eligible, so this is a verified copy
        # rather than an assumed-equivalent one. FormationOutcome does not
        # expose the list, only the count.
        formation_close = data.close.iloc[i]
        eligible = [
            t
            for t in data.close.columns
            if was_member(t, record.date.date()) and np.isfinite(formation_close[t])
        ]
        assert len(eligible) == record.n_eligible, (
            f"{spec.pattern_id} @ {record.date.date()}: re-derived {len(eligible)} eligible names "
            f"but the harness recorded {record.n_eligible} — the eligibility rule copied here has "
            "drifted from form_portfolio's."
        )
        # Restricted to names carrying a short-interest RATIO on that date.
        # Percentiles are taken WITHIN this universe -- the same convention the
        # lazy_prices measurement used, and conservative for the same reason
        # (D'Avolio p.273: S&P 500 constituents "are almost always general
        # collateral", so the top decile of this panel holds far fewer true
        # specials than the market-wide decile his fee schedule was measured
        # on).
        sir_row = ratio_frame.loc[record.date] if record.date in ratio_frame.index else None
        cross_section = (
            pd.Series(dtype=float) if sir_row is None else sir_row.reindex(eligible).dropna()
        )
        if len(cross_section) < 20:
            row["sir_covered"] = False
            row["n_cross_section"] = len(cross_section)
            per_formation.append(row)
            continue

        pct = cross_sectional_percentiles(cross_section)
        net = pd.Series(outcome.net_weights, dtype=float)
        short_side = net[net < 0.0]
        short_notional = float(-short_side.sum())
        if short_notional <= 0.0:
            row["sir_covered"] = False
            per_formation.append(row)
            continue

        short_pct = pct.reindex(short_side.index)
        rates = DEFAULT_SCHEDULE.rate_for_percentiles(short_pct)
        weights = -short_side  # positive borrowed notional per name
        charge_bps = float((weights * rates).sum())

        measured = short_pct.dropna()
        measured_w = weights.reindex(measured.index)
        is_tail = (measured <= lo) | (measured >= hi)
        long_pct = pct.reindex(list(record.long_tickers)).dropna()

        row.update(
            {
                "sir_covered": True,
                "n_cross_section": len(cross_section),
                "n_short_names": len(short_side),
                "n_short_with_sir": len(measured),
                "short_sir_coverage_by_notional": float(measured_w.sum() / short_notional),
                "short_notional": short_notional,
                # Composition of the short side. Notional-weighted is the one
                # that drives the charge; equal-weighted is reported beside it
                # because that is the number the lazy_prices report quoted and
                # the two must be comparable.
                "short_tail_share_notional": float(
                    (measured_w[is_tail].sum() / measured_w.sum()) if measured_w.sum() else np.nan
                ),
                "short_tail_share_equal": float(is_tail.mean()) if len(measured) else np.nan,
                "short_high_tail_share_equal": (
                    float((measured >= hi).mean()) if len(measured) else np.nan
                ),
                "short_low_tail_share_equal": (
                    float((measured <= lo).mean()) if len(measured) else np.nan
                ),
                "short_median_sir_pct": float(measured.median()) if len(measured) else np.nan,
                "long_tail_share_equal": (
                    float(((long_pct <= lo) | (long_pct >= hi)).mean()) if len(long_pct) else np.nan
                ),
                "long_median_sir_pct": float(long_pct.median()) if len(long_pct) else np.nan,
                # THE TWO NUMBERS THIS RUN EXISTS FOR.
                "book_bps_on_short_side": charge_bps / short_notional,
                "implied_financing_bps_per_year": charge_bps / outcome.gross_notional_held,
            }
        )
        per_formation.append(row)

    covered = [r for r in per_formation if r.get("sir_covered")]
    if not covered:
        return {"spec_id": spec.pattern_id, "n_formations": len(per_formation),
                "n_formations_sir_covered": 0, "per_formation": per_formation}

    def agg(key: str) -> dict[str, float]:
        values = [r[key] for r in covered if r.get(key) is not None and np.isfinite(r[key])]
        return {
            "n": len(values),
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
        }

    return {
        "spec_id": spec.pattern_id,
        "portfolio": spec.portfolio,
        "holding_days": spec.holding_days,
        "n_formations": len(per_formation),
        "n_formations_formed": sum(1 for r in per_formation if r.get("skipped_reason") is None),
        "n_formations_sir_covered": len(covered),
        "gross_notional_held": agg("gross_notional_held"),
        "short_tail_share_notional": agg("short_tail_share_notional"),
        "short_tail_share_equal": agg("short_tail_share_equal"),
        "short_high_tail_share_equal": agg("short_high_tail_share_equal"),
        "short_low_tail_share_equal": agg("short_low_tail_share_equal"),
        "long_tail_share_equal": agg("long_tail_share_equal"),
        "short_median_sir_pct": agg("short_median_sir_pct"),
        "long_median_sir_pct": agg("long_median_sir_pct"),
        "short_sir_coverage_by_notional": agg("short_sir_coverage_by_notional"),
        "book_bps_on_short_side": agg("book_bps_on_short_side"),
        "implied_financing_bps_per_year": agg("implied_financing_bps_per_year"),
        "per_formation": per_formation,
    }


# ---------------------------------------------------------------------------
# DSR, RE-DERIVED OUTSIDE THE SCREENING PATH
# ---------------------------------------------------------------------------


def dsr_at(n_trials: int, result: Any, periods_per_year: float = 252.0) -> float | None:
    """DSR at an arbitrary denominator from a screening result's own stored
    primitives, via deflated_sharpe's two building blocks -- never by
    re-running a backtest and never by reading a stored dsr.

    Same construction as run_global_effective_n._dsr_at, deliberately: those
    two must agree, and this run's verification checks that it reproduces the
    screening's own n_trials=12 figure to floating-point noise."""
    d = result.deflated_sharpe
    if n_trials < MIN_TRIALS_FOR_DSR:
        return None
    if d.sigma_sr_annualized is None or d.sharpe_net_daily is None:
        return None
    root = float(np.sqrt(periods_per_year))
    sr0_daily = expected_max_sharpe_under_noise(d.sigma_sr_annualized / root, n_trials)
    if sr0_daily is None:
        return None
    return probabilistic_sharpe_ratio(
        d.sharpe_net_daily, sr0_daily, d.n_observations, d.skewness, d.kurtosis
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main() -> None:
    padded_start = START - timedelta(days=SHORT_INTEREST_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    universe = sorted(get_universe_over(START, END))
    log.info("universe over %s..%s: %d tickers", START, END, len(universe))

    # ONE price fetch for the whole run. Every arm below is handed this same
    # dict as price_frames, so no arm can differ from another by prices --
    # which is the single thing fa614ac showed can move this family's Sharpe
    # between runs of identical code.
    frames, missing_price = YFinanceProvider().get_daily_ohlcv(universe, padded_start, END)
    close = frames["close"]
    log.info(
        "prices: %d tickers %s..%s (%d unresolved)",
        len(close.columns), close.index[0].date(), close.index[-1].date(), len(missing_price),
    )
    # A provenance fingerprint of the exact price panel every arm shares, so a
    # future re-run can say whether it faced the same prices rather than
    # guessing (fa614ac: this family's Sharpe has moved between runs of
    # identical code because the prices underneath moved).
    close_digest = hashlib.sha256(
        np.ascontiguousarray(close.to_numpy(dtype=float)).tobytes()
        + "\x00".join(map(str, close.columns)).encode()
        + "\x00".join(str(x) for x in close.index).encode()
    ).hexdigest()

    # --- the ratio panel, by the family's own production path ---------------
    priced = list(close.columns)
    si_obs, finra_diag = FinraShortInterestProvider().fetch_observations_for_tickers(
        priced, SHORT_INTEREST_CYCLE_FETCH_START, END
    )
    cik_map = EdgarXbrlProvider().get_ticker_cik_map()
    resolvable = {t: cik_map[t] for t in priced if t in cik_map}
    share_obs, _share_diag = SecSharesOutstandingProvider().fetch_share_counts(
        resolvable, padded_start, END, missing_from_map=[t for t in priced if t not in cik_map]
    )
    share_frame, no_shares = build_point_in_time_share_count_frame(
        close, share_obs, max_staleness_days=SHARES_MAX_STALENESS_DAYS
    )
    ratio_frame, dtc_frame, panel_diag = build_short_interest_panels(close, si_obs, share_frame)
    log.info(
        "SIR panel: %d cells, %d FINRA cycles, %d tickers with no share count, %d never ranked",
        int(ratio_frame.notna().to_numpy().sum()), finra_diag.n_cycles_resolved,
        len(no_shares), len(panel_diag.tickers_never_ranked),
    )

    # --- composition, every spec of the pre-declared grid --------------------
    config = default_short_interest_config()
    config.formation_start = START
    assert config.financing_bps_per_year == 0.0, "composition must be measured on the LIVE config"
    panel_for = {"si_ratio": ratio_frame, "si_dtc": dtc_frame}
    composition: dict[str, Any] = {}
    for spec in build_short_interest_family():
        panel = panel_for["si_ratio" if spec.pattern_id.startswith("si_ratio") else "si_dtc"]
        data = CrossSectionalData(close=close, fundamental_signal=panel)
        composition[spec.pattern_id] = measure_spec_composition(data, spec, config, ratio_frame)
        c = composition[spec.pattern_id]
        if c["n_formations_sir_covered"]:
            log.info(
                "%-22s %-20s tail(notional) %.4f  book %.2f bp/yr  => financing %.4f",
                spec.pattern_id, spec.portfolio,
                c["short_tail_share_notional"]["mean"],
                c["book_bps_on_short_side"]["mean"],
                c["implied_financing_bps_per_year"]["mean"],
            )

    registered = composition[REGISTERED_SPEC_ID]
    measured_hedged = round(registered["implied_financing_bps_per_year"]["mean"], 4)
    ls_specs = [k for k, v in composition.items() if v.get("portfolio") == "long_short"]
    ls_ratio = composition["si_ratio_ls_h21"]
    measured_ls = round(ls_ratio["implied_financing_bps_per_year"]["mean"], 4)

    # CROSS-CHECK 1, HARD. For a long_short book gross notional is exactly 2.0
    # and the short leg exactly 1.0, so the general net-weight formula MUST
    # collapse to borrow_cost's own B/2. If it does not, the net-weight walk
    # above is wrong and every number in this run is suspect.
    for key in ls_specs:
        c = composition[key]
        if not c["n_formations_sir_covered"]:
            continue
        b_over_2 = financing_bps_for_long_short_book(c["book_bps_on_short_side"]["mean"])
        got = c["implied_financing_bps_per_year"]["mean"]
        assert abs(got - b_over_2) < 1e-6, (
            f"{key}: net-weight financing {got} disagrees with borrow_cost's B/2 {b_over_2}"
        )
    log.info("cross-check 1: all %d long_short specs reproduce borrow_cost's B/2 exactly",
             len(ls_specs))

    # CROSS-CHECK 2, REPORTED NOT ASSERTED. For a HEDGED book the same
    # collapse holds only while every long-leg name is genuinely net long
    # (long weight > 1/N). When it does, gross = 2 * short_notional and
    # implied = B/2 again; a name whose magnitude weight fell below an equal
    # universe share would break it and is a real thing to know about rather
    # than to abort on. Reported per spec so the report can say which.
    hedged_collapse = {}
    for key, c in composition.items():
        if c.get("portfolio") != "long_universe_hedged" or not c["n_formations_sir_covered"]:
            continue
        b_over_2 = financing_bps_for_long_short_book(c["book_bps_on_short_side"]["mean"])
        hedged_collapse[key] = float(c["implied_financing_bps_per_year"]["mean"] - b_over_2)
    log.info("cross-check 2 (hedged, implied - B/2): %s", hedged_collapse)

    # --- the cost arms, all on the SAME price frames ------------------------
    arms_spec = [
        ("baseline (LIVE config, financing 0.0)", 0.0),
        (f"measured for the REGISTERED hedged book ({measured_hedged} bp/yr)", measured_hedged),
        (f"measured for this family's long_short books ({measured_ls} bp/yr)", measured_ls),
        (
            "the GC bracket borrow_cost offered (34 bp/yr on the short leg)",
            financing_bps_for_long_short_book(GENERAL_COLLATERAL_BPS_PER_YEAR),
        ),
        (
            "the hard-to-borrow bracket borrow_cost offered (430 bp/yr on the short leg)",
            financing_bps_for_long_short_book(HARD_TO_BORROW_BPS_PER_YEAR),
        ),
    ]
    denominators = _pooled_denominators()
    log.info("DSR denominators: %s", denominators)

    arms: list[dict[str, Any]] = []
    for label, financing in arms_spec:
        arm_config = default_short_interest_config()
        arm_config.financing_bps_per_year = financing
        summary = run_short_interest_screening(
            start=START, end=END, config=arm_config, universe=universe, price_frames=frames
        )
        by_spec: dict[str, Any] = {}
        for r in summary.results:
            by_spec[r.pattern_id] = {
                "sharpe_annualized": r.sharpe_annualized,
                "total_cost_drag": r.total_cost_drag,
                "total_financing_drag": r.total_financing_drag,
                "n_formations": r.n_formations,
                "n_skipped_formations": r.n_skipped_formations,
                "n_trading_days": r.n_trading_days,
                "avg_names_per_leg": r.avg_names_per_leg,
                "dsr_screened": r.deflated_sharpe.dsr,
                "n_trials_screened": r.deflated_sharpe.n_trials,
                "dsr_by_n": {str(n): dsr_at(n, r) for n in denominators},
                # THE PRIMITIVES, so every DSR above can be re-derived from
                # this artifact alone with the formulas typed fresh -- rather
                # than a reader having to take the stored dsr on faith.
                "psr_vs_zero": r.deflated_sharpe.psr_vs_zero,
                "sharpe_net_daily": r.deflated_sharpe.sharpe_net_daily,
                "n_observations": r.deflated_sharpe.n_observations,
                "skewness": r.deflated_sharpe.skewness,
                "kurtosis": r.deflated_sharpe.kurtosis,
                "sigma_sr_annualized": r.deflated_sharpe.sigma_sr_annualized,
            }
        # preservation_score for the registered spec, on this arm's own realized
        # series -- the standing secondary check, computed rather than skipped.
        reg_spec = next(s for s in build_short_interest_family() if s.pattern_id == REGISTERED_SPEC_ID)
        reg_config = default_short_interest_config()
        reg_config.financing_bps_per_year = financing
        reg_config.formation_start = START
        replay = run_cross_sectional_backtest(
            CrossSectionalData(close=close, fundamental_signal=ratio_frame), reg_spec, reg_config
        )
        preservation = None
        if replay.status == "ok" and len(replay.daily_returns):
            preservation = compute_preservation_metrics(
                replay.daily_returns, dsr=by_spec[REGISTERED_SPEC_ID]["dsr_screened"]
            ).as_dict()

        # The fingerprint consequence, computed from the code rather than
        # restated: financing_bps_per_year IS in config_identity().
        arms.append({
            "label": label,
            "financing_bps_per_year": financing,
            "config_fingerprint": config_fingerprint(arm_config),
            "config_identity": config_identity(arm_config),
            "n_positive_specs": sum(1 for v in by_spec.values() if v["sharpe_annualized"] > 0),
            "n_specs": len(by_spec),
            "specs": by_spec,
            "registered_preservation": preservation,
        })
        reg = by_spec[REGISTERED_SPEC_ID]
        log.info(
            "ARM %-62s %s Sharpe %+.6f  DSR@%d %.4f  financing drag %.4f  positive %d/%d",
            label[:62], REGISTERED_SPEC_ID, reg["sharpe_annualized"], LOCAL_N,
            reg["dsr_by_n"][str(LOCAL_N)], reg["total_financing_drag"],
            sum(1 for v in by_spec.values() if v["sharpe_annualized"] > 0), len(by_spec),
        )

    # --- verification the report can show -----------------------------------
    reproduction = []
    for arm in arms:
        for spec_id, v in arm["specs"].items():
            if v["dsr_screened"] is not None and v["dsr_by_n"][str(LOCAL_N)] is not None:
                reproduction.append({
                    "arm": arm["label"], "spec": spec_id,
                    "delta": float(v["dsr_by_n"][str(LOCAL_N)] - v["dsr_screened"]),
                })
    worst_reproduction = max((abs(r["delta"]) for r in reproduction), default=float("nan"))
    log.info("worst |re-derived DSR - screened DSR| across %d specs: %.3e",
             len(reproduction), worst_reproduction)

    payload = {
        "run_date": RUN_DATE,
        "purpose": (
            "MEASUREMENT ONLY. No registration status, config, cost model or DB row is written "
            "by this script. The numbers exist for the repo owner's pending borrow decision, "
            "paired with lazy_prices' already-measured 96.33 bp/yr => financing 48.16."
        ),
        "registered_spec": REGISTERED_SPEC_ID,
        "registered_spec_portfolio": registered.get("portfolio"),
        "window": [START.isoformat(), END.isoformat()],
        "data_build": {
            "universe_size": len(universe),
            "priced_tickers": len(close.columns),
            "unresolved_tickers": len(missing_price),
            "close_first_date": str(close.index[0].date()),
            "close_last_date": str(close.index[-1].date()),
            "close_content_sha256": close_digest,
            "finra_cycles_resolved": finra_diag.n_cycles_resolved,
            "sir_cells": int(ratio_frame.notna().to_numpy().sum()),
            "tickers_without_share_count": len(no_shares),
            "tickers_never_ranked": len(panel_diag.tickers_never_ranked),
            "one_shared_fetch": True,
        },
        "schedule": {
            "general_collateral_bps": GENERAL_COLLATERAL_BPS_PER_YEAR,
            "hard_to_borrow_bps": HARD_TO_BORROW_BPS_PER_YEAR,
            "tail_fraction": DEFAULT_SCHEDULE.tail_fraction,
            "no_tilt_tail_share": NO_TILT_TAIL_SHARE,
            "no_tilt_book_bps": NO_TILT_BPS,
            "percentile_panel": "short_interest_ratio, for every spec including the dtc half",
        },
        "measured_financing_bps_per_year": {
            "registered_hedged_book": measured_hedged,
            "long_short_books_si_ratio_h21": measured_ls,
        },
        "dsr_denominators": denominators,
        "reference_figures": {
            "section_8_pinned_sharpe": SECTION_8_PINNED_SHARPE,
            "section_8_pinned_dsr": SECTION_8_PINNED_DSR,
            "registration_documented_sharpe": REGISTRATION_DOCUMENTED_SHARPE,
            "registration_documented_dsr": REGISTRATION_DOCUMENTED_DSR,
        },
        "composition": composition,
        "arms": arms,
        "verification": {
            "n_dsr_reproductions": len(reproduction),
            "worst_abs_dsr_reproduction_delta": worst_reproduction,
            "long_short_specs_reproduce_borrow_cost_b_over_2": True,
            "hedged_implied_minus_b_over_2": hedged_collapse,
        },
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    OUT_TXT.write_text(render_report(payload))
    log.info("wrote %s and %s", OUT_JSON.name, OUT_TXT.name)


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------


# WHAT THIS RUN DOES NOT ESTABLISH. Kept as data next to the renderer, the way
# the lazy_prices report's own limits section is, so a reader of the committed
# .txt gets the caveats in the same file as the numbers rather than having to
# find them in a commit message.
LIMITS = (
    (
        "IT IS STILL NOT A BORROW-RATE FEED. Every rate here is D'Avolio's or "
        "Beneish/Lee/Nichols', mapped onto names by a short-interest proxy both papers "
        'explicitly warn against (D\'Avolio p.285: "the limited use of this measure as a proxy '
        'for short-sale constraints"). The paid-feed gap stays open -- '
        "PENDING_PAID_DATA_DECISIONS.md, entry P1."
    ),
    (
        'THE SCHEDULE OVERCHARGES BY CONSTRUCTION. Beneish/Lee/Nichols p.17: "even in the '
        'highest SIR decile, less than 30 percent of the stocks are special". Charging a whole '
        "decile the specials rate therefore prices roughly 70% of it too high, and that bound "
        "bites HARDEST on this family's long_short specs, whose short leg is entirely inside "
        "that decile by construction. Their 430 bp/yr is the schedule's answer, not an estimate "
        "of what a broker would charge."
    ),
    (
        "PERCENTILES ARE WITHIN THE S&P 500 CROSS-SECTION, not the whole market. D'Avolio's "
        'deciles are market-wide and p.273 says index constituents "are almost always general '
        'collateral", so an S&P 500 top decile holds far fewer true specials than the '
        "market-wide one his fee schedule was measured on. Same direction: overcharges."
    ),
    (
        "FINRA's free file starts 2017-12-29 and this family's window opens 2018-01-12, so "
        "coverage is near-complete here -- unlike lazy_prices, where 7 of 24 formations predated "
        "it. Any formation reported as uncovered above is excluded from every average rather "
        "than folded in."
    ),
    (
        "THE STALENESS IN borrow_cost.py APPLIES UNCHANGED. Its samples end 2013; securities "
        "lending has since electronified and compressed, which makes both legs of the schedule "
        "more likely overstatements than understatements in 2026."
    ),
    (
        "THE HEDGED BOOK'S SHORT SIDE IS AN EQUAL-WEIGHTED INDEX BASKET, which is exactly the "
        "population D'Avolio p.273 calls almost always general collateral -- so its measured "
        "rate is, if anything, an overstatement of an already-cheap side. The schedule cannot "
        "see that, because it prices the tails of whatever cross-section it is handed."
    ),
)


def _lazy_prices_pairing() -> dict[str, Any] | None:
    """lazy_prices' already-measured borrow figures, READ from its own two
    committed artifacts rather than retyped into this file.

    The repo owner's pending decision is about both families at once, so the
    two sets of numbers belong on one page. Retyping them would be the exact
    fabrication risk this project's rules exist to remove -- and they would go
    stale silently the first time that family is re-measured."""
    runs = _BACKEND / "data" / "research_runs"
    borrow = runs / "lazy_prices_borrow_composition_2026-09-05.json"
    switch = runs / "lazy_prices_cost_basis_switch_2026-09-05.json"
    if not (borrow.is_file() and switch.is_file()):
        return None
    try:
        b = json.loads(borrow.read_text())
        s = json.loads(switch.read_text())
    except (OSError, ValueError):
        return None
    scenarios = s.get("scenarios", {})
    before = scenarios.get("AFTER-calibrated", {}).get("best", {})
    after = scenarios.get("AFTER+measured-borrow", {}).get("best", {})
    if not before or not after:
        return None

    def _dsr(blob: dict, n_trials: int) -> float | None:
        """That family's DSR at an arbitrary denominator, from ITS OWN stored
        primitives via the same two deflated_sharpe building blocks used for
        this family above -- so the "does it clear the 0.50 floor" comparison
        below is computed for both families rather than asserted for either."""
        root = float(np.sqrt(252.0))
        sr_daily = blob["sharpe"] / root
        sr0 = expected_max_sharpe_under_noise(blob["sigma_sr_annualized"] / root, n_trials)
        if sr0 is None:
            return None
        return probabilistic_sharpe_ratio(
            sr_daily, sr0, blob["n_observations"], blob["skewness"], blob["kurtosis"]
        )

    dens = s.get("policy_d_n") or []
    return {
        "spec": b.get("spec"),
        "n_formations_total": b.get("n_formations_total"),
        "n_formations_sir_covered": b.get("n_formations_sir_covered"),
        "short_tail_share": b["short_tail_share"]["mean"],
        "book_bps": b["book_bps_schedule_default"]["mean"],
        "financing_bps_per_year": b["book_bps_schedule_default"][
            "implied_financing_bps_per_year"
        ],
        "sharpe_before": before["sharpe"],
        "sharpe_after": after["sharpe"],
        "n_positive_before": scenarios["AFTER-calibrated"]["n_specs_positive"],
        "n_positive_after": scenarios["AFTER+measured-borrow"]["n_specs_positive"],
        "n_specs": scenarios["AFTER-calibrated"]["n_specs"],
        "denominators": dens,
        "dsr_before": {str(n): _dsr(before, n) for n in dens},
        "dsr_after": {str(n): _dsr(after, n) for n in dens},
        "source": [borrow.name, switch.name],
    }


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def render_report(p: dict[str, Any]) -> str:
    L: list[str] = []
    a = L.append
    a(f"SHORT_INTEREST'S REAL BORROW EXPOSURE -- MEASURED, NOT BRACKETED -- {p['run_date']}")
    a("=" * 100)
    a("")
    for line in _wrap(p["purpose"], 96):
        a(line)
    a("")
    a("THE HEADLINE, AND IT IS NOT THE ONE borrow_cost.py's SENTENCE IMPLIES")
    a("-" * 100)
    for line in _wrap(
        "borrow_cost.py names this family as where the 0.0 borrow assumption bites hardest, and "
        "the sentence it uses is about the long_short specs, which short the most heavily shorted "
        f"names in the index. THE REGISTERED SPEC IS NOT ONE OF THEM. {p['registered_spec']} is a "
        f"{p['registered_spec_portfolio']} spec: its short side is the equal-weighted WHOLE "
        "eligible universe, and its long leg is the LOWEST-short-interest 5%, which removes part "
        "of the low tail from the short side. So the family contains both the most exposed book "
        "in this project and, in the same grid, one that is slightly LESS exposed than a random "
        "short. Both are measured below.", 96
    ):
        a(line)
    a("")
    s = p["schedule"]
    a(f"  schedule: GC {s['general_collateral_bps']:.0f} bp/yr, hard-to-borrow "
      f"{s['hard_to_borrow_bps']:.0f} bp/yr, tails {s['tail_fraction']:.2f} each side")
    a(f"  NO-TILT BASELINE: a short side drawn independently of short interest holds "
      f"{s['no_tilt_tail_share']:.2f} tail")
    a(f"  notional and therefore costs {s['no_tilt_book_bps']:.1f} bp/yr -- NOT "
      f"{s['general_collateral_bps']:.0f}. That is the number to read every row against.")
    a(f"  percentiles are taken on the {s['percentile_panel']}")
    a("")
    a("COMPOSITION OF EACH SPEC'S REALIZED SHORT SIDE")
    a("-" * 100)
    a(f"{'spec':22s} {'portfolio':21s} {'forms':>6s} {'tailN':>7s} {'tailEW':>7s} "
      f"{'medSIRpct':>9s} {'gross':>6s} {'bookbp':>8s} {'financing':>10s}")
    a("-" * 100)
    for spec_id, c in p["composition"].items():
        if not c.get("n_formations_sir_covered"):
            a(f"{spec_id:22s} {c.get('portfolio', '?'):21s}  NO SIR-COVERED FORMATION")
            continue
        a(f"{spec_id:22s} {c['portfolio']:21s} {c['n_formations_sir_covered']:6d} "
          f"{c['short_tail_share_notional']['mean']:7.4f} {c['short_tail_share_equal']['mean']:7.4f} "
          f"{c['short_median_sir_pct']['mean']:9.4f} {c['gross_notional_held']['mean']:6.3f} "
          f"{c['book_bps_on_short_side']['mean']:8.2f} "
          f"{c['implied_financing_bps_per_year']['mean']:10.4f}")
    a("")
    a("  tailN     = share of SHORT-SIDE NOTIONAL in a hard-to-borrow tail (no-tilt = "
      f"{s['no_tilt_tail_share']:.2f})")
    a("  tailEW    = the same share, equal-weighted across names (the lazy_prices report's units)")
    a("  medSIRpct = median short-interest percentile of the short side (0.5 = no tilt)")
    a("  gross     = mean gross notional held; 2.0 for long_short, less for hedged (the legs net)")
    a("  bookbp    = notional-weighted borrow rate the schedule charges the short side, bp/yr")
    a("  financing = the SCALAR config.financing_bps_per_year that accrues exactly that charge")
    a("")
    m = p["measured_financing_bps_per_year"]
    a(f"  MEASURED for the registered {p['registered_spec']}: "
      f"financing_bps_per_year = {m['registered_hedged_book']}")
    a(f"  MEASURED for si_ratio_ls_h21 (registered? NO): "
      f"financing_bps_per_year = {m['long_short_books_si_ratio_h21']}")
    a("")
    for line in _wrap(
        "THE si_ratio LONG_SHORT ROWS ARE NOT AN APPROXIMATION OF THE WORST-CASE BRACKET, THEY "
        "ARE IT. Their short leg is the top 5% of the cross-section by short-interest ratio and "
        "borrow_cost's expensive tail is the top 10%, so 5% sits wholly inside 10% and every "
        "single name in that leg is priced at the specials rate -- tail share exactly 1.0000, "
        "book rate exactly 430.00, financing exactly 215.0. borrow_cost's 'bites hardest' "
        "sentence is, for these six specs, precisely right and precisely quantified. The "
        "days-to-cover long_short specs land just below it (0.79-0.80 tail share) because "
        "days-to-cover normalizes by volume and so re-orders the names somewhat relative to the "
        "ratio the schedule keys on.", 96
    ):
        a(f"  {line}")
    a("")
    a("THE ARITHMETIC, CHECKED RATHER THAN TRUSTED")
    a("-" * 100)
    a("The schedule is a two-rate step function, so bookbp must be recoverable by hand from three")
    a("published numbers and one measured share. tailN is the share of SIR-COVERED short notional")
    a("in a tail; the rest of the short side has NO short-interest observation and takes")
    a("borrow_cost's documented NaN->GC default. So:")
    a("")
    a("    bookbp  =  cov * [ tailN*430 + (1-tailN)*34 ]  +  (1-cov) * 34")
    a("")
    a("with cov = short-side notional carrying a SIR. Any residual is the gap between a mean of")
    a("per-formation products and a product of per-formation means, and is expected to be small.")
    a("")
    a(f"{'spec':22s} {'tailN':>8s} {'cov':>7s} {'hand bookbp':>12s} {'script bookbp':>14s} "
      f"{'gap':>8s}")
    for spec_id, c in p["composition"].items():
        if not c.get("n_formations_sir_covered"):
            continue
        t = c["short_tail_share_notional"]["mean"]
        cov = c["short_sir_coverage_by_notional"]["mean"]
        covered_rate = t * s["hard_to_borrow_bps"] + (1.0 - t) * s["general_collateral_bps"]
        hand = cov * covered_rate + (1.0 - cov) * s["general_collateral_bps"]
        got = c["book_bps_on_short_side"]["mean"]
        a(f"{spec_id:22s} {t:8.4f} {cov:7.4f} {hand:12.2f} {got:14.2f} {got - hand:8.2f}")
    a("")
    a("BEFORE / AFTER FOR THE REGISTERED SPEC")
    a("-" * 100)
    a("Every arm below is ONE screening of the whole 12-spec grid on the SAME price frames, with")
    a("only config.financing_bps_per_year changed. NOTHING IS ADOPTED BY THIS RUN.")
    a("")
    dens = p["dsr_denominators"]
    header = f"{'arm':58s} {'financing':>10s} {'Sharpe':>9s}"
    for n in dens:
        header += f" {('DSR@' + str(n)):>9s}"
    header += f" {'finDrag':>8s} {'pos':>6s}"
    a(header)
    a("-" * 100)
    for arm in p["arms"]:
        reg = arm["specs"][p["registered_spec"]]
        line = (f"{arm['label'][:58]:58s} {arm['financing_bps_per_year']:10.4f} "
                f"{reg['sharpe_annualized']:9.4f}")
        for n in dens:
            v = reg["dsr_by_n"].get(str(n))
            line += f" {'n/a':>9s}" if v is None else f" {v:9.4f}"
        line += f" {reg['total_financing_drag']:8.4f} {arm['n_positive_specs']:3d}/{arm['n_specs']:<2d}"
        a(line)
    a("")
    base = p["arms"][0]["specs"][p["registered_spec"]]
    after = p["arms"][1]["specs"][p["registered_spec"]]
    a(f"  ADOPTING THE MEASURED RATE WOULD COST: Sharpe {base['sharpe_annualized']:.4f} -> "
      f"{after['sharpe_annualized']:.4f} ({after['sharpe_annualized'] - base['sharpe_annualized']:+.4f})")
    for n in dens:
        b, aa = base["dsr_by_n"].get(str(n)), after["dsr_by_n"].get(str(n))
        if b is not None and aa is not None:
            a(f"    DSR at N={n:<5d} {b:.4f} -> {aa:.4f} ({aa - b:+.4f})")
    a("")
    a("PRESERVATION SCORE for the registered spec, per arm (the standing secondary check)")
    a("-" * 100)
    a(f"{'arm':58s} {'score':>8s} {'noStab':>8s} {'sharpe':>8s} {'calmar':>8s} "
      f"{'SR 1st½':>8s} {'SR 2nd½':>8s}")
    for arm in p["arms"]:
        pr = arm["registered_preservation"]
        if pr is None:
            a(f"{arm['label'][:58]:58s}   (no replay)")
            continue
        a(f"{arm['label'][:58]:58s} {pr['preservation_score']:8.4f} "
          f"{pr['preservation_score_no_stab']:8.4f} {pr['sharpe_full']:8.4f} "
          f"{pr['calmar']:8.4f} {pr['sharpe_first_half']:8.4f} {pr['sharpe_second_half']:8.4f}")
    a("")
    for line in _wrap(
        "READ THE ZERO SCORES CORRECTLY: they are 0.0 in EVERY arm including the untouched "
        "baseline, so they are not something the borrow charge did. stability collapses to 0 "
        "because this spec's FIRST-HALF Sharpe is negative while its second half is strongly "
        "positive -- the whole realized edge sits in the back half of the window. That is a "
        "property of the registered strategy, measured here and reported rather than omitted, "
        "and it is unrelated to the borrow question. preservation_score_no_stab is shown beside "
        "it because that column DOES move with the charge.", 96
    ):
        a(f"  {line}")
    a("")
    lp = _lazy_prices_pairing()
    if lp is not None:
        a("SIDE BY SIDE WITH lazy_prices, THE OTHER FAMILY AWAITING THE SAME DECISION")
        a("-" * 100)
        a(f"Read from {', '.join(lp['source'])} -- not retyped.")
        a("")
        a(f"{'':40s} {'short-side':>12s} {'book':>9s} {'financing':>10s} {'Sharpe':>9s} "
          f"{'Sharpe':>9s} {'specs':>10s}")
        a(f"{'':40s} {'tail share':>12s} {'bp/yr':>9s} {'bps/yr':>10s} {'before':>9s} "
          f"{'after':>9s} {'positive':>10s}")
        a("-" * 100)
        base = p["arms"][0]["specs"][p["registered_spec"]]
        aft = p["arms"][1]["specs"][p["registered_spec"]]
        c = p["composition"][p["registered_spec"]]
        a(f"{'short_interest ' + p['registered_spec']:40s} "
          f"{c['short_tail_share_notional']['mean']:12.4f} "
          f"{c['book_bps_on_short_side']['mean']:9.2f} "
          f"{p['measured_financing_bps_per_year']['registered_hedged_book']:10.4f} "
          f"{base['sharpe_annualized']:9.4f} {aft['sharpe_annualized']:9.4f} "
          f"{p['arms'][0]['n_positive_specs']:4d}->{p['arms'][1]['n_positive_specs']:<5d}")
        a(f"{'lazy_prices ' + str(lp['spec']):40s} {lp['short_tail_share']:12.4f} "
          f"{lp['book_bps']:9.2f} {lp['financing_bps_per_year']:10.4f} "
          f"{lp['sharpe_before']:9.4f} {lp['sharpe_after']:9.4f} "
          f"{lp['n_positive_before']:4d}->{lp['n_positive_after']:<5d}")
        ls_key = "si_ratio_ls_h21"
        ls = p["composition"].get(ls_key, {})
        if ls.get("n_formations_sir_covered"):
            a(f"{'short_interest ' + ls_key + ' *':40s} "
              f"{ls['short_tail_share_notional']['mean']:12.4f} "
              f"{ls['book_bps_on_short_side']['mean']:9.2f} "
              f"{ls['implied_financing_bps_per_year']['mean']:10.4f} "
              f"{'  n/a':>9s} {'  n/a':>9s} {'  NOT REGISTERED':>10s}")
        a("")
        a("  * shown because it is the book borrow_cost.py's 'bites hardest' sentence is about.")
        a("    It is NOT the live registration and no forward record depends on it.")
        a("")
        a("  DSR AFTER PAYING EACH FAMILY'S OWN MEASURED RATE, against the 0.50 screening floor.")
        a("  Each family is shown at ITS OWN denominator grid -- the first entry is that family's")
        a("  pre-declared grid size (12 here, 36 there) and the rest are the shared pooled ones.")
        a("")
        floor_ok: dict[str, bool] = {}
        for label, grid, getter in (
            (f"short_interest {p['registered_spec']}", p["dsr_denominators"],
             lambda n: (base["dsr_by_n"].get(str(n)), aft["dsr_by_n"].get(str(n)))),
            (f"lazy_prices {lp['spec']}", lp["denominators"],
             lambda n: (lp["dsr_before"].get(str(n)), lp["dsr_after"].get(str(n)))),
        ):
            ok = True
            cells = []
            for n in grid:
                b_, a_ = getter(n)
                ok = ok and (a_ is not None and a_ >= 0.50)
                cells.append(
                    f"N={n:<4d} {b_:6.4f}->{a_:6.4f}" if (b_ is not None and a_ is not None)
                    else f"N={n:<4d} {'n/a':>14s}"
                )
            floor_ok[label] = ok
            a(f"  {label:40s} " + "   ".join(cells))
        a("")
        for label, ok in floor_ok.items():
            a(f"  clears 0.50 at EVERY denominator after paying its own rate: "
              f"{label:40s} {'YES' if ok else 'NO'}")
        a("")
        for line in _wrap(
            "THE PREDICTION THIS RUN FALSIFIES, recorded because it was written down and was "
            "wrong. lazy_prices_borrow_composition_2026-09-05.txt closes by saying of this "
            "family: \"Its short leg is selected ON the variable this schedule keys off, so its "
            "tail share will be far above 20% and its true rate far above this family's.\" That "
            "is exactly right about the six long_short specs and exactly wrong about the "
            "REGISTERED one, which is the hedged book. Measured, the registered "
            "short_interest_ratio registration is slightly LESS borrow-exposed than lazy_prices, "
            "not more.", 96
        ):
            a(f"  {line}")
        a("")
    a("THE OPERATIONAL CONSEQUENCE OF ADOPTING ANY OF THESE, computed rather than asserted")
    a("-" * 100)
    for line in _wrap(
        "financing_bps_per_year IS a field of config_identity(), so every non-zero value below "
        "re-hashes config_fingerprint. The forward-validation runner re-derives that fingerprint "
        "every tick and parks a row whose fingerprint moved as spec_drift, which is excluded from "
        "ACTIVE_STATUSES. That is an operational-status change and the repo owner's call, which "
        "is exactly why this run measures and adopts nothing -- the same wall lazy_prices' switch "
        "stopped at (26d1ce1).", 96
    ):
        a(line)
    a("")
    for arm in p["arms"]:
        a(f"  financing {arm['financing_bps_per_year']:>10.4f}  config_fingerprint "
          f"{arm['config_fingerprint'][:12]}…"
          + ("   <- the LIVE row's value" if arm["financing_bps_per_year"] == 0.0 else ""))
    a("")
    a("DATA BUILD, AND WHAT IT DOES AND DOES NOT PIN")
    a("-" * 100)
    d = p["data_build"]
    a(f"  universe {d['universe_size']} tickers, {d['priced_tickers']} priced, "
      f"{d['unresolved_tickers']} unresolved")
    a(f"  close frame {d['close_first_date']}..{d['close_last_date']}, "
      f"content sha256 {d['close_content_sha256'][:16]}…")
    a(f"  FINRA cycles resolved {d['finra_cycles_resolved']}, SIR cells {d['sir_cells']}, "
      f"{d['tickers_without_share_count']} tickers with no share count, "
      f"{d['tickers_never_ranked']} never ranked")
    a("")
    r = p["reference_figures"]
    a(f"  section 8's pinned reproducible backward figure: Sharpe {r['section_8_pinned_sharpe']:+.8f} "
      f"DSR {r['section_8_pinned_dsr']:.8f}")
    a(f"  this run's baseline arm:                        Sharpe "
      f"{p['arms'][0]['specs'][p['registered_spec']]['sharpe_annualized']:+.8f} "
      f"DSR {p['arms'][0]['specs'][p['registered_spec']]['dsr_screened']:.8f}")
    a(f"  the registration's own documented figures:      Sharpe "
      f"{r['registration_documented_sharpe']:+.4f} DSR {r['registration_documented_dsr']:.4f}")
    for line in _wrap(
        "A gap between the first two is the reproducibility drift fa614ac diagnosed (a mid-split "
        "price freeze), NOT an effect of anything measured here. It is why every before/after "
        "figure above is a DIFFERENCE within one shared data build rather than a comparison "
        "against a historical number.", 96
    ):
        a(f"  {line}")
    a("")
    v = p["verification"]
    a("VERIFICATION")
    a("-" * 100)
    a(f"  every DSR re-derived OUTSIDE the screening path from the row's own primitives "
      f"({v['n_dsr_reproductions']} of them);")
    a(f"  worst |re-derived - screened| at N={LOCAL_N}: {v['worst_abs_dsr_reproduction_delta']:.3e}")
    a("  every long_short spec's net-weight financing reproduces borrow_cost's own B/2 exactly")
    a("    (asserted in code, not eyeballed -- the run aborts if it does not)")
    for key, gap in (v.get("hedged_implied_minus_b_over_2") or {}).items():
        a(f"  hedged {key}: implied financing minus B/2 = {gap:.3e} (0 means every long-leg name")
        a("    is genuinely net long, so gross = 2 x short notional and the collapse holds here too)")
    a("  formations come from form_portfolio(), the harness's own function, at the same positions")
    a("    run_cross_sectional_backtest walks -- not a re-derivation of the formation cadence")
    a("  the eligible cross-section each percentile is taken over is re-derived from")
    a("    form_portfolio's own eligibility rule and CHECKED against FormationRecord.n_eligible")
    a("    on every single formation (the run aborts on any mismatch)")
    a("")
    a("WHAT THIS RUN DOES *NOT* ESTABLISH -- the limits, stated rather than found later")
    a("-" * 100)
    for i, text in enumerate(LIMITS, start=1):
        lines = _wrap(text, 92)
        a(f" {i}. {lines[0]}")
        for line in lines[1:]:
            a(f"    {line}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    # --render-only re-renders the .txt from the PERSISTED .json without
    # re-measuring anything. Deliberate: the JSON is the artifact, the text is
    # a view of it, and re-running a 3-minute measurement to reword a table
    # would risk moving the numbers (this family's prices are not guaranteed
    # to reproduce across runs -- fa614ac). It cannot compute anything: if a
    # field is missing from the JSON, the render fails rather than filling in.
    if "--render-only" in sys.argv:
        persisted = json.loads(OUT_JSON.read_text())
        OUT_TXT.write_text(render_report(persisted))
        log.info("re-rendered %s from %s (no measurement re-run)", OUT_TXT.name, OUT_JSON.name)
    else:
        main()
