"""preservation_score for the crypto family — the one live registration the
2026-09-03 preservation run predates and does not cover.

    set -a; . ./.env; set +a
    ./venv/bin/python data/research_runs/scorecard_layer4_2026-09-10/run_crypto_preservation_score.py

CLAUDE.md requires preservation_score for every family with no exceptions,
and the scorecard validator refuses a card without it. The score needs the
spec's realized daily net-return series, which is not persisted, so the
family's own production entry point is replayed with the SAME capture hook
data/research_runs/run_preservation_score.py uses (imported from it, not
re-implemented), and every spec is scored on the family's own 365-day
calendar. The rebuilt Sharpe is checked against the persisted canonical row
(global_effective_n_2026-09-04) per spec and reported either way.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "data" / "research_runs"))

import run_preservation_score as runner

from app.services.research_lab.cross_sectional_crypto import (
    CRYPTO_PERIODS_PER_YEAR,
    run_crypto_screening,
)
from app.services.research_lab.preservation_score import (
    compute_preservation_metrics,
)

HERE = Path(__file__).resolve().parent
STAMP = "2026-09-10"
CANONICAL_RUN_TAG = "global_effective_n_2026-09-04"
REGISTERED = "xc_btcbeta_l180_h180"


def main() -> int:
    now = datetime.now(UTC)
    persisted = runner.load_persisted()
    runner.CAPTURED.clear()
    results = list(run_crypto_screening(end=date(2026, 8, 31)).results)
    specs = []
    for res in results:
        cap = runner.CAPTURED.get(res.pattern_id)
        if cap is None:
            continue
        m = compute_preservation_metrics(
            cap["returns"], dsr=res.deflated_sharpe.dsr, periods_per_year=float(CRYPTO_PERIODS_PER_YEAR)
        )
        prow = persisted.get((CANONICAL_RUN_TAG, res.pattern_id), {})
        d = m.as_dict()
        d.update(
            {
                "pattern_id": res.pattern_id,
                "rerun_dsr": res.deflated_sharpe.dsr,
                "rerun_n_trials": res.deflated_sharpe.n_trials,
                "persisted_sharpe": prow.get("persisted_sharpe"),
                "persisted_dsr": prow.get("persisted_dsr"),
                "sharpe_delta_vs_persisted": (
                    None if prow.get("persisted_sharpe") is None else m.sharpe_full - prow["persisted_sharpe"]
                ),
            }
        )
        specs.append(d)
    reg = [s for s in specs if s["pattern_id"] == REGISTERED]
    payload = {
        "run_at": now.isoformat(timespec="minutes"),
        "family_key": "crypto",
        "covers": ["crypto", "cross_sectional_crypto"],
        "canonical_run_tag": CANONICAL_RUN_TAG,
        "periods_per_year": float(CRYPTO_PERIODS_PER_YEAR),
        "n_specs_scored": len(specs),
        "registered_spec": reg[0] if reg else None,
        "specs": specs,
    }
    out = HERE / f"preservation_score_crypto_{STAMP}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=float) + "\n")
    if reg:
        r = reg[0]
        keys = [k for k in r if "preservation" in k or k in ("sharpe_full", "sharpe_delta_vs_persisted", "rerun_dsr")]
        print(f"{REGISTERED}: " + "  ".join(f"{k}={r[k]}" for k in keys))
    print(f"scored {len(specs)} specs; written {out.relative_to(_BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
