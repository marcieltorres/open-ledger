from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api import app
from src.config.database import get_db
from src.model.chart_of_accounts import ChartOfAccounts
from src.model.entity import Entity
from src.model.enums import AccountType

_EFFECTIVE_DATE = "2026-04-21"


def _make_entity(session):
    entity = Entity(external_id=f"ext-{uuid4()}")
    session.add(entity)
    session.flush()
    return entity


def _provision_entity_accounts(session, entity_id, include_transfer: bool = True):
    accounts = [
        ChartOfAccounts(
            entity_id=entity_id, code="1.1.001", name="Checking",
            account_type=AccountType.ASSET, currency="BRL",
            current_balance=Decimal("500.00"),
        ),
    ]
    if include_transfer:
        accounts.append(
            ChartOfAccounts(
                entity_id=entity_id, code="9.9.998", name="Transfer",
                account_type=AccountType.ASSET, currency="BRL",
            )
        )
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


class TransferITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

        self.sender = _make_entity(self.db_session)
        self.receiver = _make_entity(self.db_session)
        _provision_entity_accounts(self.db_session, self.sender.id)
        _provision_entity_accounts(self.db_session, self.receiver.id)

    def tearDown(self):
        app.dependency_overrides.clear()

    def _post_transfer(self, amount="100.00", idem_key=None, sender_id=None, receiver_id=None):
        return self.client.post(
            "/transfers",
            json={
                "sender_entity_id": str(sender_id or self.sender.id),
                "receiver_entity_id": str(receiver_id or self.receiver.id),
                "amount": amount,
                "currency": "BRL",
                "effective_date": _EFFECTIVE_DATE,
                "description": "test PIX transfer",
            },
            headers={"Idempotency-Key": idem_key or str(uuid4())},
        )

    def test_transfer_decreases_sender_checking_increases_receiver_checking(self):
        resp = self._post_transfer(amount="100.00")
        self.assertEqual(resp.status_code, 201, resp.text)

        sender_balance = _get_balance(self.db_session, self.sender.id, "1.1.001")
        receiver_balance = _get_balance(self.db_session, self.receiver.id, "1.1.001")

        self.assertEqual(sender_balance, Decimal("400.00"))
        self.assertEqual(receiver_balance, Decimal("600.00"))

    def test_transfer_account_9998_net_zero_across_both_entities(self):
        self._post_transfer(amount="250.00")

        sender_transfer_balance = _get_balance(self.db_session, self.sender.id, "9.9.998")
        receiver_transfer_balance = _get_balance(self.db_session, self.receiver.id, "9.9.998")

        self.assertEqual(sender_transfer_balance + receiver_transfer_balance, Decimal("0.00"))

    def test_response_contains_sender_and_receiver_transactions(self):
        resp = self._post_transfer(amount="75.00")
        self.assertEqual(resp.status_code, 201)

        body = resp.json()
        self.assertIn("sender_transaction", body)
        self.assertIn("receiver_transaction", body)
        self.assertEqual(body["sender_transaction"]["transaction_type"], "transfer")
        self.assertEqual(body["receiver_transaction"]["transaction_type"], "transfer")
        self.assertEqual(body["sender_transaction"]["entity_id"], str(self.sender.id))
        self.assertEqual(body["receiver_transaction"]["entity_id"], str(self.receiver.id))

    def test_idempotent_second_request_returns_same_result(self):
        idem_key = str(uuid4())
        resp1 = self._post_transfer(amount="100.00", idem_key=idem_key)
        resp2 = self._post_transfer(amount="100.00", idem_key=idem_key)

        self.assertEqual(resp1.status_code, 201)
        self.assertEqual(resp2.status_code, 201)
        self.assertEqual(
            resp1.json()["sender_transaction"]["id"],
            resp2.json()["sender_transaction"]["id"],
        )
        # Balance unchanged after duplicate
        sender_balance = _get_balance(self.db_session, self.sender.id, "1.1.001")
        self.assertEqual(sender_balance, Decimal("400.00"))

    def test_nonexistent_receiver_entity_returns_422(self):
        resp = self._post_transfer(receiver_id=uuid4())
        self.assertEqual(resp.status_code, 422)

    def test_nonexistent_sender_entity_returns_422(self):
        resp = self._post_transfer(sender_id=uuid4())
        self.assertEqual(resp.status_code, 422)

    def test_sender_without_transfer_account_returns_422(self):
        no_transfer_entity = _make_entity(self.db_session)
        _provision_entity_accounts(self.db_session, no_transfer_entity.id, include_transfer=False)

        resp = self._post_transfer(sender_id=no_transfer_entity.id)
        self.assertEqual(resp.status_code, 422)

    def test_receiver_without_transfer_account_returns_422(self):
        no_transfer_entity = _make_entity(self.db_session)
        _provision_entity_accounts(self.db_session, no_transfer_entity.id, include_transfer=False)

        resp = self._post_transfer(receiver_id=no_transfer_entity.id)
        self.assertEqual(resp.status_code, 422)

    def test_negative_balance_sender_is_allowed(self):
        # Ledger does not block on negative balance — upstream responsibility
        resp = self._post_transfer(amount="10000.00")
        self.assertEqual(resp.status_code, 201)

        sender_balance = _get_balance(self.db_session, self.sender.id, "1.1.001")
        self.assertEqual(sender_balance, Decimal("-9500.00"))
