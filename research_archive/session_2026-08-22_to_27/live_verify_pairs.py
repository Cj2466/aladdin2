import sys, time
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.models.screening_job import ScreeningJob
from app.models.screening_candidate import ScreeningCandidate
from app.services.research_lab.screening_runner import ScreeningRunner, _JobSnapshot
from app.services.research_lab.ou_pairs import STRATEGY_NAME as PAIRS_STRATEGY

db = SessionLocal()
job = ScreeningJob(user_id=1, strategy_name=PAIRS_STRATEGY, universe_size=503, status="queued")
db.add(job)
db.commit()
db.refresh(job)
job_id = job.id
db.close()

runner = ScreeningRunner()
t0 = time.time()
runner._process_job(_JobSnapshot(id=job_id, strategy_name=PAIRS_STRATEGY))
elapsed = time.time() - t0
print(f"elapsed: {elapsed:.1f}s")

db = SessionLocal()
job = db.get(ScreeningJob, job_id)
print("status:", job.status, "n_tickers_resolved:", job.n_tickers_resolved, "n_candidates_found:", job.n_candidates_found)
if job.status == "failed":
    print("error:", job.error_message)
candidates = db.execute(
    ScreeningCandidate.__table__.select().where(ScreeningCandidate.job_id == job_id).order_by(ScreeningCandidate.id)
).fetchall()
for c in candidates[:15]:
    print(c)
db.close()
