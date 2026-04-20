from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.model.base_model import BaseModel

if TYPE_CHECKING:
    from src.model.transaction_entry import TransactionEntry


class Transaction(BaseModel):
    __tablename__ = "transactions"

    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="committed")
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_data: Mapped[dict | None] = mapped_column("custom_data", JSONB, nullable=True)

    entries: Mapped[list[TransactionEntry]] = relationship("TransactionEntry", lazy="select")
