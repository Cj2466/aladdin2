"""Alpaca **trading** REST client — the order/position/account path.

Deliberately distinct from any market-data provider: this module places
orders and reads balances, and is the only thing in this codebase that can
move money. It talks exclusively to the trading API host.

Sync httpx, matching resend_client's style rather than finnhub's async
websocket — this is request/response REST, not a stream, and every caller is
already running inside asyncio.to_thread.
"""

import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"
LIVE_BASE_URL = "https://api.alpaca.markets/v2"

REQUEST_TIMEOUT_SECONDS = 15.0

# Same shape and same numbers as yfinance_provider._call_with_retry — the
# existing retry precedent in this codebase — rather than a second, subtly
# different backoff policy.
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0

T = TypeVar("T")


class AlpacaError(Exception):
    """Any failure to get a trustworthy answer out of the broker.

    Every caller treats this as fail-closed: the tick logs it and returns
    without submitting a single order. There is deliberately no "assume flat"
    or "assume the market is open" fallback anywhere.
    """


def _call_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = RETRY_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Exponential backoff with jitter, mirroring
    yfinance_provider._call_with_retry exactly, including its reason for
    resolving `sleep` at call time rather than binding time.sleep as a
    parameter default (a bound default captures the original function at
    import time, before any monkeypatch applies)."""
    sleep_fn = sleep if sleep is not None else time.sleep
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception:
            if attempt == attempts:
                raise
            sleep_fn(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1))
    raise AssertionError("unreachable")  # loop always returns or raises


def is_paper() -> bool:
    """Live trading requires BOTH flags: paper mode off AND an independently
    named confirmation flag on. One accidental env edit — a copied .env with
    ALPACA_PAPER_TRADING=false, a typo'd deploy variable — can therefore never
    by itself point this system at real money. Anything short of both being
    set resolves to paper."""
    return not (
        settings.alpaca_paper_trading is False and settings.alpaca_live_trading_confirmed is True
    )


def base_url() -> str:
    return PAPER_BASE_URL if is_paper() else LIVE_BASE_URL


def _headers() -> dict[str, str]:
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        # Raised BEFORE any network call, so a misconfigured deployment fails
        # loudly and immediately instead of producing a stream of 401s that
        # look like a transient outage.
        raise AlpacaError("Alpaca credentials are not configured (ALPACA_API_KEY/ALPACA_API_SECRET).")
    return {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
        "accept": "application/json",
    }


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    retry: bool = True,
    sleep: Callable[[float], None] | None = None,
) -> Any:
    headers = _headers()
    url = f"{base_url()}{path}"

    def _do() -> Any:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.request(method, url, headers=headers, params=params, json=json_body)
            response.raise_for_status()
            if not response.content:
                return None
            return response.json()

    try:
        if retry:
            return _call_with_retry(_do, sleep=sleep)
        return _do()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        raise AlpacaError(f"Alpaca {method} {path} failed: {exc.response.status_code} {body}") from exc
    except AlpacaError:
        raise
    except Exception as exc:
        raise AlpacaError(f"Alpaca {method} {path} failed: {exc}") from exc


# --- reads -------------------------------------------------------------------


def get_account(*, sleep: Callable[[float], None] | None = None) -> dict:
    """GET /account. Every numeric field comes back as a STRING (verified
    against the real paper account: equity "100000", not 100000) — callers use
    account_float() rather than indexing and hoping."""
    return _request("GET", "/account", sleep=sleep)


def get_clock(*, sleep: Callable[[float], None] | None = None) -> dict:
    """GET /clock — the broker's own holiday-aware session clock. Used instead
    of this repo's market_hours.py, which was built for live-quote staleness
    display and says in its own docstring that it does not know about market
    holidays."""
    return _request("GET", "/clock", sleep=sleep)


def get_positions(*, sleep: Callable[[float], None] | None = None) -> list[dict]:
    """GET /positions. Returns [] when flat."""
    return _request("GET", "/positions", sleep=sleep) or []


def get_open_orders(
    symbol: str | None = None, *, sleep: Callable[[float], None] | None = None
) -> list[dict]:
    params: dict[str, Any] = {"status": "open"}
    if symbol is not None:
        params["symbols"] = symbol
    return _request("GET", "/orders", params=params, sleep=sleep) or []


def get_order(order_id: str, *, sleep: Callable[[float], None] | None = None) -> dict:
    return _request("GET", f"/orders/{order_id}", sleep=sleep)


# --- writes ------------------------------------------------------------------


def submit_notional_order(
    *,
    symbol: str,
    notional: float,
    side: str,
    client_order_id: str,
    sleep: Callable[[float], None] | None = None,
) -> dict:
    """Dollar-denominated market order.

    Notional orders are restricted to type="market"/time_in_force="day" (and
    limit/stop variants), per Alpaca's own fractional-trading documentation —
    GTC/IOC/FOK/OPG/CLS are rejected outright.

    They also CANNOT open or extend a short position. Verified directly against
    the real paper account (2026-08-26, flat, market closed): a $1 notional SELL
    of AAPL came back
        422 {"code":42210000,"message":"fractional orders cannot be sold short"}
    while the same order as 1 whole share was accepted. Callers must therefore
    route anything touching a short to submit_qty_order — without that routing
    every pairs trade's short leg would be rejected and the trade would execute
    one-legged, which is not market-neutral at all.

    Deliberately NOT retried. Every other call here is a read, where a retry is
    free; re-POSTing an order is not. `client_order_id` makes a duplicate
    submission a broker-side rejection rather than a duplicate fill, but the
    correct response to an ambiguous order failure is still to stop and let the
    next tick re-derive from the broker's real positions."""
    return _request(
        "POST",
        "/orders",
        json_body={
            "symbol": symbol,
            # Two decimals: Alpaca rejects sub-cent notionals, and this makes
            # the requested amount exactly reproducible from the stored row.
            "notional": f"{notional:.2f}",
            "side": side,
            "type": "market",
            "time_in_force": "day",
            "client_order_id": client_order_id,
        },
        retry=False,
        sleep=sleep,
    )


