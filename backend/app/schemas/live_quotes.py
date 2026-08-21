from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SubscribeMessage(BaseModel):
    """Inbound message from a browser client: the full set of tickers it
    currently wants live quotes for (replaces, not appends to, its previous
    subscription)."""

    type: Literal["subscribe"] = "subscribe"
    tickers: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("tickers")
    @classmethod
    def normalize_tickers(cls, tickers: list[str]) -> list[str]:
        normalized: list[str] = []
        for ticker in tickers:
            cleaned = ticker.strip().upper()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized
