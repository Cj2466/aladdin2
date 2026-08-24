"""add screening jobs and candidates tables

Revision ID: b5f9850987cf
Revises: db5cce5e05f3
Create Date: 2026-08-24 13:01:56.904078

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5f9850987cf'
down_revision: Union[str, Sequence[str], None] = 'db5cce5e05f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('screening_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('strategy_name', sa.String(length=50), nullable=False),
    sa.Column('universe_size', sa.Integer(), nullable=False),
    sa.Column('n_tickers_resolved', sa.Integer(), nullable=False),
    sa.Column('n_candidates_found', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('last_ticked_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_screening_jobs_status'), 'screening_jobs', ['status'], unique=False)
    op.create_index(op.f('ix_screening_jobs_strategy_name'), 'screening_jobs', ['strategy_name'], unique=False)
    op.create_index(op.f('ix_screening_jobs_user_id'), 'screening_jobs', ['user_id'], unique=False)

    op.create_table('screening_candidates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('ticker_a', sa.String(length=10), nullable=False),
    sa.Column('ticker_b', sa.String(length=10), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=True),
    sa.Column('discovered_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['screening_jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_screening_candidates_job_id'), 'screening_candidates', ['job_id'], unique=False)
    op.create_index(op.f('ix_screening_candidates_ticker_a'), 'screening_candidates', ['ticker_a'], unique=False)
    op.create_index(op.f('ix_screening_candidates_ticker_b'), 'screening_candidates', ['ticker_b'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_screening_candidates_ticker_b'), table_name='screening_candidates')
    op.drop_index(op.f('ix_screening_candidates_ticker_a'), table_name='screening_candidates')
    op.drop_index(op.f('ix_screening_candidates_job_id'), table_name='screening_candidates')
    op.drop_table('screening_candidates')

    op.drop_index(op.f('ix_screening_jobs_user_id'), table_name='screening_jobs')
    op.drop_index(op.f('ix_screening_jobs_strategy_name'), table_name='screening_jobs')
    op.drop_index(op.f('ix_screening_jobs_status'), table_name='screening_jobs')
    op.drop_table('screening_jobs')
