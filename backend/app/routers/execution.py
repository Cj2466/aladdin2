import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import settings
from app.db import get_db
from app.models.forward_validation import ForwardValidationRegistration
from app.models.live_order import LiveOrder
from app.models.strategy_execution_state import StrategyExecutionState
from app.models.user import User
from app.schemas.execution import (
    ExecutionAccountOut,
    ExecutionControlOut,
    ExecutionSettingsOut,
    ExecutionStatusOut,
    HaltRequest,
    LiveOrderOut,
    LivePositionOut,
    ResumeRequest,
    SlippageAggregateOut,
    SlippageReportOut,
    StrategyExecutionStateOut,
    StrategyResumeRequest,
)
from app.services.execution import alpaca_client, slippage, strategy_breaker
from app.services.execution.alpaca_client import AlpacaError
from app.services.execution.execution_control_service import (
    RESUME_CONFIRMATION,
    ResumeRefused,
    eastern_trading_date,
    get_control,
    halt,
    resume,
)
from app.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/execution", tags=["execution"])

MAX_ORDERS_PAGE = 200


def _control_out(db: Session) -> ExecutionControlOut:
    control = get_control(db)
    blocked = False
    if control.daily_loss_breach_at is not None:
        blocked = eastern_trading_date(control.daily_loss_breach_at) >= eastern_trading_date(
            utcnow_naive()
        )
    return ExecutionControlOut(
        trading_halted=control.trading_halted,
        halted_reason=control.halted_reason,
        halted_at=control.halted_at,
        daily_loss_breach_at=control.daily_loss_breach_at,
        daily_loss_breach_pct=control.daily_loss_breach_pct,
        resumed_at=control.resumed_at,
        last_tick_at=control.last_tick_at,
        last_tick_status=control.last_tick_status,
        resume_blocked_until_next_trading_day=blocked,
    )


def _settings_out() -> ExecutionSettingsOut:
    return ExecutionSettingsOut(
        paper_trading=alpaca_client.is_paper(),
        broker_base_url=alpaca_client.base_url(),
        capital_fraction=settings.execution_capital_fraction,
        max_position_notional=settings.execution_max_position_notional,
        max_total_notional=settings.execution_max_total_notional,
        daily_loss_limit_pct=settings.execution_daily_loss_limit_pct,
        min_order_notional=settings.execution_min_order_notional,
        check_interval_seconds=settings.execution_check_interval_seconds,
    )


def _slippage_report(db: Session, user: User) -> SlippageReportOut:
    """Realized execution cost versus the cost_bps every backtest assumed.

    Measurement and disclosure only — nothing here feeds back into cost_bps,
    into halting, or into position sizing. What a divergence means is a
    judgment call for a human reading the numbers.
    """
    rows = (
        db.execute(
            select(LiveOrder).where(
                LiveOrder.user_id == user.id,
                LiveOrder.realized_slippage_bps.is_not(None),
            )
        )
        .scalars()
        .all()
    )

    registration_ids = {r.forward_validation_registration_id for r in rows if r.forward_validation_registration_id}
    labels: dict[int, str] = {}
    if registration_ids:
        for registration in (
            db.execute(
                select(ForwardValidationRegistration).where(
                    ForwardValidationRegistration.id.in_(registration_ids)
                )
            )
            .scalars()
            .all()
        ):
            labels[registration.id] = (
                f"{registration.strategy_name} {registration.ticker_a}/{registration.ticker_b}"
            )

    all_fills: list[slippage.FillObservation] = []
    per_strategy: dict[str, list[slippage.FillObservation]] = {}
    for row in rows:
        notional = row.notional_requested
        if notional is None and row.filled_qty is not None and row.filled_avg_price is not None:
            notional = abs(row.filled_qty * row.filled_avg_price)
        label = labels.get(row.forward_validation_registration_id or -1, "unattributed")
        observation = slippage.FillObservation(
            label=label,
            slippage_bps=float(row.realized_slippage_bps or 0.0),
            notional=float(notional or 0.0),
            assumed_cost_bps=row.assumed_cost_bps,
        )
        all_fills.append(observation)
        per_strategy.setdefault(label, []).append(observation)

    def _to_out(aggregate: slippage.SlippageAggregate) -> SlippageAggregateOut:
        return SlippageAggregateOut(**aggregate.__dict__)

    return SlippageReportOut(
        overall=_to_out(slippage.aggregate("all strategies", all_fills)),
        per_strategy=[
            _to_out(slippage.aggregate(label, fills))
            for label, fills in sorted(per_strategy.items())
        ],
        min_fills_for_meaningful_sample=slippage.MIN_FILLS_FOR_MEANINGFUL_SLIPPAGE,
        methodology_note=(
            "Realized slippage is the fill price against the most recent daily close the signal "
            "was computed on, signed so positive is always adverse. That is the correct reference "
            "for testing cost_bps: the walk-forward engine realizes close-to-close returns and "
            "charges cost_bps once per unit of position change against them. Measurement only — "
            "nothing here adjusts cost_bps or halts trading."
        ),
    )


