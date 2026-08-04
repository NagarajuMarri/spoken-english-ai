from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .models import CacheKind


@dataclass(frozen=True)
class CacheValue:
    key: str
    kind: CacheKind
    version: int
    content: str


class VersionedLessonCache:
    def __init__(self) -> None:
        self._items: dict[tuple[str, CacheKind, int], CacheValue] = {}
        self._hits = 0
        self._misses = 0
        self._invalidations = 0

    def put(self, key: str, kind: CacheKind, content: str, *, version: int = 1) -> CacheValue:
        value = CacheValue(key, kind, version, content)
        self._items[(key, kind, version)] = value
        return value

    def get(self, key: str, kind: CacheKind, *, version: int = 1) -> CacheValue | None:
        value = self._items.get((key, kind, version))
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
    def __init__(self) -> None:
        self._items: dict[str, str] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(text: str, tutor_voice: str) -> str:
        canonical = f"{tutor_voice.strip().lower()}\0{' '.join(text.split())}"
        return sha256(canonical.encode()).hexdigest()

    def resolve(self, text: str, tutor_voice: str) -> str | None:
        value = self._items.get(self.key(text, tutor_voice))
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def store(self, text: str, tutor_voice: str, audio_reference: str) -> None:
        self._items[self.key(text, tutor_voice)] = audio_reference
