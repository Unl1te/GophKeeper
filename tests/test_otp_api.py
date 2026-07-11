from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.main import app
from app.models.models import DataType, Item, User

client = TestClient(app)

VALID_OTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"  # 32 chars → 20 bytes
ANOTHER_VALID_OTP_SECRET = "JBSWY3DPEHPK3PXPAJBSWY3DPEHPK3PXP"  # 32 chars


@pytest.fixture
def mock_user():
    return User(id=1, login="test_user")


@pytest.fixture
def override_auth(mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield
    app.dependency_overrides.clear()


# ---- CREATE OTP ----


@patch("app.repositories.item_repository.create_item")
def test_create_otp_with_valid_secret(mock_create, override_auth):
    mock_item = Item(
        id=1,
        user_id=1,
        type=DataType.otp,
        content=VALID_OTP_SECRET.encode(),
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_create.return_value = mock_item

    payload = {"type": "otp", "content": VALID_OTP_SECRET, "metadata": {}}
    response = client.post("/items/", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "otp"
    assert data["content"] == VALID_OTP_SECRET


@patch("app.repositories.item_repository.create_item")
def test_create_otp_with_invalid_secret_returns_422(mock_create, override_auth):
    payload = {"type": "otp", "content": "invalid!", "metadata": {}}
    response = client.post("/items/", json=payload)

    assert response.status_code == 422
    assert "OTP secret must be a valid base32-encoded string" in str(
        response.json()["detail"]
    )
    mock_create.assert_not_called()


@patch("app.repositories.item_repository.create_item")
def test_create_otp_with_short_secret_returns_422(mock_create, override_auth):
    payload = {"type": "otp", "content": "JBSWY3DP", "metadata": {}}
    response = client.post("/items/", json=payload)

    assert response.status_code == 422
    assert "OTP secret must be a valid base32-encoded string" in str(
        response.json()["detail"]
    )
    mock_create.assert_not_called()


@patch("app.repositories.item_repository.create_item")
def test_create_non_otp_with_invalid_base32_allowed(mock_create, override_auth):
    mock_item = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        content=b"not base32!",
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_create.return_value = mock_item

    payload = {"type": "text", "content": "not base32!", "metadata": {}}
    response = client.post("/items/", json=payload)

    assert response.status_code == 201


# ---- UPDATE OTP ----


@patch("app.repositories.item_repository.get_item_by_id")
@patch("app.repositories.item_repository.update_item")
def test_update_otp_with_valid_secret(mock_update, mock_get, override_auth):
    existing = Item(
        id=1,
        user_id=1,
        type=DataType.otp,
        content=VALID_OTP_SECRET.encode(),
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_get.return_value = existing

    updated = Item(
        id=1,
        user_id=1,
        type=DataType.otp,
        content=ANOTHER_VALID_OTP_SECRET.encode(),
        version=2,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_update.return_value = updated

    content_b64 = base64.b64encode(ANOTHER_VALID_OTP_SECRET.encode()).decode()
    payload = {"content": content_b64, "metadata": {}, "version": 1}
    response = client.put("/items/1", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 2
    assert data["content"] == content_b64


@patch("app.repositories.item_repository.get_item_by_id")
def test_update_otp_with_invalid_secret_returns_422(mock_get, override_auth):
    existing = Item(
        id=1,
        user_id=1,
        type=DataType.otp,
        content=VALID_OTP_SECRET.encode(),
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_get.return_value = existing

    payload = {"content": "invalid!", "metadata": {}, "version": 1}
    response = client.put("/items/1", json=payload)

    assert response.status_code == 422
    assert "OTP secret must be a valid base32-encoded string" in str(
        response.json()["detail"]
    )


@patch("app.repositories.item_repository.get_item_by_id")
@patch("app.repositories.item_repository.update_item")
def test_update_non_otp_does_not_validate_base32(mock_update, mock_get, override_auth):
    existing = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        content=b"old",
        version=1,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_get.return_value = existing

    updated = Item(
        id=1,
        user_id=1,
        type=DataType.text,
        content=b"new",
        version=2,
        updated_at=datetime.now(timezone.utc),
        metadata_={},
    )
    mock_update.return_value = updated

    payload = {"content": "not base32 at all", "metadata": {}, "version": 1}
    response = client.put("/items/1", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 2
