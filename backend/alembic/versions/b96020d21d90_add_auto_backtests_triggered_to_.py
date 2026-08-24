"""add auto_backtests_triggered to screening_jobs

Revision ID: b96020d21d90
Revises: 7a59e4b33aba
Create Date: 2026-08-24 20:03:40.189083

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b96020d21d90'
down_revision: Union[str, Sequence[str], None] = '7a59e4b33aba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default=true so pre-existing (all user-submitted, non-system-owned)
    # rows backfill to "already handled" and are never retroactively picked up
    # by AutonomousResearchRunner — mirrors fe9ec946c496's exact precedent for
    # users.is_verified. The ORM's own default=False governs all new inserts.
    op.add_column(
        'screening_jobs',
        sa.Column('auto_backtests_triggered', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('screening_jobs') as batch_op:
        batch_op.drop_column('auto_backtests_triggered')
