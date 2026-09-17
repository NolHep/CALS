"""A tiny SQLite response cache.

The upstream API is rate limited, and repeated searches for the same state
are the common case, so caching responses is what keeps the app usable on a
free token.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any


class Cache:
    def __init__(self, path: str, ttl_seconds: int = 3600) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS responses ("
            "  key TEXT PRIMARY KEY,"
            "  stored_at REAL NOT NULL,"
            "  payload TEXT NOT NULL)"
        )
        self._conn.commit()

    def get(self, key: str) -> Any | None:
        cutoff = time.time() - self.ttl_seconds
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM responses WHERE key = ? AND stored_at > ?",
                (key, cutoff),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO responses (key, stored_at, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET stored_at = excluded.stored_at, "
                "payload = excluded.payload",
                (key, time.time(), json.dumps(value)),
            )
            self._conn.commit()

    def purge_expired(self) -> int:
        cutoff = time.time() - self.ttl_seconds
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM responses WHERE stored_at <= ?", (cutoff,)
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
