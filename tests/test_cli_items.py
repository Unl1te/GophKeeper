from unittest.mock import patch

import cli

# ==========================================
# CLI CRUD INTEGRATION TESTS
# ==========================================


@patch("sys.argv", ["cli.py", "add", "--type", "text", "--content", "my_secret"])
@patch("getpass.getpass", return_value="master_password")
@patch("cli.load_token", return_value="fake_jwt_token")
def test_cli_add_item_success(mock_token, mock_getpass, requests_mock, capsys):
    """Test successful creation and encryption of an item via CLI."""
    requests_mock.post(
        "http://localhost/items", status_code=201, json={"id": 1, "version": 1}
    )

    cli.add_item()

    captured = capsys.readouterr()
    assert "Success" in captured.out
    assert "Item created (id: 1, version: 1)" in captured.out


@patch("cli.load_token", return_value="fake_jwt_token")
def test_cli_list_items_success(mock_token, requests_mock, capsys):
    """Test displaying list of items in CLI."""
    requests_mock.get(
        "http://localhost/items",
        status_code=200,
        json=[
            {
                "id": 1,
                "type": "text",
                "version": 1,
                "updated_at": "2026-06-28T12:00:00.000000",
            }
        ],
    )

    cli.list_items()

    captured = capsys.readouterr()
    assert "ID" in captured.out
    assert "1" in captured.out
    assert "text" in captured.out


@patch("sys.argv", ["cli.py", "get", "1"])
@patch("getpass.getpass", return_value="master_password")
@patch("cli.load_token", return_value="fake_jwt_token")
@patch("cli.decrypt_data", return_value=b"my_decrypted_secret")
def test_cli_get_item_success(
    mock_decrypt, mock_token, mock_getpass, requests_mock, capsys
):
    """Test retrieving and decrypting an item via CLI."""
    requests_mock.get(
        "http://localhost/items/1",
        status_code=200,
        json={
            "id": 1,
            "type": "text",
            "version": 1,
            "content": "deadbeef",  # Mocked hex content
            "updated_at": "2026-06-28T12:00:00.000000",
            "metadata": {"note": "test"},
        },
    )

    cli.get_item()

    captured = capsys.readouterr()
    assert "Item #1" in captured.out
    assert "my_decrypted_secret" in captured.out


@patch("sys.argv", ["cli.py", "delete", "1"])
@patch("builtins.input", return_value="y")
@patch("cli.load_token", return_value="fake_jwt_token")
def test_cli_delete_item_success(mock_token, mock_input, requests_mock, capsys):
    """Test soft-deletion of an item via CLI."""
    requests_mock.delete("http://localhost/items/1", status_code=204)

    cli.delete_item()

    captured = capsys.readouterr()
    assert "deleted" in captured.out
