import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from crypto_interface import derive_key, encrypt_data, decrypt_data

BASE_URL = os.environ.get("GOPHKEEPER_TEST_SERVER", "http://localhost:8000")
MASTER_PASSWORD = "test-master-password"
SALT = b"gophkeeper_salt_16bytes"
KEY = derive_key(MASTER_PASSWORD, SALT)


def _skip_if_server_down():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=2)
        if r.status_code != 200 or r.json().get("status") != "ok":
            pytest.skip(f"GophKeeper server at {BASE_URL} is not healthy")
    except requests.exceptions.ConnectionError:
        pytest.skip(
            f"GophKeeper server not reachable at {BASE_URL} — start it with docker-compose up"
        )


@pytest.fixture(scope="module", autouse=True)
def ensure_server_up():
    _skip_if_server_down()


def _register_and_login(login: str, password: str) -> str:
    r = requests.post(
        f"{BASE_URL}/register", json={"login": login, "password": password}
    )
    assert r.status_code == 201, f"register failed: {r.status_code} {r.text}"

    r = requests.post(f"{BASE_URL}/login", json={"login": login, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _encrypt(text: str) -> str:
    return encrypt_data(text.encode("utf-8"), KEY).hex()


def _decrypt(hex_content: str) -> str:
    return decrypt_data(bytes.fromhex(hex_content), KEY).decode("utf-8")


@pytest.fixture
def user_and_item():
    unique = uuid.uuid4().hex[:10]
    login = f"conflict_test_{unique}"
    password = "Sup3rSecret!1"

    token_a = _register_and_login(login, password)
    r = requests.post(f"{BASE_URL}/login", json={"login": login, "password": password})
    assert r.status_code == 200
    token_b = r.json()["access_token"]

    r = requests.post(
        f"{BASE_URL}/items/",
        json={
            "type": "text",
            "content": _encrypt("initial content"),
            "metadata": {"case": "conflict"},
        },
        headers=_auth_headers(token_a),
    )
    assert r.status_code == 201, f"item creation failed: {r.status_code} {r.text}"
    item = r.json()

    yield {
        "token_a": token_a,
        "token_b": token_b,
        "item_id": item["id"],
        "version": item["version"],
    }

    requests.delete(f"{BASE_URL}/items/{item['id']}", headers=_auth_headers(token_a))


def test_second_stale_write_gets_409(user_and_item):
    item_id = user_and_item["item_id"]
    base_version = user_and_item["version"]
    token_a, token_b = user_and_item["token_a"], user_and_item["token_b"]

    r = requests.get(f"{BASE_URL}/items/{item_id}", headers=_auth_headers(token_a))
    assert r.status_code == 200
    assert r.json()["version"] == base_version

    r = requests.get(f"{BASE_URL}/items/{item_id}", headers=_auth_headers(token_b))
    assert r.status_code == 200
    assert r.json()["version"] == base_version

    r_a = requests.put(
        f"{BASE_URL}/items/{item_id}",
        json={
            "content": _encrypt("written by A"),
            "metadata": {"writer": "A"},
            "version": base_version,
        },
        headers=_auth_headers(token_a),
    )
    assert (
        r_a.status_code == 200
    ), f"first writer should succeed, got {r_a.status_code}: {r_a.text}"
    new_version = r_a.json()["version"]
    assert new_version == base_version + 1

    r_b = requests.put(
        f"{BASE_URL}/items/{item_id}",
        json={
            "content": _encrypt("written by B"),
            "metadata": {"writer": "B"},
            "version": base_version,
        },
        headers=_auth_headers(token_b),
    )
    assert (
        r_b.status_code == 409
    ), f"stale writer should get 409, got {r_b.status_code}: {r_b.text}"
    conflict_detail = r_b.json()["detail"]
    assert conflict_detail["current_version"] == new_version

    r_check = requests.get(
        f"{BASE_URL}/items/{item_id}", headers=_auth_headers(token_a)
    )
    assert r_check.status_code == 200
    assert r_check.json()["version"] == new_version
    assert _decrypt(r_check.json()["content"]) == "written by A"


def test_conflict_then_successful_retry(user_and_item):
    item_id = user_and_item["item_id"]
    base_version = user_and_item["version"]
    token_a, token_b = user_and_item["token_a"], user_and_item["token_b"]

    r_a = requests.put(
        f"{BASE_URL}/items/{item_id}",
        json={
            "content": _encrypt("A's update"),
            "metadata": {},
            "version": base_version,
        },
        headers=_auth_headers(token_a),
    )
    assert r_a.status_code == 200

    r_b_stale = requests.put(
        f"{BASE_URL}/items/{item_id}",
        json={
            "content": _encrypt("B's stale update"),
            "metadata": {},
            "version": base_version,
        },
        headers=_auth_headers(token_b),
    )
    assert r_b_stale.status_code == 409

    r_b_get = requests.get(
        f"{BASE_URL}/items/{item_id}", headers=_auth_headers(token_b)
    )
    assert r_b_get.status_code == 200
    current_version = r_b_get.json()["version"]
    assert current_version == base_version + 1

    r_b_retry = requests.put(
        f"{BASE_URL}/items/{item_id}",
        json={
            "content": _encrypt("B's retried update"),
            "metadata": {},
            "version": current_version,
        },
        headers=_auth_headers(token_b),
    )
    assert (
        r_b_retry.status_code == 200
    ), f"retry with fresh version should succeed: {r_b_retry.text}"
    assert r_b_retry.json()["version"] == current_version + 1

    r_final = requests.get(
        f"{BASE_URL}/items/{item_id}", headers=_auth_headers(token_a)
    )
    assert _decrypt(r_final.json()["content"]) == "B's retried update"


def test_third_client_also_gets_409_against_same_stale_version(user_and_item):
    item_id = user_and_item["item_id"]
    base_version = user_and_item["version"]
    token_a, token_b = user_and_item["token_a"], user_and_item["token_b"]

    r_a = requests.put(
        f"{BASE_URL}/items/{item_id}",
        json={
            "content": _encrypt("first writer"),
            "metadata": {},
            "version": base_version,
        },
        headers=_auth_headers(token_a),
    )
    assert r_a.status_code == 200

    for token, label in [(token_b, "B"), (token_a, "A-again")]:
        r = requests.put(
            f"{BASE_URL}/items/{item_id}",
            json={
                "content": _encrypt(f"stale write from {label}"),
                "metadata": {},
                "version": base_version,
            },
            headers=_auth_headers(token),
        )
        assert (
            r.status_code == 409
        ), f"{label} should still get 409 on stale version, got {r.status_code}"


def test_update_by_non_owner_is_404_not_409(user_and_item):
    item_id = user_and_item["item_id"]
    base_version = user_and_item["version"]

    stranger_login = f"stranger_{uuid.uuid4().hex[:10]}"
    stranger_token = _register_and_login(stranger_login, "Sup3rSecret!1")

    r = requests.put(
        f"{BASE_URL}/items/{item_id}",
        json={
            "content": _encrypt("hijack attempt"),
            "metadata": {},
            "version": base_version,
        },
        headers=_auth_headers(stranger_token),
    )
    assert (
        r.status_code == 404
    ), f"expected 404 for a non-owner's update, got {r.status_code}: {r.text}"


def test_update_with_correct_current_version_never_conflicts(user_and_item):
    item_id = user_and_item["item_id"]
    version = user_and_item["version"]
    token = user_and_item["token_a"]

    for i in range(5):
        r = requests.put(
            f"{BASE_URL}/items/{item_id}",
            json={
                "content": _encrypt(f"revision {i}"),
                "metadata": {},
                "version": version,
            },
            headers=_auth_headers(token),
        )
        assert (
            r.status_code == 200
        ), f"revision {i} unexpectedly conflicted: {r.status_code} {r.text}"
        version = r.json()["version"]
