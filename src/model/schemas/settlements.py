from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class SettlementCreate(BaseModel):
    receivable_id: UUID
    amount: Decimal
    settlement_date: date
    clearing_network: str | None = None
    custom_data: dict | None = None
