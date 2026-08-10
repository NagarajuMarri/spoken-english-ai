from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from backend.app.api.routes.health import authentication_schema_is_compatible, ready
from backend.app.core.config import Settings
from backend.app.core.operations import RATE_POLICIES, RedisRateLimiter
from backend.app.db.schema import ALEMBIC_HEAD_REVISION
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
    def ping(self): return True
    def get(self, key): return self.values.get(key)


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


def test_readiness_rejects_stamped_head_with_legacy_authentication_schema():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE learners (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE refresh_tokens (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": ALEMBIC_HEAD_REVISION})
        assert authentication_schema_is_compatible(connection) is False


def _install_compatible_schema(connection, revision=ALEMBIC_HEAD_REVISION):
    connection.execute(text("CREATE TABLE user_accounts (session_epoch INTEGER NOT NULL)"))
    connection.execute(text("CREATE TABLE learners (user_account_id VARCHAR(36))"))
    connection.execute(text("CREATE TABLE refresh_tokens (family_id VARCHAR(36), parent_token_id VARCHAR(36))"))
    connection.execute(text(
        "CREATE TABLE password_reset_tokens ("
        "user_id VARCHAR(36), token_hash VARCHAR(64), expires_at DATETIME, used_at DATETIME)"
    ))
    connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision})


def _health_request(engine, *, environment="test", redis=None, worker_enabled=False):
    settings = SimpleNamespace(
        environment=environment,
        auto_create_tables=False,
        providers_ready=lambda: True,
        signing_keys=lambda: {"active": "x" * 32},
        redis_required=environment == "production",
        worker_enabled=worker_enabled,
        worker_heartbeat_key="spoken-english:worker:heartbeat",
        llm_provider="fake",
        speech_to_text_provider="fake",
        text_to_speech_provider="fake",
        openai_api_key="",
        razorpay_enabled=False,
        razorpay_webhook_secret="",
    )
    state = SimpleNamespace(
        settings=settings,
        engine=engine,
        redis=redis,
        object_storage=SimpleNamespace(healthcheck=lambda: True),
    )
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_readiness_accepts_actual_head_and_rejects_stale_revision():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    with engine.begin() as connection:
        _install_compatible_schema(connection)

    accepted = ready(_health_request(engine))
    assert accepted.status_code == 200
    assert json.loads(accepted.body)["checks"]["migration"] == "ready"

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = :revision"),
            {"revision": "0014_native_telugu_review"},
        )
    rejected = ready(_health_request(engine))
    assert rejected.status_code == 503
    assert json.loads(rejected.body)["checks"]["migration"] == "incompatible"
    engine.dispose()


def test_runtime_schema_revision_matches_the_alembic_head():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_current_head() == ALEMBIC_HEAD_REVISION


def test_subscription_uniqueness_migration_fails_closed_on_legacy_duplicates(monkeypatch):
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    migration = scripts.get_revision("0015_subscription_runtime").module
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE commercial_subscriptions (id VARCHAR(36), learner_id VARCHAR(36))"
        ))
        connection.execute(text(
            "INSERT INTO commercial_subscriptions (id, learner_id) "
            "VALUES ('one', 'learner'), ('two', 'learner')"
        ))
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)
        with pytest.raises(RuntimeError, match="duplicate commercial subscriptions"):
            migration.upgrade()
    engine.dispose()


def test_subscription_uniqueness_migration_enforces_clean_legacy_data(monkeypatch):
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    migration = scripts.get_revision("0015_subscription_runtime").module
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE commercial_subscriptions (id VARCHAR(36), learner_id VARCHAR(36))"
        ))
        connection.execute(text(
            "INSERT INTO commercial_subscriptions (id, learner_id) VALUES ('one', 'learner')"
        ))
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)

        migration.upgrade()

        with pytest.raises(IntegrityError):
            connection.execute(text(
                "INSERT INTO commercial_subscriptions (id, learner_id) "
                "VALUES ('two', 'learner')"
            ))
    engine.dispose()


