"""THE REGISTRATION SCORECARD — Layers 1-4, made a required artifact.

WHAT THIS EXISTS TO STOP
========================
Two failures this project actually had, neither hypothetical:

 1. preservation_score.py shipped 2026-09-03 and was then SKIPPED for the two
    registration decisions that came after it (asset_growth and
    residual_momentum, both DECLINED in dd288f9/20417f8 on DSR and prose
    alone). It was applied only because the repo owner asked directly whether
    it had been. A metric that is applied when someone remembers is not a
    gate; it is a decoration.

 2. Every family states its Layer 1 numbers, its citations, its regime claim
    and its cost assumptions somewhere — a pre-registration, a run report, a
    commit message, or a conversation — and no two families state the same
    SET of things. There has been no way to ask "which families have never
    had a capacity estimate written down?" except by reading thirty documents.

So the scorecard is a committed, schema-validated JSON artifact per family,
and tests/test_registration_scorecards.py fails when a family that has
persisted trial results (or holds a live forward registration) has no filled
scorecard. The template a human fills in is
templates/REGISTRATION_SCORECARD_TEMPLATE.md; this module is the thing that
refuses to accept it half-filled.

WHY JSON AND NOT THE .txt PRE-REGISTRATION FORMAT
=================================================
Both conventions already exist here and each is kept for what it is good at.
data/research_runs/*_PREREGISTRATION.txt are BINDING PROSE written before a
result exists — argument, prior, and the reasoning behind a grid. Nothing
about them should become machine-readable; their value is that a human wrote
out why. The scorecard is the opposite artifact: a fixed set of fields that
must exist for EVERY family so they can be compared and so absence is
detectable. That is the same job global_effective_n.json does, and it is
built the same way — committed JSON, a frozen dataclass, and a loader that
RAISES rather than defaulting, because a silently-defaulted governance field
is indistinguishable from a filled one.

A scorecard does not replace a pre-registration and cannot: a scorecard is
written AFTER results exist. It records what the decision was made on.

POLICY D — THE MULTI-N DSR RULE THIS ENCODES
============================================
Agreed after commit f385fc5 wired global_effective_n.dsr_n_trials() into
every family. That function returns max(local grid size, pooled effective N),
and the pooled estimate currently returns ONC's own structural floor of 2
(effective_n_clustering found no real cluster structure: 25 of 25 seeds
returned k=2, mean silhouette 0.235). So the wiring is presently a NO-OP —
every family still deflates against its own grid size — and pretending the
project knows one precise N would be false either way.

Policy D therefore refuses to pick one N and reports three:

  * n_local      the family's own pre-declared grid size
  * 481          n_specs_clustered in global_effective_n.json — the pooled
                 population that actually carries a realized return series
  * 857          raw_pooled_distinct_trials in the same file — every distinct
                 trial this project has ever persisted

and reads them under a TWO-TIER rule:

  DEFINITE_NEGATIVE   fails at n_local. Nothing above it can rescue it;
                      a larger denominator only ever lowers DSR.
  UNRESOLVED          passes at n_local but fails at a higher measured N.
                      NOT a pass. Explicitly not eligible for live or
                      capital-relevant status without more forward-validation
                      evidence.
  PASS                clears the bar even at the highest measured N.

MONOTONICITY, which is what makes the three-point report sufficient rather
than a sample of a curve: DSR = PSR(SR0(N)), SR0 is strictly increasing in N
(deflated_sharpe.expected_max_sharpe_under_noise), and PSR is strictly
decreasing in its benchmark. So DSR is strictly decreasing in N and the three
points bracket every N between them. There is no N in [n_local, 857] at which
a DEFINITE_NEGATIVE passes.

THE THRESHOLD IS PER-FAMILY AND MUST BE STATED, NOT ASSUMED. This project has
two standing bars and they are not interchangeable: 0.95 is the
"VALIDATED EDGE" bar (e.g. short_interest_PREREGISTRATION.txt section 5) and
0.50 is the "forward-registration screening floor, never proof" (same
document, section 8). A scorecard names the bar its own pre-registration
declared; this module computes the verdict against that number and refuses a
scorecard whose stated verdict disagrees with the computed one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA = "registration_scorecard/v1"

# data/research_runs/scorecards/<family_key>_SCORECARD.json — alongside the
# *_PREREGISTRATION.txt documents they close out, not buried in the module
# tree, because a human writes them.
SCORECARD_DIR = (
    Path(__file__).resolve().parents[3] / "data" / "research_runs" / "scorecards"
)
SCORECARD_SUFFIX = "_SCORECARD.json"

TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "templates" / "REGISTRATION_SCORECARD_TEMPLATE.md"
)

# The two pooled denominators Policy D reports alongside n_local. Both are
# read from global_effective_n.json rather than retyped, so they cannot drift
# apart from the artifact that measured them.
POOLED_N_CLUSTERED_KEY = "n_specs_clustered"
POOLED_N_RAW_KEY = "raw_pooled_distinct_trials"

# Text that means "not filled in yet". Checked case-insensitively against
# every string field. A scorecard is either finished or it is not present;
# there is no half-filled state worth accepting, because a half-filled one
# passes a completeness test while answering nothing.
PLACEHOLDER_PATTERNS = (
    re.compile(r"^\s*$"),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"\bFIXME\b", re.IGNORECASE),
    re.compile(r"\bXXX\b"),
    re.compile(r"<[^>]*>"),  # <fill this in>
    re.compile(r"\bfill me\b", re.IGNORECASE),
)

VERDICT_DEFINITE_NEGATIVE = "definite_negative"
VERDICT_UNRESOLVED = "unresolved"
VERDICT_PASS = "pass"
VERDICTS = (VERDICT_DEFINITE_NEGATIVE, VERDICT_UNRESOLVED, VERDICT_PASS)

CLAIM_UNCONDITIONAL = "unconditional"
CLAIM_CONDITIONAL = "conditional"
CLAIM_TYPES = (CLAIM_UNCONDITIONAL, CLAIM_CONDITIONAL)


# The major market regimes a US equity backtest window either contains or does
# not. Dates are the ones this project's own reports already use when they
# talk about these episodes; each is a CALENDAR BRACKET for disclosure, not a
# dated claim about when a regime "really" started. They exist so
# regime-coverage cannot be asserted: the validator computes overlap from the
# declared window and refuses a scorecard whose present/absent lists disagree.
@dataclass(frozen=True)
class MarketRegime:
    key: str
    label: str
    start: date
    end: date


KNOWN_REGIMES: tuple[MarketRegime, ...] = (
    MarketRegime("dotcom_2000", "dot-com bust", date(2000, 3, 24), date(2002, 10, 9)),
    MarketRegime("gfc_2008", "global financial crisis", date(2007, 10, 9), date(2009, 3, 9)),
    MarketRegime("covid_2020", "COVID crash and recovery", date(2020, 2, 19), date(2020, 12, 31)),
    MarketRegime("rate_hike_2022", "2022 rate-hike bear market", date(2022, 1, 3), date(2022, 10, 12)),
)
KNOWN_REGIME_KEYS = tuple(r.key for r in KNOWN_REGIMES)

# A regime counts as PRESENT only when the tested window covers at least this
# much of it. A window whose last day is 2008-01-02 has technically "touched"
# the GFC and has learned nothing about it; requiring a majority of the
# episode stops a one-day overlap from being reported as coverage.
MIN_REGIME_COVERAGE_FRACTION = 0.5


class ScorecardError(ValueError):
    """A scorecard file exists but is not usable as a governance record.

    Deliberately a hard error and never a warning: every caller of this module
    is either a test asserting completeness or a human reading a decision, and
    both are worse off with a partially-parsed scorecard than with a refusal.
    """


def _require(payload: dict[str, Any], key: str, where: str) -> Any:
    if key not in payload:
        raise ScorecardError(f"{where}: required field {key!r} is missing")
    return payload[key]


def _require_text(payload: dict[str, Any], key: str, where: str) -> str:
    value = _require(payload, key, where)
    if not isinstance(value, str):
        raise ScorecardError(f"{where}.{key}: expected a string, got {type(value).__name__}")
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(value):
            raise ScorecardError(
                f"{where}.{key} is still a placeholder ({value!r} matches {pattern.pattern!r}). "
                "An unfilled governance field is not a filled one."
            )
    return value


def _require_number(payload: dict[str, Any], key: str, where: str) -> float:
    value = _require(payload, key, where)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScorecardError(f"{where}.{key}: expected a number, got {value!r}")
    return float(value)


def _require_int(payload: dict[str, Any], key: str, where: str) -> int:
    value = _require(payload, key, where)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScorecardError(f"{where}.{key}: expected an integer, got {value!r}")
    return value


def _require_date(payload: dict[str, Any], key: str, where: str) -> date:
    raw = _require_text(payload, key, where)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ScorecardError(f"{where}.{key}: {raw!r} is not an ISO date (YYYY-MM-DD)") from exc


def _require_list(payload: dict[str, Any], key: str, where: str, *, min_len: int = 1) -> list[Any]:
    value = _require(payload, key, where)
    if not isinstance(value, list):
        raise ScorecardError(f"{where}.{key}: expected a list, got {type(value).__name__}")
    if len(value) < min_len:
        raise ScorecardError(
            f"{where}.{key}: needs at least {min_len} entr{'y' if min_len == 1 else 'ies'}, got {len(value)}"
        )
    return value


def _require_dict(payload: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    value = _require(payload, key, where)
    if not isinstance(value, dict):
        raise ScorecardError(f"{where}.{key}: expected an object, got {type(value).__name__}")
    return value


def policy_d_verdict(
    *,
    dsr_by_n: dict[int, float | None],
    threshold: float,
    n_local: int,
) -> str:
    """Policy D's two-tier verdict from DSR measured at several denominators.

    `dsr_by_n` maps an n_trials value to the DSR computed at it. A None DSR
    means the machinery could not produce one at that N (deflated_sharpe
    returns None below MIN_TRIALS_FOR_DSR, or on a degenerate return series)
    and is treated as NOT CLEARING the bar — an unmeasurable deflation is not
    a passing one.

    Uses the HIGHEST N present as the pass tier, so a family whose own grid is
    larger than the pooled numbers is judged once rather than twice.
    """
    if n_local not in dsr_by_n:
        raise ScorecardError(f"policy_d_verdict: no DSR supplied at n_local={n_local}")
    local = dsr_by_n[n_local]
    if local is None or local < threshold:
        return VERDICT_DEFINITE_NEGATIVE
    highest_n = max(dsr_by_n)
    highest = dsr_by_n[highest_n]
    if highest is not None and highest >= threshold:
        return VERDICT_PASS
    return VERDICT_UNRESOLVED


def regimes_covered_by(window_start: date, window_end: date) -> tuple[list[str], list[str]]:
    """(present, absent) regime keys for a tested window, computed — never
    declared. Present means the window covers at least
    MIN_REGIME_COVERAGE_FRACTION of the regime's calendar span."""
    present: list[str] = []
    absent: list[str] = []
    for regime in KNOWN_REGIMES:
        overlap_start = max(window_start, regime.start)
        overlap_end = min(window_end, regime.end)
        overlap_days = (overlap_end - overlap_start).days + 1
        regime_days = (regime.end - regime.start).days + 1
        fraction = max(0, overlap_days) / regime_days
        (present if fraction >= MIN_REGIME_COVERAGE_FRACTION else absent).append(regime.key)
    return present, absent


