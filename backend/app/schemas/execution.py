from datetime import datetime

from pydantic import BaseModel, Field


class ExecutionControlOut(BaseModel):
    trading_halted: bool
    halted_reason: str | None
    halted_at: datetime | None
    daily_loss_breach_at: datetime | None
    daily_loss_breach_pct: float | None
    resumed_at: datetime | None
    last_tick_at: datetime | None
    last_tick_status: str | None
    # True when a resume would be refused purely because the breaker fired
    # today. Surfaced so the UI can explain WHY the button will not work,
    # rather than letting a user click it and get a 409 they have to decode.
    resume_blocked_until_next_trading_day: bool


class ExecutionAccountOut(BaseModel):
    """A live snapshot, never cached. Numbers are floats here even though
    Alpaca returns strings — parsed once, at the edge."""

    equity: float
    last_equity: float
    cash: float
    buying_power: float
    daily_pnl_pct: float
    status: str
    trading_blocked: bool
    account_blocked: bool


class ExecutionSettingsOut(BaseModel):
    """The limits currently in force, echoed back so the operating envelope is
    visible on the same screen as the halt button rather than only in a .env
    file."""

    paper_trading: bool
    broker_base_url: str
    capital_fraction: float
    max_position_notional: float
    max_total_notional: float
    daily_loss_limit_pct: float
    min_order_notional: float
    check_interval_seconds: int


class StrategyExecutionStateOut(BaseModel):
    forward_validation_registration_id: int
    strategy_name: str
    ticker_a: str
    ticker_b: str
    halted_at: datetime | None
    halted_reason: str | None
    halted_trailing_sharpe: float | None
    halted_trailing_days: int | None
    trailing_sharpe: float | None
    trailing_days: int
    trailing_return: float | None
    breaker_threshold: float
    breaker_lookback_trading_days: int


class SlippageAggregateOut(BaseModel):
    label: str
    n_fills: int
    notional_weighted_mean_bps: float | None
    simple_mean_bps: float | None
    median_bps: float | None
    worst_bps: float | None
    assumed_cost_bps: float | None
    excess_vs_assumed_bps: float | None
    # False below the fill-count floor. Reported alongside every average so a
    # mean over three fills is never mistaken for a finding.
    meaningful_sample: bool


class SlippageReportOut(BaseModel):
    overall: SlippageAggregateOut
    per_strategy: list[SlippageAggregateOut]
    min_fills_for_meaningful_sample: int
    methodology_note: str


class ExecutionStatusOut(BaseModel):
    control: ExecutionControlOut
    settings: ExecutionSettingsOut
    # None when the broker could not be reached, or no credentials are
    # configured. Deliberately nullable rather than zero-filled: "we do not
    # know the account state" and "the account has zero equity" must never look
    # the same on a control screen.
    account: ExecutionAccountOut | None
    account_error: str | None
    market_open: bool | None
    strategies: list[StrategyExecutionStateOut]
    slippage: SlippageReportOut


class LiveOrderOut(BaseModel):
    id: int
    forward_validation_registration_id: int | None
    strategy_portfolio_allocation_id: int | None
    ticker: str
    side: str
    notional_requested: float | None
    qty_requested: float | None
    status: str
    broker_order_id: str | None
    client_order_id: str
    submitted_at: datetime
    filled_at: datetime | None
    filled_avg_price: float | None
    filled_qty: float | None
    decision_price: float | None
    realized_slippage_bps: float | None
    assumed_cost_bps: float | None
    error_message: str | None


class LivePositionOut(BaseModel):
    ticker: str
    qty: float
    signed_market_value: float
    avg_entry_price: float | None
    current_price: float | None
    unrealized_pl: float | None
    side: str


class HaltRequest(BaseModel):
    reason: str = Field(default="manual", min_length=1, max_length=255)


class ResumeRequest(BaseModel):
    # Must equal execution_control_service.RESUME_CONFIRMATION exactly.
    # Asymmetric on purpose: halting takes no confirmation at all, because
    # friction belongs only on the direction that can lose money.
    confirmation: str


class StrategyResumeRequest(BaseModel):
    confirmation: str


class SetLivePortfolioRequest(BaseModel):
    is_live: bool
