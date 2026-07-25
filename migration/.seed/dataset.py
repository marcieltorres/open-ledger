"""Declarative seed data. No I/O — constants and derived values only."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

from src.model.constants.account_codes import ACC_RECEIVABLES
from src.model.enums import AccountTemplate, AccountType, ClearingNetwork, Currency, EntryType
from src.model.schemas.accounts import AccountCreate
from src.model.schemas.transactions import TransactionEntryCreate

SEED_PREFIX = "seed-"
PERIOD_NOTE_PREFIX = "seed:"
CUSTOM_DATA = {"source": "seed"}

ANCHOR = date.today()

ACC_REVENUE_SALES = "3.1.001"
ACC_EXPENSE_MDR = "4.1.001"
ACC_EXPENSE_PLATFORM = "4.1.002"

MDR_RATE = Decimal("0.02")
PLATFORM_FEE_RATE = Decimal("0.10")
ANTICIPATION_FEE_RATE = Decimal("0.015")

_CENTS = Decimal("0.01")

MERCHANT = "seed-merchant-01"
PLATFORM = "seed-platform-01"
OPERATOR = "seed-operator-01"
BAAS_A = "seed-baas-a"
BAAS_B = "seed-baas-b"
CUSTOMER = "seed-customer-01"

ENTITIES = [
    (MERCHANT, "Example Store Ltd", AccountTemplate.MERCHANT),
    (PLATFORM, "Example Platform", AccountTemplate.PLATFORM),
    (OPERATOR, "Example White-label Operator", AccountTemplate.OPERATOR),
    (BAAS_A, "BaaS Customer A", AccountTemplate.BAAS_CUSTOMER),
    (BAAS_B, "BaaS Customer B", AccountTemplate.BAAS_CUSTOMER),
    (CUSTOMER, "Example Buyer", AccountTemplate.CUSTOMER),
]

CLEARING_ACCOUNTS = [
    AccountCreate(code="9.9.901", name="World - STR", account_type=AccountType.EQUITY, currency=Currency.BRL),
    AccountCreate(code="9.9.902", name="World - CIP-PIX", account_type=AccountType.EQUITY, currency=Currency.BRL),
    AccountCreate(code="9.9.903", name="World - COMPE", account_type=AccountType.EQUITY, currency=Currency.BRL),
]
CLEARING_ENTITIES = [MERCHANT, BAAS_A, BAAS_B]


def offset(days: int) -> date:
    return ANCHOR + timedelta(days=days)


def money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def mdr(gross: Decimal) -> Decimal:
    return money(gross * MDR_RATE)


def platform_fee(gross: Decimal) -> Decimal:
    return money(gross * PLATFORM_FEE_RATE)


def anticipation_fee(amount: Decimal) -> Decimal:
    return money(amount * ANTICIPATION_FEE_RATE)


class Sale(NamedTuple):
    key: str
    gross: Decimal
    effective_offset: int
    settlement_offset: int

    @property
    def reference_id(self) -> str:
        return f"seed-sale-{self.key}"


SALES = [
    Sale("01", Decimal("300.00"), -20, 10),
    Sale("02", Decimal("100.00"), -10, 20),
    Sale("03", Decimal("500.00"), -5, 25),
    Sale("04", Decimal("150.00"), -3, 27),
]

ANTICIPATED_SALE = SALES[0]
REVERSED_SALE = SALES[3]

SETTLEMENT_NETWORK = ClearingNetwork.CIP_PIX
SETTLEMENT_OFFSET = -1
ANTICIPATION_OFFSET = -2
REVERSAL_REASON = "Example chargeback"


class Movement(NamedTuple):
    entity: str
    amount: Decimal
    clearing_network: ClearingNetwork
    effective_offset: int


DEPOSITS = [
    Movement(BAAS_A, Decimal("1000.00"), ClearingNetwork.STR, -15),
    Movement(BAAS_B, Decimal("500.00"), ClearingNetwork.STR, -14),
]

WITHDRAWALS = [
    Movement(BAAS_A, Decimal("250.00"), ClearingNetwork.CIP_PIX, -7),
]

TRANSFER_SENDER = BAAS_A
TRANSFER_RECEIVER = BAAS_B
TRANSFER_AMOUNT = Decimal("150.00")
TRANSFER_OFFSET = -5
TRANSFER_DESCRIPTION = "Example internal PIX transfer"

SNAPSHOT_ENTITY = BAAS_A
SNAPSHOT_ACCOUNT_CODE = ACC_RECEIVABLES
SNAPSHOT_OFFSET = -60
SNAPSHOT_BALANCE = Decimal("0")


def period_dates() -> list[date]:
    """First day of the previous and of the current month."""
    current = ANCHOR.replace(day=1)
    previous = (current - timedelta(days=1)).replace(day=1)
    return [previous, current]


def sale_entries(gross: Decimal) -> list[TransactionEntryCreate]:
    """Sale with MDR and platform fee, following .docs/open-ledger-examples.md."""
    fee_mdr = mdr(gross)
    fee_platform = platform_fee(gross)
    return [
        TransactionEntryCreate(account_code=ACC_RECEIVABLES, entry_type=EntryType.DEBIT, amount=gross),
        TransactionEntryCreate(account_code=ACC_REVENUE_SALES, entry_type=EntryType.CREDIT, amount=gross),
        TransactionEntryCreate(account_code=ACC_EXPENSE_MDR, entry_type=EntryType.DEBIT, amount=fee_mdr),
        TransactionEntryCreate(account_code=ACC_RECEIVABLES, entry_type=EntryType.CREDIT, amount=fee_mdr),
        TransactionEntryCreate(account_code=ACC_EXPENSE_PLATFORM, entry_type=EntryType.DEBIT, amount=fee_platform),
        TransactionEntryCreate(account_code=ACC_RECEIVABLES, entry_type=EntryType.CREDIT, amount=fee_platform),
    ]


def platform_entries(amount: Decimal) -> list[TransactionEntryCreate]:
    """Platform fee counterpart on the platform's own books."""
    return [
        TransactionEntryCreate(account_code=ACC_RECEIVABLES, entry_type=EntryType.DEBIT, amount=amount),
        TransactionEntryCreate(account_code=ACC_REVENUE_SALES, entry_type=EntryType.CREDIT, amount=amount),
    ]
