class RiskComputationError(Exception):
    """Base for domain errors raised by compute_portfolio_risk. Deliberately
    has no FastAPI/HTTPException knowledge — each router translates these to
    a status code at its own boundary."""


class MissingTickerDataError(RiskComputationError):
    def __init__(self, tickers: list[str], is_benchmark: bool = False, label: str | None = None) -> None:
        self.tickers = tickers
        self.is_benchmark = is_benchmark
        resolved_label = label or ("benchmark" if is_benchmark else "holdings")
        super().__init__(f"No price data available for {resolved_label}: {', '.join(tickers)}")


class InsufficientHistoryError(RiskComputationError):
    def __init__(self, n_obs: int, label: str = "holdings") -> None:
        # `label` defaults to "holdings" so all three pre-existing call
        # sites keep their exact original message; strategy-portfolio call
        # sites pass label="selected strategies", where "holdings" would be
        # actively misleading (the assets are backtested strategy
        # instances, not tickers).
        self.n_obs = n_obs
        super().__init__(
            f"Only {n_obs} overlapping trading days of history across these "
            f"{label} — not enough to compute meaningful risk estimates."
        )


class OptimizationInfeasibleError(RiskComputationError):
    """Raised when the long-only, capped-weight optimization problem has no
    feasible solution (too few holdings for the per-holding cap) or the
    solver fails to converge."""
