from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.model.base_model import BaseModel


class AccountBalanceSnapshot(BaseModel):
    __tablename__ = "account_balance_snapshots"

    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=6), nullable=False)
