import sys

import pytest
import requests

from cli_cache import LocalCache

SERVER = "http://localhost"


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Import the CLI with an isolated cache and no real auth."""
    import cli as cli_module

    cli_module.cache = LocalCache(path=str(tmp_path / "cache.json"))
    monkeypatch.setattr(
        cli_module, "get_headers", lambda: {"Authorization": "Bearer t"}
    )
    return cli_module


def _item(item_id, version=1, type="text"):
    return {
        "id": item_id,
        "type": type,
        "version": version,
        "updated_at": "2026-01-01T00:00:00Z",
        "metadata": {},
    }


def test_list_pulls_from_server_and_populates_cache(
    cli, requests_mock, monkeypatch, capsys
):
    requests_mock.get(f"{SERVER}/items", json=[_item(1), _item(2, version=3)])
    monkeypatch.setattr(sys, "argv", ["cli.py", "list"])

    cli.list_items()

    out = capsys.readouterr().out
    assert "1" in out and "2" in out
    assert [i["id"] for i in cli.cache.list_items()] == [1, 2]


def test_list_reads_cache_without_hitting_server(
    cli, requests_mock, monkeypatch, capsys
):
    cli.cache.sync([_item(5)])
    monkeypatch.setattr(sys, "argv", ["cli.py", "list"])

    cli.list_items()

    out = capsys.readouterr().out
    assert "5" in out
    # cache was non-empty and no --refresh -> server must not be called
    assert requests_mock.call_count == 0


def test_list_refresh_updates_cache(cli, requests_mock, monkeypatch, capsys):
    cli.cache.sync([_item(5)])
    requests_mock.get(f"{SERVER}/items", json=[_item(8)])
    monkeypatch.setattr(sys, "argv", ["cli.py", "list", "--refresh"])

    cli.list_items()

    assert [i["id"] for i in cli.cache.list_items()] == [8]
    assert requests_mock.call_count == 1


def test_list_offline_falls_back_to_cache(cli, requests_mock, monkeypatch, capsys):
    cli.cache.sync([_item(7, type="card")])
    requests_mock.get(f"{SERVER}/items", exc=requests.exceptions.ConnectionError)
    monkeypatch.setattr(sys, "argv", ["cli.py", "list", "--refresh"])

    cli.list_items()

    out = capsys.readouterr().out
    assert "7" in out
    assert "offline" in out.lower()


def test_delete_removes_item_from_cache(cli, requests_mock, monkeypatch):
    cli.cache.sync([_item(9)])
    requests_mock.delete(f"{SERVER}/items/9", status_code=204)
    monkeypatch.setattr("builtins.input", lambda *a: "y")
    monkeypatch.setattr(sys, "argv", ["cli.py", "delete", "9"])

    cli.delete_item()

    assert cli.cache.get(9) is None
