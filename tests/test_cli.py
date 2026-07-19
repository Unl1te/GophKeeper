"""
Tests for cli.py.

Everything that touches the outside world (HTTP via `requests`, the local
cache, the crypto module, interactive prompts, and the filesystem) is
mocked/monkeypatched so these tests are fast and deterministic.

`cli` is imported once; per-test isolation for CONFIG_DIR/CONFIG_FILE/
HISTORY_FILE/cache is handled by the `isolated_cli_env` autouse fixture
below, which points those module-level globals at a fresh tmp_path and
resets sys.argv.

Adjust the `import cli` line if your test runner needs a different import
path (e.g. `from app import cli`).
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

import cli


class FakeResponse:
    """Minimal stand-in for `requests.Response`."""

    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


@pytest.fixture(autouse=True)
def isolated_cli_env(tmp_path, monkeypatch):
    """Give every test a clean config dir, a mocked cache, and a clean argv."""
    config_dir = tmp_path / "gophkeeper_home"
    config_dir.mkdir()
    monkeypatch.setattr(cli, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_dir / "config.json"))
    monkeypatch.setattr(cli, "HISTORY_FILE", str(config_dir / "history.json"))

    fake_cache = MagicMock()
    fake_cache.list_items.return_value = []
    monkeypatch.setattr(cli, "cache", fake_cache)

    monkeypatch.setattr(sys, "argv", ["cli.py"])
    yield


@pytest.fixture
def logged_out(monkeypatch):
    monkeypatch.setattr(cli, "load_token", lambda: None)


@pytest.fixture
def logged_in(monkeypatch):
    monkeypatch.setattr(cli, "load_token", lambda: "tok123")


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------


def test_save_and_load_token_roundtrip():
    cli.save_token("abc123")
    assert cli.load_token() == "abc123"


def test_load_token_returns_none_when_no_file():
    assert cli.load_token() is None


def test_get_headers_empty_when_no_token(monkeypatch):
    monkeypatch.setattr(cli, "load_token", lambda: None)
    assert cli.get_headers() == {}


def test_get_headers_contains_bearer_token(monkeypatch):
    monkeypatch.setattr(cli, "load_token", lambda: "mytoken")
    assert cli.get_headers() == {"Authorization": "Bearer mytoken"}


# ---------------------------------------------------------------------------
# ask_master_password / derive_encryption_key / print helpers
# ---------------------------------------------------------------------------


def test_ask_master_password_returns_input(monkeypatch):
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "s3cr3t")
    assert cli.ask_master_password() == "s3cr3t"


def test_ask_master_password_reraises_keyboard_interrupt(monkeypatch):
    def raise_interrupt(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.getpass, "getpass", raise_interrupt)
    with pytest.raises(KeyboardInterrupt):
        cli.ask_master_password()


def test_derive_encryption_key_calls_derive_key_with_fixed_salt(monkeypatch):
    calls = {}

    def fake_derive_key(password, salt):
        calls["password"] = password
        calls["salt"] = salt
        return b"derived-key"

    monkeypatch.setattr(cli, "derive_key", fake_derive_key)
    result = cli.derive_encryption_key("hunter2")

    assert result == b"derived-key"
    assert calls["password"] == "hunter2"
    assert calls["salt"] == b"gophkeeper_salt_16bytes"


def test_print_error_outputs_message(capsys):
    cli.print_error("something broke")
    assert "Error: something broke" in capsys.readouterr().out


def test_print_success_outputs_message(capsys):
    cli.print_success("all good")
    assert "Success: all good" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------


def test_load_history_returns_empty_dict_when_no_file():
    assert cli._load_history() == {}


def test_save_and_load_history_roundtrip():
    cli._save_history({"1": [{"version": 1}]})
    assert cli._load_history() == {"1": [{"version": 1}]}


def test_add_history_entry_appends_and_truncates_preview():
    long_content = "x" * 100
    cli._add_history_entry(1, 2, long_content, {"k": "v"})

    history = cli._load_history()
    assert "1" in history
    entry = history["1"][0]
    assert entry["version"] == 2
    assert entry["content_preview"] == long_content[:50]
    assert entry["metadata"] == {"k": "v"}


def test_add_history_entry_stringifies_non_string_content():
    cli._add_history_entry(2, 1, {"nested": "dict"}, {})
    history = cli._load_history()
    assert history["2"][0]["content_preview"] == str({"nested": "dict"})[:50]


def test_add_history_entry_appends_to_existing_list():
    cli._add_history_entry(1, 1, "first", {})
    cli._add_history_entry(1, 2, "second", {})
    entries = cli._load_history()["1"]
    assert len(entries) == 2
    assert entries[1]["version"] == 2


# ---------------------------------------------------------------------------
# _fetch_versions
# ---------------------------------------------------------------------------


def test_fetch_versions_returns_json_on_200(monkeypatch):
    monkeypatch.setattr(
        cli.requests,
        "get",
        lambda *a, **k: FakeResponse(200, [{"id": 1, "version": 1}]),
    )
    assert cli._fetch_versions() == [{"id": 1, "version": 1}]


def test_fetch_versions_returns_none_on_401(monkeypatch, capsys):
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(401))
    assert cli._fetch_versions() is None
    assert "Not authenticated" in capsys.readouterr().out


def test_fetch_versions_returns_none_on_other_error(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.requests, "get", lambda *a, **k: FakeResponse(500, {"detail": "boom"})
    )
    assert cli._fetch_versions() is None
    assert "boom" in capsys.readouterr().out


def test_fetch_versions_returns_none_on_connection_error(monkeypatch):
    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "get", raise_conn_error)
    assert cli._fetch_versions() is None


# ---------------------------------------------------------------------------
# _refresh_cache_from_server
# ---------------------------------------------------------------------------


def test_refresh_cache_from_server_success(monkeypatch):
    items = [{"id": 1, "version": 1}]
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(200, items))
    assert cli._refresh_cache_from_server() is True
    cli.cache.sync.assert_called_once_with(items)


def test_refresh_cache_from_server_unauthenticated(monkeypatch, capsys):
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(401))
    assert cli._refresh_cache_from_server() is False
    assert "Not authenticated" in capsys.readouterr().out


def test_refresh_cache_from_server_other_error(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.requests, "get", lambda *a, **k: FakeResponse(500, {"detail": "oops"})
    )
    assert cli._refresh_cache_from_server() is False


def test_refresh_cache_from_server_connection_error(monkeypatch, capsys):
    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "get", raise_conn_error)
    assert cli._refresh_cache_from_server() is False
    assert "Could not connect" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _check_and_update_cache_if_needed
# ---------------------------------------------------------------------------


def test_check_and_update_cache_offline_with_cached_items(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_fetch_versions", lambda: None)
    cli.cache.list_items.return_value = [{"id": 1, "version": 1}]
    assert cli._check_and_update_cache_if_needed() is False
    assert "offline" in capsys.readouterr().out


def test_check_and_update_cache_offline_without_cached_items(monkeypatch):
    monkeypatch.setattr(cli, "_fetch_versions", lambda: None)
    cli.cache.list_items.return_value = []
    assert cli._check_and_update_cache_if_needed() is False


def test_check_and_update_cache_no_update_needed(monkeypatch):
    monkeypatch.setattr(cli, "_fetch_versions", lambda: [{"id": 1, "version": 1}])
    cli.cache.list_items.return_value = [{"id": 1, "version": 1}]
    refresh_mock = MagicMock()
    monkeypatch.setattr(cli, "_refresh_cache_from_server", refresh_mock)

    assert cli._check_and_update_cache_if_needed() is False
    refresh_mock.assert_not_called()


def test_check_and_update_cache_triggers_refresh_on_version_mismatch(monkeypatch):
    monkeypatch.setattr(cli, "_fetch_versions", lambda: [{"id": 1, "version": 2}])
    cli.cache.list_items.return_value = [{"id": 1, "version": 1}]
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: True)

    assert cli._check_and_update_cache_if_needed() is True


def test_check_and_update_cache_triggers_refresh_on_length_mismatch(monkeypatch):
    monkeypatch.setattr(
        cli,
        "_fetch_versions",
        lambda: [{"id": 1, "version": 1}, {"id": 2, "version": 1}],
    )
    cli.cache.list_items.return_value = [{"id": 1, "version": 1}]
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: True)

    assert cli._check_and_update_cache_if_needed() is True


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def test_health_ok(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.requests, "get", lambda *a, **k: FakeResponse(200, {"status": "ok"})
    )
    cli.health()
    assert "OK" in capsys.readouterr().out


def test_health_unexpected_response(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.requests, "get", lambda *a, **k: FakeResponse(200, {"status": "weird"})
    )
    cli.health()
    assert "Unexpected response" in capsys.readouterr().out


def test_health_connection_error(monkeypatch, capsys):
    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "get", raise_conn_error)
    cli.health()
    assert "Could not connect" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


def test_register_skips_when_already_logged_in(logged_in, capsys):
    cli.register()
    assert "already logged in" in capsys.readouterr().out


def test_register_success(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw123456")
    monkeypatch.setattr(
        cli.requests,
        "post",
        lambda *a, **k: FakeResponse(201, {"message": "Registered successfully"}),
    )
    cli.register()
    assert "Registered successfully" in capsys.readouterr().out


def test_register_username_taken(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw123456")
    monkeypatch.setattr(cli.requests, "post", lambda *a, **k: FakeResponse(409))
    cli.register()
    assert "already exists" in capsys.readouterr().out


def test_register_password_too_short(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "x")
    detail = [
        {"loc": ["body", "password"], "type": "string_too_short", "msg": "too short"}
    ]
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(422, {"detail": detail})
    )
    cli.register()
    assert "at least 6 characters" in capsys.readouterr().out


def test_register_validation_error_other_field(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw123456")
    detail = [{"loc": ["body", "login"], "type": "value_error", "msg": "bad login"}]
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(422, {"detail": detail})
    )
    cli.register()
    assert "bad login" in capsys.readouterr().out


def test_register_validation_error_empty_detail(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw123456")
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(422, {"detail": []})
    )
    cli.register()
    assert "Invalid input" in capsys.readouterr().out


def test_register_other_error_status(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw123456")
    monkeypatch.setattr(
        cli.requests,
        "post",
        lambda *a, **k: FakeResponse(500, {"detail": "server error"}),
    )
    cli.register()
    assert "server error" in capsys.readouterr().out


def test_register_connection_error(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw123456")

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "post", raise_conn_error)
    cli.register()
    assert "could not connect" in capsys.readouterr().out


def test_register_keyboard_interrupt_during_prompt(logged_out, monkeypatch, capsys):
    def raise_interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.Prompt, "ask", raise_interrupt)
    cli.register()
    assert "cancelled" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


def test_login_skips_when_already_logged_in(logged_in, capsys):
    cli.login()
    assert "already logged in" in capsys.readouterr().out


def test_login_success_saves_token_and_clears_state(monkeypatch, capsys):
    # No `logged_out` fixture here: it stubs cli.load_token to always
    # return None, which would also hide the token we're about to save.
    # The autouse isolated_cli_env fixture already gives us a fresh,
    # token-free CONFIG_FILE, so the "not already logged in" check in
    # login() passes naturally.
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw123456")
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(200, {"access_token": "tok"})
    )

    cli.login()

    assert cli.load_token() == "tok"
    cli.cache.clear.assert_called_once()
    assert "Logged in successfully" in capsys.readouterr().out


def test_login_invalid_credentials(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "wrong")
    monkeypatch.setattr(cli.requests, "post", lambda *a, **k: FakeResponse(401))

    cli.login()
    assert "Invalid username or password" in capsys.readouterr().out


def test_login_other_error(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw")
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(500, {"detail": "oops"})
    )
    cli.login()
    assert "oops" in capsys.readouterr().out


def test_login_connection_error(logged_out, monkeypatch, capsys):
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "alice")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw")

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "post", raise_conn_error)
    cli.login()
    assert "could not connect" in capsys.readouterr().out


def test_login_keyboard_interrupt(logged_out, monkeypatch, capsys):
    def raise_interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.Prompt, "ask", raise_interrupt)
    cli.login()
    assert "cancelled" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------


def test_logout_when_not_logged_in(logged_out, capsys):
    cli.logout()
    assert "not logged in" in capsys.readouterr().out


def test_logout_clears_token_cache_and_history():
    cli.save_token("tok")
    cli._save_history({"1": []})

    cli.logout()

    assert cli.load_token() is None
    assert not os.path.exists(cli.HISTORY_FILE)
    cli.cache.clear.assert_called_once()


# ---------------------------------------------------------------------------
# add_item
# ---------------------------------------------------------------------------


def _prep_add(monkeypatch, argv_tail, master_password="masterpw"):
    monkeypatch.setattr(sys, "argv", ["cli.py", "add"] + argv_tail)
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: master_password)
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")
    monkeypatch.setattr(cli, "encrypt_data", lambda content, key: b"\xde\xad\xbe\xef")


def test_add_item_with_content_success(monkeypatch, capsys):
    _prep_add(monkeypatch, ["--type", "text", "--content", "hello", "--meta", "note=x"])
    monkeypatch.setattr(
        cli.requests,
        "post",
        lambda *a, **k: FakeResponse(201, {"id": 1, "version": 1}),
    )
    cli.add_item()
    out = capsys.readouterr().out
    assert "Item created" in out
    cli.cache.upsert.assert_called_once()


def test_add_item_meta_without_equals_sign_is_flag(monkeypatch):
    _prep_add(monkeypatch, ["--type", "text", "--content", "hello", "--meta", "urgent"])
    captured = {}

    def fake_post(url, json=None, headers=None):
        captured["payload"] = json
        return FakeResponse(201, {"id": 1, "version": 1})

    monkeypatch.setattr(cli.requests, "post", fake_post)
    cli.add_item()
    assert captured["payload"]["metadata"] == {"urgent": True}


def test_add_item_otp_generate_secret(monkeypatch, capsys):
    _prep_add(monkeypatch, ["--type", "otp", "--generate-secret"])
    monkeypatch.setattr(cli, "generate_otp_secret", lambda: "SECRET123")
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(201, {"id": 2, "version": 1})
    )
    cli.add_item()
    out = capsys.readouterr().out
    assert "generate TOTP codes" in out


def test_add_item_from_file(monkeypatch, tmp_path):
    file_path = tmp_path / "secret.bin"
    file_path.write_bytes(b"binary-data")
    _prep_add(monkeypatch, ["--type", "binary", "--file", str(file_path)])
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(201, {"id": 3, "version": 1})
    )
    cli.add_item()
    cli.cache.upsert.assert_called_once()


def test_add_item_from_file_not_found(monkeypatch, capsys):
    _prep_add(monkeypatch, ["--type", "binary", "--file", "/no/such/file"])
    cli.add_item()
    assert "File not found" in capsys.readouterr().out


def test_add_item_interactive_binary_prompt(monkeypatch, tmp_path):
    file_path = tmp_path / "f.bin"
    file_path.write_bytes(b"data")
    _prep_add(monkeypatch, ["--type", "binary"])
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: str(file_path))
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(201, {"id": 4, "version": 1})
    )
    cli.add_item()
    cli.cache.upsert.assert_called_once()


def test_add_item_interactive_binary_no_path_given(monkeypatch, capsys):
    _prep_add(monkeypatch, ["--type", "binary"])
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "")
    cli.add_item()
    assert "No file provided" in capsys.readouterr().out


def test_add_item_interactive_otp_confirm_generate(monkeypatch, capsys):
    _prep_add(monkeypatch, ["--type", "otp"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(cli, "generate_otp_secret", lambda: "GENSECRET")
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(201, {"id": 5, "version": 1})
    )
    cli.add_item()
    assert "Generated secret" in capsys.readouterr().out


def test_add_item_interactive_otp_manual_entry(monkeypatch):
    _prep_add(monkeypatch, ["--type", "otp"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: False)
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "MANUALSECRET")
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(201, {"id": 6, "version": 1})
    )
    cli.add_item()
    cli.cache.upsert.assert_called_once()


def test_add_item_interactive_text_prompt(monkeypatch):
    _prep_add(monkeypatch, ["--type", "text"])
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "typed content")
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(201, {"id": 7, "version": 1})
    )
    cli.add_item()
    cli.cache.upsert.assert_called_once()


def test_add_item_interactive_text_prompt_keyboard_interrupt(monkeypatch, capsys):
    _prep_add(monkeypatch, ["--type", "text"])

    def raise_interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.Prompt, "ask", raise_interrupt)
    cli.add_item()
    assert "cancelled" in capsys.readouterr().out


def test_add_item_master_password_keyboard_interrupt(monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["cli.py", "add", "--type", "text", "--content", "x"]
    )

    def raise_interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "ask_master_password", raise_interrupt)
    cli.add_item()
    assert "cancelled" in capsys.readouterr().out


def test_add_item_unauthenticated(monkeypatch, capsys):
    _prep_add(monkeypatch, ["--type", "text", "--content", "hi"])
    monkeypatch.setattr(cli.requests, "post", lambda *a, **k: FakeResponse(401))
    cli.add_item()
    assert "Not authenticated" in capsys.readouterr().out


def test_add_item_other_error(monkeypatch, capsys):
    _prep_add(monkeypatch, ["--type", "text", "--content", "hi"])
    monkeypatch.setattr(
        cli.requests, "post", lambda *a, **k: FakeResponse(500, {"detail": "boom"})
    )
    cli.add_item()
    assert "boom" in capsys.readouterr().out


def test_add_item_connection_error(monkeypatch, capsys):
    _prep_add(monkeypatch, ["--type", "text", "--content", "hi"])

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "post", raise_conn_error)
    cli.add_item()
    assert "Could not connect" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _print_items / list_items
# ---------------------------------------------------------------------------


def test_print_items_empty(capsys):
    cli._print_items([])
    assert "No items found" in capsys.readouterr().out


def test_print_items_with_data(capsys):
    cli._print_items(
        [{"id": 1, "type": "text", "version": 1, "updated_at": "2026-01-01T00:00:00Z"}]
    )
    out = capsys.readouterr().out
    assert "Your Items" in out


def test_list_items_refresh_success(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli.py", "list", "--refresh"])
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: True)
    cli.cache.list_items.return_value = [
        {"id": 1, "type": "text", "version": 1, "updated_at": None}
    ]
    cli.list_items()
    cli.cache.list_items.assert_called()


def test_list_items_refresh_fails_falls_back_to_cache(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "list", "--refresh"])
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: False)
    cli.cache.list_items.return_value = [
        {"id": 1, "type": "text", "version": 1, "updated_at": None}
    ]
    cli.list_items()
    assert "offline" in capsys.readouterr().out


def test_list_items_refresh_fails_and_no_cache(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "list", "--refresh"])
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: False)
    cli.cache.list_items.return_value = []
    cli.list_items()
    assert "Could not refresh" in capsys.readouterr().out


def test_list_items_uses_cache_when_present(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli.py", "list"])
    cli.cache.list_items.return_value = [
        {"id": 1, "type": "text", "version": 1, "updated_at": None}
    ]
    monkeypatch.setattr(cli, "_check_and_update_cache_if_needed", lambda: False)
    cli.list_items()


def test_list_items_no_cache_fetches_from_server(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli.py", "list"])
    cli.cache.list_items.return_value = []
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: False)
    cli.list_items()  # should hit "Could not fetch items" branch, no exception


# ---------------------------------------------------------------------------
# get_item
# ---------------------------------------------------------------------------


def test_get_item_missing_arg(capsys):
    cli.get_item()
    assert "Usage" in capsys.readouterr().out


def test_get_item_success(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "get", "1"])
    item = {
        "id": 1,
        "type": "text",
        "version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "content": "deadbeef",
        "metadata": {},
    }
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(200, item))
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: "pw")
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")
    monkeypatch.setattr(cli, "decrypt_data", lambda data, key: b"plaintext")

    cli.get_item()
    assert "plaintext" in capsys.readouterr().out


def test_get_item_decrypted_content_not_utf8(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "get", "1"])
    item = {
        "id": 1,
        "type": "binary",
        "version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "content": "deadbeef",
        "metadata": {},
    }
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(200, item))
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: "pw")
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")
    monkeypatch.setattr(cli, "decrypt_data", lambda data, key: b"\xff\xfe\x00")

    cli.get_item()
    assert "fffe00" in capsys.readouterr().out


def test_get_item_keyboard_interrupt_on_password(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "get", "1"])
    item = {"id": 1, "content": "aa"}
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(200, item))

    def raise_interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "ask_master_password", raise_interrupt)
    cli.get_item()
    assert "cancelled" in capsys.readouterr().out


def test_get_item_not_found(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "get", "999"])
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(404))
    cli.get_item()
    assert "not found" in capsys.readouterr().out
    cli.cache.remove.assert_called_once_with("999")


def test_get_item_conflict_then_retry_success(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "get", "1"])
    item = {
        "id": 1,
        "type": "text",
        "version": 2,
        "updated_at": "x",
        "content": "aa",
        "metadata": {},
    }
    responses = [FakeResponse(409), FakeResponse(200, item)]
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: True)
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: "pw")
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")
    monkeypatch.setattr(cli, "decrypt_data", lambda data, key: b"content")

    cli.get_item()
    assert "content" in capsys.readouterr().out


def test_get_item_conflict_refresh_fails(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "get", "1"])
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(409))
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: False)
    cli.get_item()
    assert "Could not refresh cache" in capsys.readouterr().out


def test_get_item_unauthenticated(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "get", "1"])
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(401))
    cli.get_item()
    assert "Not authenticated" in capsys.readouterr().out


def test_get_item_other_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "get", "1"])
    monkeypatch.setattr(
        cli.requests, "get", lambda *a, **k: FakeResponse(500, {"detail": "boom"})
    )
    cli.get_item()
    assert "boom" in capsys.readouterr().out


def test_get_item_connection_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "get", "1"])

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "get", raise_conn_error)
    cli.get_item()
    assert "Could not connect" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# delete_item
# ---------------------------------------------------------------------------


def test_delete_item_missing_arg(capsys):
    cli.delete_item()
    assert "Usage" in capsys.readouterr().out


def test_delete_item_cancelled(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "delete", "1"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: False)
    cli.delete_item()
    assert "Cancelled" in capsys.readouterr().out


def test_delete_item_success(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "delete", "1"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(cli.requests, "delete", lambda *a, **k: FakeResponse(204))
    cli.delete_item()
    cli.cache.remove.assert_called_once_with("1")
    assert "deleted" in capsys.readouterr().out


def test_delete_item_not_found(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "delete", "1"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(cli.requests, "delete", lambda *a, **k: FakeResponse(404))
    cli.delete_item()
    assert "not found" in capsys.readouterr().out


def test_delete_item_conflict_then_retry_success(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli.py", "delete", "1"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: True)
    responses = [FakeResponse(409), FakeResponse(204)]
    monkeypatch.setattr(cli.requests, "delete", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: True)
    cli.delete_item()
    cli.cache.remove.assert_called_once_with("1")


def test_delete_item_conflict_refresh_fails(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "delete", "1"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(cli.requests, "delete", lambda *a, **k: FakeResponse(409))
    monkeypatch.setattr(cli, "_refresh_cache_from_server", lambda: False)
    cli.delete_item()
    assert "Could not refresh cache" in capsys.readouterr().out


def test_delete_item_unauthenticated(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "delete", "1"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(cli.requests, "delete", lambda *a, **k: FakeResponse(401))
    cli.delete_item()
    assert "Not authenticated" in capsys.readouterr().out


def test_delete_item_other_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "delete", "1"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(
        cli.requests, "delete", lambda *a, **k: FakeResponse(500, {"detail": "boom"})
    )
    cli.delete_item()
    assert "boom" in capsys.readouterr().out


def test_delete_item_connection_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "delete", "1"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: True)

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "delete", raise_conn_error)
    cli.delete_item()
    assert "Could not connect" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# update_item
# ---------------------------------------------------------------------------


def _prep_update_get(monkeypatch, item):
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(200, item))
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: "pw")
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")
    monkeypatch.setattr(cli, "decrypt_data", lambda data, key: b"old content")
    monkeypatch.setattr(cli, "encrypt_data", lambda data, key: b"\xaa\xbb")


def test_update_item_missing_arg(capsys):
    cli.update_item()
    assert "Usage" in capsys.readouterr().out


def test_update_item_not_found(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(404))
    cli.update_item()
    assert "not found" in capsys.readouterr().out


def test_update_item_unauthenticated_on_get(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(401))
    cli.update_item()
    assert "Not authenticated" in capsys.readouterr().out


def test_update_item_other_error_on_get(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    monkeypatch.setattr(
        cli.requests, "get", lambda *a, **k: FakeResponse(500, {"detail": "boom"})
    )
    cli.update_item()
    assert "boom" in capsys.readouterr().out


def test_update_item_connection_error_on_get(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "get", raise_conn_error)
    cli.update_item()
    assert "Could not connect" in capsys.readouterr().out


def test_update_item_keyboard_interrupt_on_password(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    monkeypatch.setattr(
        cli.requests,
        "get",
        lambda *a, **k: FakeResponse(200, {"id": 1, "content": "aa"}),
    )

    def raise_interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "ask_master_password", raise_interrupt)
    cli.update_item()
    assert "cancelled" in capsys.readouterr().out


def test_update_item_decrypt_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    monkeypatch.setattr(
        cli.requests,
        "get",
        lambda *a, **k: FakeResponse(200, {"id": 1, "content": "aa"}),
    )
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: "pw")
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")

    def raise_error(data, key):
        raise ValueError("bad")

    monkeypatch.setattr(cli, "decrypt_data", raise_error)
    cli.update_item()
    assert "Wrong master password" in capsys.readouterr().out


def test_update_item_success(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    item = {"id": 1, "content": "aa", "version": 1, "metadata": {}}
    _prep_update_get(monkeypatch, item)
    monkeypatch.setattr(cli.Prompt, "ask", lambda prompt, default=None: default)
    monkeypatch.setattr(
        cli.requests,
        "put",
        lambda *a, **k: FakeResponse(200, {"id": 1, "version": 2}),
    )

    cli.update_item()
    assert "updated" in capsys.readouterr().out
    cli.cache.upsert.assert_called_once()


def test_update_item_invalid_metadata_json_keeps_old(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    item = {"id": 1, "content": "aa", "version": 1, "metadata": {"a": "b"}}
    _prep_update_get(monkeypatch, item)

    prompts = iter(["new content", "not-json{{"])
    monkeypatch.setattr(cli.Prompt, "ask", lambda prompt, default=None: next(prompts))
    monkeypatch.setattr(
        cli.requests,
        "put",
        lambda *a, **k: FakeResponse(200, {"id": 1, "version": 2}),
    )

    cli.update_item()
    assert "Invalid JSON" in capsys.readouterr().out


def test_update_item_conflict_then_retry_success(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    item = {"id": 1, "content": "aa", "version": 1, "metadata": {}}
    _prep_update_get(monkeypatch, item)
    monkeypatch.setattr(cli.Prompt, "ask", lambda prompt, default=None: default)

    put_responses = [FakeResponse(409), FakeResponse(200, {"id": 1, "version": 3})]
    monkeypatch.setattr(cli.requests, "put", lambda *a, **k: put_responses.pop(0))

    get_calls = {"n": 0}

    def fake_get(*a, **k):
        get_calls["n"] += 1
        if get_calls["n"] == 1:
            return FakeResponse(200, item)
        return FakeResponse(200, {"id": 1, "version": 2})

    monkeypatch.setattr(cli.requests, "get", fake_get)

    cli.update_item()
    assert "updated" in capsys.readouterr().out


def test_update_item_conflict_refetch_fails(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    item = {"id": 1, "content": "aa", "version": 1, "metadata": {}}
    _prep_update_get(monkeypatch, item)
    monkeypatch.setattr(cli.Prompt, "ask", lambda prompt, default=None: default)
    monkeypatch.setattr(cli.requests, "put", lambda *a, **k: FakeResponse(409))

    get_calls = {"n": 0}

    def fake_get(*a, **k):
        get_calls["n"] += 1
        if get_calls["n"] == 1:
            return FakeResponse(200, item)
        return FakeResponse(500, {"detail": "boom"})

    monkeypatch.setattr(cli.requests, "get", fake_get)
    cli.update_item()
    assert "Could not fetch latest version" in capsys.readouterr().out


def test_update_item_unauthenticated_on_put(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    item = {"id": 1, "content": "aa", "version": 1, "metadata": {}}
    _prep_update_get(monkeypatch, item)
    monkeypatch.setattr(cli.Prompt, "ask", lambda prompt, default=None: default)
    monkeypatch.setattr(cli.requests, "put", lambda *a, **k: FakeResponse(401))
    cli.update_item()
    assert "Not authenticated" in capsys.readouterr().out


def test_update_item_other_error_on_put(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    item = {"id": 1, "content": "aa", "version": 1, "metadata": {}}
    _prep_update_get(monkeypatch, item)
    monkeypatch.setattr(cli.Prompt, "ask", lambda prompt, default=None: default)
    monkeypatch.setattr(
        cli.requests, "put", lambda *a, **k: FakeResponse(500, {"detail": "boom"})
    )
    cli.update_item()
    assert "boom" in capsys.readouterr().out


def test_update_item_connection_error_on_put(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    item = {"id": 1, "content": "aa", "version": 1, "metadata": {}}
    _prep_update_get(monkeypatch, item)
    monkeypatch.setattr(cli.Prompt, "ask", lambda prompt, default=None: default)

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "put", raise_conn_error)
    cli.update_item()
    assert "Could not connect" in capsys.readouterr().out


def test_update_item_max_retries_exceeded(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "update", "1"])
    item = {"id": 1, "content": "aa", "version": 1, "metadata": {}}
    _prep_update_get(monkeypatch, item)
    monkeypatch.setattr(cli.Prompt, "ask", lambda prompt, default=None: default)
    monkeypatch.setattr(cli.requests, "put", lambda *a, **k: FakeResponse(409))
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(200, item))

    cli.update_item()
    assert "failed after multiple retries" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


def test_history_missing_arg(capsys):
    cli.history()
    assert "Usage" in capsys.readouterr().out


def test_history_shows_local_history(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "history", "1"])
    cli._save_history({"1": [{"version": 1, "timestamp": "t", "content_preview": "p"}]})
    cli.history()
    assert "History for item 1" in capsys.readouterr().out


def test_history_no_local_history_fetches_current_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "history", "1"])
    monkeypatch.setattr(
        cli.requests,
        "get",
        lambda *a, **k: FakeResponse(200, {"version": 3, "updated_at": "now"}),
    )
    cli.history()
    assert "No local history found" in capsys.readouterr().out


def test_history_no_local_history_item_not_found(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "history", "1"])
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(404))
    cli.history()
    assert "not found" in capsys.readouterr().out


def test_history_no_local_history_other_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "history", "1"])
    monkeypatch.setattr(
        cli.requests, "get", lambda *a, **k: FakeResponse(500, {"detail": "boom"})
    )
    cli.history()
    assert "boom" in capsys.readouterr().out


def test_history_no_local_history_connection_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "history", "1"])

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "get", raise_conn_error)
    cli.history()
    assert "Could not connect" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# otp_command
# ---------------------------------------------------------------------------


def test_otp_command_missing_arg(capsys):
    cli.otp_command()
    assert "Usage" in capsys.readouterr().out


def test_otp_command_success(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "otp", "1"])
    monkeypatch.setattr(
        cli.requests,
        "get",
        lambda *a, **k: FakeResponse(200, {"id": 1, "content": "aa"}),
    )
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: "pw")
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")
    monkeypatch.setattr(cli, "decrypt_data", lambda data, key: b"SECRET")
    monkeypatch.setattr(cli, "get_totp_code", lambda secret: "654321")

    cli.otp_command()
    assert "654321" in capsys.readouterr().out


def test_otp_command_item_not_found(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "otp", "1"])
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(404))
    cli.otp_command()
    assert "not found" in capsys.readouterr().out


def test_otp_command_unauthenticated(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "otp", "1"])
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(401))
    cli.otp_command()
    assert "Not authenticated" in capsys.readouterr().out


def test_otp_command_other_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "otp", "1"])
    monkeypatch.setattr(
        cli.requests, "get", lambda *a, **k: FakeResponse(500, {"detail": "boom"})
    )
    cli.otp_command()
    assert "boom" in capsys.readouterr().out


def test_otp_command_connection_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "otp", "1"])

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "get", raise_conn_error)
    cli.otp_command()
    assert "Could not connect" in capsys.readouterr().out


def test_otp_command_keyboard_interrupt(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "otp", "1"])
    monkeypatch.setattr(
        cli.requests,
        "get",
        lambda *a, **k: FakeResponse(200, {"id": 1, "content": "aa"}),
    )

    def raise_interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "ask_master_password", raise_interrupt)
    cli.otp_command()
    assert "cancelled" in capsys.readouterr().out


def test_otp_command_decrypt_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "otp", "1"])
    monkeypatch.setattr(
        cli.requests,
        "get",
        lambda *a, **k: FakeResponse(200, {"id": 1, "content": "aa"}),
    )
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: "pw")
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")

    def raise_error(data, key):
        raise ValueError("bad")

    monkeypatch.setattr(cli, "decrypt_data", raise_error)
    cli.otp_command()
    assert "Failed to decrypt" in capsys.readouterr().out


def test_otp_command_totp_generation_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "otp", "1"])
    monkeypatch.setattr(
        cli.requests,
        "get",
        lambda *a, **k: FakeResponse(200, {"id": 1, "content": "aa"}),
    )
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: "pw")
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")
    monkeypatch.setattr(cli, "decrypt_data", lambda data, key: b"SECRET")

    def raise_error(secret):
        raise ValueError("bad secret")

    monkeypatch.setattr(cli, "get_totp_code", raise_error)
    cli.otp_command()
    assert "Failed to generate TOTP code" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# verify_otp_command
# ---------------------------------------------------------------------------


def test_verify_otp_command_missing_args(capsys):
    cli.verify_otp_command()
    assert "Usage" in capsys.readouterr().out


def _prep_verify(monkeypatch, item=None):
    monkeypatch.setattr(sys, "argv", ["cli.py", "verify-otp", "1", "123456"])
    monkeypatch.setattr(
        cli.requests,
        "get",
        lambda *a, **k: FakeResponse(200, item or {"id": 1, "content": "aa"}),
    )
    monkeypatch.setattr(cli, "ask_master_password", lambda *a, **k: "pw")
    monkeypatch.setattr(cli, "derive_key", lambda pw, salt: b"key")
    monkeypatch.setattr(cli, "decrypt_data", lambda data, key: b"SECRET")


def test_verify_otp_command_valid_code(monkeypatch, capsys):
    _prep_verify(monkeypatch)
    monkeypatch.setattr(cli, "verify_totp", lambda secret, code: True)
    cli.verify_otp_command()
    assert "valid" in capsys.readouterr().out


def test_verify_otp_command_invalid_code(monkeypatch, capsys):
    _prep_verify(monkeypatch)
    monkeypatch.setattr(cli, "verify_totp", lambda secret, code: False)
    cli.verify_otp_command()
    assert "invalid or expired" in capsys.readouterr().out


def test_verify_otp_command_item_not_found(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "verify-otp", "1", "123456"])
    monkeypatch.setattr(cli.requests, "get", lambda *a, **k: FakeResponse(404))
    cli.verify_otp_command()
    assert "not found" in capsys.readouterr().out


def test_verify_otp_command_connection_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "verify-otp", "1", "123456"])

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(cli.requests, "get", raise_conn_error)
    cli.verify_otp_command()
    assert "Could not connect" in capsys.readouterr().out


def test_verify_otp_command_verification_error(monkeypatch, capsys):
    _prep_verify(monkeypatch)

    def raise_error(secret, code):
        raise ValueError("bad")

    monkeypatch.setattr(cli, "verify_totp", raise_error)
    cli.verify_otp_command()
    assert "Failed to verify code" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# version / help
# ---------------------------------------------------------------------------


def test_version_prints_version_and_build_date(capsys):
    cli.version()
    out = capsys.readouterr().out
    assert cli.VERSION in out
    assert cli.BUILD_DATE in out


def test_help_prints_usage(capsys):
    cli.help()
    assert "GophKeeper CLI" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# export_items / import_items
# ---------------------------------------------------------------------------


def test_export_items_missing_arg(capsys):
    cli.export_items()
    assert "Usage" in capsys.readouterr().out


def test_export_items_empty_cache(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "export", "out.json"])
    cli.cache.list_items.return_value = []
    cli.export_items()
    assert "Nothing to export" in capsys.readouterr().out


def test_export_items_writes_file(monkeypatch, tmp_path):
    out_file = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["cli.py", "export", str(out_file)])
    cli.cache.list_items.return_value = [{"id": 1}]

    cli.export_items()

    assert out_file.exists()
    assert json.loads(out_file.read_text()) == [{"id": 1}]


def test_export_items_existing_file_cancelled(monkeypatch, tmp_path):
    out_file = tmp_path / "out.json"
    out_file.write_text("[]")
    monkeypatch.setattr(sys, "argv", ["cli.py", "export", str(out_file)])
    cli.cache.list_items.return_value = [{"id": 1}]
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: False)

    cli.export_items()

    assert out_file.read_text() == "[]"


def test_export_items_existing_file_overwritten(monkeypatch, tmp_path):
    out_file = tmp_path / "out.json"
    out_file.write_text("[]")
    monkeypatch.setattr(sys, "argv", ["cli.py", "export", str(out_file)])
    cli.cache.list_items.return_value = [{"id": 42}]
    monkeypatch.setattr(cli.Confirm, "ask", lambda *a, **k: True)

    cli.export_items()

    assert json.loads(out_file.read_text()) == [{"id": 42}]


def test_import_items_missing_arg(capsys):
    cli.import_items()
    assert "Usage" in capsys.readouterr().out


def test_import_items_invalid_json(monkeypatch, tmp_path, capsys):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not json")
    monkeypatch.setattr(sys, "argv", ["cli.py", "import", str(bad_file)])
    cli.import_items()
    assert "Invalid file" in capsys.readouterr().out


def test_import_items_not_a_list(monkeypatch, tmp_path, capsys):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({"not": "a list"}))
    monkeypatch.setattr(sys, "argv", ["cli.py", "import", str(bad_file)])
    cli.import_items()
    assert "Invalid file" in capsys.readouterr().out


def test_import_items_new_and_overwritten(monkeypatch, tmp_path, capsys):
    data = [{"id": 1}, {"id": 2}, {"no_id": True}]
    in_file = tmp_path / "in.json"
    in_file.write_text(json.dumps(data))
    monkeypatch.setattr(sys, "argv", ["cli.py", "import", str(in_file)])
    cli.cache.list_items.return_value = [{"id": 1}]

    cli.import_items()

    out = capsys.readouterr().out
    assert "1 new, 1 overwritten" in out
    assert cli.cache.upsert.call_count == 2  # the item without "id" is skipped


# ---------------------------------------------------------------------------
# tui
# ---------------------------------------------------------------------------


def test_tui_invokes_tui_main(monkeypatch):
    fake_module = SimpleNamespace(main=MagicMock())
    monkeypatch.setitem(sys.modules, "tui", fake_module)

    cli.tui()

    fake_module.main.assert_called_once()


# ---------------------------------------------------------------------------
# main() dispatcher
# ---------------------------------------------------------------------------


def test_main_no_command_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py"])
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 1
    assert "No command provided" in capsys.readouterr().out


def test_main_unknown_command_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "not-a-real-command"])
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 1
    assert "Unknown command" in capsys.readouterr().out


def test_main_dispatches_to_matching_command(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["cli.py", "VERSION"]
    )  # command matching is lowercased
    called = MagicMock()
    monkeypatch.setitem(cli.COMMANDS, "version", called)
    cli.main()
    called.assert_called_once()
