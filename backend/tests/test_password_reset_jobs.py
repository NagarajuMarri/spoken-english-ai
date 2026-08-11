import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.cli.worker import process_job
from backend.app.core.security import hash_password_reset_token
from backend.app.jobs import Job, JobStatus, RedisJobQueue
from backend.app.models import PasswordResetToken, SecurityAuditEvent, UserAccount
from backend.app.providers.password_reset import RedisPasswordResetDispatch
from backend.app.providers.password_reset.dispatch import PASSWORD_RESET_EMAIL_JOB_KIND
from backend.app.providers.password_reset.jobs import PasswordResetEmailJobHandler


class FakePipeline:
    def __init__(self, client, transaction=True):
        self.client = client
        self.operations = []

    def lrem(self, key, count, value):
        self.operations.append(("lrem", key, count, value))
        return self

    def lpush(self, key, value):
        self.operations.append(("lpush", key, value))
        return self

    def execute(self):
        results = []
        for operation in self.operations:
            if operation[0] == "lrem":
                results.append(self.client.lrem(*operation[1:]))
            else:
                results.append(self.client.lpush(*operation[1:]))
        return results


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.lists = {}

    def pipeline(self, transaction=True):
        return FakePipeline(self, transaction)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def eval(
        self,
        script,
        key_count,
        idempotency_key,
        queue_key,
        job_id,
        payload,
        ttl,
    ):
        _ = script, key_count
        if idempotency_key in self.values:
            return 0
        self.values[idempotency_key] = job_id
        self.ttls[idempotency_key] = int(ttl)
        self.lpush(queue_key, payload)
        return 1

    def delete(self, key):
        self.values.pop(key, None)

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)
        return len(self.lists[key])

    def brpoplpush(self, source, destination, timeout=0):
        _ = timeout
        if not self.lists.get(source):
            return None
        value = self.lists[source].pop()
        self.lists.setdefault(destination, []).insert(0, value)
        return value

    def rpoplpush(self, source, destination):
        if not self.lists.get(source):
            return None
        value = self.lists[source].pop()
        self.lists.setdefault(destination, []).insert(0, value)
        return value

    def lrem(self, key, count, value):
        values = self.lists.get(key, [])
        removed = 0
        retained = []
        for item in values:
            if item == value and (count == 0 or removed < count):
                removed += 1
            else:
                retained.append(item)
        self.lists[key] = retained
        return removed


class RecordingDelivery:
    def __init__(self, failures=0, failure_text="temporary SMTP failure"):
        self.failures = failures
        self.failure_text = failure_text
        self.calls = []

    def deliver(self, recipient, verification_code):
        self.calls.append((recipient, verification_code))
        if len(self.calls) <= self.failures:
            raise RuntimeError(self.failure_text)


def _register(client, email="queued-reset@example.com"):
    response = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "StrongPassword123!",
        "display_name": "Queued Reset",
        "terms_privacy_accepted": True,
    })
    assert response.status_code == 201
    return response.json()


def _reset_record(client, raw_token="123456"):
    _register(client)
    with client.app.state.session_factory() as session:
        user = session.scalar(select(UserAccount).where(
            UserAccount.email == "queued-reset@example.com"
        ))
        reset = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_token(f"{user.id}:{raw_token}"),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        session.add(reset)
        session.commit()
        reset_id = reset.id
    return reset_id, raw_token, raw_token


def _handler(client, delivery):
    return PasswordResetEmailJobHandler(
        client.app.state.session_factory,
        delivery,
        public_frontend_url="http://localhost:5173",
    )


def test_request_path_enqueues_without_smtp_and_applies_same_response_floor(
    client, monkeypatch
):
    from backend.app.services import auth as auth_service

    _register(client)
    redis = FakeRedis()
    queue = RedisJobQueue(redis)
    client.app.state.password_reset_dispatch = RedisPasswordResetDispatch(
        queue,
        maximum_attempts=3,
        idempotency_ttl_seconds=3_600,
    )
    floors = []
    monkeypatch.setattr(
        auth_service,
        "enforce_password_reset_response_floor",
        lambda _started_at, minimum_milliseconds: floors.append(minimum_milliseconds),
    )

    known = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "queued-reset@example.com"},
    )
    unknown = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "unknown-queued-reset@example.com"},
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert floors == [0, 0]
    assert client.app.state.password_reset_delivery.deliveries == []
    queued = redis.lists[queue.queue_key]
    assert len(queued) == 1
    assert "queued-reset@example.com" not in queued[0]
    with client.app.state.session_factory() as session:
        reset = session.scalar(select(PasswordResetToken))
    payload = json.loads(queued[0])
    client.app.state.password_reset_dispatch.dispatch(
        reset.id,
        "queued-reset@example.com",
        payload["payload"]["verification_code"],
    )
    assert len(redis.lists[queue.queue_key]) == 1


