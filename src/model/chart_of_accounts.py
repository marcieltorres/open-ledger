import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.model.base_model import BaseModel


class AccountType(str, enum.Enum):
    asset = "asset"
    liability = "liability"
    revenue = "revenue"
    expense = "expense"
    equity = "equity"


class ChartOfAccounts(BaseModel):
    __tablename__ = "chart_of_accounts"

    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=6), nullable=False, default=Decimal("0")
    )
    balance_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_entry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_account_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    custom_data: Mapped[dict | None] = mapped_column("custom_data", JSONB, nullable=True)
