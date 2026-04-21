from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.model.base_model import BaseModel


class ReceivableStatus(str, enum.Enum):
    pending = "pending"
    settled = "settled"
    cancelled = "cancelled"


class Receivable(BaseModel):
    __tablename__ = "receivables"

    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    expected_settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    custom_data: Mapped[dict | None] = mapped_column("custom_data", JSONB, nullable=True)
