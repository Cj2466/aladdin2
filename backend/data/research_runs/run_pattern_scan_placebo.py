"""RUNNER for the pre-registered rule-free pattern scan vs. placebo.

Contract: `data/research_runs/pattern_scan_2026-09-11/PREREGISTRATION.md`
plus ADDENDUM_01 (placebo target and the under-specified points) and
ADDENDUM_02 (Panel E's universe and bar calendar, and the disclosed timing
probe). This script computes nothing the pre-registration does not ask for
and chooses nothing the addenda do not already declare.

TWO PHASES, DELIBERATELY SEPARATE COMMANDS:

    python -m data.research_runs.run_pattern_scan_placebo --phase discovery
    python -m data.research_runs.run_pattern_scan_placebo --phase holdout

§4 fixes that the holdout window "is touched exactly once, in §6, after §5 is
complete and committed". The discovery phase writes
`patterns_discovery_E.csv`, `patterns_discovery_C.csv` and
`placebo_envelope.json` and evaluates GATE 1; the holdout phase REFUSES to
start unless those files already exist on disk. That is the ordering as a
mechanical precondition rather than as an intention. (A phase-2 run also
re-derives discovery from the seeds, which is deterministic, and checks that
the re-derived GATE 1 numbers equal what phase 1 committed — so a holdout run
against a changed panel fails loudly instead of silently comparing apples to
oranges.)

Every number this script produces lands in a committed file under
`data/research_runs/pattern_scan_2026-09-11/`, and one summary row per
(panel, arm) lands in `cross_sectional_trial_results` under run tag
`pattern_scan_placebo_2026-09-11` — this project's persist-every-result rule.
Nothing here registers, promotes or retires anything; this is not a family.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import _main_checkout_backend_dir
from app.db import SessionLocal
from app.services.market_data.price_store import (
    DEFAULT_STORE_DIR,
    PriceStore,
    adjusted_frames,
    store_manifest,
    trades_every_calendar_day,
)
from app.services.research_lab import pattern_scan_placebo as ps
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
)
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)

RUN_TAG = "pattern_scan_placebo_2026-09-11"
FAMILY_KEY = "pattern_scan_placebo"
OUT_DIR = Path(__file__).resolve().parent / "pattern_scan_2026-09-11"
# data/binance_hourly/ is gitignored, so — exactly like the price store and
# the local SQLite file — it exists only under the MAIN checkout. Resolving it
# through the same helper app/config.py uses is what stops a worktree run from
# silently finding nothing (or, worse, a different copy) there.
BINANCE_DIR = _main_checkout_backend_dir(Path(__file__).resolve().parents[1].parent) / "data" / "binance_hourly"

# ADDENDUM 02 §2(b): a date is a Panel E bar iff it carries at least this
# fraction of the median daily live-name count. The two populations on this
# store are 1,300-1,431 names and <= 17 names, so the cut is an order of
# magnitude from either — a separation, not a tuned threshold.
PANEL_E_LIVE_NAME_FRACTION = 0.10
MIN_STORE_ROWS = 1000          # §2 "with >= 1,000 daily rows"


# ---------------------------------------------------------------------------
# Panel loading
# ---------------------------------------------------------------------------

def _returns_from_wide(wide: pd.DataFrame) -> np.ndarray:
    """r_{i,t} = close_t/close_{t-1} - 1, defined only where the name has a
    close on t AND on the immediately preceding PANEL bar (§2's
    "bars with a missing predecessor are dropped"; ADDENDUM 01 item F)."""
    previous = wide.shift(1)
    return (wide / previous - 1.0).where(wide.notna() & previous.notna()).to_numpy()


def load_panel_e() -> tuple[pd.DatetimeIndex, list[str], np.ndarray, dict]:
    """Panel E per §2 as amended by ADDENDUM 02: every store ticker with
    >= 1,000 stored rows, minus the continuous-calendar instruments the store
    itself identifies, on the bar calendar the live-name count defines.
    Split/dividend adjustment is the store's own `adjusted_frames`, never a
    local reimplementation."""
    store = PriceStore()
    series: dict[str, pd.Series] = {}
    skipped_continuous = 0
    skipped_short = 0
    for path in sorted(DEFAULT_STORE_DIR.glob("*.csv.gz")):
        ticker = path.name[: -len(".csv.gz")]
        if trades_every_calendar_day(ticker):
            skipped_continuous += 1
            continue
        frame = store.read_ticker(ticker)
        if frame is None or len(frame) < MIN_STORE_ROWS:
            skipped_short += 1
            continue
        close = adjusted_frames(frame)["close"]
        close = close[(close.index >= ps.PANEL_E.discovery_start) & (close.index <= ps.PANEL_E.holdout_end)]
        if close.empty:
            continue
        series[ticker] = close
    wide = pd.DataFrame(series).sort_index()
    live = wide.notna().sum(axis=1)
    keep = live >= PANEL_E_LIVE_NAME_FRACTION * float(live.median())
    dropped_dates = [str(d.date()) for d in wide.index[~keep]]
    wide = wide[keep]
    meta = {
        "store_dir": str(DEFAULT_STORE_DIR),
        "store_manifest": store_manifest(DEFAULT_STORE_DIR),
        "files_in_store": len(list(DEFAULT_STORE_DIR.glob("*.csv.gz"))),
        "skipped_continuous_calendar": skipped_continuous,
        "skipped_under_min_rows": skipped_short,
        "n_names": int(wide.shape[1]),
        "n_bars": int(wide.shape[0]),
        "n_dates_dropped_by_live_name_rule": len(dropped_dates),
        "dropped_dates_sample": dropped_dates[:5],
        "non_equity_tickers_retained": sorted(
            t for t in wide.columns if t.endswith("=X") or t.startswith("^")
        ),
    }
    return pd.DatetimeIndex(wide.index), list(wide.columns), _returns_from_wide(wide), meta


def load_panel_c(market: str = "spot") -> tuple[pd.DatetimeIndex, list[str], np.ndarray, dict]:
    """Panel C per §2: the 25 Binance hourly symbols. `market="perp"` is §6's
    perp-close robustness re-run — reported, never gating."""
    series: dict[str, pd.Series] = {}
    for path in sorted(BINANCE_DIR.glob(f"{market}_*.csv")):
        symbol = path.name[len(market) + 1 : -len(".csv")]
        frame = pd.read_csv(path, parse_dates=["open_time"]).set_index("open_time")["close"]
        series[symbol] = frame
    wide = pd.DataFrame(series).sort_index()
    wide = wide[(wide.index >= ps.PANEL_C.discovery_start) & (wide.index <= ps.PANEL_C.holdout_end)]
    meta = {
        "market": market,
        "directory": str(BINANCE_DIR),
        "n_names": int(wide.shape[1]),
        "n_bars": int(wide.shape[0]),
        "symbols": list(wide.columns),
    }
    return pd.DatetimeIndex(wide.index), list(wide.columns), _returns_from_wide(wide), meta


# ---------------------------------------------------------------------------
# One panel's arms
# ---------------------------------------------------------------------------

@dataclass
class ArmDiscovery:
    arm: str
    seed: int
    horizon: int
    n_measurable: int
    n_unmeasurable: int
    n_t_ge_3: int
    n_t_ge_4: int
    t_max_abs: float
    n_formation_bars: int


def _arm_row(result: ps.ScanResult) -> ArmDiscovery:
    return ArmDiscovery(
        arm=result.arm,
        seed=result.seed,
        horizon=result.horizon,
        n_measurable=result.n_measurable,
        n_unmeasurable=result.n_unmeasurable,
        n_t_ge_3=result.n_t_ge_3,
        n_t_ge_4=result.n_t_ge_4,
        t_max_abs=result.t_max_abs,
        n_formation_bars=result.n_formation_bars,
    )


def discover_panel(dates, names, returns, spec, *, log) -> dict:
    """Real arm + 20 P1 draws + 20 P2 draws, all through the same code path."""
    real_panel = ps.build_panel(dates, names, returns)
    real = ps.run_discovery(real_panel, spec)
    log(f"  [{spec.key}] real arm: " + ", ".join(
        f"h={h} measurable={r.n_measurable} N3={r.n_t_ge_3} N4={r.n_t_ge_4} Tmax={r.t_max_abs:.4f}"
        for h, r in real.items()
    ))

    placebo: dict[str, dict[int, list[ps.ScanResult]]] = {}
    first_p1_panel = None
    for arm in (ps.ARM_P1, ps.ARM_P2):
        per_horizon: dict[int, list[ps.ScanResult]] = {h: [] for h in ps.HORIZONS}
        for seed in ps.PLACEBO_SEEDS:
            panel = ps.build_panel(dates, names, ps.placebo_returns(returns, arm, seed))
            if arm == ps.ARM_P1 and seed == ps.PLACEBO_SEEDS[0]:
                first_p1_panel = panel
            for h, result in ps.run_discovery(panel, spec, arm=arm, seed=seed).items():
                per_horizon[h].append(result)
        placebo[arm] = per_horizon
        for h in ps.HORIZONS:
            n3 = [r.n_t_ge_3 for r in per_horizon[h]]
            tm = [r.t_max_abs for r in per_horizon[h]]
            log(
                f"  [{spec.key}] {arm} h={h}: N3 max={max(n3)} median={int(np.median(n3))}, "
                f"Tmax max={np.nanmax(tm):.4f}"
            )

    fraction, identical, union = ps.identical_membership_fraction(real_panel, first_p1_panel, spec)
    log(f"  [{spec.key}] control non-degeneracy: {identical}/{union} identical cells = {fraction:.5f}")

    return {
        "real_panel": real_panel,
        "real": real,
        "placebo": placebo,
        "non_degeneracy": {
            "identical_cells": identical,
            "union_cells": union,
            "fraction": fraction,
            "bar": ps.NON_DEGENERACY_MAX_IDENTICAL_FRACTION,
            "passes": bool(fraction < ps.NON_DEGENERACY_MAX_IDENTICAL_FRACTION),
        },
    }


# ---------------------------------------------------------------------------
# Phase 1 — discovery + GATE 1
# ---------------------------------------------------------------------------

def phase_discovery(log) -> dict:
    started = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panels = {}
    out: dict = {"phase": "discovery", "run_tag": RUN_TAG, "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds")}

    loaders = [("E", ps.PANEL_E, load_panel_e), ("C", ps.PANEL_C, lambda: load_panel_c("spot"))]
    for key, spec, loader in loaders:
        log(f"loading panel {key} ...")
        dates, names, returns, meta = loader()
        log(f"  panel {key}: {meta['n_bars']} bars x {meta['n_names']} names")
        result = discover_panel(dates, names, returns, spec, log=log)
        panels[key] = {"spec": spec, "dates": dates, "names": names, "returns": returns, **result}

        frames = []
        for h, scan in result["real"].items():
            frame = ps.patterns_to_frame(scan)
            frame.insert(0, "horizon", h)
            frames.append(frame)
        pd.concat(frames).to_csv(OUT_DIR / f"patterns_discovery_{key}.csv", index=False)

        out[key] = {
            "panel_meta": meta,
            "panel_fingerprint_sha256": ps.panel_fingerprint(result["real_panel"]),
            "non_degeneracy": result["non_degeneracy"],
            "real": {str(h): asdict(_arm_row(r)) for h, r in result["real"].items()},
            "placebo": {
                arm: {str(h): [asdict(_arm_row(r)) for r in rows] for h, rows in per_h.items()}
                for arm, per_h in result["placebo"].items()
            },
            "gate1": {
                str(h): asdict(
                    ps.evaluate_gate1(result["real"][h], result["placebo"][ps.ARM_P1][h])
                )
                for h in ps.HORIZONS
            },
            "gate1_vs_P2_reported_only": {
                str(h): asdict(
                    ps.evaluate_gate1(result["real"][h], result["placebo"][ps.ARM_P2][h])
                )
                for h in ps.HORIZONS
            },
        }
        for h in ps.HORIZONS:
            g = out[key]["gate1"][str(h)]
            log(f"  [{key}] GATE 1 h={h}: {'PASS' if g['passed'] else 'FAIL'} — {g['detail']}")

    out["runtime_seconds"] = round(time.time() - started, 1)
    (OUT_DIR / "placebo_envelope.json").write_text(json.dumps(out, indent=2, default=str))
    log(f"discovery phase complete in {out['runtime_seconds']}s; wrote placebo_envelope.json and both CSVs")
    log("COMMIT these three files before running --phase holdout (PREREGISTRATION §4).")
    return out


# ---------------------------------------------------------------------------
# Phase 2 — holdout + GATE 2 + persistence
# ---------------------------------------------------------------------------

@dataclass
class PanelArmSummary:
    """One persisted row per (panel, arm). `spec_id`, `sharpe_annualized`,
    `n_trading_days` and `deflated_sharpe` are the four fields
    `persist_cross_sectional_trial_results` requires; everything else rides
    along in `full_result_json`."""

    spec_id: str
    panel_key: str
    arm: str
    horizon: int
    sharpe_annualized: float
    n_trading_days: int
    deflated_sharpe: DeflatedSharpeResult
    discovery_n_measurable: int
    discovery_n_t_ge_3: int
    discovery_n_t_ge_4: int
    discovery_t_max_abs: float
    holdout_t: float
    holdout_t_after_cost: float
    holdout_mean_turnover: float
    gate1_passed: bool | None
    gate2_passed: bool | None
    note: str
    top_labels: list[str] = field(default_factory=list)


def _summary_row(
    spec, arm: str, scan: ps.ScanResult, holdout: ps.HoldoutResult, gate1, gate2, note: str
) -> PanelArmSummary:
    series = pd.Series(holdout.book_returns)
    dsr = compute_deflated_sharpe(
        holdout.sharpe_annualized,
        series,
        n_trials=ps.TOTAL_PATTERNS,
        sigma_sr_annualized=scan.sigma_sr_annualized,
        periods_per_year=spec.periods_per_year,
    )
    return PanelArmSummary(
        spec_id=f"{spec.key}|{arm}|h{holdout.horizon}",
        panel_key=spec.key,
        arm=arm,
        horizon=holdout.horizon,
        sharpe_annualized=float(holdout.sharpe_annualized),
        n_trading_days=int(holdout.n_bars),
        deflated_sharpe=dsr,
        discovery_n_measurable=scan.n_measurable,
        discovery_n_t_ge_3=scan.n_t_ge_3,
        discovery_n_t_ge_4=scan.n_t_ge_4,
        discovery_t_max_abs=float(scan.t_max_abs),
        holdout_t=float(holdout.t_stat),
        holdout_t_after_cost=float(holdout.t_stat_after_cost),
        holdout_mean_turnover=float(holdout.mean_turnover),
        gate1_passed=gate1,
        gate2_passed=gate2,
        note=note,
        top_labels=list(holdout.top_labels),
    )


def _require_discovery_outputs() -> dict:
    needed = ["patterns_discovery_E.csv", "patterns_discovery_C.csv", "placebo_envelope.json"]
    missing = [n for n in needed if not (OUT_DIR / n).exists()]
    if missing:
        raise SystemExit(
            "REFUSING to touch the holdout window: the discovery phase's outputs "
            f"{missing} are not on disk. PREREGISTRATION §4 fixes that the holdout is "
            "touched once, after §5 is complete and committed. Run --phase discovery first."
        )
    return json.loads((OUT_DIR / "placebo_envelope.json").read_text())


def phase_holdout(log) -> dict:
    started = time.time()
    committed = _require_discovery_outputs()
    out: dict = {
        "phase": "holdout",
        "run_tag": RUN_TAG,
        "family_key": FAMILY_KEY,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "discovery_generated_at_utc": committed.get("generated_at_utc"),
        "patterns_scanned": {
            "per_panel": ps.TOTAL_PATTERNS,
            "horizons": len(ps.HORIZONS),
            "panels": 2,
            "total": ps.TOTAL_PATTERNS * len(ps.HORIZONS) * 2,
        },
    }
    summaries: list[PanelArmSummary] = []

    loaders = [("E", ps.PANEL_E, load_panel_e), ("C", ps.PANEL_C, lambda: load_panel_c("spot"))]
    for key, spec, loader in loaders:
        log(f"panel {key}: reloading and re-deriving discovery (deterministic) ...")
        dates, names, returns, meta = loader()
        real_panel = ps.build_panel(dates, names, returns)
        real_discovery = ps.run_discovery(real_panel, spec)

        # A holdout run against a changed panel must fail loudly, not silently
        # compare against a different discovery than the one committed.
        for h in ps.HORIZONS:
            was = committed[key]["real"][str(h)]
            now = _arm_row(real_discovery[h])
            if (was["n_measurable"], was["n_t_ge_3"]) != (now.n_measurable, now.n_t_ge_3) or not np.isclose(
                was["t_max_abs"], now.t_max_abs, rtol=0, atol=1e-9
            ):
                raise SystemExit(
                    f"panel {key} h={h} no longer reproduces the committed discovery "
                    f"({was} vs {asdict(now)}) — refusing to run the holdout against a moved panel."
                )
        log(f"  panel {key}: discovery reproduces the committed numbers exactly")

        results: dict[int, dict] = {}
        for h in ps.HORIZONS:
            real_holdout = ps.run_holdout(real_panel, spec, real_discovery[h])
            # §6 defines GATE 2 against P1. P2 gets the same holdout leg for
            # reporting only — §5's "if P1 and P2 disagree, P1 decides, and P2
            # is reported" needs a P2 number to report, and a computed number
            # beats leaving the row blank.
            placebo_holdouts: dict[str, list[ps.HoldoutResult]] = {}
            for arm in (ps.ARM_P1, ps.ARM_P2):
                rows_for_arm = []
                for seed in ps.PLACEBO_SEEDS:
                    panel = ps.build_panel(dates, names, ps.placebo_returns(returns, arm, seed))
                    disc = ps.run_discovery(panel, spec, arm=arm, seed=seed, horizons=(h,))[h]
                    rows_for_arm.append(
                        ps.run_holdout(panel, spec, disc, arm=arm, seed=seed, charge_cost=False)
                    )
                placebo_holdouts[arm] = rows_for_arm
            gate2 = ps.evaluate_gate2(real_holdout, placebo_holdouts[ps.ARM_P1])
            gate2_p2 = ps.evaluate_gate2(real_holdout, placebo_holdouts[ps.ARM_P2])
            results[h] = {
                "real": real_holdout,
                "placebo": placebo_holdouts,
                "gate2": gate2,
                "gate2_vs_P2_reported_only": gate2_p2,
            }
            log(
                f"  [{key}] GATE 2 h={h}: {'PASS' if gate2.passed else 'FAIL'} — {gate2.detail}"
                + f"  (after naive cost t={real_holdout.t_stat_after_cost:.4f},"
                + f" mean turnover {real_holdout.mean_turnover:.3f}/bar)"
            )
            log(
                f"  [{key}] GATE 2 vs P2 h={h} (reported only): {gate2_p2.detail} -> "
                + ("real above" if gate2_p2.passed else "real NOT above")
            )

        primary = results[ps.HORIZON_PRIMARY]
        rows = []
        for pattern_idx, label in enumerate(primary["real"].top_labels):
            rows.append({
                "rank": pattern_idx + 1,
                "pattern_id": primary["real"].top_pattern_ids[pattern_idx],
                "label": label,
                "k": len(label),
                "orientation": primary["real"].top_signs[pattern_idx],
                "discovery_t": primary["real"].top_discovery_t[pattern_idx],
                "holdout_t_oriented": primary["real"].top_holdout_t[pattern_idx],
            })
        pd.DataFrame(rows).to_csv(OUT_DIR / f"holdout_top20_{key}.csv", index=False)

        gate1_primary = committed[key]["gate1"][str(ps.HORIZON_PRIMARY)]["passed"]
        out[key] = {
            "panel_meta": meta,
            "gate1": {str(h): committed[key]["gate1"][str(h)] for h in ps.HORIZONS},
            "gate2": {str(h): asdict(results[h]["gate2"]) for h in ps.HORIZONS},
            "gate2_vs_P2_reported_only": {
                str(h): asdict(results[h]["gate2_vs_P2_reported_only"]) for h in ps.HORIZONS
            },
            "holdout_real": {
                str(h): {k: v for k, v in asdict(results[h]["real"]).items() if not k.startswith("book_returns")}
                for h in ps.HORIZONS
            },
            "holdout_real_book_returns_h1": primary["real"].book_returns,
            "overall_verdict": (
                "patterns beyond noise on this data"
                if gate1_primary and results[ps.HORIZON_PRIMARY]["gate2"].passed
                else "NOT beyond noise on this data at this resolution"
            ),
        }

        summaries.append(_summary_row(
            spec, ps.ARM_REAL, real_discovery[ps.HORIZON_PRIMARY], primary["real"],
            gate1_primary, primary["gate2"].passed,
            "real arm: the top-20 discovery patterns held out",
        ))
        for arm in (ps.ARM_P1, ps.ARM_P2):
            envelope = committed[key]["placebo"][arm][str(ps.HORIZON_PRIMARY)]
            best_draw = max(primary["placebo"][arm], key=lambda r: r.t_stat)
            envelope_scan = ps.ScanResult(
                panel_key=key, arm=arm, seed=best_draw.seed, horizon=ps.HORIZON_PRIMARY,
                window="discovery", n_formation_bars=envelope[0]["n_formation_bars"],
                n_measurable=max(r["n_measurable"] for r in envelope),
                n_unmeasurable=min(r["n_unmeasurable"] for r in envelope),
                n_t_ge_3=max(r["n_t_ge_3"] for r in envelope),
                n_t_ge_4=max(r["n_t_ge_4"] for r in envelope),
                t_max_abs=max(r["t_max_abs"] for r in envelope),
                sigma_sr_annualized=real_discovery[ps.HORIZON_PRIMARY].sigma_sr_annualized,
                patterns=[],
            )
            summaries.append(_summary_row(
                spec, arm, envelope_scan, best_draw, None, None,
                f"{arm} envelope row: the discovery fields are the MAXIMUM over the 20 draws "
                "(the quantity GATE 1 compares against) and the holdout fields are the single "
                "draw with the largest holdout t (the quantity GATE 2 compares against). "
                + (
                    "GATE 2 is defined against P1; this arm's holdout leg is reported only (§5)."
                    if arm == ps.ARM_P2 else
                    "This is the arm GATE 1 and GATE 2 are read against."
                ),
            ))

    # §6 secondary: perp-close robustness for Panel C. Reported, never gating.
    log("panel C perp robustness re-run (reported, not gating) ...")
    dates, names, returns, meta = load_panel_c("perp")
    perp_panel = ps.build_panel(dates, names, returns)
    perp_disc = ps.run_discovery(perp_panel, ps.PANEL_C, horizons=(ps.HORIZON_PRIMARY,))[ps.HORIZON_PRIMARY]
    perp_placebo = []
    for seed in ps.PLACEBO_SEEDS:
        panel = ps.build_panel(dates, names, ps.placebo_returns(returns, ps.ARM_P1, seed))
        perp_placebo.append(
            ps.run_discovery(panel, ps.PANEL_C, arm=ps.ARM_P1, seed=seed, horizons=(ps.HORIZON_PRIMARY,))[
                ps.HORIZON_PRIMARY
            ]
        )
    perp_gate1 = ps.evaluate_gate1(perp_disc, perp_placebo)
    perp_holdout = ps.run_holdout(perp_panel, ps.PANEL_C, perp_disc)
    perp_holdout_placebo = [
        ps.run_holdout(
            ps.build_panel(dates, names, ps.placebo_returns(returns, ps.ARM_P1, s)),
            ps.PANEL_C,
            d,
            arm=ps.ARM_P1,
            seed=s,
            charge_cost=False,
        )
        for s, d in zip(ps.PLACEBO_SEEDS, perp_placebo)
    ]
    perp_gate2 = ps.evaluate_gate2(perp_holdout, perp_holdout_placebo)
    out["C_perp_robustness"] = {
        "panel_meta": meta,
        "gate1": asdict(perp_gate1),
        "gate2": asdict(perp_gate2),
        "holdout_real": {k: v for k, v in asdict(perp_holdout).items() if not k.startswith("book_returns")},
        "note": "PREREGISTRATION §2/§6 secondary: perp close instead of spot close. Reported, never gating.",
    }
    log(f"  [C_perp] GATE 1 {'PASS' if perp_gate1.passed else 'FAIL'} — {perp_gate1.detail}")
    log(f"  [C_perp] GATE 2 {'PASS' if perp_gate2.passed else 'FAIL'} — {perp_gate2.detail}")

    out["summaries"] = [asdict(s) for s in summaries]
    out["runtime_seconds"] = round(time.time() - started, 1)

    with SessionLocal() as db:
        written = persist_cross_sectional_trial_results(db, FAMILY_KEY, summaries, run_tag=RUN_TAG)
        read_back = verify_persisted_trial_results(db, RUN_TAG, written, family_key=FAMILY_KEY)
    out["persistence"] = {"rows_written": written, "rows_read_back": read_back}
    log(f"persisted {written} rows under run_tag={RUN_TAG}, read back {read_back}")

    (OUT_DIR / "run_output.json").write_text(json.dumps(out, indent=2, default=str))
    _write_report(out, committed)
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _write_report(out: dict, committed: dict) -> None:
    lines: list[str] = []
    w = lines.append
    w("RULE-FREE PATTERN SCAN vs. PLACEBO — RUN REPORT")
    w("=" * 78)
    w(f"run_tag            {RUN_TAG}")
    w(f"family_key         {FAMILY_KEY}   (a run tag, NOT a registered family)")
    w(f"discovery phase    {out['discovery_generated_at_utc']}  ({committed.get('runtime_seconds')}s)")
    w(f"holdout phase      {out['generated_at_utc']}  ({out['runtime_seconds']}s)")
    w("contract           PREREGISTRATION.md + ADDENDUM_01 + ADDENDUM_02 (same directory)")
    w(
        "patterns scanned   "
        f"{out['patterns_scanned']['per_panel']} per panel x "
        f"{out['patterns_scanned']['horizons']} horizons x {out['patterns_scanned']['panels']} panels "
        f"= {out['patterns_scanned']['total']} (§6: recorded so nothing is hidden)"
    )
    w("")
    for key in ("E", "C"):
        block = out[key]
        cd = committed[key]
        w("-" * 78)
        w(f"PANEL {key} — {cd['panel_meta']['n_bars']} bars x {cd['panel_meta']['n_names']} names")
        w(f"  panel fingerprint sha256 {cd['panel_fingerprint_sha256']}")
        nd = cd["non_degeneracy"]
        w(
            f"  control non-degeneracy (§5): {nd['identical_cells']}/{nd['union_cells']} identical "
            f"(pattern,date) membership cells = {nd['fraction']:.5f}, bar {nd['bar']} -> "
            + ("OK" if nd["passes"] else "DEGENERATE")
        )
        w("")
        w("  GATE 1 (existence) — real vs the 20 P1 draws, discovery window")
        w("    horizon | measurable | N3 real | N3 placebo max | N4 real | Tmax real | Tmax placebo max | verdict")
        for h in ps.HORIZONS:
            g = cd["gate1"][str(h)]
            r = cd["real"][str(h)]
            tag = "PASS" if g["passed"] else "FAIL"
            note = "" if h == ps.HORIZON_PRIMARY else "  (secondary, not gating)"
            w(
                f"    h={h:<6} | {r['n_measurable']:>10} | {g['n3_real']:>7} | {g['n3_placebo_max']:>14} | "
                f"{g['n4_real']:>7} | {g['tmax_real']:>9.4f} | {g['tmax_placebo_max']:>16.4f} | {tag}{note}"
            )
        for h in ps.HORIZONS:
            g2 = cd["gate1_vs_P2_reported_only"][str(h)]
            w(
                f"    P2 (cruder null, reported; §5 'if P1 and P2 disagree, P1 decides') h={h}: "
                f"N3 max {g2['n3_placebo_max']}, Tmax max {g2['tmax_placebo_max']:.4f} -> "
                + ("real above" if g2["passed"] else "real NOT above")
            )
        w("")
        w("  GATE 2 (survival) — the real top-20, oriented, over the holdout")
        for h in ps.HORIZONS:
            g = block["gate2"][str(h)]
            hr = block["holdout_real"][str(h)]
            tag = "PASS" if g["passed"] else "FAIL"
            note = "" if h == ps.HORIZON_PRIMARY else "  (secondary, not gating)"
            w(
                f"    h={h}: t(H_real)={g['t_real']:.4f} vs floor {ps.GATE2_T_FLOOR} and P1 max "
                f"{g['t_placebo_max']:.4f} over {hr['n_bars']} bars -> {tag}{note}"
            )
            w(
                f"        Sharpe {hr['sharpe_annualized']:.4f} annualized; naive cost arm "
                f"t={hr['t_stat_after_cost']:.4f} at {hr['mean_turnover']:.3f} turnover/bar "
                f"({'5' if key == 'E' else '10'} bp one-way)"
            )
            g2 = block["gate2_vs_P2_reported_only"][str(h)]
            w(
                f"        P2 (cruder null, reported only; GATE 2 is defined against P1): "
                f"placebo max {g2['t_placebo_max']:.4f} -> "
                + ("real above" if g2["passed"] else "real NOT above")
            )
        w("")
        w(f"  OVERALL ({key}): {block['overall_verdict']}")
        w("")
        w("  top-20 discovery patterns (h=1), with their own holdout t:")
        w("    rank  pattern    k  orient   discovery t   holdout t")
        hr = block["holdout_real"][str(ps.HORIZON_PRIMARY)]
        for i, label in enumerate(hr["top_labels"]):
            w(
                f"    {i + 1:>4}  {label:<9} {len(label):>2}  {hr['top_signs'][i]:>+6}   "
                f"{hr['top_discovery_t'][i]:>11.4f}   {hr['top_holdout_t'][i]:>9.4f}"
            )
        w("")
    perp = out["C_perp_robustness"]
    w("-" * 78)
    w("SECONDARY — Panel C perp-close robustness re-run (reported, never gating)")
    w(f"  GATE 1: {'PASS' if perp['gate1']['passed'] else 'FAIL'} — {perp['gate1']['detail']}")
    w(f"  GATE 2: {'PASS' if perp['gate2']['passed'] else 'FAIL'} — {perp['gate2']['detail']}")
    w("")
    w("-" * 78)
    w("PERSISTENCE")
    w(f"  {out['persistence']['rows_written']} rows written, {out['persistence']['rows_read_back']} read back")
    w(f"  one row per (panel, arm) under run_tag {RUN_TAG}, family_key {FAMILY_KEY}")
    w("  DSR on those rows is informational only: §6 handles multiple comparisons with the")
    w("  placebo envelope, not with DSR, and no gate reads the DSR field.")
    w("")
    w("LIMITS (PREREGISTRATION §9 plus what this run found)")
    limits = [
        (
            "One alphabet (sign/size bins of the last 3-8 bars); a negative says nothing about "
            "volume-based, multi-scale, cross-asset or level-based shapes."
        ),
        "Daily equities and hourly crypto only; no tick data.",
        (
            "The demeaned outcome tests RELATIVE predictability; a pattern predicting the whole "
            "market's next move is invisible here by design."
        ),
        (
            "The universe is the store's, not a clean point-in-time index; both arms share it. "
            "Under §2's literal 'every ticker' rule Panel E still contains 17 FX quotes and 7 "
            "index symbols (ADDENDUM 02) — 24 of its names are not US equities and two are not "
            "tradable."
        ),
        (
            "The cost arm is naive (bar-by-bar rebalancing) and charges only the pattern-basket "
            "leg, not the short implied by cross-sectional demeaning (ADDENDUM 01 item H) — it "
            "understates."
        ),
        (
            "P1 preserves return MAGNITUDES exactly but not sigma bit-exactly (the 20-bar sample "
            "std is taken about a window mean that a sign flip moves), and it leaves the placebo "
            "arm with no market factor for the demeaning to remove (ADDENDUM 01 item A)."
        ),
        (
            "Most k=8 patterns are unmeasurable on both panels: a few thousand names divided over "
            "6,561 codes cannot put the name floor on a bar for most of them. The scan's real "
            "resolution is k=3 and the common k=5 shapes; the measurable counts above say how many."
        ),
    ]
    for i, item in enumerate(limits, start=1):
        w(f"  {i}. {item}")
    (OUT_DIR / "RUN_REPORT.txt").write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["discovery", "holdout"], required=True)
    args = parser.parse_args()

    def log(message: str) -> None:
        print(message, flush=True)

    if args.phase == "discovery":
        phase_discovery(log)
    else:
        phase_holdout(log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
