"""transactions_and_entries

Revision ID: 5d2821f9e0cc
Revises: 3b5d7e9c1f0a
Create Date: 2026-04-20 14:33:08.805930

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5d2821f9e0cc'
down_revision: Union[str, None] = '3b5d7e9c1f0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'transactions',
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('transaction_type', sa.String(length=50), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('reference_id', sa.String(length=255), nullable=True),
        sa.Column('reference_type', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('custom_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_transactions_idempotency_key'),
    )
    op.create_index('idx_txn_entity', 'transactions', ['entity_id', sa.text('effective_date DESC')])
    op.create_index('idx_txn_status', 'transactions', ['status'], postgresql_where=sa.text("status != 'committed'"))
    op.create_index('idx_txn_reference', 'transactions', ['reference_type', 'reference_id'])
    op.create_index('idx_txn_type', 'transactions', ['transaction_type'])
    op.create_index('idx_txn_entity_date', 'transactions', ['entity_id', sa.text('effective_date DESC'), 'transaction_type'])

    op.create_table(
        'transaction_entries',
        sa.Column('transaction_id', sa.UUID(), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('entry_type', sa.String(length=10), nullable=False),
        sa.Column('amount', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('custom_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['chart_of_accounts.id']),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id'),
    )
    op.create_index('idx_entry_txn', 'transaction_entries', ['transaction_id'])
    op.create_index('idx_entry_account', 'transaction_entries', ['account_id'])
    op.create_index('idx_entry_metadata', 'transaction_entries', ['custom_data'], postgresql_using='gin')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_entry_metadata', table_name='transaction_entries')
    op.drop_index('idx_entry_account', table_name='transaction_entries')
    op.drop_index('idx_entry_txn', table_name='transaction_entries')
    op.drop_table('transaction_entries')

    op.drop_index('idx_txn_entity_date', table_name='transactions')
    op.drop_index('idx_txn_type', table_name='transactions')
    op.drop_index('idx_txn_reference', table_name='transactions')
    op.drop_index('idx_txn_status', table_name='transactions')
    op.drop_index('idx_txn_entity', table_name='transactions')
    op.drop_table('transactions')
