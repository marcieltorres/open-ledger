from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from src.model.transaction import Transaction
from src.model.transaction_entry import TransactionEntry
from src.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Transaction)

    def get_by_entity(self, entity_id: UUID, skip: int = 0, limit: int = 100) -> list[Transaction]:
        return (
            self.db.query(Transaction)
            .filter(Transaction.entity_id == entity_id)
            .order_by(Transaction.effective_date.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_idempotency_key(self, key: str) -> Transaction | None:
        return self.db.query(Transaction).filter(Transaction.idempotency_key == key).first()

    def get_with_entries(self, entity_id: UUID, txn_id: UUID) -> Transaction | None:
        return (
            self.db.query(Transaction)
            .options(joinedload(Transaction.entries))
            .filter(Transaction.entity_id == entity_id, Transaction.id == txn_id)
            .first()
        )


class TransactionEntryRepository(BaseRepository[TransactionEntry]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, TransactionEntry)

    def get_by_transaction(self, transaction_id: UUID) -> list[TransactionEntry]:
        return self.db.query(TransactionEntry).filter(TransactionEntry.transaction_id == transaction_id).all()
