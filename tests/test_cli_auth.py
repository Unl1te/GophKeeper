from unittest.mock import patch

import cli

# ==========================================
# CLI REGISTER TESTS (with masked password)
# ==========================================


@patch("getpass.getpass", return_value="cli_pwd")
@patch("builtins.input", return_value="new_cli_user")
def test_cli_register_success(mock_input, mock_getpass, requests_mock, capsys):
    """Test successful user registration via CLI."""
    requests_mock.post(
        "http://localhost/register",
        status_code=201,
        json={"message": "Registered successfully"},
    )

    cli.register()

    captured = capsys.readouterr()
    assert "Registered successfully" in captured.out


@patch("getpass.getpass", return_value="cli_pwd")
@patch("builtins.input", return_value="existing_user")
def test_cli_register_existing(mock_input, mock_getpass, requests_mock, capsys):
    """Test registration failure when username already exists."""
    requests_mock.post("http://localhost/register", status_code=409)

    cli.register()

    captured = capsys.readouterr()
    assert "already exists" in captured.out


# ==========================================
# CLI LOGIN TESTS (with masked password)
# ==========================================


@patch("cli.save_token")
@patch("getpass.getpass", return_value="cli_pwd")
@patch("builtins.input", return_value="cli_user")
def test_cli_login_success(
    mock_input, mock_getpass, mock_save_token, requests_mock, capsys
):
    """Test successful login and local token saving."""
    requests_mock.post(
        "http://localhost/login",
        status_code=200,
        json={"access_token": "mock_jwt_token"},
    )

    cli.login()

    captured = capsys.readouterr()
    assert "Logged in successfully" in captured.out
    mock_save_token.assert_called_once_with("mock_jwt_token")


@patch("getpass.getpass", return_value="wrong_pwd")
@patch("builtins.input", return_value="cli_user")
def test_cli_login_failure(mock_input, mock_getpass, requests_mock, capsys):
    """Test login failure with incorrect credentials."""
    requests_mock.post("http://localhost/login", status_code=401)

    cli.login()

    captured = capsys.readouterr()
    assert "invalid login or password" in captured.out