@dataclass(frozen=True)
class Layer1Statistical:
    """DSR under Policy D, plus the preservation score — MANDATORY, no
    exceptions. `preservation_score` may not be omitted for any family: the
    whole reason this layer is a dataclass field rather than a convention is
    that the convention was skipped twice."""

    n_local: int
    dsr_pass_threshold: float
    dsr_by_n: dict[int, float | None]
    verdict: str
    sharpe_net_annualized: float
    n_observations: int
    preservation_score: float
    preservation_score_no_stab: float
    preservation_inputs_note: str
    best_spec_pattern_id: str

    @property
    def computed_verdict(self) -> str:
        return policy_d_verdict(
            dsr_by_n=self.dsr_by_n, threshold=self.dsr_pass_threshold, n_local=self.n_local
        )


@dataclass(frozen=True)
class ConstructionChoice:
    choice: str
    source_locus: str


@dataclass(frozen=True)
class Deviation:
    deviation: str
    reason: str


@dataclass(frozen=True)
class Layer2MechanismFidelity:
    source_citation: str
    source_text_obtained: bool
    construction_choices: tuple[ConstructionChoice, ...]
    deviations: tuple[Deviation, ...]
    independent_reviewer: str
    independent_reviewer_signed_off_at: date
    independent_reviewer_findings: str


