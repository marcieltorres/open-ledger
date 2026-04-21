from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from src.exceptions.receivable import InvalidReceivableStatusTransitionError, ReceivableNotFoundError
from src.model.receivable import Receivable
from src.model.schemas.receivables import ReceivableCreate
from src.repositories.receivable import ReceivableRepository

_PRECISION = Decimal("0.01")


class ReceivableService:
    def __init__(self, session: Session) -> None:
        self._repo = ReceivableRepository(session)

    def _round(self, value: Decimal) -> Decimal:
        return value.quantize(_PRECISION, rounding=ROUND_HALF_UP)

    def create(self, entity_id: UUID, transaction_id: UUID, payload: ReceivableCreate) -> Receivable:
        receivable = Receivable(
            entity_id=entity_id,
            transaction_id=transaction_id,
            gross_amount=self._round(payload.gross_amount),
            net_amount=self._round(payload.net_amount),
            fee_amount=self._round(payload.fee_amount),
            status="pending",
            expected_settlement_date=payload.expected_settlement_date,
            custom_data=payload.custom_data,
        )
        return self._repo.save(receivable)

    def settle(self, entity_id: UUID, receivable_id: UUID, actual_settlement_date: date) -> Receivable:
        receivable = self._get_for_entity(entity_id, receivable_id)
        if receivable.status != "pending":
            raise InvalidReceivableStatusTransitionError(
                f"Cannot settle receivable with status '{receivable.status}'"
            )
        receivable.status = "settled"
        receivable.actual_settlement_date = actual_settlement_date
        return receivable

    def cancel(self, entity_id: UUID, receivable_id: UUID) -> Receivable:
        receivable = self._get_for_entity(entity_id, receivable_id)
        if receivable.status != "pending":
            raise InvalidReceivableStatusTransitionError(
                f"Cannot cancel receivable with status '{receivable.status}'"
            )
        receivable.status = "cancelled"
        return receivable

    def get_by_id(self, entity_id: UUID, receivable_id: UUID) -> Receivable:
        return self._get_for_entity(entity_id, receivable_id)

    def list_by_entity(self, entity_id: UUID, status: str | None = None) -> list[Receivable]:
        return self._repo.get_by_entity(entity_id, status=status)

    def _get_for_entity(self, entity_id: UUID, receivable_id: UUID) -> Receivable:
        receivable = self._repo.get_by_entity_and_id(entity_id, receivable_id)
        if receivable is None:
            raise ReceivableNotFoundError(f"Receivable '{receivable_id}' not found for entity '{entity_id}'")
        return receivable
