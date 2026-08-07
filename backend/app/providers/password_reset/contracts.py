from typing import Protocol


class PasswordResetDelivery(Protocol):
    def deliver(self, recipient: str, reset_url: str) -> None: ...
