from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TransactionEntryCreate(BaseModel):
    account_id: UUID
    entry_type: str
    amount: Decimal
    currency: str = "BRL"
    custom_data: dict | None = None


class TransactionEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    account_id: UUID
    entry_type: str
    amount: Decimal
    currency: str
    custom_data: dict | None
    created_at: datetime
    updated_at: datetime | None


class TransactionCreate(BaseModel):
    idempotency_key: str
    transaction_type: str
    effective_date: date
    entries: list[TransactionEntryCreate]
    reference_id: str | None = None
    reference_type: str | None = None
    description: str | None = None
    custom_data: dict | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_id: UUID
    idempotency_key: str
    status: str
    transaction_type: str
    effective_date: date
    reference_id: str | None
    reference_type: str | None
    description: str | None
    custom_data: dict | None
    created_at: datetime
    updated_at: datetime | None
