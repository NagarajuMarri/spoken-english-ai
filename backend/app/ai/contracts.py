from typing import Protocol

from backend.app.ai.models import AIConversationRequest, AIConversationResponse


class AIConversationProvider(Protocol):
    name: str

    def generate(self, request: AIConversationRequest) -> AIConversationResponse: ...
