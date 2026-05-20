from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from src.exceptions.entity import EntityNotFoundError
from src.model.account_balance_snapshot import AccountBalanceSnapshot
from src.model.chart_of_accounts import AccountType, ChartOfAccounts
from src.model.transaction import Transaction
from src.model.transaction_entry import TransactionEntry
from src.services.statement import StatementService, _asset_delta


def _make_account(account_type=AccountType.asset, balance="0", code="1.1.001") -> ChartOfAccounts:
    acc = ChartOfAccounts(
        entity_id=uuid4(),
        code=code,
        name=f"Account {code}",
        account_type=account_type,
        currency="BRL",
        current_balance=Decimal(balance),
        balance_version=0,
    )
    acc.id = uuid4()
    return acc


def _make_entry(account: ChartOfAccounts, entry_type: str, amount: str) -> TransactionEntry:
    entry = TransactionEntry(
        transaction_id=uuid4(),
        account_id=account.id,
        entry_type=entry_type,
        amount=Decimal(amount),
        currency="BRL",
    )
    entry.id = uuid4()
    entry.account = account
    return entry


def _make_transaction(entity_id=None, effective_date=None, txn_type="sale") -> Transaction:
    txn = Transaction(
        entity_id=entity_id or uuid4(),
        idempotency_key=str(uuid4()),
        status="committed",
        transaction_type=txn_type,
        effective_date=effective_date or date(2025, 12, 10),
    )
    txn.id = uuid4()
    return txn


def _make_service() -> StatementService:
    session = MagicMock()
    service = StatementService(session)
    service._snapshot_repo = MagicMock()
    service._account_repo = MagicMock()
    service._entity_repo = MagicMock()
    return service


class AssetDeltaTest(TestCase):
    def test_asset_debit_positive(self):
        self.assertEqual(_asset_delta("asset", "debit", Decimal("100")), Decimal("100"))

    def test_asset_credit_negative(self):
        self.assertEqual(_asset_delta("asset", "credit", Decimal("100")), Decimal("-100"))

    def test_non_asset_returns_zero(self):
        self.assertEqual(_asset_delta("revenue", "credit", Decimal("100")), Decimal("0"))
        self.assertEqual(_asset_delta("expense", "debit", Decimal("100")), Decimal("0"))
        self.assertEqual(_asset_delta("liability", "credit", Decimal("50")), Decimal("0"))


class GetBalanceTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_entity_not_found_raises(self):
        self.service._entity_repo.exists.return_value = False
        with self.assertRaises(EntityNotFoundError):
            self.service.get_balance(uuid4())

    def test_returns_account_balance_list(self):
        entity_id = uuid4()
        acc = _make_account(balance="150.00")
        self.service._entity_repo.exists.return_value = True
        self.service._account_repo.get_by_entity.return_value = [acc]

        result = self.service.get_balance(entity_id)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].account_id, acc.id)
        self.assertEqual(result[0].code, acc.code)
        self.assertEqual(result[0].current_balance, Decimal("150.00"))

    def test_empty_accounts_returns_empty_list(self):
        self.service._entity_repo.exists.return_value = True
        self.service._account_repo.get_by_entity.return_value = []
        result = self.service.get_balance(uuid4())
        self.assertEqual(result, [])


class OpeningBalanceTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_non_asset_account_returns_zero(self):
        acc = _make_account(account_type=AccountType.revenue)
        result = self.service._opening_balance_for_account(acc, date(2025, 12, 1))
        self.assertEqual(result, Decimal(0))
        self.service._snapshot_repo.get_latest_before.assert_not_called()

    def test_uses_snapshot_when_available(self):
        acc = _make_account(account_type=AccountType.asset)
        snapshot = AccountBalanceSnapshot(account_id=acc.id, snapshot_date=date(2025, 11, 30), balance=Decimal("200"))
        self.service._snapshot_repo.get_latest_before.return_value = snapshot

        result = self.service._opening_balance_for_account(acc, date(2025, 12, 1))

        self.assertEqual(result, Decimal("200"))

    def test_fallback_to_entries_when_no_snapshot(self):
        acc = _make_account(account_type=AccountType.asset)
        self.service._snapshot_repo.get_latest_before.return_value = None

        entry1 = _make_entry(acc, "debit", "100")
        entry2 = _make_entry(acc, "credit", "30")

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.all.return_value = [entry1, entry2]
        self.service._session.query.return_value = mock_chain

        result = self.service._opening_balance_for_account(acc, date(2025, 12, 1))

        self.assertEqual(result, Decimal("70"))

    def test_fallback_no_entries_returns_zero(self):
        acc = _make_account(account_type=AccountType.asset)
        self.service._snapshot_repo.get_latest_before.return_value = None

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.all.return_value = []
        self.service._session.query.return_value = mock_chain

        result = self.service._opening_balance_for_account(acc, date(2025, 12, 1))

        self.assertEqual(result, Decimal(0))


