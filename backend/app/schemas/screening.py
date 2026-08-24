from typing import Literal

from pydantic import BaseModel


class ScreeningJobCreateRequest(BaseModel):
    strategy_name: Literal["ou_pairs_v1", "momentum_v1"]


class ScreeningCandidateOut(BaseModel):
    ticker_a: str
    ticker_b: str
    score: float
    direction: Literal["long", "short"] | None
    regime: Literal["trending", "mean_reverting", "indeterminate"] | None
    discovered_at: str


class ScreeningJobOut(BaseModel):
    id: int
    strategy_name: str
    universe_size: int
    n_tickers_resolved: int
    n_candidates_found: int
    status: Literal["queued", "running", "completed", "failed"]
    error_message: str | None
    created_at: str
    completed_at: str | None


class ScreeningJobDetailOut(ScreeningJobOut):
    candidates: list[ScreeningCandidateOut]
    methodology_note: str
