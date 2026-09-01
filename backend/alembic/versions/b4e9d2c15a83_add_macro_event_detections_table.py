"""add macro event detections table

Revision ID: b4e9d2c15a83
Revises: a1f7c3d90b42
Create Date: 2026-09-02 00:00:00.000000

Chains after a1f7c3d90b42 (confirmed the single current head via
`alembic heads` before writing this file).

Phase 2.2 of "Project 2", Layer 2 — Stage A only. THIS MIGRATION CREATES
EXACTLY ONE TABLE. The plan describes six further macro_event_* tables
(llm_judgments, candidate_tickers, registrations, execution_states, control)
but every one of them belongs to Phase 2.3 or 2.4, and creating them now would
ship empty schema for code that does not exist and has not been designed
against real data yet.

DELIBERATELY NO UNIQUE CONSTRAINT, same reasoning as macro_commodity_betas:
the table is APPEND-ONLY. Every tick INSERTs one row per source and nothing is
ever updated or deleted. A duplicate row from a double-run is recoverable; an
overwritten observation destroys the trigger-frequency record that is this
entire phase's deliverable.

MOST ROWS WILL HAVE triggered=False, AND THAT IS THE POINT. The phase exists to
measure how often uncalibrated thresholds actually trip, and a rate needs a
denominator. A table holding only the moments something fired would leave the
trigger RATE permanently unrecoverable.

trigger_value / trigger_threshold / driver / trigger_metric are all NULLABLE
because a source that failed (network timeout, malformed payload) still writes
its row — with `error` populated and no measurement. That is a genuinely
different state from a measured zero and must never be backfilled to 0.0, the
same missing-vs-measured discipline macro_commodity_betas.beta_shock_days
documents.

The composite index is plain ASCENDING, never DESC. A DESC modifier makes it an
EXPRESSION index that Alembic's autogenerate cannot compare against a reflected
schema, which makes `alembic check` report a spurious drop+recreate on every
run against a database that is genuinely up to date — measured directly on this
repo while writing the macro_commodity_betas migration. B-trees are traversable
in both directions, so ORDER BY detected_at DESC uses an ascending index fine.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e9d2c15a83'
down_revision: Union[str, Sequence[str], None] = 'a1f7c3d90b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'macro_event_detections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('driver', sa.String(length=64), nullable=True),
        sa.Column('trigger_metric', sa.String(length=64), nullable=True),
        sa.Column('trigger_value', sa.Float(), nullable=True),
        sa.Column('trigger_threshold', sa.Float(), nullable=True),
        sa.Column('triggered', sa.Boolean(), nullable=False),
        sa.Column('escalated', sa.Boolean(), nullable=False),
        sa.Column('raw_metrics_json', sa.Text(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_macro_event_detections_detected_at'),
        'macro_event_detections',
        ['detected_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_macro_event_detections_source'), 'macro_event_detections', ['source'], unique=False
    )
    op.create_index(
        op.f('ix_macro_event_detections_driver'), 'macro_event_detections', ['driver'], unique=False
    )
    op.create_index(
        op.f('ix_macro_event_detections_triggered'),
        'macro_event_detections',
        ['triggered'],
        unique=False,
    )
    op.create_index(
        'ix_macro_event_detections_source_detected_at',
        'macro_event_detections',
        ['source', 'detected_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_macro_event_detections_source_detected_at', table_name='macro_event_detections'
    )
    op.drop_index(op.f('ix_macro_event_detections_triggered'), table_name='macro_event_detections')
    op.drop_index(op.f('ix_macro_event_detections_driver'), table_name='macro_event_detections')
    op.drop_index(op.f('ix_macro_event_detections_source'), table_name='macro_event_detections')
    op.drop_index(
        op.f('ix_macro_event_detections_detected_at'), table_name='macro_event_detections'
    )
    op.drop_table('macro_event_detections')
