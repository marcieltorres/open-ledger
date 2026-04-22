from pydantic import BaseModel


class ReversalCreate(BaseModel):
    reason: str
    custom_data: dict | None = None
