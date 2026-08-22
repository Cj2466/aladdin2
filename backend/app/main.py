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
    export,
    factor_risk,
    live_quotes,
    optimizer,
    portfolios,
    risk,
    stress,
)
from app.services.alerts.checker import AlertChecker
from app.services.live_quotes.finnhub_ws_client import FinnhubWebSocketClient
from app.services.live_quotes.manager import live_quote_manager

_finnhub_client = FinnhubWebSocketClient(live_quote_manager)
_alert_checker = AlertChecker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    finnhub_task = asyncio.create_task(_finnhub_client.run())
    alert_task = asyncio.create_task(_alert_checker.run())
    yield
    for task in (finnhub_task, alert_task):
        task.cancel()
    for task in (finnhub_task, alert_task):
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/_debug/email-config")
def _debug_email_config() -> dict[str, bool | str]:
    return {
        "frontend_url": settings.frontend_url,
        "resend_api_key_set": bool(settings.resend_api_key),
    }
