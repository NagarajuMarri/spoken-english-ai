import json
import logging
import ssl
from types import SimpleNamespace

import pytest

from backend.app.core.config import Settings
from backend.app.providers.password_reset import SmtpPasswordResetDelivery, build_password_reset_delivery
from backend.app.providers.password_reset import delivery as delivery_module
from backend.app.services.auth import enforce_password_reset_response_floor


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls = []
        self.message = None
        self.__class__.instances.append(self)

    def __enter__(self):
        self.calls.append(("enter",))
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.calls.append(("exit", exc_type))

    def ehlo(self):
        self.calls.append(("ehlo",))

    def starttls(self, *, context):
        self.calls.append(("starttls", context))

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.message = message
        self.calls.append(("send_message",))


def smtp_settings():
    return SimpleNamespace(
        password_reset_email_from="SpeakMate <no-reply@test.speakmate.in>",
        smtp_host="smtp.test.speakmate.in",
        smtp_port=587,
        smtp_username="smtp-user",
        smtp_password="smtp-password-for-transport-test",
        smtp_timeout_seconds=9,
    )


def test_smtp_delivery_uses_verified_tls_auth_and_redacted_telemetry(monkeypatch, caplog):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(delivery_module.smtplib, "SMTP", FakeSMTP)
    caplog.set_level(logging.INFO, logger="spoken_english.password_reset_delivery")
    recipient = "private-learner@example.test"
    token = "123456"
    reset_url = token

    SmtpPasswordResetDelivery(smtp_settings()).deliver(recipient, reset_url)

    smtp = FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.test.speakmate.in", 587, 9)
    assert [call[0] for call in smtp.calls] == [
        "enter", "ehlo", "starttls", "ehlo", "login", "send_message", "exit"
    ]
    tls_context = smtp.calls[2][1]
    assert isinstance(tls_context, ssl.SSLContext)
    assert tls_context.check_hostname is True
    assert tls_context.verify_mode == ssl.CERT_REQUIRED
    assert smtp.calls[4] == ("login", "smtp-user", "smtp-password-for-transport-test")
    assert smtp.message["Subject"] == "SpeakMate password reset code"
    assert smtp.message["From"] == "SpeakMate <no-reply@test.speakmate.in>"
    assert smtp.message["To"] == recipient
    assert reset_url in smtp.message.get_content()

    record = json.loads(caplog.records[-1].message)
    assert record["event_name"] == "password_reset_delivery_completed"
    assert record["provider"] == "smtp"
    assert record["outcome"] == "SUCCEEDED"
    assert record["duration_ms"] >= 0
    for secret in (recipient, reset_url, token, "smtp-password-for-transport-test"):
        assert secret not in caplog.text


def test_smtp_delivery_failure_logs_only_safe_error_class(monkeypatch, caplog):
    class FailingSMTP(FakeSMTP):
        def starttls(self, *, context):
            raise RuntimeError("provider response included sensitive transport detail")

    FailingSMTP.instances.clear()
    monkeypatch.setattr(delivery_module.smtplib, "SMTP", FailingSMTP)
    caplog.set_level(logging.WARNING, logger="spoken_english.password_reset_delivery")
    recipient = "private-learner@example.test"
    token = "654321"
    reset_url = token

    with pytest.raises(RuntimeError, match="sensitive transport detail"):
        SmtpPasswordResetDelivery(smtp_settings()).deliver(recipient, reset_url)

    record = json.loads(caplog.records[-1].message)
    assert record["outcome"] == "FAILED"
    assert record["error_type"] == "RuntimeError"
    for secret in (recipient, reset_url, token, "sensitive transport detail"):
        assert secret not in caplog.text


def valid_production_settings(**overrides):
    values = {
        "environment": "production",
        "database_url": "postgresql://db/app",
        "auto_create_tables": False,
        "jwt_secret": "x" * 48,
        "force_https": True,
        "secure_cookies": True,
        "cors_origins": "https://test.speakmate.in",
        "trusted_hosts": "test.speakmate.in",
        "public_frontend_url": "https://test.speakmate.in",
        "redis_required": True,
        "redis_url": "rediss://redis:6379/0",
        "worker_enabled": True,
        "object_storage_backend": "s3",
        "object_storage_bucket": "private",
        "password_reset_delivery_provider": "smtp",
        "password_reset_email_from": "no-reply@test.speakmate.in",
        "smtp_host": "smtp.test.speakmate.in",
        "smtp_port": 587,
        "smtp_username": "smtp-user",
        "smtp_password": "smtp-password-for-config-test",
        "llm_provider": "openai",
        "speech_to_text_provider": "openai",
        "text_to_speech_provider": "openai",
        "language_review_provider": "openai",
        "openai_api_key": "test-key",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_valid_production_password_reset_configuration_is_ready():
    settings = valid_production_settings()
    assert settings.providers_ready() is True
    assert isinstance(build_password_reset_delivery(settings), SmtpPasswordResetDelivery)


@pytest.mark.parametrize(
    ("overrides", "missing_name"),
    [
        ({"public_frontend_url": "http://test.speakmate.in"}, "public_frontend_url"),
        ({"password_reset_email_from": "no-reply@example.com"}, "password_reset_email_from"),
        ({"password_reset_delivery_provider": "development_file"}, "password_reset_delivery_provider"),
        ({"smtp_host": "SMTP_HOST"}, "smtp_host"),
        ({"smtp_port": 0}, "smtp_port"),
        ({"smtp_username": ""}, "smtp_username"),
        ({"smtp_username": "FROM_SECRET_STORE"}, "smtp_username"),
        ({"smtp_password": ""}, "smtp_password"),
        ({"smtp_password": "FROM_SECRET_STORE"}, "smtp_password"),
        ({"smtp_timeout_seconds": 0}, "smtp_timeout_seconds"),
        ({"redis_required": False}, "redis_required"),
        ({"worker_enabled": False}, "worker_enabled"),
        ({"redis_url": ""}, "redis_url"),
        ({"redis_url": "redis://redis:6379/0"}, "redis_url"),
        ({"redis_url": "not-a-redis-url"}, "redis_url"),
        ({"password_reset_minimum_response_milliseconds": 0}, "password_reset_minimum_response_milliseconds"),
        ({"password_reset_job_max_attempts": 0}, "password_reset_job_max_attempts"),
        ({"password_reset_job_retry_delay_seconds": 0}, "password_reset_job_retry_delay_seconds"),
        ({"password_reset_job_idempotency_ttl_seconds": 60}, "password_reset_job_idempotency_ttl_seconds"),
    ],
)
def test_production_password_reset_configuration_fails_closed(overrides, missing_name):
    with pytest.raises(ValueError, match=missing_name):
        valid_production_settings(**overrides)


def test_password_reset_response_floor_delays_only_the_remaining_interval():
    sleeps = []
    enforce_password_reset_response_floor(
        10.0,
        250,
        clock=lambda: 10.05,
        sleeper=sleeps.append,
    )
    assert sleeps == pytest.approx([0.2])

    sleeps.clear()
    enforce_password_reset_response_floor(
        10.0,
        250,
        clock=lambda: 10.3,
        sleeper=sleeps.append,
    )
    assert sleeps == []
