import importlib
import json
import os

import cli


def test_defaults(monkeypatch):
    monkeypatch.delenv("GOPHKEEPER_HOME", raising=False)
    monkeypatch.delenv("GOPHKEEPER_SERVER", raising=False)
    importlib.reload(cli)
    assert cli.CONFIG_DIR == os.path.expanduser("~/.gophkeeper")
    assert cli.SERVER_URL == "http://localhost"


def test_config_dir_and_server_from_env(monkeypatch, tmp_path):
    home = str(tmp_path / "client-a")
    monkeypatch.setenv("GOPHKEEPER_HOME", home)
    monkeypatch.setenv("GOPHKEEPER_SERVER", "http://vm:80")
    try:
        importlib.reload(cli)
        assert cli.CONFIG_DIR == home
        assert cli.CONFIG_FILE == os.path.join(home, "config.json")
        assert cli.cache.path == os.path.join(home, "cache.json")
        assert cli.SERVER_URL == "http://vm:80"
    finally:
        monkeypatch.delenv("GOPHKEEPER_HOME", raising=False)
        monkeypatch.delenv("GOPHKEEPER_SERVER", raising=False)
        importlib.reload(cli)  # restore default module state for other tests


def test_two_clients_use_separate_dirs(monkeypatch, tmp_path):
    a = str(tmp_path / "a")
    b = str(tmp_path / "b")
    try:
        monkeypatch.setenv("GOPHKEEPER_HOME", a)
        importlib.reload(cli)
        cli.save_token("token-a")

        monkeypatch.setenv("GOPHKEEPER_HOME", b)
        importlib.reload(cli)
        cli.save_token("token-b")

        with open(os.path.join(a, "config.json")) as f:
            assert json.load(f)["token"] == "token-a"
        with open(os.path.join(b, "config.json")) as f:
            assert json.load(f)["token"] == "token-b"
    finally:
        monkeypatch.delenv("GOPHKEEPER_HOME", raising=False)
        importlib.reload(cli)