def test_queue_submission_failure_is_neutral_and_invalidates_token(client):
    class FailingRedis(FakeRedis):
        def lpush(self, key, value):
            _ = key, value
            raise RuntimeError("queue unavailable")

    _register(client)
    redis = FailingRedis()
    queue = RedisJobQueue(redis)
    client.app.state.password_reset_dispatch = RedisPasswordResetDispatch(
        queue,
        maximum_attempts=3,
        idempotency_ttl_seconds=3_600,
    )

    known = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "queued-reset@example.com"},
    )
    unknown = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "unknown-queued-reset@example.com"},
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert redis.lists.get(queue.queue_key, []) == []
    with client.app.state.session_factory() as session:
        reset = session.scalar(select(PasswordResetToken))
        failure = session.scalar(select(SecurityAuditEvent).where(
            SecurityAuditEvent.event_type == "PASSWORD_RESET_DELIVERY_FAILED"
        ))
        assert reset.used_at is not None
        assert failure.outcome == "FAILED"
        assert failure.reason_code == "delivery_unavailable"


def test_transient_delivery_retries_then_records_success(client):
    reset_id, reset_url, _ = _reset_record(client)
    redis = FakeRedis()
    queue = RedisJobQueue(redis)
    RedisPasswordResetDispatch(
        queue,
        maximum_attempts=3,
        idempotency_ttl_seconds=3_600,
    ).dispatch(reset_id, "queued-reset@example.com", reset_url)
    delivery = RecordingDelivery(failures=1)
    handler = _handler(client, delivery)

    first = queue.take()
    process_job(queue, first, handler)
    assert first.status == JobStatus.RETRYING
    second = queue.take()
    process_job(queue, second, handler)

    assert second.status == JobStatus.SUCCEEDED
    assert len(delivery.calls) == 2
    assert redis.lists[queue.processing_key] == []
    with client.app.state.session_factory() as session:
        reset = session.get(PasswordResetToken, reset_id)
        success = session.scalar(select(SecurityAuditEvent).where(
            SecurityAuditEvent.event_type == "PASSWORD_RESET_DELIVERY_SUCCEEDED"
        ))
        assert reset.used_at is None
        assert success.outcome == "SUCCEEDED"
        assert success.reason_code == "smtp_accepted"


def test_worker_restart_recovers_inflight_password_reset_job(client):
    reset_id, reset_url, _ = _reset_record(client)
    redis = FakeRedis()
    queue = RedisJobQueue(redis)
    RedisPasswordResetDispatch(
        queue,
        maximum_attempts=3,
        idempotency_ttl_seconds=3_600,
    ).dispatch(reset_id, "queued-reset@example.com", reset_url)

    taken = queue.take()
    assert taken is not None
    assert redis.lists[queue.processing_key]

    restarted = RedisJobQueue(redis)
    assert restarted.recover_inflight() == 1
    recovered = restarted.take()
    assert recovered is not None
    assert recovered.job_id == taken.job_id
    restarted.complete(recovered)
    assert redis.lists[restarted.processing_key] == []


def test_terminal_delivery_failure_scrubs_dead_letter_and_invalidates_token(
    client, caplog
):
    reset_id, reset_url, raw_token = _reset_record(client)
    recipient = "queued-reset@example.com"
    sensitive_error = f"provider rejected {recipient} {raw_token}"
    redis = FakeRedis()
    queue = RedisJobQueue(redis)
    RedisPasswordResetDispatch(
        queue,
        maximum_attempts=2,
        idempotency_ttl_seconds=3_600,
    ).dispatch(reset_id, recipient, reset_url)
    handler = _handler(
        client,
        RecordingDelivery(failures=2, failure_text=sensitive_error),
    )

    process_job(queue, queue.take(), handler)
    terminal = queue.take()
    process_job(queue, terminal, handler)

    assert terminal.status == JobStatus.DEAD_LETTER
    dead_letter = redis.lists[queue.dead_letter_key][0]
    for sensitive in (recipient, raw_token, reset_url, sensitive_error, reset_id):
        assert sensitive not in dead_letter
        assert sensitive not in caplog.text
    decoded = json.loads(dead_letter)
    assert decoded["payload"] == {
        "outcome": "terminal_failure",
        "sensitive_payload": "redacted",
    }
    assert decoded["idempotency_key"] == "redacted"
    with client.app.state.session_factory() as session:
        reset = session.get(PasswordResetToken, reset_id)
        failure = session.scalar(select(SecurityAuditEvent).where(
            SecurityAuditEvent.event_type == "PASSWORD_RESET_DELIVERY_FAILED"
        ))
        assert reset.used_at is not None
        assert failure.outcome == "FAILED"
        assert failure.reason_code == "delivery_retry_limit_reached"
        assert recipient not in json.dumps(failure.metadata_json)
        assert raw_token not in json.dumps(failure.metadata_json)


def test_malformed_password_reset_job_is_safely_dead_lettered(client):
    redis = FakeRedis()
    queue = RedisJobQueue(redis)
    queue.submit(Job(
        kind=PASSWORD_RESET_EMAIL_JOB_KIND,
        payload={"reset_url": "https://attacker.invalid/reset-password#token=secret"},
        idempotency_key="malformed-sensitive-reference",
        max_attempts=3,
    ))

    malformed = queue.take()
    assert malformed is not None
    process_job(queue, malformed, _handler(client, RecordingDelivery()))

    assert malformed.status == JobStatus.DEAD_LETTER
    dead_letter = redis.lists[queue.dead_letter_key][0]
    assert "attacker.invalid" not in dead_letter
    assert "secret" not in dead_letter
    assert "malformed-sensitive-reference" not in dead_letter
