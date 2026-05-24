import enum


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    committed = "committed"
    voided = "voided"


class TransactionType(str, enum.Enum):
    sale = "sale"
    anticipation = "anticipation"
    settlement = "settlement"
    deposit = "deposit"
    withdrawal = "withdrawal"
    transfer = "transfer"
    reversal = "reversal"


class EntryType(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class ReferenceType(str, enum.Enum):
    receivable = "receivable"
    transaction = "transaction"


class ClearingNetwork(str, enum.Enum):
    STR = "STR"
    CIP_PIX = "CIP-PIX"
    COMPE = "COMPE"


class AccountTemplate(str, enum.Enum):
    merchant = "merchant"
    customer = "customer"
    operator = "operator"
    platform = "platform"
    baas_customer = "baas_customer"


class ReceivableStatus(str, enum.Enum):
    pending = "pending"
    settled = "settled"
    cancelled = "cancelled"


class Currency(str, enum.Enum):
    BRL = "BRL"
    USD = "USD"
