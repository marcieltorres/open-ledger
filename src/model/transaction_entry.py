from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.model.base_model import BaseModel


class TransactionEntry(BaseModel):
    __tablename__ = "transaction_entries"

    transaction_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'debit' | 'credit'
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    custom_data: Mapped[dict | None] = mapped_column("custom_data", JSONB, nullable=True)
