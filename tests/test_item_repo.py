"""
Tests for app.repositories.item_repository.

Strategy: the AsyncSession is fully mocked (AsyncMock/MagicMock) so these tests
don't need a real database. `db.execute(...)` is mocked to return an object
whose `.scalars().all()` / `.scalar_one_or_none()` behave like SQLAlchemy
results. For functions that internally call `get_item_by_id`, we monkeypatch
that function directly on the module to keep tests focused and avoid
duplicating the "how db.execute results look" plumbing.

If your actual `DataType` enum uses different member names than the ones
guessed below (`password`, `text`, ...), adjust `TEST_TYPE` accordingly -
everything else in the file is independent of the concrete enum values.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.models import DataType, Item
from app.repositories import item_repository as repo

# Pick some concrete enum member defensively, in case naming differs slightly.
TEST_TYPE = getattr(DataType, "password", next(iter(DataType)))


def make_mock_db():
    """A bare AsyncSession mock: add/commit/refresh/execute are all mocked."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def make_execute_result(scalars_all=None, scalar_one_or_none=None):
    """Builds a fake object mimicking the return value of `await db.execute(...)`."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = scalars_all if scalars_all is not None else []
    result.scalars.return_value = scalars_mock
    result.scalar_one_or_none.return_value = scalar_one_or_none
    return result


def make_item(**overrides):
    defaults = dict(
        id=1,
        user_id=42,
        type=TEST_TYPE,
        content=b"encrypted-bytes",
        metadata_={"note": "test"},
        version=1,
        deleted=False,
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    item = Item(
        user_id=defaults["user_id"],
        type=defaults["type"],
        content=defaults["content"],
        metadata_=defaults["metadata_"],
        version=defaults["version"],
        deleted=defaults["deleted"],
    )
    item.id = defaults["id"]
    item.updated_at = defaults["updated_at"]
    return item


# ---------------------------------------------------------------------------
# create_item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_item_persists_item_with_expected_fields():
    db = make_mock_db()

    result = await repo.create_item(
        db,
        user_id=7,
        type=TEST_TYPE,
        content=b"hello",
        metadata={"k": "v"},
    )

    db.add.assert_called_once()
    added_item = db.add.call_args[0][0]
    assert added_item.user_id == 7
    assert added_item.type == TEST_TYPE
    assert added_item.content == b"hello"
    assert added_item.metadata_ == {"k": "v"}
    assert added_item.version == 1
    assert added_item.deleted is False

    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(added_item)
    assert result is added_item


@pytest.mark.asyncio
async def test_create_item_defaults_metadata_to_empty_dict_when_none():
    db = make_mock_db()

    result = await repo.create_item(db, user_id=1, type=TEST_TYPE, content=b"x")

    assert result.metadata_ == {}


# ---------------------------------------------------------------------------
# get_items_by_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_items_by_user_returns_items():
    db = make_mock_db()
    items = [make_item(id=1), make_item(id=2)]
    db.execute.return_value = make_execute_result(scalars_all=items)

    result = await repo.get_items_by_user(db, user_id=42)

    assert result == items
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_items_by_user_returns_empty_list_when_no_items():
    db = make_mock_db()
    db.execute.return_value = make_execute_result(scalars_all=[])

    result = await repo.get_items_by_user(db, user_id=42)

    assert result == []


# ---------------------------------------------------------------------------
# get_item_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_item_by_id_found():
    db = make_mock_db()
    item = make_item(id=5)
    db.execute.return_value = make_execute_result(scalar_one_or_none=item)

    result = await repo.get_item_by_id(db, item_id=5, user_id=42)

    assert result is item


@pytest.mark.asyncio
async def test_get_item_by_id_not_found_returns_none():
    db = make_mock_db()
    db.execute.return_value = make_execute_result(scalar_one_or_none=None)

    result = await repo.get_item_by_id(db, item_id=999, user_id=42)

    assert result is None


# ---------------------------------------------------------------------------
# update_item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_item_success_increments_version_and_updates_fields(monkeypatch):
    db = make_mock_db()
    existing = make_item(id=1, version=3, metadata_={"old": "meta"})
    monkeypatch.setattr(repo, "get_item_by_id", AsyncMock(return_value=existing))

    result = await repo.update_item(
        db,
        item_id=1,
        user_id=42,
        new_content=b"new-content",
        new_metadata={"new": "meta"},
        version=3,
    )

    assert result.content == b"new-content"
    assert result.metadata_ == {"new": "meta"}
    assert result.version == 4
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(existing)


@pytest.mark.asyncio
async def test_update_item_keeps_old_metadata_when_new_metadata_is_none(monkeypatch):
    db = make_mock_db()
    existing = make_item(version=1, metadata_={"keep": "me"})
    monkeypatch.setattr(repo, "get_item_by_id", AsyncMock(return_value=existing))

    result = await repo.update_item(
        db,
        item_id=1,
        user_id=42,
        new_content=b"x",
        new_metadata=None,
        version=1,
    )

    assert result.metadata_ == {"keep": "me"}


@pytest.mark.asyncio
async def test_update_item_raises_lookup_error_when_item_missing(monkeypatch):
    db = make_mock_db()
    monkeypatch.setattr(repo, "get_item_by_id", AsyncMock(return_value=None))

    with pytest.raises(LookupError):
        await repo.update_item(
            db, item_id=1, user_id=42, new_content=b"x", new_metadata=None, version=1
        )
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_item_raises_value_error_on_version_conflict(monkeypatch):
    db = make_mock_db()
    existing = make_item(version=5)
    monkeypatch.setattr(repo, "get_item_by_id", AsyncMock(return_value=existing))

    with pytest.raises(ValueError):
        await repo.update_item(
            db,
            item_id=1,
            user_id=42,
            new_content=b"x",
            new_metadata=None,
            version=1,  # stale version -> conflict
        )
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# delete_item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_item_soft_deletes_and_commits(monkeypatch):
    db = make_mock_db()
    existing = make_item(deleted=False)
    monkeypatch.setattr(repo, "get_item_by_id", AsyncMock(return_value=existing))

    await repo.delete_item(db, item_id=1, user_id=42)

    assert existing.deleted is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_item_raises_lookup_error_when_missing(monkeypatch):
    db = make_mock_db()
    monkeypatch.setattr(repo, "get_item_by_id", AsyncMock(return_value=None))

    with pytest.raises(LookupError):
        await repo.delete_item(db, item_id=1, user_id=42)
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_items_by_user_with_versions / get_items_versions / get_items_changed_since
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_items_by_user_with_versions_returns_items():
    db = make_mock_db()
    items = [make_item(id=1), make_item(id=2)]
    db.execute.return_value = make_execute_result(scalars_all=items)

    result = await repo.get_items_by_user_with_versions(db, user_id=42)

    assert result == items


@pytest.mark.asyncio
async def test_get_items_versions_returns_items():
    db = make_mock_db()
    items = [make_item(id=1)]
    db.execute.return_value = make_execute_result(scalars_all=items)

    result = await repo.get_items_versions(db, user_id=42)

    assert result == items


@pytest.mark.asyncio
async def test_get_items_changed_since_returns_only_newer_items():
    db = make_mock_db()
    newer_items = [make_item(id=3, version=10)]
    db.execute.return_value = make_execute_result(scalars_all=newer_items)

    result = await repo.get_items_changed_since(db, user_id=42, since_version=5)

    assert result == newer_items
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_items_changed_since_returns_empty_when_nothing_changed():
    db = make_mock_db()
    db.execute.return_value = make_execute_result(scalars_all=[])

    result = await repo.get_items_changed_since(db, user_id=42, since_version=100)

    assert result == []