def submit_qty_order(
    *,
    symbol: str,
    qty: float,
    side: str,
    client_order_id: str,
    sleep: Callable[[float], None] | None = None,
) -> dict:
    """Whole-share market order — the only route Alpaca offers for opening or
    extending a SHORT position (see submit_notional_order for the live-verified
    rejection), and also the exact way to close a position in full without a
    rounding remainder.

    Not retried, for the same reason as submit_notional_order."""
    return _request(
        "POST",
        "/orders",
        json_body={
            "symbol": symbol,
            "qty": f"{qty:g}",
            "side": side,
            "type": "market",
            "time_in_force": "day",
            "client_order_id": client_order_id,
        },
        retry=False,
        sleep=sleep,
    )


def cancel_all_orders(*, sleep: Callable[[float], None] | None = None) -> list[dict]:
    """DELETE /orders — cancels every open, unfilled order.

    Called on every halt, manual or automatic. Deliberately does NOT liquidate
    already-filled positions: force-flattening during exactly the stressed
    moment that triggered a halt can realize a worse price than waiting, and on
    a single-operator system that judgment belongs to the human."""
    return _request("DELETE", "/orders", sleep=sleep) or []


# --- parsing helpers ---------------------------------------------------------


def account_float(account: dict, field: str) -> float:
    """Alpaca returns every account number as a string. Verified against the
    real paper account: {"equity": "100000", "last_equity": "100000", ...}."""
    raw = account.get(field)
    if raw is None or raw == "":
        raise AlpacaError(f"Alpaca account response is missing {field!r}")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise AlpacaError(f"Alpaca account field {field!r} is not numeric: {raw!r}") from exc


def position_signed_market_value(position: dict) -> float:
    """Signed dollar exposure of one position: positive long, negative short.

    Derived from `side` plus abs(market_value), NOT from market_value's raw
    sign. Alpaca's own API reference documents `side` as an enum of
    "long"/"short" and says nothing at all about the sign convention for the
    numeric fields (checked directly). Real payloads in the wild do carry
    negative qty/market_value for shorts, and Alpaca's own example code tests
    `qty < 0` — but "the docs don't promise it" plus "this is the number that
    decides order sizes" is exactly the combination that warrants not
    depending on it. Taking abs() and re-applying the sign from the documented
    enum is correct under either convention.
    """
    raw = position.get("market_value")
    try:
        value = abs(float(raw))
    except (TypeError, ValueError) as exc:
        raise AlpacaError(f"Alpaca position market_value is not numeric: {raw!r}") from exc
    return -value if str(position.get("side", "")).lower() == "short" else value


def position_signed_qty(position: dict) -> float:
    """Signed share count, sign taken from `side` for the same reason as
    position_signed_market_value."""
    raw = position.get("qty")
    try:
        qty = abs(float(raw))
    except (TypeError, ValueError) as exc:
        raise AlpacaError(f"Alpaca position qty is not numeric: {raw!r}") from exc
    return -qty if str(position.get("side", "")).lower() == "short" else qty


def position_intraday_pnl(position: dict) -> float | None:
    """The broker's own session P&L for this position, in dollars. Server-side,
    so it is not this codebase's arithmetic — the same reason the daily-loss
    breaker reads account.equity rather than deriving equity itself."""
    raw = position.get("unrealized_intraday_pl")
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
