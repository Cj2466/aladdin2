"""add strategy portfolios and allocations tables

Revision ID: 7b7a98d4b443
Revises: f7afb72c016d
Create Date: 2026-08-25 20:26:46.238033

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b7a98d4b443'
down_revision: Union[str, Sequence[str], None] = 'f7afb72c016d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('strategy_portfolios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('last_optimized_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_strategy_portfolios_user_id'), 'strategy_portfolios', ['user_id'], unique=False)

    op.create_table('strategy_portfolio_allocations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('strategy_portfolio_id', sa.Integer(), nullable=False),
    sa.Column('experiment_run_id', sa.Integer(), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['experiment_run_id'], ['experiment_runs.id'], ),
    sa.ForeignKeyConstraint(['strategy_portfolio_id'], ['strategy_portfolios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('strategy_portfolio_id', 'experiment_run_id', name='uq_strategy_allocation_portfolio_run')
    )
    op.create_index(op.f('ix_strategy_portfolio_allocations_experiment_run_id'), 'strategy_portfolio_allocations', ['experiment_run_id'], unique=False)
    op.create_index(op.f('ix_strategy_portfolio_allocations_strategy_portfolio_id'), 'strategy_portfolio_allocations', ['strategy_portfolio_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_strategy_portfolio_allocations_strategy_portfolio_id'), table_name='strategy_portfolio_allocations')
    op.drop_index(op.f('ix_strategy_portfolio_allocations_experiment_run_id'), table_name='strategy_portfolio_allocations')
    op.drop_table('strategy_portfolio_allocations')
    op.drop_index(op.f('ix_strategy_portfolios_user_id'), table_name='strategy_portfolios')
    op.drop_table('strategy_portfolios')
