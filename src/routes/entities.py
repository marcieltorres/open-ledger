from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.model.schemas.entities import EntityCreate, EntityResponse, EntityUpdate
from src.services.entity import EntityService
from src.services.errors import DuplicateEntityError, EntityNotFoundError

router = APIRouter(prefix="/entities", tags=["entities"])


@router.post("", status_code=201, response_model=EntityResponse)
def create_entity(payload: EntityCreate, session: Session = Depends(get_db)):
    service = EntityService(session)
    try:
        entity = service.create(payload)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return EntityResponse.model_validate(entity)


@router.get("", response_model=list[EntityResponse])
def list_entities(page: int = 0, limit: int = 100, session: Session = Depends(get_db)):
    service = EntityService(session)
    return [EntityResponse.model_validate(e) for e in service.list(skip=page * limit, limit=limit)]


@router.get("/{entity_id}", response_model=EntityResponse)
def get_entity(entity_id: UUID, session: Session = Depends(get_db)):
    service = EntityService(session)
    try:
        entity = service.get_by_id(entity_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return EntityResponse.model_validate(entity)


@router.patch("/{entity_id}", response_model=EntityResponse)
def update_entity(entity_id: UUID, payload: EntityUpdate, session: Session = Depends(get_db)):
    service = EntityService(session)
    try:
        entity = service.update(entity_id, payload)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return EntityResponse.model_validate(entity)
