"""Seeds the local development database. Run it through `make db/seed`."""

# The sys.path bootstrap must run before the `src.*` and local module imports, because this file is
# executed as a script — `migration/.seed` is not an importable Python package.
# ruff: noqa: E402, I001

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.config.settings import settings
from src.model.account_balance_snapshot import AccountBalanceSnapshot
from src.model.chart_of_accounts import ChartOfAccounts
from src.model.entity import Entity
from src.model.receivable import Receivable
from src.model.schemas.accounts import AccountProvision
from src.model.schemas.anticipations import AnticipationCreate
from src.model.schemas.deposits import DepositCreate
from src.model.schemas.entities import EntityCreate
from src.model.schemas.periods import PeriodCreate
from src.model.schemas.reversals import ReversalCreate
from src.model.schemas.settlements import SettlementCreate
from src.model.schemas.transactions import TransactionCreate
from src.model.schemas.transfers import TransferCreate
from src.model.schemas.withdrawals import WithdrawalCreate
from src.model.transaction import Transaction
from src.model.transaction_entry import TransactionEntry
from src.repositories.account import AccountRepository
from src.repositories.base import BaseRepository
from src.repositories.period import PeriodRepository
from src.repositories.snapshot import SnapshotRepository
from src.services.account import AccountService
from src.services.entity import EntityService
from src.services.period import PeriodService
from src.services.transaction import TransactionService
from src.services.transfer import TransferService

import dataset
import reset

from src.model.enums import ReferenceType, TransactionType

_ALLOWED_ENVS = {"dev", "test", "local"}
_LOCAL_ENDPOINTS = {"localhost", "127.0.0.1", "::1", "db", "postgres", "open-ledger-db", "host.docker.internal"}
_CONFIRMATION = "DELETE"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populates the local database with sample ledger data.")
    parser.add_argument("--reset", action="store_true", help="wipe seed data before recreating it")
    parser.add_argument("--force", action="store_true", help="bypass the local environment guard")
    return parser.parse_args(argv)


def _guard_environment(args: argparse.Namespace) -> None:
    env = str(settings.get_from_env("ENV", "")).lower()
    endpoint = str(settings.get_from_env("DATABASE_ENDPOINT", "")).lower()

    problems = []
    if env not in _ALLOWED_ENVS:
        problems.append(f"ENV='{env}' is not a local environment (expected one of: {sorted(_ALLOWED_ENVS)})")
    if endpoint not in _LOCAL_ENDPOINTS:
        problems.append(f"DATABASE_ENDPOINT='{endpoint}' is not a local database")
    if not problems:
        return

    detail = "\n".join(f"  - {problem}" for problem in problems)
    if not args.force:
        raise SystemExit(
            f"seed aborted: the target does not look like a local database.\n{detail}\n"
            "If this is intentional, run it again with --force."
        )

    print(f"WARNING: environment guard bypassed via --force.\n{detail}")
    if args.reset:
        answer = input(f"--reset will DELETE data from this database. Type {_CONFIRMATION} to confirm: ")
        if answer.strip() != _CONFIRMATION:
            raise SystemExit("seed aborted: confirmation not received.")


def _already_seeded(session: Session) -> bool:
    statement = select(Entity.id).where(Entity.external_id.like(f"{dataset.SEED_PREFIX}%")).limit(1)
    return session.execute(statement).first() is not None


def _seed_periods(session: Session) -> None:
    service = PeriodService(session)
    repository = PeriodRepository(session)
    for period_date in dataset.period_dates():
        if repository.get_by_field("period_date", period_date) is not None:
            continue
        service.create(PeriodCreate(period_date=period_date, notes=f"{dataset.PERIOD_NOTE_PREFIX} sample period"))


def _seed_entities(session: Session) -> dict[str, Entity]:
    entity_service = EntityService(session)
    account_service = AccountService(session)
    repository: BaseRepository[Entity] = BaseRepository(session, Entity)

    entities: dict[str, Entity] = {}
    for external_id, name, template in dataset.ENTITIES:
        entity = repository.get_by_field("external_id", external_id)
        if entity is None:
            entity = entity_service.create(
                EntityCreate(external_id=external_id, name=name, custom_data=dataset.CUSTOM_DATA)
            )
        account_service.provision(entity.id, AccountProvision(template=template))
        entities[external_id] = entity

    for external_id in dataset.CLEARING_ENTITIES:
        account_service.provision(entities[external_id].id, AccountProvision(accounts=dataset.CLEARING_ACCOUNTS))

    return entities


