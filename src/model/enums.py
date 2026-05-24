import enum


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
