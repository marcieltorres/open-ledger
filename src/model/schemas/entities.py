from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.model.entity import Entity


class EntityCreate(BaseModel):
    external_id: str
    name: str | None = None
    parent_entity_id: UUID | None = None
    custom_data: dict | None = None

    def to_model(self) -> Entity:
        return Entity(**self.model_dump())


class EntityUpdate(BaseModel):
    name: str | None = None
    custom_data: dict | None = None


class EntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str
    name: str | None
    parent_entity_id: UUID | None
    enabled: bool
    custom_data: dict | None
    created_at: datetime
    updated_at: datetime | None
