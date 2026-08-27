import sys
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.services.research_lab.autonomous_research_runner import AutonomousResearchRunner
from app.models.forward_validation import ForwardValidationRegistration
from app.models.screening_job import ScreeningJob
from sqlalchemy import select

runner = AutonomousResearchRunner()
system_user_id = runner._ensure_system_user()
print("system_user_id:", system_user_id)

db = SessionLocal()
try:
    jobs = db.execute(
        select(ScreeningJob).where(
            ScreeningJob.user_id == system_user_id,
            ScreeningJob.status == "completed",
            ScreeningJob.auto_backtests_triggered.is_(False),
        )
    ).scalars().all()
    print("completed unflagged jobs:", [(j.id, j.strategy_name) for j in jobs])
finally:
    db.close()

before = SessionLocal()
try:
    n_before = len(before.execute(select(ForwardValidationRegistration)).scalars().all())
finally:
    before.close()
print("registrations before:", n_before)

for job in jobs:
    runner._trigger_top_candidate_backtests(job.id, job.strategy_name, system_user_id)

after = SessionLocal()
try:
    regs = after.execute(select(ForwardValidationRegistration)).scalars().all()
    print("registrations after:", len(regs))
    for r in regs:
        print(" -", r.id, r.strategy_name, r.ticker_a, r.ticker_b, "user_id=", r.user_id, "is_system=", r.user_id == system_user_id)
finally:
    after.close()
