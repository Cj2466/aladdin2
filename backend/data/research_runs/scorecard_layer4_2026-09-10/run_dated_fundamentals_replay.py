"""Is the quality_cbop backward drift found on 2026-09-10 explained by the
companyfacts documents having changed since the canonical run?

    set -a; . ./.env; set +a
    ./venv/bin/python data/research_runs/scorecard_layer4_2026-09-10/run_dated_fundamentals_replay.py

THE SYMPTOM. Re-screening the quality family today with the canonical config
(run_tag scorecard_cost_scenarios_2026-09-10_quality_cbop_baseline_5bp) does
NOT reproduce run_tag quality_build_2026-08-28: the registered cbop_ls_h63
moves only -0.0027 Sharpe, but cbop_ls_h126 moves -0.0633, cbop_ls_h252
-0.0754 and the quintile variants up to -0.0900. The 2026-09-04 rerun
(global_effective_n_2026-09-04) still matched the canonical to 3e-4, so the
inputs moved between 2026-09-04 and today.

WHAT IS ALREADY EXCLUDED. The seeded 200-ticker sample is identical (the
768-name union is unchanged, and the sample is a fixed-seed draw from it).
The APH/MNST share-basis repair of 2026-09-09 cannot be the cause: the
canonical run predates the price store and used correct prices, and so does
the repaired store.

THE SUSPECT. 165 of the 166 cached companyfacts documents were refetched
2026-09-09 23:45 during the fact-store ingestion. A newer document can change
a firm-year value only through facts filed since the old version, or through
the provider's cross-filing scale-conflict guard dropping a period it did not
drop before.

THE TEST. The fact store keeps SEC's own `filed` date per fact, so a document
can be rebuilt AS SEC SHOWED IT on any date. Two arms, everything else today's:
  as_of 2026-09-10 — must reproduce today's baseline exactly, proving the
                     rebuilt document shape is neutral (else arm 2 is moot);
  as_of 2026-08-28 — fundamentals as filed by the canonical run's date. If
                     this reproduces quality_build_2026-08-28, the drift is
                     new filings and is explained; if not, the cause is
                     elsewhere (price path) and this test says so.
Rows are persisted under their own run_tags; nothing canonical is touched and
no live registration is read or written.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.db import SessionLocal
from app.models.cross_sectional_trial_result import (
    CrossSectionalTrialResult,
)
from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.cross_sectional_quality import (
    run_quality_screening,
)

HERE = Path(__file__).resolve().parent
STAMP = "2026-09-10"
QUALITY_END = date(2026, 8, 28)
CANONICAL = "quality_build_2026-08-28"
BASELINE = f"scorecard_cost_scenarios_{STAMP}_quality_cbop_baseline_5bp"


class DatedEdgarProvider(EdgarXbrlProvider):
    """Every companyfacts read — direct or through successor-shell
    resolution — served as the document stood on `as_of`, from the fact
    store's own filed dates. Nothing else about the provider changes."""

    def __init__(self, as_of: date, **kwargs):
        super().__init__(**kwargs)
        self.as_of = as_of

    def get_company_facts(self, cik: int) -> dict:  # type: ignore[override]
        document = self.facts_store.document_as_of(cik, as_of=self.as_of)
        if document is None:
            raise RuntimeError(f"fact store holds nothing for CIK {cik} as of {self.as_of}")
        return document


def _grid(db, run_tag: str) -> dict[str, float]:
    rows = (
        db.query(CrossSectionalTrialResult.trial_id, CrossSectionalTrialResult.sharpe_annualized)
        .filter(
            CrossSectionalTrialResult.family_key == "quality_cbop",
            CrossSectionalTrialResult.run_tag == run_tag,
        )
        .all()
    )
    return {tid: float(sh) for tid, sh in rows}


def main() -> int:
    now = datetime.now(UTC)
    out: dict = {"run_at": now.isoformat(timespec="minutes"), "arms": {}}
    with SessionLocal() as db:
        reference = {"canonical": _grid(db, CANONICAL), "today_baseline": _grid(db, BASELINE)}
    for label, as_of in (("asof_2026-09-10", date(2026, 9, 10)), ("asof_2026-08-28", date(2026, 8, 28))):
        run_tag = f"scorecard_cost_scenarios_{STAMP}_quality_cbop_fundamentals_{label}"
        print(f"\n=== fundamentals {label}  run_tag={run_tag}", flush=True)
        summary = run_quality_screening(end=QUALITY_END, edgar=DatedEdgarProvider(as_of))
        results = list(summary.cbop_results)
        with SessionLocal() as db:
            db.query(CrossSectionalTrialResult).filter(
                CrossSectionalTrialResult.family_key == "quality_cbop",
                CrossSectionalTrialResult.run_tag == run_tag,
            ).delete(synchronize_session=False)
            db.commit()
            n = persist_cross_sectional_trial_results(db, "quality_cbop", results, run_tag=run_tag)
        grid = {r.pattern_id: float(r.sharpe_annualized) for r in results}
        cmp = {}
        for ref_name, ref in reference.items():
            deltas = {tid: grid[tid] - ref[tid] for tid in grid if tid in ref}
            cmp[ref_name] = {"max_abs_delta": max(abs(v) for v in deltas.values()), "deltas": deltas}
            print(f"   vs {ref_name:14s}: max |delta Sharpe| {cmp[ref_name]['max_abs_delta']:.6f}", flush=True)
        out["arms"][label] = {"run_tag": run_tag, "rows_persisted": n, "grid": grid, "comparison": cmp}
        (HERE / f"dated_fundamentals_replay_{STAMP}.json").write_text(
            json.dumps(out, indent=2, sort_keys=True) + "\n"
        )
    print("\nwritten dated_fundamentals_replay JSON")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
