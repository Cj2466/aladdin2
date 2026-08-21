import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, live_quotes, portfolios, risk, stress
from app.services.live_quotes.finnhub_ws_client import FinnhubWebSocketClient
from app.services.live_quotes.manager import live_quote_manager

_finnhub_client = FinnhubWebSocketClient(live_quote_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_finnhub_client.run())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="Aladdin2 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(risk.router)
app.include_router(live_quotes.router)
app.include_router(auth.router)
app.include_router(portfolios.router)
app.include_router(stress.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
