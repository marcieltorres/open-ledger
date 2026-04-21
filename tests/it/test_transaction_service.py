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

_EFFECTIVE_DATE = "2026-04-20"
_SALE_ENTRIES = [
    {"account_code": "1.1.001", "entry_type": "debit",  "amount": "100.00", "currency": "BRL"},
    {"account_code": "3.1.001", "entry_type": "credit", "amount": "100.00", "currency": "BRL"},
    {"account_code": "4.1.001", "entry_type": "debit",  "amount":   "2.00", "currency": "BRL"},
    {"account_code": "1.1.001", "entry_type": "credit", "amount":   "2.00", "currency": "BRL"},
    {"account_code": "4.1.002", "entry_type": "debit",  "amount":   "0.30", "currency": "BRL"},
    {"account_code": "1.1.001", "entry_type": "credit", "amount":   "0.30", "currency": "BRL"},
]


def _provision_accounts(session, entity_id):
    accounts = [
        ChartOfAccounts(entity_id=entity_id, code="1.1.001", name="Receivables", account_type=AccountType.asset, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="3.1.001", name="Revenue",     account_type=AccountType.revenue, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="4.1.001", name="MDR Expense", account_type=AccountType.expense, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="4.1.002", name="Fee Expense", account_type=AccountType.expense, currency="BRL"),
    ]
    for a in accounts:
        session.add(a)
    session.flush()
    return accounts


def _open_period(session, period_date: date):
    period = AccountingPeriod(period_date=period_date, status=PeriodStatus.open, opened_at=datetime.now(timezone.utc))
    session.add(period)
    session.flush()
    return period


class TransactionPostITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

        entity = Entity(external_id=f"ext-{uuid4()}")
        self.db_session.add(entity)
        self.db_session.flush()
        self.entity_id = str(entity.id)

        _provision_accounts(self.db_session, entity.id)
        _open_period(self.db_session, date.fromisoformat(_EFFECTIVE_DATE))

    def tearDown(self):
        app.dependency_overrides.clear()

    def _post(self, entries=None, idempotency_key=None, headers=None):
        payload = {
            "transaction_type": "sale",
            "effective_date": _EFFECTIVE_DATE,
            "entries": entries or _SALE_ENTRIES,
        }
        h = {"Idempotency-Key": idempotency_key or str(uuid4())}
        if headers:
            h.update(headers)
        return self.client.post(f"/entities/{self.entity_id}/transactions", json=payload, headers=h)

    def test_sale_creates_transaction_with_correct_balance(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 201)
        txn_id = resp.json()["id"]

        detail = self.client.get(f"/entities/{self.entity_id}/transactions/{txn_id}")
        self.assertEqual(detail.status_code, 200)
        data = detail.json()
        self.assertEqual(len(data["entries"]), 6)

        accounts = self.client.get(f"/entities/{self.entity_id}/accounts").json()
        balances = {a["code"]: Decimal(a["current_balance"]) for a in accounts}
        self.assertEqual(balances["1.1.001"], Decimal("97.70"))
        self.assertEqual(balances["3.1.001"], Decimal("100.00"))
        self.assertEqual(balances["4.1.001"], Decimal("2.00"))
        self.assertEqual(balances["4.1.002"], Decimal("0.30"))

    def test_missing_idempotency_key_returns_422(self):
        payload = {"transaction_type": "sale", "effective_date": _EFFECTIVE_DATE, "entries": _SALE_ENTRIES}
        resp = self.client.post(f"/entities/{self.entity_id}/transactions", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_duplicate_idempotency_key_is_idempotent(self):
        key = str(uuid4())
        r1 = self._post(idempotency_key=key)
        r2 = self._post(idempotency_key=key)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json()["id"], r2.json()["id"])

    def test_currency_mismatch_returns_422(self):
        entries = [
            {"account_code": "1.1.001", "entry_type": "debit",  "amount": "100.00", "currency": "USD"},
            {"account_code": "3.1.001", "entry_type": "credit", "amount": "100.00", "currency": "USD"},
        ]
        resp = self._post(entries=entries)
        self.assertEqual(resp.status_code, 422)

    def test_closed_period_returns_422(self):
        entries = [
            {"account_code": "1.1.001", "entry_type": "debit",  "amount": "10.00", "currency": "BRL"},
            {"account_code": "3.1.001", "entry_type": "credit", "amount": "10.00", "currency": "BRL"},
        ]
        payload = {"transaction_type": "sale", "effective_date": "2020-01-01", "entries": entries}
        resp = self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json=payload,
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 422)

    def test_unknown_account_code_returns_422(self):
        entries = [
            {"account_code": "9.9.000", "entry_type": "debit",  "amount": "10.00", "currency": "BRL"},
            {"account_code": "9.9.001", "entry_type": "credit", "amount": "10.00", "currency": "BRL"},
        ]
        resp = self._post(entries=entries)
        self.assertEqual(resp.status_code, 422)


class TransactionListGetITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

        entity = Entity(external_id=f"ext-{uuid4()}")
        self.db_session.add(entity)
        self.db_session.flush()
        self.entity_id = str(entity.id)

        _provision_accounts(self.db_session, entity.id)
        _open_period(self.db_session, date.fromisoformat(_EFFECTIVE_DATE))

    def tearDown(self):
        app.dependency_overrides.clear()

    def _post_sale(self):
        return self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json={"transaction_type": "sale", "effective_date": _EFFECTIVE_DATE, "entries": _SALE_ENTRIES},
            headers={"Idempotency-Key": str(uuid4())},
        )

    def test_list_returns_posted_transactions(self):
        self._post_sale()
        self._post_sale()
        resp = self.client.get(f"/entities/{self.entity_id}/transactions")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_get_not_found_returns_404(self):
        resp = self.client.get(f"/entities/{self.entity_id}/transactions/{uuid4()}")
        self.assertEqual(resp.status_code, 404)
