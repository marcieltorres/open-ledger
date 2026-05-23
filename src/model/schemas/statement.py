from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, computed_field


class BalanceBreakdownItem(BaseModel):
    code: str
    name: str
    balance: Decimal

    @computed_field
    @property
    def rounded(self) -> Decimal:
        return self.balance.quantize(Decimal("0.01"))


class EntityBalanceResponse(BaseModel):
    entity_id: UUID
    balance: Decimal
    as_of: date
    breakdown: list[BalanceBreakdownItem]

    @computed_field
    @property
    def rounded(self) -> Decimal:
        return self.balance.quantize(Decimal("0.01"))


class MovementLine(BaseModel):
    account: str
    entry_type: str
    amount: Decimal


class StatementEntry(BaseModel):
    date: date
    transaction_id: UUID
    type: str
    description: str
    movements: list[MovementLine]
    balance_after: Decimal


class StatementSummary(BaseModel):
    opening_balance: Decimal
    total_in: Decimal
    total_out: Decimal
    closing_balance: Decimal


class StatementPeriod(BaseModel):
    start_date: date
    end_date: date


class StatementResponse(BaseModel):
    entity_id: UUID
    period: StatementPeriod
    summary: StatementSummary
    entries: list[StatementEntry]