@dataclass(frozen=True)
class Layer3RegimeConditional:
    source_claim_type: str
    claim_evidence: str
    regime_definition_rule: str | None
    regime_rule_pre_declared_at: date | None
    dsr_in_regime: float | None
    dsr_out_of_regime: float | None
    not_applicable_reason: str | None

    @property
    def is_conditional(self) -> bool:
        return self.source_claim_type == CLAIM_CONDITIONAL


@dataclass(frozen=True)
class CostScenario:
    name: str
    one_way_bps: float
    source: str
    best_spec_net_sharpe: float


@dataclass(frozen=True)
class CapacityEstimate:
    avg_daily_dollar_volume_usd: float
    participation_cap_fraction: float
    n_names_per_leg: int
    capacity_usd: float
    method: str


@dataclass(frozen=True)
class RegimeCoverage:
    window_start: date
    window_end: date
    regimes_present: tuple[str, ...]
    regimes_absent: tuple[str, ...]
    statement: str


@dataclass(frozen=True)
class Layer4Economics:
    cost_scenarios: tuple[CostScenario, ...]
    capacity: CapacityEstimate
    regime_coverage: RegimeCoverage


@dataclass(frozen=True)
class RegistrationScorecard:
    family_key: str
    covers_family_keys: tuple[str, ...]
    pattern_id: str
    written_at: date
    author: str
    decision: str
    decision_rationale: str
    preregistration_path: str
    layer_1: Layer1Statistical
    layer_2: Layer2MechanismFidelity
    layer_3: Layer3RegimeConditional
    layer_4: Layer4Economics
    source_path: Path = field(compare=False, default=Path())

    def summary(self) -> str:
        l1 = self.layer_1
        points = ", ".join(
            f"N={n}: {'n/a' if v is None else f'{v:.3f}'}" for n, v in sorted(l1.dsr_by_n.items())
        )
        return (
            f"{self.family_key}/{l1.best_spec_pattern_id}: {l1.verdict.upper()} "
            f"(bar {l1.dsr_pass_threshold:.2f}; {points}); "
            f"preservation {l1.preservation_score:.4f}; decision {self.decision}"
        )


