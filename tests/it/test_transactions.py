from datetime import date
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.model.chart_of_accounts import AccountType, ChartOfAccounts
from src.model.entity import Entity
from src.model.transaction import Transaction
from src.model.transaction_entry import TransactionEntry
from src.repositories.transaction import TransactionEntryRepository, TransactionRepository


def _make_entity(session):
    entity = Entity(external_id=f"ext-{uuid4()}")
    session.add(entity)
    session.flush()
    return entity


def _make_account(session, entity_id):
    account = ChartOfAccounts(
        entity_id=entity_id,
        code=f"1.1.{uuid4().hex[:3]}",
        name="Test Account",
        account_type=AccountType.asset,
        currency="BRL",
    )
    session.add(account)
    session.flush()
    return account


def _make_transaction(session, entity_id, idempotency_key=None):
    txn = Transaction(
        entity_id=entity_id,
        idempotency_key=idempotency_key or str(uuid4()),
        transaction_type="sale",
        effective_date=date(2026, 4, 20),
        status="committed",
    )
    session.add(txn)
    session.flush()
    return txn


class TransactionRepositoryITTest(TestCase):
    db_session = None

    def setUp(self):
        self.repo = TransactionRepository(self.db_session)
        self.entity = _make_entity(self.db_session)

    def test_create_and_get_by_id(self):
        txn = _make_transaction(self.db_session, self.entity.id)
        result = self.repo.get_by_id(txn.id)
        self.assertEqual(result.id, txn.id)
        self.assertEqual(result.transaction_type, "sale")

    def test_get_by_idempotency_key(self):
        key = f"idem-{uuid4()}"
        txn = _make_transaction(self.db_session, self.entity.id, idempotency_key=key)
        result = self.repo.get_by_idempotency_key(key)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, txn.id)

    def test_get_by_idempotency_key_not_found_returns_none(self):
        result = self.repo.get_by_idempotency_key("nonexistent-key")
        self.assertIsNone(result)

    def test_get_by_entity_returns_only_own_transactions(self):
        other_entity = _make_entity(self.db_session)
        _make_transaction(self.db_session, self.entity.id)
        _make_transaction(self.db_session, self.entity.id)
        _make_transaction(self.db_session, other_entity.id)

        results = self.repo.get_by_entity(self.entity.id)
        self.assertEqual(len(results), 2)
        for txn in results:
            self.assertEqual(txn.entity_id, self.entity.id)

    def test_get_by_entity_pagination(self):
        for _ in range(5):
            _make_transaction(self.db_session, self.entity.id)

        page1 = self.repo.get_by_entity(self.entity.id, skip=0, limit=3)
        page2 = self.repo.get_by_entity(self.entity.id, skip=3, limit=3)
        self.assertEqual(len(page1), 3)
        self.assertLessEqual(len(page2), 3)

    def test_get_with_entries_loads_eager(self):
        txn = _make_transaction(self.db_session, self.entity.id)
        account = _make_account(self.db_session, self.entity.id)
        entry = TransactionEntry(
            transaction_id=txn.id,
            account_id=account.id,
            entry_type="debit",
            amount=Decimal("100.00"),
            currency="BRL",
        )
        self.db_session.add(entry)
        self.db_session.flush()

        result = self.repo.get_with_entries(self.entity.id, txn.id)
        self.assertIsNotNone(result)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].entry_type, "debit")

    def test_idempotency_key_unique_constraint_raises(self):
        key = f"dup-{uuid4()}"
        _make_transaction(self.db_session, self.entity.id, idempotency_key=key)
        with pytest.raises(IntegrityError):
            _make_transaction(self.db_session, self.entity.id, idempotency_key=key)


class TransactionEntryRepositoryITTest(TestCase):
    db_session = None

    def setUp(self):
        self.repo = TransactionEntryRepository(self.db_session)
        self.entity = _make_entity(self.db_session)

    def test_get_by_transaction(self):
        txn = _make_transaction(self.db_session, self.entity.id)
        account = _make_account(self.db_session, self.entity.id)
        entry = TransactionEntry(
            transaction_id=txn.id,
            account_id=account.id,
            entry_type="credit",
            amount=Decimal("50.00"),
            currency="BRL",
        )
        self.db_session.add(entry)
        self.db_session.flush()

        results = self.repo.get_by_transaction(txn.id)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].amount, Decimal("50.00"))
