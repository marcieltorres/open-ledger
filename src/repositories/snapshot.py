from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from src.model.account_balance_snapshot import AccountBalanceSnapshot
from src.repositories.base import BaseRepository


class SnapshotRepository(BaseRepository[AccountBalanceSnapshot]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AccountBalanceSnapshot)

    def get_latest_before(self, account_id: UUID, before_date: date) -> AccountBalanceSnapshot | None:
        return (
            self.db.query(AccountBalanceSnapshot)
            .filter(
                AccountBalanceSnapshot.account_id == account_id,
                AccountBalanceSnapshot.snapshot_date < before_date,
            )
            .order_by(AccountBalanceSnapshot.snapshot_date.desc())
            .first()
        )