def _seed_sales(session: Session, entities: dict[str, Entity]) -> dict[str, Transaction]:
    service = TransactionService(session)
    merchant_id = entities[dataset.MERCHANT].id
    platform_id = entities[dataset.PLATFORM].id

    sales: dict[str, Transaction] = {}
    for sale in dataset.SALES:
        sales[sale.key] = service.post(
            merchant_id,
            TransactionCreate(
                transaction_type=TransactionType.SALE,
                effective_date=dataset.offset(sale.effective_offset),
                entries=dataset.sale_entries(sale.gross),
                reference_id=sale.reference_id,
                reference_type=ReferenceType.TRANSACTION,
                description=f"Sample sale {sale.reference_id}",
                custom_data=dataset.CUSTOM_DATA,
                expected_settlement_date=dataset.offset(sale.settlement_offset),
            ),
            f"seed:sale:{sale.key}",
        )
        service.post(
            platform_id,
            TransactionCreate(
                transaction_type=TransactionType.SALE,
                effective_date=dataset.offset(sale.effective_offset),
                entries=dataset.platform_entries(dataset.platform_fee(sale.gross)),
                reference_id=sale.reference_id,
                reference_type=ReferenceType.TRANSACTION,
                description=f"Platform fee for {sale.reference_id}",
                custom_data=dataset.CUSTOM_DATA,
            ),
            f"seed:sale:{sale.key}:platform",
        )

    return sales


def _seed_anticipation_and_settlement(
    session: Session, entities: dict[str, Entity], sales: dict[str, Transaction]
) -> None:
    """Anticipates and settles the same receivable, so that 1.1.002 ends at zero."""
    service = TransactionService(session)
    merchant_id = entities[dataset.MERCHANT].id
    sale = dataset.ANTICIPATED_SALE
    receivable = sales[sale.key].receivable
    amount = receivable.net_amount
    fee = dataset.anticipation_fee(amount)

    service.anticipate(
        merchant_id,
        AnticipationCreate(
            receivable_id=receivable.id,
            receivable_amount=amount,
            anticipation_fee=fee,
            effective_date=dataset.offset(dataset.ANTICIPATION_OFFSET),
            custom_data=dataset.CUSTOM_DATA,
        ),
        f"seed:anticipation:{sale.key}",
    )
    service.settle(
        merchant_id,
        SettlementCreate(
            receivable_id=receivable.id,
            amount=amount - fee,
            settlement_date=dataset.offset(dataset.SETTLEMENT_OFFSET),
            clearing_network=dataset.SETTLEMENT_NETWORK,
            custom_data=dataset.CUSTOM_DATA,
        ),
        f"seed:settlement:{sale.key}",
    )


def _seed_reversal(session: Session, entities: dict[str, Entity], sales: dict[str, Transaction]) -> None:
    sale = dataset.REVERSED_SALE
    TransactionService(session).reverse(
        entities[dataset.MERCHANT].id,
        sales[sale.key].id,
        ReversalCreate(reason=dataset.REVERSAL_REASON, custom_data=dataset.CUSTOM_DATA),
        f"seed:reversal:{sale.key}",
    )


def _seed_baas_flows(session: Session, entities: dict[str, Entity]) -> None:
    service = TransactionService(session)

    for movement in dataset.DEPOSITS:
        service.deposit(
            entities[movement.entity].id,
            DepositCreate(
                amount=movement.amount,
                effective_date=dataset.offset(movement.effective_offset),
                clearing_network=movement.clearing_network,
                custom_data=dataset.CUSTOM_DATA,
            ),
            f"seed:deposit:{movement.entity}",
        )

    for movement in dataset.WITHDRAWALS:
        service.withdraw(
            entities[movement.entity].id,
            WithdrawalCreate(
                amount=movement.amount,
                effective_date=dataset.offset(movement.effective_offset),
                clearing_network=movement.clearing_network,
                custom_data=dataset.CUSTOM_DATA,
            ),
            f"seed:withdrawal:{movement.entity}",
        )

    TransferService(session).transfer(
        TransferCreate(
            sender_entity_id=entities[dataset.TRANSFER_SENDER].id,
            receiver_entity_id=entities[dataset.TRANSFER_RECEIVER].id,
            amount=dataset.TRANSFER_AMOUNT,
            effective_date=dataset.offset(dataset.TRANSFER_OFFSET),
            description=dataset.TRANSFER_DESCRIPTION,
            custom_data=dataset.CUSTOM_DATA,
        ),
        "seed:transfer:01",
    )


