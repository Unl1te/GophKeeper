from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.models.models import DataType


class ItemCreateRequest(BaseModel):
    type: DataType
    content: bytes
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ItemUpdateRequest(BaseModel):
    content: bytes
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    version: int


class ItemResponse(BaseModel):
    id: int
    type: DataType
    version: int
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None


class ItemDetailResponse(ItemResponse):
    content: bytes


class ItemVersionResponse(BaseModel):
    """Lightweight response for /items/versions — no content, no metadata."""
    id: int
    version: int
    updated_at: datetime
    