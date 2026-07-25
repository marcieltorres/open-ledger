"""Scoped seed cleanup: deletes only entities carrying the seed prefix and periods it annotated."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.model.account_balance_snapshot import AccountBalanceSnapshot
from src.model.accounting_period import AccountingPeriod
from src.model.chart_of_accounts import ChartOfAccounts
from src.model.entity import Entity
from src.model.receivable import Receivable
from src.model.transaction import Transaction
from src.model.transaction_entry import TransactionEntry

_NO_SYNC = {"synchronize_session": False}


def wipe(session: Session, entity_prefix: str, period_note_prefix: str) -> dict[str, int]:
    """Deletes seed data in FK order. Never TRUNCATEs — data outside the prefix survives."""
    entity_ids = select(Entity.id).where(Entity.external_id.like(f"{entity_prefix}%"))
    account_ids = select(ChartOfAccounts.id).where(ChartOfAccounts.entity_id.in_(entity_ids))
    transaction_ids = select(Transaction.id).where(Transaction.entity_id.in_(entity_ids))

    statements = [
        ("transaction_entries", delete(TransactionEntry).where(TransactionEntry.transaction_id.in_(transaction_ids))),
        ("receivables", delete(Receivable).where(Receivable.entity_id.in_(entity_ids))),
        ("transactions", delete(Transaction).where(Transaction.entity_id.in_(entity_ids))),
        (
            "account_balance_snapshots",
            delete(AccountBalanceSnapshot).where(AccountBalanceSnapshot.account_id.in_(account_ids)),
        ),
        ("chart_of_accounts", delete(ChartOfAccounts).where(ChartOfAccounts.entity_id.in_(entity_ids))),
        ("entities", delete(Entity).where(Entity.id.in_(entity_ids))),
        ("accounting_periods", delete(AccountingPeriod).where(AccountingPeriod.notes.like(f"{period_note_prefix}%"))),
    ]

    deleted = {}
    for table, statement in statements:
        deleted[table] = session.execute(statement, execution_options=_NO_SYNC).rowcount
    session.flush()
    return deleted
