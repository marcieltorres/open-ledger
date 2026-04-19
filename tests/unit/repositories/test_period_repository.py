from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from src.model.accounting_period import AccountingPeriod, PeriodStatus
from src.repositories.period import PeriodRepository


def _make_period(**kwargs) -> AccountingPeriod:
    period = AccountingPeriod(
        period_date=kwargs.get("period_date", date(2025, 12, 1)),
        status=kwargs.get("status", PeriodStatus.open),
        opened_at=kwargs.get("opened_at", datetime.now(tz=timezone.utc)),
    )
    period.id = kwargs.get("id", uuid4())
    return period


class PeriodRepositoryGetOpenForDateTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.repo = PeriodRepository(self.session)

    def test_returns_open_period_for_date(self):
        period = _make_period()
        self.session.query.return_value.filter.return_value.first.return_value = period
        result = self.repo.get_open_for_date(date(2025, 12, 1))
        self.assertEqual(result, period)

    def test_returns_none_when_no_open_period(self):
        self.session.query.return_value.filter.return_value.first.return_value = None
        result = self.repo.get_open_for_date(date(2025, 12, 1))
        self.assertIsNone(result)
