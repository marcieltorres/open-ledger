import enum


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    VOIDED = "VOIDED"


class TransactionType(str, enum.Enum):
    SALE = "SALE"
    ANTICIPATION = "ANTICIPATION"
    SETTLEMENT = "SETTLEMENT"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER = "TRANSFER"
    REVERSAL = "REVERSAL"


class EntryType(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class ReferenceType(str, enum.Enum):
    RECEIVABLE = "RECEIVABLE"
    TRANSACTION = "TRANSACTION"


class ClearingNetwork(str, enum.Enum):
    STR = "STR"
    CIP_PIX = "CIP-PIX"
    COMPE = "COMPE"


class AccountTemplate(str, enum.Enum):
    MERCHANT = "MERCHANT"
    CUSTOMER = "CUSTOMER"
    OPERATOR = "OPERATOR"
    PLATFORM = "PLATFORM"
    BAAS_CUSTOMER = "BAAS_CUSTOMER"


class ReceivableStatus(str, enum.Enum):
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class Currency(str, enum.Enum):
    BRL = "BRL"
    USD = "USD"
