from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.models.models import User

client = TestClient(app)


@pytest.fixture
def mock_db_session():
    """Override FastAPI DB dependency with an AsyncMock."""
    session = AsyncMock()
    app.dependency_overrides[get_db] = lambda: session
    yield session
    app.dependency_overrides.clear()


@patch("crypto_interface.hash_password")
def test_register_success(mock_hash, mock_db_session):
    """Test successful user registration."""
    # Mock DB: user does not exist
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = mock_result

    mock_hash.return_value = "fake_hashed_password"

    response = client.post(
        "/register", json={"login": "new_user", "password": "secure_pwd"}
    )

    assert response.status_code == 201
    assert response.json() == {"message": "User 'new_user' registered successfully"}
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()


def test_register_existing_user(mock_db_session):
    """Test registration failure when username is taken."""
    # Mock DB: user already exists
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = User(
        login="existing_user", hashed_password="xyz"
    )
    mock_db_session.execute.return_value = mock_result

    response = client.post(
        "/register", json={"login": "existing_user", "password": "password123"}
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    mock_db_session.add.assert_not_called()


@patch("app.api.login.create_access_token")
@patch("crypto_interface.verify_password")
def test_login_success(mock_verify, mock_create_token, mock_db_session):
    """Test successful login and JWT generation."""
    # Mock DB: user found
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = User(
        id=1, login="test_user", hashed_password="hashed_pwd"
    )
    mock_db_session.execute.return_value = mock_result

    mock_verify.return_value = True
    mock_create_token.return_value = "fake_jwt_token"

    response = client.post(
        "/login", json={"login": "test_user", "password": "correct_pwd"}
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "fake_jwt_token"
    assert response.json()["token_type"] == "bearer"


@patch("crypto_interface.verify_password")
def test_login_wrong_password(mock_verify, mock_db_session):
    """Test login failure with incorrect password."""
    # Mock DB: user found
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = User(
        id=1, login="test_user", hashed_password="hashed_pwd"
    )
    mock_db_session.execute.return_value = mock_result

    # Mock Crypto: password mismatch
    mock_verify.return_value = False

    response = client.post(
        "/login", json={"login": "test_user", "password": "wrong_pwd"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid login or password"
