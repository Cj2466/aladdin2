from dataclasses import dataclass


@dataclass
class QuoteState:
    price: float
    previous_close: float
    change_percent: float
    market_state: str  # "open" | "closed"
    last_updated: float  # unix epoch seconds
