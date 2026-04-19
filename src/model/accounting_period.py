import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from src.model.base_model import BaseModel


class PeriodStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    locked = "locked"


class AccountingPeriod(BaseModel):
    __tablename__ = "accounting_periods"

    period_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    status: Mapped[PeriodStatus] = mapped_column(Enum(PeriodStatus), nullable=False, default=PeriodStatus.open)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
