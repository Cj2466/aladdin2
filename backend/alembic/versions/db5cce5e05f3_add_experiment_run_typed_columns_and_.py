"""add experiment run typed columns and backfill

Revision ID: db5cce5e05f3
Revises: 5a658cb38b77
Create Date: 2026-08-23 14:47:23.907835

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db5cce5e05f3'
down_revision: Union[str, Sequence[str], None] = '5a658cb38b77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    with op.batch_alter_table('experiment_runs') as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('fit_window_days', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('entry_z', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('exit_z', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('cost_bps', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('lookback_years', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('num_trades', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('sharpe_net', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('sharpe_gross', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('max_drawdown_net', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('win_rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('sweep_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('configurations_tested', sa.Integer(), nullable=False, server_default='1')
        )
        batch_op.create_index(
            batch_op.f('ix_experiment_runs_sweep_id'), ['sweep_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_experiment_runs_sweep_id_sweep_jobs', 'sweep_jobs', ['sweep_id'], ['id']
        )

    # Backfill the 4 pre-existing rows by parsing their already-computed
    # results_json — pure JSON parsing, no recomputation — before
    # tightening the always-present columns to NOT NULL below.
    experiment_runs = sa.table(
        'experiment_runs',
        sa.column('id', sa.Integer),
        sa.column('results_json', sa.Text),
        sa.column('status', sa.String),
        sa.column('fit_window_days', sa.Integer),
        sa.column('entry_z', sa.Float),
        sa.column('exit_z', sa.Float),
        sa.column('cost_bps', sa.Float),
        sa.column('lookback_years', sa.Integer),
        sa.column('num_trades', sa.Integer),
        sa.column('sharpe_net', sa.Float),
        sa.column('sharpe_gross', sa.Float),
        sa.column('max_drawdown_net', sa.Float),
        sa.column('win_rate', sa.Float),
    )
    rows = bind.execute(sa.select(experiment_runs.c.id, experiment_runs.c.results_json)).fetchall()
    for row_id, results_json in rows:
        payload = json.loads(results_json)
        bind.execute(
            experiment_runs.update()
            .where(experiment_runs.c.id == row_id)
            .values(
                status=payload['status'],
                fit_window_days=payload['fit_window_days'],
                entry_z=payload['entry_z'],
                exit_z=payload['exit_z'],
                cost_bps=payload['cost_bps'],
                lookback_years=payload['lookback_years'],
                num_trades=payload['num_trades'],
                sharpe_net=payload.get('sharpe_net'),
                sharpe_gross=payload.get('sharpe_gross'),
                max_drawdown_net=payload.get('max_drawdown_net'),
                win_rate=payload.get('win_rate'),
            )
        )

    with op.batch_alter_table('experiment_runs') as batch_op:
        batch_op.alter_column('status', existing_type=sa.String(length=20), nullable=False)
        batch_op.alter_column('fit_window_days', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('entry_z', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('exit_z', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('cost_bps', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('lookback_years', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('num_trades', existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('experiment_runs') as batch_op:
        batch_op.drop_index(batch_op.f('ix_experiment_runs_sweep_id'))
        batch_op.drop_column('configurations_tested')
        batch_op.drop_column('sweep_id')
        batch_op.drop_column('win_rate')
        batch_op.drop_column('max_drawdown_net')
        batch_op.drop_column('sharpe_gross')
        batch_op.drop_column('sharpe_net')
        batch_op.drop_column('num_trades')
        batch_op.drop_column('lookback_years')
        batch_op.drop_column('cost_bps')
        batch_op.drop_column('exit_z')
        batch_op.drop_column('entry_z')
        batch_op.drop_column('fit_window_days')
        batch_op.drop_column('status')
