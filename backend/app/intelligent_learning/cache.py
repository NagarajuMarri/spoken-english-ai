from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from collections.abc import Callable

from .models import CacheKind


@dataclass(frozen=True)
class CacheValue:
    key: str
    kind: CacheKind
    version: int
    content: str
    expires_at: datetime


class VersionedLessonCache:
    def __init__(self, *, max_entries: int = 500, ttl: timedelta = timedelta(days=30), clock: Callable[[], datetime] | None = None) -> None:
        if max_entries <= 0 or ttl <= timedelta(0):
            raise ValueError("Cache retention must be positive and bounded")
        self.max_entries, self.ttl = max_entries, ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._items: dict[tuple[str, CacheKind, int], CacheValue] = {}
        self._hits = 0
        self._misses = 0
        self._invalidations = 0

    def put(self, key: str, kind: CacheKind, content: str, *, version: int = 1) -> CacheValue:
        value = CacheValue(key, kind, version, content, self._clock() + self.ttl)
        self._items[(key, kind, version)] = value
        while len(self._items) > self.max_entries:
            del self._items[next(iter(self._items))]
        return value

    def get(self, key: str, kind: CacheKind, *, version: int = 1) -> CacheValue | None:
        value = self._items.get((key, kind, version))
        if value is not None and value.expires_at <= self._clock():
            del self._items[(key, kind, version)]
            value = None
        if value is None:
            self._misses += 1
        else:
            self._hits += 1
        return value

    def invalidate(self, key: str, kind: CacheKind, *, before_version: int | None = None) -> int:
        matches = [item for item in self._items if item[0] == key and item[1] == kind and (before_version is None or item[2] < before_version)]
        for item in matches:
            del self._items[item]
        self._invalidations += len(matches)
        return len(matches)

    def statistics(self) -> dict[str, int | float]:
        total = self._hits + self._misses
        return {"entries": len(self._items), "hits": self._hits, "misses": self._misses, "invalidations": self._invalidations, "hit_rate": self._hits / total if total else 0.0}


class TTSAudioCache:
    def __init__(self, *, max_entries: int = 500, ttl: timedelta = timedelta(days=7), clock: Callable[[], datetime] | None = None) -> None:
        if max_entries <= 0 or ttl <= timedelta(0):
            raise ValueError("Cache retention must be positive and bounded")
        self.max_entries, self.ttl = max_entries, ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._items: dict[str, str] = {}
        self._expires: dict[str, datetime] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(text: str, tutor_voice: str, privacy_scope: str = "shared-public") -> str:
        canonical = f"{privacy_scope}\0{tutor_voice.strip().lower()}\0{' '.join(text.split())}"
        return sha256(canonical.encode()).hexdigest()

    def resolve(self, text: str, tutor_voice: str, *, privacy_scope: str = "shared-public") -> str | None:
        key = self.key(text, tutor_voice, privacy_scope)
        value = self._items.get(key)
        if value is not None and self._expires[key] <= self._clock():
            del self._items[key]
            del self._expires[key]
            value = None
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def store(self, text: str, tutor_voice: str, audio_reference: str, *, privacy_scope: str = "shared-public", consent: bool = True, completed: bool = True, cancelled: bool = False) -> bool:
        if not consent or not completed or cancelled or not audio_reference:
            return False
        key = self.key(text, tutor_voice, privacy_scope)
        self._items[key] = audio_reference
        self._expires[key] = self._clock() + self.ttl
        while len(self._items) > self.max_entries:
            oldest = next(iter(self._items))
            del self._items[oldest]
            del self._expires[oldest]
        return True
