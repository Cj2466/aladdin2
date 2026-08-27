import asyncio, logging
from sqlalchemy import select
from app.db import SessionLocal
from app.models.experiment_run import ExperimentRun
from app.models.forward_validation import ForwardValidationRegistration
from app.models.strategy_portfolio import StrategyPortfolio
from app.services.research_lab.autonomous_portfolio_runner import (
    AutonomousPortfolioRunner, SYSTEM_PORTFOLIO_NAME, MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO)
from app.services.research_lab.system_account import get_system_user_id

logging.basicConfig(level=logging.INFO, format="    LOG %(levelname)s %(message)s")
runner = AutonomousPortfolioRunner()


def show(tag):
    with SessionLocal() as db:
        sid = get_system_user_id(db)
        regs = db.execute(select(ForwardValidationRegistration).where(
            ForwardValidationRegistration.user_id == sid).order_by(ForwardValidationRegistration.id)).scalars().all()
        print(f"\n===== {tag} =====")
        print("  system registrations:", {f"{r.ticker_a}/{r.ticker_b}": r.status for r in regs})
        p = db.execute(select(StrategyPortfolio).where(
            StrategyPortfolio.user_id == sid,
            StrategyPortfolio.name == SYSTEM_PORTFOLIO_NAME)).scalar_one_or_none()
        if p is None:
            print("  system portfolio: DOES NOT EXIST")
            return None
        out = {}
        print(f"  system portfolio #{p.id}: {len(p.allocations)} allocations, last_optimized_at={p.last_optimized_at}")
        for a in sorted(p.allocations, key=lambda a: -a.weight):
            run = db.get(ExperimentRun, a.experiment_run_id)
            label = f"{run.ticker_a}/{run.ticker_b}"
            out[label] = round(a.weight, 4)
            print(f"      {label:<14} run#{a.experiment_run_id:<4} weight {round(a.weight,4)}")
        return out


def reg_ids():
    with SessionLocal() as db:
        sid = get_system_user_id(db)
        rows = db.execute(select(ForwardValidationRegistration.id, ForwardValidationRegistration.ticker_a,
                                 ForwardValidationRegistration.ticker_b).where(
            ForwardValidationRegistration.user_id == sid).order_by(ForwardValidationRegistration.id)).all()
    return [(r[0], f"{r[1]}/{r[2]}") for r in rows]


def set_status(reg_id, status, days=None):
    with SessionLocal() as db:
        r = db.get(ForwardValidationRegistration, reg_id)
        r.status = status
        if days is not None:
            r.n_forward_trading_days = days
        db.commit()


ids = reg_ids()
before = show("STEP 0 — real dev DB as it stands today")

print("\n>>> TICK 1 (nothing graduated yet — expect the minimum-count gate to refuse to build)")
asyncio.run(runner._tick())
show("AFTER TICK 1")

first_five = ids[:MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO]
for rid, label in first_five:
    set_status(rid, "forward_validated", days=126)
print(f"\n>>> simulated day-126 graduation for {len(first_five)} REAL registrations: {[l for _, l in first_five]}")
print("    (only `status`/`n_forward_trading_days` are simulated — the config hash, the ExperimentRun")
print("     resolution, the return series and the optimizer all run on genuine dev-DB data)")
print("\n>>> TICK 2 (expect: portfolio built and optimized)")
asyncio.run(runner._tick())
after_build = show("AFTER TICK 2")

sixth = ids[MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO]
set_status(sixth[0], "forward_validated", days=126)
print(f"\n>>> a 6th real registration graduates: {sixth[1]}")
print(">>> TICK 3 (expect: auto-inclusion + a forced reweight, despite the once-a-day guard)")
asyncio.run(runner._tick())
after_add = show("AFTER TICK 3")

victim = first_five[0]
set_status(victim[0], "underperforming")
print(f"\n>>> G1's trailing-Sharpe rule flags {victim[1]} underperforming")
print(">>> TICK 4 (expect: removed from the portfolio, survivors reweighted)")
asyncio.run(runner._tick())
after_prune = show("AFTER TICK 4")

print("\n>>> TICK 5 (nothing changed — expect a pure no-op)")
asyncio.run(runner._tick())
after_noop = show("AFTER TICK 5")

print("\n===== SUMMARY =====")
print("  after build (5 members):", after_build)
print("  after add   (6 members):", after_add)
print("  after prune (5 members):", after_prune)
print("  after no-op tick       :", after_noop)
print("  weights actually changed on auto-add?   ", after_build != after_add)
print("  weights actually changed on auto-prune? ", after_add != after_prune)
print("  pruned member gone?                     ", victim[1] not in (after_prune or {}))
print("  no-op tick left everything untouched?   ", after_prune == after_noop)
