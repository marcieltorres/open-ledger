class PeriodNotFoundError(Exception):
    pass


class PeriodClosedError(Exception):
    pass


class InvalidPeriodTransitionError(Exception):
    pass


class DuplicatePeriodError(Exception):
    pass
