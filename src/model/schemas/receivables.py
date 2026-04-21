from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReceivableCreate(BaseModel):
    gross_amount: Decimal
    net_amount: Decimal
    fee_amount: Decimal
    expected_settlement_date: date | None = None
    custom_data: dict | None = None


class ReceivableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_id: UUID
    transaction_id: UUID
    gross_amount: Decimal
    net_amount: Decimal
    fee_amount: Decimal
    status: str
    expected_settlement_date: date | None
    actual_settlement_date: date | None
    custom_data: dict | None
    created_at: datetime
    updated_at: datetime | None
