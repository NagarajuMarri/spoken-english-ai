from typing import Protocol


class PasswordResetDelivery(Protocol):
    def deliver(self, recipient: str, verification_code: str) -> None: ...
