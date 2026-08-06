from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from pathlib import Path
import re


SAFE_OBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")


@dataclass(frozen=True)
class ObjectReference:
    key: str
    content_type: str
    size_bytes: int
    expires_at: datetime
    scoped_reference: str


class LocalObjectStorage:
    """Local adapter. Relational records retain only ObjectReference metadata."""

    def __init__(self, root: Path, signing_key: str, clock=lambda: datetime.now(timezone.utc)) -> None:
        if len(signing_key) < 16:
            raise ValueError("Object-reference signing key is too short")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.signing_key = signing_key.encode()
        self.clock = clock

    def put(self, key: str, data: bytes, content_type: str, retention_hours: int = 24) -> ObjectReference:
        if not SAFE_OBJECT.fullmatch(key) or ".." in key:
            raise ValueError("Invalid object key")
        target = (self.root / key).resolve()
        if self.root not in target.parents:
            raise ValueError("Invalid object key")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        expires = self.clock() + timedelta(hours=retention_hours)
        signature = hmac.new(self.signing_key, f"{key}:{int(expires.timestamp())}".encode(), hashlib.sha256).hexdigest()
        return ObjectReference(key, content_type, len(data), expires, f"local:{key}:{int(expires.timestamp())}:{signature}")

    def delete(self, reference: ObjectReference) -> bool:
        target = (self.root / reference.key).resolve()
        if target.exists():
            target.unlink()
        return not target.exists()

    def cleanup_expired(self, references: list[ObjectReference]) -> list[str]:
        deleted = []
        for reference in references:
            if reference.expires_at <= self.clock() and self.delete(reference):
                deleted.append(reference.key)
        return deleted


class S3ObjectStorageBoundary:
    """Production boundary; credentials are injected and never represented in references."""

    def __init__(self, client, bucket: str) -> None:
        self.client, self.bucket = client, bucket

    def put(self, key: str, data: bytes, content_type: str, retention_hours: int = 24) -> ObjectReference:
        if not SAFE_OBJECT.fullmatch(key) or ".." in key:
            raise ValueError("Invalid object key")
        expires = datetime.now(timezone.utc) + timedelta(hours=retention_hours)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata={"expires-at": expires.isoformat()},
        )
        scoped = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=max(1, retention_hours * 3600),
        )
        return ObjectReference(key, content_type, len(data), expires, scoped)

    def delete(self, reference: ObjectReference) -> bool:
        self.client.delete_object(Bucket=self.bucket, Key=reference.key)
        return True

    def healthcheck(self) -> bool:
        self.client.head_bucket(Bucket=self.bucket)
        return True
