"""add last_optimization_method to strategy_portfolios

Revision ID: e2b7c1a94f30
Revises: ac4e9d44c9a0
Create Date: 2026-08-28 00:00:00.000000

Chains after ac4e9d44c9a0 (confirmed the single current head via
ScriptDirectory.get_heads()).

One nullable column. NULL means "no automated reweighting has ever written
this portfolio's weights" — true of every user-built portfolio and of every
row that already exists when this migration runs, so there is deliberately no
backfill: inventing "mean_variance" for historical rows would assert something
this schema never actually recorded. AutonomousPortfolioRunner fills it in on
its next tick for the one portfolio it owns.

Nullable and therefore needing no server_default (contrast the is_live column
added in c4a91d7e5f20, which is NOT NULL and so required one).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b7c1a94f30'
down_revision: Union[str, Sequence[str], None] = 'ac4e9d44c9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'strategy_portfolios',
        sa.Column('last_optimization_method', sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('strategy_portfolios', 'last_optimization_method')
