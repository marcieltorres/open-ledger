from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from src.model.enums import ClearingNetwork


class DepositCreate(BaseModel):
    amount: Decimal
    currency: str = "BRL"
    effective_date: date
    clearing_network: ClearingNetwork | None = None
    custom_data: dict | None = None
