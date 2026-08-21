from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """Naive-but-UTC, used for every stored/compared timestamp — SQLite has
    no real timezone-aware datetime type, so mixing naive/aware here would
    risk a comparison TypeError."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
