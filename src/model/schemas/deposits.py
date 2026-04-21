from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DepositCreate(BaseModel):
    amount: Decimal
    currency: str = "BRL"
    effective_date: date
    clearing_network: str | None = None
    custom_data: dict | None = None
