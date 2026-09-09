"""Run from the MAIN checkout:  ./venv/bin/python data/research_runs/live_panel_coverage_2026-09-10/reset_live_registrations.py

Owner-approved reset (2026-09-10, 'ตามนี้'): the three equity live
registrations go back to just before their first formation, with
last_processed_date = 2026-09-03 so the runner's normal catch-up re-forms on
the 2026-09-04 row and realizes 09-08 onward from the complete, repaired
panel. Nothing else on the rows changes. Refuses to run unless the pre-reset
backup file exists and matches the rows as they are now."""
import json
import sys
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))
from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models.cross_sectional_forward_validation import (
    CrossSectionalForwardValidationRegistration as R,
)
from app.services.research_lab.cross_sectional_forward import (
    CrossSectionalForwardState,
    serialize_cross_sectional_forward_state,
)

backup = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("live_registrations_pre_reset_2026-09-10.json")
ids = [2, 4, 5]
saved = {r["id"]: r for r in json.loads(backup.read_text())["rows"]}
assert sorted(saved) == ids, sorted(saved)
print("db:", engine.url)
db = SessionLocal()
rows = db.execute(select(R).where(R.id.in_(ids))).scalars().all()
assert len(rows) == 3
for r in rows:
    b = saved[r.id]
    assert r.status == "in_progress" == b["status"], (r.id, r.status)
    assert json.loads(r.day_results_json) == b["day_results_json"], f"row {r.id} differs from the backup; refusing"
    assert json.loads(r.carry_state_json) == b["carry_state_json"], f"row {r.id} state differs from the backup; refusing"
fresh = json.dumps(serialize_cross_sectional_forward_state(CrossSectionalForwardState()))
for r in rows:
    r.carry_state_json = fresh
    r.day_results_json = "[]"
    r.formations_json = "[]"
    r.n_forward_trading_days = 0
    r.n_formations = 0
    r.last_processed_date = date(2026, 9, 3)
    r.last_ticked_at = None
    r.graduated_at = None
db.commit()
for r in db.execute(select(R).where(R.id.in_(ids))).scalars().all():
    print("reset:", r.id, r.family_key, r.pattern_id, r.status, "last_processed", r.last_processed_date,
          "n_days", r.n_forward_trading_days, "n_formations", r.n_formations, "days", r.day_results_json, "state", r.carry_state_json)
db.close()
