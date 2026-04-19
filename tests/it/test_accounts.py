from unittest import TestCase
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api import app
from src.config.database import get_db


class AccountProvisionITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)
        resp = self.client.post("/entities", json={"external_id": f"ext-{uuid4()}"})
        self.entity_id = resp.json()["id"]

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_provision_merchant_template_returns_15_accounts(self):
        response = self.client.post(f"/entities/{self.entity_id}/accounts", json={"template": "merchant"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()), 15)

    def test_provision_inline_accounts(self):
        response = self.client.post(
            f"/entities/{self.entity_id}/accounts",
            json={"accounts": [
                {"code": "1.1.001", "name": "Receivables", "account_type": "asset"},
                {"code": "9.9.999", "name": "World", "account_type": "equity"},
            ]},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()), 2)

    def test_provision_same_accounts_twice_is_idempotent(self):
        payload = {"accounts": [{"code": "1.1.001", "name": "Receivables", "account_type": "asset"}]}
        r1 = self.client.post(f"/entities/{self.entity_id}/accounts", json=payload)
        r2 = self.client.post(f"/entities/{self.entity_id}/accounts", json=payload)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json()[0]["id"], r2.json()[0]["id"])

    def test_provision_entity_not_found_returns_404(self):
        response = self.client.post(f"/entities/{uuid4()}/accounts", json={"template": "merchant"})
        self.assertEqual(response.status_code, 404)

    def test_provision_invalid_template_returns_422(self):
        response = self.client.post(f"/entities/{self.entity_id}/accounts", json={"template": "invalid"})
        self.assertEqual(response.status_code, 422)


class AccountListITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)
        resp = self.client.post("/entities", json={"external_id": f"ext-{uuid4()}"})
        self.entity_id = resp.json()["id"]

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_list_accounts_returns_empty_before_provision(self):
        response = self.client.get(f"/entities/{self.entity_id}/accounts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_list_accounts_after_provision_has_zero_balance(self):
        self.client.post(f"/entities/{self.entity_id}/accounts", json={"template": "merchant"})
        response = self.client.get(f"/entities/{self.entity_id}/accounts")
        self.assertEqual(response.status_code, 200)
        for account in response.json():
            self.assertEqual(float(account["current_balance"]), 0.0)

    def test_list_accounts_entity_not_found_returns_404(self):
        response = self.client.get(f"/entities/{uuid4()}/accounts")
        self.assertEqual(response.status_code, 404)


class AccountGetITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)
        resp = self.client.post("/entities", json={"external_id": f"ext-{uuid4()}"})
        self.entity_id = resp.json()["id"]

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_get_account_returns_correct_data(self):
        accounts = self.client.post(
            f"/entities/{self.entity_id}/accounts",
            json={"accounts": [{"code": "1.1.001", "name": "Receivables", "account_type": "asset"}]},
        ).json()
        account_id = accounts[0]["id"]
        response = self.client.get(f"/entities/{self.entity_id}/accounts/{account_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], account_id)

    def test_get_account_not_found_returns_404(self):
        response = self.client.get(f"/entities/{self.entity_id}/accounts/{uuid4()}")
        self.assertEqual(response.status_code, 404)


class AccountUpdateITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)
        resp = self.client.post("/entities", json={"external_id": f"ext-{uuid4()}"})
        self.entity_id = resp.json()["id"]

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_update_account_name(self):
        accounts = self.client.post(
            f"/entities/{self.entity_id}/accounts",
            json={"accounts": [{"code": "1.1.001", "name": "Receivables", "account_type": "asset"}]},
        ).json()
        account_id = accounts[0]["id"]
        response = self.client.patch(
            f"/entities/{self.entity_id}/accounts/{account_id}", json={"name": "New Name"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "New Name")

    def test_update_account_not_found_returns_404(self):
        response = self.client.patch(
            f"/entities/{self.entity_id}/accounts/{uuid4()}", json={"name": "X"}
        )
        self.assertEqual(response.status_code, 404)
