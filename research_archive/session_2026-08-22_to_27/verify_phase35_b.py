import sys
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.services.research_lab.autonomous_research_runner import AutonomousResearchRunner
from app.models.forward_validation import ForwardValidationRegistration
from app.models.screening_job import ScreeningJob
from app.models.screening_candidate import ScreeningCandidate
from sqlalchemy import select

runner = AutonomousResearchRunner()
system_user_id = runner._ensure_system_user()

db = SessionLocal()
try:
    jobs = db.execute(
        select(ScreeningJob).where(ScreeningJob.user_id == system_user_id, ScreeningJob.status == "completed")
        .order_by(ScreeningJob.id.desc()).limit(4)
    ).scalars().all()
    for j in jobs:
        cands = db.execute(select(ScreeningCandidate).where(ScreeningCandidate.job_id == j.id).limit(3)).scalars().all()
        print(j.id, j.strategy_name, "triggered=", j.auto_backtests_triggered, "candidates:", [(c.ticker_a, c.ticker_b) for c in cands])
    pick = jobs[0] if jobs else None
finally:
    db.close()

if pick is not None:
    reset_db = SessionLocal()
    try:
        job = reset_db.get(ScreeningJob, pick.id)
        job.auto_backtests_triggered = False
        reset_db.commit()
        print("reset job", pick.id, "auto_backtests_triggered -> False")
    finally:
        reset_db.close()

    before = SessionLocal()
    try:
        n_before = len(before.execute(select(ForwardValidationRegistration)).scalars().all())
    finally:
        before.close()
    print("registrations before:", n_before)

    runner._trigger_top_candidate_backtests(pick.id, pick.strategy_name, system_user_id)

    after = SessionLocal()
    try:
        regs = after.execute(select(ForwardValidationRegistration)).scalars().all()
        print("registrations after:", len(regs))
        for r in regs:
            print(" -", r.id, r.strategy_name, r.ticker_a, r.ticker_b, "user_id=", r.user_id, "is_system=", r.user_id == system_user_id)
        job2 = after.get(ScreeningJob, pick.id)
        print("job auto_backtests_triggered now:", job2.auto_backtests_triggered)
    finally:
        after.close()
else:
    print("no completed system jobs found at all")
