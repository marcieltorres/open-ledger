from unittest import TestCase

from fastapi.testclient import TestClient

from src.api import app


class ApiITTest(TestCase):
    def setUp(self):
        self.client_api = TestClient(app)

    def test_when_i_call_health_check_should_be_success(self):
        response = self.client_api.get("/health-check")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "OK"})
