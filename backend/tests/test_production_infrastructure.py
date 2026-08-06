from datetime import datetime, timezone

import pytest

from backend.app.core.config import Settings
from backend.app.core.operations import RATE_POLICIES, RedisRateLimiter
from backend.app.jobs import Job, JobStatus, RedisJobQueue
from backend.app.storage import S3ObjectStorageBoundary


class FakePipeline:
    def __init__(self, client): self.client = client
    def incr(self, key): self.key = key; return self
    def ttl(self, key): return self
    def execute(self):
        self.client.values[self.key] = int(self.client.values.get(self.key, 0)) + 1
        return [self.client.values[self.key], self.client.ttls.get(self.key, -1)]


class FakeRedis:
    def __init__(self): self.values = {}; self.ttls = {}; self.lists = {}
    def pipeline(self): return FakePipeline(self)
    def expire(self, key, ttl): self.ttls[key] = ttl
    def delete(self, key): self.values.pop(key, None)
    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values: return False
        self.values[key] = value
        if ex: self.ttls[key] = ex
        return True
    def lpush(self, key, value): self.lists.setdefault(key, []).insert(0, value)
    def brpop(self, key, timeout=0):
        return (key, self.lists[key].pop()) if self.lists.get(key) else None


class FakeS3:
    def __init__(self): self.calls = []
    def put_object(self, **kwargs): self.calls.append(("put", kwargs))
    def delete_object(self, **kwargs): self.calls.append(("delete", kwargs))
    def generate_presigned_url(self, operation, Params, ExpiresIn): return f"signed:{Params['Key']}:{ExpiresIn}"
    def head_bucket(self, **kwargs): self.calls.append(("head", kwargs))


def test_production_configuration_rejects_local_dependencies():
    with pytest.raises(ValueError, match="database_url.*object_storage_backend"):
        Settings(environment="production", auto_create_tables=False, force_https=True, secure_cookies=True, _env_file=None)


def test_redis_rate_limiter_and_job_retry_are_deterministic():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis)
    policy = RATE_POLICIES["registration"]
    assert all(limiter.decide(policy, "network").allowed for _ in range(policy.limit))
    assert not limiter.decide(policy, "network").allowed
    queue = RedisJobQueue(redis)
    job = queue.submit(Job("healthcheck", {}, "one", max_attempts=1))
    assert queue.take().job_id == job.job_id
    queue.fail(job)
    assert job.status == JobStatus.DEAD_LETTER


def test_s3_boundary_returns_metadata_only_reference():
    client = FakeS3()
    storage = S3ObjectStorageBoundary(client, "audio")
    reference = storage.put("users/u1/audio.webm", b"voice", "audio/webm", 1)
    assert reference.size_bytes == 5
    assert reference.expires_at > datetime.now(timezone.utc)
    assert reference.scoped_reference.startswith("signed:")
    assert storage.healthcheck()
    assert storage.delete(reference)
