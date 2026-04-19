from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from src.exceptions.period import (
    DuplicatePeriodError,
    InvalidPeriodTransitionError,
    PeriodClosedError,
    PeriodNotFoundError,
)
from src.model.accounting_period import AccountingPeriod, PeriodStatus
from src.model.schemas.periods import PeriodCloseRequest, PeriodCreate, PeriodLockRequest
from src.services.period import PeriodService


def _make_period(**kwargs) -> AccountingPeriod:
    period = AccountingPeriod(
        period_date=kwargs.get("period_date", date(2025, 12, 1)),
        status=kwargs.get("status", PeriodStatus.open),
        opened_at=kwargs.get("opened_at", datetime.now(tz=timezone.utc)),
        closed_at=kwargs.get("closed_at", None),
        locked_at=kwargs.get("locked_at", None),
        closed_by=kwargs.get("closed_by", None),
        locked_by=kwargs.get("locked_by", None),
        notes=kwargs.get("notes", None),
    )
    period.id = kwargs.get("id", uuid4())
    return period


class PeriodServiceCreateTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = PeriodService(self.session)
        self.service._repo = MagicMock()

    def test_create_period(self):
        period = _make_period()
        self.service._repo.save.return_value = period
        result = self.service.create(PeriodCreate(period_date=date(2025, 12, 1)))
        self.service._repo.save.assert_called_once()
        self.assertEqual(result, period)

    def test_create_period_with_notes(self):
        period = _make_period(notes="fiscal year end")
        self.service._repo.save.return_value = period
        result = self.service.create(PeriodCreate(period_date=date(2025, 12, 1), notes="fiscal year end"))
        self.assertIsNotNone(result)

    def test_create_duplicate_raises(self):
        self.service._repo.save.side_effect = IntegrityError(None, None, None)
        with self.assertRaises(DuplicatePeriodError):
            self.service.create(PeriodCreate(period_date=date(2025, 12, 1)))
        self.session.rollback.assert_called_once()


class PeriodServiceGetByIdTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = PeriodService(self.session)
        self.service._repo = MagicMock()

    def test_get_by_id_returns_period(self):
        period = _make_period()
        self.service._repo.get_by_id.return_value = period
        self.assertEqual(self.service.get_by_id(period.id), period)

    def test_get_by_id_not_found_raises(self):
        self.service._repo.get_by_id.return_value = None
        with self.assertRaises(PeriodNotFoundError):
            self.service.get_by_id(uuid4())


class PeriodServiceValidateOpenTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = PeriodService(self.session)
        self.service._repo = MagicMock()

    def test_validate_open_passes_for_open_period(self):
        self.service._repo.get_open_for_date.return_value = _make_period()
        self.service.validate_open(date(2025, 12, 1))

    def test_validate_open_raises_when_no_open_period(self):
        self.service._repo.get_open_for_date.return_value = None
        with self.assertRaises(PeriodClosedError):
            self.service.validate_open(date(2025, 12, 1))


class PeriodServiceCloseTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = PeriodService(self.session)
        self.service._repo = MagicMock()

    def test_close_open_period(self):
        period = _make_period(status=PeriodStatus.open)
        self.service._repo.get_by_id.return_value = period
        self.service._repo.save.return_value = period
        result = self.service.close(period.id, PeriodCloseRequest(closed_by="admin"))
        self.assertEqual(result.status, PeriodStatus.closed)
        self.assertIsNotNone(result.closed_at)
        self.assertEqual(result.closed_by, "admin")

    def test_close_closed_period_raises(self):
        period = _make_period(status=PeriodStatus.closed)
        self.service._repo.get_by_id.return_value = period
        with self.assertRaises(InvalidPeriodTransitionError):
            self.service.close(period.id, PeriodCloseRequest(closed_by="admin"))

    def test_close_locked_period_raises(self):
        period = _make_period(status=PeriodStatus.locked)
        self.service._repo.get_by_id.return_value = period
        with self.assertRaises(InvalidPeriodTransitionError):
            self.service.close(period.id, PeriodCloseRequest(closed_by="admin"))


class PeriodServiceReopenTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = PeriodService(self.session)
        self.service._repo = MagicMock()

    def test_reopen_closed_period(self):
        period = _make_period(status=PeriodStatus.closed)
        self.service._repo.get_by_id.return_value = period
        self.service._repo.save.return_value = period
        result = self.service.reopen(period.id)
        self.assertEqual(result.status, PeriodStatus.open)
        self.assertIsNone(result.closed_at)
        self.assertIsNone(result.closed_by)

    def test_reopen_locked_period_raises(self):
        period = _make_period(status=PeriodStatus.locked)
        self.service._repo.get_by_id.return_value = period
        with self.assertRaises(InvalidPeriodTransitionError):
            self.service.reopen(period.id)

    def test_reopen_open_period_raises(self):
        period = _make_period(status=PeriodStatus.open)
        self.service._repo.get_by_id.return_value = period
        with self.assertRaises(InvalidPeriodTransitionError):
            self.service.reopen(period.id)


class PeriodServiceLockTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = PeriodService(self.session)
        self.service._repo = MagicMock()

    def test_lock_closed_period(self):
        period = _make_period(status=PeriodStatus.closed)
        self.service._repo.get_by_id.return_value = period
        self.service._repo.save.return_value = period
        result = self.service.lock(period.id, PeriodLockRequest(locked_by="admin"))
        self.assertEqual(result.status, PeriodStatus.locked)
        self.assertIsNotNone(result.locked_at)
        self.assertEqual(result.locked_by, "admin")

    def test_lock_locked_period_raises(self):
        period = _make_period(status=PeriodStatus.locked)
        self.service._repo.get_by_id.return_value = period
        with self.assertRaises(InvalidPeriodTransitionError):
            self.service.lock(period.id, PeriodLockRequest(locked_by="admin"))

    def test_lock_open_period_raises(self):
        period = _make_period(status=PeriodStatus.open)
        self.service._repo.get_by_id.return_value = period
        with self.assertRaises(InvalidPeriodTransitionError):
            self.service.lock(period.id, PeriodLockRequest(locked_by="admin"))
