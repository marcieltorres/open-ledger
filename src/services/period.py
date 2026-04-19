from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.exceptions.period import (
    DuplicatePeriodError,
    InvalidPeriodTransitionError,
    PeriodClosedError,
    PeriodNotFoundError,
)
from src.model.accounting_period import AccountingPeriod, PeriodStatus
from src.model.schemas.periods import PeriodCloseRequest, PeriodCreate, PeriodLockRequest
from src.repositories.period import PeriodRepository


class PeriodService:
    def __init__(self, session: Session) -> None:
        self._repo = PeriodRepository(session)
        self._session = session

    def create(self, payload: PeriodCreate) -> AccountingPeriod:
        period = AccountingPeriod(
            period_date=payload.period_date,
            status=PeriodStatus.open,
            opened_at=datetime.now(tz=timezone.utc),
            notes=payload.notes,
        )
        try:
            return self._repo.save(period)
        except IntegrityError:
            self._session.rollback()
            raise DuplicatePeriodError(f"Period for date '{payload.period_date}' already exists")

    def list(self, skip: int = 0, limit: int = 100) -> list[AccountingPeriod]:
        return self._repo.get_all(skip=skip, limit=limit)

    def get_by_id(self, period_id: UUID) -> AccountingPeriod:
        period = self._repo.get_by_id(period_id)
        if period is None:
            raise PeriodNotFoundError(f"Period '{period_id}' not found")
        return period

    def validate_open(self, period_date: date) -> None:
        period = self._repo.get_open_for_date(period_date)
        if period is None:
            raise PeriodClosedError(f"No open period for date '{period_date}'")

    def close(self, period_id: UUID, payload: PeriodCloseRequest) -> AccountingPeriod:
        period = self.get_by_id(period_id)
        if period.status != PeriodStatus.open:
            raise InvalidPeriodTransitionError(f"Cannot close period with status '{period.status}'")
        period.status = PeriodStatus.closed
        period.closed_at = datetime.now(tz=timezone.utc)
        period.closed_by = payload.closed_by
        if payload.notes is not None:
            period.notes = payload.notes
        return self._repo.save(period)

    def reopen(self, period_id: UUID) -> AccountingPeriod:
        period = self.get_by_id(period_id)
        if period.status != PeriodStatus.closed:
            raise InvalidPeriodTransitionError(f"Cannot reopen period with status '{period.status}'")
        period.status = PeriodStatus.open
        period.closed_at = None
        period.closed_by = None
        return self._repo.save(period)

    def lock(self, period_id: UUID, payload: PeriodLockRequest) -> AccountingPeriod:
        period = self.get_by_id(period_id)
        if period.status != PeriodStatus.closed:
            raise InvalidPeriodTransitionError(f"Cannot lock period with status '{period.status}'")
        period.status = PeriodStatus.locked
        period.locked_at = datetime.now(tz=timezone.utc)
        period.locked_by = payload.locked_by
        return self._repo.save(period)
