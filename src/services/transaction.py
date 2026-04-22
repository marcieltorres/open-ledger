from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.exceptions.transaction import (
    AccountCodeNotFoundError,
    CurrencyMismatchError,
    DoubleEntryImbalanceError,
    InvalidStatusTransitionError,
    TransactionNotFoundError,
)
from src.model.chart_of_accounts import ChartOfAccounts
from src.model.constants.account_codes import (
    ACC_ANTICIPATION_FEE,
    ACC_RECEIVABLES,
    ACC_RECEIVABLES_ANTICIPATED,
    WORLD_ACCOUNTS,
)
from src.model.schemas.anticipations import AnticipationCreate
from src.model.schemas.deposits import DepositCreate
from src.model.schemas.reversals import ReversalCreate
from src.model.schemas.settlements import SettlementCreate
from src.model.schemas.transactions import TransactionCreate, TransactionEntryCreate
from src.model.schemas.withdrawals import WithdrawalCreate
from src.model.transaction import Transaction
from src.model.transaction_entry import TransactionEntry
from src.repositories.account import AccountRepository
from src.repositories.transaction import TransactionRepository
from src.services.period import PeriodService
from src.services.receivable import ReceivableService

_PRECISION = Decimal("0.01")


def _world_account(clearing_network: str | None) -> str:
    return WORLD_ACCOUNTS.get(clearing_network, "9.9.999")