def _parse_layer_1(payload: dict[str, Any], where: str) -> Layer1Statistical:
    n_local = _require_int(payload, "n_local", where)
    if n_local < 1:
        raise ScorecardError(f"{where}.n_local must be >= 1, got {n_local}")
    threshold = _require_number(payload, "dsr_pass_threshold", where)
    if not 0.0 < threshold < 1.0:
        raise ScorecardError(
            f"{where}.dsr_pass_threshold must be a probability strictly between 0 and 1, "
            f"got {threshold}. This project's two standing bars are 0.95 (validated edge) "
            "and 0.50 (forward-registration screening floor)."
        )

    raw_points = _require_dict(payload, "dsr_by_n", where)
    dsr_by_n: dict[int, float | None] = {}
    for key, value in raw_points.items():
        try:
            n = int(key)
        except (TypeError, ValueError) as exc:
            raise ScorecardError(f"{where}.dsr_by_n has a non-integer key {key!r}") from exc
        if value is None:
            dsr_by_n[n] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ScorecardError(f"{where}.dsr_by_n[{key}]: expected a number or null, got {value!r}")
        if not 0.0 <= float(value) <= 1.0:
            raise ScorecardError(
                f"{where}.dsr_by_n[{key}] = {value} is not a probability in [0, 1]"
            )
        dsr_by_n[n] = float(value)

    if n_local not in dsr_by_n:
        raise ScorecardError(
            f"{where}.dsr_by_n must include the family's own grid size n_local={n_local} — "
            "Policy D's first tier is the local-N reading and it cannot be inferred."
        )

    # Policy D names 481 and 857 specifically; each is required unless the
    # family's own grid already exceeds it, in which case dsr_n_trials()'s
    # max() makes the two identical and a separate entry would be a duplicate.
    for pooled_n in required_pooled_denominators():
        if pooled_n <= n_local:
            continue
        if pooled_n not in dsr_by_n:
            raise ScorecardError(
                f"{where}.dsr_by_n is missing N={pooled_n}. Policy D requires DSR at the local "
                f"grid size and at both pooled denominators from global_effective_n.json "
                f"({', '.join(str(n) for n in required_pooled_denominators())})."
            )

    verdict = _require_text(payload, "verdict", where)
    if verdict not in VERDICTS:
        raise ScorecardError(f"{where}.verdict must be one of {VERDICTS}, got {verdict!r}")
    computed = policy_d_verdict(dsr_by_n=dsr_by_n, threshold=threshold, n_local=n_local)
    if verdict != computed:
        raise ScorecardError(
            f"{where}.verdict says {verdict!r} but the numbers in this same scorecard compute "
            f"{computed!r} under Policy D (bar {threshold}, DSR {dsr_by_n}). The stated verdict "
            "is never allowed to disagree with the stated numbers."
        )

    preservation = _require_number(payload, "preservation_score", where)
    preservation_no_stab = _require_number(payload, "preservation_score_no_stab", where)
    return Layer1Statistical(
        n_local=n_local,
        dsr_pass_threshold=threshold,
        dsr_by_n=dsr_by_n,
        verdict=verdict,
        sharpe_net_annualized=_require_number(payload, "sharpe_net_annualized", where),
        n_observations=_require_int(payload, "n_observations", where),
        preservation_score=preservation,
        preservation_score_no_stab=preservation_no_stab,
        preservation_inputs_note=_require_text(payload, "preservation_inputs_note", where),
        best_spec_pattern_id=_require_text(payload, "best_spec_pattern_id", where),
    )


