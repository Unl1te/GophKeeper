from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DataType, Item


async def create_item(
    db: AsyncSession,
    user_id: int,
    type: DataType,
    content: bytes,
    metadata: Optional[Dict[str, Any]] = None,
) -> Item:
    """Create a new item for the given user and persist it."""
    item = Item(
        user_id=user_id,
        type=type,
        content=content,
        metadata_=metadata or {},
        version=1,
        deleted=False,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def get_items_by_user(db: AsyncSession, user_id: int) -> List[Item]:
    """Return all non-deleted items belonging to the user."""
    result = await db.execute(
        select(Item)
        .where(Item.user_id == user_id, Item.deleted == False)
        .order_by(Item.id)
    )
    return list(result.scalars().all())


async def get_item_by_id(
    db: AsyncSession, item_id: int, user_id: int
) -> Optional[Item]:
    """Return a single non-deleted item by ID with ownership check, or None."""
    result = await db.execute(
        select(Item).where(
            Item.id == item_id,
            Item.user_id == user_id,
            Item.deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def update_item(
    db: AsyncSession,
    item_id: int,
    user_id: int,
    new_content: bytes,
    new_metadata: Optional[Dict[str, Any]],
    version: int,
) -> Item:
    """
    Update content and metadata of an item.
    Raises LookupError if item not found.
    Raises ValueError on version conflict.
    Increments version on success.
    """
    item = await get_item_by_id(db, item_id, user_id)
    if item is None:
        raise LookupError(f"Item {item_id} not found or not owned by you")

    if item.version != version:
        raise ValueError(
            f"Version conflict: server has version {item.version}, "
            f"you provided {version}"
        )

    item.content = new_content
    item.metadata_ = new_metadata if new_metadata is not None else item.metadata_
    item.version += 1
    item.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(item)
    return item


async def delete_item(db: AsyncSession, item_id: int, user_id: int) -> None:
    """
    Soft-delete an item by setting deleted=True.
    Raises LookupError if item not found.
    """
    item = await get_item_by_id(db, item_id, user_id)
    if item is None:
        raise LookupError(f"Item {item_id} not found or not owned by you")

    item.deleted = True
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()