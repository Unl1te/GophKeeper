from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.main import app
from app.models.models import DataType, Item, User

client = TestClient(app)


@pytest.fixture
def mock_user():
    return User(id=1, login="test_user")


@pytest.fixture
def override_auth(mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield
    app.dependency_overrides.clear()


@patch("app.repositories.item_repository.create_item")
def test_create_item_with_metadata(mock_create, override_auth):
    """Test that metadata is stored and returned correctly on creation."""
    mock_item = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        content=b"encrypted",
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={"note": "test", "tags": ["a", "b"]},
    )
    mock_create.return_value = mock_item

    payload = {
        "type": "text",
        "content": "ZW5jcnlwdGVk",
        "metadata": {"note": "test", "tags": ["a", "b"]},
    }
    response = client.post("/items/", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["metadata"] == {"note": "test", "tags": ["a", "b"]}


@patch("app.repositories.item_repository.get_items_by_user")
def test_list_items_returns_metadata(mock_get_all, override_auth):
    """Test that metadata is returned in the list endpoint."""
    mock_item = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={"source": "test"},
    )
    mock_get_all.return_value = [mock_item]

    response = client.get("/items/")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["metadata"] == {"source": "test"}


@patch("app.repositories.item_repository.get_item_by_id")
def test_get_single_item_returns_metadata(mock_get, override_auth):
    """Test that metadata is returned when fetching a single item."""
    mock_item = Item(
        id=42,
        user_id=1,
        type=DataType.text,
        content=b"secret",
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={"private": True},
    )
    mock_get.return_value = mock_item

    response = client.get("/items/42")

    assert response.status_code == 200
    data = response.json()
    assert data["metadata"] == {"private": True}


@patch("app.repositories.item_repository.update_item")
@patch("app.repositories.item_repository.get_item_by_id")
def test_update_item_updates_metadata(mock_get, mock_update, override_auth):
    """Test that metadata is updated correctly."""
    # First, mock the existing item (to allow update to proceed)
    existing = Item(
        id=42,
        user_id=1,
        type=DataType.text,
        content=b"old",
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={"old": "data"},
    )
    mock_get.return_value = existing

    updated = Item(
        id=42,
        user_id=1,
        type=DataType.text,
        content=b"new",
        version=2,
        updated_at=datetime.now(timezone.utc),
        metadata_={"new": "metadata", "extra": True},
    )
    mock_update.return_value = updated

    payload = {
        "content": "bmV3",
        "metadata": {"new": "metadata", "extra": True},
        "version": 1,
    }
    response = client.put("/items/42", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["metadata"] == {"new": "metadata", "extra": True}
    assert data["version"] == 2


@patch("app.repositories.item_repository.create_item")
def test_create_item_with_empty_metadata_uses_default(mock_create, override_auth):
    """Test that when metadata is not provided, it defaults to empty dict {}."""
    mock_item = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        content=b"encrypted",
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={},  # default
    )
    mock_create.return_value = mock_item

    payload = {"type": "text", "content": "ZW5jcnlwdGVk"}  # no metadata field
    response = client.post("/items/", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["metadata"] == {}
