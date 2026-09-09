"""Run from the MAIN checkout (its data/ holds the EDGAR/FINRA caches the panels read), after reset_live_registrations.py:
    set -a; . ./.env; set +a; ./venv/bin/python data/research_runs/live_panel_coverage_2026-09-10/tick_live_registrations.py

One catch-up tick for registrations 2, 4, 5 ONLY (the crypto registration
is deliberately not touched), using the runner's own _process_family exactly
as a running server would. Records store-file mtimes before/after to prove
the tick made no vendor fetch."""
import glob
import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))
from sqlalchemy import select
from app.db import SessionLocal, engine
from app.models.cross_sectional_forward_validation import CrossSectionalForwardValidationRegistration as R
from app.services.research_lab.cross_sectional_forward_validation_runner import CrossSectionalForwardValidationRunner
from app.services.market_data.price_store import PriceStore
import logging; logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
store = PriceStore(); print("db:", engine.url, "| store:", store.store_dir)
def snapshot():
    return {f: os.path.getmtime(f) for f in glob.glob(str(store.store_dir / "*"))}
before = snapshot()
runner = CrossSectionalForwardValidationRunner()
snaps = [s for s in runner._load_active_registrations() if s.id in (2, 4, 5)]
print("ticking:", [(s.id, s.family_key, str(s.last_processed_date)) for s in snaps])
for s in snaps:  # sequential, one family at a time
    runner._process_family(s.family_key, [s])
    print("done", s.family_key, flush=True)
after = snapshot()
changed = [f for f in after if before.get(f) != after[f]] + [f for f in before if f not in after]
print("store files changed during tick:", len(changed), changed[:5])
db = SessionLocal()
for r in db.execute(select(R).where(R.id.in_([2, 4, 5]))).scalars().all():
    days = json.loads(r.day_results_json)
    print(r.id, r.family_key, r.status, "last_processed", r.last_processed_date, "n_days", r.n_forward_trading_days, "n_formations", r.n_formations, "ticked", r.last_ticked_at)
    for d in days: print("   ", d["date"], "reformed", d["reformed"], "realized", d["realized"], "gross", round(d["gross_return"], 6), "net", round(d["net_return"], 6), "n_long/short", d["n_long"], d["n_short"], "n_eligible", d.get("n_eligible"))
db.close()