def _strategy_states(db: Session, user: User) -> list[StrategyExecutionStateOut]:
    rows = (
        db.execute(
            select(StrategyExecutionState).where(StrategyExecutionState.user_id == user.id)
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    registrations = {
        r.id: r
        for r in db.execute(
            select(ForwardValidationRegistration).where(
                ForwardValidationRegistration.id.in_(
                    [r.forward_validation_registration_id for r in rows]
                )
            )
        )
        .scalars()
        .all()
    }

    out: list[StrategyExecutionStateOut] = []
    for row in rows:
        registration = registrations.get(row.forward_validation_registration_id)
        verdict = strategy_breaker.evaluate(strategy_breaker.load_day_pnl(row.day_pnl_json))
        out.append(
            StrategyExecutionStateOut(
                forward_validation_registration_id=row.forward_validation_registration_id,
                strategy_name=registration.strategy_name if registration else "unknown",
                ticker_a=registration.ticker_a if registration else "",
                ticker_b=registration.ticker_b if registration else "",
                halted_at=row.halted_at,
                halted_reason=row.halted_reason,
                halted_trailing_sharpe=row.halted_trailing_sharpe,
                halted_trailing_days=row.halted_trailing_days,
                trailing_sharpe=verdict.trailing_sharpe,
                trailing_days=verdict.trailing_days,
                trailing_return=verdict.trailing_return,
                breaker_threshold=strategy_breaker.BREAKER_SHARPE_THRESHOLD,
                breaker_lookback_trading_days=strategy_breaker.BREAKER_LOOKBACK_TRADING_DAYS,
            )
        )
    return out


@router.get("/status", response_model=ExecutionStatusOut)
def get_execution_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionStatusOut:
    account_out: ExecutionAccountOut | None = None
    account_error: str | None = None
    market_open: bool | None = None

    if settings.alpaca_api_key and settings.alpaca_api_secret:
        try:
            account = alpaca_client.get_account()
            equity = alpaca_client.account_float(account, "equity")
            last_equity = alpaca_client.account_float(account, "last_equity")
            account_out = ExecutionAccountOut(
                equity=equity,
                last_equity=last_equity,
                cash=alpaca_client.account_float(account, "cash"),
                buying_power=alpaca_client.account_float(account, "buying_power"),
                daily_pnl_pct=((equity - last_equity) / last_equity) if last_equity else 0.0,
                status=str(account.get("status", "")),
                trading_blocked=bool(account.get("trading_blocked")),
                account_blocked=bool(account.get("account_blocked")),
            )
            market_open = bool(alpaca_client.get_clock().get("is_open"))
        except AlpacaError as exc:
            # Surfaced, never swallowed: a control screen that silently shows
            # nothing is indistinguishable from one showing a flat account.
            account_error = str(exc)
    else:
        account_error = "Alpaca credentials are not configured."

    return ExecutionStatusOut(
        control=_control_out(db),
        settings=_settings_out(),
        account=account_out,
        account_error=account_error,
        market_open=market_open,
        strategies=_strategy_states(db, current_user),
        slippage=_slippage_report(db, current_user),
    )


@router.post("/halt", response_model=ExecutionControlOut)
def halt_trading(
    payload: HaltRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionControlOut:
    """Always succeeds, no confirmation, idempotent. The safe direction should
    never have friction — including when the broker is unreachable, which is
    why a failed cancel_all_orders cannot fail this request."""
    reason = payload.reason if payload is not None else "manual"
    halt(db, reason=f"manual:{reason}", user_id=current_user.id)
    try:
        cancelled = alpaca_client.cancel_all_orders()
        logger.warning(
            "Execution halted by user %s; cancelled %s open order(s).",
            current_user.id,
            len(cancelled),
        )
    except AlpacaError:
        logger.exception("Execution halted, but cancelling open orders failed.")
    return _control_out(db)


@router.post("/resume", response_model=ExecutionControlOut)
def resume_trading(
    payload: ResumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionControlOut:
    try:
        resume(db, user_id=current_user.id, confirmation=payload.confirmation)
    except ResumeRefused as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _control_out(db)


@router.post("/strategies/{registration_id}/resume", response_model=StrategyExecutionStateOut)
def resume_strategy(
    registration_id: int,
    payload: StrategyResumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyExecutionStateOut:
    """Lift a per-strategy circuit breaker. Confirmation-gated like the
    account-wide resume, and never automatic: the breaker only ever transitions
    INTO halted, matching check_underperformance's own deliberately
    non-reversible posture."""
    if payload.confirmation != RESUME_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Confirmation must be exactly {RESUME_CONFIRMATION!r}.",
        )
    row = db.execute(
        select(StrategyExecutionState).where(
            StrategyExecutionState.forward_validation_registration_id == registration_id,
            StrategyExecutionState.user_id == current_user.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    row.halted_at = None
    row.halted_reason = None
    # frozen_target_json is cleared so the strategy resumes tracking its live
    # signal rather than staying pinned to the exposure it had when it tripped.
    row.frozen_target_json = None
    row.resumed_at = utcnow_naive()
    row.resumed_by_user_id = current_user.id
    db.commit()

    states = {
        s.forward_validation_registration_id: s for s in _strategy_states(db, current_user)
    }
    return states[registration_id]


@router.get("/orders", response_model=list[LiveOrderOut])
def list_live_orders(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LiveOrderOut]:
    rows = (
        db.execute(
            select(LiveOrder)
            .where(LiveOrder.user_id == current_user.id)
            .order_by(LiveOrder.id.desc())
            .limit(min(limit, MAX_ORDERS_PAGE))
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [LiveOrderOut.model_validate(row, from_attributes=True) for row in rows]


@router.get("/positions", response_model=list[LivePositionOut])
def list_live_positions(
    current_user: User = Depends(get_current_user),
) -> list[LivePositionOut]:
    """Proxied straight from the broker, uncached — the same source of truth the
    runner diffs against, so the screen can never disagree with what actually
    gets traded."""
    try:
        positions = alpaca_client.get_positions()
    except AlpacaError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    out: list[LivePositionOut] = []
    for position in positions:
        out.append(
            LivePositionOut(
                ticker=position.get("symbol", ""),
                qty=alpaca_client.position_signed_qty(position),
                signed_market_value=alpaca_client.position_signed_market_value(position),
                avg_entry_price=_maybe_float(position.get("avg_entry_price")),
                current_price=_maybe_float(position.get("current_price")),
                unrealized_pl=_maybe_float(position.get("unrealized_pl")),
                side=str(position.get("side", "")),
            )
        )
    return out


def _maybe_float(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
