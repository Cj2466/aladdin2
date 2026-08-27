import sys, time
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.models.screening_job import ScreeningJob
from app.models.screening_candidate import ScreeningCandidate
from app.services.research_lab.screening_runner import ScreeningRunner, _JobSnapshot
from app.services.research_lab.momentum import STRATEGY_NAME as MOM_STRATEGY

db = SessionLocal()
job = ScreeningJob(user_id=1, strategy_name=MOM_STRATEGY, universe_size=503, status="queued")
db.add(job)
db.commit()
db.refresh(job)
job_id = job.id
db.close()

runner = ScreeningRunner()
t0 = time.time()
runner._process_job(_JobSnapshot(id=job_id, strategy_name=MOM_STRATEGY))
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
n_hac_true = sum(1 for c in candidates if c.hac_significant)
n_hmm_set = sum(1 for c in candidates if c.regime_hmm is not None)
print(f"total candidates: {len(candidates)}, hac_significant=True: {n_hac_true}, regime_hmm set: {n_hmm_set}")
for c in candidates[:10]:
    print(c.ticker_a, "score=", round(c.score,2), "direction=", c.direction, "regime=", c.regime, "hac_sig=", c.hac_significant, "regime_hmm=", c.regime_hmm)
db.close()
