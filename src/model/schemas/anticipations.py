from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class AnticipationCreate(BaseModel):
    receivable_id: UUID
    receivable_amount: Decimal
    anticipation_fee: Decimal
    effective_date: date
    custom_data: dict | None = None
