from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api import app
from src.config.database import get_db
from src.model.accounting_period import AccountingPeriod, PeriodStatus
from src.model.chart_of_accounts import AccountType, ChartOfAccounts
from src.model.entity import Entity
from src.model.transaction import Transaction

_EFFECTIVE_DATE = "2026-04-21"


def _make_entity(session):
    entity = Entity(external_id=f"ext-{uuid4()}")
    session.add(entity)
    session.flush()
    return entity


def _open_period(session, period_date: date):
    period = AccountingPeriod(
        period_date=period_date, status=PeriodStatus.open, opened_at=datetime.now(timezone.utc)
    )
    session.add(period)
    session.flush()
    return period


def _provision_accounts(session, entity_id):
    accounts = [
        ChartOfAccounts(entity_id=entity_id, code="1.1.001", name="Receivables",
                        account_type=AccountType.asset, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="1.1.002", name="Receivables Anticipated",
                        account_type=AccountType.asset, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="3.1.001", name="Revenue",
                        account_type=AccountType.revenue, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="4.1.003", name="Anticipation Fee Expense",
                        account_type=AccountType.expense, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="9.9.902", name="World/CIP-PIX",
                        account_type=AccountType.asset, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="9.9.999", name="World",
                        account_type=AccountType.asset, currency="BRL"),
    ]
    for a in accounts:
        session.add(a)
    session.flush()
    return {a.code: a for a in accounts}


def _get_balance(session, entity_id, code) -> Decimal:
    account = (
        session.query(ChartOfAccounts)
        .filter(ChartOfAccounts.entity_id == entity_id, ChartOfAccounts.code == code)
        .first()
    )
    session.refresh(account)
    return account.current_balance


