import asyncio
import logging

from fastapi import APIRouter, WebSocket
from pydantic import ValidationError

from app.config import settings
from app.schemas.live_quotes import SubscribeMessage
from app.services.live_quotes.manager import live_quote_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/live-quotes")
async def live_quotes_ws(websocket: WebSocket) -> None:
    if not settings.finnhub_api_key:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "code": "not_configured",
            "message": "Live quotes are not configured on this server.",
        })
        await websocket.close(code=1011)
        return

    await websocket.accept()
    queue = live_quote_manager.register(websocket)

    async def writer() -> None:
        while True:
            message = await queue.get()
            await websocket.send_json(message)

    async def reader() -> None:
        while True:
            raw = await websocket.receive_json()
            try:
                parsed = SubscribeMessage.model_validate(raw)
            except ValidationError:
                continue
            await live_quote_manager.subscribe(websocket, set(parsed.tickers))

    writer_task = asyncio.create_task(writer())
    reader_task = asyncio.create_task(reader())
    try:
        _, pending = await asyncio.wait(
            {writer_task, reader_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    finally:
        writer_task.cancel()
        reader_task.cancel()
        await asyncio.gather(writer_task, reader_task, return_exceptions=True)
        await live_quote_manager.unsubscribe_all(websocket)
