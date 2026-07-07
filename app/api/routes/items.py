from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.models import User
from app.repositories import item_repository
from app.schemas.item import (
    ItemCreateRequest,
    ItemDetailResponse,
    ItemResponse,
    ItemUpdateRequest,
    SyncRequest,
    SyncResponse,
    SyncUpdateItem,
)

router = APIRouter(prefix="/items", tags=["Items"])


# ---- CREATE ----
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


# ---- LIST (with versions) ----
@router.get("/", response_model=list[ItemResponse])
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


# ---- VERSIONS (lightweight) ----
@router.get("/versions", response_model=list[dict])
async def get_items_versions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lightweight endpoint that returns only id, version, updated_at for all user items.
    Used by the CLI to check for changes without downloading full data.
    """
    items = await item_repository.get_items_versions(db=db, user_id=current_user.id)
    return [
        {
            "id": item.id,
            "version": item.version,
            "updated_at": item.updated_at,
        }
        for item in items
    ]


# ---- GET ONE ----
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


# ---- UPDATE (with version check) ----
@router.put("/{item_id}", response_model=ItemDetailResponse)
async def update_item(
    item_id: int,
    update_data: ItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing item.
    Returns 409 Conflict if the client version is stale.
    """
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
        # Conflict: client version does not match server version.
        # We can optionally include the current version in the response body.
        # We'll fetch the current item to get its version.
        current_item = await item_repository.get_item_by_id(
            db, item_id, current_user.id
        )
        if current_item is None:
            # Should not happen if LookupError was not raised, but just in case.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(e),
                "current_version": current_item.version,
            },
        )

    return ItemDetailResponse(
        id=item.id,
        type=item.type,
        version=item.version,
        updated_at=item.updated_at,
        content=item.content,
        metadata=item.metadata_,
    )


# ---- DELETE (soft delete) ----
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


# ---- INCREMENTAL SYNC ----
@router.post("/sync", response_model=SyncResponse)
async def sync_items(
    sync_data: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Incremental sync endpoint.
    Client sends a list of {id, version} it currently holds.
    Server returns only items where the server version is greater than the client version.
    """
    # If the client sends no items, we treat it as "send me everything" (since_version = 0).
    if not sync_data.items:
        # Return all items
        items = await item_repository.get_items_by_user(db=db, user_id=current_user.id)
        updates = [
            SyncUpdateItem(
                id=item.id,
                version=item.version,
                updated_at=item.updated_at,
                content=item.content,
                metadata=item.metadata_,
            )
            for item in items
        ]
        return SyncResponse(updates=updates)

    # For each item, we need to check if server version > client version.
    # We can use a set of ids to reduce the number of queries.
    # But we'll do a single query using a filter on version per item.
    # However, get_items_changed_since returns all items with version > since_version,
    # but that's global, not per item. That method is not suitable here.
    # Instead, we'll fetch all items for the user and filter in Python.
    # For a small number of items (<1000), this is fine.
    all_items = await item_repository.get_items_by_user(db=db, user_id=current_user.id)
    # Build a dict from client items
    client_versions = {item.id: item.version for item in sync_data.items}

    updates = []
    for item in all_items:
        client_version = client_versions.get(item.id, 0)
        if item.version > client_version:
            updates.append(
                SyncUpdateItem(
                    id=item.id,
                    version=item.version,
                    updated_at=item.updated_at,
                    content=item.content,
                    metadata=item.metadata_,
                )
            )

    return SyncResponse(updates=updates)
