from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.model.chart_of_accounts import AccountType


class AccountCreate(BaseModel):
    code: str
    name: str
    account_type: AccountType
    category: str | None = None
    currency: str = "BRL"
    custom_data: dict | None = None


class AccountProvision(BaseModel):
    template: str | None = None
    accounts: list[AccountCreate] | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    custom_data: dict | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_id: UUID
    code: str
    name: str
    account_type: AccountType
    category: str | None
    currency: str
    current_balance: Decimal
    balance_version: int
    last_entry_at: datetime | None
    parent_account_id: UUID | None
    enabled: bool
    custom_data: dict | None
    created_at: datetime
    updated_at: datetime | None
