"""period_status_varchar

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert accounting_periods.status from PostgreSQL ENUM to VARCHAR(20) with UPPERCASE values."""
    op.execute(
        """
        ALTER TABLE accounting_periods
            ALTER COLUMN status TYPE VARCHAR(20) USING upper(status::text)
        """
    )
    op.execute('DROP TYPE IF EXISTS periodstatus')
    op.drop_index('idx_periods_status', table_name='accounting_periods')
    op.create_index(
        'idx_periods_status',
        'accounting_periods',
        ['status'],
        postgresql_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    """Revert accounting_periods.status from VARCHAR(20) back to PostgreSQL ENUM with lowercase values."""
    op.execute("CREATE TYPE periodstatus AS ENUM ('open', 'closed', 'locked')")
    op.execute(
        """
        ALTER TABLE accounting_periods
            ALTER COLUMN status TYPE periodstatus USING lower(status)::periodstatus
        """
    )
    op.drop_index('idx_periods_status', table_name='accounting_periods')
    op.create_index(
        'idx_periods_status',
        'accounting_periods',
        ['status'],
        postgresql_where=sa.text("status = 'open'"),
    )
