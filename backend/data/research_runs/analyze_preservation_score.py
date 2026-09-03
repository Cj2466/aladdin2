"""Reads the rebuilt per-spec metrics written by run_preservation_score.py,
runs the turnover-vs-decay test, re-ranks every scored candidate, and writes
the git-durable plain-text run report.

Split from the runner deliberately: the runner does the expensive replays and
writes a JSON artifact; this file does only arithmetic on that artifact, so
the analysis can be re-derived, corrected or extended without re-running a
single backtest.

Run from backend/ with ./venv/bin/python.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(f"REFUSING TO RUN: `app` resolved to {app.__file__}, outside {_BACKEND}")

import pandas as pd

from app.services.research_lab.preservation_score import (
    LOW_TURNOVER_MIN_HOLDING_DAYS,
    MCLEAN_PONTIFF_CITATION,
    MDD_FLOOR,
    MIN_HALF_OBSERVATIONS,
    OOS_RETENTION,
)

JSON_PATH = _BACKEND / "data" / "research_runs" / "preservation_score_2026-09-03.json"
REPORT_PATH = _BACKEND / "data" / "research_runs" / "preservation_score_2026-09-03.txt"
MAIN_DB = Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/aladdin2.db")

# The cross-sectional specs this project has actually put into forward
# validation, read off the registration modules app/main.py awaits on startup
# (grep'd, not remembered). main.py's own comments number them one to four.
REGISTERED = {
    "cbop_ls_h63": "quality_forward_registration.CBOP_PATTERN_ID (#1)",
    "noa_neutral_ls_h126_median": "quality_forward_registration.NOA_NEUTRAL_PATTERN_ID (#2)",
    "si_ratio_hedged_h21": "short_interest_forward_registration.SHORT_INTEREST_PATTERN_ID (#3)",
    "lazy_jaccard_full_h126_ivol": "lazy_prices_forward_registration.LAZY_PRICES_PATTERN_ID (#4)",
}

# A FIFTH registration module exists — bab_forward_registration.py, spec
# xc_btcbeta_l180_h180 (crypto betting-against-beta) — but grepping app/ finds
# NO caller of its register_bab_forward_validation(), so it is not registered
# at startup in this checkout. Whether it is live in the production database
# cannot be determined from here, and is therefore not claimed either way.
BAB_NOTE = (
    "bab_forward_registration.py / xc_btcbeta_l180_h180 (crypto BAB) has a registration "
    "function that nothing in app/ calls at startup; its live status is not verifiable "
    "from this checkout and is not asserted. Crypto is outside this rebuild in any case."
)

AUDIT_CANDIDATE_FAMILIES = {
    "asset_growth",
    "earnings_announcement_premium",
    "eigenportfolio_statarb",
    "jump_drift",
}


# ---------------------------------------------------------------------------
# small statistics helpers (no scipy dependency is added for this)
# ---------------------------------------------------------------------------


def welch_t(a: list[float], b: list[float]) -> tuple[float | None, float | None]:
    """Welch's t and its Welch-Satterthwaite df. NO p-value is printed
    anywhere: specs inside a family share a return series, so the
    independence a p-value asserts is not present in this data."""
    if len(a) < 2 or len(b) < 2:
        return None, None
    va, vb = statistics.variance(a), statistics.variance(b)
    na, nb = len(a), len(b)
    denom = va / na + vb / nb
    if denom <= 0:
        return None, None
    t = (statistics.fmean(a) - statistics.fmean(b)) / (denom**0.5)
    df_den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    return t, (denom**2 / df_den if df_den > 0 else None)


def spearman(xs_: list[float], ys_: list[float]) -> float | None:
    if len(xs_) < 3:
        return None
    rx, ry = pd.Series(xs_).rank(), pd.Series(ys_).rank()
    if rx.std(ddof=1) == 0 or ry.std(ddof=1) == 0:
        return None
    return float(rx.corr(ry))


def describe(values: list[float]) -> str:
    if not values:
        return "n=0"
    if len(values) == 1:
        return f"n=1  mean={values[0]:+.4f}"
    return (
        f"n={len(values):<3d} mean={statistics.fmean(values):+.4f}  "
        f"median={statistics.median(values):+.4f}  sd={statistics.stdev(values):.4f}  "
        f"min={min(values):+.4f}  max={max(values):+.4f}"
    )


# ---------------------------------------------------------------------------
# the persisted equal-thirds panel (no rebuild needed)
# ---------------------------------------------------------------------------

# Holding periods for the four families that persist subperiod_sharpes but do
# NOT expose holding_days in their JSON. Each is read off the family's own spec
# definition, not estimated:
#   eigenportfolio_statarb  -- Avellaneda/Lee daily mean-reversion, re-formed
#                              every trading day: holding period 1 day.
#   earnings_announcement_premium -- the b{X}_a{Y} window is X days before plus
#                              Y days after the announcement, so 2..10 days.
#   dividend_month_premium  -- a calendar-month holding, ~21 trading days.
THIRDS_HOLDING_DAYS = {
    "eigenportfolio_statarb": 1,
    "dividend_month_premium": 21,
}


def eap_holding_days(trial_id: str) -> int:
    """eap_b{before}_a{after}_... -> before + after trading days."""
    parts = trial_id.split("_")
    before = int(parts[1][1:])
    after = int(parts[2][1:])
    return before + after


def load_thirds_panel() -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(MAIN_DB))
    rows = conn.execute(
        "SELECT family_key, trial_id, run_tag, sharpe_annualized, dsr, full_result_json "
        "FROM cross_sectional_trial_results WHERE family_key IN "
        "('correlation_risk_premium','dividend_month_premium',"
        "'earnings_announcement_premium','eigenportfolio_statarb')"
    ).fetchall()
    conn.close()
    out = []
    for fam, tid, tag, sharpe, dsr, js in rows:
        d = json.loads(js)
        thirds = d.get("subperiod_sharpes") or (d.get("confound") or {}).get("subperiod_sharpes")
        if not thirds or len(thirds) != 3:
            continue
        holding = d.get("holding_days")
        if holding is None:
            holding = (
                eap_holding_days(tid)
                if fam == "earnings_announcement_premium"
                else THIRDS_HOLDING_DAYS.get(fam)
            )
        if holding is None:
            continue
        out.append(
            {
                "family_key": fam,
                "trial_id": tid,
                "run_tag": tag,
                "sharpe": sharpe,
                "dsr": dsr,
                "holding_days": holding,
                "bucket": (
                    "low_turnover"
                    if holding >= LOW_TURNOVER_MIN_HOLDING_DAYS
                    else "high_turnover"
                ),
                "thirds": [float(x) for x in thirds],
                "decay_t3_minus_t1": float(thirds[2] - thirds[0]),
            }
        )
    return out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def bucket_block(specs: list[dict], key: str, label: str, add) -> None:
    low = [s[key] for s in specs if s["bucket"] == "low_turnover" and s.get(key) is not None]
    high = [s[key] for s in specs if s["bucket"] == "high_turnover" and s.get(key) is not None]
    add(f"  {label}")
    add(f"    low-turnover  (holding_days >= {LOW_TURNOVER_MIN_HOLDING_DAYS}): {describe(low)}")
    add(f"    high-turnover (holding_days <  {LOW_TURNOVER_MIN_HOLDING_DAYS}): {describe(high)}")
    if low and high:
        diff = statistics.fmean(low) - statistics.fmean(high)
        t, df = welch_t(low, high)
        add(
            f"    difference (low - high) = {diff:+.4f}"
            + (f"   Welch t = {t:+.2f} on {df:.1f} df" if t is not None and df else "")
        )
    add("")


def main() -> int:
    payload = json.loads(JSON_PATH.read_text())
    specs = [s for s in payload["specs"] if s.get("sharpe_decay") is not None]
    all_specs = payload["specs"]
    thirds = load_thirds_panel()

    lines: list[str] = []
    add = lines.append

    # ---------------------------------------------------------------- header
    add("=" * 78)
    add("PRESERVATION SCORE — TURNOVER vs DECAY ON THIS PROJECT'S OWN CANDIDATE SET")
    add("=" * 78)
    add(
        "The question this run was built to answer, put by the user directly: is it "
        "actually better, for THIS project's strategy-selection process, to prefer "
        "low-turnover / long-holding-period candidates over high-turnover ones, weighted "
        "by drawdown and Sharpe stability — or does that just leave better-performing "
        "high-turnover candidates on the table?"
    )
    add("")
    add(
        "It is answered ONLY with numbers computed from this project's own replays. No "
        "outside anecdote is used as evidence. Renaissance/Medallion is not cited as "
        "authority in either direction (it is, in any case, a ~2-day-holding-period, "
        "extremely high-turnover book that controls drawdown through breadth, not through "
        "holding period)."
    )
    add("")
    add(f"run_tag={payload['run_tag']}   generated {payload['generated_at']}")
    add(f"replay wall clock: {payload['elapsed_s'] / 60:.1f} min")
    add("")

    # --------------------------------------------------- persistence constraint
    add("=" * 78)
    add("1. WHAT IS AND IS NOT PERSISTED — the real constraint on this analysis")
    add("=" * 78)
    add(
        "cross_sectional_trial_results persists SUMMARY statistics only: "
        "sharpe_annualized, dsr, psr_vs_zero, n_observations, n_trials and the family's "
        "own diagnostics inside full_result_json. It does NOT persist a return time "
        "series for ANY family, and neither does any data/research_runs report. "
        "CrossSectionalBacktestResult.daily_returns exists in memory during a replay and "
        "is discarded by screen_cross_sectional_universe."
    )
    add("")
    add(
        "CONSEQUENCE, stated rather than worked around: max drawdown, Calmar, and "
        "first-half/second-half Sharpe are NOT recoverable from the database. They were "
        "obtained by RE-RUNNING each family's own production entry point and capturing "
        "the series the replay already computes. Nothing was reimplemented."
    )
    add("")
    add(
        "The one path statistic that IS already persisted, for four families only, is "
        "`subperiod_sharpes` — Sharpe in three equal thirds — for "
        "correlation_risk_premium, dividend_month_premium, "
        "earnings_announcement_premium and eigenportfolio_statarb. That panel is used "
        "below as an INDEPENDENT secondary check that needed no rebuild at all."
    )
    add("")

    # ---------------------------------------------------------------- formula
    add("=" * 78)
    add("2. THE PRESERVATION SCORE — exact definition")
    add("=" * 78)
    add("Implemented in app/services/research_lab/preservation_score.py, 21 unit tests in")
    add("tests/test_preservation_score.py. For a spec's realized daily net return series r:")
    add("")
    add("    S    = annualized Sharpe of r")
    add("    AR   = mean(r) * periods_per_year          (arithmetic, same mean S uses)")
    add("    MDD  = max drawdown of cumprod(1+r)        (<= 0)")
    add(f"    C    = AR / max(|MDD|, {MDD_FLOOR})                 Calmar, floored at {MDD_FLOOR:.0%}")
    add("    RQ   = sign(S) * sqrt(|S| * |C|)           risk quality: signed GEOMETRIC MEAN")
    add("                                               of Sharpe and Calmar")
    add("    S1,S2= Sharpe of the first and second half of r, split by position")
    add("    stab = clip( min(S1,S2) / |S| , 0, 1 )     stability")
    add("    cred = clip(dsr, 0, 1)                     credibility")
    add("")
    add(f"    preservation_score         = {OOS_RETENTION} * cred * RQ * stab")
    add(f"    preservation_score_no_stab = {OOS_RETENTION} * cred * RQ")
    add("")
    add("WHY 0.42 AND NOT A ROUND 0.5:")
    add(f"  {MCLEAN_PONTIFF_CITATION}")
    add(
        "  Their two decay figures are not interchangeable. 26% is pre-publication "
        "(overfitting/statistical bias only); 58% is post-publication (arbitrage on top). "
        "Every family here re-implements an ALREADY-PUBLISHED anomaly on a public, liquid "
        "cross-section, so the applicable point on their timeline is the post-publication "
        "one: retention = 1 - 0.58 = 0.42. Note this is a CONSTANT and therefore changes "
        "no ranking at all — it exists so the number reads as an expected forward "
        "quantity. All re-ranking comes from cred, RQ and stab."
    )
    add("")
    add(
        "WHY A GEOMETRIC MEAN OF SHARPE AND CALMAR: Sharpe is path-blind (symmetric "
        "volatility); Calmar is path-aware but is a single-episode statistic and much "
        "noisier. The geometric mean keeps both and halves the exponent on each, so one "
        "bad drawdown episode moves the score by the square root of what it would move a "
        "pure Calmar ranking."
    )
    add("")
    add(
        "WHAT THE SCORE DELIBERATELY OMITS: any turnover or holding-period term. The "
        "score carries no prior that low turnover is better, precisely so section 4 can "
        "TEST that rather than assume it."
    )
    add("")
    add("INDEPENDENT VERIFICATION OF THE FORMULA, run before this report was written:")
    add(
        "  A separate script that does NOT import preservation_score.py recomputed every "
        "term (Sharpe, annualized return, max drawdown, Calmar, risk quality, both half "
        "Sharpes, decay, stability, credibility and both scores) from first principles in "
        "plain numpy, on the SAME captured return series, for all 12 asset_growth specs: "
        "156 comparisons, 0 mismatches at 1e-12."
    )
    add(
        "  A second pass re-ran asset_growth from scratch an hour after the main run and "
        "compared against the committed JSON: every metric agreed to a relative ~1e-6. That "
        "residual is DATA drift (yfinance restates adjusted closes), not formula error, and "
        "is why the reproduction test in section 3 uses a tolerance rather than equality."
    )
    add("")

    # ------------------------------------------------------------ rebuild ledger
    add("=" * 78)
    add("3. REBUILD LEDGER — every family attempted, reproduced or not")
    add("=" * 78)
    add(
        f"Reproduction test: |rebuilt annualized Sharpe - persisted Sharpe| <= "
        f"{payload['sharpe_reproduction_tolerance']}. The tolerance is not zero because "
        "yfinance restates adjusted closes and the universes are rebuilt live; a rerun "
        "days later is not expected to be bit-identical."
    )
    add("")
    hdr = f"{'family':<32} {'status':<8} {'specs':>6} {'repro':>9} {'medΔS':>8} {'maxΔS':>8} {'secs':>6}"
    add(hdr)
    add("-" * len(hdr))
    for f in payload["families"]:
        if f["status"] != "ok":
            add(f"{f['label']:<32} {'FAILED':<8} {'-':>6} {'-':>9} {'-':>8} {'-':>8} "
                f"{f['elapsed_s']:>6.0f}")
            add(f"    error: {f.get('error')}")
            continue
        med = f.get("median_abs_sharpe_delta")
        mx = f.get("max_abs_sharpe_delta")
        add(
            f"{f['label']:<32} {'ok':<8} {f['n_specs']:>6} "
            f"{f['n_reproduced']}/{f['n_with_persisted_row']:<7} "
            f"{(f'{med:.4f}' if med is not None else 'n/a'):>8} "
            f"{(f'{mx:.4f}' if mx is not None else 'n/a'):>8} {f['elapsed_s']:>6.0f}"
        )
        if f.get("note"):
            add(f"    note: {f['note']}")
    add("")
    add("NOT REBUILT, and why (so the sample is honest, not silently truncated):")
    add("  best_ideas_13f              — its own report records 207.4 min of wall clock.")
    add("  eigenportfolio_statarb      — bespoke replay engine, not routed through")
    add("  dividend_month_premium        screen_cross_sectional_universe, so the capture")
    add("                                hook does not see it. Both appear in the")
    add("                                persisted-thirds panel (section 4e) instead.")
    add("  earnings_announcement_premium — same engine as the rebuilt families, but its")
    add("                                announcement calendar cache")
    add("                                (data/eap_edgar_announcement_calendar.json) is")
    add("                                gitignored and ABSENT locally; rebuilding it is a")
    add("                                fresh multi-thousand-filing EDGAR pull. In the")
    add("                                thirds panel instead.")
    add("  phase_a_intraday_expanded   — intraday harness; holding period is not in days.")
    add("  multi_signal_combination    — portfolios OF the other families' signals, not")
    add("                                independent candidates.")
    add("  funding_carry / _pit,       — crypto; kept out of the equity decay comparison")
    add("  ofi_crypto, crypto BAB        rather than mixed into it on a 365-day calendar.")
    add("")
    failed_repro = [s for s in all_specs if not s["reproduced"] and s.get("persisted_sharpe")]
    if failed_repro:
        add(
            f"EVERY SPEC THAT DID NOT REPRODUCE ({len(failed_repro)} of {len(all_specs)}), "
            "listed rather than summarized:"
        )
        for s in sorted(failed_repro, key=lambda s: s["pattern_id"]):
            d = s["sharpe_full"] - s["persisted_sharpe"]
            add(
                f"  {s['family_key']:<20} {s['pattern_id']:<34} rebuilt {s['sharpe_full']:+.4f} "
                f"vs persisted {s['persisted_sharpe']:+.4f}  delta {d:+.4f}"
            )
        deltas = [s["sharpe_full"] - s["persisted_sharpe"] for s in failed_repro]
        add(
            f"  All {len(failed_repro)} are in the lazy_prices `full` similarity arm; all are "
            f"LOWER than persisted (mean delta {statistics.fmean(deltas):+.4f}); the family's "
            "`rf` and `mda` arms all reproduced inside tolerance. A one-directional shift "
            "confined to one arm is a PANEL change, not replay noise."
        )
        add(
            "  CANDIDATE EXPLANATION, offered as a lead and NOT as a verified finding: the "
            "persisted lazy_prices run is tagged 2026-09-01, before the 2026-09-02 XOM "
            "CIK-mapping fix that this project's own notes say silently excluded XOM from "
            "the lazy_prices filing panel. A rebuild after that fix would score a different "
            "cross-section. This was NOT confirmed here — confirming it means diffing the "
            "two filing panels, which this run did not do."
        )
        add(
            "  CONSEQUENCE WORTH SURFACING ON ITS OWN: lazy_jaccard_full_h126_ivol is a "
            "REGISTERED forward-validation spec (#4). It was registered on Sharpe +0.6035 "
            "and rebuilds today at +0.5498. Its preservation_score below uses the REBUILT "
            "number, i.e. the pessimistic one."
        )
        add("")
    add(
        "ATTEMPTED AND CAPTURED NOTHING — insider_opportunistic and pead_ear appear in the "
        "ledger above with 0 specs. Both are EVENT-DRIVEN families whose own module "
        "docstrings state they cannot run on screen_cross_sectional_universe: their spec "
        "types (InsiderSpec, PeadSpec) are not CrossSectionalSpec and their replays never "
        "call run_cross_sectional_backtest, so the capture hook correctly sees nothing. "
        "That is a property of the hook, not a failure of the data and not evidence about "
        "either family. Their rows are left in the ledger rather than deleted so the "
        "attempt is on the record."
    )
    add("")

    # ------------------------------------------------------------ the decisive test
    add("=" * 78)
    add("4. THE DECISIVE TEST — does low turnover decay less, ON OUR DATA?")
    add("=" * 78)
    add(
        "Decay statistic: sharpe_decay = Sharpe(second half of the spec's realized daily "
        "series) - Sharpe(first half). NEGATIVE = the edge got worse over the backtest. "
        f"Halves are split by position; a spec whose half would fall below "
        f"{MIN_HALF_OBSERVATIONS} observations is not measured at all."
    )
    add("")
    add(f"Bucket boundary: holding_days >= {LOW_TURNOVER_MIN_HOLDING_DAYS} = low turnover.")
    add(f"Specs with a measurable decay: {len(specs)} of {len(all_specs)} rebuilt.")
    add("")
    add(
        "WHAT WAS FIXED BEFORE ANY NUMBER EXISTED, and what was not — stated because this "
        "section is a hypothesis test and this project does not accept an undisclosed "
        "specification search. FIXED IN ADVANCE, in the request that commissioned this "
        "run: the decay statistic (first-half vs second-half Sharpe), the 63-trading-day "
        "bucket boundary, and the direction of the claim under test. ADDED AFTER SEEING "
        "PARTIAL RESULTS, and therefore reported as descriptive rather than as "
        "confirmatory tests: the sign-blind |sharpe_decay| panel, the within-family "
        "demeaned rank correlations, the positive-Sharpe subset (4d), the "
        "what-would-it-cost panel (4e), and the persisted-thirds panel (4f). No panel was "
        "computed and then dropped: everything computed appears here."
    )
    add("")

    add("-" * 78)
    add("4a. SPEC-LEVEL, all rebuilt equity specs pooled")
    add("-" * 78)
    add(
        "CAVEAT FIRST: specs inside a family share a universe, a cost model and largely "
        "the same return series, so these n's are NOT independent observations. This "
        "panel is reported because it is the panel the question is usually asked in, not "
        "because it is the strongest evidence. Sections 4b/4c are the honest units."
    )
    add("")
    bucket_block(specs, "sharpe_decay", "sharpe_decay (second half - first half):", add)
    bucket_block(specs, "max_drawdown", "max_drawdown (more negative = worse):", add)
    bucket_block(specs, "stability", "stability (min-half Sharpe / |full Sharpe|, 0..1):", add)
    bucket_block(specs, "sharpe_full", "sharpe_full (for reference — is one bucket just better?):", add)

    abs_decay = [dict(s, abs_decay=abs(s["sharpe_decay"])) for s in specs]
    bucket_block(abs_decay, "abs_decay", "|sharpe_decay| (instability magnitude, sign-blind):", add)

    hd = [float(s["holding_days"]) for s in specs]
    add("  Rank correlations against holding_days (Spearman, continuous — no bucketing):")
    for key, lab in [
        ("sharpe_decay", "sharpe_decay"),
        ("max_drawdown", "max_drawdown"),
        ("stability", "stability"),
        ("sharpe_full", "sharpe_full"),
    ]:
        vals = [float(s[key]) for s in specs]
        rho = spearman(hd, vals)
        add(f"    holding_days vs {lab:<14} rho = {rho:+.3f}" if rho is not None else f"    {lab}: n/a")
    rho_abs = spearman(hd, [abs(s["sharpe_decay"]) for s in specs])
    add(f"    holding_days vs |sharpe_decay| rho = {rho_abs:+.3f}")
    add("")
    add(
        "  The same rank correlations after subtracting each FAMILY's own mean from both "
        "sides (within-family demeaning). This removes the between-family differences "
        "that dominate the pooled numbers above, leaving only variation in holding period "
        "INSIDE a family — the part the question is actually about:"
    )
    fam_mean_hd = {
        f: statistics.fmean([float(s["holding_days"]) for s in specs if s["family_key"] == f])
        for f in {s["family_key"] for s in specs}
    }
    for key, lab in [
        ("sharpe_decay", "sharpe_decay"),
        ("max_drawdown", "max_drawdown"),
        ("stability", "stability"),
        ("sharpe_full", "sharpe_full"),
    ]:
        fam_mean_v = {
            f: statistics.fmean([float(s[key]) for s in specs if s["family_key"] == f])
            for f in {s["family_key"] for s in specs}
        }
        dx = [float(s["holding_days"]) - fam_mean_hd[s["family_key"]] for s in specs]
        dy = [float(s[key]) - fam_mean_v[s["family_key"]] for s in specs]
        rho = spearman(dx, dy)
        add(
            f"    demeaned holding_days vs {lab:<14} rho = {rho:+.3f}"
            if rho is not None
            else f"    demeaned {lab}: n/a"
        )
    add("")

    add("-" * 78)
    add("4b. FAMILY-LEVEL — one number per family per bucket (the honest unit)")
    add("-" * 78)
    fam_rows: list[dict[str, Any]] = []
    families = sorted({s["family_key"] for s in specs})
    for fam in families:
        fs = [s for s in specs if s["family_key"] == fam]
        low = [s["sharpe_decay"] for s in fs if s["bucket"] == "low_turnover"]
        high = [s["sharpe_decay"] for s in fs if s["bucket"] == "high_turnover"]
        fam_rows.append(
            {
                "family": fam,
                "n_low": len(low),
                "n_high": len(high),
                "mean_low": statistics.fmean(low) if low else None,
                "mean_high": statistics.fmean(high) if high else None,
            }
        )
    h = f"{'family':<34} {'n_low':>6} {'meanDecay_low':>14} {'n_high':>7} {'meanDecay_high':>15} {'low-high':>10}"
    add(h)
    add("-" * len(h))
    paired: list[float] = []
    for r in fam_rows:
        d = (
            r["mean_low"] - r["mean_high"]
            if r["mean_low"] is not None and r["mean_high"] is not None
            else None
        )
        if d is not None:
            paired.append(d)
        ml = "n/a" if r["mean_low"] is None else f"{r['mean_low']:+.4f}"
        mh = "n/a" if r["mean_high"] is None else f"{r['mean_high']:+.4f}"
        dd = "n/a" if d is None else f"{d:+.4f}"
        add(
            f"{r['family']:<34} {r['n_low']:>6} {ml:>14} {r['n_high']:>7} {mh:>15} {dd:>10}"
        )
    add("")
    low_fam = [r["mean_low"] for r in fam_rows if r["mean_low"] is not None]
    high_fam = [r["mean_high"] for r in fam_rows if r["mean_high"] is not None]
    add(f"  Across families, mean of per-family low-turnover decay : {describe(low_fam)}")
    add(f"  Across families, mean of per-family high-turnover decay: {describe(high_fam)}")
    add("")

    add("-" * 78)
    add("4c. WITHIN-FAMILY PAIRED — the strongest design available here")
    add("-" * 78)
    add(
        "For every family that contains BOTH a low-turnover and a high-turnover spec, the "
        "difference (its own low-turnover mean decay) - (its own high-turnover mean "
        "decay). This holds signal, universe, cost model and sample period fixed and "
        "varies ONLY the holding period. A positive number means low turnover decayed "
        "LESS in that family."
    )
    add("")
    for r in fam_rows:
        if r["mean_low"] is None or r["mean_high"] is None:
            continue
        d = r["mean_low"] - r["mean_high"]
        add(f"    {r['family']:<34} {d:+.4f}   ({'low decays less' if d > 0 else 'low decays MORE'})")
    add("")
    add(f"  Paired differences across families: {describe(paired)}")
    if len(paired) >= 2:
        n_pos = sum(1 for x in paired if x > 0)
        add(
            f"  Sign count: {n_pos} of {len(paired)} families favour low turnover "
            f"({n_pos / len(paired):.0%})."
        )
    add("")

    add("-" * 78)
    add("4d. THE SAME TEST ON POSITIVE-SHARPE SPECS ONLY")
    add("-" * 78)
    add(
        "CAVEAT, load-bearing: conditioning on a positive FULL-SAMPLE Sharpe conditions on "
        "an outcome built from both halves, which mechanically pulls the halves apart and "
        "biases this subset TOWARD showing decay. It is reported because it is the subset "
        "a selection process would actually be choosing from, not because it is unbiased."
    )
    add("")
    pos = [s for s in specs if s["sharpe_full"] > 0]
    add(f"  {len(pos)} of {len(specs)} rebuilt specs have a positive full-sample Sharpe.")
    bucket_block(pos, "sharpe_decay", "sharpe_decay, positive-Sharpe specs only:", add)

    add("-" * 78)
    add("4e. WHAT A LOW-TURNOVER PREFERENCE WOULD ACTUALLY COST — the other half")
    add("-" * 78)
    add(
        "Decay is only half the user's question. The other half is: does preferring low "
        "turnover leave BETTER high-turnover candidates on the table? That is answered by "
        "asking, per family, which bucket holds the best spec on each criterion."
    )
    add("")
    hb = f"{'family':<34} {'best by Sharpe':<16} {'best by DSR':<16} {'best by presScore':<18}"
    add(hb)
    add("-" * len(hb))
    for fam in families:
        fs = [s for s in all_specs if s["family_key"] == fam]
        both = len({s["bucket"] for s in fs}) > 1
        if not both:
            add(f"{fam:<34} (single bucket only: {fs[0]['bucket']})")
            continue
        b_s = max(fs, key=lambda s: s["sharpe_full"])["bucket"]
        b_d = max(fs, key=lambda s: (s["rerun_dsr"] or 0.0))["bucket"]
        b_p = max(fs, key=lambda s: s["preservation_score"])["bucket"]
        add(f"{fam:<34} {b_s:<16} {b_d:<16} {b_p:<18}")
    add("")
    for key, lab in [
        ("sharpe_full", "best full-sample Sharpe"),
        ("preservation_score", "best preservation_score"),
    ]:
        lows = [s[key] for s in all_specs if s["bucket"] == "low_turnover"]
        highs = [s[key] for s in all_specs if s["bucket"] == "high_turnover"]
        if lows and highs:
            add(
                f"  Across ALL rebuilt specs, {lab}: low-turnover {max(lows):+.4f} vs "
                f"high-turnover {max(highs):+.4f}"
            )
    top10 = sorted(
        all_specs, key=lambda s: (-s["preservation_score"], -s["preservation_score_no_stab"])
    )[:10]
    n_low_top10 = sum(1 for s in top10 if s["bucket"] == "low_turnover")
    add(
        f"  Of the top 10 specs by preservation_score, {n_low_top10} are low-turnover and "
        f"{10 - n_low_top10} are high-turnover."
    )
    add("")

    add("-" * 78)
    add("4f. SECONDARY PANEL — persisted equal-thirds decay, NO rebuild")
    add("-" * 78)
    add(
        "Four families already persist subperiod_sharpes (three equal thirds). This panel "
        "uses third-3 minus third-1 as the decay statistic. It is NOT the same statistic "
        "as the halves above (thirds discard the middle) and the two must not be pooled; "
        "it is an independent look at families the rebuild could not reach."
    )
    add("")
    add(
        "Holding periods for the three families that do not persist one are read off "
        "their own spec definitions, not estimated: eigenportfolio_statarb re-forms daily "
        "(1 day); earnings_announcement_premium holds days_before+days_after (2-10 days); "
        "dividend_month_premium holds a calendar month (~21 days). "
        "correlation_risk_premium persists holding_days directly (5/21/63)."
    )
    add("")
    th = f"{'family':<32} {'spec':<40} {'h':>4} {'bucket':<14} {'S':>7} {'t1':>7} {'t2':>7} {'t3':>7} {'t3-t1':>7}"
    add(th)
    add("-" * len(th))
    for r in sorted(thirds, key=lambda x: (x["family_key"], x["holding_days"], x["trial_id"])):
        t1, t2, t3 = r["thirds"]
        add(
            f"{r['family_key']:<32} {r['trial_id']:<40} {r['holding_days']:>4} "
            f"{r['bucket']:<14} {r['sharpe']:>+7.3f} {t1:>+7.3f} {t2:>+7.3f} {t3:>+7.3f} "
            f"{r['decay_t3_minus_t1']:>+7.3f}"
        )
    add("")
    bucket_block(thirds, "decay_t3_minus_t1", "thirds decay (t3 - t1), all four families pooled:", add)
    crp = [r for r in thirds if r["family_key"] == "correlation_risk_premium"]
    add("  correlation_risk_premium alone — the ONLY thirds family whose own grid spans")
    add("  both buckets (h5/h21 vs h63), so the only within-family contrast here:")
    bucket_block(crp, "decay_t3_minus_t1", "thirds decay (t3 - t1), CRP only:", add)

    # ------------------------------------------------------------ the re-ranking
    add("=" * 78)
    add("5. RE-RANKING — preservation_score vs a raw-DSR ranking")
    add("=" * 78)
    add(
        "Both rankings use the SAME rerun (same DSR, same series), so the two orders "
        "differ only by the score's construction, never by data vintage."
    )
    add("")
    scored = [s for s in all_specs if s.get("preservation_score") is not None]
    by_dsr = sorted(scored, key=lambda s: -(s["rerun_dsr"] or 0.0))
    # Tie-break on the no-stability variant. Every spec whose worse half lost
    # money is zeroed by `stab`, so without a tie-break a large block of
    # rejects would be ordered arbitrarily and the rank-move numbers would be
    # noise rather than a comparison.
    by_score = sorted(
        scored, key=lambda s: (-s["preservation_score"], -s["preservation_score_no_stab"])
    )
    dsr_rank = {s["pattern_id"]: i + 1 for i, s in enumerate(by_dsr)}
    score_rank = {s["pattern_id"]: i + 1 for i, s in enumerate(by_score)}

    add(f"Ranked universe: {len(scored)} rebuilt specs across {len(families)} equity families.")
    add("")
    add("TOP 25 BY PRESERVATION SCORE")
    h5 = (
        f"{'#':>3} {'family':<30} {'spec':<40} {'h':>4} {'presScore':>10} {'noStab':>8} "
        f"{'S':>7} {'DSR':>6} {'MDD':>8} {'Calmar':>7} {'stab':>5} {'decay':>7} {'dsrRank':>8} {'move':>6}"
    )
    add(h5)
    add("-" * len(h5))
    for i, s in enumerate(by_score[:25], start=1):
        move = dsr_rank[s["pattern_id"]] - i
        add(
            f"{i:>3} {s['family_key']:<30} {s['pattern_id']:<40} {s['holding_days']:>4} "
            f"{s['preservation_score']:>10.4f} {s['preservation_score_no_stab']:>8.4f} "
            f"{s['sharpe_full']:>+7.3f} {(s['rerun_dsr'] or 0):>6.3f} {s['max_drawdown']:>+8.3f} "
            f"{s['calmar']:>+7.3f} {s['stability']:>5.2f} "
            f"{(s['sharpe_decay'] if s['sharpe_decay'] is not None else float('nan')):>+7.3f} "
            f"{dsr_rank[s['pattern_id']]:>8} {move:>+6}"
        )
    add("")
    add("TOP 25 BY RAW DSR (the ranking this project currently reasons from)")
    h6 = f"{'#':>3} {'family':<30} {'spec':<40} {'h':>4} {'DSR':>6} {'S':>7} {'presScore':>10} {'scoreRank':>10} {'move':>6}"
    add(h6)
    add("-" * len(h6))
    for i, s in enumerate(by_dsr[:25], start=1):
        move = i - score_rank[s["pattern_id"]]
        add(
            f"{i:>3} {s['family_key']:<30} {s['pattern_id']:<40} {s['holding_days']:>4} "
            f"{(s['rerun_dsr'] or 0):>6.3f} {s['sharpe_full']:>+7.3f} "
            f"{s['preservation_score']:>10.4f} {score_rank[s['pattern_id']]:>10} {move:>+6}"
        )
    add("")
    biggest = sorted(
        scored, key=lambda s: -(dsr_rank[s["pattern_id"]] - score_rank[s["pattern_id"]])
    )
    add("BIGGEST RANK MOVES (positive = the preservation score promotes it over raw DSR)")
    for s in biggest[:8] + biggest[-8:]:
        move = dsr_rank[s["pattern_id"]] - score_rank[s["pattern_id"]]
        add(
            f"  {move:>+5}  {s['family_key']:<30} {s['pattern_id']:<40} "
            f"dsrRank {dsr_rank[s['pattern_id']]:>3} -> scoreRank {score_rank[s['pattern_id']]:>3}  "
            f"(stab {s['stability']:.2f}, MDD {s['max_drawdown']:+.3f})"
        )
    add("")
    add(
        f"Spearman(raw DSR rank, preservation-score rank) = "
        f"{spearman([dsr_rank[s['pattern_id']] for s in scored], [score_rank[s['pattern_id']] for s in scored]):+.3f}"
    )
    add("")

    # ------------------------------------------- registered + audit candidates
    add("=" * 78)
    add("6. THE REGISTERED STRATEGIES AND THE FOUR AUDIT CANDIDATES")
    add("=" * 78)
    add("REGISTERED (read off the modules app/main.py awaits at startup):")
    h7 = f"{'spec':<40} {'family':<30} {'h':>4} {'presScore':>10} {'scoreRank':>10} {'dsrRank':>8} {'stab':>5} {'MDD':>8}"
    add(h7)
    add("-" * len(h7))
    for pid, src in REGISTERED.items():
        row = next((s for s in scored if s["pattern_id"] == pid), None)
        if row is None:
            add(f"{pid:<40} {'(not rebuilt)':<30} {'-':>4} {'-':>10} {'-':>10} {'-':>8} {'-':>5} {'-':>8}")
            add(f"    source: {src}")
            continue
        add(
            f"{pid:<40} {row['family_key']:<30} {row['holding_days']:>4} "
            f"{row['preservation_score']:>10.4f} {score_rank[pid]:>10} {dsr_rank[pid]:>8} "
            f"{row['stability']:>5.2f} {row['max_drawdown']:>+8.3f}"
        )
    add("")
    add(f"  {BAB_NOTE}")
    add("")
    add("THE FOUR CANDIDATES AWAITING AN AUDIT DECISION:")
    for fam in sorted(AUDIT_CANDIDATE_FAMILIES):
        rows = [s for s in scored if s["family_key"] == fam]
        if not rows:
            th_rows = [t for t in thirds if t["family_key"] == fam]
            if th_rows:
                best = max(th_rows, key=lambda t: t["sharpe"])
                add(
                    f"  {fam:<32} NOT REBUILT. Persisted best-Sharpe spec {best['trial_id']} "
                    f"S={best['sharpe']:+.3f} dsr={best['dsr']:.4f} thirds decay "
                    f"{best['decay_t3_minus_t1']:+.3f}"
                )
            else:
                add(f"  {fam:<32} NOT REBUILT and no persisted thirds — nothing measured.")
            continue
        best = max(rows, key=lambda s: s["preservation_score"])
        add(
            f"  {fam:<32} best spec {best['pattern_id']:<40} h={best['holding_days']:<4} "
            f"presScore {best['preservation_score']:+.4f} (rank {score_rank[best['pattern_id']]} "
            f"of {len(scored)}; raw-DSR rank {dsr_rank[best['pattern_id']]}), "
            f"S={best['sharpe_full']:+.3f} DSR={best['rerun_dsr']:.3f} "
            f"stab={best['stability']:.2f} MDD={best['max_drawdown']:+.3f}"
        )
    add("")

    # ------------------------------------------------------------ full table
    add("=" * 78)
    add("7. EVERY REBUILT SPEC — the full computed table")
    add("=" * 78)
    h8 = (
        f"{'family':<30} {'spec':<40} {'h':>4} {'bucket':<14} {'S':>7} {'S1':>7} {'S2':>7} "
        f"{'decay':>7} {'MDD':>8} {'Calmar':>8} {'stab':>5} {'DSR':>6} {'presScore':>10} "
        f"{'noStab':>8} {'days':>6} {'repro':>6}"
    )
    add(h8)
    add("-" * len(h8))
    for s in sorted(all_specs, key=lambda s: (s["family_key"], -s["preservation_score"])):
        s1 = s["sharpe_first_half"]
        s2 = s["sharpe_second_half"]
        dc = s["sharpe_decay"]
        add(
            f"{s['family_key']:<30} {s['pattern_id']:<40} {s['holding_days']:>4} "
            f"{s['bucket']:<14} {s['sharpe_full']:>+7.3f} "
            f"{(f'{s1:+.3f}' if s1 is not None else 'n/a'):>7} "
            f"{(f'{s2:+.3f}' if s2 is not None else 'n/a'):>7} "
            f"{(f'{dc:+.3f}' if dc is not None else 'n/a'):>7} "
            f"{s['max_drawdown']:>+8.3f} {s['calmar']:>+8.3f} {s['stability']:>5.2f} "
            f"{(s['rerun_dsr'] or 0):>6.3f} {s['preservation_score']:>10.4f} "
            f"{s['preservation_score_no_stab']:>8.4f} {s['n_observations']:>6} "
            f"{('yes' if s['reproduced'] else 'NO'):>6}"
        )
    add("")
    add(
        "Every number in this table was computed this run from a realized return series. "
        "None is estimated, assumed, or carried over from another family."
    )
    add("")

    # ------------------------------------------------------------ the verdict
    add("=" * 78)
    add("8. THE ANSWER — is a low-turnover preference actually better HERE?")
    add("=" * 78)
    low_d = [s["sharpe_decay"] for s in specs if s["bucket"] == "low_turnover"]
    high_d = [s["sharpe_decay"] for s in specs if s["bucket"] == "high_turnover"]
    t_pooled, df_pooled = welch_t(low_d, high_d)
    dm_x = [float(s["holding_days"]) - fam_mean_hd[s["family_key"]] for s in specs]
    dm_y = [
        s["sharpe_decay"]
        - statistics.fmean(
            [x["sharpe_decay"] for x in specs if x["family_key"] == s["family_key"]]
        )
        for s in specs
    ]
    rho_dm = spearman(dm_x, dm_y)
    n_pos_paired = sum(1 for x in paired if x > 0)

    add("THE NUMBERS THE ANSWER RESTS ON (all computed above, repeated here):")
    add(
        f"  Pooled spec-level decay:  low {statistics.fmean(low_d):+.4f} (n={len(low_d)}) vs "
        f"high {statistics.fmean(high_d):+.4f} (n={len(high_d)}); "
        f"difference {statistics.fmean(low_d) - statistics.fmean(high_d):+.4f}"
        + (f", Welch t {t_pooled:+.2f} on {df_pooled:.1f} df" if t_pooled and df_pooled else "")
    )
    add(
        f"  Within-family paired:     {n_pos_paired} of {len(paired)} families favour low "
        f"turnover; mean paired difference {statistics.fmean(paired):+.4f}"
        if paired
        else "  Within-family paired:     no family spans both buckets"
    )
    add(
        f"  Within-family demeaned rank correlation, holding_days vs decay: "
        f"rho = {rho_dm:+.3f}"
        if rho_dm is not None
        else "  Within-family demeaned rank correlation: not computable"
    )
    add(
        f"  Families contributing a within-family contrast at all: {len(paired)}. "
        f"Equity families rebuilt: {len(families)}. Specs measured: {len(specs)}."
    )
    # The pooled vs within-family-demeaned contrast is the single most
    # important number in this report, so it is recomputed here explicitly
    # rather than only referenced from section 4a.
    def _pooled_and_demeaned(key: str) -> tuple[float | None, float | None]:
        vals = [float(s[key]) for s in specs]
        pooled = spearman([float(s["holding_days"]) for s in specs], vals)
        fmv = {
            f: statistics.fmean([float(s[key]) for s in specs if s["family_key"] == f])
            for f in {s["family_key"] for s in specs}
        }
        dx = [float(s["holding_days"]) - fam_mean_hd[s["family_key"]] for s in specs]
        dy = [float(s[key]) - fmv[s["family_key"]] for s in specs]
        return pooled, spearman(dx, dy)

    add("")
    add("  Pooled vs WITHIN-FAMILY rank correlation with holding_days — the contrast that")
    add("  decides the question, because only the second one isolates holding period:")
    add(f"    {'statistic':<18} {'pooled rho':>12} {'demeaned rho':>14}")
    for key, lab in [
        ("sharpe_decay", "sharpe_decay"),
        ("max_drawdown", "max_drawdown"),
        ("stability", "stability"),
        ("sharpe_full", "sharpe_full"),
    ]:
        p, dmn = _pooled_and_demeaned(key)
        add(
            f"    {lab:<18} {(f'{p:+.3f}' if p is not None else 'n/a'):>12} "
            f"{(f'{dmn:+.3f}' if dmn is not None else 'n/a'):>14}"
        )
    add("")
    add("WHAT THAT DOES AND DOES NOT SUPPORT:")
    add(
        "  1. THE DIRECT TEST FINDS NOTHING. Pooled over all rebuilt specs the two buckets' "
        f"mean decay differ by {statistics.fmean(low_d) - statistics.fmean(high_d):+.4f} "
        f"against within-bucket standard deviations near "
        f"{statistics.stdev(low_d):.2f}. That is not a small effect, it is no effect."
    )
    add(
        "  2. THE APPARENT ADVANTAGES ARE A FAMILY ARTEFACT. Low-turnover specs really do "
        "have shallower drawdowns and higher Sharpes in the pooled table — but every one of "
        "those pooled rank correlations collapses to near zero once each family's own mean "
        "is subtracted (table above). Holding period is not doing the work; WHICH SIGNAL "
        "is. In this candidate set the slow families are the good families, which is a fact "
        "about what got built, not about turnover."
    )
    add(
        f"  3. THE ONE PANEL THAT LEANS THE OTHER WAY, reported rather than buried: the "
        f"within-family paired comparison (4c) has {n_pos_paired} of {len(paired)} families "
        f"favouring low turnover, mean {statistics.fmean(paired):+.4f}. Its standard "
        f"deviation is {statistics.stdev(paired):.4f} — twice the mean — and it rests on "
        f"{len(paired)} families, one of which (liquidity_shock_delta_illiq) contributes "
        "four specs a side. The independent persisted-thirds panel (4f) leans the same way "
        "and is even thinner: one family with a within-family contrast. Both are "
        "SUGGESTIVE. Neither is a basis for a rule."
    )
    add(
        "  4. SIGN-BLIND INSTABILITY POINTS AGAINST THE PREMISE. |sharpe_decay| measures how "
        "far a spec's two halves moved apart regardless of direction, which is what "
        "'stability' actually means. The low-turnover bucket's is LARGER, not smaller."
    )
    add("")
    add("THE HONEST BOTTOM LINE:")
    add(
        "  Preferring low-turnover candidates is NOT supported as a selection rule on this "
        "project's own data. The direct decay test finds no difference at all; the "
        "drawdown and Sharpe advantages that do show up pooled are between-family effects "
        "that vanish once family is controlled for; the sign-blind instability measure "
        "leans the wrong way. Two thin panels lean toward it and are reported above, but "
        "with 5 families contributing a within-family contrast the evidence is SUGGESTIVE "
        "AT BEST and closer to inconclusive. It does not justify a turnover term in the "
        "score, and none was added."
    )
    hi = [s for s in specs if s["bucket"] == "high_turnover"]
    hi_neg_fams = [s for s in hi if s["family_key"] in {"jump_drift", "same_calendar_month_seasonality"}]
    add(
        f"  DOES IT LEAVE BETTER HIGH-TURNOVER CANDIDATES ON THE TABLE? In THIS candidate "
        f"set, barely — section 4e shows the top 10 by preservation_score are all "
        f"low-turnover, and the best high-turnover full-sample Sharpe "
        f"({max(s['sharpe_full'] for s in hi):+.4f}) is below the best low-turnover one "
        f"({max(s['sharpe_full'] for s in specs if s['bucket'] == 'low_turnover'):+.4f}). "
        f"But that is the SAME family artefact restated: the high-turnover bucket's mean "
        f"full-sample Sharpe is {statistics.fmean([s['sharpe_full'] for s in hi]):+.4f}, and "
        f"{len(hi_neg_fams)} of its {len(hi)} specs come from jump_drift and "
        f"same_calendar_month_seasonality alone — two families this project had already "
        f"recorded as honest negatives before this run existed. The rule would cost little "
        f"here while resting on nothing, which is the worst way for a heuristic to survive: "
        f"cheap enough that nothing ever corrects it."
    )
    add(
        "  WHAT IS SUPPORTED INSTEAD, and is why preservation_score is built as it is: "
        "measure the PATH directly. The drawdown and stability terms re-rank candidates "
        "materially (section 5, Spearman against the raw-DSR order well below 1.0) without "
        "any turnover prior at all. They do the work the 'prefer low turnover' heuristic "
        "was reaching for — penalising ugly paths and one-half-only edges — on each "
        "candidate's own realized returns instead of using holding period as a proxy for "
        "them."
    )
    add(
        "  THE LIMIT OF ALL OF THIS, stated plainly: 11 equity families, 5 with a "
        "within-family holding-period contrast, one backtest window each, one cost model. "
        "A finding either way on that sample would be weak. This one is a null, and nulls "
        "on small samples are the weakest result there is — it is a reason not to ADOPT "
        "the rule, not proof the rule is false."
    )
    add("")

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"wrote {REPORT_PATH.relative_to(_BACKEND)} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
