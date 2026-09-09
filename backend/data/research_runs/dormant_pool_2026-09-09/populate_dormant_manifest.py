#!/usr/bin/env python
"""Populate the Dormant pool from the owner-signed triage list (2026-09-09).

The owner signed DORMANT_POOL_GATES_RESULT.md's "Proposed triage" on
2026-09-09. This script turns that signature into manifest entries, ONE
family at a time, measuring everything an entry needs instead of asserting it:

  * the frozen spec = the family's best net-Sharpe spec in its LATEST
    persisted run (baseline cost arm where the family persists arms);
  * window_end_at_entry = the persisted run's window end, found by matching
    the re-run's observation count to the persisted n_observations (walking
    back from the run's computed_at date);
  * phi_hat_entry and the bucket from the re-run's pre-entry series;
  * pit_ok = the pre-entry drift check passes (|drift| <= DRIFT_FLAG_ABS) AND
    the family is not in KNOWN_REPRODUCIBILITY_GAPS;
  * rescorable = the family is in dormant_rescore's registry (it is, or it
    would not be here) and its pattern was actually captured.

Entry rule applied (stated, because the triage table did not spell it out):
a family enters only if its best persisted spec has POSITIVE net Sharpe —
a Dormant look promotes on out-of-sample evidence for the frozen spec, and
a spec that was negative in sample has nothing to promote. Families whose
best spec is negative are recorded in the report as "nothing to park".

Output: dormant_pool_manifest.staged.json (entries, resumable: a family
already staged is skipped) and POPULATE_REPORT.md. The real manifest is
written by hand from the staged file after review. A real (non-demo) look
record is persisted for every staged entry.

Run from backend/:  nohup python data/research_runs/dormant_pool_2026-09-09/populate_dormant_manifest.py > populate.log 2>&1 &
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.research_lab import metrics  # noqa: E402
from app.services.research_lab.dormant_pool import (  # noqa: E402
    DormantEntry,
    assign_bucket,
    lag1_autocorrelation,
    parse_entry,
)

_spec = importlib.util.spec_from_file_location("dormant_rescore", HERE / "dormant_rescore.py")
dr = importlib.util.module_from_spec(_spec)
sys.modules["dormant_rescore"] = dr
_spec.loader.exec_module(dr)

STAGED = HERE / "dormant_pool_manifest.staged.json"
REPORT = HERE / "POPULATE_REPORT.md"
ENTERED_AT = date(2026, 9, 9)  # the owner's sign-off date

# family_key -> (triage line, mechanism_review pointer). Only families the
# triage put in "-> Dormant candidates" or "review individually", that are
# rescorable, and that are neither Active nor closed on mechanism/structure.
CANDIDATES = {
    "asset_growth": ("statistical close, power never computed", "data/research_runs/asset_growth_2026-09-01 (Cooper-Gulen-Schill): no mechanism-absence finding recorded"),
    "residual_momentum": ("statistical close, power never computed", "data/research_runs/residual_momentum_2026-09-02: no mechanism-absence finding recorded"),
    "best_ideas_13f": ("statistical close, power never computed", "data/research_runs/best_ideas_13f_2026-09-02: no mechanism-absence finding recorded"),
    "ivol": ("statistical close", "criteria_audit family_power.csv row; no mechanism-absence finding"),
    "buyback": ("statistical close", "no mechanism-absence finding recorded"),
    "bonds": ("statistical close", "no mechanism-absence finding recorded"),
    "fx": ("statistical close", "no mechanism-absence finding recorded"),
    "commodities": ("statistical close", "no mechanism-absence finding recorded"),
    "vol_regime": ("statistical close", "signature library found a VIX-term-structure claim bug (2026-09-03); no mechanism-absence finding"),
    "dividend_month_premium": ("statistical close", "no mechanism-absence finding recorded"),
    "dividend_payment_pressure": ("statistical close", "data/research_runs/dividend_payment_pressure_2026-09-06: no mechanism-absence finding"),
    "earnings_announcement_premium": ("statistical close", "no mechanism-absence finding recorded"),
    "pead_ear": ("statistical close", "no mechanism-absence finding recorded"),
    "insider_opportunistic": ("statistical close", "no mechanism-absence finding recorded"),
    "index_removal": ("statistical close", "no mechanism-absence finding recorded"),
    "liquidity_shock_delta_illiq": ("statistical close", "no mechanism-absence finding recorded"),
    "correlation_risk_premium": ("statistical close", "no mechanism-absence finding recorded"),
    "country_valmom": ("statistical close", "no mechanism-absence finding recorded"),
    "tax_loss_selling_turn_of_year": ("statistical close", "data/research_runs/tax_loss_selling_2026-09-06: markup mechanism not tested absent; KNOWN_REPRODUCIBILITY_GAPS"),
    "small_cap_tax_loss_selling_turn_of_year": ("statistical close", "as tax_loss_selling_turn_of_year"),
    "small_cap_disposition": ("statistical close (small-cap twin)", "no mechanism-absence finding recorded"),
    "small_cap_ivol": ("statistical close (small-cap twin)", "no mechanism-absence finding recorded"),
    "same_calendar_month_seasonality": ("statistical close", "no mechanism-absence finding recorded"),
    "rebalancing_pressure": ("statistical close", "data/research_runs/rebalancing_pressure_2026-09-06: no mechanism-absence finding"),
    "margin_credit": ("statistical close", "data/research_runs/margin_credit_2026-09-06: no mechanism-absence finding"),
    "ipo_lockup_expiration": ("review individually: sign reversed", "data/research_runs/ipo_lockup_2026-09-06: sign reversed; power not computed"),
    "jump_drift": ("review individually", "no mechanism-absence finding recorded"),
    "eigenportfolio_statarb": ("review individually", "no mechanism-absence finding recorded"),
    "round_c": ("statistical close (re-admitted patterns)", "no mechanism-absence finding recorded"),
    "patterns_d2": ("statistical close", "no mechanism-absence finding recorded"),
}
# Excluded on purpose, with the reason, so the report is complete:
EXCLUDED = {
    "quarter_end_marking": "closed on MECHANISM (markup leg absent) — triage row 1",
    "small_cap_quarter_end_marking": "as quarter_end_marking",
    "quality_cbop": "Active", "lazy_prices": "Active", "short_interest": "Active", "crypto": "Active (xc_btcbeta)",
    "quality_noa_industry_neutral": "retired on mechanism review (2026-09-04)",
    "quality_noa": "superseded by quality_noa_industry_neutral; not in the triage",
    "intraday_momentum_spy": "owner decision 2026-09-09: closed (headline predictor reversed)",
}


def latest_rows(family_key: str) -> list:
    from app.db import SessionLocal
    from app.models.cross_sectional_trial_result import CrossSectionalTrialResult as T

    db = SessionLocal()
    try:
        rows = db.query(T).filter(T.family_key == family_key).all()
        if not rows:
            return []
        latest_tag = max(rows, key=lambda r: r.computed_at).run_tag
        out = []
        for r in rows:
            if r.run_tag != latest_tag:
                continue
            j = json.loads(r.full_result_json)
            out.append({
                "id": r.id, "trial_id": r.trial_id, "run_tag": r.run_tag, "computed_at": r.computed_at,
                "sharpe": float(r.sharpe_annualized), "n_obs": int(r.n_observations), "json": r.full_result_json,
                "cost_arm": j.get("cost_arm") or j.get("arm"), "is_control": bool(j.get("is_control", False)),
            })
        return out
    finally:
        db.close()


# MOST FAMILIES DO NOT PERSIST is_control (checked 2026-09-09: only
# dividend_payment_pressure, ipo_lockup, margin_credit and intraday do), so
# the flag alone silently admitted a PLACEBO as the frozen spec for
# tax_loss_selling (tls_jun_placebo_signed_h21, the family's highest net
# Sharpe). Controls are therefore also matched by name. The token list was
# derived by scanning every distinct trial_id in the trial store: it matches
# exactly the placebo/control specs of intraday_momentum_spy, ipo_lockup,
# quarter_end_marking (+small cap), residual_momentum, tax_loss (+small cap)
# and same_calendar_month_seasonality, with no false positives.
CONTROL_NAME = re.compile(r"placebo|control|shuffle|sham|random|_null|permut", re.IGNORECASE)

# A Dormant look scores the segment AFTER window_end_at_entry as out-of-sample.
# A spec whose construction is fitted on the WHOLE sample breaks that: re-running
# it to today refits using the extension itself, so the extension is not
# out-of-sample and its PSR is not a valid test. margin_credit's `insample`
# estimation mode is exactly this ("fits Eq. (1) once on the whole sample",
# margin_credit_timing.py) and it is the only family in the store with such
# specs (12 of them); its `recursive` mode is the point-in-time counterpart.
LOOKAHEAD_NAME = re.compile(r"insample|in_sample|full_?sample|look_?ahead", re.IGNORECASE)


def is_lookahead_spec(row: dict) -> bool:
    return bool(LOOKAHEAD_NAME.search(row["trial_id"]))


def is_control_spec(row: dict) -> bool:
    return bool(row["is_control"]) or bool(CONTROL_NAME.search(row["trial_id"]))


def choose_spec(rows: list) -> dict | None:
    arms = {r["cost_arm"] for r in rows if r["cost_arm"]}
    if arms:
        base = [r for r in rows if r["cost_arm"] == "baseline"]
        rows = base or rows
    controls = [r for r in rows if is_control_spec(r)]
    candidates = [r for r in rows if not is_control_spec(r) and not is_lookahead_spec(r)]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: r["sharpe"])
    if best["sharpe"] <= 0:
        return None
    # An honest attribution note, not a filter: this project's families carry
    # placebo legs precisely so a mechanism-free construction that reproduces
    # the result is visible. If one matches or beats the frozen spec, the
    # entry says so where a human reads it.
    if controls:
        top_control = max(controls, key=lambda r: r["sharpe"])
        if top_control["sharpe"] >= best["sharpe"]:
            best = dict(best, attribution_warning=(
                f"ATTRIBUTION WARNING: the control/placebo spec {top_control['trial_id']} "
                f"(net Sharpe {top_control['sharpe']:+.4f}) matches or beats this spec "
                f"({best['sharpe']:+.4f}) in the same run. A mechanism-free construction "
                f"reproducing the result is evidence against the family, and this entry "
                f"should be reviewed before any promotion. "))
    return best


def find_cut(series: pd.Series, computed_at: datetime, n_obs: int) -> date | None:
    """The latest date at or before computed_at such that the series has
    exactly n_obs observations up to it; None if no cut matches."""
    idx = pd.DatetimeIndex(series.index)
    d = computed_at.date()
    for _ in range(40):
        n = int((idx <= pd.Timestamp(d)).sum())
        if n == n_obs:
            return d
        if n < n_obs:
            return None
        d -= timedelta(days=1)
    return None


def load_staged() -> dict:
    if STAGED.exists():
        return json.loads(STAGED.read_text())
    return {"schema": "dormant_pool/v1", "staged_from": "owner-signed triage 2026-09-09", "entries": [], "skipped": {}}


def save_staged(payload: dict) -> None:
    STAGED.write_text(json.dumps(payload, indent=2) + "\n")


def report(line: str) -> None:
    with REPORT.open("a") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    end = date.today()  # noqa: DTZ011
    staged = load_staged()
    done = {e["family_key"] for e in staged["entries"]} | set(staged["skipped"])
    if not REPORT.exists():
        REPORT.write_text("# Dormant pool population report (2026-09-09, owner-signed triage)\n\n")
    for family_key, (triage, mech) in CANDIDATES.items():
        if family_key in done:
            continue
        t0 = time.time()
        rows = latest_rows(family_key)
        if not rows:
            staged["skipped"][family_key] = "no persisted rows"; save_staged(staged)
            report(f"- {family_key}: SKIP, no persisted rows"); continue
        spec = choose_spec(rows)
        if spec is None:
            # Report the best NON-CONTROL spec, which is what the rule tests.
            # Printing the overall best produced a false line for
            # same_calendar_month_seasonality ("+0.234 <= 0"): that Sharpe
            # belonged to the family's PLACEBO, which is itself a finding.
            cands = [r for r in rows if not is_control_spec(r)]
            ctrls = [r for r in rows if is_control_spec(r)]
            best_c = max(cands, key=lambda r: r["sharpe"]) if cands else None
            top_ctrl = max(ctrls, key=lambda r: r["sharpe"]) if ctrls else None
            why = ("no non-control spec exists" if best_c is None
                   else f"best candidate spec {best_c['trial_id']} net Sharpe {best_c['sharpe']:+.4f} is not positive")
            if top_ctrl is not None and top_ctrl["sharpe"] > (best_c["sharpe"] if best_c else 0.0):
                why += (f"; its control/placebo {top_ctrl['trial_id']} scores {top_ctrl['sharpe']:+.4f}, ABOVE every "
                        "candidate spec - evidence against the family, not for it")
            staged["skipped"][family_key] = f"nothing to park: {why}"
            save_staged(staged)
            report(f"- {family_key}: nothing to park ({why})"); continue
        try:
            captured = dr.run_family_and_capture(family_key, end)
        except Exception as exc:  # noqa: BLE001
            staged["skipped"][family_key] = f"re-run FAILED: {type(exc).__name__}: {str(exc)[:200]}"; save_staged(staged)
            report(f"- {family_key}: re-run FAILED {type(exc).__name__}: {str(exc)[:200]}"); continue
        if spec["trial_id"] not in captured:
            staged["skipped"][family_key] = f"pattern {spec['trial_id']} not captured ({len(captured)} captured)"; save_staged(staged)
            report(f"- {family_key}: pattern {spec['trial_id']} not captured; captured {sorted(captured)[:6]}"); continue
        series = pd.Series(captured[spec["trial_id"]], dtype=float).dropna().sort_index()
        ppy = float(dr.DEMO_PERIODS_PER_YEAR.get(family_key, metrics.TRADING_DAYS_PER_YEAR))
        cut = find_cut(series, spec["computed_at"], spec["n_obs"])
        n_match = cut is not None
        if cut is None:
            cut = spec["computed_at"].date()
        pre = series[pd.DatetimeIndex(series.index) <= pd.Timestamp(cut)]
        phi = lag1_autocorrelation(pre) if len(pre) >= 3 and float(pre.std(ddof=1)) > 0 else 0.0
        sharpe_pre = metrics.sharpe_ratio(pre, periods_per_year=ppy) if len(pre) >= 20 else None
        drift = None if sharpe_pre is None else float(sharpe_pre - spec["sharpe"])
        # A small-cap twin runs the SAME construction on a different universe,
        # so it inherits its parent's reproducibility doubt. Without this,
        # small_cap_tax_loss_selling_turn_of_year was given pit_ok=True while
        # tax_loss_selling_turn_of_year itself was not.
        base = family_key[len("small_cap_"):] if family_key.startswith("small_cap_") else family_key
        gap = family_key in dr.KNOWN_REPRODUCIBILITY_GAPS or base in dr.KNOWN_REPRODUCIBILITY_GAPS
        pit_ok = bool(n_match and drift is not None and abs(drift) <= dr.DRIFT_FLAG_ABS and not gap)
        entry_payload = {
            "family_key": family_key,
            "pattern_id": spec["trial_id"],
            "spec_fingerprint": f"{family_key}/{spec['trial_id']}@{spec['run_tag']}#row{spec['id']}",
            "config_fingerprint": "sha256:" + hashlib.sha256(spec["json"].encode()).hexdigest()[:24],
            "window_end_at_entry": cut.isoformat(),
            "entered_at": ENTERED_AT.isoformat(),
            "periods_per_year": ppy,
            "phi_hat_entry": float(phi),
            "bucket": assign_bucket(float(phi)),
            "pit_ok": pit_ok,
            "rescorable": True,
            "mechanism_review": mech,
            "entry_rationale": (
                spec.get("attribution_warning", "") +
                f"Owner-signed triage 2026-09-09 ({triage}). Persisted net Sharpe {spec['sharpe']:+.4f} on n={spec['n_obs']} "
                f"(run {spec['run_tag']}); criteria_fix family_power.csv records under 80 percent power at a true 0.5 for every family. "
                f"Re-run pre-entry Sharpe {sharpe_pre if sharpe_pre is None else round(sharpe_pre, 4)} (drift {None if drift is None else round(drift, 4)}), "
                f"n_match={n_match}, known_gap={gap}, giving pit_ok={pit_ok}."
            ),
        }
        try:
            entry = parse_entry(entry_payload, family_key)  # validates
            rec = dr.score_series(series, entry, persisted_sharpe=spec["sharpe"], data_end=end)
            path = dr.persist(rec)
        except Exception as exc:  # noqa: BLE001 - a bad entry must not end a multi-hour run
            staged["skipped"][family_key] = f"entry REJECTED: {type(exc).__name__}: {str(exc)[:300]}"
            save_staged(staged)
            report(f"- {family_key}: entry REJECTED {type(exc).__name__}: {str(exc)[:200]}")
            continue
        staged["entries"].append(entry_payload); save_staged(staged)
        report(f"- {family_key}/{spec['trial_id']}: persisted {spec['sharpe']:+.4f} n={spec['n_obs']} | cut {cut} n_match={n_match} "
               f"| rerun {sharpe_pre if sharpe_pre is None else f'{sharpe_pre:+.4f}'} drift {None if drift is None else f'{drift:+.4f}'} "
               f"| phi {phi:+.3f} {entry.bucket} | pit_ok={pit_ok} | ext {rec.n_extension} look {rec.look_index} | {path.name} | {time.time()-t0:.0f}s")
    for k, why in EXCLUDED.items():
        if k not in staged["skipped"]:
            staged["skipped"][k] = "excluded: " + why
    save_staged(staged)
    report(f"\nstaged {len(staged['entries'])} entries; skipped {len(staged['skipped'])}. Staged file: {STAGED.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
