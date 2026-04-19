from datetime import date

from sqlalchemy.orm import Session

from src.model.accounting_period import AccountingPeriod, PeriodStatus
from src.repositories.base import BaseRepository


class PeriodRepository(BaseRepository[AccountingPeriod]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AccountingPeriod)

    def get_open_for_date(self, period_date: date) -> AccountingPeriod | None:
        return (
            self.db.query(AccountingPeriod)
            .filter(AccountingPeriod.period_date == period_date, AccountingPeriod.status == PeriodStatus.open)
            .first()
        )
