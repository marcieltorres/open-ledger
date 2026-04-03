from datetime import date, datetime, timezone
from unittest import TestCase
from uuid import UUID

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from src.model.base_model import BaseModel


class ConcreteModel(BaseModel):
    """Concrete model for testing BaseModel."""

    __tablename__ = "concrete_model"

    name: Mapped[str] = mapped_column(String(100), nullable=False)


class ModelWithDate(BaseModel):
    """Model with date column for testing."""

    __tablename__ = "model_with_date"

    birth_date: Mapped[date] = mapped_column(Date, nullable=True)


class BaseModelTest(TestCase):
    def test_to_dict_converts_uuid_to_string(self):
        model = ConcreteModel(name="test")
        model.id = UUID("12345678-1234-5678-1234-567812345678")
        model.created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        model.updated_at = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

        result = model.to_dict()

        self.assertEqual(result["id"], "12345678-1234-5678-1234-567812345678")

    def test_to_dict_converts_datetime_to_isoformat(self):
        model = ConcreteModel(name="test")
        model.id = UUID("12345678-1234-5678-1234-567812345678")
        model.created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        model.updated_at = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

        result = model.to_dict()

        self.assertEqual(result["created_at"], "2024-01-01T12:00:00+00:00")
        self.assertEqual(result["updated_at"], "2024-01-02T12:00:00+00:00")

    def test_to_dict_includes_all_columns(self):
        model = ConcreteModel(name="test_name")
        model.id = UUID("12345678-1234-5678-1234-567812345678")
        model.created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        model.updated_at = None

        result = model.to_dict()

        self.assertIn("id", result)
        self.assertIn("name", result)
        self.assertIn("created_at", result)
        self.assertIn("updated_at", result)
        self.assertEqual(result["name"], "test_name")
        self.assertIsNone(result["updated_at"])

    def test_to_dict_converts_date_to_isoformat(self):
        model = ModelWithDate()
        model.id = UUID("12345678-1234-5678-1234-567812345678")
        model.created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        model.updated_at = None
        model.birth_date = date(1990, 5, 15)

        result = model.to_dict()

        self.assertEqual(result["birth_date"], "1990-05-15")
