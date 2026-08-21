from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
MARKET_OPEN_MINUTES = 9 * 60 + 30
MARKET_CLOSE_MINUTES = 16 * 60


def current_market_state() -> str:
    """Plain US-equity regular-session clock check. Does not know about
    market holidays — paired on the frontend with a staleness fallback
    (no ticks for ~2 min => show 'no live updates' regardless of this)."""
    now = datetime.now(EASTERN)
    if now.weekday() >= 5:  # Saturday, Sunday
        return "closed"
    minutes_since_midnight = now.hour * 60 + now.minute
    if MARKET_OPEN_MINUTES <= minutes_since_midnight < MARKET_CLOSE_MINUTES:
        return "open"
    return "closed"