class TransactionLifecycleFullFlowTest(TestCase):
    """Tests the complete sale → anticipation → settlement flow."""

    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

        self.entity = _make_entity(self.db_session)
        self.entity_id = str(self.entity.id)
        _provision_accounts(self.db_session, self.entity.id)
        _open_period(self.db_session, date.fromisoformat(_EFFECTIVE_DATE))

    def tearDown(self):
        app.dependency_overrides.clear()

    def _post_sale(self, recv_payload=None, idem_key=None):
        payload = {
            "transaction_type": "sale",
            "effective_date": _EFFECTIVE_DATE,
            "entries": [
                {"account_code": "1.1.001", "entry_type": "debit",  "amount": "97.70", "currency": "BRL"},
                {"account_code": "3.1.001", "entry_type": "credit", "amount": "97.70", "currency": "BRL"},
            ],
        }
        if recv_payload:
            payload["receivable"] = recv_payload
        return self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json=payload,
            headers={"Idempotency-Key": idem_key or str(uuid4())},
        )

    def test_full_sale_anticipation_settlement_flow(self):
        recv_payload = {
            "gross_amount": "100.00", "net_amount": "97.70", "fee_amount": "2.30",
            "expected_settlement_date": _EFFECTIVE_DATE,
        }
        sale_resp = self._post_sale(recv_payload=recv_payload)
        self.assertEqual(sale_resp.status_code, 201)

        recv_list = self.client.get(f"/entities/{self.entity_id}/receivables")
        self.assertEqual(len(recv_list.json()), 1)
        recv_id = recv_list.json()[0]["id"]

        ant_resp = self.client.post(
            f"/entities/{self.entity_id}/anticipations",
            json={
                "receivable_id": recv_id,
                "receivable_amount": "97.70",
                "anticipation_fee": "1.47",
                "effective_date": _EFFECTIVE_DATE,
                "custom_data": {"anticipation_id": "ant_456"},
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(ant_resp.status_code, 201)
        self.assertEqual(ant_resp.json()["transaction_type"], "anticipation")

        sett_resp = self.client.post(
            f"/entities/{self.entity_id}/settlements",
            json={
                "receivable_id": recv_id,
                "amount": "96.23",
                "settlement_date": _EFFECTIVE_DATE,
                "clearing_network": "CIP-PIX",
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(sett_resp.status_code, 201)
        self.assertEqual(sett_resp.json()["transaction_type"], "settlement")

        recv_detail = self.client.get(f"/entities/{self.entity_id}/receivables/{recv_id}")
        self.assertEqual(recv_detail.json()["status"], "settled")

        balance_001 = _get_balance(self.db_session, self.entity.id, "1.1.001")
        balance_002 = _get_balance(self.db_session, self.entity.id, "1.1.002")
        balance_world = _get_balance(self.db_session, self.entity.id, "9.9.902")

        self.assertEqual(balance_001, Decimal("0.00"))
        self.assertEqual(balance_002, Decimal("0.00"))
        self.assertEqual(balance_world, Decimal("96.23"))

    def test_anticipation_idempotency(self):
        sale_resp = self._post_sale()
        self.assertEqual(sale_resp.status_code, 201)

        idem_key = str(uuid4())
        payload = {
            "receivable_id": str(uuid4()),
            "receivable_amount": "97.70",
            "anticipation_fee": "1.47",
            "effective_date": _EFFECTIVE_DATE,
        }

        r1 = self.client.post(
            f"/entities/{self.entity_id}/anticipations",
            json=payload,
            headers={"Idempotency-Key": idem_key},
        )
        r2 = self.client.post(
            f"/entities/{self.entity_id}/anticipations",
            json=payload,
            headers={"Idempotency-Key": idem_key},
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json()["id"], r2.json()["id"])

    def test_settlement_receivable_not_found_returns_404(self):
        resp = self.client.post(
            f"/entities/{self.entity_id}/settlements",
            json={
                "receivable_id": str(uuid4()),
                "amount": "96.23",
                "settlement_date": _EFFECTIVE_DATE,
                "clearing_network": "CIP-PIX",
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 404)


class TransactionLifecycleErrorHandlingTest(TestCase):
    """Tests that new endpoints return 422 when business rules are violated."""

    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)
        self.entity = _make_entity(self.db_session)
        self.entity_id = str(self.entity.id)
        _provision_accounts(self.db_session, self.entity.id)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_anticipation_closed_period_returns_422(self):
        resp = self.client.post(
            f"/entities/{self.entity_id}/anticipations",
            json={
                "receivable_id": str(uuid4()),
                "receivable_amount": "97.70",
                "anticipation_fee": "1.47",
                "effective_date": _EFFECTIVE_DATE,
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 422)

    def test_deposit_closed_period_returns_422(self):
        resp = self.client.post(
            f"/entities/{self.entity_id}/deposits",
            json={"amount": "500.00", "currency": "BRL", "effective_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 422)

    def test_withdrawal_closed_period_returns_422(self):
        resp = self.client.post(
            f"/entities/{self.entity_id}/withdrawals",
            json={"amount": "200.00", "currency": "BRL", "effective_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 422)

    def test_settlement_invalid_receivable_status_returns_422(self):
        _open_period(self.db_session, date.fromisoformat(_EFFECTIVE_DATE))

        self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json={
                "transaction_type": "sale",
                "effective_date": _EFFECTIVE_DATE,
                "entries": [
                    {"account_code": "1.1.001", "entry_type": "debit",  "amount": "97.70", "currency": "BRL"},
                    {"account_code": "3.1.001", "entry_type": "credit", "amount": "97.70", "currency": "BRL"},
                ],
                "receivable": {"gross_amount": "100.00", "net_amount": "97.70", "fee_amount": "2.30"},
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        recv_list = self.client.get(f"/entities/{self.entity_id}/receivables")
        recv_id = recv_list.json()[0]["id"]

        self.client.post(
            f"/entities/{self.entity_id}/settlements",
            json={"receivable_id": recv_id, "amount": "97.70", "settlement_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )

        resp = self.client.post(
            f"/entities/{self.entity_id}/settlements",
            json={"receivable_id": recv_id, "amount": "97.70", "settlement_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 422)


class DepositWithdrawalTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

        self.entity = _make_entity(self.db_session)
        self.entity_id = str(self.entity.id)
        _provision_accounts(self.db_session, self.entity.id)
        _open_period(self.db_session, date.fromisoformat(_EFFECTIVE_DATE))

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_deposit_increases_checking_and_credits_world(self):
        resp = self.client.post(
            f"/entities/{self.entity_id}/deposits",
            json={"amount": "500.00", "currency": "BRL", "effective_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["transaction_type"], "deposit")

        checking = _get_balance(self.db_session, self.entity.id, "1.1.001")
        world = _get_balance(self.db_session, self.entity.id, "9.9.999")
        self.assertEqual(checking, Decimal("500.00"))
        self.assertEqual(world, Decimal("-500.00"))

    def test_deposit_idempotency(self):
        idem_key = str(uuid4())
        payload = {"amount": "100.00", "currency": "BRL", "effective_date": _EFFECTIVE_DATE}
        r1 = self.client.post(
            f"/entities/{self.entity_id}/deposits", json=payload, headers={"Idempotency-Key": idem_key}
        )
        r2 = self.client.post(
            f"/entities/{self.entity_id}/deposits", json=payload, headers={"Idempotency-Key": idem_key}
        )
        self.assertEqual(r1.json()["id"], r2.json()["id"])

    def test_withdrawal_decreases_checking_and_debits_world(self):
        self.client.post(
            f"/entities/{self.entity_id}/deposits",
            json={"amount": "500.00", "currency": "BRL", "effective_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )

        resp = self.client.post(
            f"/entities/{self.entity_id}/withdrawals",
            json={"amount": "200.00", "currency": "BRL", "effective_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["transaction_type"], "withdrawal")

        checking = _get_balance(self.db_session, self.entity.id, "1.1.001")
        world = _get_balance(self.db_session, self.entity.id, "9.9.999")
        self.assertEqual(checking, Decimal("300.00"))
        self.assertEqual(world, Decimal("-300.00"))

    def test_withdrawal_idempotency(self):
        self.client.post(
            f"/entities/{self.entity_id}/deposits",
            json={"amount": "500.00", "currency": "BRL", "effective_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )
        idem_key = str(uuid4())
        payload = {"amount": "100.00", "currency": "BRL", "effective_date": _EFFECTIVE_DATE}
        r1 = self.client.post(
            f"/entities/{self.entity_id}/withdrawals", json=payload, headers={"Idempotency-Key": idem_key}
        )
        r2 = self.client.post(
            f"/entities/{self.entity_id}/withdrawals", json=payload, headers={"Idempotency-Key": idem_key}
        )
        self.assertEqual(r1.json()["id"], r2.json()["id"])


class VoidTransactionITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

        self.entity = _make_entity(self.db_session)
        self.entity_id = str(self.entity.id)
        _provision_accounts(self.db_session, self.entity.id)
        _open_period(self.db_session, date.fromisoformat(_EFFECTIVE_DATE))

    def tearDown(self):
        app.dependency_overrides.clear()

    def _create_pending_transaction(self):
        txn = Transaction(
            entity_id=self.entity.id,
            idempotency_key=str(uuid4()),
            transaction_type="sale",
            effective_date=date.fromisoformat(_EFFECTIVE_DATE),
            status="pending",
        )
        self.db_session.add(txn)
        self.db_session.flush()
        return txn

    def _create_committed_transaction(self):
        resp = self.client.post(
            f"/entities/{self.entity_id}/deposits",
            json={"amount": "100.00", "currency": "BRL", "effective_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )
        return resp.json()["id"]

    def test_void_pending_transaction_returns_voided_status(self):
        txn = self._create_pending_transaction()
        resp = self.client.post(f"/entities/{self.entity_id}/transactions/{txn.id}/void")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "voided")

    def test_void_pending_transaction_leaves_balances_unchanged(self):
        txn = self._create_pending_transaction()
        self.client.post(f"/entities/{self.entity_id}/transactions/{txn.id}/void")

        checking = _get_balance(self.db_session, self.entity.id, "1.1.001")
        self.assertEqual(checking, Decimal("0.00"))

    def test_void_committed_transaction_returns_422(self):
        txn_id = self._create_committed_transaction()
        resp = self.client.post(f"/entities/{self.entity_id}/transactions/{txn_id}/void")
        self.assertEqual(resp.status_code, 422)

    def test_void_nonexistent_transaction_returns_404(self):
        resp = self.client.post(f"/entities/{self.entity_id}/transactions/{uuid4()}/void")
        self.assertEqual(resp.status_code, 404)


class ReverseTransactionITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

        self.entity = _make_entity(self.db_session)
        self.entity_id = str(self.entity.id)
        _provision_accounts(self.db_session, self.entity.id)
        _open_period(self.db_session, date.fromisoformat(_EFFECTIVE_DATE))
        today = date.today()
        if today != date.fromisoformat(_EFFECTIVE_DATE):
            _open_period(self.db_session, today)

    def tearDown(self):
        app.dependency_overrides.clear()

    def _post_deposit(self, amount="500.00"):
        resp = self.client.post(
            f"/entities/{self.entity_id}/deposits",
            json={"amount": amount, "currency": "BRL", "effective_date": _EFFECTIVE_DATE},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 201)
        return resp.json()["id"]

    def test_reverse_restores_balances(self):
        txn_id = self._post_deposit("300.00")

        checking_before = _get_balance(self.db_session, self.entity.id, "1.1.001")
        self.assertEqual(checking_before, Decimal("300.00"))

        resp = self.client.post(
            f"/entities/{self.entity_id}/transactions/{txn_id}/reverse",
            json={"reason": "test reversal"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["transaction_type"], "reversal")

        checking_after = _get_balance(self.db_session, self.entity.id, "1.1.001")
        self.assertEqual(checking_after, Decimal("0.00"))

    def test_reverse_without_receivable_works(self):
        txn_id = self._post_deposit()
        resp = self.client.post(
            f"/entities/{self.entity_id}/transactions/{txn_id}/reverse",
            json={"reason": "no receivable"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 201)

    def test_reverse_with_receivable_cancels_it(self):
        sale_resp = self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json={
                "transaction_type": "sale",
                "effective_date": _EFFECTIVE_DATE,
                "entries": [
                    {"account_code": "1.1.001", "entry_type": "debit",  "amount": "97.70", "currency": "BRL"},
                    {"account_code": "3.1.001", "entry_type": "credit", "amount": "97.70", "currency": "BRL"},
                ],
                "receivable": {
                    "gross_amount": "100.00", "net_amount": "97.70", "fee_amount": "2.30",
                },
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(sale_resp.status_code, 201)
        txn_id = sale_resp.json()["id"]

        recv_list = self.client.get(f"/entities/{self.entity_id}/receivables")
        recv_id = recv_list.json()[0]["id"]

        resp = self.client.post(
            f"/entities/{self.entity_id}/transactions/{txn_id}/reverse",
            json={"reason": "chargeback", "custom_data": {"reversal_id": "rev_999"}},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 201)

        recv_detail = self.client.get(f"/entities/{self.entity_id}/receivables/{recv_id}")
        self.assertEqual(recv_detail.json()["status"], "cancelled")

    def test_reverse_nonexistent_transaction_returns_404(self):
        resp = self.client.post(
            f"/entities/{self.entity_id}/transactions/{uuid4()}/reverse",
            json={"reason": "test"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 404)

    def test_reverse_422_when_receivable_already_cancelled(self):
        sale_resp = self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json={
                "transaction_type": "sale",
                "effective_date": _EFFECTIVE_DATE,
                "entries": [
                    {"account_code": "1.1.001", "entry_type": "debit",  "amount": "97.70", "currency": "BRL"},
                    {"account_code": "3.1.001", "entry_type": "credit", "amount": "97.70", "currency": "BRL"},
                ],
                "receivable": {"gross_amount": "100.00", "net_amount": "97.70", "fee_amount": "2.30"},
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        txn_id = sale_resp.json()["id"]

        self.client.post(
            f"/entities/{self.entity_id}/transactions/{txn_id}/reverse",
            json={"reason": "first reversal"},
            headers={"Idempotency-Key": str(uuid4())},
        )

        resp = self.client.post(
            f"/entities/{self.entity_id}/transactions/{txn_id}/reverse",
            json={"reason": "second reversal"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 422)

    def test_reverse_idempotency(self):
        txn_id = self._post_deposit("100.00")
        idem_key = str(uuid4())
        payload = {"reason": "duplicate"}

        r1 = self.client.post(
            f"/entities/{self.entity_id}/transactions/{txn_id}/reverse",
            json=payload,
            headers={"Idempotency-Key": idem_key},
        )
        r2 = self.client.post(
            f"/entities/{self.entity_id}/transactions/{txn_id}/reverse",
            json=payload,
            headers={"Idempotency-Key": idem_key},
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json()["id"], r2.json()["id"])
