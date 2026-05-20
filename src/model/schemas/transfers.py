from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.model.schemas.transactions import TransactionResponse


class TransferCreate(BaseModel):
    sender_entity_id: UUID
    receiver_entity_id: UUID
    amount: Decimal
    currency: str = "BRL"
    effective_date: date
    description: str | None = None
    custom_data: dict | None = None


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sender_transaction: TransactionResponse
    receiver_transaction: TransactionResponse
