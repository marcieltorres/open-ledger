from unittest import TestCase
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api import app
from src.config.database import get_db


class EntityCreateITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_create_entity_returns_201(self):
        response = self.client.post("/entities", json={"external_id": f"ext-{uuid4()}", "name": "ACME"})
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "ACME")
        self.assertTrue(data["enabled"])
        self.assertIsNotNone(data["id"])

    def test_create_entity_with_custom_data(self):
        response = self.client.post(
            "/entities",
            json={"external_id": f"ext-{uuid4()}", "custom_data": {"type": "merchant"}},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["custom_data"], {"type": "merchant"})

    def test_create_entity_duplicate_external_id_returns_409(self):
        external_id = f"ext-{uuid4()}"
        self.client.post("/entities", json={"external_id": external_id})
        response = self.client.post("/entities", json={"external_id": external_id})
        self.assertEqual(response.status_code, 409)

    def test_create_entity_with_valid_parent(self):
        parent = self.client.post("/entities", json={"external_id": f"parent-{uuid4()}"}).json()
        response = self.client.post(
            "/entities",
            json={"external_id": f"child-{uuid4()}", "parent_entity_id": parent["id"]},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["parent_entity_id"], parent["id"])

    def test_create_entity_with_invalid_parent_returns_404(self):
        response = self.client.post(
            "/entities",
            json={"external_id": f"ext-{uuid4()}", "parent_entity_id": str(uuid4())},
        )
        self.assertEqual(response.status_code, 404)


class EntityGetITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_get_entity_returns_correct_data(self):
        created = self.client.post("/entities", json={"external_id": f"ext-{uuid4()}", "name": "Shop"}).json()
        response = self.client.get(f"/entities/{created['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], created["id"])
        self.assertEqual(response.json()["name"], "Shop")

    def test_get_entity_not_found_returns_404(self):
        response = self.client.get(f"/entities/{uuid4()}")
        self.assertEqual(response.status_code, 404)


class EntityListITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_list_entities_returns_list(self):
        self.client.post("/entities", json={"external_id": f"ext-{uuid4()}"})
        response = self.client.get("/entities")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertGreaterEqual(len(response.json()), 1)

    def test_list_entities_with_pagination(self):
        for _ in range(3):
            self.client.post("/entities", json={"external_id": f"ext-{uuid4()}"})
        response = self.client.get("/entities?page=0&limit=2")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()), 2)


class EntityUpdateITTest(TestCase):
    db_session = None

    def setUp(self):
        app.dependency_overrides[get_db] = lambda: self.db_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_update_entity_name(self):
        created = self.client.post("/entities", json={"external_id": f"ext-{uuid4()}", "name": "Old"}).json()
        response = self.client.patch(f"/entities/{created['id']}", json={"name": "New"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "New")

    def test_update_entity_not_found_returns_404(self):
        response = self.client.patch(f"/entities/{uuid4()}", json={"name": "New"})
        self.assertEqual(response.status_code, 404)
