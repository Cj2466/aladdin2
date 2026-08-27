import sys
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.services.research_lab.autonomous_research_runner import AutonomousResearchRunner
from app.models.forward_validation import ForwardValidationRegistration
from app.models.screening_job import ScreeningJob
from sqlalchemy import select

runner = AutonomousResearchRunner()
system_user_id = runner._ensure_system_user()

db = SessionLocal()
try:
    job = db.get(ScreeningJob, 7)
    job.auto_backtests_triggered = False
    db.commit()
finally:
    db.close()

runner._trigger_top_candidate_backtests(7, "ou_pairs_v1", system_user_id)

after = SessionLocal()
try:
    regs = after.execute(select(ForwardValidationRegistration)).scalars().all()
    print("registrations after re-run (should still be 8, idempotent):", len(regs))
finally:
    after.close()
