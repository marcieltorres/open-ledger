class TransactionNotFoundError(Exception):
    pass


class CurrencyMismatchError(Exception):
    def __init__(self, account_code: str, account_currency: str, entry_currency: str) -> None:
        super().__init__(
            f"Currency mismatch for account '{account_code}': "
            f"account currency is {account_currency} but entry currency is {entry_currency}"
        )


class DoubleEntryImbalanceError(Exception):
    def __init__(self, currency: str, total_debit, total_credit) -> None:
        super().__init__(
            f"Imbalanced entries for currency {currency}: "
            f"debits={total_debit}, credits={total_credit}"
        )


class IdempotencyConflictError(Exception):
    pass


class AccountCodeNotFoundError(Exception):
    pass


class InvalidStatusTransitionError(Exception):
    pass
