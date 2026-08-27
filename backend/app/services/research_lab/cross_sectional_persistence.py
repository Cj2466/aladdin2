import json
from dataclasses import asdict
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.models.cross_sectional_trial_result import CrossSectionalTrialResult

# The generic writer for EVERY cross-sectional/timing family's per-spec
# screening output, closing a gap found and fixed 2026-08-27: every family
# built so far (Commodities, Buyback, Bonds, FX, IVOL, D1, D2, Round C,
# Crypto, Vol-Regime, Index-removal, Small/mid-cap, Correlation Risk
# Premium) computed real results with nowhere durable to persist them —
# every number only ever existed as ad-hoc script output in a temp
# scratchpad, which directly caused two real incidents the same day this
# was built: a local DB wipe silently destroyed 249 real rows, and a
# synthetic RNG test fixture got mistaken for real archived results by a
# later analysis, producing a fabricated "finding" that only fell apart
# under adversarial re-verification.
#
# Deliberately generic rather than one function per family: every family's
# per-spec result dataclass, however different its own fields are, carries
# the same four things this table actually needs to be useful for future
# analysis (empirical-Bayes shrinkage, effective-N clustering, or just "did
# this number get computed before") — a trial identifier (spec_id in the
# newer timing-style modules, pattern_id in the cross_sectional.py-based
# ones), sharpe_annualized, n_trading_days, and a deflated_sharpe object.
# Extracted via getattr rather than a shared base class, since retrofitting
# ~12 existing, independently-tested result dataclasses onto one base class
# is a much bigger, riskier change than this gap justifies — the two field
# names in practice are a closed set, checked explicitly below rather than
# silently returning None for a typo'd or genuinely new third name.
#
# NOT wired into any of the run_*_screening entrypoints as a default side
# effect: none of those functions currently has a `db: Session` parameter,
# none of them is called from a live/automated runner today (every family
# so far has only ever been invoked from an ad-hoc script), and threading a
# database dependency into ~12 independently-tested, working functions is a
# larger, separate change than closing "there is nowhere to persist to."
# The pattern going forward: run_x_screening(...) to get a summary, then
# persist_cross_sectional_trial_results(db, "x", summary.results, run_tag=...)
# — two calls, not a hidden side effect inside the first one.


def persist_cross_sectional_trial_results(
    db: Session,
    family_key: str,
    results: Sequence[Any],
    run_tag: str,
) -> int:
    """Writes one CrossSectionalTrialResult row per element of `results`.
    Commits and returns the row count.

    `run_tag` is mandatory and free-text on purpose — there is no default,
    so every call site has to consciously choose a label rather than
    accepting a generic one that would make a real production run
    indistinguishable from a one-off dev/test invocation at read time. Use
    something that says what this run actually was, e.g.
    "production_2026-08-27" or "adhoc_recheck_after_d1_fix" — not "run" or
    "test".

    Raises ValueError on the first result missing a required field, rather
    than silently skipping it — a family module with a genuinely new
    result shape needs this function taught about it explicitly, not a
    partial, silently-incomplete write that looks complete."""
    if not run_tag or not run_tag.strip():
        raise ValueError("run_tag is mandatory and must be non-empty — see module docstring")
    if not results:
        raise ValueError(
            f"persist_cross_sectional_trial_results called with zero results for "
            f"family_key={family_key!r} — if this family genuinely produced no "
            "replayable specs this run, that is itself worth a row or a log line "
            "at the call site, not a silent no-op here."
        )

    rows = []
    for r in results:
        trial_id = getattr(r, "spec_id", None)
        if trial_id is None:
            trial_id = getattr(r, "pattern_id", None)
        if trial_id is None:
            raise ValueError(
                f"result {r!r} has neither .spec_id nor .pattern_id — this function "
                "only knows those two trial-identifier field names; teach it the "
                "new one explicitly rather than guessing."
            )

        deflated = getattr(r, "deflated_sharpe", None)
        if deflated is None:
            raise ValueError(f"result {r!r} (trial_id={trial_id}) has no .deflated_sharpe")

        n_observations = getattr(r, "n_trading_days", None)
        if n_observations is None:
            raise ValueError(f"result {r!r} (trial_id={trial_id}) has no .n_trading_days")

        rows.append(
            CrossSectionalTrialResult(
                family_key=family_key,
                trial_id=str(trial_id),
                run_tag=run_tag,
                sharpe_annualized=float(r.sharpe_annualized),
                n_observations=int(n_observations),
                n_trials=int(deflated.n_trials),
                dsr=deflated.dsr,
                psr_vs_zero=deflated.psr_vs_zero,
                full_result_json=json.dumps(asdict(r), default=str),
            )
        )

    db.add_all(rows)
    db.commit()
    return len(rows)
