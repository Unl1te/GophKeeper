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


# ---- OTP CREATE VALIDATION ----


@patch("app.repositories.item_repository.create_item")
def test_create_otp_with_valid_secret(mock_create, override_auth):
    """Test that creating an OTP item with a valid secret succeeds."""
    secret = "JBSWY3DPEHPK3PXP"  # valid 16-byte base32
    mock_item = Item(
        id=1,
        user_id=1,
        type=DataType.otp,
        content=secret.encode(),
        version=1,
        metadata_={},
    )
    mock_create.return_value = mock_item

    payload = {"type": "otp", "content": secret, "metadata": {}}
    response = client.post("/items/", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "otp"
    assert data["content"] == secret


@patch("app.repositories.item_repository.create_item")
def test_create_otp_with_invalid_secret_returns_422(mock_create, override_auth):
    """Test that creating an OTP item with an invalid secret returns 422."""
    invalid_secret = "invalid!"
    payload = {"type": "otp", "content": invalid_secret, "metadata": {}}
    response = client.post("/items/", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "OTP secret must be a valid base32-encoded string" in str(detail)
    mock_create.assert_not_called()


@patch("app.repositories.item_repository.create_item")
def test_create_otp_with_short_secret_returns_422(mock_create, override_auth):
    """Test that creating an OTP item with a secret <16 bytes returns 422."""
    short_secret = "JBSWY3DP"  # only 6 bytes after decoding
    payload = {"type": "otp", "content": short_secret, "metadata": {}}
    response = client.post("/items/", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "OTP secret must be a valid base32-encoded string" in str(detail)
    mock_create.assert_not_called()


@patch("app.repositories.item_repository.create_item")
def test_create_non_otp_with_invalid_base32_allowed(mock_create, override_auth):
    """Test that non-OTP types don't validate base32 (so invalid content is allowed)."""
    invalid_content = "not base32!"
    mock_item = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        content=invalid_content.encode(),
        version=1,
        metadata_={},
    )
    mock_create.return_value = mock_item

    payload = {"type": "text", "content": invalid_content, "metadata": {}}
    response = client.post("/items/", json=payload)

    assert response.status_code == 201


# ---- OTP UPDATE VALIDATION ----


@patch("app.repositories.item_repository.get_item_by_id")
@patch("app.repositories.item_repository.update_item")
def test_update_otp_with_valid_secret(mock_update, mock_get, override_auth):
    """Test that updating an OTP item with a valid secret succeeds."""
    old_secret = "JBSWY3DPEHPK3PXP"
    new_secret = "JBSWY3DPEHPK3PXL"  # different valid secret

    # Mock existing item (type=otp)
    existing_item = Item(
        id=1,
        user_id=1,
        type=DataType.otp,
        content=old_secret.encode(),
        version=1,
        metadata_={},
    )
    mock_get.return_value = existing_item

    # Mock updated item
    updated_item = Item(
        id=1,
        user_id=1,
        type=DataType.otp,
        content=new_secret.encode(),
        version=2,
        metadata_={},
    )
    mock_update.return_value = updated_item

    payload = {"content": new_secret, "metadata": {}, "version": 1}
    response = client.put("/items/1", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 2
    assert data["content"] == new_secret


@patch("app.repositories.item_repository.get_item_by_id")
def test_update_otp_with_invalid_secret_returns_422(mock_get, override_auth):
    """Test that updating an OTP item with an invalid secret returns 422."""
    old_secret = "JBSWY3DPEHPK3PXP"
    invalid_secret = "invalid!"

    existing_item = Item(
        id=1,
        user_id=1,
        type=DataType.otp,
        content=old_secret.encode(),
        version=1,
        metadata_={},
    )
    mock_get.return_value = existing_item

    payload = {"content": invalid_secret, "metadata": {}, "version": 1}
    response = client.put("/items/1", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "OTP secret must be a valid base32-encoded string" in str(detail)


@patch("app.repositories.item_repository.get_item_by_id")
@patch("app.repositories.item_repository.update_item")
def test_update_non_otp_does_not_validate_base32(mock_update, mock_get, override_auth):
    """Test that updating a non-OTP item allows any content."""
    existing_item = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        content=b"old",
        version=1,
        metadata_={},
    )
    mock_get.return_value = existing_item

    updated_item = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        content=b"new",
        version=2,
        metadata_={},
    )
    mock_update.return_value = updated_item

    payload = {"content": "not base32 at all", "metadata": {}, "version": 1}
    response = client.put("/items/1", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 2
