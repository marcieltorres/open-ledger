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

_EFFECTIVE_DATE = "2026-04-21"
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
        ChartOfAccounts(entity_id=entity_id, code="1.1.001", name="Receivables",
                        account_type=AccountType.asset, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="3.1.001", name="Revenue",
                        account_type=AccountType.revenue, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="4.1.001", name="MDR Expense",
                        account_type=AccountType.expense, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="4.1.002", name="Fee Expense",
                        account_type=AccountType.expense, currency="BRL"),
    ]
    for a in accounts:
        session.add(a)
    session.flush()
    return accounts


def _open_period(session, period_date: date):
    period = AccountingPeriod(
        period_date=period_date, status=PeriodStatus.open, opened_at=datetime.now(timezone.utc)
    )
    session.add(period)
    session.flush()
    return period


class ReceivableCreateITTest(TestCase):
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

    def _post_transaction(self, receivable_payload=None, idempotency_key=None):
        payload = {
            "transaction_type": "sale",
            "effective_date": _EFFECTIVE_DATE,
            "entries": _SALE_ENTRIES,
        }
        if receivable_payload is not None:
            payload["receivable"] = receivable_payload
        headers = {"Idempotency-Key": idempotency_key or str(uuid4())}
        return self.client.post(f"/entities/{self.entity_id}/transactions", json=payload, headers=headers)

    def test_post_transaction_with_receivable_creates_pending_receivable(self):
        recv_payload = {
            "gross_amount": "100.00",
            "net_amount": "97.70",
            "fee_amount": "2.30",
            "expected_settlement_date": "2026-05-01",
        }
        resp = self._post_transaction(receivable_payload=recv_payload)
        self.assertEqual(resp.status_code, 201)

        txn_id = resp.json()["id"]

        recv_list = self.client.get(f"/entities/{self.entity_id}/receivables")
        self.assertEqual(recv_list.status_code, 200)
        items = recv_list.json()
        self.assertEqual(len(items), 1)
        recv_id = items[0]["id"]
        self.assertEqual(items[0]["status"], "pending")
        self.assertEqual(items[0]["transaction_id"], txn_id)

        recv_detail = self.client.get(f"/entities/{self.entity_id}/receivables/{recv_id}")
        self.assertEqual(recv_detail.status_code, 200)
        data = recv_detail.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(Decimal(data["gross_amount"]), Decimal("100.00"))
        self.assertEqual(Decimal(data["net_amount"]), Decimal("97.70"))
        self.assertEqual(Decimal(data["fee_amount"]), Decimal("2.30"))
        self.assertEqual(data["expected_settlement_date"], "2026-05-01")

    def test_post_transaction_without_receivable_creates_no_receivable(self):
        resp = self._post_transaction()
        self.assertEqual(resp.status_code, 201)

        recv_list = self.client.get(f"/entities/{self.entity_id}/receivables")
        self.assertEqual(recv_list.status_code, 200)
        self.assertEqual(recv_list.json(), [])

    def test_get_receivable_wrong_entity_returns_404(self):
        recv_payload = {
            "gross_amount": "100.00",
            "net_amount": "97.70",
            "fee_amount": "2.30",
        }
        resp = self._post_transaction(receivable_payload=recv_payload)
        self.assertEqual(resp.status_code, 201)

        recv_list = self.client.get(f"/entities/{self.entity_id}/receivables")
        recv_id = recv_list.json()[0]["id"]

        other_entity = Entity(external_id=f"ext-{uuid4()}")
        self.db_session.add(other_entity)
        self.db_session.flush()

        resp = self.client.get(f"/entities/{other_entity.id}/receivables/{recv_id}")
        self.assertEqual(resp.status_code, 404)

    def test_list_receivables_filter_by_status(self):
        recv_payload = {
            "gross_amount": "100.00",
            "net_amount": "97.70",
            "fee_amount": "2.30",
        }
        self._post_transaction(receivable_payload=recv_payload)
        self._post_transaction(receivable_payload=recv_payload)

        pending_list = self.client.get(f"/entities/{self.entity_id}/receivables?status=pending")
        self.assertEqual(pending_list.status_code, 200)
        self.assertEqual(len(pending_list.json()), 2)

        settled_list = self.client.get(f"/entities/{self.entity_id}/receivables?status=settled")
        self.assertEqual(settled_list.status_code, 200)
        self.assertEqual(settled_list.json(), [])

    def test_gross_net_fee_stored_exactly(self):
        recv_payload = {
            "gross_amount": "100.00",
            "net_amount": "97.70",
            "fee_amount": "2.30",
        }
        self._post_transaction(receivable_payload=recv_payload)

        recv_list = self.client.get(f"/entities/{self.entity_id}/receivables")
        data = recv_list.json()[0]
        self.assertEqual(Decimal(data["gross_amount"]), Decimal("100.00"))
        self.assertEqual(Decimal(data["net_amount"]), Decimal("97.70"))
        self.assertEqual(Decimal(data["fee_amount"]), Decimal("2.30"))
