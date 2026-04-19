from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.model.schemas.accounts import AccountProvision, AccountResponse, AccountUpdate
from src.model.schemas.entities import EntityCreate, EntityResponse, EntityUpdate
from src.services.account import AccountService
from src.services.entity import EntityService
from src.services.errors import AccountNotFoundError, DuplicateEntityError, EntityNotFoundError, InvalidTemplateError

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


@router.post("/{entity_id}/accounts", status_code=201, response_model=list[AccountResponse])
def provision_accounts(entity_id: UUID, payload: AccountProvision, session: Session = Depends(get_db)):
    service = AccountService(session)
    try:
        accounts = service.provision(entity_id, payload)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTemplateError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return [AccountResponse.model_validate(a) for a in accounts]


@router.get("/{entity_id}/accounts", response_model=list[AccountResponse])
def list_accounts(entity_id: UUID, session: Session = Depends(get_db)):
    service = AccountService(session)
    try:
        accounts = service.list_by_entity(entity_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return [AccountResponse.model_validate(a) for a in accounts]


@router.get("/{entity_id}/accounts/{account_id}", response_model=AccountResponse)
def get_account(entity_id: UUID, account_id: UUID, session: Session = Depends(get_db)):
    service = AccountService(session)
    try:
        account = service.get_by_id(entity_id, account_id)
    except (EntityNotFoundError, AccountNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return AccountResponse.model_validate(account)


@router.patch("/{entity_id}/accounts/{account_id}", response_model=AccountResponse)
def update_account(entity_id: UUID, account_id: UUID, payload: AccountUpdate, session: Session = Depends(get_db)):
    service = AccountService(session)
    try:
        account = service.update(entity_id, account_id, payload)
    except (EntityNotFoundError, AccountNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return AccountResponse.model_validate(account)
