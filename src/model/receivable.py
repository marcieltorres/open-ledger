from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.model.base_model import BaseModel
from src.model.enums import ReceivableStatus


class Receivable(BaseModel):
    __tablename__ = "receivables"

    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    status: Mapped[ReceivableStatus] = mapped_column(String(20), nullable=False, default=ReceivableStatus.pending)
    expected_settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    custom_data: Mapped[dict | None] = mapped_column("custom_data", JSONB, nullable=True)
