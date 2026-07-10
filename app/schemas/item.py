from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from app.models.models import DataType
from app.core.validators import is_valid_otp_secret


class ItemCreateRequest(BaseModel):
    type: DataType
    content: bytes
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @validator("content")
    def validate_otp_content(cls, v, values):
        if values.get("type") == DataType.otp:
            if not is_valid_otp_secret(v):
                raise ValueError(
                    "OTP secret must be a valid base32-encoded string (minimum 16 bytes after decoding)"
                )
        return v


class ItemUpdateRequest(BaseModel):
    content: bytes
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    version: int

    @validator("content")
    def validate_otp_content(cls, v, values):
        # For update, we don't have the type in the request, so we can't validate.
        # Validation will be done at the repository/endpoint level if needed.
        # We'll skip validation here for simplicity; the endpoint can fetch the item type.
        return v


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
