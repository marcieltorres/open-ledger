from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.exceptions.period import DuplicatePeriodError, InvalidPeriodTransitionError, PeriodNotFoundError
from src.model.schemas.periods import PeriodCloseRequest, PeriodCreate, PeriodLockRequest, PeriodResponse
from src.services.period import PeriodService

router = APIRouter(prefix="/periods", tags=["periods"])


@router.post("", status_code=201, response_model=PeriodResponse)
def create_period(payload: PeriodCreate, session: Session = Depends(get_db)):
    service = PeriodService(session)
    try:
        period = service.create(payload)
    except DuplicatePeriodError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return PeriodResponse.model_validate(period)


@router.get("", response_model=list[PeriodResponse])
def list_periods(page: int = 0, limit: int = 100, session: Session = Depends(get_db)):
    service = PeriodService(session)
    return [PeriodResponse.model_validate(p) for p in service.list(skip=page * limit, limit=limit)]


@router.get("/{period_id}", response_model=PeriodResponse)
def get_period(period_id: UUID, session: Session = Depends(get_db)):
    service = PeriodService(session)
    try:
        period = service.get_by_id(period_id)
    except PeriodNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return PeriodResponse.model_validate(period)


@router.patch("/{period_id}/close", response_model=PeriodResponse)
def close_period(period_id: UUID, payload: PeriodCloseRequest, session: Session = Depends(get_db)):
    service = PeriodService(session)
    try:
        period = service.close(period_id, payload)
    except PeriodNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidPeriodTransitionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return PeriodResponse.model_validate(period)


@router.patch("/{period_id}/reopen", response_model=PeriodResponse)
def reopen_period(period_id: UUID, session: Session = Depends(get_db)):
    service = PeriodService(session)
    try:
        period = service.reopen(period_id)
    except PeriodNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidPeriodTransitionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return PeriodResponse.model_validate(period)


@router.patch("/{period_id}/lock", response_model=PeriodResponse)
def lock_period(period_id: UUID, payload: PeriodLockRequest, session: Session = Depends(get_db)):
    service = PeriodService(session)
    try:
        period = service.lock(period_id, payload)
    except PeriodNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidPeriodTransitionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return PeriodResponse.model_validate(period)