def _parse_layer_2(payload: dict[str, Any], where: str) -> Layer2MechanismFidelity:
    choices_raw = _require_list(payload, "construction_choices", where)
    choices = []
    for i, entry in enumerate(choices_raw):
        sub = f"{where}.construction_choices[{i}]"
        if not isinstance(entry, dict):
            raise ScorecardError(f"{sub}: expected an object")
        choices.append(
            ConstructionChoice(
                choice=_require_text(entry, "choice", sub),
                source_locus=_require_text(entry, "source_locus", sub),
            )
        )

    # An EMPTY deviations list is a legitimate, meaningful claim ("we deviated
    # nowhere"), so unlike construction_choices it has no minimum length.
    deviations_raw = _require_list(payload, "deviations", where, min_len=0)
    deviations = []
    for i, entry in enumerate(deviations_raw):
        sub = f"{where}.deviations[{i}]"
        if not isinstance(entry, dict):
            raise ScorecardError(f"{sub}: expected an object")
        deviations.append(
            Deviation(
                deviation=_require_text(entry, "deviation", sub),
                reason=_require_text(entry, "reason", sub),
            )
        )

    obtained = _require(payload, "source_text_obtained", where)
    if not isinstance(obtained, bool):
        raise ScorecardError(f"{where}.source_text_obtained must be true or false, got {obtained!r}")

    return Layer2MechanismFidelity(
        source_citation=_require_text(payload, "source_citation", where),
        source_text_obtained=obtained,
        construction_choices=tuple(choices),
        deviations=tuple(deviations),
        independent_reviewer=_require_text(payload, "independent_reviewer", where),
        independent_reviewer_signed_off_at=_require_date(
            payload, "independent_reviewer_signed_off_at", where
        ),
        independent_reviewer_findings=_require_text(
            payload, "independent_reviewer_findings", where
        ),
    )


def _parse_layer_3(payload: dict[str, Any], where: str) -> Layer3RegimeConditional:
    claim = _require_text(payload, "source_claim_type", where)
    if claim not in CLAIM_TYPES:
        raise ScorecardError(f"{where}.source_claim_type must be one of {CLAIM_TYPES}, got {claim!r}")
    evidence = _require_text(payload, "claim_evidence", where)

    if claim == CLAIM_CONDITIONAL:
        rule = _require_text(payload, "regime_definition_rule", where)
        declared_at = _require_date(payload, "regime_rule_pre_declared_at", where)
        in_regime = _require_number(payload, "dsr_in_regime", where)
        out_regime = _require_number(payload, "dsr_out_of_regime", where)
        return Layer3RegimeConditional(
            source_claim_type=claim,
            claim_evidence=evidence,
            regime_definition_rule=rule,
            regime_rule_pre_declared_at=declared_at,
            dsr_in_regime=in_regime,
            dsr_out_of_regime=out_regime,
            not_applicable_reason=None,
        )

    reason = _require_text(payload, "not_applicable_reason", where)
    for key in ("regime_definition_rule", "dsr_in_regime", "dsr_out_of_regime"):
        if payload.get(key) is not None:
            raise ScorecardError(
                f"{where}.{key} is set but source_claim_type is {CLAIM_UNCONDITIONAL!r}. "
                "An unconditional claim split by regime after the fact is a post-hoc "
                "conditioning, which is the thing Layer 3 exists to make visible."
            )
    return Layer3RegimeConditional(
        source_claim_type=claim,
        claim_evidence=evidence,
        regime_definition_rule=None,
        regime_rule_pre_declared_at=None,
        dsr_in_regime=None,
        dsr_out_of_regime=None,
        not_applicable_reason=reason,
    )


