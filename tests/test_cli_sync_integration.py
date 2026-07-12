from unittest.mock import patch

import pytest

from cli_cache import LocalCache

SERVER = "http://localhost"


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Import CLI with an isolated cache and fake headers."""
    import cli as cli_module

    cli_module.cache = LocalCache(path=str(tmp_path / "cache.json"))
    monkeypatch.setattr(
        cli_module, "get_headers", lambda: {"Authorization": "Bearer t"}
    )
    return cli_module


@patch("sys.argv", ["cli.py", "add", "--type", "text", "--content", "secret"])
@patch("getpass.getpass", return_value="master_password")
def test_cli_add_syncs_to_cache(mock_getpass, cli, requests_mock):
    """Verify that CLI 'add' command automatically syncs new item to cache."""
    requests_mock.post(
        f"{SERVER}/items",
        status_code=201,
        json={
            "id": 42,
            "type": "text",
            "version": 1,
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    cli.add_item()

    cached_item = cli.cache.get(42)
    assert cached_item is not None
    assert cached_item["version"] == 1


@patch("sys.argv", ["cli.py", "get", "42"])
@patch("getpass.getpass", return_value="master_password")
@patch("cli.decrypt_data", return_value=b"decrypted")
def test_cli_get_updates_cache(mock_decrypt, mock_getpass, cli, requests_mock):
    """Verify that CLI 'get' command updates/caches the fetched item."""
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

    cli.get_item()

    cached_item = cli.cache.get(42)
    assert cached_item is not None
    assert cached_item["version"] == 3


@patch("sys.argv", ["cli.py", "get", "42"])
def test_cli_get_cleans_cache_on_404(cli, requests_mock, capsys):
    """Verify that CLI 'get' removes stale items from cache if deleted on server."""
    # Seed cache with stale item
    cli.cache.sync(
        [{"id": 42, "type": "text", "version": 1, "updated_at": "2026-01-01T00:00:00Z"}]
    )
    assert cli.cache.get(42) is not None

    requests_mock.get(f"{SERVER}/items/42", status_code=404)

    cli.get_item()

    # Must be auto-deleted from cache
    assert cli.cache.get(42) is None
