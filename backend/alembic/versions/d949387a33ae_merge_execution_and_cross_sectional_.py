"""merge execution and cross-sectional forward validation heads

Revision ID: d949387a33ae
Revises: c4a91d7e5f20, c4e1a9d70f52
Create Date: 2026-08-27 17:49:54.916014

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd949387a33ae'
down_revision: Union[str, Sequence[str], None] = ('c4a91d7e5f20', 'c4e1a9d70f52')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