def _parse_layer_4(payload: dict[str, Any], where: str) -> Layer4Economics:
    # At least TWO scenarios: a single cost number is an assumption, and a
    # RANGE is what Layer 4 asks for.
    scenarios_raw = _require_list(payload, "cost_scenarios", where, min_len=2)
    scenarios = []
    for i, entry in enumerate(scenarios_raw):
        sub = f"{where}.cost_scenarios[{i}]"
        if not isinstance(entry, dict):
            raise ScorecardError(f"{sub}: expected an object")
        bps = _require_number(entry, "one_way_bps", sub)
        if bps < 0:
            raise ScorecardError(f"{sub}.one_way_bps must be >= 0, got {bps}")
        scenarios.append(
            CostScenario(
                name=_require_text(entry, "name", sub),
                one_way_bps=bps,
                source=_require_text(entry, "source", sub),
                best_spec_net_sharpe=_require_number(entry, "best_spec_net_sharpe", sub),
            )
        )

    cap_raw = _require_dict(payload, "capacity", where)
    cap_where = f"{where}.capacity"
    capacity = CapacityEstimate(
        avg_daily_dollar_volume_usd=_require_number(cap_raw, "avg_daily_dollar_volume_usd", cap_where),
        participation_cap_fraction=_require_number(cap_raw, "participation_cap_fraction", cap_where),
        n_names_per_leg=_require_int(cap_raw, "n_names_per_leg", cap_where),
        capacity_usd=_require_number(cap_raw, "capacity_usd", cap_where),
        method=_require_text(cap_raw, "method", cap_where),
    )

    cov_raw = _require_dict(payload, "regime_coverage", where)
    cov_where = f"{where}.regime_coverage"
    window_start = _require_date(cov_raw, "window_start", cov_where)
    window_end = _require_date(cov_raw, "window_end", cov_where)
    if window_end <= window_start:
        raise ScorecardError(f"{cov_where}: window_end {window_end} is not after {window_start}")
    declared_present = _require_list(cov_raw, "regimes_present", cov_where, min_len=0)
    declared_absent = _require_list(cov_raw, "regimes_absent", cov_where, min_len=0)
    unknown = sorted((set(declared_present) | set(declared_absent)) - set(KNOWN_REGIME_KEYS))
    if unknown:
        raise ScorecardError(
            f"{cov_where}: unknown regime key(s) {unknown}; the declared set is {list(KNOWN_REGIME_KEYS)}"
        )
    computed_present, computed_absent = regimes_covered_by(window_start, window_end)
    if sorted(declared_present) != sorted(computed_present) or sorted(declared_absent) != sorted(
        computed_absent
    ):
        raise ScorecardError(
            f"{cov_where}: declared coverage disagrees with the declared window. "
            f"{window_start}..{window_end} covers {computed_present} and misses {computed_absent}; "
            f"the scorecard says {sorted(declared_present)} / {sorted(declared_absent)}. "
            "Regime coverage is COMPUTED from the window, never asserted."
        )
    coverage = RegimeCoverage(
        window_start=window_start,
        window_end=window_end,
        regimes_present=tuple(computed_present),
        regimes_absent=tuple(computed_absent),
        statement=_require_text(cov_raw, "statement", cov_where),
    )
    return Layer4Economics(
        cost_scenarios=tuple(scenarios), capacity=capacity, regime_coverage=coverage
    )


