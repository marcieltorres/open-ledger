from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.exceptions.period import PeriodClosedError
from src.exceptions.receivable import InvalidReceivableStatusTransitionError, ReceivableNotFoundError
from src.exceptions.transaction import (
    AccountCodeNotFoundError,
    CurrencyMismatchError,
    DoubleEntryImbalanceError,
    InvalidStatusTransitionError,
    TransactionNotFoundError,
)
from src.model.schemas.anticipations import AnticipationCreate
from src.model.schemas.deposits import DepositCreate
from src.model.schemas.reversals import ReversalCreate
from src.model.schemas.settlements import SettlementCreate
from src.model.schemas.transactions import TransactionCreate, TransactionDetailResponse, TransactionResponse
from src.model.schemas.withdrawals import WithdrawalCreate
from src.services.transaction import TransactionService

router = APIRouter(prefix="/entities", tags=["transactions"])

_UNPROCESSABLE = (PeriodClosedError, AccountCodeNotFoundError, CurrencyMismatchError, DoubleEntryImbalanceError)
_UNPROCESSABLE_WITH_RECV = (
    PeriodClosedError,
    AccountCodeNotFoundError,
    CurrencyMismatchError,
    DoubleEntryImbalanceError,
    InvalidReceivableStatusTransitionError,
)


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
    except _UNPROCESSABLE as e:
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


@router.post("/{entity_id}/anticipations", status_code=201, response_model=TransactionResponse)
def create_anticipation(
    entity_id: UUID,
    payload: AnticipationCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_db),
):
    service = TransactionService(session)
    try:
        transaction = service.anticipate(entity_id, payload, idempotency_key)
    except _UNPROCESSABLE as e:
        raise HTTPException(status_code=422, detail=str(e))
    return TransactionResponse.model_validate(transaction)


@router.post("/{entity_id}/settlements", status_code=201, response_model=TransactionResponse)
def create_settlement(
    entity_id: UUID,
    payload: SettlementCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_db),
):
    service = TransactionService(session)
    try:
        transaction = service.settle(entity_id, payload, idempotency_key)
    except ReceivableNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except _UNPROCESSABLE_WITH_RECV as e:
        raise HTTPException(status_code=422, detail=str(e))
    return TransactionResponse.model_validate(transaction)


@router.post("/{entity_id}/deposits", status_code=201, response_model=TransactionResponse)
def create_deposit(
    entity_id: UUID,
    payload: DepositCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_db),
):
    service = TransactionService(session)
    try:
        transaction = service.deposit(entity_id, payload, idempotency_key)
    except _UNPROCESSABLE as e:
        raise HTTPException(status_code=422, detail=str(e))
    return TransactionResponse.model_validate(transaction)


@router.post("/{entity_id}/withdrawals", status_code=201, response_model=TransactionResponse)
def create_withdrawal(
    entity_id: UUID,
    payload: WithdrawalCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_db),
):
    service = TransactionService(session)
    try:
        transaction = service.withdraw(entity_id, payload, idempotency_key)
    except _UNPROCESSABLE as e:
        raise HTTPException(status_code=422, detail=str(e))
    return TransactionResponse.model_validate(transaction)


@router.post("/{entity_id}/transactions/{txn_id}/void", response_model=TransactionResponse)
def void_transaction(entity_id: UUID, txn_id: UUID, session: Session = Depends(get_db)):
    service = TransactionService(session)
    try:
        transaction = service.void(entity_id, txn_id)
    except TransactionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return TransactionResponse.model_validate(transaction)


@router.post("/{entity_id}/transactions/{txn_id}/reverse", status_code=201, response_model=TransactionResponse)
def reverse_transaction(
    entity_id: UUID,
    txn_id: UUID,
    payload: ReversalCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_db),
):
    service = TransactionService(session)
    try:
        transaction = service.reverse(entity_id, txn_id, payload, idempotency_key)
    except TransactionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except _UNPROCESSABLE_WITH_RECV as e:
        raise HTTPException(status_code=422, detail=str(e))
    return TransactionResponse.model_validate(transaction)
