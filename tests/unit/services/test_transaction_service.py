from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.exceptions.transaction import DoubleEntryImbalanceError
from src.model.chart_of_accounts import AccountType, ChartOfAccounts
from src.model.schemas.transactions import TransactionCreate, TransactionEntryCreate
from src.services.transaction import TransactionService


def _entry(entry_type: str, amount: str, currency: str = "BRL") -> TransactionEntryCreate:
    return TransactionEntryCreate(
        account_code="1.1.001", entry_type=entry_type, amount=Decimal(amount), currency=currency
    )


def _make_account(account_type: AccountType = AccountType.asset, balance: str = "0") -> ChartOfAccounts:
    account = ChartOfAccounts(
        entity_id=uuid4(),
        code="1.1.001",
        name="Test",
        account_type=account_type,
        currency="BRL",
        current_balance=Decimal(balance),
        balance_version=0,
    )
    account.id = uuid4()
    return account


def _make_entry(account: ChartOfAccounts, entry_type: str, amount: str) -> TransactionEntryCreate:
    return TransactionEntryCreate(account_code=account.code, entry_type=entry_type, amount=Decimal(amount))


def _make_service(session=None) -> TransactionService:
    return TransactionService(session or MagicMock())


class RoundAmountTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_rounds_up_at_half(self):
        self.assertEqual(self.service._round_amount(Decimal("1.4655")), Decimal("1.47"))

    def test_rounds_down_below_half(self):
        self.assertEqual(self.service._round_amount(Decimal("1.4645")), Decimal("1.46"))

    def test_rounds_half_up_at_midpoint(self):
        self.assertEqual(self.service._round_amount(Decimal("1.005")), Decimal("1.01"))

    def test_exact_value_unchanged(self):
        self.assertEqual(self.service._round_amount(Decimal("5.00")), Decimal("5.00"))


class ComputeDeltaTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_asset_debit(self):
        self.assertEqual(self.service._compute_delta("asset", "debit", Decimal("100")), Decimal("100"))

    def test_asset_credit(self):
        self.assertEqual(self.service._compute_delta("asset", "credit", Decimal("100")), Decimal("-100"))

    def test_expense_debit(self):
        self.assertEqual(self.service._compute_delta("expense", "debit", Decimal("100")), Decimal("100"))

    def test_expense_credit(self):
        self.assertEqual(self.service._compute_delta("expense", "credit", Decimal("100")), Decimal("-100"))

    def test_liability_debit(self):
        self.assertEqual(self.service._compute_delta("liability", "debit", Decimal("100")), Decimal("-100"))

    def test_liability_credit(self):
        self.assertEqual(self.service._compute_delta("liability", "credit", Decimal("100")), Decimal("100"))

    def test_revenue_debit(self):
        self.assertEqual(self.service._compute_delta("revenue", "debit", Decimal("100")), Decimal("-100"))

    def test_revenue_credit(self):
        self.assertEqual(self.service._compute_delta("revenue", "credit", Decimal("100")), Decimal("100"))

    def test_equity_debit(self):
        self.assertEqual(self.service._compute_delta("equity", "debit", Decimal("100")), Decimal("-100"))

    def test_equity_credit(self):
        self.assertEqual(self.service._compute_delta("equity", "credit", Decimal("100")), Decimal("100"))


class ValidateDoubleEntryTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_balanced_passes(self):
        self.service._validate_double_entry([_entry("debit", "100.00"), _entry("credit", "100.00")])

    def test_imbalanced_raises(self):
        with self.assertRaises(DoubleEntryImbalanceError):
            self.service._validate_double_entry([_entry("debit", "100.00"), _entry("credit", "90.00")])

    def test_imbalanced_includes_currency_in_error(self):
        with self.assertRaises(DoubleEntryImbalanceError) as ctx:
            self.service._validate_double_entry([_entry("debit", "100.00", "USD"), _entry("credit", "90.00", "USD")])
        self.assertIn("USD", str(ctx.exception))

    def test_two_currencies_both_balanced_passes(self):
        self.service._validate_double_entry([
            _entry("debit", "50.00", "BRL"), _entry("credit", "50.00", "BRL"),
            _entry("debit", "20.00", "USD"), _entry("credit", "20.00", "USD"),
        ])

    def test_two_currencies_one_imbalanced_raises_correct_currency(self):
        with self.assertRaises(DoubleEntryImbalanceError) as ctx:
            self.service._validate_double_entry([
                _entry("debit", "50.00", "BRL"), _entry("credit", "50.00", "BRL"),
                _entry("debit", "20.00", "USD"), _entry("credit", "10.00", "USD"),
            ])
        self.assertIn("USD", str(ctx.exception))

    def test_empty_entries_passes(self):
        self.service._validate_double_entry([])


class ApplyBalanceUpdatesTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = _make_service(self.session)

    def _setup_locked(self, locked_account: ChartOfAccounts) -> None:
        self.session.execute.return_value.scalar_one.return_value = locked_account

    def test_asset_debit_increases_balance(self):
        account = _make_account(AccountType.asset, "100")
        locked = _make_account(AccountType.asset, "100")
        locked.id = account.id
        self._setup_locked(locked)

        self.service._apply_balance_updates([_make_entry(account, "debit", "50")], [account])

        self.assertEqual(locked.current_balance, Decimal("150"))
        self.assertEqual(locked.balance_version, 1)
        self.assertIsNotNone(locked.last_entry_at)

    def test_asset_credit_decreases_balance(self):
        account = _make_account(AccountType.asset, "200")
        locked = _make_account(AccountType.asset, "200")
        locked.id = account.id
        locked.balance_version = 2
        self._setup_locked(locked)

        self.service._apply_balance_updates([_make_entry(account, "credit", "75")], [account])

        self.assertEqual(locked.current_balance, Decimal("125"))
        self.assertEqual(locked.balance_version, 3)

    def test_liability_credit_increases_balance(self):
        account = _make_account(AccountType.liability, "0")
        locked = _make_account(AccountType.liability, "0")
        locked.id = account.id
        self._setup_locked(locked)

        self.service._apply_balance_updates([_make_entry(account, "credit", "300")], [account])

        self.assertEqual(locked.current_balance, Decimal("300"))

    def test_execute_called_once_per_entry(self):
        account = _make_account()
        locked = _make_account(AccountType.asset, "0")
        locked.id = account.id
        self._setup_locked(locked)

        self.service._apply_balance_updates([_make_entry(account, "debit", "10")], [account])

        self.session.execute.assert_called_once()

    def test_multiple_entries_execute_called_for_each(self):
        account1 = _make_account(AccountType.asset, "0")
        account2 = _make_account(AccountType.liability, "0")
        locked1 = _make_account(AccountType.asset, "0")
        locked2 = _make_account(AccountType.liability, "0")
        locked1.id = account1.id
        locked2.id = account2.id
        locked1.balance_version = 0
        locked2.balance_version = 0

        self.session.execute.return_value.scalar_one.side_effect = [locked1, locked2]

        self.service._apply_balance_updates(
            [_make_entry(account1, "debit", "100"), _make_entry(account2, "credit", "100")],
            [account1, account2],
        )

        self.assertEqual(self.session.execute.call_count, 2)
        self.assertEqual(locked1.current_balance, Decimal("100"))
        self.assertEqual(locked2.current_balance, Decimal("100"))


class TransactionServicePostTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = TransactionService(self.session)
        self.service._repo = MagicMock()
        self.service._account_repo = MagicMock()
        self.service._period_svc = MagicMock()

    def _payload(self):
        return TransactionCreate(
            transaction_type="sale",
            effective_date=date(2026, 4, 20),
            entries=[
                TransactionEntryCreate(account_code="1.1.001", entry_type="debit",  amount=Decimal("100")),
                TransactionEntryCreate(account_code="3.1.001", entry_type="credit", amount=Decimal("100")),
            ],
        )

    def test_pending_status_skips_balance_update(self):
        self.service._repo.get_by_idempotency_key.return_value = None
        mock_account = MagicMock()
        mock_account.currency = "BRL"
        self.service._account_repo.get_by_entity_and_code.return_value = mock_account

        mock_txn = MagicMock()
        mock_txn.status = "pending"
        mock_txn.id = uuid4()

        with patch("src.services.transaction.Transaction", return_value=mock_txn):
            result = self.service.post(uuid4(), self._payload(), "key-pending")

        self.session.execute.assert_not_called()
        self.assertEqual(result, mock_txn)

    def test_idempotency_returns_existing_without_writes(self):
        existing = MagicMock()
        self.service._repo.get_by_idempotency_key.return_value = existing

        result = self.service.post(uuid4(), self._payload(), "key-existing")

        self.assertEqual(result, existing)
        self.session.add.assert_not_called()
