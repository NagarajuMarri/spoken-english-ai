from __future__ import annotations

import time
from typing import Protocol


class DistributedStore(Protocol):
    def increment(self, key: str, ttl_seconds: int) -> int: ...
    def claim(self, key: str, value: str, ttl_seconds: int) -> bool: ...
    def get(self, key: str) -> str | None: ...


class InMemoryDistributedStore:
    """Deterministic local implementation for limits, locks and health state."""

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self._values: dict[str, tuple[str, float]] = {}

    def _read(self, key: str) -> str | None:
        value = self._values.get(key)
        if not value:
            return None
        if value[1] <= self.clock():
            self._values.pop(key, None)
            return None
        return value[0]

    def increment(self, key: str, ttl_seconds: int) -> int:
        count = int(self._read(key) or 0) + 1
        self._values[key] = (str(count), self.clock() + ttl_seconds)
        return count

    def claim(self, key: str, value: str, ttl_seconds: int) -> bool:
        if self._read(key) is not None:
            return False
        self._values[key] = (value, self.clock() + ttl_seconds)
        return True

    def get(self, key: str) -> str | None:
        return self._read(key)


class RedisDistributedStore:
    """Redis adapter; accepts a redis-py compatible client at composition time."""

    def __init__(self, client) -> None:
        self.client = client

    def increment(self, key: str, ttl_seconds: int) -> int:
        value = int(self.client.incr(key))
        if value == 1:
            self.client.expire(key, ttl_seconds)
        return value

    def claim(self, key: str, value: str, ttl_seconds: int) -> bool:
        return bool(self.client.set(key, value, nx=True, ex=ttl_seconds))

    def get(self, key: str) -> str | None:
        value = self.client.get(key)
        return value.decode() if isinstance(value, bytes) else value
