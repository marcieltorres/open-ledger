"""accounting_periods

Revision ID: 3b5d7e9c1f0a
Revises: f0e0b682daf3
Create Date: 2026-04-19 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '3b5d7e9c1f0a'
down_revision: Union[str, None] = 'f0e0b682daf3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'accounting_periods',
        sa.Column('period_date', sa.Date(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('open', 'closed', 'locked', name='periodstatus'),
            nullable=False,
        ),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_by', sa.String(), nullable=True),
        sa.Column('locked_by', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id'),
        sa.UniqueConstraint('period_date', name='uq_accounting_periods_date'),
    )
    op.create_index(
        'idx_periods_status',
        'accounting_periods',
        ['status'],
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index('idx_periods_date', 'accounting_periods', [sa.text('period_date DESC')])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_periods_date', table_name='accounting_periods')
    op.drop_index('idx_periods_status', table_name='accounting_periods')
    op.drop_table('accounting_periods')
    op.execute('DROP TYPE IF EXISTS periodstatus')