class TransactionService:
    def __init__(self, session: Session) -> None:
        self._repo = TransactionRepository(session)
        self._account_repo = AccountRepository(session)
        self._period_svc = PeriodService(session)
        self._session = session

    def _round_amount(self, value: Decimal) -> Decimal:
        return value.quantize(_PRECISION, rounding=ROUND_HALF_UP)

    def _compute_delta(self, account_type: str, entry_type: str, amount: Decimal) -> Decimal:
        """Returns the delta to apply to current_balance based on account and entry type."""
        increases_on_debit = account_type in ("asset", "expense")
        if increases_on_debit:
            return amount if entry_type == "debit" else -amount
        return -amount if entry_type == "debit" else amount

    def _validate_double_entry(self, entries: list[TransactionEntryCreate]) -> None:
        """Raises DoubleEntryImbalanceError if Σdebits ≠ Σcredits per currency."""
        by_currency: dict[str, dict[str, Decimal]] = {}
        for entry in entries:
            bucket = by_currency.setdefault(entry.currency, {"debit": Decimal(0), "credit": Decimal(0)})
            bucket[entry.entry_type] += entry.amount
        for currency, totals in by_currency.items():
            if totals["debit"] != totals["credit"]:
                raise DoubleEntryImbalanceError(currency, totals["debit"], totals["credit"])

    def _apply_balance_updates(
        self,
        entries: list[TransactionEntryCreate],
        accounts: list[ChartOfAccounts],
    ) -> None:
        """Applies balance deltas with SELECT FOR UPDATE per account. Must be called inside an open DB transaction."""
        for entry, account in zip(entries, accounts):
            locked = self._session.execute(
                select(ChartOfAccounts).where(ChartOfAccounts.id == account.id).with_for_update()
            ).scalar_one()
            locked.current_balance += self._compute_delta(locked.account_type, entry.entry_type, entry.amount)
            locked.balance_version += 1
            locked.last_entry_at = datetime.now(timezone.utc)

    def post(self, entity_id: UUID, payload: TransactionCreate, idempotency_key: str) -> Transaction:
        existing = self._repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        self._period_svc.validate_open(payload.effective_date)

        accounts = []
        for entry in payload.entries:
            account = self._account_repo.get_by_entity_and_code(entity_id, entry.account_code)
            if account is None:
                raise AccountCodeNotFoundError(
                    f"Account code '{entry.account_code}' not found for entity '{entity_id}'"
                )
            accounts.append(account)

        self._validate_double_entry(payload.entries)

        for entry, account in zip(payload.entries, accounts):
            if account.currency != entry.currency:
                raise CurrencyMismatchError(entry.account_code, account.currency, entry.currency)

        transaction = Transaction(
            entity_id=entity_id,
            idempotency_key=idempotency_key,
            status="committed",
            **payload.model_dump(exclude={"entries", "receivable"}),
        )
        self._session.add(transaction)
        self._session.flush()

        for entry, account in zip(payload.entries, accounts):
            self._session.add(TransactionEntry(
                transaction_id=transaction.id,
                account_id=account.id,
                **entry.model_dump(exclude={"account_code"}),
            ))

        if transaction.status != "pending":
            self._apply_balance_updates(payload.entries, accounts)

        if payload.receivable is not None:
            recv_svc = ReceivableService(self._session)
            recv_svc.create(entity_id, transaction.id, payload.receivable)

        return transaction

    def get_by_id(self, entity_id: UUID, transaction_id: UUID) -> Transaction:
        transaction = self._repo.get_with_entries(entity_id, transaction_id)
        if transaction is None:
            raise TransactionNotFoundError(f"Transaction '{transaction_id}' not found for entity '{entity_id}'")
        return transaction

    def list_by_entity(self, entity_id: UUID, skip: int = 0, limit: int = 100) -> list[Transaction]:
        return self._repo.get_by_entity(entity_id, skip=skip, limit=limit)

    def anticipate(self, entity_id: UUID, payload: AnticipationCreate, idempotency_key: str) -> Transaction:
        entries = [
            TransactionEntryCreate(
                account_code=ACC_RECEIVABLES_ANTICIPATED, entry_type="debit", amount=payload.receivable_amount
            ),
            TransactionEntryCreate(
                account_code=ACC_RECEIVABLES, entry_type="credit", amount=payload.receivable_amount
            ),
            TransactionEntryCreate(
                account_code=ACC_ANTICIPATION_FEE, entry_type="debit", amount=payload.anticipation_fee
            ),
            TransactionEntryCreate(
                account_code=ACC_RECEIVABLES_ANTICIPATED, entry_type="credit", amount=payload.anticipation_fee
            ),
        ]
        txn_create = TransactionCreate(
            transaction_type="anticipation",
            effective_date=payload.effective_date,
            entries=entries,
            reference_id=str(payload.receivable_id),
            reference_type="receivable",
            custom_data=payload.custom_data,
        )
        return self.post(entity_id, txn_create, idempotency_key)

    def settle(self, entity_id: UUID, payload: SettlementCreate, idempotency_key: str) -> Transaction:
        world_code = _world_account(payload.clearing_network)
        entries = [
            TransactionEntryCreate(account_code=world_code, entry_type="debit", amount=payload.amount),
            TransactionEntryCreate(
                account_code=ACC_RECEIVABLES_ANTICIPATED, entry_type="credit", amount=payload.amount
            ),
        ]
        txn_create = TransactionCreate(
            transaction_type="settlement",
            effective_date=payload.settlement_date,
            entries=entries,
            reference_id=str(payload.receivable_id),
            reference_type="receivable",
            custom_data=payload.custom_data,
        )
        txn = self.post(entity_id, txn_create, idempotency_key)
        ReceivableService(self._session).settle(entity_id, payload.receivable_id, payload.settlement_date)
        return txn

    def deposit(self, entity_id: UUID, payload: DepositCreate, idempotency_key: str) -> Transaction:
        world_code = _world_account(payload.clearing_network)
        entries = [
            TransactionEntryCreate(
                account_code=ACC_RECEIVABLES, entry_type="debit", amount=payload.amount, currency=payload.currency
            ),
            TransactionEntryCreate(
                account_code=world_code, entry_type="credit", amount=payload.amount, currency=payload.currency
            ),
        ]
        txn_create = TransactionCreate(
            transaction_type="deposit",
            effective_date=payload.effective_date,
            entries=entries,
            custom_data=payload.custom_data,
        )
        return self.post(entity_id, txn_create, idempotency_key)

    def withdraw(self, entity_id: UUID, payload: WithdrawalCreate, idempotency_key: str) -> Transaction:
        world_code = _world_account(payload.clearing_network)
        entries = [
            TransactionEntryCreate(
                account_code=world_code, entry_type="debit", amount=payload.amount, currency=payload.currency
            ),
            TransactionEntryCreate(
                account_code=ACC_RECEIVABLES, entry_type="credit", amount=payload.amount, currency=payload.currency
            ),
        ]
        txn_create = TransactionCreate(
            transaction_type="withdrawal",
            effective_date=payload.effective_date,
            entries=entries,
            custom_data=payload.custom_data,
        )
        return self.post(entity_id, txn_create, idempotency_key)

    def void(self, entity_id: UUID, txn_id: UUID) -> Transaction:
        transaction = self._repo.get_with_entries(entity_id, txn_id)
        if transaction is None:
            raise TransactionNotFoundError(f"Transaction '{txn_id}' not found for entity '{entity_id}'")
        if transaction.status != "pending":
            raise InvalidStatusTransitionError(
                f"Cannot void transaction with status '{transaction.status}'; only 'pending' transactions can be voided"
            )
        transaction.status = "voided"
        return transaction

    def reverse(self, entity_id: UUID, txn_id: UUID, payload: ReversalCreate, idempotency_key: str) -> Transaction:
        original = self._repo.get_with_entries(entity_id, txn_id)
        if original is None:
            raise TransactionNotFoundError(f"Transaction '{txn_id}' not found for entity '{entity_id}'")

        mirrored = [
            TransactionEntryCreate(
                account_code=entry.account.code,
                entry_type="credit" if entry.entry_type == "debit" else "debit",
                amount=entry.amount,
                currency=entry.currency,
            )
            for entry in original.entries
        ]
        txn_create = TransactionCreate(
            transaction_type="reversal",
            effective_date=date.today(),
            entries=mirrored,
            reference_id=str(txn_id),
            reference_type="transaction",
            description=payload.reason,
            custom_data=payload.custom_data,
        )
        reversal = self.post(entity_id, txn_create, idempotency_key)

        if original.receivable is not None:
            ReceivableService(self._session).cancel(entity_id, original.receivable.id)

        return reversal
