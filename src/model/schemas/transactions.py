from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.model.enums import Currency, EntryType, ReferenceType, TransactionStatus, TransactionType
from src.model.schemas.receivables import ReceivableCreate, ReceivableResponse


class TransactionEntryCreate(BaseModel):
    account_code: str
    entry_type: EntryType
    amount: Decimal
    currency: Currency = Currency.BRL
    custom_data: dict | None = None


class AccountRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str


class TransactionEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    entry_type: EntryType
    amount: Decimal
    currency: Currency
    custom_data: dict | None
    account: AccountRef
    created_at: datetime
    updated_at: datetime | None


class TransactionCreate(BaseModel):
    transaction_type: TransactionType
    effective_date: date
    entries: list[TransactionEntryCreate]
    reference_id: str | None = None
    reference_type: ReferenceType | None = None
    description: str | None = None
    custom_data: dict | None = None
    receivable: ReceivableCreate | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_id: UUID
    idempotency_key: str
    status: TransactionStatus
    transaction_type: TransactionType
    effective_date: date
    reference_id: str | None
    reference_type: ReferenceType | None
    description: str | None
    custom_data: dict | None
    receivable: ReceivableResponse | None = None
    created_at: datetime
    updated_at: datetime | None


class TransactionDetailResponse(TransactionResponse):
    entries: list[TransactionEntryResponse]
