import json
import sys
from unittest.mock import patch

import pytest

import cli
from cli_cache import LocalCache

SERVER = "http://localhost"


@pytest.fixture
def cli_instance(tmp_path, monkeypatch):
    """Import the CLI with an isolated cache and no real auth."""
    import cli as cli_module

    cli_module.cache = LocalCache(path=str(tmp_path / "cache.json"))
    monkeypatch.setattr(
        cli_module, "get_headers", lambda: {"Authorization": "Bearer t"}
    )
    return cli_module


# ==========================================
# WEEK 4: CLI BASIC CRUD TESTS (PRESERVED)
# ==========================================


@patch("sys.argv", ["cli.py", "add", "--type", "text", "--content", "my_secret"])
@patch("getpass.getpass", return_value="master_password")
@patch("cli.load_token", return_value="fake_jwt_token")
def test_cli_add_item_success(mock_token, mock_getpass, requests_mock, capsys):
    """Test successful creation and encryption of an item via CLI."""
    requests_mock.post(f"{SERVER}/items", status_code=201, json={"id": 1, "version": 1})

    cli.add_item()

    captured = capsys.readouterr()
    assert "Success" in captured.out
    assert "Item created (id: 1, version: 1)" in captured.out


@patch("sys.argv", ["cli.py", "list", "--refresh"])
@patch("cli.load_token", return_value="fake_jwt_token")
def test_cli_list_items_success(mock_token, requests_mock, capsys):
    """Test displaying list of items in CLI with --refresh to force update."""
    requests_mock.get(
        f"{SERVER}/items/versions",
        status_code=200,
        json=[{"id": 1, "version": 1}],
    )
    requests_mock.get(
        f"{SERVER}/items",
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
        f"{SERVER}/items/1",
        status_code=200,
        json={
            "id": 1,
            "type": "text",
            "version": 1,
            "content": "deadbeef",
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


# ==========================================
# WEEK 5: NEW INTEGRATION TESTS FOR NEW COMMANDS (WEEK 5 AC)
# ==========================================


@patch("sys.argv", ["cli.py", "version"])
def test_cli_version(cli_instance, capsys):
    """Test that the version command prints the version string."""
    cli.COMMANDS["version"]()
    captured = capsys.readouterr()
    assert len(captured.out) > 0


@patch("sys.argv", ["cli.py", "history", "42"])
def test_cli_history(cli_instance, requests_mock, capsys):
    """Test retrieving and displaying version history for an item."""
    requests_mock.get(
        f"{SERVER}/items/42",
        status_code=200,
        json={
            "id": 42,
            "type": "text",
            "version": 3,
            "content": "deadbeef",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    cli.COMMANDS["history"]()

    captured = capsys.readouterr()
    assert "Version" in captured.out or "3" in captured.out


@patch("sys.argv", ["cli.py", "update", "42"])
@patch("getpass.getpass", return_value="master_password")
@patch("cli.decrypt_data", return_value=b"old_secret")
@patch("cli.encrypt_data", return_value=b"new_secret")
@patch("builtins.input", return_value="new_secret")
def test_cli_update_success(
    mock_input, mock_encrypt, mock_decrypt, mock_getpass, cli_instance, requests_mock
):
    """Test successful update of an existing item."""
    requests_mock.get(
        f"{SERVER}/items/42",
        status_code=200,
        json={
            "id": 42,
            "type": "text",
            "version": 1,
            "content": "deadbeef",
            "updated_at": "2026-01-01T00:00:00Z",
            "metadata": {},
        },
    )
    requests_mock.put(
        f"{SERVER}/items/42",
        status_code=200,
        json={
            "id": 42,
            "type": "text",
            "version": 2,
            "content": "beefdead",
            "updated_at": "2026-01-01T00:00:00Z",
            "metadata": {},
        },
    )

    cli.COMMANDS["update"]()

    assert cli_instance.cache.get(42)["version"] == 2


@patch("sys.argv", ["cli.py", "update", "42"])
@patch("getpass.getpass", return_value="master_password")
@patch("cli.decrypt_data", return_value=b"old_secret")
@patch("cli.encrypt_data", return_value=b"new_secret")
@patch("builtins.input", return_value="new_secret")
def test_cli_update_conflict_and_retry(
    mock_input, mock_encrypt, mock_decrypt, mock_getpass, cli_instance, requests_mock
):
    """Test automatic conflict resolution (retry on 409) during update."""
    requests_mock.get(
        f"{SERVER}/items/42",
        status_code=200,
        json={
            "id": 42,
            "type": "text",
            "version": 1,
            "content": "deadbeef",
            "updated_at": "2026-01-01T00:00:00Z",
            "metadata": {},
        },
    )

    adapter = requests_mock.register_uri(
        "PUT",
        f"{SERVER}/items/42",
        [
            {"json": {"detail": "Conflict"}, "status_code": 409},
            {
                "json": {
                    "id": 42,
                    "type": "text",
                    "version": 2,
                    "content": "beefdead",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "metadata": {},
                },
                "status_code": 200,
            },
        ],
    )

    cli.COMMANDS["update"]()

    assert adapter.call_count == 2


@patch("sys.argv", ["cli.py", "update", "42"])
def test_cli_update_not_found(cli_instance, requests_mock, capsys):
    """Test update failure when the target item is not found (404)."""
    requests_mock.get(f"{SERVER}/items/42", status_code=404)

    cli.COMMANDS["update"]()

    captured = capsys.readouterr()
    assert "not found" in captured.out.lower()


def test_cli_export(cli_instance, tmp_path, monkeypatch):
    """Test exporting local cache to a plain JSON file."""
    cli_instance.cache.sync(
        [{"id": 42, "type": "text", "version": 1, "updated_at": "2026-01-01T00:00:00Z"}]
    )
    export_file = tmp_path / "export.json"

    monkeypatch.setattr(sys, "argv", ["cli.py", "export", str(export_file)])

    cli.COMMANDS["export"]()

    assert export_file.exists()
    with open(export_file, "r") as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["id"] == 42


def test_cli_import(cli_instance, tmp_path, monkeypatch):
    """Test importing and merging items from a JSON file into local cache."""
    import_file = tmp_path / "import.json"
    import_data = [
        {"id": 99, "type": "text", "version": 1, "updated_at": "2026-01-01T00:00:00Z"}
    ]

    with open(import_file, "w") as f:
        json.dump(import_data, f)

    monkeypatch.setattr(sys, "argv", ["cli.py", "import", str(import_file)])

    cli.COMMANDS["import"]()

    assert cli_instance.cache.get(99) is not None
