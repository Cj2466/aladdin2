#!/usr/bin/env python
"""Build MECHANICAL-FIELDS-ONLY registration scorecard drafts for the four
families holding a live forward registration.

WHY THIS SCRIPT EXISTS AND WHAT IT DELIBERATELY DOES NOT DO
=============================================================
tests/test_registration_scorecards.py::test_every_family_has_a_scorecard is
DELIBERATELY red (55 of 57 families have no scorecard as of 2026-09-10) and
that module's docstring forbids writing scorecards from the code: "An honest
Layer 2 source_locus needs the construction context the original author had
-- which paper section they were reading when they picked a breakpoint --
and inventing one produces a citation that LOOKS verified and is not."

This script does NOT try to make that test pass and does NOT write to
data/research_runs/scorecards/ (the validator's directory). It writes DRAFT
JSON files to this directory instead, containing ONLY fields that can be
mechanically pulled from persisted records -- the DB, the committed
dsr_policy_n.json ladder, the family's own *_forward_registration.py module,
and (where one exists) a committed *_PREREGISTRATION.txt. Every judgment
field (decision, decision_rationale, verdict, all of Layer 2, Layer 3's
source_claim_type/claim_evidence, Layer 4) is left null and listed in a
top-level "gaps" array with a reason. A human or a Fable pass with the actual
source papers in hand fills the rest and moves the result into
data/research_runs/scorecards/.

THE FOUR FAMILIES AND THEIR CANONICAL RUN
==========================================
cross_sectional_trial_results is not keyed 1:1 with the live forward
registrations (registration_scorecard.py's docstring on parse_scorecard
explains why: "cross_sectional_trial_results and
cross_sectional_forward_validation_registrations do NOT share a
vocabulary"). The mapping below was confirmed against
live_registration_family_keys() in
app/services/research_lab/registration_scorecard.py and against row counts
in cross_sectional_trial_results (verified live 2026-09-10):

  quality_cbop / cbop_ls_h63                  -> trial family "quality_cbop"     (27 rows)
  short_interest_ratio / si_ratio_hedged_h21  -> trial family "short_interest"   (24 rows)
  lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol -> trial family "lazy_prices" (360 rows)
  cross_sectional_crypto / xc_btcbeta_l180_h180 -> trial family "crypto"         (28 rows)

Each of the four trial families has MULTIPLE run_tags per trial_id (reruns
with cost-model corrections, global_effective_n sweeps, etc.) -- picking
"whichever row happens to have the highest DSR" or "the most recent
computed_at" would silently choose a different methodological variant than
the one that was actually used to make the registration decision, which is a
judgment this script must not make. Instead each family's own
*_forward_registration.py module quotes an EXACT run_tag and DSR value it
relied on when the registration was recorded; this script reads that number
as a citation (see CANONICAL_RUN by family below) and then VERIFIES,
computationally, that the DB row filed under that exact run_tag reproduces
the quoted DSR to within float precision before using it. That is a
mechanical cross-check, not a choice -- if it fails the script raises rather
than silently picking a different row.

RECOMPUTING DSR AT THE OTHER LADDER RUNGS
==========================================
full_result_json persists DSR only at the family's own n_local (its
"n_trials"), never at the three pooled rungs -- those did not exist as a
concept when most of these rows were written. But it DOES persist the
per-period inputs the DSR formula needs (sharpe_net_annualized,
n_observations, skewness, kurtosis, sigma_sr_annualized), and
deflated_sharpe.compute_deflated_sharpe's own body is nothing more than:

    sr0 = expected_max_sharpe_under_noise(sigma_sr_daily, n_trials)
    dsr = probabilistic_sharpe_ratio(sr_hat_daily, sr0, n, skew, kurt)

with de-annualization by periods_per_year on the way in and re-annualization
of sr0 on the way out (deflated_sharpe.py lines ~196-238). Calling those same
two certified, tested public functions directly with n_trials swapped for
each pooled rung is therefore an exact, mechanical re-application of the
existing formula to persisted inputs -- not a new computation and not a
judgment call. This is the SAME technique already used to backfill the
pooled rungs on a real, merged scorecard: see
data/research_runs/scorecards/low_frequency_patterns_SCORECARD.json's
layer_1_statistical.ladder_note_2026-09-09.

periods_per_year (252 vs 365) is not persisted either. It is determined
here by BRUTE-FORCE VERIFICATION: try both, keep whichever one exactly
reproduces the persisted DSR at n_local (see _infer_periods_per_year). This
reproduced 252 for the three equity/short-interest/filing-text families and
365 for crypto, consistent with metrics.TRADING_DAYS_PER_YEAR and this
project's known equities/crypto calendar convention -- not asserted, checked.

PRESERVATION SCORE
===================
preservation_score.py needs the spec's raw daily net-return series, which is
NOT persisted anywhere (full_result_json carries summary stats only) -- this
script does not have it and will not re-run a backtest to produce one (the
task that commissioned this script explicitly forbids that). It instead
reads data/research_runs/preservation_score_2026-09-03.json, a real,
already-committed preservation-score run that covers THREE of the four
families (quality_cbop, short_interest, lazy_prices; NOT crypto, which was
wired into a live registration the day after that run) under the exact same
run_tags this script independently identified as canonical. Where present,
those numbers are copied through with their provenance and any known
reproduction caveat (lazy_prices' rerun DSR differs from the registered DSR
by ~0.059 -- disclosed, not resolved, here). Where absent (crypto), the
field is null and listed as a gap.

POWER BLOCK
============
Deliberately left null for all four families. dsr_power's block must be
seeded from "the effect size the source literature claims... the
pre-registration, written before the family ran" (registration_scorecard.py
docstring). Only two of the four families (short_interest, lazy_prices) have
a committed *_PREREGISTRATION.txt at all, and even for those, picking out
"the" claimed Sharpe and converting it net-of-costs the way the source paper
would have wanted is a reading-and-interpretation task, not a mechanical
lookup -- exactly the kind of judgment this draft generator must not make.
Listed as a gap for all four.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

from app.config import settings
from app.services.research_lab.deflated_sharpe import (
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.registration_scorecard import (
    required_pooled_denominators,
)

DRAFTS_DIR = Path(__file__).resolve().parent
VALIDATOR_SCORECARD_DIR = BACKEND / "data" / "research_runs" / "scorecards"
PRESERVATION_ARTIFACT = BACKEND / "data" / "research_runs" / "preservation_score_2026-09-03.json"

if not settings.database_url.startswith("sqlite"):
    raise SystemExit(f"this script reads the local SQLite trial store; got {settings.database_url!r}")
DB_PATH = Path(settings.database_url.split("sqlite:///", 1)[1])

FLOAT_TOL = 1e-9


@dataclass(frozen=True)
class FamilySpec:
    live_family_key: str  # e.g. "quality_cbop" -- the forward-registration key
    live_pattern_id: str  # e.g. "cbop_ls_h63"
    trial_family_key: str  # e.g. "quality_cbop" -- cross_sectional_trial_results.family_key
    trial_id: str  # cross_sectional_trial_results.trial_id
    canonical_run_tag: str
    expected_dsr_at_n_local: float  # quoted verbatim from the registration module, for the cross-check
    threshold: float | None
    threshold_source: str
    threshold_gap_reason: str | None
    preregistration_path: str | None
    preregistration_gap_reason: str | None


# Every quoted DSR/run_tag/threshold value below was read directly out of the
# named file at the named location -- not retyped from memory. See the module
# docstring's CANONICAL_RUN discussion.
FAMILIES: tuple[FamilySpec, ...] = (
    FamilySpec(
        live_family_key="quality_cbop",
        live_pattern_id="cbop_ls_h63",
        trial_family_key="quality_cbop",
        trial_id="cbop_ls_h63",
        canonical_run_tag="quality_build_2026-08-28",
        expected_dsr_at_n_local=0.8174,  # quality_forward_registration.py:26, "DSR 0.8174 (n=9)" -- rounded to 4dp in the source; DB row checked to full precision
        threshold=0.5,
        threshold_source=(
            "app/services/research_lab/quality_forward_registration.py lines 22-23: "
            "\"both clear DSR >= 0.5 -- the level this codebase treats everywhere else as "
            "the line below which a result is an honest negative.\" This registration is "
            "explicitly NOT a validated-edge (0.95) registration -- the module's own opening "
            "paragraph says \"Neither is a promotion, and neither claims a validated edge.\""
        ),
        threshold_gap_reason=None,
        preregistration_path=None,
        preregistration_gap_reason=(
            "No *_PREREGISTRATION.txt for quality_cbop was found under data/research_runs/ "
            "(searched for *cbop*, *quality*PREREGISTRATION*, case-insensitive). The registration "
            "decision and its reasoning are recorded instead in "
            "app/services/research_lab/quality_forward_registration.py, which is a post-hoc "
            "registration writeup, not a pre-registration (it is written AFTER the backtest, unlike "
            "the PREREGISTRATION.txt convention used for short_interest and lazy_prices)."
        ),
    ),
    FamilySpec(
        live_family_key="short_interest_ratio",
        live_pattern_id="si_ratio_hedged_h21",
        trial_family_key="short_interest",
        trial_id="si_ratio_hedged_h21",
        canonical_run_tag="short_interest_build_2026-09-02",
        expected_dsr_at_n_local=0.7962,  # short_interest_forward_registration.py:29-31
        threshold=0.95,
        threshold_source=(
            "data/research_runs/short_interest_PREREGISTRATION.txt line 305-307: \"Reported as a "
            "VALIDATED EDGE only if BOTH hold: (i) the best spec's deflated Sharpe (DSR, n_trials = "
            "12) clears 0.95; AND\" [see line 308 for the second condition, not quoted here since it "
            "is not needed to fix the threshold number]. Note: this is the bar the FAMILY's best spec "
            "was screened against, not necessarily this specific registered spec (see "
            "short_interest_forward_registration.py: the registered spec si_ratio_hedged_h21 is "
            "explicitly NOT the family's best-DSR spec -- chosen instead because it measures the "
            "paper's actual construct; DSR 0.7962 sits below this same 0.95 bar)."
        ),
        threshold_gap_reason=None,
        preregistration_path="data/research_runs/short_interest_PREREGISTRATION.txt",
        preregistration_gap_reason=None,
    ),
    FamilySpec(
        live_family_key="lazy_prices_jaccard_full",
        live_pattern_id="lazy_jaccard_full_h126_ivol",
        trial_family_key="lazy_prices",
        trial_id="lazy_jaccard_full_h126_ivol",
        canonical_run_tag="lazy_prices_2026-09-01",
        expected_dsr_at_n_local=0.7540,  # lazy_prices_forward_registration.py:33, quoted to 4dp
        threshold=0.95,
        threshold_source=(
            "data/research_runs/lazy_prices_2026-09-01_preregistration.txt line 411: \"at least one "
            "spec with sharpe_annualized > 0 AND dsr >= 0.95.\" Also restated in "
            "app/services/research_lab/lazy_prices_forward_registration.py line 26: \"sharpe > 0 AND "
            "dsr >= 0.95; the best spec reached DSR 0.7540\"."
        ),
        threshold_gap_reason=None,
        preregistration_path="data/research_runs/lazy_prices_2026-09-01_preregistration.txt",
        preregistration_gap_reason=None,
    ),
    FamilySpec(
        live_family_key="cross_sectional_crypto",
        live_pattern_id="xc_btcbeta_l180_h180",
        trial_family_key="crypto",
        trial_id="xc_btcbeta_l180_h180",
        canonical_run_tag="global_effective_n_2026-09-04",
        expected_dsr_at_n_local=0.3552701584,  # bab_forward_registration.py:174/256, quoted to 10dp
        threshold=None,
        threshold_source="",
        threshold_gap_reason=(
            "No single numeric dsr_pass_threshold is pre-declared for this family in "
            "app/services/research_lab/bab_forward_registration.py. Unlike the other three "
            "registrations, this one explicitly states the spec 'does not clear the bar' and 'DSR "
            "still nowhere near any bar this project has used for a live promotion' (lines 178-179) "
            "WITHOUT naming which of this project's two standing bars (0.5 screening floor or 0.95 "
            "validated-edge bar) is meant, because this registration is an explicit, disclosed "
            "EXCEPTION to the normal DSR-pass registration path (a decision to forward-track one "
            "hypothesis specifically because its backward confound-check passed even though its DSR "
            "did not) rather than a family judged against either standing bar. Picking one of the two "
            "numbers to fill in here would be inventing a pre-declared bar that was never stated for "
            "this family, which is exactly the kind of judgment this draft generator must not make."
        ),
        preregistration_path=None,
        preregistration_gap_reason=(
            "No *_PREREGISTRATION.txt for crypto/xc_btcbeta exists (searched for *crypto*, *btcbeta*, "
            "*bab*PREREGISTRATION* under data/research_runs/, case-insensitive; none found). The "
            "closest analogous document is app/services/research_lab/bab_forward_registration.py "
            "itself, but by its own account that module records a decision made 2026-08-27 AFTER the "
            "backward screening result was already known ('READ THIS BEFORE TREATING THAT "
            "REGISTRATION AS ANYTHING... Nothing screened on 2026-08-27 cleared this project's "
            "significance bar' -- lines 4-6), so it is a registration writeup, not prose written "
            "BEFORE a result existed, which is what preregistration_path is defined to point at."
        ),
    ),
)

POOLED_RUNGS = required_pooled_denominators()


def _fetch_row(con: sqlite3.Connection, family_key: str, trial_id: str, run_tag: str) -> dict:
    cur = con.cursor()
    cur.execute(
        "select computed_at, sharpe_annualized, n_observations, n_trials, dsr, psr_vs_zero, "
        "full_result_json from cross_sectional_trial_results "
        "where family_key = ? and trial_id = ? and run_tag = ?",
        (family_key, trial_id, run_tag),
    )
    row = cur.fetchone()
    if row is None:
        raise SystemExit(
            f"no row found for family_key={family_key!r} trial_id={trial_id!r} run_tag={run_tag!r} "
            "-- the canonical run_tag hardcoded in this script no longer matches the DB. Do not "
            "silently fall back to a different row; investigate."
        )
    computed_at, sharpe_annualized, n_observations, n_trials, dsr, psr_vs_zero, full_result_json = row
    payload = json.loads(full_result_json)
    ds = payload["deflated_sharpe"]
    return {
        "computed_at": computed_at,
        "sharpe_annualized": sharpe_annualized,
        "n_observations": n_observations,
        "n_trials": n_trials,
        "dsr": dsr,
        "psr_vs_zero": psr_vs_zero,
        "citation": payload.get("citation"),
        "n_formations": payload.get("n_formations"),
        "avg_names_per_leg": payload.get("avg_names_per_leg"),
        "total_cost_drag": payload.get("total_cost_drag"),
        "sharpe_net_annualized": ds["sharpe_net_annualized"],
        "skewness": ds["skewness"],
        "kurtosis": ds["kurtosis"],
        "sigma_sr_annualized": ds["sigma_sr_annualized"],
        "dsr_at_n_local_persisted": ds["dsr"],
    }


def _dsr_from_summary(
    sharpe_annualized: float,
    n_obs: int,
    n_trials: int,
    sigma_sr_annualized: float,
    skew: float,
    kurt: float,
    periods_per_year: float,
) -> float | None:
    """Exactly deflated_sharpe.compute_deflated_sharpe's own inner computation
    (module lines ~196-226), applied directly to already-persisted summary
    stats instead of re-deriving stats from a raw return series that is not
    available. Calls the SAME two public, tested functions
    compute_deflated_sharpe calls; no formula is re-derived here."""
    import numpy as np

    sr_hat_daily = sharpe_annualized / np.sqrt(periods_per_year)
    sigma_sr_daily = sigma_sr_annualized / np.sqrt(periods_per_year)
    sr0_daily = expected_max_sharpe_under_noise(sigma_sr_daily, n_trials)
    if sr0_daily is None:
        return None
    return probabilistic_sharpe_ratio(sr_hat_daily, sr0_daily, n_obs, skew, kurt)


def _infer_periods_per_year(row: dict, n_local: int) -> float:
    """Brute-force check: try 252 (equities) and 365 (crypto calendar), keep
    whichever exactly reproduces the row's own persisted DSR at n_local. Not
    a guess -- a verified match, or the script raises."""
    for ppy in (252.0, 365.0):
        v = _dsr_from_summary(
            row["sharpe_net_annualized"],
            row["n_observations"],
            n_local,
            row["sigma_sr_annualized"],
            row["skewness"],
            row["kurtosis"],
            ppy,
        )
        if v is not None and abs(v - row["dsr_at_n_local_persisted"]) < FLOAT_TOL:
            return ppy
    raise SystemExit(
        f"could not reproduce persisted DSR {row['dsr_at_n_local_persisted']} at n_local={n_local} "
        "with periods_per_year in (252, 365) -- refusing to guess."
    )


def _load_preservation_record(trial_family_key: str, trial_id: str, run_tag: str) -> dict | None:
    if not PRESERVATION_ARTIFACT.exists():
        return None
    payload = json.loads(PRESERVATION_ARTIFACT.read_text())
    for spec in payload["specs"]:
        if (
            spec.get("family_key") == trial_family_key
            and spec.get("pattern_id") == trial_id
            and spec.get("run_tag") == run_tag
        ):
            return spec
    return None


def build_draft(spec: FamilySpec, con: sqlite3.Connection) -> dict:
    row = _fetch_row(con, spec.trial_family_key, spec.trial_id, spec.canonical_run_tag)

    # Cross-check against the value quoted in the registration module BEFORE
    # trusting this row for anything else.
    if abs(row["dsr_at_n_local_persisted"] - spec.expected_dsr_at_n_local) > 5e-4:
        raise SystemExit(
            f"{spec.live_family_key}: DB row under run_tag={spec.canonical_run_tag!r} has persisted "
            f"DSR {row['dsr_at_n_local_persisted']} but the registration module quotes "
            f"{spec.expected_dsr_at_n_local} -- these should match to the quoted precision. Refusing "
            "to proceed; the canonical run_tag may be wrong."
        )

    n_local = row["n_trials"]
    periods_per_year = _infer_periods_per_year(row, n_local)

    denominators = sorted({n_local, *POOLED_RUNGS})
    dsr_by_n: dict[str, float | None] = {}
    for n in denominators:
        dsr_by_n[str(n)] = _dsr_from_summary(
            row["sharpe_net_annualized"],
            row["n_observations"],
            n,
            row["sigma_sr_annualized"],
            row["skewness"],
            row["kurtosis"],
            periods_per_year,
        )
    assert dsr_by_n[str(n_local)] is not None
    assert abs(dsr_by_n[str(n_local)] - row["dsr_at_n_local_persisted"]) < FLOAT_TOL, (
        "recomputed dsr_by_n[n_local] must reproduce the persisted DSR exactly"
    )

    # Compute Policy D's verdict for reference ONLY -- never placed in the
    # "verdict" field itself, per the task instructions. Kept out of the
    # schema-shaped fields entirely, and surfaced only inside the gap note,
    # so this draft cannot be mistaken for an actual decision.
    computed_verdict_note: str
    if spec.threshold is None:
        computed_verdict_note = (
            "not computable: no single pre-declared dsr_pass_threshold was found for this family "
            "(see the threshold gap above)"
        )
    else:
        local_dsr = dsr_by_n[str(n_local)]
        highest_n = max(denominators)
        highest_dsr = dsr_by_n[str(highest_n)]
        if local_dsr is None or local_dsr < spec.threshold:
            computed_verdict_note = (
                f"Policy D's policy_d_verdict() computes 'definite_negative' from these numbers "
                f"(bar {spec.threshold}, DSR at n_local={n_local} is {local_dsr:.4f}) -- shown here "
                "for the human reviewer's reference only, not asserted as the registration's verdict"
            )
        elif highest_dsr is not None and highest_dsr >= spec.threshold:
            computed_verdict_note = (
                f"Policy D's policy_d_verdict() computes 'pass' from these numbers (bar "
                f"{spec.threshold}, DSR at every rung from n_local={n_local} through {highest_n} "
                f"stays >= {spec.threshold}: highest rung DSR is {highest_dsr:.4f}) -- shown here for "
                "the human reviewer's reference only, not asserted as the registration's verdict"
            )
        else:
            computed_verdict_note = (
                f"Policy D's policy_d_verdict() computes 'unresolved' from these numbers (bar "
                f"{spec.threshold}, DSR passes at n_local={n_local} ({local_dsr:.4f}) but fails by "
                f"the highest measured rung {highest_n} ({highest_dsr!r})) -- shown here for the "
                "human reviewer's reference only, not asserted as the registration's verdict"
            )

    preservation = _load_preservation_record(spec.trial_family_key, spec.trial_id, spec.canonical_run_tag)

    gaps: list[dict] = []

    gaps.append({"field": "decision", "reason": "operational/registration judgment, not mechanical; left for a human/Fable pass"})
    gaps.append({"field": "decision_rationale", "reason": "same as decision"})
    gaps.append(
        {
            "field": "layer_1_statistical.verdict",
            "reason": (
                "left null per this draft's scope even though it is deterministically computable "
                "from dsr_by_n and dsr_pass_threshold (Policy D's policy_d_verdict()) -- the "
                "reference-only computed value is recorded in layer_1_statistical.verdict_computed_"
                "for_reference_only, which is NOT a schema field and must not be copied into "
                "'verdict' without a human confirming the threshold/run choices above first"
            ),
        }
    )
    if spec.threshold is None:
        gaps.append({"field": "layer_1_statistical.dsr_pass_threshold", "reason": spec.threshold_gap_reason})
    gaps.append(
        {
            "field": "layer_1_statistical.power",
            "reason": (
                "requires the pre-registration's claimed Sharpe (a specific number read and "
                "interpreted from the source literature), which is an interpretive task this draft "
                "generator must not perform; see module docstring POWER BLOCK section"
            ),
        }
    )
    if preservation is None:
        gaps.append(
            {
                "field": "layer_1_statistical.preservation_score / preservation_score_no_stab",
                "reason": (
                    "not recoverable from any persisted record found: preservation_score.py needs "
                    "the spec's raw daily net-return series, which is not persisted, and the one "
                    "committed preservation-score artifact (preservation_score_2026-09-03.json) does "
                    "not cover this family (crypto/xc_btcbeta was wired into a live registration the "
                    "day after that run). Not recomputed here -- recomputing would mean re-running a "
                    "backtest, which this task explicitly forbids."
                ),
            }
        )
    gaps.append(
        {
            "field": "layer_2_mechanism_fidelity (entire block)",
            "reason": (
                "requires reading the source paper(s) to state an honest source_locus per "
                "construction choice; reconstructing this from code would fabricate a citation that "
                "looks verified and is not (see test_registration_scorecards.py module docstring)"
            ),
        }
    )
    gaps.append(
        {
            "field": "layer_3_regime_conditional.source_claim_type / claim_evidence",
            "reason": "requires reading the source literature to determine whether its claim is unconditional or regime-conditional",
        }
    )
    gaps.append(
        {
            "field": "layer_4_economics (entire block)",
            "reason": "cost-scenario sourcing, capacity method, and the regime-coverage narrative statement all require judgment/interpretation this draft generator must not perform",
        }
    )
    if spec.preregistration_gap_reason:
        gaps.append({"field": "preregistration_path", "reason": spec.preregistration_gap_reason})

    draft = {
        "draft_status": (
            "INCOMPLETE - mechanical fields only; layer 2 requires reading the source papers and "
            "must not be reconstructed from code"
        ),
        "schema": "registration_scorecard/v1",
        "family_key": spec.live_family_key,
        "covers_family_keys": sorted({spec.live_family_key, spec.trial_family_key}),
        "pattern_id": spec.live_pattern_id,
        "written_at": datetime.now(UTC).date().isoformat(),
        "author": "assembled by a Sonnet sub-agent, unreviewed draft",
        "decision": None,
        "decision_rationale": None,
        "preregistration_path": spec.preregistration_path,
        "layer_1_statistical": {
            "best_spec_pattern_id": spec.trial_id,
            "n_local": n_local,
            "dsr_pass_threshold": spec.threshold,
            "dsr_pass_threshold_source": spec.threshold_source or None,
            "dsr_by_n": dsr_by_n,
            "verdict": None,
            "verdict_computed_for_reference_only_NOT_A_SCHEMA_FIELD": computed_verdict_note,
            "sharpe_net_annualized": row["sharpe_net_annualized"],
            "n_observations": row["n_observations"],
            "periods_per_year": periods_per_year,
            "periods_per_year_note": (
                "not persisted directly; determined by brute-force verification against the "
                "persisted DSR at n_local (see build_scorecard_drafts.py:_infer_periods_per_year)"
            ),
            "preservation_score": preservation["preservation_score"] if preservation else None,
            "preservation_score_no_stab": preservation["preservation_score_no_stab"] if preservation else None,
            "preservation_inputs_note": (
                (
                    f"copied from data/research_runs/preservation_score_2026-09-03.json, spec entry "
                    f"family_key={spec.trial_family_key!r} pattern_id={spec.trial_id!r} run_tag="
                    f"{spec.canonical_run_tag!r} (same canonical run_tag used for layer_1's other "
                    f"fields); cred fed into that score was rerun_dsr={preservation['rerun_dsr']:.4f} "
                    f"at rerun_n_trials={preservation['rerun_n_trials']}, periods_per_year=252. "
                    + (
                        "CAVEAT: that rerun's DSR differs from this family's registered/persisted DSR "
                        f"({row['dsr_at_n_local_persisted']:.4f}) by "
                        f"{abs(preservation['rerun_dsr'] - row['dsr_at_n_local_persisted']):.4f} -- "
                        "disclosed here, not resolved. See preservation_score_2026-09-03.json's "
                        "'families' summary entry for this family for the run's own reproduction "
                        "quality numbers."
                        if abs(preservation["rerun_dsr"] - row["dsr_at_n_local_persisted"]) > 1e-3
                        else "This rerun DSR matches the registered DSR to within 1e-3."
                    )
                )
                if preservation
                else None
            ),
            "power": None,
        },
        "layer_2_mechanism_fidelity": None,
        "layer_3_regime_conditional": {
            "source_claim_type": None,
            "claim_evidence": None,
            "regime_definition_rule": None,
            "regime_rule_pre_declared_at": None,
            "dsr_in_regime": None,
            "dsr_out_of_regime": None,
            "not_applicable_reason": None,
        },
        "layer_4_economics": None,
        "provenance": {
            "trial_family_key": spec.trial_family_key,
            "trial_id": spec.trial_id,
            "canonical_run_tag": spec.canonical_run_tag,
            "canonical_run_tag_source": (
                "the DSR value quoted for this run_tag in the family's own "
                "*_forward_registration.py module (see FAMILIES table in this script) was checked "
                "against the DB row and matched to within 5e-4"
            ),
            "db_computed_at": row["computed_at"],
            "db_n_formations": row["n_formations"],
            "db_avg_names_per_leg": row["avg_names_per_leg"],
            "db_total_cost_drag": row["total_cost_drag"],
            "db_citation_field_verbatim": row["citation"],
            "generated_by": "data/research_runs/scorecard_drafts_2026-09-10/build_scorecard_drafts.py",
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "database_path": str(DB_PATH),
        },
        "gaps": gaps,
    }
    return draft


def main() -> int:
    con = sqlite3.connect(str(DB_PATH))
    try:
        written = []
        for spec in FAMILIES:
            draft = build_draft(spec, con)
            out_path = DRAFTS_DIR / f"{spec.live_family_key}_SCORECARD_DRAFT.json"
            out_path.write_text(json.dumps(draft, indent=2, sort_keys=False) + "\n")
            written.append(out_path)
            print(f"wrote {out_path}")
    finally:
        con.close()

    for path in written:
        assert path.resolve().parent != VALIDATOR_SCORECARD_DIR.resolve(), (
            f"{path} must NOT be written into the validator's directory {VALIDATOR_SCORECARD_DIR}"
        )
    print(f"\n{len(written)} draft(s) written to {DRAFTS_DIR}")
    print(f"(validator reads from {VALIDATOR_SCORECARD_DIR} -- untouched by this script)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
