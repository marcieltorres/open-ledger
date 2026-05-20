"""account_balance_snapshots

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'account_balance_snapshots',
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('balance', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['chart_of_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id'),
    )
    op.create_index(
        'idx_snapshots_account',
        'account_balance_snapshots',
        ['account_id', sa.text('snapshot_date DESC')],
    )


def downgrade() -> None:
    op.drop_index('idx_snapshots_account', table_name='account_balance_snapshots')
    op.drop_table('account_balance_snapshots')
