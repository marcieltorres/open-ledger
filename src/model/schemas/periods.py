from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.model.accounting_period import PeriodStatus


class PeriodCreate(BaseModel):
    period_date: date
    notes: str | None = None


class PeriodCloseRequest(BaseModel):
    closed_by: str
    notes: str | None = None


class PeriodLockRequest(BaseModel):
    locked_by: str


class PeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    period_date: date
    status: PeriodStatus
    opened_at: datetime
    closed_at: datetime | None
    locked_at: datetime | None
    closed_by: str | None
    locked_by: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime | None
