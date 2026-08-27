import sys
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.models.forward_validation import ForwardValidationRegistration
from app.models.screening_job import ScreeningJob
from app.services.research_lab.autonomous_research_runner import AutonomousResearchRunner
from app.models.experiment_run import ExperimentRun
from sqlalchemy import select

runner = AutonomousResearchRunner()
system_user_id = runner._ensure_system_user()

db = SessionLocal()
try:
    # Flag one real existing system-owned registration as underperforming.
    reg = db.execute(
        select(ForwardValidationRegistration).where(ForwardValidationRegistration.user_id == system_user_id).limit(1)
    ).scalar_one_or_none()
    if reg is None:
        print("no system registration found to flag")
        sys.exit(0)
    reg.status = "underperforming"
    flagged_ticker_a, flagged_ticker_b, flagged_strategy = reg.ticker_a, reg.ticker_b, reg.strategy_name
    db.commit()
    print(f"flagged registration {reg.id}: {flagged_strategy} {flagged_ticker_a}/{flagged_ticker_b} -> underperforming")

    # Find a completed system job for the same strategy whose candidates include this ticker,
    # or just reset any completed job's trigger flag and re-run to observe the skip in logs.
    job = db.execute(
        select(ScreeningJob).where(
            ScreeningJob.user_id == system_user_id, ScreeningJob.strategy_name == flagged_strategy, ScreeningJob.status == "completed"
        ).order_by(ScreeningJob.id.desc()).limit(1)
    ).scalar_one_or_none()
    if job is None:
        print("no completed job for this strategy")
        sys.exit(0)
    job.auto_backtests_triggered = False
    db.commit()
    job_id = job.id
finally:
    db.close()

before = SessionLocal()
try:
    n_runs_before = len(before.execute(select(ExperimentRun)).scalars().all())
finally:
    before.close()

runner._trigger_top_candidate_backtests(job_id, flagged_strategy, system_user_id)

after = SessionLocal()
try:
    reg_after = after.get(ForwardValidationRegistration, reg.id)
    print(f"registration {reg.id} after tick: status={reg_after.status}, n_forward_trading_days={reg_after.n_forward_trading_days}")
    runs = after.execute(select(ExperimentRun).where(ExperimentRun.strategy_name == flagged_strategy)).scalars().all()
    matching = [r for r in runs if r.ticker_a == flagged_ticker_a and r.ticker_b == flagged_ticker_b]
    print(f"ExperimentRun rows for the flagged ticker ({flagged_ticker_a}/{flagged_ticker_b}): {len(matching)} (should be unchanged from before the tick if skipped correctly)")
finally:
    after.close()
