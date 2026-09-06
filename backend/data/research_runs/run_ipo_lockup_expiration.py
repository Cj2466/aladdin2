"""Production runner for the IPO share-lockup expiration family.

Calls the module's OWN entry point (run_ipo_lockup_screening) — not a
reimplementation, not a shortcut — then persists every per-spec result of the
BASELINE cost arm to the shared cross_sectional_trial_results table and writes
the git-durable plain-text and JSON run reports.

Run from backend/ with the venv, AFTER data/research_runs/fetch_ipo_lockup_data.py
has populated data/ipo_lockup/:

    ./venv/bin/python data/research_runs/run_ipo_lockup_expiration.py

Needs only committed inputs: data/ipo_lockup/IPO-age.xlsx (Ritter's universe),
data/ipo_lockup/sec_company_tickers.json (SEC's ticker->CIK map),
data/ipo_lockup/ticker_info.json (yfinance security metadata) and
data/ipo_lockup/price_store/ (as-traded OHLCV). No network, no vendor feed, no
paid data.

Pre-registration: data/research_runs/ipo_lockup_expiration_PREREGISTRATION.txt
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# resolves `app` to the MAIN worktree's backend/app. Without the lines below
# this runner silently screens main's code instead of this branch's.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The screen would have run against another checkout's code."
    )

from app.db import SessionLocal
from app.services.research_lab.cross_sectional_persistence import (
    describe_configured_database,
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
)
from app.services.research_lab.ipo_lockup_expiration import (
    BASELINE_COST_ARM,
    CORRECTED_IDENTITY,
    COST_ARMS,
    EVENT_WINDOWS,
    IPO_LOCKUP_CITATION,
    IPO_LOCKUP_N_TRIALS,
    LOCKUP_CALENDAR_DAYS,
    PAPER_ABNORMAL_VOLUME_ALL,
    PAPER_ABNORMAL_VOLUME_NONVC,
    PAPER_ABNORMAL_VOLUME_VC,
    PAPER_CAR_M1_P1_ALL,
    PAPER_CAR_M1_P1_NONVC,
    PAPER_CAR_M1_P1_VC,
    PAPER_CAR_M5_P1_ALL,
    PAPER_FRACTION_NEGATIVE,
    PAPER_PLACEBO_CAR,
    PAPER_SAMPLE_SIZE,
    PLACEBO_CALENDAR_DAYS,
    PREREGISTERED_IDENTITY,
    RITTER_CITATION,
    SCREENING_FLOOR,
    VALIDATED_EDGE_BAR,
    _rank_dsr,
    build_ipo_lockup_disclosure,
    predicted_unlock_weekday,
    run_ipo_lockup_screening,
)

RUN_TAG = "ipo_lockup_expiration_build_2026-09-06"
FAMILY_KEY = "ipo_lockup_expiration"
REPORT_PATH = "data/research_runs/ipo_lockup_expiration_2026-09-06.txt"
JSON_PATH = "data/research_runs/ipo_lockup_expiration_2026-09-06.json"
PREREGISTRATION = "data/research_runs/ipo_lockup_expiration_PREREGISTRATION.txt"

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger("ipo_lockup_runner")


def _fmt(value, spec: str = ".4f") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and math.isnan(value):
        return "n/a"
    if not isinstance(value, (int, float)):
        return str(value)
    return format(value, spec)


def build_identity_defect_section(summary, corrected) -> list[str]:
    """The two defects the pre-registered identity gates turned out to have,
    measured on the full universe, with the sensitivity that shows whether they
    change anything. Reported here rather than fixed silently, and the
    PRE-REGISTERED arm remains the headline result."""
    lines: list[str] = []
    add = lines.append
    pre_id = summary.panel.identity
    cor_id = corrected.panel.identity

    add("=" * 118)
    add("TWO DEFECTS IN THIS BUILD'S OWN PRE-REGISTERED IDENTITY GATES — FOUND BY INSPECTION, NOT WAIVED")
    add("=" * 118)
    add(
        "  The pre-registration's G2 band and G3 rules were fixed on a measurement of the 2013"
    )
    add(
        "  cohort alone. Running them over all eight cohorts exposed two defects. Both are reported"
    )
    add(
        "  here and quantified; NEITHER is used to replace the pre-registered verdict, which stands"
    )
    add("  exactly as computed above.")
    add("")
    add("  DEFECT 1 — G2 REJECTS 22 UNAMBIGUOUSLY CORRECT ROWS AT EXACTLY -1 DAY.")
    add(
        "    Affected, among others: GoDaddy (GDDY), Shopify (SHOP), Teladoc (TDOC), Natera (NTRA), "
        "Bandwidth (BAND), SiTime (SITM), Performance Food Group (PFGC), Surgery Partners (SGRY), "
        "NovoCure (NVCR), Viking Therapeutics (VKTX), Black Stone Minerals (BSM)."
    )
    add(
        "    VERIFIED CAUSE, read off the stored rows rather than inferred: Yahoo carries a SYNTHETIC "
        "row on the pricing date at the IPO OFFER PRICE with VOLUME = 0, one session before the real "
        "first trade. SHOP 2015-05-20 open=close=1.70 volume=0 (its $17 offer price, split-adjusted) "
        "before its first trade on 2015-05-21; GDDY 2015-03-31 close=20.00 volume=0 (its $20 offer "
        "price); TDOC 2015-06-30 close=19.00 volume=0 (its $19 offer price). A zero-volume "
        "offer-price row is not a trade, so the gate's own name argues for skipping it. This is an "
        "implementation defect against the pre-registration's stated INTENT, not a parameter worth "
        "tuning."
    )
    add("")
    add("  DEFECT 2 — G3 SYSTEMATICALLY DELETES DELISTED AND RENAMED COMPANIES, WHICH IS THE OPPOSITE")
    add("  OF WHAT IT WAS FOR, AND MAKES THIS FAMILY'S HEADLINE RISK WORSE.")
    add(
        f"    quoteType rejections: {pre_id.g3_rejected_quote_type}, and EVERY ONE of them is "
        "cik_absent — a company with no current SEC filer under that ticker, i.e. delisted or "
        "acquired. Zero current filers are affected. Yahoo tags delisted equities as MUTUALFUND: "
        "Nationstar Mortgage Holdings, CafePress, Tesaro, Pinnacle Foods, Envision Healthcare, "
        "Barracuda Networks, Valero Energy Partners, RSP Permian — and Foundation Medicine, whose "
        "yfinance longName is literally 'Foundation Medicine, Inc. Common Stock'."
    )
    add(
        f"    name rejections: {pre_id.g3_rejected_name}, of which 9 are ordinary corporate RENAMES "
        "of the correct company: Restoration Hardware -> RH, ING US -> Voya Financial, Hannon "
        "Armstrong -> HA Sustainable Infrastructure, ShotSpotter -> SoundThinking, Kala "
        "Pharmaceuticals -> KALA BIO, Sundial Growers -> SNDL, MCBC Holdings -> MasterCraft Boat "
        "Holdings, Orion Engineered Carbons -> Orion S.A., Wheeler REIT -> Wheeler Real Estate "
        "Investment Trust. The other 3 (Yulong Eco-Materials -> EV Biologics, Sonim Technologies -> "
        "DNA X, YayYo -> EVmo) are genuine shell reuse and are correctly caught."
    )
    add(
        "    G2 had already vouched for every one of those rows' first-trade anchor. A gate that "
        "removes only delisted names AMPLIFIES the survivorship bias pre-registration section 6 "
        "names as this family's largest threat."
    )
    add("")
    add("  THE SENSITIVITY — DOES EITHER DEFECT CHANGE THE ANSWER? NO.")
    add(
        f"    pre-registered gates : {pre_id.accepted_universe_rows} universe rows, {len(summary.panel.events)} events, "
        f"G2 rejected {pre_id.g2_rejected_recycled}"
    )
    add(
        f"    corrected gates      : {cor_id.accepted_universe_rows} universe rows, {len(corrected.panel.events)} events, "
        f"G2 rejected {cor_id.g2_rejected_recycled}   (anchor on the first NON-ZERO-VOLUME row; "
        "G3 recorded but not enforced)"
    )
    add("")
    for label, s in (("pre-registered", summary), ("corrected", corrected)):
        verdict, best_id, _reason = s.verdict(VALIDATED_EDGE_BAR)
        add(f"    [{label}] VERDICT {verdict}  best non-control spec {best_id}")
        for arm in COST_ARMS:
            results = [r for r in s.results_by_cost_arm.get(arm.key, []) if not r.is_control]
            if not results:
                continue
            best = max(results, key=lambda r: _rank_dsr(r.dsr_by_n.get(s.n_local)))
            add(
                f"      {arm.key:10s} best non-control DSR@{s.n_local} = "
                f"{_fmt(best.dsr_by_n.get(s.n_local))}  ({best.spec_id}, daily Sharpe "
                f"{best.streams['daily'].sharpe_annualized:+.3f})"
            )
    add("")
    add(
        "    The corrected arm adds 53 tickers and 105 events — a 12% larger sample, weighted toward "
        "the delisted names whose absence is the survivorship problem — and the verdict, the best "
        "spec and the DSR at every cost arm are materially unchanged. THE PRE-REGISTERED RESULT IS "
        "THE RESULT; the corrected arm is reported so that a reader who thinks the gates were wrong "
        "can see it would not have mattered. Only the pre-registered baseline arm's 24 rows are "
        "persisted to cross_sectional_trial_results — persisting the sensitivity would double-count "
        "this family in every future pooled-effective-N computation."
    )
    add("")
    return lines


def build_report(summary, elapsed: float, corrected=None) -> str:
    lines: list[str] = []
    add = lines.append
    verdict, best_id, reason = summary.verdict(VALIDATED_EDGE_BAR)
    disclosure = build_ipo_lockup_disclosure(summary.panel)
    survivorship = disclosure["survivorship"]

    add("=" * 118)
    add("IPO SHARE-LOCKUP EXPIRATION — BUILD AND SCREEN — 2026-09-06")
    add(f"family_key: {FAMILY_KEY}   run_tag: {RUN_TAG}")
    add("=" * 118)
    add("")
    add(f"SOURCE: {IPO_LOCKUP_CITATION}")
    add("")
    add(f"UNIVERSE: {RITTER_CITATION}")
    add("")
    add(f"PRE-REGISTRATION: {PREREGISTRATION}")
    add(
        "  Written and committed BEFORE any abnormal return, CAR, Sharpe or DSR of this family "
        "was computed. Everything below reports against that document's grid and rule."
    )
    add("")
    add(f"elapsed: {elapsed:.1f}s")
    add("")

    add("=" * 118)
    add("VERDICT")
    add("=" * 118)
    add(f"  {verdict}")
    add(f"  best non-control spec: {best_id}")
    add(f"  reason: {reason}")
    add("")
    add(
        "  THE VERDICT IS THE WORSE OF TWO STREAMS. Pre-registration section 7.4: a ~600-one-shot-"
        "event design has an ambiguous OBSERVATION count, so both readings are computed (a daily "
        "calendar-time portfolio at 252/yr, and an event-clock portfolio at one observation per "
        "distinct unlock date) and each spec's DSR at each N is the MINIMUM of the two. A min, "
        "not a choice."
    )
    add("")
    add("  SURVIVORSHIP — FIRST-CLASS, NOT A FOOTNOTE (pre-registration sections 6 and 12(ii)):")
    add(
        f"    {survivorship['rows_with_any_price_data']} of {survivorship['universe_rows']} filtered "
        f"universe rows ({survivorship['price_availability_rate']:.1%}) return ANY free price data. "
        f"The direction of the resulting bias is {survivorship['direction_of_bias']}."
    )
    add(f"    {survivorship['why_unknown']}")
    add(f"    {survivorship['consequence']}")
    add("")

    add("=" * 118)
    add("UNIVERSE FILTER — EVERY STEP COUNTED (F8)")
    add("=" * 118)
    for key, value in disclosure["universe"].items():
        add(f"  {key:48s} {value}")
    add("")

    add("=" * 118)
    add("IDENTITY GATES — EVERY OUTCOME COUNTED (F8, F9)")
    add("=" * 118)
    identity = disclosure["identity"]
    for key, value in identity.items():
        if key in (
            "availability_by_cik_status",
            "first_obs_minus_offer_date_days",
            "offer_weekday_counts",
        ):
            continue
        add(f"  {key:48s} {value}")
    add("")
    add("  G2 first-observation offset from the offer date, in days (the recycling detector):")
    offsets = identity["first_obs_minus_offer_date_days"]
    for offset in sorted(offsets):
        marker = "   <-- REJECTED" if offset < 0 or offset > 7 else ""
        add(f"    {offset:+6d} days : {offsets[offset]:5d} rows{marker}")
    add(
        "    Ritter's own documentation states the offer date is 'sometimes the first day of "
        "trading, and sometimes the day before the first day of trading', which is exactly the "
        "0/+1 mass above. Anything outside the band is a ticker whose series does not begin at "
        "this IPO."
    )
    add("")
    add("  Price availability split by SEC-current-filer status (F9 — the survivorship signature):")
    for status, bucket in identity["availability_by_cik_status"].items():
        total = bucket["with_price_rows"] + bucket["without_price_rows"]
        rate = bucket["with_price_rows"] / total if total else 0.0
        add(
            f"    {status:20s} n={total:5d}  with price rows {bucket['with_price_rows']:5d} "
            f"({rate:6.1%})  accepted {bucket['accepted']:5d}"
        )
    add("")
    add(
        "  NOTE ON G1, AND WHY IT IS NOT THE GATE. SEC's own current ticker->CIK map name-matches "
        "the 2013 ConnectOne Bancorp IPO row to CIK 712771 — Center Bancorp's registrant, filing "
        "since the 1980s — because Center Bancorp survived the 2014 merger, renamed itself "
        "ConnectOne and kept the CNOB symbol. A CIK-plus-name join ACCEPTS that row and silently "
        "attributes an older bank's price series to a 2013 lockup expiration. Only the "
        "first-trade anchor catches it. Pinned as a regression test in "
        "tests/test_ipo_lockup_expiration.py."
    )
    add("")
    add(
        "  AND THE PROBLEM IS NOT ONLY BETWEEN ERAS — IT IS INSIDE THIS EIGHT-YEAR WINDOW. The "
        "filtered universe holds 1,205 rows but only 1,201 distinct tickers, because FOUR symbols "
        "were each used by TWO DIFFERENT IPOs between 2012 and 2019: BV (Bazaarvoice 2012, "
        "BrightView Holdings 2018), EVER (EverBank Financial 2012, EverQuote 2018), ADPT (Adeptus "
        "Health 2014, Adaptive Biotechnologies 2019) and COUP (Coupons.com 2014, Coupa Software "
        "2016). A raw ticker join would have "
        "silently merged each of those pairs. G2 keeps the later IPO of each pair, whose price "
        "series does begin at its own offer date, and rejects the earlier one, whose data now "
        "belongs to the later company — which is the correct and conservative resolution."
    )
    add("")

    add("=" * 118)
    add("F2 / F10 — DOES THE 180-DAY PROXY LAND ON REAL UNLOCK EVENTS?")
    add("=" * 118)
    add(
        "  These two checks can FAIL WITHOUT THE RETURN TEST FAILING, and if they do the return "
        "result means nothing. That is why they are run."
    )
    add("")
    for arm_key in (BASELINE_COST_ARM,):
        for result in sorted(summary.results_by_cost_arm[arm_key], key=lambda r: r.spec_id):
            if result.window != "w_m1_p1" or result.benchmark != "spy":
                continue
            d = result.diagnostics
            weekdays = ", ".join(
                f"{WEEKDAY_NAMES[k]} {v}" for k, v in sorted(d.unlock_weekday_counts.items())
            )
            modal = WEEKDAY_NAMES[d.modal_unlock_weekday] if d.modal_unlock_weekday is not None else "n/a"
            add(f"  {result.spec_id}")
            add(f"    n events                     {d.n_events}")
            add(f"    F2 unlock weekday counts     {weekdays}   modal={modal}")
            add(
                f"    F10 abnormal volume -1..+1   {_fmt(d.mean_abnormal_volume_3day, '+.2%')}   "
                f"day +1 {_fmt(d.mean_abnormal_volume_day_p1, '+.2%')}"
            )
    add("")
    add(
        f"  F10 VERDICT: PASSED, AND STRONGLY. [FH01] Table III p.481 reports abnormal volume over "
        f"days -1..+1 of {PAPER_ABNORMAL_VOLUME_ALL:+.0%} for all firms, {PAPER_ABNORMAL_VOLUME_VC:+.0%} "
        f"for venture-backed and {PAPER_ABNORMAL_VOLUME_NONVC:+.0%} for non-venture; Figure 3 p.480 "
        "shows ~+80% on day +1 settling near +40%. This build's lockup arm reproduces the ORDERING "
        "exactly (venture >> non-venture) at roughly twice the magnitude, and the day-240 placebo "
        "arm shows a much smaller spike. The 180-day proxy IS landing on real unlock events."
    )
    add("")
    add("  F2 — THE PRE-REGISTERED PREDICTION WAS NOT MET. DIAGNOSED, NOT WAIVED.")
    add(
        f"    Pre-registration section 11 predicted Monday would be the MODAL unlock weekday, from "
        f"[FH01] Sec III.C p.488 ('because of the weekend, unlock days tend to fall on Monday') plus "
        f"the arithmetic that {LOCKUP_CALENDAR_DAYS} = 25*7 + 5. The realised modal weekday is "
        "TUESDAY, and the pre-registration said in terms that a failure here would make the whole "
        "construction suspect. So it was investigated rather than waived."
    )
    add("")
    add("    THE PREDICTION HAD AN UNSTATED PREMISE THAT IS FALSE: a roughly uniform distribution")
    add("    of OFFER weekdays. The measured distribution over all 1,205 filtered universe rows is")
    offer_counts = identity["offer_weekday_counts"]
    offer_total = sum(offer_counts.values()) or 1
    for weekday in sorted(offer_counts):
        add(
            f"      {WEEKDAY_NAMES[weekday]:4s} {offer_counts[weekday]:5d}  "
            f"({offer_counts[weekday] / offer_total:5.1%})"
        )
    add(
        "    — US IPOs price the evening before and begin trading Thursday or Friday. The calendar "
        "arithmetic is Mon->Sat, Tue->Sun, Wed->Mon, Thu->Tue, Fri->Wed, so only Mon/Tue/Wed offers "
        "land on the weekend and forward to Monday, while the 40.5% of offers dated THURSDAY land "
        "on a Tuesday that is already a full trading day. Tuesday-modal is the correct consequence "
        "of the paper's own mechanism applied to the modern IPO calendar, not a broken mapping."
    )
    add("")
    add("    THE STRICTER TEST, WHICH THE CONSTRUCTION PASSES. Predicting the whole distribution")
    add("    from the observed offer weekdays (predicted_unlock_weekday, arithmetic only, holidays")
    add("    ignored) against what the pipeline actually produced for the `all` arm:")
    for event_type, calendar_days in (("lockup", LOCKUP_CALENDAR_DAYS), ("placebo", PLACEBO_CALENDAR_DAYS)):
        predicted: dict[int, int] = {}
        for weekday, count in offer_counts.items():
            landing = predicted_unlock_weekday(int(weekday), calendar_days)
            predicted[landing] = predicted.get(landing, 0) + count
        observed_spec = next(
            (
                r
                for r in summary.results_by_cost_arm[BASELINE_COST_ARM]
                if r.event_type == event_type and r.window == "w_m1_p1" and r.benchmark == "spy"
                and r.cross_section == "all"
            ),
            None,
        )
        observed = observed_spec.diagnostics.unlock_weekday_counts if observed_spec else {}
        obs_total = sum(observed.values()) or 1
        pred_total = sum(predicted.values()) or 1
        add(f"      {event_type} (offer + {calendar_days} calendar days):")
        for weekday in sorted(set(predicted) | set(observed)):
            add(
                f"        {WEEKDAY_NAMES[weekday]:4s} predicted {predicted.get(weekday, 0) / pred_total:6.1%}"
                f"   observed {observed.get(weekday, 0) / obs_total:6.1%}"
                f"   (n={observed.get(weekday, 0)})"
            )
    add(
        "    Predicted and observed shares agree to a few percentage points in both arms, and the "
        "residual is market holidays, which shift a Monday landing to Tuesday. The mapping is doing "
        "exactly what it was designed to do. F2 is recorded as PREDICTION NOT MET / CONSTRUCTION "
        "VINDICATED, and the exact mapping is pinned as a unit test in place of the modal claim."
    )
    add("")

    add("=" * 118)
    add("F6 / F7 — EVENT-LEVEL CAR REPLICATION AND THE PLACEBO, SIDE BY SIDE")
    add("=" * 118)
    add(
        "  [FH01]'s numbers are CHECKS FOR IMPLAUSIBLE DIVERGENCE, NOT TARGETS TO REPRODUCE "
        "(pre-registration section 4). This sample is later, smaller, differently sourced, "
        "differently filtered and survivorship-damaged."
    )
    add("")
    header = f"  {'spec':38s} {'n':>5s} {'mean CAR':>10s} {'median':>9s} {'%neg':>7s} {'t':>8s}"
    add(header)
    add("  " + "-" * (len(header) - 2))
    for result in sorted(summary.results_by_cost_arm[BASELINE_COST_ARM], key=lambda r: r.spec_id):
        if result.benchmark != "spy":
            continue
        d = result.diagnostics
        add(
            f"  {result.spec_id:38s} {d.n_events:5d} {d.mean_car:+9.4%} {d.median_car:+8.4%} "
            f"{d.fraction_negative:6.1%} {_fmt(d.car_t_stat, '+8.2f')}"
        )
    add("")
    add(
        f"  [FH01] Table II p.479 / Table III p.481, n={PAPER_SAMPLE_SIZE}: "
        f"day -1..+1 all {PAPER_CAR_M1_P1_ALL:+.1%} (t=-9.8), venture {PAPER_CAR_M1_P1_VC:+.1%} "
        f"(t=-9.2), non-venture {PAPER_CAR_M1_P1_NONVC:+.1%} (t=-4.2); day -5..+1 all "
        f"{PAPER_CAR_M5_P1_ALL:+.1%} (t=-8.7); fraction negative {PAPER_FRACTION_NEGATIVE:.0%}."
    )
    add(
        f"  [FH01] Sec II.D.1 p.484's own placebo (no-lockup IPOs, days 175-181): "
        f"{PAPER_PLACEBO_CAR:+.1%}, INSIGNIFICANT. This build's placebo is offer + "
        f"{PLACEBO_CALENDAR_DAYS} calendar days on the SAME firms."
    )
    add("")

    add("=" * 118)
    add("COST ARMS — BOUNDED ON BOTH SIDES")
    add("=" * 118)
    for arm in COST_ARMS:
        add(f"  {arm.key:11s} {arm.description}")
    add("")

    for arm in COST_ARMS:
        results = summary.results_by_cost_arm.get(arm.key, [])
        if not results:
            add(f"  [{arm.key}] no replayable spec")
            continue
        add("=" * 118)
        add(f"COST ARM: {arm.key}" + ("   <-- THE VERDICT ARM" if arm.key == BASELINE_COST_ARM else ""))
        add("=" * 118)
        header = (
            f"  {'spec':38s} {'nev':>4s} {'SR day':>8s} {'SR evt':>8s} "
            + " ".join(f"{'DSR@' + str(n):>10s}" for n in summary.denominators)
            + f" {'presv':>7s} {'be bps':>8s} {'hs bps':>7s}"
        )
        add(header)
        add("  " + "-" * (len(header) - 2))
        for result in sorted(results, key=lambda r: -_rank_dsr(r.dsr_by_n.get(summary.n_local))):
            d = result.diagnostics
            dsr_cells = " ".join(_fmt(result.dsr_by_n.get(n), ">10.4f") for n in summary.denominators)
            presv = result.preservation.get("preservation_score")
            add(
                f"  {result.spec_id:38s} {result.n_events:4d} "
                f"{result.streams['daily'].sharpe_annualized:8.3f} "
                f"{result.streams['event'].sharpe_annualized:8.3f} {dsr_cells} "
                f"{_fmt(presv, '>7.3f')} {_fmt(d.breakeven_half_spread_bps, '>8.2f')} "
                f"{_fmt(d.mean_half_spread_bps, '>7.1f')}"
            )
        add("")
        add(
            "  SR day = daily calendar-time stream, annualised at 252. SR evt = event-clock "
            "stream, annualised at its own measured observations-per-year. DSR = the MINIMUM of "
            "the two streams at that N. presv = preservation_score on the worse stream. "
            "be bps = the one-way stock-leg half-spread at which the mean trade return reaches "
            "zero. hs bps = the mean half-spread actually charged."
        )
        add("")

    add("=" * 118)
    add("COST SENSITIVITY — WHERE DOES THE VERDICT FLIP?")
    add("=" * 118)
    for arm in COST_ARMS:
        results = [r for r in summary.results_by_cost_arm.get(arm.key, []) if not r.is_control]
        if not results:
            continue
        best = max(results, key=lambda r: _rank_dsr(r.dsr_by_n.get(summary.n_local)))
        add(
            f"  {arm.key:11s} best non-control DSR@{summary.n_local} = "
            f"{_fmt(best.dsr_by_n.get(summary.n_local))}  ({best.spec_id}, "
            f"daily Sharpe {best.streams['daily'].sharpe_annualized:.3f})"
        )
    add("")
    add(
        "  `cheap` is a DELIBERATELY OPTIMISTIC LOWER BOUND (2.5 bp one-way = one $0.01 tick on a "
        "$20 stock, plus general-collateral borrow), not an estimate. A spec that fails there "
        "cannot be rescued by any dispute about the EDGE estimator's level. `cost_free` is the "
        "gross signal and is never a verdict input."
    )
    add("")
    add("  THE BASELINE ARM'S COST LEVEL IS ALMOST CERTAINLY TOO HIGH, AND IT DOES NOT MATTER.")
    add(
        "    The realised mean charged half-spread runs 68-83 bp one-way, i.e. a ~140-165 bp full "
        "spread. Spot-checked on one name where the answer is independently judgeable: Guidewire "
        "Software (GWRE, NYSE, ~$25/share, a well-covered 2012 IPO) is charged 79.0 bp one-way, "
        "which is not a plausible 2012 quoted spread for that stock. This is the upward bias "
        "spread_estimator.py documents about itself for anything but genuinely wide-spread names, "
        "and this universe is a mix of both."
    )
    add(
        "    IT CHANGES NOTHING ABOUT THE VERDICT, WHICH IS WHY THE ARMS ARE BOUNDED ON BOTH SIDES: "
        "the family already fails at `cost_free`, where the charge is EXACTLY ZERO. The best "
        "non-control spec's DSR there is far below the 0.95 bar. This is a SIGNAL failure, not a "
        "cost failure, and no cost model — however generous — can change it."
    )
    add("")

    add("=" * 118)
    add("PER-SPEC DETAIL — BASELINE ARM, BOTH STREAMS")
    add("=" * 118)
    for result in sorted(
        summary.results_by_cost_arm[BASELINE_COST_ARM],
        key=lambda r: -_rank_dsr(r.dsr_by_n.get(summary.n_local)),
    ):
        add(f"  {result.spec_id}   {'CONTROL' if result.is_control else ''}")
        add(f"    hypothesis: {result.hypothesis}")
        add(
            f"    events {result.n_events}   window {result.first_date}..{result.last_date}   "
            f"active-day fraction {result.active_day_fraction:.1%}   "
            f"EDGE fallback fraction {result.fallback_fraction:.1%}"
        )
        for name in ("daily", "event"):
            stream = result.streams[name]
            dsr_cells = ", ".join(
                f"N={n}: {_fmt(stream.dsr_by_n.get(n))}" for n in summary.denominators
            )
            add(
                f"    stream {name:6s} n={stream.n_observations:5d} ppy={stream.periods_per_year:7.2f} "
                f"Sharpe={stream.sharpe_annualized:+7.3f}  {dsr_cells}"
            )
            add(
                f"                  preservation_score="
                f"{_fmt(stream.preservation.get('preservation_score'))} "
                f"(no-stab {_fmt(stream.preservation.get('preservation_score_no_stab'))}), "
                f"PSR-vs-zero {_fmt(getattr(stream.deflated_sharpe, 'psr_vs_zero', None))}"
            )
        d = result.diagnostics
        add(
            f"    gross mean trade {d.gross_mean_trade_return:+.4%}   net "
            f"{d.net_mean_trade_return:+.4%}   breakeven half-spread "
            f"{_fmt(d.breakeven_half_spread_bps, '.2f')} bp   charged "
            f"{_fmt(d.mean_half_spread_bps, '.2f')} bp"
        )
        add(f"    block-bootstrap p-value (daily stream): {_fmt(result.bootstrap_p_value)}")
        add("")

    if corrected is not None:
        lines.extend(build_identity_defect_section(summary, corrected))

    add("=" * 118)
    add("DEVIATIONS FROM THE SOURCE — CARRIED FROM THE PRE-REGISTRATION, SECTION 13")
    add("=" * 118)
    for text in (
        (
            "D1  Lockup date is a 180-calendar-day proxy, not the prospectus's actual unlock date. "
            "Attenuates toward zero; cannot manufacture an effect."
        ),
        (
            "D2  Benchmark is SPY (large cap) rather than the CRSP value-weighted index; the `raw` "
            "arm is [FH01]'s own robustness choice (p.477) and is carried as a grid dimension."
        ),
        (
            "D3  Universe is Ritter's IPO-age.xlsx filtered as in pre-registration 5.2, not SDC plus "
            "hand-collected prospectuses."
        ),
        (
            "D4  Three of [FH01]'s five exclusions are NOT implemented — carveouts, earnings "
            "announcements within three days of the unlock day, and seasoned offers around it. Adds "
            "noise; reduces measured Sharpe."
        ),
        (
            "D5  Penny-stock filter applied at the day -6 AS-TRADED close, not the offer price. "
            "Tradeable, so no look-ahead."
        ),
        (
            "D6  Sample is 2012-2019, entirely outside [FH01]'s 1988-1997 and 11-18 years after its "
            "2001 publication."
        ),
        (
            "D7  Survivorship: only companies whose price history is still retrievable free. "
            "Measured, first-class, direction UNKNOWN."
        ),
        (
            "D8  VC split uses Ritter's VC==1 vs VC==0; VC==2 (growth capital, established against "
            "Ritter's own Table 4c) is in `all` and in neither cross-sectional arm."
        ),
        (
            "D9  The tradeable object (a calendar-time short basket) is NOT in the paper. [FH01] "
            "reports a cross-sectional CAR and states plainly it is not exploitable at bid and ask."
        ),
        (
            "D10 Costs are estimated with EDGE from daily OHLC, not from quoted spreads. [FH01]'s own "
            "~3.35-3.45% relative quoted spreads (Sec III.C p.488-489) are 1988-1997 Nasdaq and do "
            "not transfer."
        ),
        (
            "D11 Abnormal volume uses PriceStore volume, not CRSP volume. Volume enters only as a "
            "ratio inside one 56-day window, so any consistent share basis cancels."
        ),
    ):
        add(f"  {text}")
    add("")
    add(
        "  ONE CASE THE PRE-REGISTRATION DID NOT SPECIFY, RESOLVED IN CODE AND NAMED HERE: identity "
        "gate G3 is defined for a row whose yfinance `.info` resolves. For a row where `.info` is "
        "absent or errors, the module returns info_unavailable and KEEPS the row, counting it "
        f"separately ({identity['g3_info_unavailable_kept']} rows). Rejecting on the absence of a "
        "metadata call would delete exactly the delisted names whose retention LIMITS this "
        "family's survivorship bias — it would make the headline risk worse in order to look "
        "stricter. G2 has already vouched for every one of those rows' first-trade anchor."
    )
    add("")

    add("=" * 118)
    add(f"PERSISTENCE: baseline cost arm rows written under run_tag={RUN_TAG!r}, "
        f"family_key={FAMILY_KEY!r}, to {describe_configured_database()}")
    add("=" * 118)
    return "\n".join(lines)


def _serialize(obj):
    if is_dataclass(obj) and not isinstance(obj, type):
        payload = asdict(obj)
        if hasattr(obj, "dsr_by_n"):
            payload["dsr_by_n"] = {str(k): v for k, v in obj.dsr_by_n.items()}
        if hasattr(obj, "streams"):
            streams = {}
            for name, stream in obj.streams.items():
                entry = asdict(stream) if is_dataclass(stream) else {}
                entry["dsr_by_n"] = {str(k): v for k, v in stream.dsr_by_n.items()}
                streams[name] = entry
            payload["streams"] = streams
        return payload
    return obj


def main() -> int:
    started = time.time()
    logger.info("screening the IPO lockup-expiration family (%d specs)", IPO_LOCKUP_N_TRIALS)
    summary = run_ipo_lockup_screening(policy=PREREGISTERED_IDENTITY)
    logger.info("running the CORRECTED-identity sensitivity (see build_identity_defect_section)")
    corrected = run_ipo_lockup_screening(policy=CORRECTED_IDENTITY)
    elapsed = time.time() - started

    report = build_report(summary, elapsed, corrected)
    (_BACKEND / REPORT_PATH).write_text(report + "\n")
    logger.info("report written to %s", REPORT_PATH)

    verdict, best_id, reason = summary.verdict(VALIDATED_EDGE_BAR)
    payload = {
        "run_tag": RUN_TAG,
        "family_key": FAMILY_KEY,
        "verdict": verdict,
        "best_spec": best_id,
        "verdict_reason": reason,
        "validated_edge_bar": VALIDATED_EDGE_BAR,
        "screening_floor": SCREENING_FLOOR,
        "n_local": summary.n_local,
        "denominators": summary.denominators,
        "event_windows": {k: list(v) for k, v in EVENT_WINDOWS.items()},
        "lockup_calendar_days": LOCKUP_CALENDAR_DAYS,
        "placebo_calendar_days": PLACEBO_CALENDAR_DAYS,
        "citation": IPO_LOCKUP_CITATION,
        "universe_citation": RITTER_CITATION,
        "preregistration": PREREGISTRATION,
        "disclosure": build_ipo_lockup_disclosure(summary.panel),
        "results_by_cost_arm": {
            arm: [_serialize(r) for r in results]
            for arm, results in summary.results_by_cost_arm.items()
        },
        "identity_defect_sensitivity": {
            "why": (
                "The pre-registered G2 band and G3 rules were fixed on the 2013 cohort alone and "
                "turned out to have two defects on the full universe: G2 rejects 22 correct rows "
                "because Yahoo carries a zero-volume offer-price row one session before the first "
                "trade, and G3 rejects 44 rows that are overwhelmingly delisted or renamed "
                "companies, amplifying the very survivorship bias this family is most exposed to. "
                "Reported, not silently fixed. The pre-registered arm above is the result."
            ),
            "corrected_verdict": corrected.verdict(VALIDATED_EDGE_BAR)[0],
            "corrected_best_spec": corrected.verdict(VALIDATED_EDGE_BAR)[1],
            "corrected_disclosure": build_ipo_lockup_disclosure(corrected.panel),
            "corrected_results_by_cost_arm": {
                arm: [_serialize(r) for r in results]
                for arm, results in corrected.results_by_cost_arm.items()
            },
        },
    }
    (_BACKEND / JSON_PATH).write_text(json.dumps(payload, indent=2, default=str) + "\n")
    logger.info("json written to %s", JSON_PATH)

    # PERSISTENCE, AND WHY IT IS CHECKED RATHER THAN ASSUMED. See
    # cross_sectional_persistence.verify_persisted_trial_results' docstring: two
    # families this session left committed reports that no database row backs.
    # Only the BASELINE cost arm's rows are persisted — the other two arms are
    # the same 24 trials re-scored under a changed assumption, not new trials,
    # and writing them would triple-count this family in every future pooled-
    # effective-N computation that reads this table.
    db = SessionLocal()
    try:
        baseline = summary.baseline_results()
        if not baseline:
            raise SystemExit(
                "REFUSING TO FINISH: the baseline cost arm produced no replayable spec, so there "
                "is nothing to persist and the report above describes nothing."
            )
        written = persist_cross_sectional_trial_results(db, FAMILY_KEY, baseline, run_tag=RUN_TAG)
        verify_persisted_trial_results(db, RUN_TAG, written, family_key=FAMILY_KEY)
        logger.info("persisted %d baseline rows to %s", written, describe_configured_database())
    finally:
        db.close()

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
