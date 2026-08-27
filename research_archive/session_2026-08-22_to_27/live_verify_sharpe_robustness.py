import sys, json
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.models.experiment_run import ExperimentRun
from sqlalchemy import select

db = SessionLocal()
rows = db.execute(
    select(ExperimentRun).where(ExperimentRun.status == "ok", ExperimentRun.num_trades >= 3).limit(5)
).scalars().all()
print(f"found {len(rows)} candidate ok runs with >=3 trades")
for row in rows:
    print(row.id, row.strategy_name, row.ticker_a, row.ticker_b, "num_trades=", row.num_trades)
db.close()
