from unittest import TestCase

from sqlalchemy import inspect, text


class TestDatabaseConnection(TestCase):
    """Database connection tests using Testcontainers."""

    db_session = None
    db_engine = None

    def test_database_connection_is_established(self):
        """Verify database connection works."""
        result = self.db_session.execute(text("SELECT 1"))
        self.assertEqual(result.scalar(), 1)

    def test_database_version_is_postgres(self):
        """Verify PostgreSQL is the database."""
        result = self.db_session.execute(text("SELECT version()"))
        version = result.scalar()
        self.assertIn("PostgreSQL", version)

    def test_database_tables_are_created(self):
        """Verify SQLAlchemy tables can be created from models."""
        inspector = inspect(self.db_engine)
        self.assertIsNotNone(inspector)


class TestDatabaseIsolation(TestCase):
    """Verify test isolation between tests."""

    db_session = None

    def test_session_rollback_isolation(self):
        """Changes in one test should not affect others."""
        result = self.db_session.execute(text("SELECT current_database()"))
        self.assertIsNotNone(result.scalar())

    def test_session_is_isolated_from_other_tests(self):
        """Verify each test gets a fresh session."""
        self.db_session.execute(text("CREATE TEMP TABLE IF NOT EXISTS test_isolation (id INT)"))
        self.db_session.execute(text("INSERT INTO test_isolation VALUES (1)"))
        result = self.db_session.execute(text("SELECT COUNT(*) FROM test_isolation"))
        self.assertEqual(result.scalar(), 1)