def parse_scorecard(payload: dict[str, Any], *, source_path: Path | None = None) -> RegistrationScorecard:
    where = str(source_path) if source_path is not None else "<scorecard>"
    schema = payload.get("schema")
    if schema != SCHEMA:
        raise ScorecardError(
            f"{where}: declares schema {schema!r}, this module reads {SCHEMA!r}. "
            "Refusing to guess at a layout change."
        )
    family_key = _require_text(payload, "family_key", where)
    # THE TWO FAMILY-KEY NAMESPACES, and why one scorecard may cover several
    # keys. cross_sectional_trial_results and
    # cross_sectional_forward_validation_registrations do NOT share a
    # vocabulary: the screening family "lazy_prices" is registered forward
    # under "lazy_prices_jaccard_full", "short_interest" under
    # "short_interest_ratio", and "crypto" under "cross_sectional_crypto".
    # Those are the same research object viewed through two tables, so
    # demanding a separate scorecard for each key would manufacture duplicates
    # rather than coverage. covers_family_keys is the explicit, checked list of
    # every key this one scorecard answers for — required, never inferred, so a
    # key can never be quietly absorbed into a neighbouring family's card.
    covers = _require_list(payload, "covers_family_keys", where)
    for i, key in enumerate(covers):
        if not isinstance(key, str) or not key.strip():
            raise ScorecardError(f"{where}.covers_family_keys[{i}]: expected a non-empty string")
    if family_key not in covers:
        raise ScorecardError(
            f"{where}.covers_family_keys must include the scorecard's own family_key "
            f"{family_key!r}; got {covers}"
        )
    return RegistrationScorecard(
        family_key=family_key,
        covers_family_keys=tuple(covers),
        pattern_id=_require_text(payload, "pattern_id", where),
        written_at=_require_date(payload, "written_at", where),
        author=_require_text(payload, "author", where),
        decision=_require_text(payload, "decision", where),
        decision_rationale=_require_text(payload, "decision_rationale", where),
        preregistration_path=_require_text(payload, "preregistration_path", where),
        layer_1=_parse_layer_1(_require_dict(payload, "layer_1_statistical", where), f"{where}.layer_1_statistical"),
        layer_2=_parse_layer_2(
            _require_dict(payload, "layer_2_mechanism_fidelity", where),
            f"{where}.layer_2_mechanism_fidelity",
        ),
        layer_3=_parse_layer_3(
            _require_dict(payload, "layer_3_regime_conditional", where),
            f"{where}.layer_3_regime_conditional",
        ),
        layer_4=_parse_layer_4(
            _require_dict(payload, "layer_4_economics", where), f"{where}.layer_4_economics"
        ),
        source_path=source_path or Path(),
    )


def scorecard_path_for(family_key: str, *, directory: Path | None = None) -> Path:
    return (directory or SCORECARD_DIR) / f"{family_key}{SCORECARD_SUFFIX}"


def load_scorecard(family_key: str, *, directory: Path | None = None) -> RegistrationScorecard:
    path = scorecard_path_for(family_key, directory=directory)
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ScorecardError(
            f"no scorecard for family {family_key!r} at {path}. Fill in "
            f"{TEMPLATE_PATH.name} and commit it; see registration_scorecard.py's docstring."
        ) from exc
    except ValueError as exc:
        raise ScorecardError(f"{path} is not readable JSON: {exc}") from exc
    card = parse_scorecard(payload, source_path=path)
    if card.family_key != family_key:
        raise ScorecardError(
            f"{path} declares family_key {card.family_key!r} but is filed under {family_key!r}"
        )
    return card


def existing_scorecard_family_keys(*, directory: Path | None = None) -> set[str]:
    """Family keys with a scorecard FILE present. Says nothing about whether
    the file parses — that is load_scorecard's job, and the two are kept
    separate so a completeness report can distinguish "missing" from
    "present but broken"."""
    root = directory or SCORECARD_DIR
    if not root.is_dir():
        return set()
    return {p.name[: -len(SCORECARD_SUFFIX)] for p in root.glob(f"*{SCORECARD_SUFFIX}")}


def load_all_scorecards(*, directory: Path | None = None) -> list[RegistrationScorecard]:
    """Every scorecard on disk, parsed. Raises on the FIRST unparseable one:
    a governance directory that half-loads is worse than one that refuses."""
    return [
        load_scorecard(key, directory=directory)
        for key in sorted(existing_scorecard_family_keys(directory=directory))
    ]


def covered_family_keys(*, directory: Path | None = None) -> set[str]:
    """Every family key answered for by some scorecard — the union of each
    card's covers_family_keys, not just the filenames."""
    covered: set[str] = set()
    for card in load_all_scorecards(directory=directory):
        covered.update(card.covers_family_keys)
    return covered


# ---------------------------------------------------------------------------
# What the scorecard set is measured AGAINST
# ---------------------------------------------------------------------------

# The live/forward-tracked registrations, read from the registration modules
# app/main.py's lifespan actually awaits — not a hand-kept list. If a sixth
# registration is wired into main.py and not added here, the pairing test in
# tests/test_registration_scorecards.py fails, which is the point.
LIVE_REGISTRATION_MODULES = (
    "app.services.research_lab.quality_forward_registration",
    "app.services.research_lab.short_interest_forward_registration",
    "app.services.research_lab.lazy_prices_forward_registration",
    "app.services.research_lab.bab_forward_registration",
)


