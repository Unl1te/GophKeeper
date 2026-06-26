"""
Local cache for the GophKeeper CLI.

Stores item metadata (``id``, ``version``, ``type``, ``updated_at``, ``metadata``)
in a small JSON file under the user's config dir, so the client can:

* serve ``list`` from the cache instead of hitting the server every time;
* on ``get``, compare the cached ``version`` with the server's and only refetch
  the full payload when the server has a newer version;
* refresh the cache via :meth:`LocalCache.sync` after every exchange with the
  server.

The module is deliberately self-contained (standard library only) so it can be
unit-tested and wired into the CLI commands once the server item API lands.
"""

from __future__ import annotations

import json
import os
from typing import Optional

DEFAULT_CACHE_DIR = os.path.expanduser("~/.gophkeeper")
DEFAULT_CACHE_FILE = os.path.join(DEFAULT_CACHE_DIR, "cache.json")

# Fields kept for every cached item.
ITEM_FIELDS = ("id", "version", "type", "updated_at", "metadata")


class LocalCache:
    """JSON-backed cache of item metadata, keyed by item id."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or DEFAULT_CACHE_FILE

    # ------------------------------------------------------------------ I/O
    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            # A corrupt or unreadable cache must never break the CLI.
            return {}
        items = data.get("items", {})
        return items if isinstance(items, dict) else {}

    def _save(self, items: dict) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)  # atomic on POSIX and Windows

    @staticmethod
    def _normalize(item: dict) -> dict:
        if item.get("id") is None:
            raise ValueError("cached item must have an 'id'")
        return {key: item.get(key) for key in ITEM_FIELDS}

    # ---------------------------------------------------------------- reads
    def list_items(self) -> list:
        """All cached items, sorted by id (for ``list`` with no server round-trip)."""
        return sorted(self._load().values(), key=lambda it: it.get("id"))

    def get(self, item_id) -> Optional[dict]:
        return self._load().get(str(item_id))

    def get_version(self, item_id) -> Optional[int]:
        item = self.get(item_id)
        return item.get("version") if item else None

    def is_stale(self, item_id, server_version: int) -> bool:
        """True if the server's version is newer than the cache (so ``get`` refetches)."""
        cached = self.get_version(item_id)
        return cached is None or server_version > cached

    # --------------------------------------------------------------- writes
    def upsert(self, item: dict) -> None:
        """Insert or update a single item."""
        items = self._load()
        normalized = self._normalize(item)
        items[str(normalized["id"])] = normalized
        self._save(items)

    def sync(self, server_items: list) -> None:
        """Replace the whole cache with the server's current list of items."""
        items = {}
        for raw in server_items:
            normalized = self._normalize(raw)
            items[str(normalized["id"])] = normalized
        self._save(items)

    def remove(self, item_id) -> None:
        items = self._load()
        if str(item_id) in items:
            del items[str(item_id)]
            self._save(items)

    def clear(self) -> None:
        self._save({})
