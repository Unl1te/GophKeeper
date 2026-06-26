import pytest

from cli_cache import LocalCache


@pytest.fixture
def cache(tmp_path):
    return LocalCache(path=str(tmp_path / "cache.json"))


def make_item(
    item_id,
    version=1,
    type="password",
    updated_at="2026-01-01T00:00:00Z",
    metadata=None,
):
    return {
        "id": item_id,
        "version": version,
        "type": type,
        "updated_at": updated_at,
        "metadata": metadata or {},
    }


def test_empty_cache(cache):
    assert cache.list_items() == []
    assert cache.get(1) is None
    assert cache.get_version(1) is None


def test_upsert_and_get(cache):
    cache.upsert(make_item(1, version=2))
    got = cache.get(1)
    assert got["id"] == 1
    assert got["version"] == 2
    assert got["type"] == "password"
    assert cache.get_version(1) == 2


def test_upsert_updates_existing(cache):
    cache.upsert(make_item(1, version=1))
    cache.upsert(make_item(1, version=5, type="text"))
    assert cache.get_version(1) == 5
    assert cache.get(1)["type"] == "text"
    assert len(cache.list_items()) == 1


def test_list_items_sorted_by_id(cache):
    cache.upsert(make_item(3))
    cache.upsert(make_item(1))
    cache.upsert(make_item(2))
    assert [it["id"] for it in cache.list_items()] == [1, 2, 3]


def test_only_known_fields_are_stored(cache):
    cache.upsert({**make_item(1), "secret": "should-not-persist"})
    assert set(cache.get(1).keys()) == {
        "id",
        "version",
        "type",
        "updated_at",
        "metadata",
    }


def test_sync_replaces_contents(cache):
    cache.upsert(make_item(99))
    cache.sync([make_item(1), make_item(2)])
    assert [it["id"] for it in cache.list_items()] == [1, 2]


def test_is_stale(cache):
    cache.upsert(make_item(1, version=3))
    assert cache.is_stale(1, server_version=4) is True  # server is newer
    assert cache.is_stale(1, server_version=3) is False  # same version
    assert cache.is_stale(2, server_version=1) is True  # not cached


def test_remove(cache):
    cache.upsert(make_item(1))
    cache.remove(1)
    assert cache.get(1) is None


def test_clear(cache):
    cache.upsert(make_item(1))
    cache.upsert(make_item(2))
    cache.clear()
    assert cache.list_items() == []


def test_persists_across_instances(cache):
    cache.upsert(make_item(1, version=7))
    reopened = LocalCache(path=cache.path)
    assert reopened.get_version(1) == 7


def test_corrupt_cache_is_ignored(cache, tmp_path):
    with open(cache.path, "w", encoding="utf-8") as f:
        f.write("not valid json {{{")
    assert cache.list_items() == []


def test_upsert_requires_id(cache):
    with pytest.raises(ValueError):
        cache.upsert({"version": 1})
