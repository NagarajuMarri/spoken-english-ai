from typing import Protocol

from backend.app.language_review.models import LanguageReviewRequest, LanguageReviewResult


class LanguageReviewProvider(Protocol):
    name: str

    def review(self, request: LanguageReviewRequest) -> LanguageReviewResult: ...
