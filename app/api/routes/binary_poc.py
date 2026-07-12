"""
Proof-of-concept endpoint for issue #31: MessagePack as a binary
alternative to JSON for the item create/get endpoints.

Deliberately a SEPARATE router, not a replacement of app/api/routes/items.py
— the goal at this stage is to demonstrate and measure the approach, not to
migrate the whole API. If it proves out, the natural next step is content
negotiation on the existing /items/ routes (Accept / Content-Type based)
rather than a parallel path — but that's a bigger, separate change.

Wire format: request and response bodies are MessagePack
(Content-Type: application/msgpack), with the same field names as the JSON
schemas (ItemCreateRequest / ItemDetailResponse) so client code only has to
swap the (de)serialization layer, not the data model.

The main win this demonstrates concretely: the existing JSON API transports
`content` as a hex string, which is exactly 2x the size of the raw
ciphertext. MessagePack has a native binary type, so `content` here is sent
as-is with only a few bytes of framing overhead — see
tests/test_binary_protocol_poc.py for the measured numbers.

To wire this in, add to app/main.py:

    from app.api.routes import binary_poc
    app.include_router(binary_poc.router)
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
import msgpack

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.models import DataType, User
from app.repositories import item_repository

router = APIRouter(prefix="/items-binary", tags=["Items (binary protocol POC)"])

MSGPACK_CONTENT_TYPE = "application/msgpack"


def _pack_item(item) -> bytes:
    return msgpack.packb(
        {
            "id": item.id,
            "type": item.type.value,
            "version": item.version,
            "updated_at": item.updated_at.isoformat(),
            "metadata": item.metadata_,
            "content": item.content,  # raw bytes -> msgpack's native bin type
        },
        use_bin_type=True,
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_item_binary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    MessagePack equivalent of POST /items/.

    Expected request Content-Type: application/msgpack
    Body: a msgpack map with keys:
        type (str, one of the DataType values)
        content (bin — raw ciphertext, NOT hex-encoded)
        metadata (map, optional)
    """
    raw_body = await request.body()
    try:
        payload = msgpack.unpackb(raw_body, raw=False)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid MessagePack body: {exc}")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Body must be a msgpack map")

    try:
        item_type = DataType(payload["type"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid or missing 'type': {exc}")

    content = payload.get("content")
    if not isinstance(content, (bytes, bytearray)):
        raise HTTPException(
            status_code=422,
            detail="'content' must be msgpack binary (bin), not a string",
        )

    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=422, detail="'metadata' must be a map")

    item = await item_repository.create_item(
        db=db,
        user_id=current_user.id,
        type=item_type,
        content=bytes(content),
        metadata=metadata,
    )

    return Response(content=_pack_item(item), media_type=MSGPACK_CONTENT_TYPE)


@router.get("/{item_id}")
async def get_item_binary(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """MessagePack equivalent of GET /items/{id}."""
    item = await item_repository.get_item_by_id(
        db=db, item_id=item_id, user_id=current_user.id
    )
    if item is None:
        raise HTTPException(
            status_code=404, detail="Item not found or not owned by you"
        )

    return Response(content=_pack_item(item), media_type=MSGPACK_CONTENT_TYPE)
