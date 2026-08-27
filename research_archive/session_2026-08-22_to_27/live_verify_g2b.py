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
    reg = db.execute(
        select(ForwardValidationRegistration).where(
            ForwardValidationRegistration.user_id == system_user_id,
            ForwardValidationRegistration.status != "underperforming",
        ).limit(1)
    ).scalar_one_or_none()
    reg_id, flagged_ticker_a, flagged_ticker_b, flagged_strategy = reg.id, reg.ticker_a, reg.ticker_b, reg.strategy_name
    reg.status = "underperforming"
    db.commit()
    print(f"flagged registration {reg_id}: {flagged_strategy} {flagged_ticker_a}/{flagged_ticker_b} -> underperforming")

    job = db.execute(
        select(ScreeningJob).where(
            ScreeningJob.user_id == system_user_id, ScreeningJob.strategy_name == flagged_strategy, ScreeningJob.status == "completed"
        ).order_by(ScreeningJob.id.desc()).limit(1)
    ).scalar_one_or_none()
    job.auto_backtests_triggered = False
    job_id = job.id
    db.commit()
finally:
    db.close()

runner._trigger_top_candidate_backtests(job_id, flagged_strategy, system_user_id)

after = SessionLocal()
try:
    reg_after = after.get(ForwardValidationRegistration, reg_id)
    print(f"registration {reg_id} after tick: status={reg_after.status}, n_forward_trading_days={reg_after.n_forward_trading_days}")
finally:
    after.close()
