from unittest import TestCase
from unittest.mock import MagicMock, patch


class DatabaseTest(TestCase):
    def test_get_db_commits_and_closes_on_success(self):
        mock_db = MagicMock()
        with patch("src.config.database.SessionLocal", return_value=mock_db):
            from src.config.database import get_db

            gen = get_db()
            session = next(gen)
            self.assertIs(session, mock_db)
            try:
                next(gen)
            except StopIteration:
                pass
            mock_db.commit.assert_called_once()
            mock_db.close.assert_called_once()

    def test_get_db_rollbacks_and_closes_on_exception(self):
        mock_db = MagicMock()
        with patch("src.config.database.SessionLocal", return_value=mock_db):
            from src.config.database import get_db

            gen = get_db()
            next(gen)
            with self.assertRaises(ValueError):
                gen.throw(ValueError("boom"))
            mock_db.rollback.assert_called_once()
            mock_db.close.assert_called_once()
