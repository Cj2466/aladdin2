"""Single-command Databento pull for the two gaps the free sources
(CME SPAN archive, EIA) cannot close: KC/SB/CT (ICE, IFUS.IMPACT -- CME SPAN
never covered ICE-listed products at all) and the 2025-09-13-to-present
bridge window for the 31 CME/CBOT/NYMEX/COMEX roots (CME SPAN's public FTP
archive covers 2013-01-02..2025-09-12 for free; this script deliberately
does NOT re-pull that free range -- see app/services/market_data/
databento_futures.py's build_plans()). Built 2026-09-07 for the phase-2
futures-data-sourcing task.

NOT RUN in this session: this project has no Databento account and creating
one (spending its free credit) is the project owner's decision -- see the
"DATABENTO SIGN-UP" section of
backend/data/research_runs/futures_data_sourcing_phase2_2026-09-07.txt.
This script is written so that once DATABENTO_API_KEY is set (in the
environment or backend/.env) and `pip install -e ".[databento]"` has been
run, a single call does everything:

    cd backend
    python data/research_runs/fetch_databento_bridge_and_ice.py

Steps, in order:
  1. Refuse to run if DATABENTO_API_KEY is unset (raises before any
     network I/O -- see databento_futures.make_client()).
  2. Build the two request plans (build_plans()) for GLBX.MDP3 (bridge
     window only) and IFUS.IMPACT (full history).
  3. Call estimate_cost() first -- Databento's own metadata.get_cost /
     get_billable_size / list_unit_prices endpoints -- and print+log the
     real dollar figure before pulling anything, so a surprise is caught
     before it is spent, not after.
  4. Pull ohlcv-1d for both plans via timeseries.get_range (pull_ohlcv_1d()),
     write one CSV per Globex/ICE root under
     data/futures_daily/databento/<dataset>/<ROOT>.csv, and write a
     manifest.json (mirroring fetch_cme_span_archive.py's shape) so the
     result is a persisted file, not just a scratch note.

Every request shape (dataset codes, symbol format, schema, stype_in) is
documented and cited in databento_futures.py's module docstring; the
request-shaping and response-parsing logic is exercised end-to-end (no
network, no key) by tests/test_databento_futures.py's FakeClient tests.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}")

from app.services.market_data import databento_futures as db

STORE = _BACKEND / "data" / "futures_daily" / "databento"


def main() -> None:
    # Fails fast, before any network call, if DATABENTO_API_KEY is unset --
    # see databento_futures.make_client(). No account/API-call attempt is
    # made by writing or importing this script.
    client = db.make_client()

    end = datetime.now(UTC).date()
    plans = db.build_plans(end)
    STORE.mkdir(parents=True, exist_ok=True)

    print("Requesting Databento's own cost estimate before pulling anything...", flush=True)
    estimates = db.estimate_cost(client, plans)
    for e in estimates:
        print(
            f"  {e['dataset']}: {e['start']}..{e['end']} schema={e['schema']} "
            f"cost_usd={e['cost_usd']:.4f} billable_bytes={e['billable_bytes']}",
            flush=True,
        )
    total_cost = sum(e["cost_usd"] for e in estimates)
    if total_cost > 5.0:
        raise SystemExit(
            f"REFUSING TO PULL: Databento's own cost estimate is ${total_cost:.2f}, "
            "more than 5x the ~$1 order-of-magnitude this plan was scoped for "
            "(see databento_futures.py's SIZE ESTIMATE section) -- stop and "
            "have a human look before spending the free credit."
        )

    results = []
    for plan in plans:
        print(f"Pulling {plan.dataset} {plan.start}..{plan.end} ...", flush=True)
        result = db.pull_ohlcv_1d(client, plan, STORE)
        print(f"  wrote {result['rows']} rows across {len(result['per_root'])} roots", flush=True)
        results.append(result)

    manifest = {
        "source": "Databento historical ohlcv-1d",
        "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "plans": [p.as_kwargs() for p in plans],
        "cost_estimates_usd": [e["cost_usd"] for e in estimates],
        "results": results,
        "note": (
            "GLBX.MDP3 covers only the 2025-09-13-to-present bridge window "
            "(everything from 2013-01-02..2025-09-12 is free via CME SPAN, see "
            "cme_span_settlements.py); IFUS.IMPACT covers full available "
            "history (2018-12-23-to-present) since CME SPAN never had ICE data."
        ),
    }
    (STORE / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
