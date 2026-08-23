"""add sweep jobs table

Revision ID: 5a658cb38b77
Revises: 3107457b11f3
Create Date: 2026-08-23 14:47:23.765579

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a658cb38b77'
down_revision: Union[str, Sequence[str], None] = '3107457b11f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sweep_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('strategy_name', sa.String(length=50), nullable=False),
    sa.Column('ticker_a', sa.String(length=10), nullable=False),
    sa.Column('ticker_b', sa.String(length=10), nullable=False),
    sa.Column('lookback_years', sa.Integer(), nullable=False),
    sa.Column('grid_spec_json', sa.Text(), nullable=False),
    sa.Column('total_configurations', sa.Integer(), nullable=False),
    sa.Column('configurations_completed', sa.Integer(), nullable=False),
    sa.Column('configurations_failed', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('last_ticked_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sweep_jobs_status'), 'sweep_jobs', ['status'], unique=False)
    op.create_index(op.f('ix_sweep_jobs_strategy_name'), 'sweep_jobs', ['strategy_name'], unique=False)
    op.create_index(op.f('ix_sweep_jobs_ticker_a'), 'sweep_jobs', ['ticker_a'], unique=False)
    op.create_index(op.f('ix_sweep_jobs_ticker_b'), 'sweep_jobs', ['ticker_b'], unique=False)
    op.create_index(op.f('ix_sweep_jobs_user_id'), 'sweep_jobs', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sweep_jobs_user_id'), table_name='sweep_jobs')
    op.drop_index(op.f('ix_sweep_jobs_ticker_b'), table_name='sweep_jobs')
    op.drop_index(op.f('ix_sweep_jobs_ticker_a'), table_name='sweep_jobs')
    op.drop_index(op.f('ix_sweep_jobs_strategy_name'), table_name='sweep_jobs')
    op.drop_index(op.f('ix_sweep_jobs_status'), table_name='sweep_jobs')
    op.drop_table('sweep_jobs')
