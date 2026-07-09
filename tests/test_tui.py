import pytest
import requests

import cli
import tui
from cli_cache import LocalCache
from crypto_interface import encrypt_data

SERVER = "http://localhost"
KEY = b"0" * 32  # ChaCha20-Poly1305 key (32 bytes)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    cli.cache = LocalCache(path=str(tmp_path / "cache.json"))
    monkeypatch.setattr(cli, "get_headers", lambda: {"Authorization": "Bearer t"})


def _item(item_id, version=1, type="text", content=None):
    d = {
        "id": item_id,
        "type": type,
        "version": version,
        "updated_at": "2026-01-01T00:00:00Z",
        "metadata": {},
    }
    if content is not None:
        d["content"] = content
    return d


def test_api_login_ok(requests_mock):
    requests_mock.post(f"{SERVER}/login", json={"access_token": "tok"})
    token, err = tui.api_login("u", "p")
    assert token == "tok" and err is None


def test_api_login_invalid(requests_mock):
    requests_mock.post(f"{SERVER}/login", status_code=401)
    token, err = tui.api_login("u", "bad")
    assert token is None and err


def test_api_list(requests_mock):
    requests_mock.get(f"{SERVER}/items", json=[_item(1), _item(2, version=3)])
    items, err = tui.api_list()
    assert err is None
    assert [i["id"] for i in items] == [1, 2]


def test_api_add_encrypts_before_sending(requests_mock):
    captured = {}

    def _cb(request, context):
        captured["json"] = request.json()
        context.status_code = 201
        return _item(3)

    requests_mock.post(f"{SERVER}/items", json=_cb)
    item, err = tui.api_add("text", b"my-secret", {"k": "v"}, KEY)
    assert err is None and item["id"] == 3
    sent = captured["json"]["content"]
    assert "my-secret" not in sent  # ciphertext, not plaintext
    assert bytes.fromhex(sent)  # valid hex ciphertext


def test_api_get_and_decrypt_roundtrip(requests_mock):
    ct = encrypt_data(b"hello world", KEY).hex()
    requests_mock.get(f"{SERVER}/items/7", json=_item(7, version=2, content=ct))
    item, err = tui.api_get(7)
    assert err is None
    assert tui._decrypt_content(item, KEY) == b"hello world"


def test_api_get_404(requests_mock):
    requests_mock.get(f"{SERVER}/items/99", status_code=404)
    item, err = tui.api_get(99)
    assert item is None and "not found" in err


def test_api_update_version_conflict(requests_mock):
    requests_mock.put(f"{SERVER}/items/5", status_code=409)
    item, err = tui.api_update(5, b"x", {}, 1, KEY)
    assert item is None and "conflict" in err.lower()


def test_api_delete(requests_mock):
    requests_mock.delete(f"{SERVER}/items/9", status_code=204)
    deleted, err = tui.api_delete(9)
    assert deleted is True and err is None
