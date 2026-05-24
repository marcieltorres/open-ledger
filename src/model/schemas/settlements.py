from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from src.model.enums import ClearingNetwork


class SettlementCreate(BaseModel):
    receivable_id: UUID
    amount: Decimal
    settlement_date: date
    clearing_network: ClearingNetwork | None = None
    custom_data: dict | None = None
