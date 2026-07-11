from datetime import datetime
from typing import Any, Dict, List, Optional

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


# ---- Sync schemas ----
class SyncItemVersion(BaseModel):
    id: int
    version: int


class SyncRequest(BaseModel):
    items: List[SyncItemVersion]


class SyncUpdateItem(BaseModel):
    id: int
    version: int
    updated_at: datetime
    content: bytes
    metadata: Optional[Dict[str, Any]] = None


class SyncResponse(BaseModel):
    updates: List[SyncUpdateItem]
