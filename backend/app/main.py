import asyncio
import logging
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
    macro_beta,
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
from app.services.research_lab.macro_beta_refresh_runner import MacroBetaRefreshRunner
from app.services.research_lab.membership_refresh_runner import MembershipRefreshRunner
from app.services.research_lab.quality_forward_registration import (
    register_quality_forward_validations_on_startup,
)
from app.services.research_lab.screening_runner import ScreeningRunner
from app.services.research_lab.sweep_runner import SweepRunner

# The one place this application configures logging, and the reason it has to:
# uvicorn's default config (uvicorn.config.LOGGING_CONFIG, and the start
# command in render.yaml passes no --log-config) names only the `uvicorn`,
# `uvicorn.error` and `uvicorn.access` loggers and has no "root" key at all,
# so logging.config.dictConfig leaves the root logger exactly as Python
# ships it: no handlers and level WARNING. Every `logging.getLogger("app...")`
# record below WARNING is therefore dropped by the level check and never
# reaches Render's log viewer, so without something here the startup
# registration's own outcome lines would be unverifiable after a deploy.
#
# THE LEVEL IS RAISED ON THE `app` LOGGER, NOT ON ROOT, AND THAT DISTINCTION
# IS A SECURITY BOUNDARY, NOT A STYLE CHOICE. Setting root to INFO would also
# un-gate every third-party library's INFO logger, and httpx's is
# `logger.info('HTTP Request: %s %s ...', request.method, request.url)` with
# the FULL query string — while fred_provider passes api_key=, and
# finnhub_rest/finnhub_fundamentals pass token=, as query params. Root-level
# INFO would print FRED_API_KEY and FINNHUB_API_KEY verbatim into Render's log
# viewer on every such call. Scoping the level to `app` gives this project's
# own loggers exactly the visibility they need and leaves every library's
# threshold at the WARNING it already had before this line existed.
#
# basicConfig still runs, at the default WARNING, purely to put a formatted
# StreamHandler on root: without one, third-party WARNING/ERROR records fall
# through to logging.lastResort, which prints a bare message with no level or
# logger name. It is a no-op if anything (pytest, a future --log-config) has
# already configured root, and uvicorn configures its own loggers before it
# imports this module — and `uvicorn` sets propagate=False with its own
# handler — so this neither clobbers nor is clobbered nor double-prints.
# Format matches forward_validation_backfill.py's.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("app").setLevel(logging.INFO)

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
_macro_beta_refresh_runner = MacroBetaRefreshRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A ONE-SHOT setup step, deliberately NOT a background runner at all: it
    # has nothing to do periodically. It runs here because Render's free plan
    # has no Shell to run a one-off script from, so a deploy — which is
    # automatic and free — is what has to carry it. Safe on every process
    # start (it is idempotent on (user_id, config_hash) and never resets an
    # accumulated forward clock), fast (in-memory spec resolution plus a
    # couple of indexed queries, no market-data or EDGAR fetch), and it never
    # raises: a transient DB failure here logs and lets the API start, and the
    # next process start retries. Awaited rather than task-ified so the log
    # line lands before the runners start writing their own.
    await register_quality_forward_validations_on_startup()

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
    # The 11th background task ("Project 2", Layer 1). Read-only with respect
    # to every existing table — it only ever INSERTs into macro_commodity_betas
    # — and it is coupled to no execution pathway, so starting it here cannot
    # affect trading in any state.
    macro_beta_refresh_task = asyncio.create_task(_macro_beta_refresh_runner.run())
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
        macro_beta_refresh_task,
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
app.include_router(macro_beta.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
