import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


class DisabledPasswordResetDelivery:
    def deliver(self, recipient: str, reset_url: str) -> None:
        raise RuntimeError("Password-reset delivery is not configured.")


class InMemoryPasswordResetDelivery:
    """Test-only delivery boundary; never selected in production."""

    def __init__(self) -> None:
        self.deliveries: list[dict[str, str]] = []

    def deliver(self, recipient: str, reset_url: str) -> None:
        self.deliveries.append({"recipient": recipient, "reset_url": reset_url})


class DevelopmentFilePasswordResetDelivery:
    """Local-only outbox. The reset URL is written to a mode-0600 file, never logs."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def deliver(self, recipient: str, reset_url: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as outbox:
            outbox.write(json.dumps({"recipient": recipient, "reset_url": reset_url}, separators=(",", ":")) + "\n")
        os.chmod(self.path, 0o600)


class SmtpPasswordResetDelivery:
    def __init__(self, settings) -> None:
        self.settings = settings

    def deliver(self, recipient: str, reset_url: str) -> None:
        message = EmailMessage()
        message["Subject"] = "Reset your SpeakMate password"
        message["From"] = self.settings.password_reset_email_from
        message["To"] = recipient
        message.set_content(
            "Use this single-use link to choose a new password. "
            f"It expires soon:\n\n{reset_url}\n\nIf you did not request this, ignore this email."
        )
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as client:
            client.starttls()
            if self.settings.smtp_username:
                client.login(self.settings.smtp_username, self.settings.smtp_password)
            client.send_message(message)


def build_password_reset_delivery(settings):
    provider = settings.password_reset_delivery_provider
    if provider == "development_file" and settings.environment != "production":
        return DevelopmentFilePasswordResetDelivery(settings.password_reset_development_outbox_path)
    if provider == "memory" and settings.environment == "test":
        return InMemoryPasswordResetDelivery()
    if provider == "smtp":
        return SmtpPasswordResetDelivery(settings)
    return DisabledPasswordResetDelivery()
