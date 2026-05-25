from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from src.exceptions.entity import EntityNotFoundError
from src.model.chart_of_accounts import ChartOfAccounts
from src.model.entity import Entity
from src.model.enums import AccountType, EntryType, TransactionStatus
from src.model.schemas.statement import (
    BalanceBreakdownItem,
    EntityBalanceResponse,
    MovementLine,
    StatementEntry,
    StatementPeriod,
    StatementResponse,
    StatementSummary,
)
from src.model.transaction import Transaction
from src.model.transaction_entry import TransactionEntry
from src.repositories.account import AccountRepository
from src.repositories.base import BaseRepository
from src.repositories.snapshot import SnapshotRepository


def _asset_delta(account_type: str, entry_type: str, amount: Decimal) -> Decimal:
    """Returns net asset position change: only asset accounts count, debit=+, credit=-."""
    if account_type != AccountType.ASSET:
        return Decimal(0)
    return amount if entry_type == EntryType.DEBIT else -amount


class StatementService:
    def __init__(self, session: Session) -> None:
        self._snapshot_repo = SnapshotRepository(session)
        self._account_repo = AccountRepository(session)
        self._entity_repo: BaseRepository[Entity] = BaseRepository(session, Entity)
        self._session = session

    def _require_entity(self, entity_id: UUID) -> None:
        if not self._entity_repo.exists(entity_id):
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")

    def _opening_balance_for_account(self, account: ChartOfAccounts, start_date: date) -> Decimal:
        if account.account_type != AccountType.ASSET:
            return Decimal(0)

        snapshot = self._snapshot_repo.get_latest_before(account.id, start_date)
        if snapshot is not None:
            return snapshot.balance

        entries_before = (
            self._session.query(TransactionEntry)
            .join(Transaction, TransactionEntry.transaction_id == Transaction.id)
            .filter(
                TransactionEntry.account_id == account.id,
                Transaction.effective_date < start_date,
                Transaction.status == TransactionStatus.COMMITTED,
            )
            .all()
        )
        total = Decimal(0)
        for entry in entries_before:
            total += _asset_delta(account.account_type, entry.entry_type, entry.amount)
        return total

    def get_entity_balance(self, entity_id: UUID, as_of: date | None) -> EntityBalanceResponse:
        self._require_entity(entity_id)
        accounts = self._account_repo.get_by_entity(entity_id)
        asset_accounts = [a for a in accounts if a.account_type == AccountType.ASSET]
        effective_date = as_of or date.today()

        breakdown = [
            BalanceBreakdownItem(
                code=a.code,
                name=a.name,
                balance=a.current_balance if as_of is None else self._opening_balance_for_account(a, as_of),
            )
            for a in asset_accounts
        ]

        return EntityBalanceResponse(
            entity_id=entity_id,
            balance=sum((item.balance for item in breakdown), Decimal(0)),
            as_of=effective_date,
            breakdown=breakdown,
        )

    def build_statement(self, entity_id: UUID, start_date: date, end_date: date) -> StatementResponse:
        self._require_entity(entity_id)
        accounts = self._account_repo.get_by_entity(entity_id)
        account_map: dict[UUID, ChartOfAccounts] = {a.id: a for a in accounts}

        opening_balance = sum(
            (self._opening_balance_for_account(a, start_date) for a in accounts),
            Decimal(0),
        )

        rows = (
            self._session.query(TransactionEntry, Transaction)
            .join(Transaction, TransactionEntry.transaction_id == Transaction.id)
            .filter(
                TransactionEntry.account_id.in_(account_map.keys()),
                Transaction.effective_date >= start_date,
                Transaction.effective_date <= end_date,
                Transaction.status == TransactionStatus.COMMITTED,
            )
            .order_by(Transaction.effective_date, Transaction.id)
            .all()
        )

        txn_entries: dict[UUID, tuple[Transaction, list[TransactionEntry]]] = {}
        for entry, txn in rows:
            if txn.id not in txn_entries:
                txn_entries[txn.id] = (txn, [])
            txn_entries[txn.id][1].append(entry)

        running = opening_balance
        total_in = Decimal(0)
        total_out = Decimal(0)
        statement_entries: list[StatementEntry] = []

        for _, (txn, entries) in txn_entries.items():
            movements = []
            txn_delta = Decimal(0)
            for entry in entries:
                account = account_map[entry.account_id]
                movements.append(
                    MovementLine(
                        account=account.name,
                        entry_type=entry.entry_type,
                        amount=entry.amount,
                    )
                )
                delta = _asset_delta(account.account_type, entry.entry_type, entry.amount)
                txn_delta += delta

            running += txn_delta
            if txn_delta > 0:
                total_in += txn_delta
            elif txn_delta < 0:
                total_out += abs(txn_delta)

            statement_entries.append(
                StatementEntry(
                    date=txn.effective_date,
                    transaction_id=txn.id,
                    type=txn.transaction_type,
                    description=txn.description or f"{txn.transaction_type} #{txn.id}",
                    movements=movements,
                    balance_after=running,
                )
            )

        return StatementResponse(
            entity_id=entity_id,
            period=StatementPeriod(start_date=start_date, end_date=end_date),
            summary=StatementSummary(
                opening_balance=opening_balance,
                total_in=total_in,
                total_out=total_out,
                closing_balance=running,
            ),
            entries=statement_entries,
        )
