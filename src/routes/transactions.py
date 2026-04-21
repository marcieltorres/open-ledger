from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.exceptions.period import PeriodClosedError
from src.exceptions.transaction import (
    AccountCodeNotFoundError,
    CurrencyMismatchError,
    DoubleEntryImbalanceError,
    TransactionNotFoundError,
)
from src.model.schemas.transactions import TransactionCreate, TransactionDetailResponse, TransactionResponse
from src.services.transaction import TransactionService

router = APIRouter(prefix="/entities", tags=["transactions"])


@router.post("/{entity_id}/transactions", status_code=201, response_model=TransactionResponse)
def create_transaction(
    entity_id: UUID,
    payload: TransactionCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_db),
):
    service = TransactionService(session)
    try:
        transaction = service.post(entity_id, payload, idempotency_key)
    except (PeriodClosedError, AccountCodeNotFoundError, CurrencyMismatchError, DoubleEntryImbalanceError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return TransactionResponse.model_validate(transaction)


@router.get("/{entity_id}/transactions", response_model=list[TransactionResponse])
def list_transactions(entity_id: UUID, page: int = 0, limit: int = 100, session: Session = Depends(get_db)):
    transactions = TransactionService(session).list_by_entity(entity_id, skip=page * limit, limit=limit)
    return [TransactionResponse.model_validate(t) for t in transactions]


@router.get("/{entity_id}/transactions/{transaction_id}", response_model=TransactionDetailResponse)
def get_transaction(entity_id: UUID, transaction_id: UUID, session: Session = Depends(get_db)):
    service = TransactionService(session)
    try:
        transaction = service.get_by_id(entity_id, transaction_id)
    except TransactionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return TransactionDetailResponse.model_validate(transaction)
