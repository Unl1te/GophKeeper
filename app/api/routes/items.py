from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.models import User
from app.schemas.item import (
    ItemCreateRequest,
    ItemUpdateRequest,
    ItemResponse,
    ItemDetailResponse,
)
from app.repositories import item_repository
from pydantic import BaseModel

router = APIRouter(prefix="/items", tags=["Items"])


# ---- Sync schemas (embedded) ----
class SyncRequest(BaseModel):
    changes: List[Dict[str, Any]]


class SyncResponse(BaseModel):
    updates: List[Dict[str, Any]]


@router.post(
    "/", response_model=ItemDetailResponse, status_code=status.HTTP_201_CREATED
)
async def create_item(
    item_data: ItemCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new encrypted item for the authenticated user."""
    item = await item_repository.create_item(
        db=db,
        user_id=current_user.id,
        type=item_data.type,
        content=item_data.content,
        metadata=item_data.metadata,
    )
    return ItemDetailResponse(
        id=item.id,
        type=item.type,
        version=item.version,
        updated_at=item.updated_at,
        content=item.content,
        metadata=item.metadata_,
    )


@router.get("/", response_model=List[ItemResponse])
async def list_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all non-deleted items for the authenticated user (no content)."""
    items = await item_repository.get_items_by_user(db=db, user_id=current_user.id)
    return [
        ItemResponse(
            id=item.id,
            type=item.type,
            version=item.version,
            updated_at=item.updated_at,
            metadata=item.metadata_,
        )
        for item in items
    ]


@router.get("/{item_id}", response_model=ItemDetailResponse)
async def get_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single item by ID (includes encrypted content)."""
    item = await item_repository.get_item_by_id(
        db=db, item_id=item_id, user_id=current_user.id
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found or not owned by you",
        )
    return ItemDetailResponse(
        id=item.id,
        type=item.type,
        version=item.version,
        updated_at=item.updated_at,
        content=item.content,
        metadata=item.metadata_,
    )


@router.put("/{item_id}", response_model=ItemDetailResponse)
async def update_item(
    item_id: int,
    update_data: ItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing item. Returns 409 on version conflict."""
    try:
        item = await item_repository.update_item(
            db=db,
            item_id=item_id,
            user_id=current_user.id,
            new_content=update_data.content,
            new_metadata=update_data.metadata,
            version=update_data.version,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return ItemDetailResponse(
        id=item.id,
        type=item.type,
        version=item.version,
        updated_at=item.updated_at,
        content=item.content,
        metadata=item.metadata_,
    )


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete an item (sets deleted=True, data is not removed from DB)."""
    try:
        await item_repository.delete_item(
            db=db, item_id=item_id, user_id=current_user.id
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/sync", response_model=SyncResponse)
async def sync_items(
    sync_data: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch sync: returns all non-deleted items for the user."""
    items = await item_repository.get_items_by_user(db=db, user_id=current_user.id)
    updates = [
        {
            "id": item.id,
            "version": item.version,
            "updated_at": item.updated_at.isoformat(),
            "content": item.content.hex(),
            "metadata": item.metadata_,
        }
        for item in items
    ]
    return SyncResponse(updates=updates)