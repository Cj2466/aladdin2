"""add macro threshold alert rules

Revision ID: 6e17e2e70f23
Revises: cbffd3fa57df
Create Date: 2026-08-22 18:18:40.900525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e17e2e70f23'
down_revision: Union[str, Sequence[str], None] = 'cbffd3fa57df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # batch_alter_table: SQLite has no native ALTER COLUMN, so relaxing
    # portfolio_id's NOT NULL (to allow user-scoped-only macro rules) has to
    # go through the recreate-table batch path. Postgres would accept a
    # bare alter_column, but the migration must work on both.
    with op.batch_alter_table('alert_rules') as batch_op:
        batch_op.add_column(sa.Column('series_id', sa.String(length=30), nullable=True))
        batch_op.alter_column('portfolio_id', existing_type=sa.INTEGER(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('alert_rules') as batch_op:
        batch_op.alter_column('portfolio_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column('series_id')
