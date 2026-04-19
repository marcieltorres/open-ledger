"""chart_of_accounts

Revision ID: f0e0b682daf3
Revises: 7689a062042c
Create Date: 2026-04-19 11:14:48.386496

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f0e0b682daf3'
down_revision: Union[str, None] = '7689a062042c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'chart_of_accounts',
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column(
            'account_type',
            sa.Enum('asset', 'liability', 'revenue', 'expense', 'equity', name='accounttype'),
            nullable=False,
        ),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='BRL'),
        sa.Column(
            'current_balance',
            sa.Numeric(precision=20, scale=6),
            nullable=False,
            server_default='0',
        ),
        sa.Column('balance_version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_entry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('parent_account_id', sa.UUID(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('custom_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id']),
        sa.ForeignKeyConstraint(['parent_account_id'], ['chart_of_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id'),
        sa.UniqueConstraint('entity_id', 'code', name='uq_accounts_entity_code'),
    )
    op.create_index('idx_accounts_entity', 'chart_of_accounts', ['entity_id'])
    op.create_index('idx_accounts_code', 'chart_of_accounts', ['entity_id', 'code'])
    op.create_index('idx_accounts_type', 'chart_of_accounts', ['account_type'])
    op.create_index('idx_accounts_currency', 'chart_of_accounts', ['entity_id', 'currency'])
    op.create_index(
        'idx_accounts_active',
        'chart_of_accounts',
        ['entity_id'],
        postgresql_where=sa.text('enabled = true'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_accounts_active', table_name='chart_of_accounts')
    op.drop_index('idx_accounts_currency', table_name='chart_of_accounts')
    op.drop_index('idx_accounts_type', table_name='chart_of_accounts')
    op.drop_index('idx_accounts_code', table_name='chart_of_accounts')
    op.drop_index('idx_accounts_entity', table_name='chart_of_accounts')
    op.drop_table('chart_of_accounts')
    op.execute('DROP TYPE IF EXISTS accounttype')
