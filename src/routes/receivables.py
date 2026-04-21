from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.exceptions.receivable import ReceivableNotFoundError
from src.model.schemas.receivables import ReceivableResponse
from src.services.receivable import ReceivableService

router = APIRouter(prefix="/entities", tags=["receivables"])


@router.get("/{entity_id}/receivables", response_model=list[ReceivableResponse])
def list_receivables(entity_id: UUID, status: str | None = None, session: Session = Depends(get_db)):
    service = ReceivableService(session)
    return [ReceivableResponse.model_validate(r) for r in service.list_by_entity(entity_id, status=status)]


@router.get("/{entity_id}/receivables/{receivable_id}", response_model=ReceivableResponse)
def get_receivable(entity_id: UUID, receivable_id: UUID, session: Session = Depends(get_db)):
    service = ReceivableService(session)
    try:
        r = service.get_by_id(entity_id, receivable_id)
    except ReceivableNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ReceivableResponse.model_validate(r)
