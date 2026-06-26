from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.models import User, Item
from app.schemas.item import (
    ItemCreateRequest,
    ItemUpdateRequest,
    ItemResponse,
    ItemDetailResponse,
)
from pydantic import BaseModel

router = APIRouter(prefix="/items", tags=["Items"])


# ---- Sync schemas (embedded) ----
class SyncRequest(BaseModel):
    changes: List[Dict[str, Any]]  # list of local changes (id, version, content, metadata, deleted)


class SyncResponse(BaseModel):
    updates: List[Dict[str, Any]]  # list of server updates


@router.post("/", response_model=ItemDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    item_data: ItemCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new encrypted item for the authenticated user.
    """
    new_item = Item(
        user_id=current_user.id,
        type=item_data.type,
        content=item_data.content,
        version=1,
    )
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)

    return ItemDetailResponse(
        id=new_item.id,
        type=new_item.type,
        version=new_item.version,
        updated_at=new_item.updated_at,
        content=new_item.content,
        metadata={}  # stub until DB field is added
    )


@router.get("/", response_model=List[ItemResponse])
async def list_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a list of all items belonging to the authenticated user.
    Returns only id, type, version, updated_at (no content/metadata).
    """
    result = await db.execute(
        select(Item).where(Item.user_id == current_user.id).order_by(Item.id)
    )
    items = result.scalars().all()
    return [
        ItemResponse(
            id=item.id,
            type=item.type,
            version=item.version,
            updated_at=item.updated_at,
            metadata={},
        )
        for item in items
    ]


@router.get("/{item_id}", response_model=ItemDetailResponse)
async def get_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single item by ID (includes encrypted content).
    """
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
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
        metadata={},
    )


@router.put("/{item_id}", response_model=ItemDetailResponse)
async def update_item(
    item_id: int,
    update_data: ItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing item (requires correct version to avoid conflicts).
    If version mismatches, returns 409 Conflict.
    """
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found or not owned by you",
        )

    # Check version
    if item.version != update_data.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict: item has version {item.version}, but you provided {update_data.version}",
        )

    # Update content, ignore metadata for now
    item.content = update_data.content
    item.version += 1
    # updated_at will be auto-updated by SQLAlchemy onupdate

    await db.commit()
    await db.refresh(item)

    return ItemDetailResponse(
        id=item.id,
        type=item.type,
        version=item.version,
        updated_at=item.updated_at,
        content=item.content,
        metadata={},
    )


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hard delete an item (soft delete will be added when deleted flag is available).
    """
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found or not owned by you",
        )

    await db.delete(item)
    await db.commit()


@router.post("/sync", response_model=SyncResponse)
async def sync_items(
    sync_data: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Batch sync endpoint.
    Returns all items belonging to the user (full list, including content).
    In a real implementation, we'd filter by version to only return updates.
    """
    result = await db.execute(
        select(Item).where(Item.user_id == current_user.id).order_by(Item.id)
    )
    items = result.scalars().all()
    updates = [
        {
            "id": item.id,
            "version": item.version,
            "updated_at": item.updated_at.isoformat(),
            "content": item.content.hex(),  # base64 or hex; client will decode
            "metadata": {},  # stub
        }
        for item in items
    ]
    return SyncResponse(updates=updates)