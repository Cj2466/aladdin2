import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.rate_limit import limiter
from app.routers import (
    alerts,
    auth,
    cross_sectional_forward_validation,
    execution,
    export,
    factor_risk,
    forward_validation,
    live_quotes,
    macro,
    optimizer,
    portfolios,
    research_lab,
    risk,
    screening,
    stock_analysis,
    strategy_portfolios,
    stress,
    sweeps,
)
from app.services.alerts.checker import AlertChecker
from app.services.execution.execution_runner import ExecutionRunner
from app.services.live_quotes.finnhub_ws_client import FinnhubWebSocketClient
from app.services.live_quotes.manager import live_quote_manager
from app.services.research_lab.autonomous_portfolio_runner import (
    AutonomousPortfolioRunner,
)
from app.services.research_lab.autonomous_research_runner import (
    AutonomousResearchRunner,
)
from app.services.research_lab.cross_sectional_forward_validation_runner import (
    CrossSectionalForwardValidationRunner,
)
from app.services.research_lab.forward_validation_runner import ForwardValidationRunner
from app.services.research_lab.membership_refresh_runner import MembershipRefreshRunner
from app.services.research_lab.screening_runner import ScreeningRunner
from app.services.research_lab.sweep_runner import SweepRunner

_finnhub_client = FinnhubWebSocketClient(live_quote_manager)
_alert_checker = AlertChecker()
_forward_validation_runner = ForwardValidationRunner()
# The cross-sectional sibling — a SEPARATE runner over a SEPARATE table, so
# the pairs/momentum runner above keeps exactly the query, snapshot and
# processing it already had (see the model's class docstring).
_cross_sectional_forward_validation_runner = CrossSectionalForwardValidationRunner()
_sweep_runner = SweepRunner()
_screening_runner = ScreeningRunner()
_autonomous_research_runner = AutonomousResearchRunner()
_membership_refresh_runner = MembershipRefreshRunner()
_autonomous_portfolio_runner = AutonomousPortfolioRunner()
_execution_runner = ExecutionRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    finnhub_task = asyncio.create_task(_finnhub_client.run())
    alert_task = asyncio.create_task(_alert_checker.run())
    forward_validation_task = asyncio.create_task(_forward_validation_runner.run())
    cross_sectional_forward_validation_task = asyncio.create_task(
        _cross_sectional_forward_validation_runner.run()
    )
    sweep_task = asyncio.create_task(_sweep_runner.run())
    screening_task = asyncio.create_task(_screening_runner.run())
    autonomous_research_task = asyncio.create_task(_autonomous_research_runner.run())
    membership_refresh_task = asyncio.create_task(_membership_refresh_runner.run())
    autonomous_portfolio_task = asyncio.create_task(_autonomous_portfolio_runner.run())
    # The 10th background task. It starts with trading halted (ExecutionControl
    # is seeded trading_halted=True and this runner returns immediately while
    # it is), so launching it here can never begin submitting orders on its own.
    execution_task = asyncio.create_task(_execution_runner.run())
    yield
    tasks = (
        finnhub_task,
        alert_task,
        forward_validation_task,
        cross_sectional_forward_validation_task,
        sweep_task,
        screening_task,
        autonomous_research_task,
        membership_refresh_task,
        autonomous_portfolio_task,
        execution_task,
    )
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Aladdin2 API", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(risk.router)
app.include_router(live_quotes.router)
app.include_router(auth.router)
app.include_router(portfolios.router)
app.include_router(stress.router)
app.include_router(optimizer.router)
app.include_router(export.router)
app.include_router(alerts.router)
app.include_router(factor_risk.router)
app.include_router(macro.router)
app.include_router(stock_analysis.router)
app.include_router(research_lab.router)
app.include_router(forward_validation.router)
app.include_router(cross_sectional_forward_validation.router)
app.include_router(sweeps.router)
app.include_router(screening.router)
app.include_router(strategy_portfolios.router)
app.include_router(execution.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
