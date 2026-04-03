from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, class_mapper, mapped_column


class BaseModel(DeclarativeBase):
    """Base model for all models"""

    id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        unique=True,
        nullable=False,
        default=uuid4,
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
        server_default=func.now(),
    )

    def to_dict(self):
        def convert_value(value):
            if isinstance(value, UUID):
                return str(value)
            elif isinstance(value, (date, datetime)):
                return value.isoformat()
            return value

        data = map(
            lambda col: (col.key, convert_value(getattr(self, col.key))),
            class_mapper(self.__class__).columns,
        )
        return dict(data)


model_metadata = BaseModel.metadata
