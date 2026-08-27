"""add execution control, live orders, per-strategy execution state, is_live

Revision ID: c4a91d7e5f20
Revises: 7b7a98d4b443
Create Date: 2026-08-26 00:00:00.000000

Chains after Phase 4's strategy_portfolios/strategy_portfolio_allocations
migration (7b7a98d4b443, confirmed current head), which live_orders and
strategy_execution_states both reference by foreign key.

The one hand-written part autogenerate cannot produce is the execution_control
seed row at the bottom: the kill switch must exist, and must exist HALTED, from
the moment this schema does. A missing row would be created halted by
execution_control_service anyway, but relying on that would leave a window in
which the table's own state is undefined.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a91d7e5f20'
down_revision: Union[str, Sequence[str], None] = '7b7a98d4b443'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('execution_control',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trading_halted', sa.Boolean(), nullable=False),
    sa.Column('halted_reason', sa.String(length=255), nullable=True),
    sa.Column('halted_at', sa.DateTime(), nullable=True),
    sa.Column('halted_by_user_id', sa.Integer(), nullable=True),
    sa.Column('daily_loss_breach_at', sa.DateTime(), nullable=True),
    sa.Column('daily_loss_breach_pct', sa.Float(), nullable=True),
    sa.Column('resumed_at', sa.DateTime(), nullable=True),
    sa.Column('resumed_by_user_id', sa.Integer(), nullable=True),
    sa.Column('last_tick_at', sa.DateTime(), nullable=True),
    sa.Column('last_tick_status', sa.String(length=255), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['halted_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['resumed_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('live_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('forward_validation_registration_id', sa.Integer(), nullable=True),
    sa.Column('strategy_portfolio_allocation_id', sa.Integer(), nullable=True),
    sa.Column('ticker', sa.String(length=10), nullable=False),
    sa.Column('side', sa.String(length=10), nullable=False),
    sa.Column('notional_requested', sa.Float(), nullable=True),
    sa.Column('qty_requested', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('broker_order_id', sa.String(length=64), nullable=True),
    sa.Column('client_order_id', sa.String(length=64), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('filled_at', sa.DateTime(), nullable=True),
    sa.Column('filled_avg_price', sa.Float(), nullable=True),
    sa.Column('filled_qty', sa.Float(), nullable=True),
    sa.Column('decision_price', sa.Float(), nullable=True),
    sa.Column('realized_slippage_bps', sa.Float(), nullable=True),
    sa.Column('assumed_cost_bps', sa.Float(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('raw_response_json', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['forward_validation_registration_id'], ['forward_validation_registrations.id'], ),
    sa.ForeignKeyConstraint(['strategy_portfolio_allocation_id'], ['strategy_portfolio_allocations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_live_orders_broker_order_id'), 'live_orders', ['broker_order_id'], unique=False)
    op.create_index(op.f('ix_live_orders_client_order_id'), 'live_orders', ['client_order_id'], unique=True)
    op.create_index(op.f('ix_live_orders_forward_validation_registration_id'), 'live_orders', ['forward_validation_registration_id'], unique=False)
    op.create_index(op.f('ix_live_orders_status'), 'live_orders', ['status'], unique=False)
    op.create_index(op.f('ix_live_orders_strategy_portfolio_allocation_id'), 'live_orders', ['strategy_portfolio_allocation_id'], unique=False)
    op.create_index(op.f('ix_live_orders_ticker'), 'live_orders', ['ticker'], unique=False)
    op.create_index(op.f('ix_live_orders_user_id'), 'live_orders', ['user_id'], unique=False)

    op.create_table('strategy_execution_states',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('forward_validation_registration_id', sa.Integer(), nullable=False),
    sa.Column('strategy_portfolio_allocation_id', sa.Integer(), nullable=True),
    sa.Column('day_pnl_json', sa.Text(), nullable=False),
    sa.Column('last_marked_date', sa.Date(), nullable=True),
    sa.Column('halted_at', sa.DateTime(), nullable=True),
    sa.Column('halted_reason', sa.String(length=255), nullable=True),
    sa.Column('halted_trailing_sharpe', sa.Float(), nullable=True),
    sa.Column('halted_trailing_days', sa.Integer(), nullable=True),
    sa.Column('frozen_target_json', sa.Text(), nullable=True),
    sa.Column('resumed_at', sa.DateTime(), nullable=True),
    sa.Column('resumed_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['forward_validation_registration_id'], ['forward_validation_registrations.id'], ),
    sa.ForeignKeyConstraint(['resumed_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['strategy_portfolio_allocation_id'], ['strategy_portfolio_allocations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_strategy_execution_states_forward_validation_registration_id'), 'strategy_execution_states', ['forward_validation_registration_id'], unique=True)
    op.create_index(op.f('ix_strategy_execution_states_user_id'), 'strategy_execution_states', ['user_id'], unique=False)

    # server_default is required, not cosmetic: existing rows have no value for
    # a NOT NULL column without one.
    op.add_column(
        'strategy_portfolios',
        sa.Column('is_live', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )

    # Hand-added, not autogenerated. Seeded HALTED so a fresh deploy, a restored
    # backup, or any database built from this migration can never silently
    # start submitting orders — a human must explicitly resume.
    op.bulk_insert(
        sa.table(
            'execution_control',
            sa.column('id', sa.Integer),
            sa.column('trading_halted', sa.Boolean),
            sa.column('halted_reason', sa.String),
        ),
        [{'id': 1, 'trading_halted': True, 'halted_reason': 'startup_default'}],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('strategy_portfolios', 'is_live')
    op.drop_index(op.f('ix_strategy_execution_states_user_id'), table_name='strategy_execution_states')
    op.drop_index(op.f('ix_strategy_execution_states_forward_validation_registration_id'), table_name='strategy_execution_states')
    op.drop_table('strategy_execution_states')
    op.drop_index(op.f('ix_live_orders_user_id'), table_name='live_orders')
    op.drop_index(op.f('ix_live_orders_ticker'), table_name='live_orders')
    op.drop_index(op.f('ix_live_orders_strategy_portfolio_allocation_id'), table_name='live_orders')
    op.drop_index(op.f('ix_live_orders_status'), table_name='live_orders')
    op.drop_index(op.f('ix_live_orders_forward_validation_registration_id'), table_name='live_orders')
    op.drop_index(op.f('ix_live_orders_client_order_id'), table_name='live_orders')
    op.drop_index(op.f('ix_live_orders_broker_order_id'), table_name='live_orders')
    op.drop_table('live_orders')
    op.drop_table('execution_control')
