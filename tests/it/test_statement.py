from datetime import date
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api import app
from src.config.database import get_db
from src.model.account_balance_snapshot import AccountBalanceSnapshot
from src.model.chart_of_accounts import AccountType, ChartOfAccounts
from src.model.entity import Entity

_DATE = "2025-12-10"


def _make_entity(session) -> Entity:
    entity = Entity(external_id=f"ext-{uuid4()}")
    session.add(entity)
    session.flush()
    return entity


def _provision_accounts(session, entity_id) -> dict[str, ChartOfAccounts]:
    accounts = [
        ChartOfAccounts(entity_id=entity_id, code="1.1.001", name="Receivables",
                        account_type=AccountType.ASSET, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="3.1.001", name="Revenue",
                        account_type=AccountType.REVENUE, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="9.9.902", name="World/CIP-PIX",
                        account_type=AccountType.ASSET, currency="BRL"),
        ChartOfAccounts(entity_id=entity_id, code="9.9.999", name="World",
                        account_type=AccountType.ASSET, currency="BRL"),
    ]
    for a in accounts:
        session.add(a)
    session.flush()
    return {a.code: a for a in accounts}


class GetBalanceITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)
        self.entity = _make_entity(self.db_session)
        self.entity_id = str(self.entity.id)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_balance_with_no_accounts_returns_zero(self):
        response = self.client.get(f"/entities/{self.entity_id}/balance")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entity_id"], self.entity_id)
        self.assertEqual(Decimal(data["balance"]), Decimal("0"))
        self.assertIsNotNone(data["as_of"])

    def test_balance_only_sums_asset_accounts(self):
        _provision_accounts(self.db_session, self.entity.id)
        self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json={
                "transaction_type": "SALE",
                "effective_date": _DATE,
                "entries": [
                    {"account_code": "1.1.001", "entry_type": "DEBIT", "amount": "100.00", "currency": "BRL"},
                    {"account_code": "3.1.001", "entry_type": "CREDIT", "amount": "100.00", "currency": "BRL"},
                ],
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        response = self.client.get(f"/entities/{self.entity_id}/balance")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(Decimal(data["balance"]), Decimal("100.00"))
        codes = {item["code"] for item in data["breakdown"]}
        self.assertIn("1.1.001", codes)
        self.assertNotIn("3.1.001", codes)

    def test_balance_with_as_of_returns_historical(self):
        _provision_accounts(self.db_session, self.entity.id)
        self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json={
                "transaction_type": "SALE",
                "effective_date": _DATE,
                "entries": [
                    {"account_code": "1.1.001", "entry_type": "DEBIT", "amount": "200.00", "currency": "BRL"},
                    {"account_code": "3.1.001", "entry_type": "CREDIT", "amount": "200.00", "currency": "BRL"},
                ],
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        response = self.client.get(f"/entities/{self.entity_id}/balance", params={"as_of": "2025-12-09"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(Decimal(data["balance"]), Decimal("0"))
        self.assertEqual(data["as_of"], "2025-12-09")

    def test_balance_future_date_returns_422(self):
        response = self.client.get(f"/entities/{self.entity_id}/balance", params={"as_of": "2099-01-01"})
        self.assertEqual(response.status_code, 422)

    def test_balance_unknown_entity_returns_404(self):
        response = self.client.get(f"/entities/{uuid4()}/balance")
        self.assertEqual(response.status_code, 404)


class GetStatementITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)
        self.entity = _make_entity(self.db_session)
        self.entity_id = str(self.entity.id)
        _provision_accounts(self.db_session, self.entity.id)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_empty_period_returns_zero_summary(self):
        response = self.client.get(
            f"/entities/{self.entity_id}/statement",
            params={"start_date": "2025-12-01", "end_date": "2025-12-31"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(Decimal(data["summary"]["opening_balance"]), Decimal("0"))
        self.assertEqual(Decimal(data["summary"]["closing_balance"]), Decimal("0"))
        self.assertEqual(data["entries"], [])

    def test_statement_after_sale_shows_correct_entry(self):
        self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json={
                "transaction_type": "SALE",
                "effective_date": _DATE,
                "entries": [
                    {"account_code": "1.1.001", "entry_type": "DEBIT", "amount": "100.00", "currency": "BRL"},
                    {"account_code": "3.1.001", "entry_type": "CREDIT", "amount": "100.00", "currency": "BRL"},
                ],
            },
            headers={"Idempotency-Key": str(uuid4())},
        )

        response = self.client.get(
            f"/entities/{self.entity_id}/statement",
            params={"start_date": "2025-12-01", "end_date": "2025-12-31"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(Decimal(data["summary"]["total_in"]), Decimal("100.00"))
        self.assertEqual(Decimal(data["summary"]["total_out"]), Decimal("0"))
        self.assertEqual(Decimal(data["summary"]["closing_balance"]), Decimal("100.00"))
        self.assertEqual(Decimal(data["entries"][0]["balance_after"]), Decimal("100.00"))

    def test_statement_uses_snapshot_as_opening_balance(self):
        accounts = self.db_session.query(ChartOfAccounts).filter(
            ChartOfAccounts.entity_id == self.entity.id,
            ChartOfAccounts.code == "1.1.001",
        ).first()
        snapshot = AccountBalanceSnapshot(
            account_id=accounts.id,
            snapshot_date=date(2025, 11, 30),
            balance=Decimal("500.00"),
        )
        self.db_session.add(snapshot)
        self.db_session.flush()

        response = self.client.get(
            f"/entities/{self.entity_id}/statement",
            params={"start_date": "2025-12-01", "end_date": "2025-12-31"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(Decimal(data["summary"]["opening_balance"]), Decimal("500.00"))
        self.assertEqual(Decimal(data["summary"]["closing_balance"]), Decimal("500.00"))

    def test_statement_period_and_entity_id_in_response(self):
        response = self.client.get(
            f"/entities/{self.entity_id}/statement",
            params={"start_date": "2025-12-01", "end_date": "2025-12-31"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entity_id"], self.entity_id)
        self.assertEqual(data["period"]["start_date"], "2025-12-01")
        self.assertEqual(data["period"]["end_date"], "2025-12-31")

    def test_statement_unknown_entity_returns_404(self):
        response = self.client.get(
            f"/entities/{uuid4()}/statement",
            params={"start_date": "2025-12-01", "end_date": "2025-12-31"},
        )
        self.assertEqual(response.status_code, 404)

    def test_statement_entries_outside_period_excluded(self):
        self.client.post(
            f"/entities/{self.entity_id}/transactions",
            json={
                "transaction_type": "SALE",
                "effective_date": _DATE,
                "entries": [
                    {"account_code": "1.1.001", "entry_type": "DEBIT", "amount": "75.00", "currency": "BRL"},
                    {"account_code": "3.1.001", "entry_type": "CREDIT", "amount": "75.00", "currency": "BRL"},
                ],
            },
            headers={"Idempotency-Key": str(uuid4())},
        )

        response = self.client.get(
            f"/entities/{self.entity_id}/statement",
            params={"start_date": "2025-11-01", "end_date": "2025-11-30"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entries"], [])
        self.assertEqual(Decimal(data["summary"]["total_in"]), Decimal("0"))
