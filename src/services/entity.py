from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.model.entity import Entity
from src.model.schemas.entities import EntityCreate, EntityUpdate
from src.repositories.base import BaseRepository
from src.services.errors import DuplicateEntityError, EntityNotFoundError


class EntityService:
    def __init__(self, session: Session) -> None:
        self._repo: BaseRepository[Entity] = BaseRepository(session, Entity)
        self._session = session

    def create(self, payload: EntityCreate) -> Entity:
        if payload.parent_entity_id is not None and not self._repo.exists(payload.parent_entity_id):
            raise EntityNotFoundError(f"Entity '{payload.parent_entity_id}' not found")
        try:
            return self._repo.save(payload.to_model())
        except IntegrityError:
            self._session.rollback()
            raise DuplicateEntityError(f"Entity with external_id '{payload.external_id}' already exists")

    def get_by_id(self, entity_id: UUID) -> Entity:
        entity = self._repo.get_by_id(entity_id)
        if entity is None:
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        return entity

    def list(self, skip: int = 0, limit: int = 100) -> list[Entity]:
        return self._repo.get_all(skip=skip, limit=limit)

    def update(self, entity_id: UUID, payload: EntityUpdate) -> Entity:
        entity = self.get_by_id(entity_id)
        for field, value in payload.model_dump().items():
            if value is not None:
                setattr(entity, field, value)
        return self._repo.save(entity)