class BuildStatementTest(TestCase):
    def setUp(self):
        self.service = _make_service()
        self.entity_id = uuid4()
        self.service._entity_repo.exists.return_value = True

    def _setup_session_query(self, period_rows, before_rows=None):
        before_rows = before_rows or []

        call_count = [0]

        def query_side_effect(*args, **kwargs):
            chain = MagicMock()
            chain.join.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            call_count[0] += 1
            if call_count[0] == 1:
                chain.all.return_value = before_rows
            else:
                chain.all.return_value = period_rows
            return chain

        self.service._session.query.side_effect = query_side_effect

    def test_entity_not_found_raises(self):
        self.service._entity_repo.exists.return_value = False
        with self.assertRaises(EntityNotFoundError):
            self.service.build_statement(uuid4(), date(2025, 12, 1), date(2025, 12, 31))

    def test_no_entries_returns_zero_summary(self):
        self.service._account_repo.get_by_entity.return_value = []
        self.service._snapshot_repo.get_latest_before.return_value = None

        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.all.return_value = []
        self.service._session.query.return_value = mock_chain

        result = self.service.build_statement(self.entity_id, date(2025, 12, 1), date(2025, 12, 31))

        self.assertEqual(result.summary.opening_balance, Decimal(0))
        self.assertEqual(result.summary.closing_balance, Decimal(0))
        self.assertEqual(result.summary.total_in, Decimal(0))
        self.assertEqual(result.summary.total_out, Decimal(0))
        self.assertEqual(result.entries, [])

    def test_sale_increases_running_balance(self):
        acc_recv = _make_account(account_type=AccountType.asset, code="1.1.001")
        acc_rev = _make_account(account_type=AccountType.revenue, code="3.1.001")
        self.service._account_repo.get_by_entity.return_value = [acc_recv, acc_rev]
        # snapshot returns zero opening for asset account; non-asset returns 0 immediately
        snap = AccountBalanceSnapshot(account_id=acc_recv.id, snapshot_date=date(2025, 11, 30), balance=Decimal("0"))
        self.service._snapshot_repo.get_latest_before.return_value = snap

        txn = _make_transaction(entity_id=self.entity_id, effective_date=date(2025, 12, 10))
        entry_recv = _make_entry(acc_recv, "debit", "100")
        entry_recv.transaction_id = txn.id
        entry_rev = _make_entry(acc_rev, "credit", "100")
        entry_rev.transaction_id = txn.id

        c = MagicMock()
        c.join.return_value = c
        c.filter.return_value = c
        c.order_by.return_value = c
        c.all.return_value = [(entry_recv, txn), (entry_rev, txn)]
        self.service._session.query.return_value = c

        result = self.service.build_statement(self.entity_id, date(2025, 12, 1), date(2025, 12, 31))

        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].balance_after, Decimal("100"))
        self.assertEqual(result.summary.total_in, Decimal("100"))
        self.assertEqual(result.summary.total_out, Decimal("0"))
        self.assertEqual(result.summary.closing_balance, Decimal("100"))

    def test_total_out_on_net_negative_asset_delta(self):
        acc_recv = _make_account(account_type=AccountType.asset, code="1.1.001")
        acc_world = _make_account(account_type=AccountType.asset, code="9.9.999")
        self.service._account_repo.get_by_entity.return_value = [acc_recv, acc_world]
        snap = AccountBalanceSnapshot(account_id=acc_recv.id, snapshot_date=date(2025, 11, 30), balance=Decimal("100"))
        snap2 = AccountBalanceSnapshot(account_id=acc_world.id, snapshot_date=date(2025, 11, 30), balance=Decimal("0"))
        self.service._snapshot_repo.get_latest_before.side_effect = [snap, snap2]

        # settlement: world debit 100, receivables credit 100 → net asset delta = 0
        txn = _make_transaction(entity_id=self.entity_id, effective_date=date(2025, 12, 15), txn_type="settlement")
        entry_world = _make_entry(acc_world, "debit", "100")
        entry_world.transaction_id = txn.id
        entry_recv = _make_entry(acc_recv, "credit", "100")
        entry_recv.transaction_id = txn.id

        c = MagicMock()
        c.join.return_value = c
        c.filter.return_value = c
        c.order_by.return_value = c
        c.all.return_value = [(entry_world, txn), (entry_recv, txn)]
        self.service._session.query.return_value = c

        result = self.service.build_statement(self.entity_id, date(2025, 12, 1), date(2025, 12, 31))

        # world debit +100, recv credit -100 → net delta = 0 → neither total_in nor total_out
        self.assertEqual(result.summary.total_in, Decimal("0"))
        self.assertEqual(result.summary.total_out, Decimal("0"))
        self.assertEqual(result.summary.opening_balance, Decimal("100"))

    def test_total_out_on_negative_net_asset_delta(self):
        acc_recv = _make_account(account_type=AccountType.asset, code="1.1.001")
        acc_rev = _make_account(account_type=AccountType.revenue, code="3.1.001")
        self.service._account_repo.get_by_entity.return_value = [acc_recv, acc_rev]
        snap = AccountBalanceSnapshot(account_id=acc_recv.id, snapshot_date=date(2025, 11, 30), balance=Decimal("100"))
        self.service._snapshot_repo.get_latest_before.return_value = snap

        txn = _make_transaction(entity_id=self.entity_id, effective_date=date(2025, 12, 20), txn_type="refund")
        entry_recv = _make_entry(acc_recv, "credit", "30")
        entry_recv.transaction_id = txn.id
        entry_rev = _make_entry(acc_rev, "debit", "30")
        entry_rev.transaction_id = txn.id

        c = MagicMock()
        c.join.return_value = c
        c.filter.return_value = c
        c.order_by.return_value = c
        c.all.return_value = [(entry_recv, txn), (entry_rev, txn)]
        self.service._session.query.return_value = c

        result = self.service.build_statement(self.entity_id, date(2025, 12, 1), date(2025, 12, 31))

        self.assertEqual(result.summary.total_out, Decimal("30"))
        self.assertEqual(result.summary.total_in, Decimal("0"))
        self.assertEqual(result.summary.closing_balance, Decimal("70"))

    def test_summary_period_fields(self):
        self.service._account_repo.get_by_entity.return_value = []
        self.service._snapshot_repo.get_latest_before.return_value = None

        c = MagicMock()
        c.join.return_value = c
        c.filter.return_value = c
        c.order_by.return_value = c
        c.all.return_value = []
        self.service._session.query.return_value = c

        result = self.service.build_statement(self.entity_id, date(2025, 12, 1), date(2025, 12, 31))

        self.assertEqual(result.entity_id, self.entity_id)
        self.assertEqual(result.period.start_date, date(2025, 12, 1))
        self.assertEqual(result.period.end_date, date(2025, 12, 31))
