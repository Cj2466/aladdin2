"""add macro commodity betas table

Revision ID: a1f7c3d90b42
Revises: e2b7c1a94f30
Create Date: 2026-09-01 00:00:00.000000

Chains after e2b7c1a94f30 (confirmed the single current head via
`alembic heads` before writing this file).

Layer 1 of "Project 2". One row per (driver, ticker, as_of_date).

DELIBERATELY NO UNIQUE CONSTRAINT on (driver, ticker, as_of_date), and that
absence is a design decision rather than an oversight. The table is
APPEND-ONLY: every recompute INSERTs a new generation so that beta drift stays
auditable and so a later phase's record of "which beta value did we act on"
can never be invalidated by a subsequent recompute. A uniqueness constraint
would invite an upsert, and an upsert would destroy exactly the history this
table exists to keep. A duplicate row from a double-run is recoverable; an
overwritten generation is not.

The composite index on (driver, ticker, as_of_date) serves the read pattern the
API actually uses — newest generation for one driver — while the single-column
indexes come from index=True on the model and match SQLAlchemy's default
ix_<table>_<column> naming.

That composite index is plain ASCENDING even though the design sketch asked for
"as_of_date DESC". A DESC modifier makes it an EXPRESSION index, which
Alembic's autogenerate cannot compare against a reflected schema: measured
directly while writing this migration, `alembic check` then reports a
drop+recreate of that index on every run, against a database that is genuinely
up to date. A permanently false drift signal would train future authors to
ignore the one command that catches real drift, and the DESC bought nothing to
offset it — B-tree indexes are traversable in both directions, so
ORDER BY as_of_date DESC uses an ascending index perfectly well.

beta_shock_days and sign_agreement are nullable because "not estimable"
(too few usable shock days) is a real and distinct state from a measured zero.
Backfilling either with 0.0 would turn missing data into a confident claim of
no sensitivity, so both stay NULL-able permanently rather than being a gap to
close later.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f7c3d90b42'
down_revision: Union[str, Sequence[str], None] = 'e2b7c1a94f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'macro_commodity_betas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('driver', sa.String(length=64), nullable=False),
        sa.Column('ticker', sa.String(length=20), nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('window_days', sa.Integer(), nullable=False),
        sa.Column('beta_full_sample', sa.Float(), nullable=False),
        sa.Column('beta_shock_days', sa.Float(), nullable=True),
        sa.Column('correlation_full_sample', sa.Float(), nullable=False),
        sa.Column('n_observations_full_sample', sa.Integer(), nullable=False),
        sa.Column('n_observations_shock_days', sa.Integer(), nullable=False),
        sa.Column('t_stat_full_sample', sa.Float(), nullable=False),
        sa.Column('sign_agreement', sa.Float(), nullable=True),
        sa.Column(
            'computed_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_macro_commodity_betas_driver'), 'macro_commodity_betas', ['driver'], unique=False
    )
    op.create_index(
        op.f('ix_macro_commodity_betas_ticker'), 'macro_commodity_betas', ['ticker'], unique=False
    )
    op.create_index(
        op.f('ix_macro_commodity_betas_as_of_date'),
        'macro_commodity_betas',
        ['as_of_date'],
        unique=False,
    )
    op.create_index(
        'ix_macro_commodity_betas_driver_ticker_as_of',
        'macro_commodity_betas',
        ['driver', 'ticker', 'as_of_date'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_macro_commodity_betas_driver_ticker_as_of', table_name='macro_commodity_betas')
    op.drop_index(op.f('ix_macro_commodity_betas_as_of_date'), table_name='macro_commodity_betas')
    op.drop_index(op.f('ix_macro_commodity_betas_ticker'), table_name='macro_commodity_betas')
    op.drop_index(op.f('ix_macro_commodity_betas_driver'), table_name='macro_commodity_betas')
    op.drop_table('macro_commodity_betas')
