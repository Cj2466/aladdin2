"""The second half of the quality_cbop drift: what on the PRICE side moved
between the canonical run and today?

    set -a; . ./.env; set +a
    ./venv/bin/python data/research_runs/scorecard_layer4_2026-09-10/run_price_path_replay.py

CONTEXT. run_dated_fundamentals_replay.py showed that rolling the
companyfacts documents back to 2026-08-28 recovers the long-hold specs
(cbop_ls_h252 back to the canonical exactly) but leaves the three hedged
specs -0.027 / -0.040 off the canonical in BOTH dated arms, and moves
cbop_ls_h63 -0.017. That residual is fundamentals-independent. The
APH/MNST/RUSHA repair is excluded (their adjusted series carry no fabricated
day). Two candidates remain, each answerable by one replay on the SAME
08-28-dated fundamentals:

  yahoo_convention — the shared price store, but the adjustment convention
                     the canonical run used (AdjustmentConvention.YAHOO,
                     default until 2026-09-04; quality_forward_registration
                     section J measured the switch only on cbop_ls_h63).
                     If this reproduces the canonical, the residual is the
                     documented convention change and nothing is wrong.
  fresh_vendor     — a THROW-AWAY price store populated from the vendor
                     today, CRSP convention. If this matches the shared-store
                     arm, the store equals the vendor and any remaining gap
                     to the canonical is vendor revision since 08-28 (which
                     the store exists to freeze going forward and cannot undo
                     backward). If it differs from the shared store, the
                     store itself is off.

Every arm persists its rows under its own run_tag. Nothing canonical is
touched; no live registration is read or written. The throw-away store lives
under this directory and is deleted at the end.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.db import SessionLocal
from app.models.cross_sectional_trial_result import (
    CrossSectionalTrialResult,
)
from app.services.market_data.price_store import AdjustmentConvention, PriceStore
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.cross_sectional_quality import (
    run_quality_screening,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_dated_fundamentals_replay import (
    BASELINE,
    CANONICAL,
    DatedEdgarProvider,
    _grid,
)

HERE = Path(__file__).resolve().parent
STAMP = "2026-09-10"
QUALITY_END = date(2026, 8, 28)
AS_OF = date(2026, 8, 28)
DATED_STORE_ARM = f"scorecard_cost_scenarios_{STAMP}_quality_cbop_fundamentals_asof_2026-08-28"


def main() -> int:
    now = datetime.now(UTC)
    out: dict = {"run_at": now.isoformat(timespec="minutes"), "arms": {}}
    with SessionLocal() as db:
        reference = {
            "canonical": _grid(db, CANONICAL),
            "today_baseline": _grid(db, BASELINE),
            "asof_0828_shared_store_crsp": _grid(db, DATED_STORE_ARM),
        }
    tmp = Path(tempfile.mkdtemp(prefix="throwaway_price_store_", dir=HERE))
    arms = (
        ("yahoo_convention", lambda: YFinanceProvider(adjustment=AdjustmentConvention.YAHOO)),
        ("fresh_vendor", lambda: YFinanceProvider(price_store=PriceStore(tmp))),
    )
    try:
        for label, make_provider in arms:
            run_tag = f"scorecard_cost_scenarios_{STAMP}_quality_cbop_price_{label}"
            print(f"\n=== price path {label}  run_tag={run_tag}", flush=True)
            summary = run_quality_screening(
                end=QUALITY_END, provider=make_provider(), edgar=DatedEdgarProvider(AS_OF)
            )
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
                print(f"   vs {ref_name:28s}: max |delta Sharpe| {cmp[ref_name]['max_abs_delta']:.6f}", flush=True)
            out["arms"][label] = {"run_tag": run_tag, "rows_persisted": n, "grid": grid, "comparison": cmp}
            (HERE / f"price_path_replay_{STAMP}.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nwritten price_path_replay JSON")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
