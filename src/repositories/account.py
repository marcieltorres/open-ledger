from uuid import UUID

from sqlalchemy.orm import Session

from src.model.chart_of_accounts import ChartOfAccounts
from src.repositories.base import BaseRepository


class AccountRepository(BaseRepository[ChartOfAccounts]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ChartOfAccounts)

    def get_by_entity(self, entity_id: UUID) -> list[ChartOfAccounts]:
        return self.db.query(ChartOfAccounts).filter(ChartOfAccounts.entity_id == entity_id).all()

    def get_by_entity_and_code(self, entity_id: UUID, code: str) -> ChartOfAccounts | None:
        return (
            self.db.query(ChartOfAccounts)
            .filter(ChartOfAccounts.entity_id == entity_id, ChartOfAccounts.code == code)
            .first()
        )
