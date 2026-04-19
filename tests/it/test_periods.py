from unittest import TestCase
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api import app
from src.config.database import get_db


class PeriodCreateITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_create_period_returns_201(self):
        response = self.client.post("/periods", json={"period_date": "2025-12-01"})
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["period_date"], "2025-12-01")
        self.assertEqual(data["status"], "open")
        self.assertIsNotNone(data["id"])
        self.assertIsNotNone(data["opened_at"])
        self.assertIsNone(data["closed_at"])

    def test_create_period_with_notes(self):
        response = self.client.post("/periods", json={"period_date": "2025-11-01", "notes": "November"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["notes"], "November")

    def test_create_duplicate_period_returns_409(self):
        self.client.post("/periods", json={"period_date": "2026-01-01"})
        response = self.client.post("/periods", json={"period_date": "2026-01-01"})
        self.assertEqual(response.status_code, 409)


class PeriodGetITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_get_period_returns_correct_data(self):
        created = self.client.post("/periods", json={"period_date": "2025-10-01"}).json()
        response = self.client.get(f"/periods/{created['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], created["id"])

    def test_get_period_not_found_returns_404(self):
        response = self.client.get(f"/periods/{uuid4()}")
        self.assertEqual(response.status_code, 404)


class PeriodListITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_list_periods_returns_list(self):
        self.client.post("/periods", json={"period_date": "2025-09-01"})
        response = self.client.get("/periods")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertGreaterEqual(len(response.json()), 1)

    def test_list_periods_with_pagination(self):
        self.client.post("/periods", json={"period_date": "2025-08-01"})
        response = self.client.get("/periods?page=0&limit=2")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()), 2)


class PeriodCloseITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_close_period_changes_status(self):
        created = self.client.post("/periods", json={"period_date": "2025-07-01"}).json()
        response = self.client.patch(f"/periods/{created['id']}/close", json={"closed_by": "admin"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "closed")
        self.assertIsNotNone(data["closed_at"])
        self.assertEqual(data["closed_by"], "admin")

    def test_close_already_closed_returns_422(self):
        created = self.client.post("/periods", json={"period_date": "2025-06-01"}).json()
        self.client.patch(f"/periods/{created['id']}/close", json={"closed_by": "admin"})
        response = self.client.patch(f"/periods/{created['id']}/close", json={"closed_by": "admin"})
        self.assertEqual(response.status_code, 422)

    def test_close_not_found_returns_404(self):
        response = self.client.patch(f"/periods/{uuid4()}/close", json={"closed_by": "admin"})
        self.assertEqual(response.status_code, 404)


class PeriodReopenITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_reopen_closed_period(self):
        created = self.client.post("/periods", json={"period_date": "2025-05-01"}).json()
        self.client.patch(f"/periods/{created['id']}/close", json={"closed_by": "admin"})
        response = self.client.patch(f"/periods/{created['id']}/reopen")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "open")

    def test_reopen_locked_period_returns_422(self):
        created = self.client.post("/periods", json={"period_date": "2025-04-01"}).json()
        self.client.patch(f"/periods/{created['id']}/close", json={"closed_by": "admin"})
        self.client.patch(f"/periods/{created['id']}/lock", json={"locked_by": "admin"})
        response = self.client.patch(f"/periods/{created['id']}/reopen")
        self.assertEqual(response.status_code, 422)

    def test_reopen_not_found_returns_404(self):
        response = self.client.patch(f"/periods/{uuid4()}/reopen")
        self.assertEqual(response.status_code, 404)


class PeriodLockITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_lock_closed_period(self):
        created = self.client.post("/periods", json={"period_date": "2025-03-01"}).json()
        self.client.patch(f"/periods/{created['id']}/close", json={"closed_by": "admin"})
        response = self.client.patch(f"/periods/{created['id']}/lock", json={"locked_by": "admin"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "locked")
        self.assertIsNotNone(data["locked_at"])
        self.assertEqual(data["locked_by"], "admin")

    def test_lock_locked_period_returns_422(self):
        created = self.client.post("/periods", json={"period_date": "2025-02-01"}).json()
        self.client.patch(f"/periods/{created['id']}/close", json={"closed_by": "admin"})
        self.client.patch(f"/periods/{created['id']}/lock", json={"locked_by": "admin"})
        response = self.client.patch(f"/periods/{created['id']}/lock", json={"locked_by": "admin"})
        self.assertEqual(response.status_code, 422)

    def test_lock_open_period_returns_422(self):
        created = self.client.post("/periods", json={"period_date": "2025-01-01"}).json()
        response = self.client.patch(f"/periods/{created['id']}/lock", json={"locked_by": "admin"})
        self.assertEqual(response.status_code, 422)

    def test_lock_not_found_returns_404(self):
        response = self.client.patch(f"/periods/{uuid4()}/lock", json={"locked_by": "admin"})
        self.assertEqual(response.status_code, 404)
