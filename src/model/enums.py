import enum


class AccountTemplate(str, enum.Enum):
    MERCHANT = "MERCHANT"
    CUSTOMER = "CUSTOMER"
    OPERATOR = "OPERATOR"
    PLATFORM = "PLATFORM"
    BAAS_CUSTOMER = "BAAS_CUSTOMER"


class AccountType(str, enum.Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"
    EQUITY = "EQUITY"


class ClearingNetwork(str, enum.Enum):
    STR = "STR"
    CIP_PIX = "CIP-PIX"
    COMPE = "COMPE"


class Currency(str, enum.Enum):
    BRL = "BRL"
    USD = "USD"


class PeriodStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"


class ReceivableStatus(str, enum.Enum):
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"