def test_stt_attempt_migration_defines_privacy_minimised_idempotency(monkeypatch):
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    migration = scripts.get_revision("0016_stt_attempts").module
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE learners (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE conversations (id VARCHAR(36) PRIMARY KEY)"))
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)

        migration.upgrade()

        columns = {column["name"] for column in inspect(connection).get_columns("voice_transcription_attempts")}
        assert {"audio_digest", "idempotency_key", "charge_duration_ms", "result_json"} <= columns
        assert {"audio_bytes", "raw_audio"}.isdisjoint(columns)
        unique_columns = {
            tuple(constraint["column_names"])
            for constraint in inspect(connection).get_unique_constraints("voice_transcription_attempts")
        }
        assert ("conversation_id", "idempotency_key") in unique_columns
    engine.dispose()


def test_provider_call_migration_records_each_dated_call_without_raw_audio(monkeypatch):
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    migration = scripts.get_revision("0017_provider_call_events").module
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE learners (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE user_accounts (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO learners (id) VALUES ('learner')"))
        connection.execute(text("INSERT INTO user_accounts (id) VALUES ('user')"))
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)

        migration.upgrade()

        reflected_columns = {
            column["name"]: column
            for column in inspect(connection).get_columns("provider_call_events")
        }
        assert {
            "attempt_reference",
            "operation_kind",
            "request_count",
            "duration_ms",
            "occurred_at",
            "completed_at",
        } <= reflected_columns.keys()
        assert reflected_columns["duration_ms"]["nullable"] is False
        assert reflected_columns["occurred_at"]["nullable"] is False
        assert {
            "audio",
            "audio_bytes",
            "raw_audio",
            "request_payload",
            "response_payload",
            "transcript",
        }.isdisjoint(reflected_columns)

        event_values = {
            "learner_id": "learner",
            "user_id": "user",
            "operation_kind": "stt",
            "attempt_reference": "attempt-one",
            "request_count": 1,
            "input_units": 0,
            "output_units": 0,
            "outcome": "SUCCESS",
            "failed": False,
            "completed_at": None,
        }
        connection.execute(
            text(
                "INSERT INTO provider_call_events "
                "(id, learner_id, user_id, operation_kind, attempt_reference, request_count, "
                "duration_ms, input_units, output_units, outcome, failed, occurred_at, completed_at) "
                "VALUES (:id, :learner_id, :user_id, :operation_kind, :attempt_reference, :request_count, "
                ":duration_ms, :input_units, :output_units, :outcome, :failed, :occurred_at, :completed_at)"
            ),
            [
                {**event_values, "id": "call-one", "duration_ms": 1_250, "occurred_at": "2026-08-09T23:59:59Z"},
                {**event_values, "id": "call-two", "duration_ms": 2_500, "occurred_at": "2026-08-10T00:00:01Z"},
            ],
        )
        calls = connection.execute(text(
            "SELECT duration_ms, occurred_at FROM provider_call_events ORDER BY occurred_at"
        )).mappings().all()
        assert [call["duration_ms"] for call in calls] == [1_250, 2_500]
        assert calls[0]["occurred_at"] != calls[1]["occurred_at"]
    engine.dispose()


def test_production_worker_readiness_uses_redis_heartbeat():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    with engine.begin() as connection:
        _install_compatible_schema(connection)
    redis = FakeRedis()
    redis.values["spoken-english:worker:heartbeat"] = "alive"

    available = ready(_health_request(
        engine,
        environment="production",
        redis=redis,
        worker_enabled=True,
    ))
    assert available.status_code == 200
    assert json.loads(available.body)["checks"]["worker"] == "ready"

    redis.values.pop("spoken-english:worker:heartbeat")
    unavailable = ready(_health_request(
        engine,
        environment="production",
        redis=redis,
        worker_enabled=True,
    ))
    assert unavailable.status_code == 503
    assert json.loads(unavailable.body)["checks"]["worker"] == "unavailable"
    engine.dispose()
