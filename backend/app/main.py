import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
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


@app.get("/_debug/client-ip")
def debug_client_ip(request: Request) -> dict[str, object]:
    # Temporary diagnostic to find why rate limiting isn't triggering in
    # production — will be removed once the cause is confirmed.
    return {
        "client_host": request.client.host if request.client else None,
        "client_port": request.client.port if request.client else None,
        "x_forwarded_for": request.headers.get("x-forwarded-for"),
        "x_real_ip": request.headers.get("x-real-ip"),
        "headers": dict(request.headers),
    }


@app.get("/_debug/limiter-state")
def debug_limiter_state(request: Request) -> dict[str, object]:
    from app.rate_limit import limiter as _limiter

    storage = _limiter._storage
    window = _limiter._storage.__class__.__name__
    keys = list(getattr(storage, "storage", {}).keys()) if hasattr(storage, "storage") else []
    return {
        "storage_class": window,
        "num_keys_tracked": len(keys),
        "keys": [str(k) for k in keys][:20],
        "enabled": _limiter.enabled,
        "default_limits": [str(x) for x in _limiter._default_limits],
        "worker_pid": __import__("os").getpid(),
    }
