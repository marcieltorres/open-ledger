"""account_type_varchar

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-24 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert chart_of_accounts.account_type from PostgreSQL ENUM to VARCHAR(20) with UPPERCASE values."""
    op.drop_index('idx_accounts_type', table_name='chart_of_accounts')
    op.execute(
        """
        ALTER TABLE chart_of_accounts
            ALTER COLUMN account_type TYPE VARCHAR(20) USING upper(account_type::text)
        """
    )
    op.execute('DROP TYPE IF EXISTS accounttype')
    op.create_index('idx_accounts_type', 'chart_of_accounts', ['account_type'])


def downgrade() -> None:
    """Revert chart_of_accounts.account_type from VARCHAR(20) back to PostgreSQL ENUM with lowercase values."""
    op.execute("CREATE TYPE accounttype AS ENUM ('asset', 'liability', 'revenue', 'expense', 'equity')")
    op.execute(
        """
        ALTER TABLE chart_of_accounts
            ALTER COLUMN account_type TYPE accounttype USING lower(account_type)::accounttype
        """
    )
    op.drop_index('idx_accounts_type', table_name='chart_of_accounts')
    op.create_index('idx_accounts_type', 'chart_of_accounts', ['account_type'])
