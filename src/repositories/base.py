from typing import Generic, List, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository(Generic[T]):
    def __init__(self, db: Session, model_class: Type[T]):
        self.db = db
        self.model_class = model_class

    def get_by_id(self, id: UUID) -> Optional[T]:
        return self.db.query(self.model_class).filter(self.model_class.id == id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        return self.db.query(self.model_class).offset(skip).limit(limit).all()

    def save(self, instance: T) -> T:
        self.db.add(instance)
        self.db.flush()
        return instance

    def delete(self, id: UUID) -> bool:
        entity = self.get_by_id(id)
        if not entity:
            return False
        self.db.delete(entity)
        self.db.flush()
        return True

    def exists(self, id: UUID) -> bool:
        return self.db.query(self.model_class).filter(self.model_class.id == id).first() is not None

    def list_by_field(self, field: str, value) -> List[T]:
        return self.db.query(self.model_class).filter(
            getattr(self.model_class, field) == value
        ).all()

    def get_by_field(self, field: str, value) -> Optional[T]:
        results = self.list_by_field(field, value)
        return results[0] if results else None
