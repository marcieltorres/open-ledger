from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.exceptions.period import PeriodClosedError
from src.exceptions.transaction import AccountCodeNotFoundError, CurrencyMismatchError, DoubleEntryImbalanceError
from src.exceptions.transfer import TransferAccountNotFoundError, TransferEntityNotFoundError
from src.model.schemas.transactions import TransactionResponse
from src.model.schemas.transfers import TransferCreate, TransferResponse
from src.services.transfer import TransferService

router = APIRouter(prefix="/transfers", tags=["transfers"])

_UNPROCESSABLE = (
    PeriodClosedError,
    AccountCodeNotFoundError,
    CurrencyMismatchError,
    DoubleEntryImbalanceError,
    TransferEntityNotFoundError,
    TransferAccountNotFoundError,
)


@router.post("", status_code=201, response_model=TransferResponse)
def create_transfer(
    payload: TransferCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_db),
):
    service = TransferService(session)
    try:
        sender_txn, receiver_txn = service.transfer(payload, idempotency_key)
    except _UNPROCESSABLE as e:
        raise HTTPException(status_code=422, detail=str(e))
    return TransferResponse(
        sender_transaction=TransactionResponse.model_validate(sender_txn),
        receiver_transaction=TransactionResponse.model_validate(receiver_txn),
    )
