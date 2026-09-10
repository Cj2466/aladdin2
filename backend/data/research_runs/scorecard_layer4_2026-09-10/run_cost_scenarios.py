"""Cost-scenario arms for the two live registrations whose only persisted
run is the as-built cost basis: quality_cbop / cbop_ls_h63 and
cross_sectional_crypto / xc_btcbeta_l180_h180.

    set -a; . ./.env; set +a
    ./venv/bin/python data/research_runs/scorecard_layer4_2026-09-10/run_cost_scenarios.py

WHY. Layer 4 of the registration scorecard requires at least two cost
scenarios, each with the registered spec's MEASURED net Sharpe — a range, not
an assumption. lazy_prices already carries a nine-run cost ladder in
cross_sectional_trial_results (edge_cost_correction_2026-09-05_* and
cost_basis_switch_2026-09-05_*), and short_interest carries a measured
financing ladder in short_interest_borrow_composition_2026-09-05.txt. The
other two live families have exactly one persisted cost basis each, so their
range has to be measured here.

WHAT THIS DOES. Re-screens each family's WHOLE pre-declared grid — never the
registered spec alone, so the DSR denominator and sigma_SR are the family's
own — with ONE config field changed per arm, and persists every arm's rows
under its own run_tag so the numbers are auditable in the same table as the
originals. The registered spec's Sharpe / DSR per arm is also written to a
JSON beside this script. The canonical rows are not touched.

ARMS (each a labelled scenario, not a prediction):
  quality_cbop
    trading  2 bp  — the corrected EDGE large-cap median one-way half-spread
                     (edge_cost_correction_2026-09-05); the optimistic bound
    trading 10 bp  — 2x the as-run flat 5 bp; stress
    financing 17 bp/yr on gross (5 bp trading) — the general-collateral bracket
                     borrow_cost offers (34 bp/yr on the short leg); NOT a
                     measurement for this book — cbop's short leg was never
                     measured the way short_interest's and lazy_prices' were
  cross_sectional_crypto
    trading 15 bp  — half the as-run blended 30 bp assumption
    trading 60 bp  — double it; stress for the thinner alts
    financing 0    — what the as-run 800 bp/yr spot borrow is worth; NOT the
                     perpetual-funding credit the module refuses to book

Read-only with respect to every live registration; writes only trial rows
(CLAUDE.md rule 6 is untouched). Idempotent per run_tag, as the reference
run_global_effective_n.py is.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.db import SessionLocal
from app.models.cross_sectional_trial_result import (
    CrossSectionalTrialResult,
)
from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.research_lab.cross_sectional_crypto import (
    default_crypto_config,
    run_crypto_screening,
)
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.cross_sectional_quality import (
    default_quality_config,
    run_quality_screening,
)

HERE = Path(__file__).resolve().parent
STAMP = "2026-09-10"

# (family_key for the rows, registered spec, arm label, config overrides, runner)
ARMS = [
    # Same-day baselines: every arm must be read against a baseline built on
    # the SAME inputs the arms saw, not against a canonical run whose inputs
    # may since have drifted (found 2026-09-10: they had).
    ("quality_cbop", "cbop_ls_h63", "baseline_5bp", {}),
    ("crypto", "xc_btcbeta_l180_h180", "baseline_30bp", {}),
    ("quality_cbop", "cbop_ls_h63", "trading_2bp", {"cost_bps": 2.0}),
    ("quality_cbop", "cbop_ls_h63", "trading_10bp", {"cost_bps": 10.0}),
    ("quality_cbop", "cbop_ls_h63", "financing_gc_17bp", {"financing_bps_per_year": 17.0}),
    ("crypto", "xc_btcbeta_l180_h180", "trading_15bp", {"cost_bps": 15.0}),
    ("crypto", "xc_btcbeta_l180_h180", "trading_60bp", {"cost_bps": 60.0}),
    ("crypto", "xc_btcbeta_l180_h180", "financing_0", {"financing_bps_per_year": 0.0}),
]

# The canonical runs' end dates, so every arm replays the SAME window.
QUALITY_END = date(2026, 8, 28)
CRYPTO_END = date(2026, 8, 31)


def _run(family_key: str, overrides: dict) -> list:
    if family_key == "quality_cbop":
        config = replace(default_quality_config(), **overrides)
        summary = run_quality_screening(end=QUALITY_END, edgar=EdgarXbrlProvider(), config=config)
        return list(summary.cbop_results)
    config = replace(default_crypto_config(), **overrides)
    return list(run_crypto_screening(end=CRYPTO_END, config=config).results)


def main() -> int:
    now = datetime.now(UTC)
    path = HERE / f"cost_scenarios_{STAMP}.json"
    # Optional argv: arm labels to run; earlier arms' entries are kept.
    wanted = set(sys.argv[1:])
    out: dict = json.loads(path.read_text()) if path.exists() else {"arms": []}
    out["run_at"] = now.isoformat(timespec="minutes")
    out["arms"] = [e for e in out["arms"] if not wanted or e["arm"] not in wanted]
    for family_key, spec, arm, overrides in ARMS:
        if wanted and arm not in wanted:
            continue
        run_tag = f"scorecard_cost_scenarios_{STAMP}_{family_key}_{arm}"
        print(f"\n=== {family_key} / {arm}  overrides={overrides}  run_tag={run_tag}", flush=True)
        results = _run(family_key, overrides)
        hit = [r for r in results if r.pattern_id == spec]
        if len(hit) != 1:
            print(f"   registered spec {spec} not found exactly once in {len(results)} results", flush=True)
            return 1
        r = hit[0]
        with SessionLocal() as db:
            deleted = (
                db.query(CrossSectionalTrialResult)
                .filter(
                    CrossSectionalTrialResult.family_key == family_key,
                    CrossSectionalTrialResult.run_tag == run_tag,
                )
                .delete(synchronize_session=False)
            )
            db.commit()
            if deleted:
                print(f"   (replaced {deleted} row(s) from an earlier attempt)", flush=True)
            n = persist_cross_sectional_trial_results(db, family_key, results, run_tag=run_tag)
        entry = {
            "family_key": family_key,
            "pattern_id": spec,
            "arm": arm,
            "overrides": overrides,
            "run_tag": run_tag,
            "rows_persisted": n,
            "sharpe_annualized": float(r.sharpe_annualized),
            "dsr": float(r.deflated_sharpe.dsr),
            "total_cost_drag": float(r.total_cost_drag),
            "total_financing_drag": float(getattr(r, "total_financing_drag", 0.0)),
            "n_trading_days": int(r.n_trading_days),
            "n_formations": int(r.n_formations),
            "avg_names_per_leg": float(r.avg_names_per_leg),
        }
        out["arms"].append(entry)
        print(
            f"   {spec}: sharpe {entry['sharpe_annualized']:+.4f}  dsr {entry['dsr']:.4f}  "
            f"cost_drag {entry['total_cost_drag']:.4f}  fin_drag {entry['total_financing_drag']:.4f}  "
            f"({n} rows persisted)",
            flush=True,
        )
        path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"\nwritten {path.relative_to(_BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