def live_registration_family_keys() -> dict[str, str]:
    """{family_key: pattern_id} for every registration app/main.py opens at
    startup, resolved by importing the modules' own constants rather than
    copying their values. Includes quality_noa_industry_neutral, which
    main.py's lifespan creates and then RETIRES in the same process start
    (see quality_forward_registration §I): a retired registration still has a
    decision behind it and still needs the record of what that decision was
    made on."""
    from app.services.research_lab.bab_forward_registration import (
        BAB_FAMILY_KEY,
        BAB_PATTERN_ID,
    )
    from app.services.research_lab.cross_sectional_forward_registry import (
        LAZY_PRICES_JACCARD_FULL_FAMILY_KEY,
        QUALITY_CBOP_FAMILY_KEY,
        QUALITY_NOA_NEUTRAL_FAMILY_KEY,
        SHORT_INTEREST_RATIO_FAMILY_KEY,
    )
    from app.services.research_lab.lazy_prices_forward_registration import (
        LAZY_PRICES_PATTERN_ID,
    )
    from app.services.research_lab.quality_forward_registration import (
        CBOP_PATTERN_ID,
        NOA_NEUTRAL_PATTERN_ID,
    )
    from app.services.research_lab.short_interest_forward_registration import (
        SHORT_INTEREST_PATTERN_ID,
    )

    return {
        QUALITY_CBOP_FAMILY_KEY: CBOP_PATTERN_ID,
        QUALITY_NOA_NEUTRAL_FAMILY_KEY: NOA_NEUTRAL_PATTERN_ID,
        SHORT_INTEREST_RATIO_FAMILY_KEY: SHORT_INTEREST_PATTERN_ID,
        LAZY_PRICES_JACCARD_FULL_FAMILY_KEY: LAZY_PRICES_PATTERN_ID,
        BAB_FAMILY_KEY: BAB_PATTERN_ID,
    }


# A committed snapshot of the family keys in cross_sectional_trial_results.
# WHY A SNAPSHOT AT ALL, given the table is the real source: aladdin2.db is
# gitignored, so it exists on the repo owner's machine and in production and
# NOWHERE ELSE — not in a worktree, not in CI, not on a fresh clone. A
# completeness test that silently skipped whenever the DB was absent would
# pass everywhere it was actually run by an agent. The snapshot makes the
# requirement travel with the repo; the DB, when present, is checked AGAINST
# the snapshot so it cannot go stale unnoticed.
FAMILY_INVENTORY_PATH = SCORECARD_DIR / "FAMILY_INVENTORY.json"
FAMILY_INVENTORY_SCHEMA = "scorecard_family_inventory/v1"


@dataclass(frozen=True)
class FamilyInventory:
    schema: str
    captured_at: str
    source_query: str
    database: str
    family_keys: tuple[str, ...]
    note: str


def load_family_inventory(path: Path | None = None) -> FamilyInventory:
    target = path or FAMILY_INVENTORY_PATH
    try:
        payload = json.loads(target.read_text())
    except FileNotFoundError as exc:
        raise ScorecardError(
            f"{target} is missing. It is a TRACKED governance artifact, not a cache — "
            "regenerate it with data/research_runs/refresh_family_inventory.py and commit it."
        ) from exc
    if payload.get("schema") != FAMILY_INVENTORY_SCHEMA:
        raise ScorecardError(
            f"{target} declares schema {payload.get('schema')!r}, expected "
            f"{FAMILY_INVENTORY_SCHEMA!r}"
        )
    keys = payload.get("family_keys")
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys):
        raise ScorecardError(f"{target}.family_keys must be a non-empty list of strings")
    return FamilyInventory(
        schema=str(payload["schema"]),
        captured_at=str(payload.get("captured_at", "unknown")),
        source_query=str(payload.get("source_query", "")),
        database=str(payload.get("database", "")),
        family_keys=tuple(keys),
        note=str(payload.get("note", "")),
    )


def required_pooled_denominators() -> tuple[int, ...]:
    """(481, 857) — read from global_effective_n.json, never retyped.

    Imported lazily so that this module stays importable (and the template
    stays readable) on a checkout whose global_effective_n.json is being
    regenerated."""
    from app.services.research_lab.global_effective_n import load_global_effective_n

    artifact = load_global_effective_n()
    return (artifact.n_specs_clustered, artifact.raw_pooled_distinct_trials)
