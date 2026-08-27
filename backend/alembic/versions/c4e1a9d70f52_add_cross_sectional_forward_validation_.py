"""add cross sectional forward validation registrations table

Revision ID: c4e1a9d70f52
Revises: 7b7a98d4b443
Create Date: 2026-08-27 02:10:00.000000

A NEW table, deliberately, rather than columns added to
forward_validation_registrations — see
app/models/cross_sectional_forward_validation.py's class docstring for the
three reasons, of which the decisive one is that the live pairs/momentum
runner's query (SELECT ... FROM forward_validation_registrations WHERE
status IN (...)) must stay correct WITHOUT gaining a discriminator filter it
never had. A separate table makes that structural: the existing table is not
touched by this migration at all.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e1a9d70f52'
down_revision: Union[str, Sequence[str], None] = '7b7a98d4b443'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'cross_sectional_forward_validation_registrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('family_key', sa.String(length=50), nullable=False),
        sa.Column('pattern_id', sa.String(length=80), nullable=False),
        sa.Column('module_path', sa.String(length=160), nullable=False),
        sa.Column('spec_family', sa.String(length=60), nullable=False),
        sa.Column('citation', sa.Text(), nullable=False),
        sa.Column('universe_rule', sa.Text(), nullable=False),
        sa.Column('family_n_trials', sa.Integer(), nullable=False),
        sa.Column('config_hash', sa.String(length=64), nullable=False),
        sa.Column('spec_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('config_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('spec_snapshot_json', sa.Text(), nullable=False),
        sa.Column('config_snapshot_json', sa.Text(), nullable=False),
        sa.Column('registration_rationale', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('min_trading_days_threshold', sa.Integer(), nullable=False),
        sa.Column('n_forward_trading_days', sa.Integer(), nullable=False),
        sa.Column('n_formations', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.Date(), nullable=False),
        sa.Column('last_processed_date', sa.Date(), nullable=True),
        sa.Column('last_ticked_at', sa.DateTime(), nullable=True),
        sa.Column('graduated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('carry_state_json', sa.Text(), nullable=False),
        sa.Column('day_results_json', sa.Text(), nullable=False),
        sa.Column('formations_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'config_hash', name='uq_xs_forward_validation_user_config')
    )
    op.create_index(
        op.f('ix_cross_sectional_forward_validation_registrations_family_key'),
        'cross_sectional_forward_validation_registrations', ['family_key'], unique=False,
    )
    op.create_index(
        op.f('ix_cross_sectional_forward_validation_registrations_pattern_id'),
        'cross_sectional_forward_validation_registrations', ['pattern_id'], unique=False,
    )
    op.create_index(
        op.f('ix_cross_sectional_forward_validation_registrations_status'),
        'cross_sectional_forward_validation_registrations', ['status'], unique=False,
    )
    op.create_index(
        op.f('ix_cross_sectional_forward_validation_registrations_user_id'),
        'cross_sectional_forward_validation_registrations', ['user_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_cross_sectional_forward_validation_registrations_user_id'),
        table_name='cross_sectional_forward_validation_registrations',
    )
    op.drop_index(
        op.f('ix_cross_sectional_forward_validation_registrations_status'),
        table_name='cross_sectional_forward_validation_registrations',
    )
    op.drop_index(
        op.f('ix_cross_sectional_forward_validation_registrations_pattern_id'),
        table_name='cross_sectional_forward_validation_registrations',
    )
    op.drop_index(
        op.f('ix_cross_sectional_forward_validation_registrations_family_key'),
        table_name='cross_sectional_forward_validation_registrations',
    )
    op.drop_table('cross_sectional_forward_validation_registrations')
