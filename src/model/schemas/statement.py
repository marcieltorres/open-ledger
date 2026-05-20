from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AccountBalance(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: UUID
    code: str
    name: str
    account_type: str
    current_balance: Decimal


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
