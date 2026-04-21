"""receivables

Revision ID: a1b2c3d4e5f6
Revises: 5d2821f9e0cc
Create Date: 2026-04-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5d2821f9e0cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'receivables',
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('transaction_id', sa.UUID(), nullable=False),
        sa.Column('gross_amount', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('net_amount', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('fee_amount', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('expected_settlement_date', sa.Date(), nullable=True),
        sa.Column('actual_settlement_date', sa.Date(), nullable=True),
        sa.Column('custom_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id']),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id'),
    )
    op.create_index('idx_recv_entity', 'receivables', ['entity_id', 'status'])
    op.create_index('idx_recv_txn', 'receivables', ['transaction_id'])
    op.create_index('idx_recv_status', 'receivables', ['status', 'expected_settlement_date'])


def downgrade() -> None:
    op.drop_index('idx_recv_status', table_name='receivables')
    op.drop_index('idx_recv_txn', table_name='receivables')
    op.drop_index('idx_recv_entity', table_name='receivables')
    op.drop_table('receivables')
