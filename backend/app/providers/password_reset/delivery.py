import json
import logging
import os
import ssl
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path


logger = logging.getLogger("spoken_english.password_reset_delivery")


def _record_smtp_delivery(started_at: float, outcome: str, error_type: str | None = None) -> None:
    """Emit operational evidence without recipient, code, or message content."""
    record = {
        "event_name": "password_reset_delivery_completed",
        "provider": "smtp",
        "outcome": outcome,
        "duration_ms": round((time.perf_counter() - started_at) * 1_000, 3),
    }
    if error_type:
        record["error_type"] = error_type
    (logger.info if outcome == "SUCCEEDED" else logger.warning)(json.dumps(record, separators=(",", ":")))


class DisabledPasswordResetDelivery:
    def deliver(self, recipient: str, verification_code: str) -> None:
        raise RuntimeError("Password-reset delivery is not configured.")


class InMemoryPasswordResetDelivery:
    """Test-only delivery boundary; never selected in production."""

    def __init__(self) -> None:
        self.deliveries: list[dict[str, str]] = []

    def deliver(self, recipient: str, verification_code: str) -> None:
        self.deliveries.append({"recipient": recipient, "verification_code": verification_code})


class DevelopmentFilePasswordResetDelivery:
    """Local-only outbox. The code is written to a mode-0600 file, never logs."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def deliver(self, recipient: str, verification_code: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as outbox:
            outbox.write(json.dumps({"recipient": recipient, "verification_code": verification_code}, separators=(",", ":")) + "\n")
        os.chmod(self.path, 0o600)


class SmtpPasswordResetDelivery:
    def __init__(self, settings) -> None:
        self.settings = settings

    def deliver(self, recipient: str, verification_code: str) -> None:
        started_at = time.perf_counter()
        try:
            message = EmailMessage()
            message["Subject"] = "SpeakMate password reset code"
            message["From"] = self.settings.password_reset_email_from
            message["To"] = recipient
            message.set_content(
                "Hello,\n\nYour SpeakMate password reset code is "
                f"{verification_code}. It expires in 10 minutes and can be used once.\n\n"
                "If you did not request this, ignore this email."
            )
            tls_context = ssl.create_default_context()
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=self.settings.smtp_timeout_seconds) as client:
                client.ehlo()
                client.starttls(context=tls_context)
                client.ehlo()
                client.login(self.settings.smtp_username, self.settings.smtp_password)
                client.send_message(message)
        except Exception as error:
            _record_smtp_delivery(started_at, "FAILED", type(error).__name__)
            raise
        _record_smtp_delivery(started_at, "SUCCEEDED")


def build_password_reset_delivery(settings):
    provider = settings.password_reset_delivery_provider
    if provider == "development_file" and settings.environment != "production":
        return DevelopmentFilePasswordResetDelivery(settings.password_reset_development_outbox_path)
    if provider == "memory" and settings.environment == "test":
        return InMemoryPasswordResetDelivery()
    if provider == "smtp":
        return SmtpPasswordResetDelivery(settings)
    return DisabledPasswordResetDelivery()
