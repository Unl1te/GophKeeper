from unittest.mock import patch

import cli

# ==========================================
# CLI REGISTER TESTS
# ==========================================


@patch("builtins.input", side_effect=["new_cli_user", "cli_pwd"])
def test_cli_register_success(mock_input, requests_mock, capsys):
    """Test successful user registration via CLI."""
    # Mock HTTP response from server
    requests_mock.post(
        "http://localhost/register",
        status_code=201,
        json={"message": "Registered successfully"},
    )

    cli.register()

    # Capture and verify console output
    captured = capsys.readouterr()
    assert "Registered successfully" in captured.out


@patch("builtins.input", side_effect=["existing_user", "cli_pwd"])
def test_cli_register_existing(mock_input, requests_mock, capsys):
    """Test registration failure when username already exists."""
    requests_mock.post("http://localhost/register", status_code=409)

    cli.register()

    captured = capsys.readouterr()
    assert "already exists" in captured.out


# ==========================================
# CLI LOGIN TESTS
# ==========================================


@patch("cli.save_token")
@patch("builtins.input", side_effect=["cli_user", "cli_pwd"])
def test_cli_login_success(mock_input, mock_save_token, requests_mock, capsys):
    """Test successful login and local token saving."""
    requests_mock.post(
        "http://localhost/login",
        status_code=200,
        json={"access_token": "mock_jwt_token"},
    )

    cli.login()

    captured = capsys.readouterr()
    assert "Logged in successfully" in captured.out

    # Verify that save_token was called with the correct token
    mock_save_token.assert_called_once_with("mock_jwt_token")


@patch("builtins.input", side_effect=["cli_user", "wrong_pwd"])
def test_cli_login_failure(mock_input, requests_mock, capsys):
    """Test login failure with incorrect credentials."""
    requests_mock.post("http://localhost/login", status_code=401)

    cli.login()

    captured = capsys.readouterr()
    assert "invalid login or password" in captured.out
