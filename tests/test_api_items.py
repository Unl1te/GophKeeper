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
    """Create a mock authenticated user."""
    return User(id=1, login="test_user")


@pytest.fixture
def override_auth(mock_user):
    """Override FastAPI auth dependency to inject our mock user."""
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield
    app.dependency_overrides.clear()


# ==========================================
# API CRUD TESTS FOR /items
# ==========================================


@patch("app.repositories.item_repository.create_item")
def test_create_item_success(mock_create, override_auth):
    """Test successful item creation."""
    mock_item = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        content=b"encrypted_data",
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_create.return_value = mock_item

    # "encrypted_data" is passed as a Base64-encoded string
    payload = {"type": "text", "content": "ZW5jcnlwdGVkX2RhdGE=", "metadata": {}}
    response = client.post("/items/", json=payload)

    assert response.status_code == 201
    assert response.json()["id"] == 1
    assert response.json()["type"] == "text"


@patch("app.repositories.item_repository.get_items_by_user")
def test_list_items_success(mock_get_all, override_auth):
    """Test retrieving list of user's items."""
    mock_item = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_get_all.return_value = [mock_item]

    response = client.get("/items/")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == 1


@patch("app.repositories.item_repository.get_item_by_id")
def test_get_single_item_success(mock_get, override_auth):
    """Test retrieving a single item by ID."""
    mock_item = Item(
        id=42,
        user_id=1,
        type=DataType.text,
        content=b"secret",
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_get.return_value = mock_item

    response = client.get("/items/42")

    assert response.status_code == 200
    assert response.json()["id"] == 42
    assert response.json()["content"] == "secret"


@patch("app.repositories.item_repository.update_item")
def test_update_item_success(mock_update, override_auth):
    """Test successful item update."""
    mock_item = Item(
        id=42,
        user_id=1,
        type=DataType.text,
        content=b"new_secret",
        version=2,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_update.return_value = mock_item

    payload = {
        "content": "bmV3X3NlY3JldA==",  # "new_secret" in Base64
        "version": 1,
        "metadata": {},
    }
    response = client.put("/items/42", json=payload)

    assert response.status_code == 200
    assert response.json()["version"] == 2


@patch("app.repositories.item_repository.update_item")
def test_update_item_conflict_409(mock_update, override_auth):
    """Test update failure due to version conflict."""
    # ValueError triggers 409 Conflict in items.py
    mock_update.side_effect = ValueError("Version conflict detected")

    payload = {"content": "bmV3X3NlY3JldA==", "version": 1, "metadata": {}}
    response = client.put("/items/42", json=payload)

    assert response.status_code == 409
    assert "Version conflict" in response.json()["detail"]


@patch("app.repositories.item_repository.delete_item")
def test_delete_item_success(mock_delete, override_auth):
    """Test successful soft-deletion of an item."""
    mock_delete.return_value = None

    response = client.delete("/items/42")

    assert response.status_code == 204