def _seed_snapshot(session: Session, entities: dict[str, Entity]) -> None:
    """Old snapshot so the statement exercises its snapshot-based opening balance path."""
    account = AccountRepository(session).get_by_entity_and_code(
        entities[dataset.SNAPSHOT_ENTITY].id, dataset.SNAPSHOT_ACCOUNT_CODE
    )
    snapshot_date = dataset.offset(dataset.SNAPSHOT_OFFSET)
    existing = session.execute(
        select(AccountBalanceSnapshot.id).where(
            AccountBalanceSnapshot.account_id == account.id,
            AccountBalanceSnapshot.snapshot_date == snapshot_date,
        )
    ).first()
    if existing is not None:
        return

    SnapshotRepository(session).save(
        AccountBalanceSnapshot(
            account_id=account.id, snapshot_date=snapshot_date, balance=dataset.SNAPSHOT_BALANCE
        )
    )


def _print_summary(session: Session, entities: dict[str, Entity]) -> None:
    entity_ids = [entity.id for entity in entities.values()]

    transactions = session.execute(
        select(func.count()).select_from(Transaction).where(Transaction.entity_id.in_(entity_ids))
    ).scalar_one()
    entries = session.execute(
        select(func.count())
        .select_from(TransactionEntry)
        .join(Transaction, Transaction.id == TransactionEntry.transaction_id)
        .where(Transaction.entity_id.in_(entity_ids))
    ).scalar_one()
    accounts = session.execute(
        select(func.count()).select_from(ChartOfAccounts).where(ChartOfAccounts.entity_id.in_(entity_ids))
    ).scalar_one()
    receivables = session.execute(
        select(Receivable.status, func.count())
        .where(Receivable.entity_id.in_(entity_ids))
        .group_by(Receivable.status)
        .order_by(Receivable.status)
    ).all()

    print(f"\nseed complete: {len(entity_ids)} entities, {accounts} accounts, "
          f"{transactions} transactions, {entries} entries")
    print("receivables: " + ", ".join(f"{status}={count}" for status, count in receivables))

    balances = session.execute(
        select(ChartOfAccounts.code, ChartOfAccounts.name, ChartOfAccounts.current_balance)
        .where(
            ChartOfAccounts.entity_id == entities[dataset.MERCHANT].id,
            ChartOfAccounts.current_balance != 0,
        )
        .order_by(ChartOfAccounts.code)
    ).all()
    print(f"\n{dataset.MERCHANT} balances:")
    for code, name, balance in balances:
        print(f"  {code} {name:<28} {balance:>14,.2f}")

    print(f"\nentities: {', '.join(sorted(entities))}")


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    _guard_environment(args)

    session = SessionLocal()
    try:
        if args.reset:
            deleted = reset.wipe(session, dataset.SEED_PREFIX, dataset.PERIOD_NOTE_PREFIX)
            removed = ", ".join(f"{table}={count}" for table, count in deleted.items() if count)
            print(f"reset: {removed or 'nothing to delete'}")
        elif _already_seeded(session):
            print(f"database already seeded (entities prefixed with '{dataset.SEED_PREFIX}'). Nothing to do.")
            print("Run `make db/seed/reset` to recreate it from scratch.")
            return 0

        _seed_periods(session)
        entities = _seed_entities(session)
        sales = _seed_sales(session, entities)
        _seed_anticipation_and_settlement(session, entities, sales)
        _seed_reversal(session, entities, sales)
        _seed_baas_flows(session, entities)
        _seed_snapshot(session, entities)
        session.commit()

        _print_summary(session, entities)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
