from uuid import UUID

from sqlalchemy.orm import Session

from src.model.receivable import Receivable
from src.repositories.base import BaseRepository


class ReceivableRepository(BaseRepository[Receivable]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Receivable)

    def get_by_entity(self, entity_id: UUID, status: str | None = None) -> list[Receivable]:
        q = self.db.query(Receivable).filter(Receivable.entity_id == entity_id)
        if status is not None:
            q = q.filter(Receivable.status == status)
        return q.order_by(Receivable.created_at.desc()).all()

    def get_by_entity_and_id(self, entity_id: UUID, receivable_id: UUID) -> Receivable | None:
        return self.db.query(Receivable).filter(
            Receivable.entity_id == entity_id,
            Receivable.id == receivable_id,
        ).first()
